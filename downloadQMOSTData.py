import requests.auth
from dotenv import load_dotenv
import os
from concurrent.futures import ThreadPoolExecutor
import requests
import json
from pathlib import Path
import argparse
import itertools
import threading
import time
import sys

def commandlineAnimate(process, whatSay):
    '''This function will add a small looping ascii animation 
    to the commandline that will run while a long function is 
    executing
    whatSay: a string that will say something informative like "Downloading"
    '''
    while process.is_alive():
        for c in itertools.cycle(['|', '/', '-', '\\']):
                sys.stdout.write('\r'+whatSay + c)
                sys.stdout.flush()
                time.sleep(0.1)
                if process.is_alive() == False:
                    break
    sys.stdout.write('\rDone!') 

def updateConfigProgress(config, keyName):
    '''To record the progress of the pipeline, this function will
    update the "completed" key in each component of the config file.
    This will let us skip the processes that have been completed. 
    '''
    config[keyName]['completed'] = True
    print(config[keyName]['completed'])

    with open("progress.json", "w") as outfile: 
        json.dump(config, outfile, indent=4)


def openConfig(configName):
    '''This funtion opens the config file. This is standard across
    '''
    configOpen = open(configName)
    config = json.load(configOpen)
    return config

def makeDirectories(config):
    '''Here we make all the directories we want for the run.
    '''
    #Let's make the directory to store all the data
    Path(specificPath).mkdir(parents=True, exist_ok=True)
    
    #Let's make a directory for any plot's we'll make
    Path(specificPath+'/plots').mkdir(parents=True, exist_ok=True)
    #updateConfigProgress(config, 'qmost')

## Below here we will download the 4MOST SELFIE files
## This will be in a parallel manner so that it will execute quickly

# async def download_QMOSTfile(url):
#     async with aiohttp.ClientSession() as session:
#         async with session.get(url, auth=aiohttp.BasicAuth(qMOSTUSER, qMOSTPASSWORD), timeout=20) as response:
#             if "content-disposition" in response.headers:
#                 header = response.headers["content-disposition"]
#                 filename = header.split("filename=")[1]
#             else:
#                 filename = url.split("/")[-1]
#             with open(specificPath+'/'+filename, mode="wb") as file:
#                 while True:
#                     chunk = await response.content.read()
#                     if not chunk:
#                         break
#                     file.write(chunk)
#                 print(f"Downloaded file {filename}")

def download_QMOSTfile(url):
    response = requests.get(url, auth=requests.auth.HTTPBasicAuth(qMOSTUSER, qMOSTPASSWORD))
    if "content-disposition" in response.headers:
        content_disposition = response.headers["content-disposition"]
        filename = content_disposition.split("filename=")[1]
    else:
        filename = url.split("/")[-1]
    with open(specificPath+'/'+filename, mode="wb") as file:
        file.write(response.content)
    print(f"Downloaded file {filename}")

def downloadQMOSTFiles(config):
    '''In this function, we will download the 4MOST Selfie files using the aiohttp library
    '''
    urls = [config["qmost"]["selfieSimTargetsURL"],
            config["qmost"]["selfieSimTilesURL"], 
            config["qmost"]["selfieSimFibresURL"],
            config["qmost"]["qvpDataURL"],
            config["qmost"]["catQMOSTURL"]
            ]
    # async def main():
    #     tasks = [download_QMOSTfile(url) for url in urls]
    #     await asyncio.gather(*tasks)
    # asyncio.run(main())
    with ThreadPoolExecutor() as executor:
        executor.map(download_QMOSTfile, urls)
    return




if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--config', help="Path to the JSON config file")

    # Execute the parse_args() method
    args = parser.parse_args()
    configPath = args.config

    #Step 1: Open the config file
    configFile = openConfig(configPath) #Opens the config file that will be used through the pipeline

    basePath = configFile["dataOutputBaseDir"]
    specificPath = basePath+'/selfie'+str(configFile["qmost"]["selfieRunID"])

    #Get the 4MOST SELFIE Username and Password from the secret file
    load_dotenv()
    qMOSTUSER= os.getenv('QMOSTUSER'); qMOSTPASSWORD=os.getenv('QMOSTPASSWORD')

    ## Step 2: Make the directories
    if configFile['qmost']['completed']==False:
        print('Doing QMOST Stuff')
        makeDirectories(configFile)

        the_process = threading.Thread(target=downloadQMOSTFiles, args=(configFile,), daemon=True)
        the_process.start()
        commandlineAnimate(the_process, 'Downloading, this make take a while (files are GBs in size)')
        the_process.join()

    ## Step 3: Process the simulation files to create the desired output

    

        
        
