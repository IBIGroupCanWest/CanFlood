'''
Created on Feb. 9, 2020

@author: cefect

simple build routines
'''

#==========================================================================
# logger setup-----------------------
#==========================================================================
import logging, configparser, datetime, shutil



#==============================================================================
# imports------------
#==============================================================================
import os
import numpy as np
import pandas as pd


#Qgis imports
from qgis.core import QgsVectorLayer, QgsWkbTypes

#==============================================================================
# custom imports
#==============================================================================

#standalone runs
if __name__ =="__main__": 
    from hlpr.logr import basic_logger
    mod_logger = basic_logger()   
    
    from hlpr.exceptions import Error
#plugin runs
else:
    #base_class = object
    from hlpr.exceptions import QError as Error
    

from hlpr.Q import Qcoms, vlay_get_fdf, vlay_get_fdata
#from hlpr.basic import *

#==============================================================================
# functions-------------------
#==============================================================================
class Preparor(Qcoms):
    """

    
    each time the user performs an action, 
        a new instance of this should be spawned
        this way all the user variables can be freshley pulled
    """


    def __init__(self,

                  *args, **kwargs):
        
        super().__init__(*args, **kwargs)
        

        
        self.logger.debug('Preparor.__init__ w/ feedback \'%s\''%type(self.feedback).__name__)
        
        
    
    def to_L1finv(self,
                in_vlay,
                drop_colns=['ogc_fid', 'fid'], #optional columns to drop from df
                new_data = {'f0_scale':1.0, 'f0_elv':0.0},
                newLayname = 'finv_L1',
                ):
        
        log = self.logger.getChild('to_L1finv')
        
        #=======================================================================
        # precheck
        #=======================================================================
        assert isinstance(in_vlay, QgsVectorLayer)
        assert 'Point' in QgsWkbTypes().displayString(in_vlay.wkbType())
        dp = in_vlay.dataProvider()
        
        log.info('on %s w/ %i feats'%(in_vlay.name(), dp.featureCount()))
        
        self.feedback.upd_prog(10)
        #=======================================================================
        # extract data
        #=======================================================================
        df_raw = vlay_get_fdf(in_vlay, logger=log)
        geo_d = vlay_get_fdata(in_vlay, geo_obj=True, logger=log)
        
        self.feedback.upd_prog(50)
        
        #=======================================================================
        # clean
        #=======================================================================
        #drop specified columns
        df0 = df_raw.drop(drop_colns,axis=1, errors='ignore')
        
        #convert empty strings to null
        df1 = df0.replace(to_replace='', value=np.nan)
        log.info('replaced %i (of %i) null values'%(df1.isna().sum().sum(), df1.size))

        #drop empty fields

        df2 = df1.dropna(axis=1, how='all')
        log.info('dropped %i empty columns'%(len(df1.columns) - len(df2.columns)))
        
        self.feedback.upd_prog(60)
        #=======================================================================
        # add fields
        #=======================================================================
        #build the new data
        log.info('adding field data:\n    %s'%new_data)
        new_df = pd.DataFrame(index=df_raw.index, data=new_data)
        
        #join the two
        res_df = new_df.join(df2)


        self.feedback.upd_prog(70)
        #=======================================================================
        # reconstruct layer
        #=======================================================================
        finv_vlay = self.vlay_new_df2(res_df,  geo_d=geo_d, crs=in_vlay.crs(),
                                logger=log,
                                layname = newLayname)
        
        #=======================================================================
        # wrap
        #=======================================================================
        fcnt = finv_vlay.dataProvider().featureCount()
        assert fcnt == dp.featureCount()
        
        log.info('finished w/ \'%s\' w/ %i feats'%(finv_vlay.name(), fcnt))
        
        self.feedback.upd_prog(99)
        return  finv_vlay
    
















                

 
    
    
    

    

            
        