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
from hlpr.basic import get_valid_filename

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
        
        
    def copy_cf_template(self, #start a new control file by copying the template
                  wdir,
                  cf_fp=None,
                  logger=None
                  ):
        
        #=======================================================================
        # defaults
        #=======================================================================
        if logger is None: logger=self.logger
        log = logger.getChild('copy_cf_template')
        
        if cf_fp is None: cf_fp = os.path.join(wdir, 'CanFlood_%s.txt'%self.tag)
        #=======================================================================
        # copy control file template
        #=======================================================================
        
        
        #get the default template from the program files
        cf_src = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 '_pars/CanFlood_control_01.txt')
        
        assert os.path.exists(cf_src)
        
        
        #get new file name
        
        
        #see if this exists
        if os.path.exists(cf_fp):
            msg = 'generated control file already exists. overwrite=%s \n     %s'%(
                self.overwrite, cf_fp)
            if self.overwrite:
                log.warning(msg)
            else:
                raise Error(msg)
            
            
        #copy over the default template
        shutil.copyfile(cf_src, cf_fp)
        
        log.debug('copied control file from\n    %s to \n    %s'%(
            cf_src, cf_fp))
        
        self.cf_fp = cf_fp
        
        return cf_fp

    def upd_cf_first(self, #seting initial values to the control file
                     curves_fp,
                     ):
        
        note_str = '#control file template created from \'upd_cf_first\' on  %s'%(
            datetime.datetime.now().strftime('%Y-%m-%d %H.%M.%S'))
        
        return self.update_cf(
            {
                'parameters':
                    ({'name':'tag'},note_str),
                    
                'dmg_fps':
                    ({'curves':curves_fp},),           
            })
        
    def finv_to_csv(self, #convert the finv to csv
                    vlay,
                    felv='datum', #should probabl just leave this if none
                    cid=None, tag=None,
                    logger=None,
                    ):
        
        #=======================================================================
        # defaults
        #=======================================================================
        if logger is None: logger=self.logger
        log=logger.getChild('finv_to_csv')
        
        if cid is None: cid=self.cid
        if tag is None: tag=self.tag
        
        #=======================================================================
        # prechecks
        #=======================================================================
        assert os.path.exists(self.cf_fp), 'bad cf_fp: %s'%self.cf_fp
        assert vlay.crs()==self.qproj.crs(), 'finv CRS (%s) does not match projects (%s)'%(
            vlay.crs(), self.qproj.crs())
        
        
        #check cid
        assert isinstance(cid, str)
        if cid == '':
            raise Error('must specify a cid') 
        if cid in self.invalid_cids:
            raise Error('user selected invalid cid \'%s\''%cid)  
        
        
        assert cid in [field.name() for field in vlay.fields()]

        #=======================================================================
        # #extract data
        #=======================================================================
        
        log.info('extracting data on \'%s\' w/ %i feats'%(
            vlay.name(), vlay.dataProvider().featureCount()))
                
        df = vlay_get_fdf(vlay, feedback=self.feedback)
          
        #drop geometery indexes
        for gindx in self.invalid_cids:   
            df = df.drop(gindx, axis=1, errors='ignore')
            
        #more cid checks
        if not cid in df.columns:
            raise Error('cid not found in finv_df')
        
        assert df[cid].is_unique
        assert 'int' in df[cid].dtypes.name, 'cid \'%s\' bad type'%cid
        
        self.feedback.upd_prog(50)
        
        #=======================================================================
        # #write to file
        #=======================================================================
        out_fp = os.path.join(self.out_dir, get_valid_filename('finv_%s_%s.csv'%(self.tag, vlay.name())))
        
        #see if this exists
        if os.path.exists(out_fp):
            msg = 'generated finv.csv already exists. overwrite=%s \n     %s'%(
                self.overwrite, out_fp)
            if self.overwrite:
                log.warning(msg)
            else:
                raise Error(msg)
            
            
        df.to_csv(out_fp, index=False)  
        
        log.info("inventory csv written to file:\n    %s"%out_fp)
        
        self.feedback.upd_prog(80)
        #=======================================================================
        # write to control file
        #=======================================================================
        assert os.path.exists(out_fp)
        
        self.update_cf(
            {
            'dmg_fps':(
                {'finv':out_fp}, 
                '#\'finv\' file path set from BuildDialog.py at %s'%(datetime.datetime.now().strftime('%Y-%m-%d %H.%M.%S')),
                ),
            'parameters':(
                {'cid':str(cid),
                 'felv':felv},
                )
             },

            )
        
        self.feedback.upd_prog(99)
        
        return out_fp
            
    
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
    
    def test(self):
        print('Preparor test')
    
















                

 
    
    
    

    

            
        