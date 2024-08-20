import dask.dataframe as dd
import pandas as pd
from dask.distributed import Client
import warnings
from qmostetc.eso.etc import run, config
from qmostetc import QMostObservatory, SEDTemplate, rebin, L1DXU
import astropy.units as u
import numpy as np
import argparse
import json


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


def getSNTemplateETC(template):
    with warnings.catch_warnings(action="ignore"):
        return SEDTemplate('/data/cf5g09/tides/s10August2020/specTest/SNSpecFits/'+str(template))
    
def getGalaxyTemplateETC(template):
    with warnings.catch_warnings(action="ignore"):
        return SEDTemplate('/data/cf5g09/tides/WAVES/round14_Files/For4FS/WAVESSpecTemp/'+str(template))

def calSNRAll(df):
    #print(df['name'], df['subsurvey'])
    with warnings.catch_warnings(action="ignore"):
        if df['subsurvey']==1:
            inTemplate = getSNTemplateETC(df.template) ## The template from the bank
            rebinSize=15*u.AA
        elif df['subsurvey']==2:
            inTemplate = getGalaxyTemplateETC(df.template) ## The template from the bank
            rebinSize=1*u.AA
        else: return None

        target = SEDTemplate(inTemplate)(df.mag*u.ABmag, 'LSST.r')

        ##Setup gloabl observtory status
        observatory = QMostObservatory('lrs')
        obs = observatory(45*u.deg, 0.8*u.arcsec, 'grey')

        obs.set_target(target, 'point')

        texp = df.visit_texp * u.minute

        tbl = obs.expose(texp)
        # dxuObs = L1DXU(observatory, tbl, texp, with_noise=True)
        # dxuIn = L1DXU(observatory, tbl, texp, with_noise=False)
        dxuOut = L1DXU(observatory, tbl, texp, with_noise=True, binwidth=rebinSize)
        # totalL1 = dxuObs.joined_spectrum()
        # totalIn = dxuIn.joined_spectrum()
        totalSpec = dxuOut.joined_spectrum()
        
        meanSNR = np.mean(totalSpec['FLUX'][(totalSpec['WAVE'].value>4500) & (totalSpec['WAVE'].value<8000)]/totalSpec['ERR_FLUX'][(totalSpec['WAVE'].value>4500) & (totalSpec['WAVE'].value<8000)])
        
        return df['name'], df['subsurvey'],df['first_obs'],meanSNR

if __name__ == '__main__':
    client = Client(threads_per_worker=1)
    
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--config', help="Path to the JSON config file")

    # Execute the parse_args() method
    args = parser.parse_args()
    configPath = args.config

    #Step 1: Open the config file
    configFile = openConfig(configPath) #Opens the config file that will be used through the pipeline

    basePath = configFile["dataOutputBaseDir"]
    specificPath = basePath+'/selfie'+str(configFile["qmost"]["selfieRunID"])

    sneGalIn = pd.read_csv(specificPath+'/'+'observedSNeAndGalaxies.csv')
    #sneGalIn = sneGalIn.iloc[:200]
    sneGal = dd.from_pandas(sneGalIn,npartitions=40)
    #sneGal = sneGal.repartition(npartitions=80)
    
    # print(sneGal.name.compute())
    print(len(sneGal))
    
    result = sneGal.apply(calSNRAll, meta={0:'int64', 1:'int', 2:'float'}, axis=1, result_type='expand').compute(num_workers=24)
    result.columns = ["name", "subsurvey","first_obs", "snr"]

    joined = sneGalIn.merge(result, how='left', left_on=["name", "subsurvey","first_obs"], right_on=["name", "subsurvey","first_obs"])
    #print(joined)
    # joinedDF = pd.DataFrame(joined)
    joined.to_csv(specificPath+'/'+'observedSNeAndGalaxies_joinedSNR.csv', index=False)

    result.to_csv(specificPath+'/'+'observedSNeAndGalaxies_justSNR.csv', index=False)

