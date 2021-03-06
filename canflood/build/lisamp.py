'''
Created on Feb. 9, 2020

@author: cefect

probability sampler
sampling overlapping polygons at inventory points to calculate combined likelihoods
'''
#==========================================================================
# logger setup-----------------------
#==========================================================================
import logging, configparser, datetime, itertools



#==============================================================================
# imports------------
#==============================================================================
import os
import numpy as np
import pandas as pd


#Qgis imports
from qgis.core import QgsVectorLayer, QgsRasterLayer, QgsFeatureRequest, QgsProject, \
    QgsWkbTypes, QgsProcessingFeedback

#==============================================================================
# custom imports
#==============================================================================

from hlpr.exceptions import QError as Error


#from hlpr.basic import 

from hlpr.Q import view, Qcoms, vlay_get_fdf, vlay_get_fdata, vlay_new_df
#==============================================================================
# classes-------------
#==============================================================================
class LikeSampler(Qcoms):
    """
    Generate conditional probability data set ('exlikes') for each asset
    
    resolve conditional probability of realizing a single failure raster
    
    where polygons overlap (asset exposed to multiple failures):    
        attribute join of all, then
        union_probabilities()  calculates of multiple events using the exclusion principle
    where an asset has a unique polygon:
        simple attribute join
    

    """
    event_rels = 'indep'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        #self.resname = 'exlikes_%s'%self.tag
        
    def load_layers(self, #load data to project (for standalone runs)
                    lpol_fp_d, #{event name:polygon filepath}
                    finv_fp,
                    providerLib='ogr'
                    ):
        
        """
        special input loader for standalone runs
        
        """
        log = self.logger.getChild('load_layers')
        #======================================================================
        # load rasters
        #======================================================================
        lpol_d = self.load_lpols(lpol_fp_d, providerLib=providerLib, logger=log)
            
        #======================================================================
        # load finv vector layer
        #======================================================================
        finv_vlay = self.load_vlay(finv_fp, logger=log, providerLib=providerLib)

        #======================================================================
        # wrap
        #======================================================================
        log.debug('finished')
        return lpol_d, finv_vlay
    
    def load_lpols(self, #helper for loading vector polygons in standalone runs
                   lpol_files_d, #{event name:polygon filepath}
                   basedir = None, #optional directory to append to lpol_files_d
                    providerLib='ogr',
                    logger=None,
                    **kwargs
                   ):
        """
        can't load from a directory dump because we need to link to events
        """
        #=======================================================================
        # defaults
        #=======================================================================
        if logger is None: logger=self.logger
        log=logger.getChild('load_lpols')
        if not basedir is None:
            assert os.path.exists(basedir)
        
        
        log.info('on %i layers'%len(lpol_files_d))
        
        #=======================================================================
        # loop and load
        #=======================================================================
        lpol_d = dict()
        for ename, file_str in lpol_files_d.items():
            
            #get filepath
            if isinstance(basedir, str):
                fp = os.path.join(basedir, file_str)
            else:
                fp = file_str
                
            #load it
            lpol_d[ename] = self.load_vlay(fp, logger=log, providerLib=providerLib,
                                           **kwargs)
            
        log.debug('finished w/ %i'%len(lpol_d))
        return lpol_d
            
    def run(self, #sample conditional probability polygon 'lfield' values with finv geometry
            finv, #inventory layer
            lpol_d, #{event name: likelihood polygon layer}
            cid = None, #index field name on finv
            lfield = 'p_fail', #field with likelihhood value
            
           event_rels=None, #ev calculation method
                #mutEx: assume each event is mutually exclusive (only one can happen)
                    #lower bound
                #indep: assume each event is independent (failure of one does not influence the other)
                    #upper bound
            ):
        #=======================================================================
        # defults
        #=======================================================================

        log = self.logger.getChild('run')

        if cid is  None: cid=self.cid
        if event_rels is None: event_rels=self.event_rels
        self.event_rels=event_rels #reset for plotting
        #======================================================================
        # #check/load the data
        #======================================================================
        #check lpols
        for ename, vlay in lpol_d.items():
            if not isinstance(vlay, QgsVectorLayer):
                raise Error('bad type on %s layer: %s'%(ename, type(vlay)))
            assert 'Polygon' in QgsWkbTypes().displayString(vlay.wkbType()), \
                'unexpected geometry: %s'%QgsWkbTypes().displayString(vlay.wkbType())
            assert lfield in [field.name() for field in vlay.fields()], \
                'specified lfield \"%s\' not on layer'
            assert vlay.isValid()
            assert vlay.crs() == self.qproj.crs(), 'crs mismatch on %s'%vlay.name()
            #==================================================================
            # #check values
            #==================================================================
            
            chk_df = vlay_get_fdf(vlay, logger=log)
            chk_ser = chk_df.loc[:, lfield]
            
            assert not chk_ser.isna().any(), 'got nulls on %s'%ename
        
            #if 0<fval<1
            boolidx = np.logical_and( #checking for fails
                chk_ser <0,
                chk_ser >1,)
            
            if boolidx.any():
                raise Error('%s.%s got %i (of %i) values out of range: \n%s'%(
                    ename,lfield, boolidx.sum(), len(boolidx), chk_ser[boolidx]))
            
        #check finv
        assert isinstance(finv, QgsVectorLayer), 'bad type on finv'
        assert finv.isValid(), 'invalid finv'
        assert cid in  [field.name() for field in finv.fields()], 'missing cid \'%s\''%cid
        assert finv.crs() == self.crs, 'crs mismatch on %s'%finv.name()
            

        #======================================================================
        # build finv
        #======================================================================
        #clean out finv
        fc_vlay = self.deletecolumn(finv, [cid], invert=True, layname='fclean')
        self.createspatialindex(fc_vlay, logger=log)
        
        self.fc_vlay = fc_vlay #set this for vectorize()
        #get cid list
        fdf = vlay_get_fdf(fc_vlay, logger=log)
        cid_l = fdf[cid].tolist()
 
        #======================================================================
        # sample values------
        #======================================================================
        log.info('sampling %i lpols w/ %i finvs and event_rels=\'%s\''%(
            len(lpol_d), len(cid_l), event_rels))
        en_c_sval_d = dict() #container for samples {event name: sample data}
        for ename, lp_vlay in lpol_d.items():
            log = self.logger.getChild('run.%s'%ename)
            log.debug('sampling %s from %s to %s w/ %i atts'%(
                lfield, lp_vlay.name(), fc_vlay.name(), len(fdf)))
            
            """
            todo: remove any features w/ zero value
            view(fc_vlay)
            """
            #===================================================================
            # sapmle values from polygons
            #===================================================================
            svlay, new_fns, jcnt = self.joinattributesbylocation(fc_vlay, lp_vlay, [lfield],
                                                  method=0, #one-to-many
                                                  logger=log,
                                                  expect_j_overlap=True,
                                                  allow_none=True,
                                                  )
            
            if jcnt == 0:
                log.warning('no assets intersect failure polygons!')
                #set a dummy entri
                en_c_sval_d[ename] = {k:[] for k in cid_l}
                continue

            #extract raw sampling data
            sdf_raw = vlay_get_fdf(svlay, logger=log) #df w/ columns = [cid, lfield]
            
            #==================================================================
            # #do some checks
            #=================================================================
            #check columns
            miss_l = set(sdf_raw.columns).symmetric_difference([lfield, cid])
            assert len(miss_l) == 0, 'bad columns on the reuslts'
            #make sure all the cids made it
            miss_l = set(cid_l).difference(sdf_raw[cid].unique().tolist())
            assert len(miss_l) == 0, 'failed to get %i assets in the smaple'%len(miss_l)
            
            #==================================================================
            # clean it
            #==================================================================
            #log misses
            boolidx = sdf_raw[lfield].isna()
            log.debug('got %i (of %i) misses. dropping these'%(boolidx.sum(), len(boolidx)))
            
            #drop misses
            sdf = sdf_raw.dropna(subset=[lfield], axis=0, how='any')

            #==================================================================
            # pivot to {cid:[sample values]}
            #==================================================================

            #drop down to cid groups (pvali values)
            d = {k:csdf[lfield].to_list() for k,csdf in sdf.groupby(cid)}
            
            #add dummy empty list for any missing cids
            """not very elegent... doing this to fit in with previous methods
            would be better to just use open joins"""
            cid_samp_d = {**d, **{k:[] for k in cid_l if not k in d}}
                
            #wrap event loop
            en_c_sval_d[ename] = cid_samp_d #add to reuslts
            log.debug('collected sample values on %i assets'%len(cid_samp_d))
        
        
        
        #======================================================================
        # resolve multiple events------
        #======================================================================
        log = self.logger.getChild('run')
        log.info('collected sample values for %i events and %i assets'%(
            len(en_c_sval_d), len(cid_l)))
        
        res_df = None #build results contqainer

        #loop and resolve

        log.debug('resolving %i events'%len(en_c_sval_d))
        for ename, cid_samp_d in en_c_sval_d.items():
            log.info('resolving \"%s\''%ename)
            
            #===================================================================
            # #loop through each asset and resolve sample values
            #===================================================================
            """
            TODO: Parallel process this
            """
            cid_res_d = dict() #harmonized likelihood results
            for cval, pvals in cid_samp_d.items():

                #simple unitaries
                if len(pvals) == 1:
                    cid_res_d[cval] = pvals[0]
                    
                elif len(pvals) == 0:
                    cid_res_d[cval] = np.nan
                    
                #multi value
                else:
                    
                    #calc union probability for multi predictions
                    if event_rels ==  'indep':
                        cid_res_d[cval] = self.union_probabilities(pvals, logger=log)
                    elif event_rels == 'mutEx':
                        cid_res_d[cval] = sum(pvals)
                    else:
                        raise Error('bad event_rels: \'%s\''%event_rels)
                               
                
            #===================================================================
            # #update results
            #===================================================================
            res_ser = pd.Series(cid_res_d, name=ename).sort_index()
            if res_df is None:
                res_df = res_ser.to_frame()
                res_df.index.name = cid
            else:
                """
                if not np.array_equal(res_df.index, res_ser.index):
                    raise Error('index mmismatch')"""
                res_df = res_df.join(res_ser, how='left')
                
            #===================================================================
            # check
            #===================================================================
            """
            res_ser.max()
            """
            bx = res_ser>1.0
            if bx.any():
                log.debug(res_ser[bx])
                raise Error('%s got %i (of %i) resolved P > 1.0.. check logger'%(
                    ename, bx.sum(), (len(bx))))
            
        #======================================================================
        # wrap-------
        #======================================================================
        log = self.logger.getChild('run')
        
        #=======================================================================
        # nulls
        #=======================================================================
        """2021-01-12: moved null handling from the model to here"""
        res_df = res_df.fillna(0.0)
        
        if res_df.isna().all().all():
            raise Error('no intersections with any events!')
            return res_df
            
            
        res_df = res_df.round(self.prec)
        #======================================================================
        # post checks
        #======================================================================
        miss_l = set(lpol_d.keys()).symmetric_difference(res_df.columns)
        assert len(miss_l) == 0, 'failed to match columns to events'
        
        #bounds
        if not res_df.max().max() <=1.0:
            raise Error('bad max: %.2f'%res_df.max().max())
        assert res_df.min().min() >= 0.0, 'bad min'
        
        miss_l = set(res_df.index).symmetric_difference(cid_l)
        assert len(miss_l)==0, 'missed some cids'
        
        #all nulls
        bc = res_df.isna().all(axis=0)
        if bc.any():
            log.warning('%i (of %i) events have no intersect!\n    %s'%(
                bc.sum(), len(bc), res_df.columns[bc].tolist()))
        
        bx = res_df.isna().all(axis=1)
        if bx.any():
            log.warning('%i (of %i) assets have no intersect!'%(
                bx.sum(), len(bx)))
        
        #======================================================================
        # close
        #======================================================================
        try: #fancy reporting
            log.debug('results stats: \nmeans: \n    %s\nnulls \n    %s \nmaxes: \n    %s \nmins: \n    %s\n\n'%(
                res_df.mean().to_dict(), 
                res_df.isna().sum().to_dict(), 
                res_df.max().to_dict(),
                res_df.min().to_dict()))
            
            log.info('finished w/ %s event_rels = \'%s\'.. see log'%(str(res_df.shape), event_rels))        
        except: log.error('logging error')

        return res_df #will have NaNs where there is no intersect
    
    """
    view(res_df)
    """
    
    def union_probabilities(self,
                            probs,
                            logger = None,
                            ):
        """
        calculating the union probability of multiple independent events using the exclusion principle
        
        probability that ANY of the passed independent events will occur
            
        
        https://en.wikipedia.org/wiki/Inclusion%E2%80%93exclusion_principle#In_probability
        
        from Walter
    
        Parameters
        ----------
        probs_list : Python 1d list
            A list of probabilities between 0 and 1 with len() less than 23
            After 23, the memory consumption gets huge. 23 items uses ~1.2gb of ram. 
    
        Returns
        -------
        total_prob : float64
            Total probability 
            
        """
        if logger is None: logger=self.logger
        #log = self.logger.getChild('union_probabilities')
        #======================================================================
        # prechecks
        #======================================================================
        assert isinstance(probs, list), 'unexpected type: %s'%type(probs)
        assert len(probs) >0, 'got empty container'
        #======================================================================
        # prefilter
        #======================================================================
        #guranteed
        if max(probs) == 1.0:
            #log.debug('passed a probability with 1.0... returning this')
            return 1.0
        
        #clean out zeros
        if 0.0 in probs:
            probs = [x for x in probs if not x==0]
        
        
        #===========================================================================
        # do some checks
        #===========================================================================
        
        assert (len(probs) < 20), "list too long"
        assert (all(map(lambda x: x < 1 and x > 0, probs))), 'probabilities out of range'
        
        #===========================================================================
        # loop and add (or subtract) joint probabliities
        #===========================================================================
        #log.debug('calc total_prob for %i probs: %s'%(len(probs), probs))
        total_prob = 0
        for r in range(1, len(probs) + 1): #enumerate through each entry in the probs list
 
            combs = itertools.combinations(probs, r) #assemble all the possible combinations
            """
            list(combs)
            """
            #multiply all the probability combinations together and add for this layer
            total_prob += ((-1) ** (r + 1)) * sum([np.prod(items) for items in combs])
            

        
        assert total_prob <1 and total_prob > 0, 'bad result'
    
        return total_prob
    
    def vectorize(self, #map results back onto the finv geometry 
                  res_df_raw,
                  layName=None,
                  ):
        
        log = self.logger.getChild('vectorize')
        if layName is None: layName = 'exlikes_%s'%self.tag
        res_df = res_df_raw.copy()
        #======================================================================
        # extract data from finv
        #======================================================================
        vlay = self.fc_vlay
        
        #get geometry
        geo_d = vlay_get_fdata(vlay, geo_obj=True)
        
        #get key conversion
        fid_cid_d = vlay_get_fdata(vlay, fieldn=self.cid, logger=log)
        
        #convert geo
        cid_geo_d = {fid_cid_d[k]:v for k, v in geo_d.items()}
        
        #======================================================================
        # build the layer
        #======================================================================
        assert res_df.index.name == self.cid, 'bad index on res_df'
        
        res_df[self.cid] = res_df.index #copy it over
        
        res_vlay = vlay_new_df(res_df, vlay.crs(), geo_d = cid_geo_d, 
                               layname = layName,
                                logger=log)
        
        return res_vlay
    
    def check(self):
        pass #placeholder
    
    def write_res(self, res_df,ofn=None, **kwargs):
        if ofn is None: ofn = 'exlikes_%s'%self.tag
        return self.output_df(res_df, ofn,write_index=True, **kwargs)
    
    def upd_cf(self, cf_fp): #configured control file updater
        return self.update_cf(
            {'risk_fps':(
                {'exlikes':self.out_fp}, 
                '#\'exlikes\' file path set from lisamp.py at %s'%(datetime.datetime.now().strftime('%Y-%m-%d %H.%M.%S')),
                )
             },
            cf_fp = cf_fp
            )
        
    def plot_hist_all(self, df, #plot failure histogram of all layers
                      
                    #figure parametrs
                    figsize     = (6.5, 4), 
                    grid=True,
                      
                      ): #plot all the histograms stacked
        
        """
        dont want to initiate matplotlib in the module...
            just using a nasty single f unction
        """
        #=======================================================================
        # defaults
        #=======================================================================
        log = self.logger.getChild('plot')
        title = '%s Conditional P histogram on %i events'%(self.tag, len(df.columns))
        
        #=======================================================================
        # manipulate data
        #=======================================================================
        #get a collectio nof arrays from a dataframe's columns
        data = [ser.values for _, ser in df.items()]
        #======================================================================
        # setup
        #======================================================================
        
        import matplotlib
        matplotlib.use('Qt5Agg') #sets the backend (case sensitive)
        import matplotlib.pyplot as plt
        
        #set teh styles
        plt.style.use('default')
        
        #font
        matplotlib_font = {
                'family' : 'serif',
                'weight' : 'normal',
                'size'   : 8}
        
        matplotlib.rc('font', **matplotlib_font)
        matplotlib.rcParams['axes.titlesize'] = 10 #set the figure title size
        
        #spacing parameters
        matplotlib.rcParams['figure.autolayout'] = False #use tight layout
        
        
        
        #======================================================================
        # figure setup
        #======================================================================
        plt.close()
        fig = plt.figure(figsize=figsize,
                     tight_layout=False,
                     constrained_layout = True,
                     )
        
        #axis setup
        ax1 = fig.add_subplot(111)
        
        #aep units
        ax1.set_xlim(0, 1.0)
 
        
        # axis label setup
        fig.suptitle(title)
        ax1.set_xlabel('Pfail')
        ax1.set_ylabel('asset count')
        """
        plt.show()
        
        pd.__version__
        """

        
        #=======================================================================
        # plot thie histogram
        #=======================================================================
        histVals_ar, bins_ar, patches = ax1.hist(
            data, bins='auto', stacked=False, label=df.columns.to_list(),
            alpha=0.9)
        
        
        #=======================================================================
        # Add text string 'annot' to lower left of plot
        #=======================================================================
        val_str = '%i assets \nevent_rels=\'%s\''%(len(df), self.event_rels)
        xmin, xmax1 = ax1.get_xlim()
        ymin, ymax1 = ax1.get_ylim()
        
        x_text = xmin + (xmax1 - xmin)*.5 # 1/10 to the right of the left ax1is
        y_text = ymin + (ymax1 - ymin)*.5 #1/10 above the bottom ax1is
        anno_obj = ax1.text(x_text, y_text, val_str)
        
        #=======================================================================
        # post formatting
        #=======================================================================
        if grid: 
            ax1.grid()
        

        #legend
        h1, l1 = ax1.get_legend_handles_labels() #pull legend handles from axis 1

        ax1.legend(h1, l1, loc=1) #turn legend on with combined handles
        
        
        return fig
        

    def plot_box_all(self, df, #plot failure histogram of all layers
                      
                    #figure parametrs
                    figsize     = (6.5, 4), 
                    grid=True,
                      
                      ): #plot all the histograms stacked
        
        """
        dont want to initiate matplotlib in the module...
            just using a nasty single f unction
        """
        #=======================================================================
        # defaults
        #=======================================================================
        log = self.logger.getChild('plot')
        title = '%s Conditional P boxplots on %i events'%(self.tag, len(df.columns))
        
        #=======================================================================
        # manipulate data
        #=======================================================================
        #get a collectio nof arrays from a dataframe's columns
        data = [ser.values for _, ser in df.items()]
        #======================================================================
        # setup
        #======================================================================
        
        import matplotlib
        matplotlib.use('Qt5Agg') #sets the backend (case sensitive)
        import matplotlib.pyplot as plt
        
        #set teh styles
        plt.style.use('default')
        
        #font
        matplotlib_font = {
                'family' : 'serif',
                'weight' : 'normal',
                'size'   : 8}
        
        matplotlib.rc('font', **matplotlib_font)
        matplotlib.rcParams['axes.titlesize'] = 10 #set the figure title size
        
        #spacing parameters
        matplotlib.rcParams['figure.autolayout'] = False #use tight layout
        
        
        
        #======================================================================
        # figure setup
        #======================================================================
        plt.close()
        fig = plt.figure(figsize=figsize,
                     tight_layout=False,
                     constrained_layout = True,
                     )
        
        #axis setup
        ax1 = fig.add_subplot(111)
        
        #aep units
        ax1.set_ylim(0, 1.0)
 
        
        # axis label setup
        fig.suptitle(title)
        ax1.set_xlabel('hazard layer')
        ax1.set_ylabel('Pfail')
        """
        plt.show()
        
        pd.__version__
        """

        
        #=======================================================================
        # plot thie histogram
        #=======================================================================
        boxRes_d = ax1.boxplot(data, whis=1.5)
        


        #=======================================================================
        # format axis labels
        #======================================================= ================
        #apply the new labels
        ax1.set_xticklabels(df.columns, rotation=90, va='center', y=.5, color='red')
        
        
        #=======================================================================
        # Add text string 'annot' to lower left of plot
        #=======================================================================
        val_str = '%i assets \nevent_rels=\'%s\''%(len(df), self.event_rels)
        xmin, xmax1 = ax1.get_xlim()
        ymin, ymax1 = ax1.get_ylim()
        
        x_text = xmin + (xmax1 - xmin)*.5 # 1/10 to the right of the left ax1is
        y_text = ymin + (ymax1 - ymin)*.8 #1/10 above the bottom ax1is
        anno_obj = ax1.text(x_text, y_text, val_str)

        
        
        return fig
        



    


    
    
    
    

