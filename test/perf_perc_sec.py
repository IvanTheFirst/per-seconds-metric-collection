#!/data/python/3.11.4/bin/python3

import re
import yaml
from argparse import ArgumentParser
import sys
import logging
import asyncio

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(lineno)s - %(funcName)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

class Configuration:
    def __init__(self):
        self.DEFAULT_CONFIG_PATH = "perf_per_sec.yaml"
        self.SAMPLE_CONFIG = """# DEBUG, INFO, WARNING, ERROR, CRITICAL, default NOTSET
log_level: "INFO"

commands:
  top:
    cmd_ver: top -v
    versions:
      - version_regexp: 3.3.\d+
        cmd: top 123
        parsers:
          - fields: [la1,la2,la3]
            regexp: .*
          - fields: [la1,la2,la3]
            regexp: .*
            
output:
    clickhouse:
        ## clickhouse connection scheme secure True/False
        secure: True
        ## clickhouse host and port
        host: "server:9440"
        login: "login"
        password: "password"
        ## clickhouse cluster to create tables, leave empty or none for local database
        # cluster: "monitoring"
        ttl_days: 720
        ## ReplicatedMergeTree - for cluster, MergeTree for local
        table_engine: "MergeTree"
        database_name: "metrics"
        reconnect_timeout_sec: 60

    tcp:
        host: "server:9440"
        format: json

    local_duckdb:
        file_path: asd
        ttl_days: 100

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

async def start_command(command:str, parsers:list(str)) -> None:
    pass

async def check_command_version(config_for_cmd:dict)-> dict:
    pass

async def main(config:dict, last_update_id:int) -> None:
    logger.setLevel(config['log_level'])

    # очереди приёма и отправки сообщений
    q_recieve = asyncio.Queue()
    q_send = asyncio.Queue()

    bot_token = config['bot_token']

    task1 = asyncio.create_task(get_messages(bot_token, q_recieve, last_update_id, config['last_update_id_path']))
    task2 = asyncio.create_task(send_messages(bot_token, q_send))
    task3 = asyncio.create_task(message_common_handler(q_recieve,q_send))

    await task1
    await task2
    await task3


if __name__ == "__main__":

    config = Configuration().read()

    asyncio.run(main(config))