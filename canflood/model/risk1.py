'''
Created on Feb. 27, 2020

@author: cefect

impact lvl 1 model

this should run w/o any qgis bindings.
'''
    
#==============================================================================
# imports---------------------------
#==============================================================================
#python standards
import os, logging

import pandas as pd
import numpy as np

from scipy import interpolate, integrate

#==============================================================================
# custom imports
#==============================================================================

#standalone runs
mod_logger = logging.getLogger('risk1') #get the root logger

from hlpr.exceptions import QError as Error

#from hlpr.Q import *
#from hlpr.basic import *
from results.riskPlot import Plotr



class Risk1(Plotr):
    """
    model for summarizing inundation counts (positive depths)
    """
    
    valid_par='risk1'
    
    #expectations from parameter file
    exp_pars_md = {#mandataory: section: {variable: handles} 
        'parameters' :
            {'name':{'type':str}, 'cid':{'type':str},
             
             'event_probs':{'values':('ari', 'aep')}, 
             'felv':{'values':('ground', 'datum')},
             'prec':{'type':int}, 
             'ltail':None, 'rtail':None, 'drop_tails':{'type':bool},
             'as_inun':{'type':bool},
              #'ground_water':{'type':bool}, #NO! risk1 only accepts positive depths
             },
            
        'dmg_fps':{
             'finv':{'ext':('.csv',)}, #should only need the expos
             'expos':{'ext':('.csv',)},
                    },
        'risk_fps':{
             'evals':{'ext':('.csv',)}
                    },
        'validation':{
            'risk1':{'type':bool}
                    }
         }
    
    exp_pars_op = {#optional expectations
        'dmg_fps':{
            'gels':{'ext':('.csv',)},
                 },
        'risk_fps':{
            'exlikes':{'ext':('.csv',)}
                    },
        
        }
    
    #number of groups to epxect per prefix
    group_cnt = 2
    
    #minimum inventory expectations
    finv_exp_d = {
        'f0_scale':{'type':np.number},
        'f0_elv':{'type':np.number}
        }
    """
    NOTE: for as_inun=True, 
    using this flag to skip conversion of exposure to binary
    we dont need any elevations (should all be zero)
    but allowing the uesr to NOT pass an elv column would be very difficult
    """
    

    
    #==========================================================================
    # plot controls
    #==========================================================================
    plot_fmt = '{0:.0f}' #floats w/ 2 decimal
    y1lab = 'impacts'
    
    def __init__(self,
                 cf_fp='',
                 **kwargs
                 ):
        
        #init the baseclass
        super().__init__(cf_fp=cf_fp, **kwargs) #initilzie Model
        
        
        
        self.logger.debug('finished __init__ on Risk1')
        
        
    def _setup(self): 
        """
        called by Dialog and standalones
        """
        self.init_model()
        self.resname = 'risk1_%s_%s'%(self.tag, self.name)
        #self.load_data()
        #======================================================================
        # load data files
        #======================================================================
        self.load_finv()
        self.load_evals()
        self.load_expos(dtag='expos')
        
        if not self.exlikes == '':
            self.load_exlikes()
        
        if self.felv == 'ground':
            self.load_gels()
            self.add_gels()
        

        self.build_exp_finv() #build the expanded finv
        self.build_depths()
        
        
        
        self.logger.debug('finished setup_data on Risk1')
        
        return self

    def run(self,
            res_per_asset=False, #whether to generate results per asset
            
            ):
        """
        main caller for L1 risk model
        """
        #======================================================================
        # defaults
        #======================================================================
        log = self.logger.getChild('run')
        #ddf_raw, finv,  = self.data_d['expos'],self.data_d['finv'] 
        aep_ser = self.data_d['evals']
        cid, bid = self.cid, self.bid        
        bdf ,ddf = self.bdf, self.ddf
        
        #======================================================================
        # prechecks
        #======================================================================
        assert isinstance(res_per_asset, bool)
        assert cid in ddf.columns, 'ddf missing %s'%cid
        assert bid in ddf.columns, 'ddf missing %s'%bid
        assert ddf.index.name == bid, 'ddf bad index'
        
        #identifier for depth columns
        #dboolcol = ~ddf.columns.isin([cid, bid])
        log.info('running on %i assets and %i events'%(len(bdf), len(ddf.columns)-2))
        
        self.feedback.setProgress(5)
        


        boolcol = ddf.columns.isin([bid, cid])
        
        ddf1 = ddf.loc[:, ~boolcol]
        
        #======================================================================
        # convert exposures to binary
        #======================================================================
        if not self.as_inun: #standard impact/noimpact analysis
            #get relvant bids
            """
            because there are no curves, Risk1 can only use positive depths.
            ground_water flag is ignored
            """
            booldf = pd.DataFrame(np.logical_and(
                ddf1 > 0,#get bids w/ positive depths
                ddf1.notna()) #real depths
                )
    
    
            if booldf.all().all():
                log.warning('got all %i entries as null... no impacts'%(ddf.size))
                raise Error('dome')
                return
            
            log.info('got %i (of %i) exposures'%(booldf.sum().sum(), ddf.size))
            
            bidf = ddf1.where(booldf, other=0.0)
            bidf = bidf.where(~booldf, other=1.0)
        
        #=======================================================================
        # leave as percentages
        #=======================================================================
        else:
            bidf = ddf1.copy()
            assert bidf.max().max() <=1
            
            #fill nulls with zero
            bidf = bidf.fillna(0)
        
        self.feedback.setProgress(10)
        #======================================================================
        # scale
        #======================================================================
        if 'fscale' in bdf:
            log.info('scaling impact values by \'fscale\' column')
            bidf = bidf.multiply(bdf.set_index(bid)['fscale'], axis=0).round(self.prec)
            
            
        #======================================================================
        # drop down to worst case
        #======================================================================
        #reattach indexers
        bidf1 = bidf.join(ddf.loc[:, boolcol])
        
        assert not bidf1.isna().any().any()
        
        cdf = bidf1.groupby(cid).max().drop(bid, axis=1)
 
        #======================================================================
        # resolve alternate impacts (per evemt)-----
        #======================================================================
        #take maximum expected value at each asset
        if 'exlikes' in self.data_d:
            bres_df = self.ev_multis(cdf, self.data_d['exlikes'], aep_ser, logger=log)
            
        #no duplicates. .just rename by aep
        else:
            bres_df = cdf.rename(columns = aep_ser.to_dict()).sort_index(axis=1)
            
            assert bres_df.columns.is_unique, 'duplicate aeps require exlikes'
            
        log.info('got damages for %i events and %i assets'%(
            len(bres_df), len(bres_df.columns)))
        
        #======================================================================
        # checks
        #======================================================================
        #check the columns
        assert np.array_equal(bres_df.columns.values, aep_ser.unique()), 'column name problem'
        _ = self.check_monot(bres_df)
        #======================================================================
        # get ead per asset------
        #======================================================================
        if res_per_asset:
            self.feedback.setProgress(50)
            res_df = self.calc_ead(bres_df, drop_tails=self.drop_tails, logger=log).round(self.prec)
                        
        else:
            res_df = None
        
        self.feedback.setProgress(90)
        #======================================================================
        # totals
        #======================================================================        
        res_ser = self.calc_ead(bres_df.sum(axis=0).to_frame().T, logger=log).iloc[0]
        
        self.res_ser = res_ser.copy() #set for risk_plot()
        self.feedback.setProgress(95)
            
        
        #=======================================================================
        # wrap
        #=======================================================================
        log.info('finished on %i assets and %i damage cols'%(len(bres_df), len(res_ser)))

        #format resul series
        res = res_ser.to_frame()
        res.index.name = 'aep'
        res.columns = ['impacts']
        
        #remove tails
        if self.drop_tails:
            res = res.iloc[1:-2,:] #slice of ends 
            res.loc['ead'] = res_ser['ead'] #add ead back
        
         
        log.info('finished')


        return res.round(self.prec), res_df
    

if __name__ =="__main__": 
      print('???')