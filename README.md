# На русском
## Краткая аннотация
**perf_per_sec.pl** скрипт на perl (для уменьшения потребления памяти и процессора), собирающий метрики от вывода команд
 - iostat
 - top
 - vmstat
 - iotop (для этого нужен sudo)

скрипт отправляет метрики по tcp в формате opentsdb или json (адаптированный для fluentbit)

**docker-compose.yaml** - запускает grafana,fluentbit и timescaledb

**docker-compose_greptimedb.yaml** - запускает grafana и greptimedb.

в каталоге config уже есть плагин grafana для greptimedb версии **0.2.5**

## особенности greptimedb
1. почти нет работы с текстом на нативной SQL
2. не ясно как сделать аннотации к графикам

## как запустить
нужно склонировать репозиторий и поставить бит исполнения на скрипт
```chmod +x ./perf_per_sec.pl```

а так же создать каталог для данных grafana и назначить ему соответствующего владельца
```
mkdir grafana_db
sudo chown 1472 grafana_db
```

### для сохранения в greptimedb:
```
sudo docker-compose -f docker-compose_greptimedb.yaml up -d
./perf_per_sec.pl opentsdb vmstat tcp://127.0.0.1:4242
./perf_per_sec.pl opentsdb top tcp://127.0.0.1:4242
./perf_per_sec.pl opentsdb iostat tcp://127.0.0.1:4242
./perf_per_sec.pl opentsdb iotop tcp://127.0.0.1:4242
```

### для сохранения в timescaledb:
```
sudo docker-compose up -d
./perf_per_sec.pl json_flientbit_postgresql vmstat tcp://127.0.0.1:2020
./perf_per_sec.pl json_flientbit_postgresql top tcp://127.0.0.1:2020
./perf_per_sec.pl json_flientbit_postgresql iostat tcp://127.0.0.1:2020
./perf_per_sec.pl json_flientbit_postgresql iotop tcp://127.0.0.1:2020
```

## визуализация в grafana
### визуализация данных в greptimedb
#### настройка источника данных
Для подключения указать следующие настройки datasource:
```
url: http://greptimedb:4000/
database: public
```

![настройки greptimedb datasource](/pictures/greptimedb_datasource.png)

будет такая ошибка - 
```Greptime error code undefined. See https://github.com/GreptimeTeam/greptimedb/blob/develop/src/common/error/src/status_code.rs for more details``` её можно игнорировать

![ошибка при сохранении greptimedb datasource](/pictures/greptimedb_datasource_error.png)

#### создание дашборда

при создании дашборда важно сначала сделать все настройки в визуальном редакторе, после этого можно переходить в режим кода. Если этого не сделать, то переменные ```$__timeFilter``` и другие не будут корректно интерпретироваться плагином.

1. выбрать поле FROM из выпадающего списка:

    ![настройки greptimedb datasource](/pictures/greptimedb_dashboard_02.png)

2. вручную (это важно!) ввести greptime_value в поле time column и поставить * в поле SELECT:

    ![настройки greptimedb datasource](/pictures/greptimedb_dashboard_03.png)

3. теперь можно проверить, что переменная grafana ```$__timeFilter``` корректно преобразуется (в запросе временные метки, вместо $__timeFilter):

    ![настройки greptimedb datasource](/pictures/greptimedb_dashboard_04.png)

4. переходим в режим редактирования кода и уже можно ввести нормальный запрос:
    ```
    SELECT date_trunc('second', 
           greptime_timestamp) as ts,
           max(greptime_value) as 'greptimedb write kb/s', 
           command
    FROM "linux_iotop.disk_write" 
    WHERE command = 'greptime' and $__timeFilter
    GROUP by command,ts
    ORDER BY ts
    ```
    ![настройки greptimedb datasource](/pictures/greptimedb_dashboard_06.png)


### визуализация данных в timescaledb
настройки подключения к timescaledb
```
Host URL: timescaledb:5432
Database name: metrics

Username: fluentbit
Password: fluentbit

TLS/SSL Mode: disable

PostgreSQL Options:
    Version: 15
```

скрипт **perf_per_sec.pl** отправляет данные в следующем формате json
```
{
    "ts": 1706423974.966248, 
    "tags": {
        "ips": "10.0.2.15|192.168.1.1", "disk": "sda", "hostname": "laptop"
        }, 
    "value": 783.0, 
    "metric": "w_s", 
    "source": "linux_iostat"
}
```

но fluentbit отправляет их так:
```
data, time, tag
```

где ```data``` - json с метрикой, ```time``` - временная метка самого fluentbit, ```tag``` - служебный тэг самого fluentbit

запрос на визуализацию данных будет выглядеть так:
```
select
  split_part(ts, '.', 1) :: int as time,
  tags :: json ->> 'command' as tags, 
  split_part(value, '.' , 1 ) :: int as " "
FROM
  (
    select
      data :: json ->> 'ts' as ts,
      data :: json ->> 'tags' as tags,
      data :: json ->> 'metric' as metric,
      data :: json ->> 'value' as value,
      data :: json ->> 'source' as source
    FROM
      metrics
    WHERE
      $__timeFilter(time)
  )
WHERE
  source = 'linux_top'
  and metric = 'cpu_percent'
ORDER BY time ASC
```

формат запроса должен быть Time series, выделено красным на скриншоте:

![запрос и график timescaledb](/pictures/timescaledb_01.png)


# in english
perf_per_sec.pl perl script (to reduce memory and CPU consumption) that collects metrics from the output of commands:
 - iostat
 - top
 - vmstat
 - iotop (this requires sudo)

script sends metrics via tcp in opentsdb or json format (adapted for fluentbit)

**docker-compose.yaml** - start grafana,fluentbit and timescaledb

**docker-compose_greptimedb.yaml** - start grafana and greptimedb.

in the config directory there is already a grafana plugin for greptimedb version **0.2.5**

## greptimedb cons
1. there isn't functions for working with strings in native SQL
2. It is not clear how to annotate charts in grafana.

## how to run
clone the repository and set the executable bit of the script
```chmod +x ./perf_per_sec.pl```

create folder and give permissions to grafana docker container
```
mkdir grafana_db
sudo chown 1472 grafana_db
```

### store in greptimedb:
```
sudo docker-compose -f docker-compose_greptimedb.yaml up -d
./perf_per_sec.pl opentsdb vmstat tcp://127.0.0.1:4242
./perf_per_sec.pl opentsdb top tcp://127.0.0.1:4242
./perf_per_sec.pl opentsdb iostat tcp://127.0.0.1:4242
./perf_per_sec.pl opentsdb iotop tcp://127.0.0.1:4242
```

### store in timescaledb:
```
sudo docker-compose up -d
./perf_per_sec.pl json_flientbit_postgresql vmstat tcp://127.0.0.1:2020
./perf_per_sec.pl json_flientbit_postgresql top tcp://127.0.0.1:2020
./perf_per_sec.pl json_flientbit_postgresql iostat tcp://127.0.0.1:2020
./perf_per_sec.pl json_flientbit_postgresql iotop tcp://127.0.0.1:2020
```

## vizualizations in grafana
### data vizualizations with greptimedb
#### datasource seting up
To connect, specify the following datasource settings:
```
url: http://greptimedb:4000/
database: public
```

![greptimedb datasource setup](/pictures/greptimedb_datasource.png)

ignore this error - 
```Greptime error code undefined. See https://github.com/GreptimeTeam/greptimedb/blob/develop/src/common/error/src/status_code.rs for more details```

![greptimedb datasource saving settings error](/pictures/greptimedb_datasource_error.png)

#### dashboard creating

When creating a dashboard, it is important to first make all the settings in the visual editor, then it is possible to switch to code mode. If this is not done, then the ```$__timeFilter``` and other variables will not be correctly interpreted by the plugin.

1. select the FROM field from the drop-down list:

    ![greptimedb datasource settings](/pictures/greptimedb_dashboard_02.png)

2. manually (this is important!) enter greptime_value in the time column field and put * in the SELECT field:

    ![greptimedb datasource settings](/pictures/greptimedb_dashboard_03.png)

3. check that the grafana variable ```$__timeFilter``` is converted correctly (time stamps in the request, instead of $__timeFilter):

    ![greptimedb datasource settings](/pictures/greptimedb_dashboard_04.png)

4. switch to code editing mode and you can already enter a normal query:
    ```
    SELECT date_trunc('second', 
           greptime_timestamp) as ts,
           max(greptime_value) as 'greptimedb write kb/s', 
           command
    FROM "linux_iotop.disk_write" 
    WHERE command = 'greptime' and $__timeFilter
    GROUP by command,ts
    ORDER BY ts
    ```
    ![greptimedb datasource settings](/pictures/greptimedb_dashboard_06.png)


### data vizualizations with timescaledb
timescaledb connection settings
```
Host URL: timescaledb:5432
Database name: metrics

Username: fluentbit
Password: fluentbit

TLS/SSL Mode: disable

PostgreSQL Options:
    Version: 15
```

script **perf_per_sec.pl** sends data in the following json format
```
{
    "ts": 1706423974.966248, 
    "tags": {
        "ips": "10.0.2.15|192.168.1.1", "disk": "sda", "hostname": "laptop"
        }, 
    "value": 783.0, 
    "metric": "w_s", 
    "source": "linux_iostat"
}
```

but fluentbit sends them like this:
```
data, time, tag
```

where ```data``` is json with a metric, ```time``` is the timestamp of fluentbit itself, ```tag``` is the service tag of fluentbit itself

The data visualization request will look like this:
```
select
  split_part(ts, '.', 1) :: int as time,
  tags :: json ->> 'command' as tags, 
  split_part(value, '.' , 1 ) :: int as " "
FROM
  (
    select
      data :: json ->> 'ts' as ts,
      data :: json ->> 'tags' as tags,
      data :: json ->> 'metric' as metric,
      data :: json ->> 'value' as value,
      data :: json ->> 'source' as source
    FROM
      metrics
    WHERE
      $__timeFilter(time)
  )
WHERE
  source = 'linux_top'
  and metric = 'cpu_percent'
ORDER BY time ASC
```

set query format to Time series, highlighted in red in the screenshot:

![query and chart timescaledb](/pictures/timescaledb_01.png)