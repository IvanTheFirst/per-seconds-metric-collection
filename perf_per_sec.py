#!/data/python/3.11.4/bin/python3

from threading import Thread
from subprocess import Popen, PIPE, STDOUT, check_output
import logging
import queue
import yaml
from argparse import ArgumentParser
import re
import sys
import time
import json
# import sqlite3
# import duckdb
# import pandas as pd
# from clickhouse_driver import Client
# import numpy as np

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(lineno)s - %(funcName)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

OUTPUT_READY = {} # ключ - имя вывода, значение - True/False

class Configuration:
    def __init__(self):
        self.DEFAULT_CONFIG_PATH = "config.yaml"
        self.SAMPLE_CONFIG = """# DEBUG, INFO, WARNING, ERROR, CRITICAL, default NOTSET
log_level: "DEBUG"

commands:
  vmstat:
    cmd_ver: vmstat -V
    versions:
      - version_regexp: .*3.3.\d+.*
        cmd: vmstat -w -a -n -S b 1
        parsers:
          - name: default
            value: {'01:METRIC:procs_r'         :'^\s*(\d+)\s+',
                    '02:METRIC:procs_b'         : '(\d+)\s+',
                    '03:METRIC:memory_swpd_b'   : '(\d+)\s+',
                    '04:METRIC:memory_free_b'   : '(\d+)\s+',
                    '05:METRIC:memory_inact_b'  : '(\d+)\s+',
                    '06:METRIC:memory_active_b' : '(\d+)\s+',
                    '07:METRIC:swap_si'         : '(\d+)\s+',
                    '08:METRIC:swap_so'         : '(\d+)\s+',
                    '09:METRIC:io_bi'           : '(\d+)\s+',
                    '10:METRIC:io_bo'           : '(\d+)\s+',
                    '11:METRIC:system_in'       : '(\d+)\s+',
                    '12:METRIC:system_cs'       : '(\d+)\s+',
                    '13:METRIC:cpu_us'          : '(\d+)\s+',
                    '14:METRIC:cpu_sy'          : '(\d+)\s+',
                    '15:METRIC:cpu_id'          : '(\d+)\s+',
                    '16:METRIC:cpu_wa'          : '(\d+)\s+',
                    '17:METRIC:cpu_st'          : '(\d+)\s*' }

output:
    clickhouse:
        ## clickhouse connection scheme secure True/False
        secure: False
        ## clickhouse host and port (secure port - 9440, insecure - 8123)
        host: "127.0.0.1:8123"
        login: "monitoring"
        password: "parol"
        ## clickhouse cluster to create tables, leave empty or none for local database
        # cluster: "monitoring"
        ttl_days: 720
        ## ReplicatedMergeTree - for cluster, MergeTree for local
        table_engine: "MergeTree"
        database_name: "metrics"
        reconnect_timeout_sec: 60

    # tcp:
    #     host: "server:9440"
    #     format: json

    # local_duckdb:
    #     file_path: asd
    #     ttl_days: 100

    stdout:
        format: json

"""

    def create_config(self, create_config_path):
        f = open(create_config_path, mode="w")
        f.write(self.SAMPLE_CONFIG)
        f.close()

    def read(self) -> dict:
        parser = ArgumentParser()
        parser.add_argument("-c", "--config", dest="config",
                            help="path to configuration file",
                            required=False,
                            default=self.DEFAULT_CONFIG_PATH)
        parser.add_argument("--create_config", dest="create_config",
                            help=f"Create default config {self.DEFAULT_CONFIG_PATH}",
                            default='-1',
                            required=False)
        args = parser.parse_args()
        configuration_file = vars(args)['config']
        create_config_path = vars(args)['create_config']
        if create_config_path != '-1':
            self.create_config(create_config_path)
            sys.exit()
        with open(configuration_file, 'r') as f:
            output = yaml.safe_load(f)
        for key in vars(args).keys():
            output[key] = vars(args)[key]
        return output

def command_prepare(commands:dict) -> dict:

    output = {}

    for command_name in commands.keys():
        
        cmd_ver_output = ''

        try:
            cmd_ver_output = check_output(commands[command_name]['cmd_ver'].split(' '))
        except Exception as exceptionError:
            logger.error(f"Command {commands[command_name]['cmd_ver']} can't be started. Error message: {exceptionError}")
            sys.exit(1)
        
        logger.debug(f'command version: {cmd_ver_output}')

        for version in commands[command_name]['versions']:
            if re.match(version['version_regexp'],str(cmd_ver_output)):
                output[command_name] = {'cmd_line': version['cmd'],'parser':{}}

                logger.info(f"Command {version['cmd']} tags, columns and regexps:")

                for i in range(len(version['parsers'])):
                    temp_parser = version['parsers'][i]
                    output[command_name]['parser'][temp_parser['name']] = {'fields':[],
                                                                           'regexp':"",
                                                                           'tags':[],
                                                                           'metrics':[]}
                    temp_tags = []
                    temp_metrics = []

                    temp_regexp = ''.join( [ temp_parser['value'][key] for key in sorted(temp_parser['value'].keys()) ] )
                    temp_fields = [ key.split(':')[2] for key in sorted(temp_parser['value'].keys()) ]

                    for key in sorted(temp_parser['value'].keys()):
                        type = key.split(':')[1]
                        if type == 'TAG':
                            temp_tags.append(key.split(':')[2])
                        elif type == 'METRIC':
                            temp_metrics.append(key.split(':')[2])

                    
                    logger.info("TAGS: " + ", ".join(temp_tags))
                    logger.info("FIELDS: " + ", ".join(temp_fields))
                    logger.info(f"REGEXP: {temp_regexp}")
                    
                    output[command_name]['parser'][temp_parser['name']]['fields'] = temp_fields
                    output[command_name]['parser'][temp_parser['name']]['regexp'] = temp_regexp
                    output[command_name]['parser'][temp_parser['name']]['tags'] = temp_tags
                    output[command_name]['parser'][temp_parser['name']]['metrics'] = temp_metrics
                    
                break

    return output

def run_commands(cmd_name:str,command_parser:dict,output_queues:dict) -> None:
    try:
        command = command_parser['cmd_line']
        process = Popen(command.split(' '), bufsize=1, universal_newlines=True, stdout=PIPE, stderr=STDOUT)

        if process.returncode:
            logger.debug(f"Cmd command {command} was spawned successfully, yet an error occuring during the execution of the command")

        for line in iter(process.stdout.readline, ''):
            if line != '': 
                timestamp = time.time()
                for parser_name in command_parser['parser'].keys():
                    # parser_name - имя парсера, связка команда - парсер формирует набор однотипных данных
                    # поэтому надо их позже собирать в отдельные списки, а сейчас просто отправлять в очередь вместе
                    parser = command_parser['parser'][parser_name]
                    temp_fields_values = re.findall(parser['regexp'],line.rstrip())
                    if temp_fields_values :
                        fields_values = { parser['fields'][j]: temp_fields_values[0][j] for j in range(len(parser['fields'])) }
                        tags = {tag: fields_values[tag] for tag in parser['tags']}
                        metrics = {metric: to_float_or_int_or_str(fields_values[metric]) for metric in parser['metrics']}
                        metrics['timestamp'] = timestamp
                        for output in output_queues.keys():
                            if OUTPUT_READY[output]:
                                output_queues[output].put((cmd_name,parser_name,tags,metrics))

    except Exception as exceptionError:
        logger.error(f"With command {command} run or parse something goes wrong. ERROR: {exceptionError}")

def to_float_or_int_or_str(metric_value:str) -> int|float|str:

    metric_value = metric_value.replace(",", ".")
    try:
        return int(metric_value)
    except:
        pass
    try:
        return float(metric_value)
    except:
        pass

    return metric_value

# def outputs(instance, methodname, method_args=None, method_kwargs=None):
#     method = getattr(instance, methodname)
#     if method_args is None:
#         method_args = ()
#     if method_kwargs is None:
#         method_kwargs = {}
#     method(*method_args, **method_kwargs)
#     # def func():
#     #     return method(*method_args, **method_kwargs)
#     # return func

class Output():
    def stdout(self, output:dict, output_queue:queue.Queue, stop) -> None:
        while True:
            if not output_queue.empty():
                (cmd,parser_name,tags,metrics) = output_queue.get()
                if output['format'] == 'json':
                    print(json.dumps(tags|metrics))
            if stop():
                break

    def clickhouse(self, output:dict, output_queue:queue.Queue, stop) -> None:

        click = clickhouse_helper(dbsecure = output['secure'],
                                dbhost = output['host'],
                                dbuser = output['login'],
                                dbpass = output['password'],
                                dbname = output['database_name'],
                                ttl = output['ttl_days'],
                                table_engine = output['table_engine'],
                                reconnect_timeout_sec = output['reconnect_timeout_sec']
                                )
        while True:
            OUTPUT_READY[output] = click.connection_status
            if not click.connection_status:
                click.connect_to_db()
                click.get_db_scheme()
                OUTPUT_READY[output] = click.connection_status

            start_time = time.time()
            messages = {}
            # суть в том, что для каждой связки команда - парсер даннные однотипные, 
            # это удобно для последующей отправки данных в БД
            while not output_queue.empty():
                (cmd_name, parser_name, tags,metrics) = output_queue.get()
                if cmd_name not in messages.keys(): 
                    messages[cmd_name + "_" + parser_name] = []
                messages[cmd_name].append(tags|metrics)

            table_to_create = list(set(messages.keys()) - set(click.db_scheme.keys()))
            if len(table_to_create) > 0:
                for table in table_to_create:
                    for insert in click.schema_inserts(messages[table],table):
                        click.send(insert)

            for cmd_parser in messages.keys():
                click.send(messages[cmd_parser],table=cmd_parser)

            if stop():
                break
            
            # всегда ожидание 1 секунда
            if (time.time() - start_time) < 1:
                time.sleep(time.time() - start_time)

class clickhouse_helper():

    from clickhouse_driver import Client
    import numpy as np
    import pandas as pd
    
    def __init__(self,
                 dbsecure:str,
                 dbhost:str,
                 dbuser:str,
                 dbpass:str,
                 dbname:str,
                 ttl:int,
                 table_engine:str,
                 chcluster: str = '',
                 reconnect_timeout_sec:int = 60
                 ):
        self.dbsecure = dbsecure
        self.dbhost = dbhost
        self.dbuser = dbuser
        self.dbpass = dbpass
        self.dbname = dbname
        self.ttl = ttl
        self.table_engine = table_engine
        self.chcluster = chcluster
        self.reconnect_timeout_sec = reconnect_timeout_sec
        self.db_scheme = {}
        self.connection_status = False

    def connect_to_db(self):
        
        while not self.connection_status:
            try:
                [host, port] = self.dbhost.split(':')
                self.click_client = self.Client(user=self.dbuser, password=self.dbpass,
                                            host=host, port=port, secure=self.dbsecure,
                                            settings={"use_numpy":True})
                result = self.click_client.execute('select 1')
                self.connection_status = True
                logger.info(f'Connected to clickhouse {self.dbhost}')
            except Exception as e:
                logger.error(f"Can't connect to clickhouse {self.dbhost}. error: {str(e)}")
                self.connection_status = False
            time.sleep(self.reconnect_timeout_sec)

    # def check_connection(self) -> bool:
    #     try:
    #         result = self.click_client.execute('select 1')
    #         return True
    #     except:
    #         return False

    def get_db_scheme(self):
        query = f'SHOW TABLES FROM `{self.dbname }`'
        result = self.click_client.execute(query)
        tables = []
        for table in result:
            tables.append(table[0])
        dict_tables = {}
        for table in tables:
            if table not in dict_tables.keys():
                dict_tables[table] = []
            query = f'describe table `{self.dbname }`.`{table}`'
            result = self.click_client.execute(query)
            dict_tables[table] = []
            for row in result:
                dict_tables[table].append(row[0])
        self.db_scheme = dict_tables.copy()
        logger.info(f'got database {self.dbname } schema ')

    def schema_inserts(self,elements:list,table_name:str,timestamp_field_name:str=None):
        df = self.pd.DataFrame(elements)
        if not timestamp_field_name:
            timestamp_field_name = 'timestamp'
        types = {}
        for col_name in df:
            if df.dtypes[col_name] == object:
                types[col_name] = 'LowCardinality(String) CODEC(ZSTD)'
            elif df.dtypes[col_name] == bool:
                df[col_name] = df[col_name].replace({True: 1, False: 0})
                types[col_name] = 'UInt8'
            elif df.dtypes[col_name] == self.np.dtype('datetime64[ns]'):
                types[col_name] = 'DateTime64 CODEC(DoubleDelta,ZSTD)'
            elif df.dtypes[col_name] == self.np.half:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.float_:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.float64:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.double:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.single:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.float16:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.float32:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            # deprecated DeprecationWarning: `self.np.int0` is a deprecated alias for `self.np.intp`.  (Deprecated NumPy 1.24)
            # elif df.dtypes[col_name] == self.np.int0:
            #     types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.int16:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.int32:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.int64:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.int8:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.int_:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.intc:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.integer:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.integer:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.intp:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.signedinteger:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.short:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.longlong:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.uint:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.uint0:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.uint16:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.uint32:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.uint64:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.uint8:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.uintc:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.uintp:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.unsignedinteger:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.ushort:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            elif df.dtypes[col_name] == self.np.ulonglong:
                types[col_name] = 'Float64 CODEC(Gorilla,ZSTD)'
            else:
                types[col_name] = 'String'
        schema_inserts = []
        if table_name not in self.db_scheme.keys():
            create_table = self.pd.io.sql.get_schema(df, table_name, dtype=types) + str("\n".join([
                f"ENGINE = {self.table_engine} ORDER BY {timestamp_field_name}",
                f"TTL toDateTime({timestamp_field_name}) + INTERVAL {self.ttl} DAY DELETE"]))
            create_table = create_table.replace('CREATE TABLE ', f'CREATE TABLE IF NOT EXISTS {self.dbname}.')
            if self.chcluster:
                create_table = create_table[:create_table.find('(')] + f' on cluster {self.chcluster} (' + create_table[
                                                                                                       create_table.find(
                                                                                                           '(') + 1:]
            else:
                create_table = create_table[:create_table.find('(')] + '(' + create_table[ create_table.find('(') + 1:]
            logger.debug(create_table)
            schema_inserts.append(create_table)
            self.db_scheme[table_name] = list(types.keys())
        else:
            columns_to_add = list(set(df.columns) - set(self.db_scheme[table_name]))
            if len(columns_to_add) > 0:
                for colunm in columns_to_add:
                    self.db_scheme[table_name].append(colunm)
                    if self.chcluster:
                        schema_inserts.append(
                            f"""ALTER TABLE `{self.dbname}`.`{table_name}` ON CLUSTER {self.chcluster} ADD COLUMN IF NOT EXISTS `{colunm}` {types[colunm]} """)
                    else:
                        schema_inserts.append(
                            f"""ALTER TABLE `{self.dbname}`.`{table_name}` ADD COLUMN IF NOT EXISTS `{colunm}` {types[colunm]} """)
        return schema_inserts

    def send(self,insert:str|list,table_name:str=None):
        try:
            if isinstance(insert,str) and not table_name:
                self.click_client.execute(insert)
            else:
                df = self.pd.DataFrame(insert)
                self.click_conn.click_client.insert_dataframe(f"INSERT INTO `{self.dbname}`.`{table_name}` VALUES ",df)
        
        except Exception as e:
            # SOCKET_TIMEOUT = 209
            # NETWORK_ERROR = 210
            error_code = ""
            try:
                error_code = str(e).split()[1].replace('Code:', '')[:-1]
            except:
                pass
            if error_code in ['209', '210']:
                logger.error(f"Network connection to clickhouse error {str(e)}")
            else:
                logger.warning(f"writting to clickhouse error {str(e)}")
            self.connection_status = False


def main():
    config = Configuration().read()
    logger.setLevel(config['log_level'])

    cmd_parsers = command_prepare(config['commands'])

    # отдельная очередь для связки вывод - команда
    output_queues = {}

    stop_threads = False

    threads = []

    # start thread for each output
    for output_type in config['output'].keys():
        func_name = None
        if output_type == 'stdout':
            OUTPUT_READY[output_type] = True
            func_name = 'stdout'

        elif output_type == 'clickhouse':
            OUTPUT_READY[output_type]  = False
            func_name = 'clickhouse'

        if func_name:
            output_queues[output_type] = queue.Queue()
            output_func = getattr(Output(), func_name)
            thread = Thread(target=output_func,args=(config['output'][output_type],
                                                            output_queues[output_type],
                                                            lambda : stop_threads))
            thread.start()
            threads.append(thread)

    # start threads for each command
    for k,v in cmd_parsers.items():
        thread = Thread(target=run_commands,args=(k,v,output_queues))
        thread.start()
        threads.append(thread)
    
    # stop_threads = True

    for t in threads:
        t.join()
    

if __name__ == "__main__":

    # commands = ['iostat -zxNp 1',
    #             'top -bi -d 1',
    #             'vmstat -w -a -n -S b 1']
    
    main()