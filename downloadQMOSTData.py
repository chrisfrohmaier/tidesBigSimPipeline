import dotenv
import asyncio
import aiohttp
import json
from pathlib import Path



configOpen = open('config.json')
config = json.load(configOpen)

#Let's make the directory to store all the data
Path(config["dataOutputBaseDir"]+'/selfie'+str(config["qmost"]["selfieRunID"])).mkdir(parents=True, exist_ok=True)
