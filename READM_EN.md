**perf_per_sec.pl** perl script (to reduce memory and CPU consumption) that collects metrics from the output of commands:
- iostat
- top
- vmstat
- iotop (this requires sudo)

script sends metrics via tcp in opentsdb or json format (adapted for fluentbit)

**docker-compose.yaml** - start grafana,fluentbit and timescaledb

**docker-compose_greptimedb.yaml** - start grafana and greptimedb.

in the config directory there is already a grafana plugin for greptimedb version **0.2.5**

---

#### greptimedb cons:
1. there isn't functions for working with strings in native SQL
2. It is not clear how to annotate charts in grafana

---

#### how to run
clone the repository and set the executable bit of the script
```chmod +x ./perf_per_sec.pl```

create folder and give permissions to grafana docker container
```
mkdir grafana_db
sudo chown 1472 grafana_db
```

---

#### store in greptimedb:
```
sudo docker-compose -f docker-compose_greptimedb.yaml up -d
./perf_per_sec.pl opentsdb vmstat tcp://127.0.0.1:4242
./perf_per_sec.pl opentsdb top tcp://127.0.0.1:4242
./perf_per_sec.pl opentsdb iostat tcp://127.0.0.1:4242
./perf_per_sec.pl opentsdb iotop tcp://127.0.0.1:4242
```

#### store in timescaledb:
```
sudo docker-compose up -d
./perf_per_sec.pl json_flientbit_postgresql vmstat tcp://127.0.0.1:2020
./perf_per_sec.pl json_flientbit_postgresql top tcp://127.0.0.1:2020
./perf_per_sec.pl json_flientbit_postgresql iostat tcp://127.0.0.1:2020
./perf_per_sec.pl json_flientbit_postgresql iotop tcp://127.0.0.1:2020
```

---

#### connect greptimedb datasource
To connect, specify the following greptimedb datasource settings:
```
url: http://greptimedb:4000/
database: public
```

![greptimedb datasource setup](/pictures/greptimedb_datasource.png)

ignore this error -
```Greptime error code undefined. See https://github.com/GreptimeTeam/greptimedb/blob/develop/src/common/error/src/status_code.rs for more details```

![greptimedb datasource saving settings error](/pictures/greptimedb_datasource_error.png)

#### create vizualizations with greptimedb
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

---

#### connect timescaledb datasource 
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

#### data vizualizations with timescaledb
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
