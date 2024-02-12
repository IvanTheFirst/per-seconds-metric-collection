#!/data/python/3.11.4/bin/python3

from threading import Thread
from subprocess import Popen, PIPE, STDOUT, check_output
import yaml
from argparse import ArgumentParser
import re
import sys
import logging
import time
import json
import queue

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(lineno)s - %(funcName)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

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
                    parser = command_parser['parser'][parser_name]
                    temp_fields_values = re.findall(parser['regexp'],line.rstrip())
                    if temp_fields_values :
                        fields_values = { parser['fields'][j]: temp_fields_values[0][j] for j in range(len(parser['fields'])) }
                        tags = {tag: fields_values[tag] for tag in parser['tags']}
                        metrics = {metric: to_float_or_int_or_str(fields_values[metric]) for metric in parser['metrics']}
                        metrics['timestamp'] = timestamp
                        output_queues['stdout'].put((cmd_name,parser_name,tags,metrics))
                        
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

def output_stdout( output:dict, output_queue:queue.Queue) -> None:
    while True:
        (cmd,parser_name,tags,metrics) = output_queue.get()
        if output['format'] == 'json':
            print(json.dumps(tags|metrics))
            
def main():
    config = Configuration().read()
    logger.setLevel(config['log_level'])

    cmd_parsers = command_prepare(config['commands'])

    # отдельная очередь для связки вывод - команда
    output_queues = {}

    output_queues['stdout'] = queue.Queue()

    threads = []

    # start threads for each command
    for k,v in cmd_parsers.items():
        thread = Thread(target=run_commands,args=(k,v,output_queues))
        thread.start()
        threads.append(thread)

    thread = Thread(target=output_stdout,args=(config['output']['stdout'],
                                                                output_queues['stdout']))
    thread.start()
    threads.append(thread)

    for t in threads:
        t.join()

if __name__ == "__main__":
    
    main()