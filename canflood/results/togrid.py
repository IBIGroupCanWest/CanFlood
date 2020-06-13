'''


@author: cefect

convert asset geometry results to new spatial grids
'''

#==========================================================================
# logger setup-----------------------
#==========================================================================
import logging, configparser, datetime



#==============================================================================
# imports------------
#==============================================================================
import os, logging, datetime, gc
import numpy as np
import pandas as pd


#Qgis imports

from qgis.core import *



#==============================================================================
# # custom
#==============================================================================

from hlpr.exceptions import QError as Error
    
from hlpr.Q import Qcoms, view, vlay_get_fdf, vlay_rename_fields, vlay_get_fdata

import processing  


#==============================================================================
# functions-------------------
#==============================================================================
class Gwrkr(Qcoms):
    """
    sampling asset geometry up to polygon grids
    """


    
    def __init__(self,
                 **kwargs
                 ):
        

        

        
        super().__init__(**kwargs) #initilzie teh baseclass
        
        self.logger.debug('init finished')
        
    def load_grid(self, #load a grid layer and do some checks
                  fp,
                  gid = 'DA_id',#grid field name
                  logger=None):
        
        if logger is None: logger=self.logger
        log=logger.getChild('load_grid')

        #=======================================================================
        # load        
        #=======================================================================
        vlay = self.load_vlay(fp, logger=log)
        
        
        #=======================================================================
        # check
        #=======================================================================
        assert 'Polygon' in QgsWkbTypes().displayString(vlay.wkbType())
        
        dp = vlay.dataProvider()
        
        assert gid in [f.name() for f in vlay.fields()], 'missing gid \'%s\''%gid
        

        
        log.info('loaded grid w/ %i cells and gid=\'%s\' \'%s\' '%(dp.featureCount(),gid, vlay.name()))
        
        self.gvlay = vlay
        self.gid=gid
        
        return vlay
    
    
    def rename_events(self, #rename events from the evals
                      vlay_raw,
                      ev_fp,
                      repl_str = '_WL_fail_0415', #optional string to drop from fieldnames
                      event_probs='ari', #format of evals
                      logger=None,
                      ):
        if logger is None: logger=self.logger
        log=logger.getChild('rnmE')
        #=======================================================================
        # get the evals
        #=======================================================================
        ev_ser = pd.read_csv(ev_fp).T.iloc[:,0].rename('evals').drop_duplicates()
        ev_ser.index = ev_ser.index.str.replace(repl_str,'', case=False)
        
        #convert 
        if event_probs=='ari':
            ev_ser = 1/ev_ser
        
        #=======================================================================
        # get conversions and check
        #=======================================================================
        rnm_d = ev_ser.astype(str).to_dict()
        rnm_d = dict(zip(rnm_d.values(), rnm_d.keys()))
        

        fn_l = [f.name() for f in vlay_raw.fields()]

        s = set(rnm_d.keys()).difference(fn_l)
        assert len(s)==0, 'vlay fields mismatch evals fields: \n    %s'%s
        
        #=======================================================================
        # rename the fields
        #=======================================================================
        vlay = vlay_rename_fields(vlay_raw, rnm_d, logger=log)
        
        log.info('renamed %i fields on \'%s\' from evals \n    %s'%(
            len(rnm_d), vlay.name(), rnm_d))
        return vlay

        """
        view(vlay)
        """
        
        
        
        
        
        
    def gsamp(self, #resample results to a grid (from single asset res layer)
              avlay, #asset results layer
              gvlay=None, #new polygon grid to sample
              gid=None,
              res_fnl = ['ead'], #list of result fields to downsample
              use_raw_fn=True, #whether to convert the summary field names back to raw.
              
              logger=None,
              discard_nomatch=False,
              **jkwargs #joinbylocationsummary kwargs
              ):
        """
        resample results 
        """
        
        if logger is None: logger=self.logger
        log=logger.getChild('gsamp')
        
        
        if gvlay is None: gvlay = self.gvlay
        if gid is None: gid=self.gid
        
        
        
        log.info('downsampling \'%s\' (%i feats) to \'%s\' (%i)'%(
            avlay.name(), avlay.dataProvider().featureCount(), gvlay.name(),
            gvlay.dataProvider().featureCount()))
        
        #=======================================================================
        # prechecks
        #=======================================================================
        fn_l = [f.name() for f in gvlay.fields()]
        assert gid in fn_l, gid
        
        fn_l = [f.name() for f in avlay.fields()]
        s = set(res_fnl).difference(fn_l)
        assert len(s)==0, 'missing requested results fields: %s'%res_fnl
        
        #check the gids
        gid_d = vlay_get_fdata(gvlay, fieldn=gid, logger=log)
        assert pd.Series(gid_d).is_unique, '%s has bad gid=\'%s\''%(gvlay.name(), gid)
        
        #=======================================================================
        # calc
        #=======================================================================
        gvlay1, nfn_l = self.joinbylocationsummary(gvlay, avlay, res_fnl, use_raw_fn=use_raw_fn,
                                                   discard_nomatch=discard_nomatch,
                                                   **jkwargs)
        
        #=======================================================================
        # wrap
        #=======================================================================
        if not discard_nomatch:
            assert gvlay1.dataProvider().featureCount()==gvlay.dataProvider().featureCount()
        
        
        
        return gvlay1, nfn_l
    
    def combine_gsamp(self, #combine a set of asset results to a grid
                      avlay_d,
                      Gw, #grid worker
                      res_fnl = ['ead'], #list of result fields to downsample

                      rnm_d=dict(), #optional POST field name conversion. {old fieldName:new fieldName}
                      logger=None,
                      ):
        """
        also see add_vlays()
        """
        #=======================================================================
        # defaults
        #=======================================================================
        if logger is None: logger=self.logger
        log=logger.getChild('cGsamp.%s'%Gw.name)
        gvlay=Gw.vlay
        gid=Gw.gid
        
        
        
        #=======================================================================
        # downsample asset results--------
        #=======================================================================
        
        res_d = dict()
        mdf = pd.DataFrame()
        #loop and collect grid totals for each inventory
        for aresName, avlay in avlay_d.items():
            log.info('downsampling \'%s\''%aresName)
            
            #sum on polys
            rvlay, nfn_l = self.gsamp(avlay, res_fnl=res_fnl,
                                      gid=gid, gvlay=gvlay, logger=log)
            
            #convert to frame
            df = vlay_get_fdf(rvlay, logger=log).drop(['fid'], axis=1, errors='ignore').rename(
                columns=rnm_d).set_index(gid).loc[:, res_fnl]
                
            #check it
            assert df.index.is_unique, aresName
            assert 'int' in df.index.dtype.name, aresName
                
            res_d[aresName] = df.round(self.prec)
            
            #meta
            mdf = mdf.append(df.sum().rename(aresName), verify_integrity=True)



        log.info('collected totals from %i layers'%len(res_d))
        
        #=======================================================================
        # combine-----
        #======================================================================
        #empty results container
        rdf = pd.DataFrame(
            index=vlay_get_fdf(gvlay, logger=log).set_index(gid, drop=True).index,
            columns=res_d[aresName].columns).fillna(0)
            

        
        #loop each asset downsample and s um
        for aresName, df in res_d.items():
            #check index compatability
            s = set(df.index).difference(rdf.index)
            assert len(s)==0, aresName
            
            #sum together
            rdf1 = rdf.add(df, axis=0, fill_value=0)
            
            #check index again
            assert np.array_equal(rdf1.index, rdf.index)
            assert np.array_equal(rdf1.columns, rdf.columns)
            
            #check summation logic
            bdf = rdf1>=rdf
            assert bdf.all().all()
            
            #clean and reset
            rdf = rdf1.round(self.prec)
            
        #wrap
        log.info('totaled across %i asset layers on %i grids'%(
            len(res_d), len(rdf)))
        
        #=======================================================================
        # build combined layer
        #=======================================================================
        geo_d = vlay_get_fdata(gvlay, geo_obj=True, logger=log, rekey=gid)
        rvlay = self.vlay_new_df2(rdf.reset_index(), geo_d=geo_d, logger=log, gkey=gid,
                                  layname='%s_comb_%i'%(Gw.name, len(res_d)))
        
        #=======================================================================
        # #meta clean up
        #=======================================================================
        mdf['gname'] = Gw.name
        mdf['gvlay_name'] = Gw.vlay.name()
        mdf.index.name='aresName'
        mdf=mdf.reset_index()
        
        
        return rvlay, res_d, mdf
        """
        view(rdf)
        [f.name() for f in avlay.fields()]
        view(rvlay)
        """
        
        
        
    
        
        


         