'''
This script will make the table that joins the simulation target file with the visit table.
The output of this code will be a table/database that can be fed into the ETC to make
spectra of our objects.
'''

from astropy.table import Table
import pandas as pd
import numpy as np
import duckdb
import argparse
from dotenv import load_dotenv
import json
import os

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

def getFileNameFromURL(urlstring):
    return urlstring.split('/')[-1]


def makeObservationTable(config):
    #Copy the process from linkSimsDevNotebook.ipynb to make the final observations table.

    tilesInput = getFileNameFromURL(config["qmost"]["selfieSimTilesURL"])
    fibresInput = getFileNameFromURL(config["qmost"]["selfieSimFibresURL"])
    targetsInput = getFileNameFromURL(config["qmost"]["selfieSimTargetsURL"])
    catmostInput = getFileNameFromURL(config["qmost"]["catQMOSTURL"])
    etcInput = getFileNameFromURL(config["qmost"]["etcOutput"])

    tiles = Table.read(specificPath+'/'+tilesInput)
    tiles.convert_bytestring_to_unicode()
    tiles_pd = tiles.to_pandas()
    del tiles

    fibres = Table.read(specificPath+'/'+fibresInput)
    fibres.convert_bytestring_to_unicode()
    fibres_pd = fibres.to_pandas()
    del fibres

    targets = Table.read(specificPath+'/'+targetsInput)
    targets = targets[(targets['ntile_obs'] > 0) &  ((targets['subsurvey_id'] == b'S1001') | (targets['subsurvey_id'] == b'S1002') | 
                                                    (targets['subsurvey_id'] == b'S1003') | (targets['subsurvey_id'] == b'S1004'))]
    targets.convert_bytestring_to_unicode()
    targets_pd = targets.to_pandas()
    del targets

    catmost = Table.read(specificPath+'/'+catmostInput)
    catmost = catmost[(catmost['survey'] == 10)]
    catmost.convert_bytestring_to_unicode()
    catmost_pd = catmost.to_pandas()
    del catmost

    etcOutput = Table.read(specificPath+'/'+etcInput)
    etcOutput.convert_bytestring_to_unicode()
    etcOutput_pd = etcOutput.to_pandas()
    del etcOutput

    targets_pd = duckdb.sql("SELECT * from targets_pd where subsurvey_id like 'S10%'").df()
    tiles_pd['visit_id'] = tiles_pd.groupby(["ra", "dec", "ntile"]).ngroup()
    visit_texp_df = duckdb.sql("SELECT visit_id, sum(texp) as visit_texp, min(jd_obs) as min_jd_obs from tiles_pd group by visit_id").df()

    bigJoinQuery = """
    SELECT
    t.targ_id, t.u_obj_id, t.subsurvey_id, t.subsurvey_index, t.single_ob, t.nrepeat, t.dt_min, t.fobs,
    t.ntile_obs, t.jd_obs_first, t.jd_obs_last, t.texp_g, f.tile_id, f.targ_id
    FROM targets_pd t JOIN fibres_pd f on t.targ_id=f.targ_id 
    WHERE f.status != -1 and f.status != 0
    """
    fibres1 = duckdb.sql(bigJoinQuery).df()

    bigJoin2 = """
    SELECT f.*, ti.tile_id, ti.visit_id, ti.ntile, ti.irank, ti.status, ti.jd_obs, ti.texp  
    FROM fibres1 f JOIN tiles_pd ti ON ti.tile_id=f.tile_id
    """
    fibres2 = duckdb.sql(bigJoin2).df()

    queryFinal = """
    SELECT u_obj_id, count(*) as nexp, sum(fibres2.texp) as texp_total, subsurvey_id,
    subsurvey_index, min(jd_obs_first) as first_obs, max(jd_obs_last) as last_obs,single_ob,nrepeat,dt_min,ntile_obs, fibres2.visit_id, vt.visit_texp, vt.min_jd_obs
    FROM fibres2
    JOIN visit_texp_df vt ON fibres2.visit_id=vt.visit_id
    GROUP BY u_obj_id, subsurvey_id, subsurvey_index, fibres2.visit_id, vt.visit_texp,single_ob,nrepeat,dt_min,ntile_obs,min_jd_obs
    """
    finalObs = duckdb.sql(queryFinal).df()

    allTable = duckdb.sql("""SELECT fo.*, cm.targ_id, cm.name, cm.resolution, cm.cadence, 
                          cm.epoch, cm.redshift_estimate, cm.date_earliest, cm.date_latest, 
                          cm.ra, cm.dec, cm.mag, cm.texp_d, cm.texp_g, cm.texp_b, cm.texp_s, 
                          cm.survey, cm.subsurvey 
                          FROM finalObs fo JOIN catmost_pd cm on fo.u_obj_id=cm.u_obj_id""").df()
    
    allTable['subsurvey_name'] = allTable.apply(lambda x: 'tides-sn' if x['subsurvey']==1 else 'tides-hosts' if x['subsurvey']==2
                                            else 'tides-rm' if x['subsurvey']==3 else 'source' if x['subsurvey']==4 else 'tides-dud' , axis=1)

    #Now return just the SNe
    queryJoinETCS1001 = """
    SELECT at.*, etc.TEMPLATE as template, etc.MAG_TYPE as mag_type
    FROM allTable at, etcOutput_pd etc
    WHERE subsurvey_id='S1001' and at.name = etc.NAME and at.date_earliest=etc.DATE_EARLIEST and at.subsurvey_name=etc.SUBSURVEY
    """
    finalETCObsS1001 = duckdb.sql(queryJoinETCS1001).df()

    ## The galaxies need to be handled slightly sifferently because objects can be observed across multiple 
    ## OBs, so the same galaxy will appear multiple times.
    ## We therefore need to aggregate the multiple entries into a single object and sum the exposure times
    queryJoinETCS1002 = """
    SELECT at.*, etc.TEMPLATE as template, etc.MAG_TYPE as mag_type
    FROM allTable at, etcOutput_pd etc
    WHERE subsurvey_id='S1002' and at.name = etc.NAME and at.date_earliest=etc.DATE_EARLIEST and at.subsurvey_name=etc.SUBSURVEY
    """
    finalETCObsS1002preSum = duckdb.sql(queryJoinETCS1002).df()
    combineGalaxyObs = """
    SELECT distinct(u_obj_id),  count(*) as nobs,
    any_value(nexp) as nexp,
    sum(texp_total) as texp_total,
    any_value(subsurvey_id) as subsurvey_id,
    any_value(subsurvey_index) as subsurvey_index,
    min(first_obs) as first_obs,
    max(last_obs) as last_obs,
    any_value(single_ob) as single_ob,
    any_value(nrepeat) as nrepeat,
    any_value(dt_min) as dt_min,
    any_value(ntile_obs) as ntile_obs,
    any_value(visit_id) as visit_id,
    sum(visit_texp) as visit_texp,
    min(min_jd_obs) as min_jd_obs,
    any_value(targ_id) as targ_id,
    any_value(name) as name,
    any_value(resolution) as resolution,
    any_value(cadence) as cadence,
    any_value(epoch) as epoch,
    any_value(redshift_estimate) as redshift_estimate,
    any_value(date_earliest) as date_earliest,
    any_value(date_latest) as date_latest,
    any_value(ra) as ra,
    any_value(dec) as dec,
    any_value(mag) as mag,
    any_value(texp_d) as texp_d,
    any_value(texp_g) as texp_g,
    any_value(texp_b) as texp_b,
    any_value(texp_s) as texp_s,
    any_value(survey) as survey,
    any_value(subsurvey) as subsurvey,
    any_value(subsurvey_name) as subsurvey_name,
    any_value(template) as template,
    any_value(mag_type) as mag_type
    FROM finalETCObsS1002preSum
    GROUP BY u_obj_id
    """
    finalETCObsS1002 = duckdb.sql(combineGalaxyObs).df()

    ## Now we return the concatenated list of JUST the SNe and Galaxies
    return pd.concat((finalETCObsS1001, finalETCObsS1002))

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

    ## All the files needed to make a big join of the 
    sneAndGalaxies = makeObservationTable(configFile)

    #sneAndGalaxies.to_hdf(specificPath+'/'+'observedSNeAndGalaxies.h5', mode='w', key=str(configFile["qmost"]["selfieRunID"]))
    sneAndGalaxies.to_csv(specificPath+'/'+'observedSNeAndGalaxies.csv', index=False)

    updateConfigProgress(configFile, 'selfieResults')

