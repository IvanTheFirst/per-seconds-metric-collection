#!/usr/bin/perl
use File::Basename;
use strict;
use warnings;
# use Data::Dumper;
use IO::Socket;
# auto-flush on socket
$| = 1;

# полезные ссылки
# https://perldoc.perl.org/perldsc - про составные типы данных, массивы массивов, массивы хешей и т.д.

# для корректной работы ctrl-c
# my $CONTINUE = 1;
# $SIG{INT} = sub { $CONTINUE = 0 };

# поддерживаемые выводы информации
my @SUPPORTED_OUTPUT_FORMATS = ('opentsdb','json_flientbit_postgresql');
my $SUPPORTED_OUTPUT_FORMATS_STR = join '|', map { "$_" } @SUPPORTED_OUTPUT_FORMATS;

# поддерживаемые сборщики метрик
my @SUPPORTED_METRIC_COLLECTIONS = ('vmstat','top','iotop','iostat');
my $SUPPORTED_SUPPORTED_METRIC_COLLECTIONS_STR = join '|', map { "$_" } @SUPPORTED_METRIC_COLLECTIONS;

# поддерживаемые протоколы передачи
my @SUPPORTED_PROTOCOLS = ('tcp');
my $SUPPORTED_PROTOCOLS_STR = join '|', map { "$_" } @SUPPORTED_PROTOCOLS;

my $SCRIPT_NAME = basename($0);
$SCRIPT_NAME =~ s/\.pl//;
my $PID_FILE = '/tmp/'.$SCRIPT_NAME.'.pid';

chomp(my $HOSTNAME = `hostname -s`);
my $ips_command = 'for int in `(/sbin/ip route | awk \'/default/ { print $5 }\')`; do ip -br a show dev $int | awk \'// { print $3 }\'| cut -d \'/\' -f 1 ; done';
chomp(my $IPS = `$ips_command`);
$IPS =~ s/\n/|/;

sub args_help {
    my $help_string = "наименования метрик и тегов - фактически столбцов в таблице greptimedb должный быть в нижнем регистре\r\n";
    return "$help_string","Usage:\n".basename($0)." ".$SUPPORTED_OUTPUT_FORMATS_STR." ".$SUPPORTED_SUPPORTED_METRIC_COLLECTIONS_STR." ".$SUPPORTED_PROTOCOLS_STR."://[user:password@]host:port \r\n";
}

sub check_args_outputs {
    my %output;
    # для самого быстрого определения наличия в массиве какого-то значения, преобразуем их в хэши
    my %temp_output_formats;
    my %temp_collectors;
    $temp_output_formats{$_} = 1 for @SUPPORTED_OUTPUT_FORMATS;
    $temp_collectors{$_} = 1 for @SUPPORTED_METRIC_COLLECTIONS;

    if (defined $ARGV[0] and exists($temp_output_formats{$ARGV[0]})){
        $output{'output'} = $ARGV[0];
    } else {
        die "Wrong output collector. ".args_help();
    }

    if (defined $ARGV[1] and exists($temp_collectors{$ARGV[1]})){
        $output{'collector'} = $ARGV[1];
    } else {
        die "Wrong metric collector. ".args_help();
    }

    if (defined $ARGV[2]){
        my ($protocol, $username, $password, $host, $port, $error, $error_str) = parse_uri($ARGV[2]);
        if ($error != 0) {
            die "\n".$error_str."\n".args_help();
        }
        $output{'connection_string'} = $ARGV[2];
        $output{'connection_protocol'} = $protocol;
    } else {
        die "\nConnection string are not defined".args_help();
    }

    return %output;
}

# sub create_message {
#     # my ($output_format, $field_name, $field_value, $timestamp_seconds, $table, %tags) = @_;
#     my (%params) = @_;

#     my $output_format = $params{'output_format'};
#     my $timestamp_seconds = $params{'timestamp_seconds'};
#     my @fields_values = $params{'fields_values'};
#     my @fields = $params{'fields'};
#     my @rows_tags = $params{'rows_tags'};
#     my @rows_metrics = $params{'rows_metrics'};
    
#     my %tags = ('hostname' => $HOSTNAME, 'ips' => $IPS);

#     print "create_message - ",Dumper(\%params, \@fields_values, \@fields);

#     my @output;

#     my %temp_fields_values;
#     # for my $i (0 .. $#fields){
#     #     $temp_fields_values{$fields[$i]} = $fields_values[$i];
#     # }
#     @temp_fields_values{@fields} = @fields_values; # создание хэша из двух массивов для получения связки поля и значения
#     print "create_message - ",Dumper(\%temp_fields_values);
#     print "create_message - ",Dumper(\@rows_metrics);
#     if ($#rows_tags > 0) {
#         %tags = (%tags , map { $_ => $temp_fields_values{$_} } @rows_tags); # значения только тегов соединяем с общими тегами
#     }
#     my %metrics = map { $_ => $temp_fields_values{$_} } @rows_metrics; # значения только метрик

#     if ($output_format eq 'opentsdb') {
#         # формат сообщения
#         # put sys.cpu.system 1667892080 3 host=web01 dc=hz
#         my $output_tags = join(' ', map{"$_=$tags{$_}"} keys %tags);
#         for my $metric_name (keys %metrics) {
#             push @output , "put " .$metric_name. " " .$timestamp_seconds. " " .$metrics{$metric_name}. " " .$output_tags. "\n";
#         }
#     }

#     return @output;
# }

sub metrics_collector {
    my (%params) = @_;

    my $output_format = $params{'output_format'};
    my $connection_string = $params{'connection_string'};
    my $connection_protocol = $params{'connection_protocol'};
    # my %common_tags = %{$params{'common_tags'}};
    my $table = $params{'table'};
    my $cmd = $params{'cmd'};
    my @rows_fields = @{ $params{'rows_fields'} };
    my @rows_regexp = @{ $params{'rows_regexp'} };
    my @rows_tags = @{ $params{'rows_tags'} };
    my @rows_metrics = @{ $params{'rows_metrics'} } ;
    
    # print 'metrics_collector - ', Dumper( \%params );

    open(my $out, "-|", $cmd);

    my $connection; # переменная для сохранения подключения, чтобы не переподключаться

    # для ctrl-c , но что-то выдаёт предупреждение - Value of <HANDLE> construct can be "0"; test with defined()
    # while (my $row = <$out> and $CONTINUE) {
    while (my $row = <$out>) {
        my $timestamp_seconds = time;#."000000000";#scalar localtime time;
        for my $i (0 .. $#rows_regexp) {
            if ( my @temp_fields_values = $row =~ m/$rows_regexp[$i]/) {
                
                @temp_fields_values = map {replace($_,$output_format)} @temp_fields_values; # замена не правильных симовлов

                my %fields_values;
                my %tags = ('hostname' => $HOSTNAME, 'ips' => $IPS);
                my %metrics;
                my @messages;
                
                @fields_values{@{ $rows_fields[$i] }} = @temp_fields_values;
                if (scalar @{ $rows_tags[$i] } > 0) {
                    %tags = (%tags , map { $_ => $fields_values{$_} } @{ $rows_tags[$i] }); # значения только тегов соединяем с общими тегами
                };
                if (scalar @{ $rows_metrics[$i] } > 0) {
                    %metrics = map { $_ => $fields_values{$_} } @{ $rows_metrics[$i] };
                };

                if ($output_format eq 'opentsdb') {
                    # формат сообщения
                    # put sys.cpu.system 1667892080 3 host=web01 dc=hz
                    my $output_tags = join(' ', map{"$_=$tags{$_}"} keys %tags);
                    for my $metric_name (keys %metrics) {
                        push @messages , "put " .$table. "." .$metric_name. " " .$timestamp_seconds. " " .$metrics{$metric_name}. " " .$output_tags. "\r\n";
                    };
                };

                if ($output_format eq 'json_flientbit_postgresql') {
                    # формат сообщения
                    # {'ts':1667892080, 'tag':'sys.cpu.system', 'data':{'metric':'sys.cpu.system', 'value':3 ,'tags':{'host':'web01','dc':'hz'} } }
                    # put sys.cpu.system 1667892080 3 host=web01 dc=hz
                    my $output_tags = join(', ', map{'"'.$_.'":"'.$tags{$_}.'"'} keys %tags);
                    for my $metric_name (keys %metrics) {
                        push @messages , '{"source":"'.$table.'", "metric":"'.$metric_name.'","value":'.$metrics{$metric_name}.',"tags": { '.$output_tags.' } }'."\r\n";
                    };
                };

                for (@messages) {
                    $connection = send_message($connection, $output_format, $connection_string, $connection_protocol, $_);
                };
            };
        };
    };   
};

sub send_message {
    my ($connection, $output_format, $connection_string, $connection_protocol, $message) = (shift,shift,shift,shift,shift);
    
    if ($connection_protocol eq "tcp"){
        if ($connection) {
            my $result;
            # типа обработчик исключений, но пишут, что со спецэффектами
            eval { 
                $result = $connection->send($message);
            };
            if ($@) {
                $connection = undef;
                print "Probably connection to server $connection_string lost. Native error - $@";
            };
        }
        else {
            my ($protocol, $username, $password, $host, $port, $error, $error_str) = parse_uri($connection_string);
            #my @host_port = split (/:/,$connection_string);
    		$connection = IO::Socket::INET->new(
        		Proto    => 'tcp',
        		PeerPort => $port,
        		PeerAddr => $host
            );
	    }
    }
    return $connection;
}

sub parse_uri {
    my ($uri) = (shift);
    my $protocol = "";
    my $username = "";
    my $password = "";
    my $host = "";
    my $port = 0;
    my $error = 0;
    my $error_str = "";

    for my $supported_protocol (@SUPPORTED_PROTOCOLS) {
        if ($supported_protocol eq 'tcp' or $supported_protocol eq 'udp') {
            if (my @temp_uri_fields = $uri =~ m/$supported_protocol:\/\/(\S+):(\d+)/) {
                $protocol = $supported_protocol;
                $host = $temp_uri_fields[0];
                $port = $temp_uri_fields[1];
            }
            else {
                $error = 2;
                $error_str = "for protocol tcp|udp can't parse host and port";
            }
            last; # сразу выходим из цикла, всегда всего один протокол и одна строка подключения
        }
        else {
            $error = 1;
            $error_str = "can't find any for protocol tcp|udp can't parse host and port";
        }
    }
    
    return $protocol, $username, $password, $host, $port, $error, $error_str;
}

sub replace {
    my ($value, $output_format) = (shift,shift);
    
    $value =~ s/,/./;

    # if ($output_format eq 'opentsdb') {
    #     $value =~ s/,/./;
    # }

    return $value;
}

sub prepare {
    my (@params) = (@_);

    my $collector = $params[0];
    my @temp_parser = @{$params[1]};

    # print "Collector $collector\n";
    #print Dumper(@temp_parser);

    my %output;

    my @tags;
    my @metrics;
    my @fields; 
    my @regexp;

    for my $i (0 .. $#temp_parser){

        my @temp_tags;
        my @temp_metrics;

        my @temp_fields = ( map{(split /:/, "$_")[2]} sort keys %{$temp_parser[$i]});
        for my $key (sort keys %{$temp_parser[$i]}) {
            my $type = (split /:/, $key )[1]; 
            if ( $type eq 'TAG') {
                push @temp_tags, (split /:/, $key)[2] ;
            } 
            elsif ($type eq 'METRIC') {
                push @temp_metrics, (split /:/, $key)[2] ;
            }
        }
        my $temp_regexp = join('',  map{"$temp_parser[$i]{$_}"} sort keys %{$temp_parser[$i]} );
        print "command $collector tags, columns and regexps:\n", join(", ", @temp_tags), "\n", join(", ", @temp_fields), "\n", "$temp_regexp\n";
        $fields[$i] = [ @temp_fields ];
        $metrics[$i] = [ @temp_metrics ];
        $regexp[$i] = $temp_regexp;
        $tags[$i] = [ @temp_tags ];
    }

    $output{'rows_fields'} = [ @fields ];
    $output{'rows_regexp'} = [ @regexp ] ;
    $output{'rows_tags'} = [ @tags ] ;
    $output{'rows_metrics'} = [ @metrics ] ;

    # print Dumper(\%output);

    return %output;
}

sub vmstat_templates {

    my %output;

    # Оюидаемый вывод команды
    # --procs-- -----------------------memory---------------------- ---swap-- -----io---- -system-- --------cpu--------
    # r    b         swpd         free        inact       active   si   so    bi    bo   in   cs  us  sy  id  wa  st
    my @vmstat_parser = ({  '01:METRIC:procs_r'         => '^\s*(\d+)\s+',
                            '02:METRIC:procs_b'         => '(\d+)\s+',
                            '03:METRIC:memory_swpd_b'   => '(\d+)\s+',
                            '04:METRIC:memory_free_b'   => '(\d+)\s+',
                            '05:METRIC:memory_inact_b'  => '(\d+)\s+',
                            '06:METRIC:memory_active_b' => '(\d+)\s+',
                            '07:METRIC:swap_si'         => '(\d+)\s+',
                            '08:METRIC:swap_so'         => '(\d+)\s+',
                            '09:METRIC:io_bi'           => '(\d+)\s+',
                            '10:METRIC:io_bo'           => '(\d+)\s+',
                            '11:METRIC:system_in'       => '(\d+)\s+',
                            '12:METRIC:system_cs'       => '(\d+)\s+',
                            '13:METRIC:cpu_us'          => '(\d+)\s+',
                            '14:METRIC:cpu_sy'          => '(\d+)\s+',
                            '15:METRIC:cpu_id'          => '(\d+)\s+',
                            '16:METRIC:cpu_wa'          => '(\d+)\s+',
                            '17:METRIC:cpu_st'          => '(\d+)\s*' });

    $output{'table'} = 'linux_vmstat';
    $output{'version'} = '*'; # для vmstat from procps-ng 3.3.17, но пока для всех версий
    $output{'cmd'} = 'vmstat -w -a -n -S b 1';
    $output{'parser'} = [ @vmstat_parser ];

    return %output;
}

sub top_templates {
    # Оюидаемый вывод команды
    # top - 21:43:56 up 3 days, 11:21,  1 user,  load average: 0,18, 0,06, 0,02
    # Tasks: 257 total,   1 running, 255 sleeping,   0 stopped,   1 zombie
    # %Cpu(s):  9,6 us,  2,1 sy,  0,0 ni, 88,3 id,  0,0 wa,  0,0 hi,  0,0 si,  0,0 st
    # МиБ Mem :   7938,3 total,    705,7 free,   3800,1 used,   3432,5 buff/cache
    # МиБ Swap:    976,0 total,    976,0 free,      0,0 used.   3722,6 avail Mem 

    #  PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
    # 2450 root      20   0 1058332 721340 136724 S   6,9   8,9  36:05.02 Xorg
    # 3099 user+     20   0  499256  68348  33452 S   2,0   0,8  14:35.21 mintreport-tray
    # 4667 user+     20   0  180,9g 702320 215352 S   2,0   8,6  36:41.51 Telegram
    # 2928 user+     20   0  229896  27596  20816 S   1,0   0,3   0:49.24 xfsettingsd
    my %output;

    $output{'table'} = 'linux_top';
    $output{'version'} = '*'; # procps-ng 3.3.17
    $output{'cmd'} = 'top -bi -d 1';
    my @top_parser =({  '01:TAG:pid'            => '^\s*(\d+)\s+', 
                        '02:TAG:user'           => '(\S+)\s+',
                        '03:METRIC:vert'        => '\d+\s+\d+\s+(\d+)\s+', # пропуск для PR и NI}
                        '04:METRIC:res'         => '(\d+)\s+',
                        '05:METRIC:shr'         => '(\d+)\s+',
                        '06:METRIC:cpu_percent' => '\w+\s+(\S+)\s+', # пропуск S
                        '07:METRIC:mem_percent' => '(\S+)\s+',
                        '08:TAG:command'        => '\S+\s+(\w+)', },# пропуск для TIME+ 

                      { '01:METRIC:la1'  => '^.*load average:\s(\d+,\d+),', 
                        '02:METRIC:la5'  => '\s(\d+,\d+),',
                        '03:METRIC:la15' => '\s(\d+,\d+)',} ,

                      { '01:METRIC:cpu_us' => '^%Cpu\(s\):\s+(\d+,\d+) us,', 
                        '02:METRIC:cpu_sy' => '\s+(\d+,\d+) sy,',
                        '03:METRIC:cpu_ni' => '\s+(\d+,\d+) ni,',
                        '04:METRIC:cpu_id' => '\s+(\d+,\d+) id,',
                        '05:METRIC:cpu_wa' => '\s+(\d+,\d+) wa,',
                        '06:METRIC:cpu_hi' => '\s+(\d+,\d+) hi,',
                        '07:METRIC:cpu_si' => '\s+(\d+,\d+) si,',
                        '08:METRIC:cpu_st' => '\s+(\d+,\d+) st',}
                     );

    $output{'parser'} = [ @top_parser ];

    return %output;
}

sub iotop_templates {
    # Оюидаемый вывод команды
    #   Total DISK READ:    0,00 K/s |   Total DISK WRITE:    7,85 K/s
    # Current DISK READ:    0,00 K/s | Current DISK WRITE:  204,21 K/s
    #    PID PRIO     USER   DISK READ  DISK WRITE SWAPIN     IO COMMAND
    # 515777 be/4     user    0,00 K/s    3,93 K/s 0,00 % 0,00 % greptime

    my %output;

    $output{'table'} = 'linux_iotop';
    $output{'version'} = '*'; # iotop 1.21
    $output{'cmd'} = 'sudo iotop -o -b -k -d 1 -P';
    my @iotop_parser =({'01:METRIC:total_disk_read'  => '^\s*Total DISK READ:\s+(\d+,\d+) K\/s\s+\|', 
                        '02:METRIC:total_disk_write' => '\s+Total DISK WRITE:\s+(\d+,\d+) K\/s',
                       },

                       {'01:METRIC:current_disk_read'  => '^\s*Current DISK READ:\s+(\d+,\d+) K\/s\s+\|', 
                        '02:METRIC:current_disk_write' => '\s+Current DISK WRITE:\s+(\d+,\d+) K\/s',
                       },

                       {'01:TAG:pid'               => '^\s*(\d+)\s+', 
                        '02:TAG:prio'              => '(\S+)\s+',
                        '03:TAG:user'              => '(\S+)\s+',
                        '04:METRIC:disk_read'      => '(\d+,\d+) K\/s\s+',
                        '05:METRIC:disk_write'     => '(\d+,\d+) K\/s\s+',
                        '06:METRIC:swapin_percent' => '(\d+,\d+) %\s+',
                        '07:METRIC:io_percent'     => '(\d+,\d+) %\s+',
                        '08:TAG:command'           => '(\S+)',
                       }
                     );

    $output{'parser'} = [ @iotop_parser ];

    return %output;
}


sub iostat_templates {
    # Оюидаемый вывод команды
    # Linux 5.15.0-91-generic (hostname) 	18.01.2024 	_x86_64_	(1 CPU)
    #
    # avg-cpu:  %user   %nice %system %iowait  %steal   %idle
    #            2,32    0,00    0,87    0,09    0,00   96,72
    #
    # Device            r/s     rkB/s   rrqm/s  %rrqm r_await rareq-sz     w/s     wkB/s   wrqm/s  %wrqm w_await wareq-sz     d/s     dkB/s   drqm/s  %drqm d_await dareq-sz     f/s f_await  aqu-sz  %util
    # sr0              0,00      0,00     0,00   0,00    1,18     0,14    0,00      0,00     0,00   0,00    0,00     0,00    0,00      0,00     0,00   0,00    0,00     0,00    0,00    0,00    0,00   0,00
    # sda              0,26      6,01     0,09  26,63    0,41    23,47    2,89     48,97     1,95  40,31    0,58    16,94    0,00      0,00     0,00   0,00    0,00     0,00    0,76    0,35    0,00   0,21
    # sda1             0,00      0,00     0,00   0,00    0,15     4,00    0,00      0,00     0,00   0,00    0,00     0,00    0,00      0,00     0,00   0,00    0,00     0,00    0,00    0,00    0,00   0,00
    # sda2             0,00      0,01     0,00   8,98    0,76    40,07    0,00      0,00     0,00   0,00    0,00     0,50    0,00      0,00     0,00   0,00    0,00     0,00    0,00    0,00    0,00   0,00
    # sda3             0,00      0,01     0,00  17,87    0,85    41,99    0,00      0,00     0,00  35,14    0,21     4,83    0,00      0,00     0,00   0,00    0,00     0,00    0,00    0,00    0,00   0,00
    # sda4             0,25      5,97     0,09  26,68    0,40    23,43    2,89     48,97     1,95  40,31    0,58    16,94    0,00      0,00     0,00   0,00    0,00     0,00    0,00    0,00    0,00   0,21
    # sda4_crypt       0,35      5,97     0,00   0,00    0,69    17,18    4,82     48,97     0,00   0,00    2,41    10,16    0,00      0,00     0,00   0,00    0,00     0,00    0,00    0,00    0,01   0,21
    # vgmint-root      0,35      5,94     0,00   0,00    0,69    17,17    4,46     48,65     0,00   0,00    2,30    10,90    0,00      0,00     0,00   0,00    0,00     0,00    0,00    0,00    0,01   0,21
    # vgmint-swap_1    0,00      0,01     0,00   0,00    1,48     8,49    0,08      0,32     0,00   0,00    7,90     4,00    0,00      0,00     0,00   0,00    0,00     0,00    0,00    0,00    0,00   0,00

    my %output;

    $output{'table'} = 'linux_iostat';
    $output{'version'} = '*'; # sysstat, версия 12.5.2
    $output{'cmd'} = 'iostat -zxNp 1';
    my @iostat_parser = ({  '01:TAG:disk'               => '^(\S+)\s+',
                            '02:METRIC:r_s'             => '(\d+,\d+)\s+',
                            '03:METRIC:rkb_s'           => '(\d+,\d+)\s+',
                            '04:METRIC:rrqm_s'          => '(\d+,\d+)\s+',
                            '05:METRIC:rrqm r_percent'  => '(\d+,\d+)\s+',
                            '06:METRIC:r_await'         => '(\d+,\d+)\s+',
                            '07:METRIC:rareq-sz'        => '(\d+,\d+)\s+',
                            '08:METRIC:w_s'             => '(\d+,\d+)\s+',
                            '09:METRIC:wkb_s'           => '(\d+,\d+)\s+',
                            '10:METRIC:wrqm_s'          => '(\d+,\d+)\s+',
                            '11:METRIC:wrqm_percent'    => '(\d+,\d+)\s+',
                            '12:METRIC:w_await'         => '(\d+,\d+)\s+',
                            '13:METRIC:wareq-sz'        => '(\d+,\d+)\s+',
                            '14:METRIC:d_s'             => '(\d+,\d+)\s+',
                            '15:METRIC:dkb_s'           => '(\d+,\d+)\s+',
                            '16:METRIC:drqm_s'          => '(\d+,\d+)\s+',
                            '17:METRIC:drqm_percent'    => '(\d+,\d+)\s+',
                            '18:METRIC:d_await'         => '(\d+,\d+)\s+',
                            '19:METRIC:dareq-sz'        => '(\d+,\d+)\s+',
                            '20:METRIC:f_s'             => '(\d+,\d+)\s+', 
                            '21:METRIC:f_await'         => '(\d+,\d+)\s+', 
                            '22:METRIC:aqu-sz'          => '(\d+,\d+)\s+', 
                            '23:METRIC:util_percent'    => '(\d+,\d+)'
                        });

    $output{'parser'} = [ @iostat_parser  ];

    return %output;
}


sub main {
    my @parser;
    my %metric_collection_settings;

    my %arguments = check_args_outputs();

    $metric_collection_settings{'output_format'} = $arguments{'output'};
    $metric_collection_settings{'connection_string'} = $arguments{'connection_string'};
    $metric_collection_settings{'connection_protocol'} = $arguments{'connection_protocol'};

    if ($arguments{'collector'} eq 'vmstat') {
        my %settings = vmstat_templates();
        @parser = @{ $settings{'parser'} };
        $metric_collection_settings{'cmd'} = $settings{'cmd'};
        $metric_collection_settings{'table'} = $settings{'table'};
    }
    elsif ($arguments{'collector'} eq 'top'){
        my %settings = top_templates();
        @parser = @{ $settings{'parser'} };
        $metric_collection_settings{'cmd'} = $settings{'cmd'};
        $metric_collection_settings{'table'} = $settings{'table'};
    }
    elsif ($arguments{'collector'} eq 'iotop'){
        my %settings = iotop_templates();
        @parser = @{ $settings{'parser'} };
        $metric_collection_settings{'cmd'} = $settings{'cmd'};
        $metric_collection_settings{'table'} = $settings{'table'};
    }
    elsif ($arguments{'collector'} eq 'iostat'){
        my %settings = iostat_templates();
        @parser = @{ $settings{'parser'} };
        $metric_collection_settings{'cmd'} = $settings{'cmd'};
        $metric_collection_settings{'table'} = $settings{'table'};
    }
    else {
        die args_help();
    }

    my (%parser_settings) = prepare( $arguments{'collector'} , \@parser);
    
    $metric_collection_settings{'rows_fields'} = $parser_settings{'rows_fields'};
    $metric_collection_settings{'rows_regexp'} = $parser_settings{'rows_regexp'};
    $metric_collection_settings{'rows_tags'} = $parser_settings{'rows_tags'};
    $metric_collection_settings{'rows_metrics'} = $parser_settings{'rows_metrics'};
    
    metrics_collector( %metric_collection_settings );
};

main()