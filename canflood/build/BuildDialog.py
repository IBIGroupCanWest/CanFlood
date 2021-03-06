# -*- coding: utf-8 -*-
"""
ui class for the BUILD toolset
"""
#==============================================================================
# imports-----------
#==============================================================================
#python
import sys, os, datetime, time

from shutil import copyfile

"""see __init__.py for dependency check"""
import pandas as pd
import numpy as np #assuming if pandas is fine, numpy will be fine

#PyQt
from PyQt5 import uic, QtWidgets
from PyQt5.QtWidgets import QAction, QFileDialog, QListWidget, QTableWidgetItem

#qgis

from qgis.core import *


#==============================================================================
# custom imports
#==============================================================================

from build.rsamp import Rsamp
from build.lisamp import LikeSampler
#from build.rfda import RFDAconv
from build.prepr import Preparor
from build.validator import Vali



import hlpr.plug
#from hlpr.Q import vlay_get_fdf

from hlpr.basic import get_valid_filename, force_open_dir 
from hlpr.exceptions import QError as Error

from .vfunc_dialog import vDialog

#===============================================================================
# load UI file
#===============================================================================
# This loads your .ui file so that PyQt can populate your plugin with the elements from Qt Designer
ui_fp = os.path.join(os.path.dirname(__file__), 'build.ui')
assert os.path.exists(ui_fp), 'failed to find the ui file: \n    %s'%ui_fp
FORM_CLASS, _ = uic.loadUiType(ui_fp)


#===============================================================================
# class objects-------
#===============================================================================

class DataPrep_Dialog(QtWidgets.QDialog, FORM_CLASS, hlpr.plug.QprojPlug):
    
    event_name_set = [] #event names
    

    def __init__(self, iface, parent=None):
        #=======================================================================
        # #init baseclass
        #=======================================================================
        """these will only ini tthe first baseclass (QtWidgets.QDialog)
        
        required"""
        
        super(DataPrep_Dialog, self).__init__(parent) #only calls QtWidgets.QDialog

        #=======================================================================
        # attachments
        #=======================================================================

        self.ras = []
        self.ras_dict = {}
        self.vec = None

        self.iface = iface
        
        self.vDialog = vDialog(self.iface) #init and attach (connected below)
        
        #=======================================================================
        # setup funcs
        #=======================================================================
        
        self.setupUi(self)
        
        # Set up the user interface from Designer through FORM_CLASS.
        # After self.setupUi() you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        
        
        self.qproj_setup() #basic dialog worker setup
        
        self.connect_slots()
        
        
        self.logger.debug('DataPrep_Dialog initilized')
        

    def connect_slots(self):
        log = self.logger.getChild('connect_slots')

        #======================================================================
        # pull project data
        #======================================================================
        #pull layer info from project
        rlays_d = dict()
        vlays_d = dict()
        for layname, layer in QgsProject.instance().mapLayers().items():
            if isinstance(layer, QgsVectorLayer):
                vlays_d[layname] = layer
            elif isinstance(layer, QgsRasterLayer):
                rlays_d[layname] = layer
            else:
                self.logger.debug('%s not filtered'%layname)
                
        #=======================================================================
        # general----------------
        #=======================================================================

        #ok/cancel buttons
        self.buttonBox.accepted.connect(self.reject) #back out of the dialog
        self.buttonBox.rejected.connect(self.reject)
        
        
        #connect to status label
        """
        this could be moved onto the feedback object...
            but would be a lot of work to move it off the logger
            and not sure what the benefit would be
            
            see hlpr.plug.logger._loghlp()
        """
        self.logger.statusQlab=self.progressText #connect to the progress text
        #self.logger.statusQlab.setText('BuildDialog initialized')
                
        #======================================================================
        #TAB: SETUP----------
        #======================================================================
        #=======================================================================
        # session controls
        #=======================================================================
        #Working Directory 
        """default is set below.
        doesn't seem to open the displayed directory on first click"""
        def browse_wd():
            return self.browse_button(self.lineEdit_wd, prompt='Select Working Directory',
                                      qfd = QFileDialog.getExistingDirectory)
            
        self.pushButton_wd.clicked.connect(browse_wd) # SS. Working Dir. Browse
        
        #WD force open
        def open_wd():
            force_open_dir(self.lineEdit_wd.text())
        
        self.pushButton_wd_open.clicked.connect(open_wd)
        
        #AOI
        self.comboBox_aoi.setFilters(QgsMapLayerProxyModel.PolygonLayer) #SS. Project AOI
        self.comboBox_aoi.setCurrentIndex(-1) #by default, lets have this be blank
        
        #Controls
        self.checkBox_SSoverwrite.stateChanged.connect(self.set_overwrite) #SS overwrite data files

        
        #CanFlood Control File
        def browse_cf():
            return self.browse_button(self.lineEdit_cf_fp, prompt='Select CanFlood control file',
                           qfd=QFileDialog.getOpenFileName)
            
        self.pushButton_cf.clicked.connect(browse_cf)# SS. Model Control File. Browse
        

        
        
        #=======================================================================
        # Control File Assembly
        #=======================================================================
        #elevation t ype
        self.comboBox_SSelv.addItems(['datum', 'ground']) #ss elevation type
        
                
        #Vulnerability Curve Set
        def browse_curves():
            return self.browse_button(self.lineEdit_curve, prompt='Select Curve Set',
                                      qfd = QFileDialog.getOpenFileName)
            
        self.pushButton_SScurves.clicked.connect(browse_curves)# SS. Vuln Curve Set. Browse
        
        #generate new control file      
        self.pushButton_generate.clicked.connect(self.build_scenario) #SS. generate
        

        
        #=======================================================================
        # TAB: INVENTORY------------
        #=======================================================================
        
        #=======================================================================
        # vfunc
        #=======================================================================
        #give commmon widgets
        self.vDialog.lineEdit_wd = self.lineEdit_wd #share the reference
        self.vDialog.lineEdit_curve = self.lineEdit_curve
        self.vDialog.linEdit_ScenTag = self.linEdit_ScenTag
        
        #connect launcher button
        def vDia(): #helper to connect slots and 
            """only executing setup once called to simplify initial loading"""
            _ = self.vDialog._setup()
            self.vDialog.show()
            
        self.pushButton_inv_vfunc.clicked.connect(vDia)
        self.pushButton_Inv_curves.clicked.connect(self.store_curves)

        #=======================================================================
        # Store IVlayer
        #=======================================================================
        #inventory vector layer box
        self.comboBox_ivlay.setFilters(QgsMapLayerProxyModel.VectorLayer) #SS. Inventory Layer: Drop down
        


        #find a good layer
        if len(vlays_d)>0:
            try:
                for layname, vlay in vlays_d.items():
                    if layname.startswith('finv'):
                        break
                
                self.logger.debug('setting comboBox_vec = %s'%vlay.name())
                self.comboBox_ivlay.setLayer(vlay)
            except Exception as e:
                self.logger.debug('failed to set inventory layer w: \n    %s'%e)
            

        #index field name
        #change the 'cid' display when the finv selection changes
        def upd_cid():
            return self.mfcb_connect(
                self.mFieldComboBox_cid, self.comboBox_ivlay.currentLayer(),
                fn_str = 'xid' )
                
        self.comboBox_ivlay.layerChanged.connect(upd_cid) #SS inventory vector layer
        
        #connect button
        self.pushButton_Inv_store.clicked.connect(self.convert_finv)
        
        
        #=======================================================================
        # NRPI
        #=======================================================================
        #filter the vector layer
        self.mMapLayerComboBox_inv_finv.setFilters(QgsMapLayerProxyModel.VectorLayer) 
        self.mMapLayerComboBox_inv_finv.setCurrentIndex(-1) #clear the selection
        
        #connect the push button
        self.pushButton_inv_const.clicked.connect(self.construct_finv)
        
        



        #======================================================================
        # TAB: HAZARD SAMPLER---------
        #======================================================================
        
        #=======================================================================
        # raster layer selection box
        #=======================================================================
        # Set GUI elements
        self.comboBox_ras.setFilters(QgsMapLayerProxyModel.RasterLayer)
        """
        todo: swap this out with better selection widget
        """
        #selection       
        self.pushButton_remove.clicked.connect(self._HS_remove)
        self.pushButton_HS_clear.clicked.connect(self._HS_clearBox)
        self.pushButton_add_all.clicked.connect(self._HS_addAll)
        
        self.comboBox_ras.currentTextChanged.connect(self._HS_comboAdd)
        
        #=======================================================================
        # inundation
        #=======================================================================
        self.comboBox_HS_DTM.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.comboBox_HS_DTM.setAllowEmptyLayer(True)
        self.comboBox_HS_DTM.setCurrentIndex(-1) #set selection to none
        #=======================================================================
        # #complex
        #=======================================================================
        #display the gtype when the finv changes
        def upd_gtype():
            vlay = self.comboBox_ivlay.currentLayer()
            if isinstance(vlay,QgsVectorLayer):
                gtype = QgsWkbTypes().displayString(vlay.wkbType())
                self.label_HS_finvgtype.setText(gtype)
            
        self.comboBox_ivlay.layerChanged.connect(upd_gtype) #SS inventory vector layer
        
        #display sampling stats options to user 
        def upd_stat():
            vlay = self.comboBox_ivlay.currentLayer()
            self.comboBox_HS_stat.clear()
            if isinstance(vlay,QgsVectorLayer):
                gtype = QgsWkbTypes().displayString(vlay.wkbType())
                self.comboBox_HS_stat.setCurrentIndex(-1)
                
                if 'Polygon' in gtype or 'Line' in gtype:
                    self.comboBox_HS_stat.addItems(
                        ['','Mean','Median','Min','Max'])
                
        self.comboBox_ivlay.layerChanged.connect(upd_stat) #SS inventory vector layer
            
            
        #disable sample stats when %inundation is checked
        def tog_SampStat(): #toggle the sample stat dropdown
            pstate = self.checkBox_HS_in.isChecked()
            #if checked, enable the second box
            self.comboBox_HS_stat.setDisabled(pstate) #disable it
            self.comboBox_HS_stat.setCurrentIndex(-1) #set selection to none
            
        self.checkBox_HS_in.stateChanged.connect(tog_SampStat)
        
        
        #=======================================================================
        # #execute buttons
        #=======================================================================
        self.pushButton_HSgenerate.clicked.connect(self.run_rsamp)
        self.pushButton_HS_prep.clicked.connect(self.run_rPrep)
        #======================================================================
        # TAB: EVENT VARIABLES---------
        #======================================================================
        self.pushButton_ELstore.clicked.connect(self.set_event_vals)
        """not much here?
        
        table population is done by run_rsamp()
        """
        

        #======================================================================
        # TAB: CONDITIONAL P-----------
        #======================================================================
        """
        run_rsamp() attempts to populate this
        
        todo: rename the buttons so they align w/ the set labels
        
        todo: automatically populate the first column of boxes w/ those layers
        sampled w/ rsamp
        """
        #list of combo box names on the likelihood sampler tab
        self.ls_cb_d = { #set {hazard raster : lpol}
            1: (self.MLCB_LS1_event_3, self.MLCB_LS1_lpol_3),
            2: (self.MLCB_LS1_event_4, self.MLCB_LS1_lpol_4),
            3: (self.MLCB_LS1_event_5, self.MLCB_LS1_lpol_5),
            4: (self.MLCB_LS1_event,   self.MLCB_LS1_lpol),
            5: (self.MLCB_LS1_event_6, self.MLCB_LS1_lpol_6),
            6: (self.MLCB_LS1_event_7, self.MLCB_LS1_lpol_7),
            7: (self.MLCB_LS1_event_2, self.MLCB_LS1_lpol_2),
            8: (self.MLCB_LS1_event_8, self.MLCB_LS1_lpol_8)
            }
        
        #loop and set filteres
        first = True
        for sname, (mlcb_haz, mlcb_lpol) in self.ls_cb_d.items():
            
            #set drop down filters on hazard bars
            mlcb_haz.setFilters(QgsMapLayerProxyModel.RasterLayer)
            mlcb_haz.setAllowEmptyLayer(True)
            mlcb_haz.setCurrentIndex(-1) #set selection to none
            
            #on polygon bars
            mlcb_lpol.setFilters(QgsMapLayerProxyModel.PolygonLayer)
            mlcb_lpol.setAllowEmptyLayer(True)
            mlcb_lpol.setCurrentIndex(-1) #set selection to none
            
            #store the first lpol box for connecting the FieldName dropdown
            if first:
                mlcb_lpol_1 = mlcb_lpol
                first = False

            
        #connect to update the field name box (based on the first layer)
        def upd_lfield(): #updating the field box
            return self.mfcb_connect(
                self.mFieldComboBox_LSfn, mlcb_lpol_1.currentLayer(),
                fn_str = 'fail' )
    
        
        mlcb_lpol_1.layerChanged.connect(upd_lfield)
        
            
        #connect execute
        self.pushButton_LSsample.clicked.connect(self.run_lisamp)
        
        
        #=======================================================================
        # clear button
        #=======================================================================

                    
        self.pushButton_CP_clear.clicked.connect(self._CP_clear)
        #======================================================================
        # DTM sampler---------
        #======================================================================
        self.comboBox_dtm.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.pushButton_DTMsamp.clicked.connect(self.run_dsamp)
        
        #======================================================================
        # validator-----------
        #======================================================================
        self.pushButton_Validate.clicked.connect(self.run_validate)
        
        #======================================================================
        # project defaults-----------
        #======================================================================
        """"
        to speed up testing.. manually configure the project
        """

        debug_dir =os.path.join(os.path.expanduser('~'), 'CanFlood', 'build')
        #self.lineEdit_cf_fp.setText(os.path.join(debug_dir, 'CanFlood_scenario1.txt'))
        self.lineEdit_wd.setText(debug_dir)
        
        if not os.path.exists(debug_dir):
            log.info('building directory: %s'%debug_dir)
            os.makedirs(debug_dir)
            
        #=======================================================================
        # wrap
        #=======================================================================
        return
            


    #===========================================================================
    # common methods----------
    #===========================================================================
    def slice_aoi(self, vlay):
        
        aoi_vlay = self.comboBox_aoi.currentLayer()
        log = self.logger.getChild('slice_aoi')
        
        
        #=======================================================================
        # selection
        #=======================================================================
        if self.checkBox_sels.isChecked():
            if not aoi_vlay is None: 
                raise Error('only one method of aoi selection is allowed')
            
            log.info('slicing finv \'%s\' w/ %i selected feats'%(
                vlay.name(), vlay.selectedFeatureCount()))
            
            res_vlay = self.saveselectedfeatures(vlay, logger=log)
        #=======================================================================
        # check for no selection
        #=======================================================================
        elif aoi_vlay is None:
            log.debug('no aoi selected... not slicing')
            return vlay

        #=======================================================================
        # slice
        #=======================================================================
        else:
            vlay.removeSelection()
            log.info('slicing finv \'%s\' and %i feats w/ aoi \'%s\''%(
                vlay.name(),vlay.dataProvider().featureCount(), aoi_vlay.name()))
            
            self.check_aoi(aoi_vlay)
            
            res_vlay =  self.selectbylocation(vlay, aoi_vlay, result_type='layer', logger=log)
            
            assert isinstance(res_vlay, QgsVectorLayer)
            
            vlay.removeSelection()
            
            res_vlay.setName('%s_aoi'%vlay.name())
        
        #=======================================================================
        # wrap
        #=======================================================================
        """no... we use this as a backend pre-filter alot
        only load excplicitly called slice values
        if self.checkBox_loadres.isChecked():
            self.qproj.addMapLayer(res_vlay)
            self.logger.info('added \'%s\' to canvas'%res_vlay.name())
            """
            
        
            
        return res_vlay
            
            
    #===========================================================================
    # Run Actions------
    #===========================================================================


    def build_scenario(self): #'Generate' on the setup tab
        """
        Generate a CanFlood project from scratch
        
        This tab facilitates the creation of a Control File from user specified parameters and inventory, 
            as well as providing general file control variables for the other tools in the toolset.
            
        
        
        """
        log = self.logger.getChild('build_scenario')
        log.info('build_scenario started')
        tag = self.linEdit_ScenTag.text() #set the secnario tag from user provided name
        wdir =  self.lineEdit_wd.text() #pull the wd filepath from the user provided in 'Browse'
        

        #=======================================================================
        # prechecks
        #=======================================================================
        assert isinstance(wdir, str)
        assert isinstance(tag, str)
 
        if self.radioButton_SS_fpRel.isChecked():
            raise Error('Relative filepaths not implemented')
             
        #======================================================================
        # setup working directory
        #======================================================================
        if not os.path.exists(wdir):
            os.makedirs(wdir)
            log.info('built working directory: %s'%wdir)
        self.feedback.upd_prog(10)
            
        #=======================================================================
        # run the control file builder----
        #=======================================================================
        #initilize
        wrkr = Preparor(logger=self.logger,  out_dir=wdir, tag=tag, feedback=self.feedback)
        self.feedback.upd_prog(20)
        
        #=======================================================================
        # #copy the template
        #=======================================================================
        cf_path = wrkr.copy_cf_template(wdir, logger=self.logger)
        self.feedback.upd_prog(75)
        
        #=======================================================================
        # #set some basics
        #=======================================================================
        #=======================================================================
        # if not self.lineEdit_curve.text()=='':
        #     curves_fp=self.lineEdit_curve.text()
        # else:
        #     curves_fp = None
        #=======================================================================
            
        wrkr.upd_cf_first(scenarioName=self.linEdit_ScenTag.text())
 
        log.info("default CanFlood model config file created :\n    %s"%cf_path)
        
        """NO. should only populate this automatically from ModelControlFile.Browse
        self.lineEdit_curve.setText(os.path.normpath(os.path.join(wdir, 'CanFlood - curve set 01.xls')))"""
        
        """TODO:
        write aoi filepath to scratch file
        """
        self.feedback.upd_prog(95)
        #======================================================================
        # wrap
        #======================================================================
        
        #display the control file in the dialog
        self.lineEdit_cf_fp.setText(cf_path)

        log.push('control file created for "\'%s\''%tag)
        self.feedback.upd_prog(None) #set the progress bar back down to zero

    def store_curves(self): #write the curves_fp to the control file
        
        curves_fp=self.lineEdit_curve.text()
        cf_fp = self.get_cf_fp()
        self.feedback.upd_prog(10)
        #=======================================================================
        # precheck
        #=======================================================================
        assert os.path.exists(curves_fp), 'bad curves_fp: %s'%curves_fp


        #=======================================================================
        # execute
        #=======================================================================
        #get a simple worker to handle the control file
        wrkr = Preparor(logger=self.logger,  feedback=self.feedback,
                       # out_dir=None, tag=tag, cid=cid, overwrite=self.overwrite
                        cf_fp=cf_fp, 
                        ) 
        self.feedback.upd_prog(50)
        wrkr.update_cf(
            {
            'dmg_fps':(
                {'curves':curves_fp}, 
                '#\'curves\' file path set from BuildDialog.py at %s'%(datetime.datetime.now().strftime('%Y-%m-%d %H.%M.%S')),
                ),
             },
            )
        
        self.feedback.upd_prog(95)
        self.feedback.upd_prog(None)
        
    def convert_finv(self): #aoi slice and convert the finv vector to csv file
        
        log = self.logger.getChild('convert_finv')
        self.feedback.upd_prog(5)
        
        
        #=======================================================================
        # retrieve data
        #=======================================================================
        cid = self.mFieldComboBox_cid.currentField() #user selected field
        vlay_raw = self.comboBox_ivlay.currentLayer()
        cf_fp = self.get_cf_fp()
        tag = self.linEdit_ScenTag.text() #set the secnario tag from user provided name
        wdir =  self.lineEdit_wd.text() #pull the wd filepath from the user provided in 'Browse'
        
        #======================================================================
        # prechecks
        #======================================================================
        assert isinstance(vlay_raw, QgsVectorLayer), 'must select a VectorLayer'
        
        assert vlay_raw.crs()==self.qproj.crs(), 'finv CRS (%s) does not match projects (%s)'%(vlay_raw.crs(), self.qproj.crs())
        
 
        
        #=======================================================================
        # aoi slice
        #=======================================================================
        vlay = self.slice_aoi(vlay_raw)
        
        #name check
        if len(vlay.name()) > 50:
            vlay.setName(vlay.name()[0:50])
        
        
        if self.checkBox_loadres.isChecked():
            self.qproj.addMapLayer(vlay)
            self.logger.info('added \'%s\' to canvas'%vlay.name())
            self.comboBox_ivlay.setLayer(vlay) #set this as the new finv
        
        self.feedback.upd_prog(30)
        
        #=======================================================================
        # extract, download, and update cf
        #=======================================================================
        wrkr = Preparor(logger=self.logger,  out_dir=wdir, tag=tag, feedback=self.feedback,
                        cid=cid, cf_fp=cf_fp, overwrite=self.overwrite) 
        
        out_fp = wrkr.finv_to_csv( vlay, felv=self.comboBox_SSelv.currentText(),
                                   logger=self.logger)

        #try the curves
        """user may think this button stores the curves also"""
        try:
            self.store_curves()
        except: pass
        #=======================================================================
        # wrap
        #=======================================================================
        log.push('inventory vector layer stored "\'%s\''%vlay.name())
        self.feedback.upd_prog(None) #set the progress bar back down to zero
        
        return 
    
    
    #===========================================================================
    # def convert_rfda(self): #Other.Rfda tab
    #     """
    #     TODO: move to drop down
    #     """
    #     log = self.logger.getChild('convert_rfda')
    #     tag = self.linEdit_ScenTag.text() #set the secnario tag from user provided name
    #     
    #     #======================================================================
    #     # collect from  ui
    #     #======================================================================
    #     rinv_vlay = self.mMapLayerComboBox_OthR_rinv.currentLayer()
    #     crv_fp = self.lineEdit_wd_OthRf_cv.text()
    #     bsmt_ht = self.lineEdit_OthRf_bht.text()
    #     #cid = self.mFieldComboBox_cid.currentField() #user selected field
    #     
    #     #crs = self.qproj.crs()
    #     out_dir = self.lineEdit_wd.text()
    #     
    #     try:
    #         bsmt_ht = float(bsmt_ht)
    #     except Exception as e:
    #         raise Error('failed to convert bsmt_ht to float w/ \n    %s'%e)
    #     
    #     
    #     #======================================================================
    #     # input checks
    #     #======================================================================
    #     
    #     wrkr = RFDAconv(logger=self.logger, out_dir=out_dir, tag=tag, bsmt_ht = bsmt_ht)
    #     #======================================================================
    #     # invnentory convert
    #     #======================================================================
    #     if isinstance(rinv_vlay, QgsVectorLayer):
    #         
    #         
    #         finv_vlay = wrkr.to_finv(rinv_vlay)
    #         
    #         self.qproj.addMapLayer(finv_vlay)
    #         log.info('added \'%s\' to canvas'%finv_vlay.name())
    #         
    #     #======================================================================
    #     # curve convert
    #     #======================================================================
    #     if os.path.exists(crv_fp):
    #         df_raw = pd.read_excel(crv_fp, header=None)
    #         
    #         df_d = wrkr.to_curveset(df_raw, logger=log)
    #         
    #         basefn = os.path.splitext(os.path.split(crv_fp)[1])[0]
    #         
    #         ofp = wrkr.output(df_d, basefn=basefn)
    #         
    #     else:
    #         log.info('no valid crv_fp provided')
    #         
    #     #======================================================================
    #     # wrap
    #     #======================================================================
    #     self.logger.push('finished')
    #         
    #===========================================================================

    def construct_finv(self): #add some fields to a finv like vectoralyer

        log = self.logger.getChild('construct_finv')
        tag = self.linEdit_ScenTag.text() #set the secnario tag from user provided name
        
        #=======================================================================
        # collect from UI
        #=======================================================================
        in_vlay = self.mMapLayerComboBox_inv_finv.currentLayer()
        out_dir = self.lineEdit_wd.text()
        nestID = int(self.spinBox_inv.value())
        new_data = dict()
        for dName, (lineEdit, reqType) in {
                                'scale':(self.lineEdit_inv_scale, float),
                                'elv':(self.lineEdit_inv_elv,float),
                                'tag':(self.lineEdit_inv_tag, str),
                                'cap':(self.lineEdit_inv_cap, float),            
                                }.items():
            
            vRaw = lineEdit.text()
            if vRaw == '':continue #blank.. ksipit
            new_data[dName] = reqType(vRaw)
            
        log.debug('collected %i:  \n%s'%(len(new_data), new_data))
        self.feedback.upd_prog(10)
        #=======================================================================
        # input checks
        #=======================================================================
        assert isinstance(in_vlay, QgsVectorLayer), 'no VectorLayer selected!'
        assert os.path.exists(out_dir)
        
        #=======================================================================
        # init
        #=======================================================================
        wrkr = Preparor(logger=self.logger,  out_dir=out_dir, tag=tag)
        
        
        #=======================================================================
        # aoi slice
        #=======================================================================
        in_vlay_aoi = self.slice_aoi(in_vlay)
        
                
        #=======================================================================
        # run converter
        #=======================================================================
        finv_vlay = wrkr.to_finv(in_vlay_aoi, newLayname = 'finv_%s'%in_vlay.name(),
                                 nestID=nestID, new_data=new_data)
        
        #=======================================================================
        # wrap
        #=======================================================================
        if self.checkBox_loadres.isChecked():
            self.qproj.addMapLayer(finv_vlay)
            self.comboBox_ivlay.setLayer(finv_vlay) #set this to the inventory selection
            log.info('added \'%s\' to canvas'%finv_vlay.name())
        else:
            raise Error('ensure load results is checked!')
        
        log.push('finished building finv from %s'%in_vlay.name())
        self.feedback.upd_prog(None) #set the progress bar back down to zero
        
    def run_rPrep(self):
        log = self.logger.getChild('run_rPrep')
        start = datetime.datetime.now()
        log.info('start \'run_rPrep\' at %s'%start)
        tag = self.linEdit_ScenTag.text() #set the secnario tag from user provided name
        
        
        
        #=======================================================================
        # assemble/prepare inputs
        #=======================================================================
        rlayRaw_l = list(self.ras_dict.values())
        out_dir = self.lineEdit_wd.text()
        
        
        #raster prep parameters
        aoi_vlay = self.comboBox_aoi.currentLayer()
        clip_rlays = self.checkBox_HS_clip.isChecked()
        allow_download = self.checkBox_HS_dpConv.isChecked()
        allow_rproj = self.checkBox_HS_rproj.isChecked()
        scaleFactor = self.doubleSpinBox_HS_sf.value()
        
        
        #=======================================================================
        # precheck
        #=======================================================================
        
        #check rastsers
        for rlay in rlayRaw_l:
            if not isinstance(rlay, QgsRasterLayer):
                raise Error('unexpected type on raster layer')
            
        
        if not os.path.exists(out_dir):
            raise Error('working directory does not exist:  %s'%out_dir)
        
        
        #raster prep checks
        assert isinstance(clip_rlays, bool)
        assert isinstance(allow_download, bool)
        assert isinstance(allow_rproj, bool)
        assert isinstance(scaleFactor, float)
        
        if clip_rlays:
            assert isinstance(aoi_vlay, QgsVectorLayer), 'for clip_rlays=True, must provide AOI'
            
        self.feedback.setProgress(10)
        #=======================================================================
        # execute
        #=======================================================================
        wrkr = Rsamp(logger=self.logger, 
                          tag = tag, #set by build_scenario() 
                          feedback = self.feedback, #let the instance build its own feedback worker
                          out_dir = out_dir
                          )
        

        #execute the tool
        rlay_l = wrkr.runPrep(rlayRaw_l, 
                        aoi_vlay = aoi_vlay,
                        clip_rlays = clip_rlays,
                        allow_download = allow_download,
                        allow_rproj = allow_rproj,
                        scaleFactor = scaleFactor,
                            )
        

        #=======================================================================
        # load results
        #=======================================================================
        
        self._HS_clearBox() #clear the raster selection box
        assert len(self.ras_dict)==0
            
            
        #=======================================================================
        # """adding the list of rasters to the canvas is crashing Qgis
        # spent an hour and couldnt resolve
        #=======================================================================

        if self.checkBox_loadres.isChecked():
            log.debug('loading %i prepped raster results'%len(rlay_l))

             

            self.qproj.addMapLayers(rlay_l)
            for rlay in rlay_l:
                assert isinstance(rlay, QgsRasterLayer)
                #self.qproj.addMapLayer(rlay)
                log.info('added \'%s\' to canvas'%rlay.name())
                 

                #update th erasterBox
                self.ras_dict.update( { rlay.name() : rlay} )
                self.listWidget_ras.addItem(str(rlay.name()))


                 
        else:
            log.warning('prepped rasters not loaded to canvas!')
             
 
             
        #=======================================================================
        # wrap
        #=======================================================================
         
        self.feedback.upd_prog(None) #set the progress bar back down to zero
 
        log.push('run_rPrep finished in %s'%(datetime.datetime.now() - start))
         
        return
        

    
    def run_rsamp(self): #execute raster sampler
        log = self.logger.getChild('run_rsamp')
        start = datetime.datetime.now()
        log.info('start \'run_rsamp\' at %s'%start)
        
        #=======================================================================
        # assemble/prepare inputs
        #=======================================================================
        finv_raw = self.comboBox_ivlay.currentLayer()
        rlay_l = list(self.ras_dict.values())
        

        cf_fp = self.get_cf_fp()
        out_dir = self.lineEdit_wd.text()
        tag = self.linEdit_ScenTag.text() #set the secnario tag from user provided name

        cid = self.mFieldComboBox_cid.currentField() #user selected field
        psmp_stat = self.comboBox_HS_stat.currentText()
        
        
        #inundation
        as_inun = self.checkBox_HS_in.isChecked()
        
        if as_inun:
            dthresh = self.mQgsDoubleSpinBox_HS.value()
            dtm_rlay=self.comboBox_HS_DTM.currentLayer()
            
            assert isinstance(dthresh, float), 'must provide a depth threshold'
            assert isinstance(dtm_rlay, QgsRasterLayer), 'must select a DTM layer'
            
        else:
            dthresh, dtm_rlay = None, None
            

        #=======================================================================
        # slice finv to aoi
        #=======================================================================
        finv = self.slice_aoi(finv_raw)

        #======================================================================
        # precheck
        #======================================================================
        if finv is None:
            raise Error('got nothing for finv')
        if not isinstance(finv, QgsVectorLayer):
            raise Error('did not get a vector layer for finv')
        
        gtype = QgsWkbTypes().displayString(finv.wkbType())
        
        for rlay in rlay_l:
            if not isinstance(rlay, QgsRasterLayer):
                raise Error('unexpected type on raster layer')
            assert rlay.crs()==self.qproj.crs(), 'layer CRS does not match project'
            
        if not os.path.exists(out_dir):
            raise Error('working directory does not exist:  %s'%out_dir)
        
        if cid is None or cid=='':
            raise Error('need to select a cid')
        
        if not cid in [field.name() for field in finv.fields()]:
            raise Error('requested cid field \'%s\' not found on the finv_raw'%cid)
        

        assert os.path.exists(cf_fp), 'bad control file specified'
        
        #geometry specific input checks
        if 'Polygon' in gtype or 'Line' in gtype:
            if not as_inun:
                assert psmp_stat in ('Mean','Median','Min','Max'), 'select a valid sample statistic'
            else:
                assert psmp_stat == '', 'expects no sample statistic for %Inundation'
        elif 'Point' in gtype:
            assert not as_inun, '%Inundation only valid for polygon type geometries'
        else:
            raise Error('unrecognized gtype: %s'%gtype)
        

        
        self.feedback.setProgress(10)
        #======================================================================
        # execute
        #======================================================================
        
        #build the sample
        wrkr = Rsamp(logger=self.logger, 
                          tag = tag, #set by build_scenario() 
                          feedback = self.feedback, #let the instance build its own feedback worker
                          cid=cid,
                          out_dir = out_dir
                          )
        

        #execute the tool
        res_vlay = wrkr.run(rlay_l, finv,
                            psmp_stat=psmp_stat,
                            as_inun=as_inun, dtm_rlay=dtm_rlay, dthresh=dthresh,
                            )
        
        self.feedback.setProgress(90)
        #check it
        wrkr.check()
        
        #save csv results to file
        wrkr.write_res(res_vlay, )
        
        #update ocntrol file
        wrkr.upd_cf(cf_fp)
        
        #======================================================================
        # post---------
        #======================================================================
        """
        the hazard sampler sets up a lot of the other tools
        """
        #======================================================================
        # add to map
        #======================================================================
        if self.checkBox_loadres.isChecked():
            self.qproj.addMapLayer(res_vlay)
            self.logger.info('added \'%s\' to canvas'%res_vlay.name())
            
        #======================================================================
        # update event names
        #======================================================================
        self.event_name_set = [lay.name() for lay in rlay_l]
        
        log.info('set %i event names: \n    %s'%(len(self.event_name_set), 
                                                         self.event_name_set))
        
        #======================================================================
        # populate Event Likelihoods table
        #======================================================================
        
        l = self.event_name_set
        for tbl in [self.fieldsTable_EL]:

            tbl.setRowCount(len(l)) #add this many rows
            
            for rindx, ename in enumerate(l):
                tbl.setItem(rindx, 0, QTableWidgetItem(ename))
            
        log.info('populated tables with event names')
        self.feedback.setProgress(95)
        #======================================================================
        # populate Conditional P
        #======================================================================
        """todo: some more intelligent populating"""
        #get the mlcb
        try:
            self._CP_clear() #clear everything
            
            #loop through each of the raster layers and collcet those with 'fail' in the name
            rFail_l = []
            for rlay in rlay_l:
                if 'fail' in rlay.name():
                    rFail_l.append(rlay)

            #loop through and re-key
            rFail_d = dict()
            for indxr, rlay in enumerate(rFail_l):
                rFail_d[list(self.ls_cb_d.keys())[indxr]] = rlay
                

            #loop through each combobox pair and assign a raster to it
            res_d = dict()
            for lsKey, (mlcb_h, mlcb_v) in self.ls_cb_d.items():
                if lsKey in rFail_d:
                    mlcb_h.setLayer(rFail_d[lsKey])
                    res_d[lsKey] = rFail_d[lsKey].name()

            #wrap
            log.info('populated %i Conditional P diaglogs'%len(res_d))
 
        except Exception as e:
            log.error('failed to populate lisamp fields w/\n    %s'%e)
            
        
        #======================================================================
        # wrap
        #======================================================================
        self.feedback.upd_prog(None) #set the progress bar back down to zero

        log.push('run_rsamp finished in %s'%(datetime.datetime.now() - start))
        
        return
    
    def run_dsamp(self): #sample dtm raster
        
        self.logger.info('user pressed \'pushButton_DTMsamp\'')

        
        #=======================================================================
        # assemble/prepare inputs
        #=======================================================================
        tag = self.linEdit_ScenTag.text() #set the secnario tag from user provided name
        finv_raw = self.comboBox_ivlay.currentLayer()
        rlay = self.comboBox_dtm.currentLayer()
        

        cf_fp = self.get_cf_fp()
        out_dir = self.lineEdit_wd.text()
        

        #update some parameters
        cid = self.mFieldComboBox_cid.currentField() #user selected field
        psmp_stat = self.comboBox_HS_stat.currentText()
        

        #======================================================================
        # aoi slice
        #======================================================================
        finv = self.slice_aoi(finv_raw)
        

        #======================================================================
        # precheck
        #======================================================================
                
        if finv is None:
            raise Error('got nothing for finv')
        if not isinstance(finv, QgsVectorLayer):
            raise Error('did not get a vector layer for finv')
        

        if not isinstance(rlay, QgsRasterLayer):
            raise Error('unexpected type on raster layer')
            
        if not os.path.exists(out_dir):
            raise Error('working directory does not exist:  %s'%out_dir)
        
        if cid is None or cid=='':
            raise Error('need to select a cid')
        
        if not cid in [field.name() for field in finv.fields()]:
            raise Error('requested cid field \'%s\' not found on the finv_raw'%cid)
            
        #check if we got a valid sample stat
        gtype = QgsWkbTypes().displayString(finv.wkbType())
        if not 'Point' in gtype:
            assert not psmp_stat=='', \
            'for %s type finvs must specifcy a sample statistic on the Hazard Sampler tab'%gtype
            """the module does a more robust check"""
        #======================================================================
        # execute
        #======================================================================

        #build the sample
        wrkr = Rsamp(logger=self.logger, 
                          tag=tag, #set by build_scenario() 
                          feedback = self.feedback, #needs to be connected to progress bar
                          cid=cid,
                          out_dir = out_dir, fname='gels', cf_fp=cf_fp
                          )
        
        

        
        res_vlay = wrkr.run([rlay], finv, psmp_stat=psmp_stat)
        
        #check it
        wrkr.dtm_check(res_vlay)
        
        #save csv results to file
        wrkr.write_res(res_vlay, out_dir = out_dir)
        
        #update ocntrol file
        wrkr.upd_cf_dtm()
        
        #======================================================================
        # add to map
        #======================================================================
        if self.checkBox_loadres.isChecked():
            self.qproj.addMapLayer(finv)
            self.logger.info('added \'%s\' to canvas'%finv.name())
            
        self.feedback.upd_prog(None) #set the progress bar back down to zero
        self.logger.push('dsamp finished')    
        
    def run_lisamp(self): #sample dtm raster
        
        self.logger.info('user pressed \'pushButton_DTMsamp\'')
        
        
        #=======================================================================
        # assemble/prepare inputs
        #=======================================================================
        tag = self.linEdit_ScenTag.text() #set the secnario tag from user provided name
        finv_raw = self.comboBox_ivlay.currentLayer()

        cf_fp = self.get_cf_fp()
        out_dir = self.lineEdit_wd.text()
        cid = self.mFieldComboBox_cid.currentField() #user selected field
        
        lfield = self.mFieldComboBox_LSfn.currentField()
        
        #collect lpols
        lpol_d = dict()
        for sname, (mlcb_haz, mlcb_lpol) in self.ls_cb_d.items():
            hlay = mlcb_haz.currentLayer()
            
            if not isinstance(hlay, QgsRasterLayer):
                continue
            
            lpol_vlay = mlcb_lpol.currentLayer()
            
            if not isinstance(lpol_vlay, QgsVectorLayer):
                raise Error('must provide a matching VectorLayer for set %s'%sname)

            lpol_d[hlay.name()] = lpol_vlay 
            
        #get relation type
        if self.radioButton_LS_mutEx.isChecked():
            event_rels='mutEx'
        elif self.radioButton_LS_indep.isChecked():
            event_rels='indep'
        else:
            raise Error('button logic fail')
            
        #======================================================================
        # aoi slice
        #======================================================================
        finv = self.slice_aoi(finv_raw)
        

        #======================================================================
        # precheck
        #======================================================================
                
        if finv is None:
            raise Error('got nothing for finv')
        if not isinstance(finv, QgsVectorLayer):
            raise Error('did not get a vector layer for finv')
                    
        if not os.path.exists(out_dir):
            raise Error('working directory does not exist:  %s'%out_dir)
        
        if cid is None or cid=='':
            raise Error('need to select a cid')
        
        if lfield is None or lfield=='':
            raise Error('must select a valid lfield')
        
        if not cid in [field.name() for field in finv.fields()]:
            raise Error('requested cid field \'%s\' not found on the finv_raw'%cid)
 
        #======================================================================
        # execute
        #======================================================================

        #build the sample
        wrkr = LikeSampler(logger=self.logger, 
                          tag=tag, #set by build_scenario() 
                          feedback = self.feedback, #needs to be connected to progress bar
                          cid=cid, out_dir=out_dir
                          )
        
        #connect the status bar
        #wrkr.feedback.progressChanged.connect(self.upd_prog)
        
        res_df = wrkr.run(finv, lpol_d,lfield=lfield, event_rels=event_rels)
        
        #check it
        wrkr.check()
        
        #save csv results to file
        wrkr.write_res(res_df, out_dir = out_dir)
        
        #update ocntrol file
        wrkr.upd_cf(cf_fp)
        
        #=======================================================================
        # summary plots
        #=======================================================================
        if self.checkBox_LS_hist.isChecked():
            fig = wrkr.plot_hist_all(res_df)
            wrkr.output_fig(fig)
            
        if self.checkBox_LS_box.isChecked():
            fig = wrkr.plot_box_all(res_df)
            wrkr.output_fig(fig)
        
        #======================================================================
        # add to map
        #======================================================================
        if self.checkBox_loadres.isChecked():
            res_vlay = wrkr.vectorize(res_df)
            self.qproj.addMapLayer(res_vlay)
            self.logger.info('added \'%s\' to canvas'%finv.name())
            
        self.feedback.upd_prog(None) #set the progress bar back down to zero
        self.logger.push('lisamp finished')    
        
        return
        
    def _pop_el_table(self): #developing the table widget
        

        l = ['e1', 'e2', 'e3']
        tbl = self.fieldsTable_EL
        tbl.setRowCount(len(l)) #add this many rows
        
        for rindx, ename in enumerate(l):
            tbl.setItem(rindx, 0, QTableWidgetItem(ename))
            
        self.logger.push('populated likelihoods table with event names')
            
            
    
    def set_event_vals(self): #saving the event likelihoods table to file

        log = self.logger.getChild('set_event_vals')
        #log.info('user pushed \'pushButton_ELstore\'')
        

        #======================================================================
        # collect variables
        #======================================================================
        tag = self.linEdit_ScenTag.text() #set the secnario tag from user provided name
        #get displayed control file path
        cf_fp = self.get_cf_fp()
        out_dir = self.lineEdit_wd.text()
        
        #likelihood paramter
        if self.radioButton_ELari.isChecked():
            event_probs = 'ari'
        else:
            event_probs = 'aep'
        self.logger.info('\'event_probs\' set to \'%s\''%event_probs)
        
        #event_rels
        if self.radioButton_EL_max.isChecked():
            event_rels = 'max'
        elif self.radioButton_EL_mutEx.isChecked():
            event_rels='mutEx'
        elif self.radioButton_EL_indep.isChecked():
            event_rels='indep'
        else:
            raise Error('event_rels radio logic fail')
        #======================================================================
        # collcet table data
        #======================================================================

        df = hlpr.plug.qtbl_get_df(self.fieldsTable_EL)
        
        self.logger.info('extracted data w/ %s \n%s'%(str(df.shape), df))
        
        # check it
        if df.iloc[:, 1].isna().any():
            raise Error('got %i nulls in the likelihood column'%df.iloc[:,1].isna().sum())
        
        miss_l = set(self.event_name_set).symmetric_difference(df.iloc[:,0].values)
        if len(miss_l)>0:
            raise Error('event name mismatch')
        
        
        #======================================================================
        # clean it
        #======================================================================
        aep_df = df.set_index(df.columns[0]).iloc[:,0].to_frame().T
        

        
        #======================================================================
        # #write to file
        #======================================================================
        ofn = os.path.join(self.lineEdit_wd.text(), 'evals_%i_%s.csv'%(len(aep_df.columns), tag))
        
        from hlpr.Q import Qcoms
        #build a shell worker for these taxks
        wrkr = Qcoms(logger=log, tag=tag, feedback=self.feedback, out_dir=out_dir)
        
        eaep_fp = wrkr.output_df(aep_df, ofn, 
                                  overwrite=self.overwrite, write_index=False)
        
        
        
        #======================================================================
        # update the control file
        #======================================================================
        wrkr.update_cf(
            {
                'parameters':({
                    'event_probs':event_probs, 'event_rels':event_rels},),
                'risk_fps':({'evals':eaep_fp}, 
                            '#evals file path set from %s.py at %s'%(
                                __name__, datetime.datetime.now().strftime('%Y-%m-%d %H.%M.%S')))
                          
             },
            cf_fp = cf_fp
            )
        
        
            
        self.logger.push('generated \'aeps\' and set \'event_probs\' to control file')
        
    def run_validate(self):
        """only validating the text in the control file for now (not the data objects)
        
        
        """

        log = self.logger.getChild('validator')
        log.info('user pressed \'pushButton_Validate\'')
        
        #======================================================================
        # collect form ui
        #======================================================================
        tag = self.linEdit_ScenTag.text() #set the secnario tag from user provided name
        cf_fp = self.get_cf_fp() #get the control file path
        
        
        #===================================================================
        # setup validation worker
        #===================================================================
        wrkr = Vali(cf_fp=cf_fp, logger=self.logger, out_dir=self.lineEdit_wd.text(), tag=tag)
        

        #======================================================================
        # assemble the validation parameters
        #======================================================================
        #import the class objects
        from model.dmg2 import Dmg2
        from model.risk2 import Risk2
        from model.risk1 import Risk1
        
        #populate all possible test parameters
        vpars_all_d = {
                    'risk1':(self.checkBox_Vr1, Risk1),
                    'dmg2':(self.checkBox_Vi2, Dmg2),
                    'risk2':(self.checkBox_Vr2, Risk2),
                    #'risk3':(self.checkBox_Vr3, None), 
                                           }
        
        #loop and collect based on check boxes
        vpars_d = dict()
        for vtag, (checkBox, modObj) in vpars_all_d.items():
            if not checkBox.isChecked(): continue #skip this one
            vpars_d[vtag] = modObj
        
        self.feedback.upd_prog(10)
        
        #======================================================================
        # loop through each possibility and validate
        #======================================================================
        res_d = dict()
        for vtag, modObj in vpars_d.items():
            log.debug('checking \"%s\''%vtag)
            #===================================================================
            # parameter value/type check
            #===================================================================
            errors = wrkr.cf_check(modObj)
            

            # #report on all the errors
            for indxr, msg in enumerate(errors):
                log.error('%s error %i: \n%s'%(vtag, indxr+1, msg))
                
            #===================================================================
            # update control file
            #===================================================================
            wrkr.cf_mark()
            
            self.feedback.upd_prog(80/len(vpars_d), method='append')
            
            #store
            if len(errors) == 0: 
                res_d[vtag] = True
            else:
                res_d[vtag] = False
            
        #=======================================================================
        # wrap
        #=======================================================================
        self.feedback.upd_prog(100)
        
        log.push('passed %i (of %i) validations. see log'%(
             np.array(list(res_d.values())).sum(), len(vpars_d)
             ))
        
        self.feedback.upd_prog(None)
        return
    
    #==========================================================================
    # HazardSampler Raster Box---------------
    #==========================================================================
    def _HS_comboAdd(self):
        x = [str(self.listWidget_ras.item(i).text()) for i in range(self.listWidget_ras.count())]
        self.ras_dict.update({ (self.comboBox_ras.currentText()) : (self.comboBox_ras.currentLayer()) })
        if (self.comboBox_ras.currentText()) not in x:
            self.listWidget_ras.addItem(self.comboBox_ras.currentText())
            self.ras_dict.update({ (self.comboBox_ras.currentText()) : (self.comboBox_ras.currentLayer()) })
        
    def _HS_clearBox(self):
        if len(self.ras_dict) > 0:
            self.listWidget_ras.clear()
            self.ras_dict = {}
    
    def _HS_remove(self):
        if (self.listWidget_ras.currentItem()) is not None:
            value = self.listWidget_ras.currentItem().text()
            item = self.listWidget_ras.takeItem(self.listWidget_ras.currentRow())
            item = None
            for k in list(self.ras_dict):
                if k == value:
                    self.ras_dict.pop(value)

    def _HS_addAll(self): #scan the canvas and intelligently add all the rasters
        layers = self.iface.mapCanvas().layers()
        #layers_vec = [layer for layer in layers if layer.type() == QgsMapLayer.VectorLayer]
        layers_ras = [layer for layer in layers if layer.type() == QgsMapLayer.RasterLayer]
        x = [str(self.listWidget_ras.item(i).text()) for i in range(self.listWidget_ras.count())]
        for layer in layers_ras:
            if (layer.name()) not in x:
                self.ras_dict.update( { layer.name() : layer} )
                self.listWidget_ras.addItem(str(layer.name()))
                
    def _CP_clear(self): #clear all the drop downs
        
        for sname, (mlcb_haz, mlcb_lpol) in self.ls_cb_d.items():
            mlcb_haz.setCurrentIndex(-1) #set selection to none
            mlcb_lpol.setCurrentIndex(-1) #set selection to none
                

    

            
            
    
     
            
                    
                
            
        

            
            
             
        
        
        
                
  
 

           
            
                    
            