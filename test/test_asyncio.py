#!/data/python/3.11.4/bin/python3

import asyncio
import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(lineno)s - %(funcName)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_commands(command) -> None:
    
    temp = command.split(' ')

    if len(temp) == 1:
        proc = await asyncio.create_subprocess_exec(temp[0], stdout=asyncio.subprocess.PIPE)
    elif len(temp) == 2:
        proc = await asyncio.create_subprocess_exec(temp[0], temp[1], stdout=asyncio.subprocess.PIPE)
    elif len(temp) == 3:
        proc = await asyncio.create_subprocess_exec(temp[0], temp[1], temp[2], stdout=asyncio.subprocess.PIPE)
    elif len(temp) == 4:
        proc = await asyncio.create_subprocess_exec(temp[0], temp[1], temp[2], temp[3], stdout=asyncio.subprocess.PIPE)
    elif len(temp) == 5:
        proc = await asyncio.create_subprocess_exec(temp[0], temp[1], temp[2], temp[3], 
                                                    temp[4], stdout=asyncio.subprocess.PIPE)
    elif len(temp) == 6:
        proc = await asyncio.create_subprocess_exec(temp[0], temp[1], temp[2], temp[3], 
                                                    temp[4], temp[5], stdout=asyncio.subprocess.PIPE)
    elif len(temp) == 7:
        proc = await asyncio.create_subprocess_exec(temp[0], temp[1], temp[2], temp[3], 
                                                    temp[4], temp[5], temp[6], stdout=asyncio.subprocess.PIPE)
    elif len(temp) == 8:
        proc = await asyncio.create_subprocess_exec(temp[0], temp[1], temp[2], temp[3], 
                                                    temp[4], temp[5], temp[6], temp[6], stdout=asyncio.subprocess.PIPE)
    # Read one line of output.
    while True:
        data = await proc.stdout.readline()
        line = data.decode('utf8').rstrip()
        if line != '': print(line)

    # Wait for the subprocess exit.
    await proc.wait()

async def main(commands):
    tasks = []
    for command in commands:
        tasks.append(asyncio.create_task(run_commands(command)))

    for task in tasks:
        await task

if __name__ == "__main__":

    commands = ['iostat -zxNp 1',
                'top -bi -d 1',
                'vmstat -w -a -n -S b 1']

    asyncio.run(main(commands))
