# -*- coding: utf-8 -*-
"""
/***************************************************************************
 CanFlood_Model
                                 A QGIS plugin
 CanFlood model data
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2020-02-19
        git sha              : $Format:%H$
        copyright            : (C) 2020 by Tony De Crescenzo
        email                : tony.decrescenzo@ibigroup.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QObject
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QListWidget

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .canFlood_model_dialog import CanFlood_ModelDialog
import os.path
from qgis.core import QgsProject, Qgis, QgsVectorLayer, QgsRasterLayer, QgsFeatureRequest

# User defined imports
from qgis.core import *
from qgis.analysis import *
import qgis.utils
import processing
from processing.core.Processing import Processing
import sys, os, warnings, tempfile, logging, configparser

sys.path.append(r'C:\IBI\_QGIS_\QGIS 3.8\apps\Python37\Lib\site-packages')
#sys.path.append(os.path.join(sys.exec_prefix, 'Lib/site-packages'))
import numpy as np
import pandas as pd

file_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(file_dir)
#import model
#from risk import RiskModel

import canflood_model.model.risk
import canflood_model.model.dmg2
import prep.wsamp
#from canFlood_model import CanFlood_Model
from hp import Error
from shutil import copyfile


class CanFlood_Model:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.wd = None
        self.cf = None
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'CanFlood_Model_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&CanFlood_Model')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('CanFlood_Model', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/canFlood_model/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u''),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&CanFlood_Model'),
                action)
            self.iface.removeToolBarIcon(action)

    def select_output_folder(self):
        foldername = QFileDialog.getExistingDirectory(self.dlg, "Select Directory")
        print(foldername)
        if foldername is not "":
            self.dlg.lineEdit_wd_1.setText(os.path.normpath(foldername))
            self.dlg.lineEdit_wd_2.setText(os.path.normpath(foldername))
            self.dlg.lineEdit_cf_1.setText(os.path.normpath(os.path.join(foldername, 'CanFlood_control_01.txt')))
            self.dlg.lineEdit_cf_2.setText(os.path.normpath(os.path.join(foldername, 'CanFlood_control_01.txt')))
    
    def select_output_file(self):
        filename = QFileDialog.getOpenFileName(self.dlg, "Select File") 
        self.dlg.lineEdit_cf_1.setText(str(filename[0]))
        self.dlg.lineEdit_cf_2.setText(str(filename[0]))
    
    def run_risk(self):
        self.wd = self.dlg.lineEdit_wd_1.text()
        self.cf = self.dlg.lineEdit_cf_1.text()
        if (self.wd is None or self.cf is None):
            self.iface.messageBar().pushMessage("Input field missing",
                                                level=Qgis.Critical, duration=10)
        canflood_model.model.risk.main_run(self.wd, self.cf)
        self.iface.messageBar().pushMessage(
                "Success", "Process successful", level=Qgis.Success, duration=10)
    
    def run_dmg(self):
        self.wd = self.dlg.lineEdit_wd_1.text()
        self.cf = self.dlg.lineEdit_cf_1.text()
        if (self.wd is None or self.cf is None):
            self.iface.messageBar().pushMessage("Input field missing",
                                                level=Qgis.Critical, duration=10)
        canflood_model.model.dmg2.main_run(self.wd, self.cf)
        self.iface.messageBar().pushMessage(
                "Success", "Process successful", level=Qgis.Success, duration=10)

    def run(self):
        """Run method that performs all the real work"""

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start == True:
            self.first_start = False
            self.dlg = CanFlood_ModelDialog()
            self.dlg.pushButton_wd.clicked.connect(self.select_output_folder)
            self.dlg.pushButton_br_2.clicked.connect(self.select_output_file)
            self.dlg.pushButton_cf.clicked.connect(self.select_output_folder)
            self.dlg.pushButton_br_4.clicked.connect(self.select_output_file)
            self.dlg.pushButton_run_1.clicked.connect(self.run_risk)
            self.dlg.pushButton_run_2.clicked.connect(self.run_dmg)
            
            self.dlg.buttonBox.accepted.connect(self.dlg.accept)
            self.dlg.buttonBox.rejected.connect(self.dlg.reject)
            
        self.dlg.lineEdit_wd_1.clear()
        self.dlg.lineEdit_cf_1.clear()
        self.dlg.lineEdit_wd_2.clear()
        self.dlg.lineEdit_cf_2.clear()

        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result:
            # Do something useful here - delete the line containing pass and
            # substitute with your code.
            pass
