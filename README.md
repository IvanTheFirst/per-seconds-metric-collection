**perf_per_sec.pl** скрипт на perl (для уменьшения потребления памяти и процессора), собирающий метрики от вывода команд
 - iostat
 - top
 - vmstat
 - iotop (для этого нужен sudo)

скрипт отправляет метрики по tcp в формате opentsdb или json (адаптированный для fluentbit)

**docker-compose.yaml** - запускает grafana,fluentbit и timescaledb

**docker-compose_greptimedb.yaml** - запускает grafana и greptimedb.

в каталоге config уже есть плагин grafana для greptimedb версии **0.2.5**

---

#### минусы greptimedb
1. почти нет работы с текстом на нативной SQL
2. не ясно как сделать аннотации к графикам

---

#### как запустить
нужно склонировать репозиторий и поставить бит исполнения на скрипт
```chmod +x ./perf_per_sec.pl```

а так же создать каталог для данных grafana и назначить ему соответствующего владельца
```
mkdir grafana_db
sudo chown 1472 grafana_db
```

---

#### для сохранения в greptimedb:
```
sudo docker-compose -f docker-compose_greptimedb.yaml up -d
./perf_per_sec.pl opentsdb vmstat tcp://127.0.0.1:4242
./perf_per_sec.pl opentsdb top tcp://127.0.0.1:4242
./perf_per_sec.pl opentsdb iostat tcp://127.0.0.1:4242
./perf_per_sec.pl opentsdb iotop tcp://127.0.0.1:4242
```

#### для сохранения в timescaledb:
```
sudo docker-compose up -d
./perf_per_sec.pl json_flientbit_postgresql vmstat tcp://127.0.0.1:2020
./perf_per_sec.pl json_flientbit_postgresql top tcp://127.0.0.1:2020
./perf_per_sec.pl json_flientbit_postgresql iostat tcp://127.0.0.1:2020
./perf_per_sec.pl json_flientbit_postgresql iotop tcp://127.0.0.1:2020
```

---

#### подключить источник данных greptimedb
Для подключения указать следующие настройки источника данных greptinedb:
```
url: http://greptimedb:4000/
database: public
```

![настройки greptimedb datasource](/pictures/greptimedb_datasource.png)

будет такая ошибка - 
```Greptime error code undefined. See https://github.com/GreptimeTeam/greptimedb/blob/develop/src/common/error/src/status_code.rs for more details``` её можно игнорировать

![ошибка при сохранении greptimedb datasource](/pictures/greptimedb_datasource_error.png)

#### создать визуализацию из данных в greptimedb
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

---

#### подключить источник данных timescaledb
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

#### создать визуализацию из данных в timescaledb
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