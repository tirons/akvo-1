#/usr/bin/env python 
import sys
#import readline
try: 
    from akvo.gui.main_ui import Ui_MainWindow
    uicerr = False
except: # Fallback 
    from akvo.gui.mainui import Ui_MainWindow
    uicerr = """
USING THE DEFAULT GUI FILES, AKVO MAY NOT WORK CORRECTLY!

See INSTALL.txt for details regarding GUI configuration 
if you are encountering problems.     

Clicking ignore will prevent this warning from showing 
each time you launch Akvo.                  
"""

import matplotlib
#matplotlib.use("QT4Agg")
from PyQt5 import QtCore, QtGui, QtWidgets

import numpy as np
import time
import os
from copy import deepcopy
from matplotlib.backends.backend_qt4 import NavigationToolbar2QT #as NavigationToolbar
import datetime, time


from akvo.tressel import mrsurvey 
import pkg_resources  # part of setuptools
version = pkg_resources.require("Akvo")[0].version

import yaml
# Writes out numpy arrays into Eigen vectors as serialized by Lemma
class MatrixXr(yaml.YAMLObject):
    yaml_tag = u'MatrixXr'
    def __init__(self, rows, cols, data):
        self.rows = rows
        self.cols = cols
        self.data = np.zeros((rows,cols))
    def __repr__(self):
        return "%s(rows=%r, cols=%r, data=%r)" % (self.__class__.__name__, self.rows, self.cols, self.data) 

class VectorXr(yaml.YAMLObject):
    yaml_tag = r'VectorXr'
    def __init__(self, array):
        self.size = np.shape(array)[0]
        self.data = array.tolist()
    def __repr__(self):
        # Converts to numpy array on import 
        return "np.array(%r)" % (self.data)

from collections import OrderedDict
#def represent_ordereddict(dumper, data):
#    print("representing IN DA HOUSE!!!!!!!!!!!!!!!!!!!!!")
#    value = []
#    for item_key, item_value in data.items():
#        node_key = dumper.represent_data(item_key)
#        node_value = dumper.represent_data(item_value)
#        value.append((node_key, node_value))
#    return yaml.nodes.MappingNode(u'tag:yaml.org,2002:map', value)
#yaml.add_representer(OrderedDict, represent_ordereddict)

def setup_yaml():
    """ https://stackoverflow.com/a/8661021 """
    represent_dict_order = lambda self, data:  self.represent_mapping('tag:yaml.org,2002:map', data.items())
    yaml.add_representer(OrderedDict, represent_dict_order)    
setup_yaml()

class AkvoYamlNode(yaml.YAMLObject):
    yaml_tag = u'AkvoData'
    def __init__(self):
        self.Akvo_VERSION = version
        self.Import = OrderedDict() # {}
        self.Processing = OrderedDict() 
    #def __init__(self, node):
    #    self.Akvo_VERSION = node["version"]
    #    self.Import = OrderedDict( node["Import"] ) # {}
    #    self.Processing = OrderedDict( node["Processing"] ) 
    def __repr__(self):
        return "%s(name=%r, Akvo_VESION=%r, Import=%r, Processing=%r)" % (
            #self.__class__.__name__, self.Akvo_VERSION, self.Import, self.Processing )
            self.__class__.__name__, self.Akvo_VERSION, self.Import, OrderedDict(self.Processing) ) 
            #self.__class__.__name__, self.Akvo_VERSION, self.Import, OrderedDict(self.Processing)) 
    
try:    
    import thread 
except ImportError:
    import _thread as thread  #Py3K compatibility 

class MyPopup(QtWidgets.QWidget):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.initUI()

    def initUI(self):
        lblName = QtWidgets.QLabel(self.name, self)

class ApplicationWindow(QtWidgets.QMainWindow):
    
    def __init__(self):
        
        QtWidgets.QMainWindow.__init__(self)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)       
 
        akvohome = os.path.expanduser("~") + "/.akvo"
        if not os.path.exists(akvohome):
            os.makedirs(akvohome)

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        if uicerr != False and not os.path.exists(akvohome+"/pyuic-warned"):
            reply = QtGui.QMessageBox.warning(self, 'Warning', uicerr, QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ignore) 
            if reply == 1024:      # "0x400" in hex
                pass
            elif reply == 1048576: # "0x100000" in hex
                warn = open( akvohome+"/pyuic-warned" ,"w" )
                warn.write("Gui files were not compiled locally using pyuic! Further warnings have been supressed")
                warn.close()
        self.RAWDataProc = None 

        self.YamlNode = AkvoYamlNode()           
 
        # initialise some stuff
        self.ui.lcdNumberTauPulse2.setEnabled(0)
        self.ui.lcdNumberTauPulse1.setEnabled(0)
        self.ui.lcdNumberNuTx.setEnabled(0)
        self.ui.lcdNumberTuneuF.setEnabled(0)
        self.ui.lcdNumberSampFreq.setEnabled(0)
        self.ui.lcdNumberTauDelay.setEnabled(0)
        self.ui.lcdNumberNQ.setEnabled(0)

        #MAK 20170126: add in a list to hold processing steps
        self.logText = []      

        ####################
        # Make connections #
        ####################

        # Menu items 
        self.ui.actionOpen_GMR.triggered.connect(self.openGMRRAWDataset)
        self.ui.actionSave_Preprocessed_Dataset.triggered.connect(self.SavePreprocess)
        self.ui.actionExport_Preprocessed_Dataset.triggered.connect(self.ExportPreprocess)
        self.ui.actionExport_Preprocessed_Dataset.setEnabled(False)
        self.ui.actionOpen_Preprocessed_Dataset.triggered.connect(self.OpenPreprocess)
        self.ui.actionAboutAkvo.triggered.connect(self.about)

        # Buttons
#         #QtCore.QObject.connect(self.ui.fullWorkflowPushButton, QtCore.SIGNAL("clicked()"), self.preprocess )
        self.ui.loadDataPushButton.pressed.connect(self.loadRAW) 
        self.ui.sumDataGO.pressed.connect( self.sumDataChans )
        self.ui.bandPassGO.pressed.connect( self.bandPassFilter )
        self.ui.filterDesignPushButton.pressed.connect( self.designFilter )
        self.ui.fdDesignPushButton.pressed.connect( self.designFDFilter )
        self.ui.downSampleGO.pressed.connect( self.downsample )
        self.ui.windowFilterGO.pressed.connect( self.windowFilter )
#        self.ui.despikeGO.pressed.connect( self.despikeFilter ) # use smart stack instead 
        self.ui.adaptGO.pressed.connect( self.adaptFilter )
        self.ui.adaptFDGO.pressed.connect( self.adaptFilterFD )
        self.ui.qdGO.pressed.connect( self.quadDet )
        self.ui.gateIntegrateGO.pressed.connect( self.gateIntegrate )
        self.ui.calcQGO.pressed.connect( self.calcQ )
        self.ui.FDSmartStackGO.pressed.connect( self.FDSmartStack )
        
        self.ui.plotQD.setEnabled(False) 
        self.ui.plotQD.pressed.connect( self.plotQD )
        
        self.ui.plotGI.setEnabled(False) 
        self.ui.plotGI.pressed.connect( self.plotGI )
 
        # Add progressbar to statusbar
        self.ui.barProgress =  QtWidgets.QProgressBar()
        self.ui.statusbar.addPermanentWidget(self.ui.barProgress, 0);
        self.ui.barProgress.setMaximumSize(100, 16777215);
        self.ui.barProgress.hide();        

        self.ui.mplwidget_navigator.setCanvas(self.ui.mplwidget)
        self.ui.mplwidget_navigator_2.setCanvas(self.ui.mplwidget_2)

        ##########################################################################
        # Loop Table 
        self.ui.loopTableWidget.setRowCount(80)       
        self.ui.loopTableWidget.setColumnCount(6)      
        self.ui.loopTableWidget.setHorizontalHeaderLabels( ["ch. tag", \
            "Northing [m]","Easting [m]","Height [m]", "Radius","Tx"] )
        
        for ir in range(0, self.ui.loopTableWidget.rowCount() ):
            for ic in range(1, self.ui.loopTableWidget.columnCount() ):
                pCell = QtWidgets.QTableWidgetItem()
                #pCell.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                pCell.setFlags(QtCore.Qt.NoItemFlags) # not selectable 
                pCell.setBackground( QtGui.QColor("lightgrey").lighter(110) )
                self.ui.loopTableWidget.setItem(ir, ic, pCell)

        self.ui.loopTableWidget.cellChanged.connect(self.loopCellChanged)
        #self.ui.loopTableWidget.cellPressed.connect(self.loopCellChanged) 
        self.ui.loopTableWidget.itemClicked.connect(self.loopCellClicked) 
        #self.ui.loopTableWidget.cellPressed.connect(self.loopCellClicked) 

        self.ui.loopTableWidget.setDragDropOverwriteMode(False)
        self.ui.loopTableWidget.setDragEnabled(False)
        #self.ui.loopTableWidget.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)

        self.loops = {}        

        ##########################################################################
        # layer Table 
        self.ui.layerTableWidget.setRowCount(80)       
        self.ui.layerTableWidget.setColumnCount(3)      
        self.ui.layerTableWidget.setHorizontalHeaderLabels( [r"top [m]", r"bottom [m]", "σ [ Ωm]" ] )

        # do we want this
        self.ui.layerTableWidget.setDragDropOverwriteMode(False)
        self.ui.layerTableWidget.setDragEnabled(True)
        self.ui.layerTableWidget.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        
        pCell = QtWidgets.QTableWidgetItem()
        pCell.setFlags(QtCore.Qt.NoItemFlags) # not selectable 
        pCell.setBackground( QtGui.QColor("lightgrey").lighter(110) )
        self.ui.layerTableWidget.setItem(0, 1, pCell)
        for ir in range(1, self.ui.layerTableWidget.rowCount() ):
            for ic in range(0, self.ui.layerTableWidget.columnCount() ):
                pCell = QtWidgets.QTableWidgetItem()
                #pCell.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                pCell.setFlags(QtCore.Qt.NoItemFlags) # not selectable 
                pCell.setBackground( QtGui.QColor("lightgrey").lighter(110) )
                self.ui.layerTableWidget.setItem(ir, ic, pCell)
        self.ui.layerTableWidget.cellChanged.connect(self.sigmaCellChanged) 


    def sigmaCellChanged(self):
        self.ui.layerTableWidget.cellChanged.disconnect(self.sigmaCellChanged) 
        # TODO consider building the model whenever this is called. Would be nice to be able to 
        # do that. Would require instead dist of T2 I guess.
        jj = self.ui.layerTableWidget.currentColumn()
        ii = self.ui.layerTableWidget.currentRow()
        val = "class 'NoneType'>" 
        try:
            val = eval (str( self.ui.layerTableWidget.item(ii, jj).text() ))
        except:
            #if jj != 0:
            #    Error = QtWidgets.QMessageBox()
            #    Error.setWindowTitle("Error!")
            #    Error.setText("Non-numeric value encountered")
            self.ui.layerTableWidget.cellChanged.connect(self.sigmaCellChanged) 
            return
        if jj == 1:
            #item.setFlags(QtCore.Qt.ItemIsEnabled)
            pCell = self.ui.layerTableWidget.item(ii, jj)
            pCell.setBackground( QtGui.QColor("white"))
            
            pCell = self.ui.layerTableWidget.item(ii+1, jj-1)
            if str(type(pCell)) == "<class 'NoneType'>":  
                pCell = QtWidgets.QTableWidgetItem()
                pCell.setFlags(QtCore.Qt.ItemIsEnabled)
                self.ui.layerTableWidget.setItem(ii+1, jj-1, pCell)
            if ii == 0:
                pCell.setText(str(val))
                #pCell3 = self.ui.layerTableWidget.item(ii+1, jj)
                #print ("setting", ii, jj, type(pCell3))
                #print ( "setting", ii, jj, type(pCell3))
                #pCell3.setFlags( QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled )
                #pCell3.setFlags( QtCore.Qt.ItemIsEditable  )
            elif ii > 0:
                val2 = eval (str( self.ui.layerTableWidget.item(ii-1, jj).text() ))
                #print ("val2", val2, val, type(val))
                #if str(type(pCell)) == "<class 'NoneType'>":  
                if type(val) == str or val > val2:
                    pCell.setText(str(val))
                else:
                    Error = QtWidgets.QMessageBox()
                    Error.setWindowTitle("Error!")
                    Error.setText("Non-increasing layer detected")
                    Error.setDetailedText("Each layer interface must be below the one above it.")
                    Error.exec_()
            
                    pCell2 = self.ui.layerTableWidget.item(ii, jj)
                    pCell2.setText(str(""))
                    self.ui.layerTableWidget.cellChanged.connect(self.sigmaCellChanged) 
                    return

            # enable next layer
            pCell4 = self.ui.layerTableWidget.item(ii+1, jj)
            pCell4.setBackground( QtGui.QColor("lightblue") ) #.lighter(110))
            pCell4.setFlags( QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled )
            
            pCell5 = self.ui.layerTableWidget.item(ii+1, jj+1)
            pCell5.setBackground( QtGui.QColor("white"))
            pCell5.setFlags( QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled )
            
        print("ii", ii, "jj", jj)
        if ii == 0 and jj == 0:
            pCell = self.ui.layerTableWidget.item(0, 1)
            pCell.setBackground( QtGui.QColor("lightblue")) #.lighter(110) )
            pCell.setFlags( QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled )

        self.ui.layerTableWidget.cellChanged.connect(self.sigmaCellChanged) 

    def loopCellClicked(self, item):
        print("checkstate", item.checkState(),item.row())

        #self.ui.loopTableWidget.itemClicked.disconnect(self.loopCellClicked)
        jj = item.column() 
        ii = item.row()
        tp = type(self.ui.loopTableWidget.item(ii, 0))
        print("tp", tp, ii, jj)
        if str(tp) == "<class 'NoneType'>": 
            return 
        #print("Clicked", ii, jj)
        if jj == 5 and self.ui.loopTableWidget.item(ii, 0).text() in self.loops.keys():
            #print("jj=5")
            self.loops[ self.ui.loopTableWidget.item(ii, 0).text() ]["Tx"] = self.ui.loopTableWidget.item(ii, 5).checkState()
            # update surrogates  
            print("updating surrogates")
            for point in self.loops[ self.ui.loopTableWidget.item(ii, 0).text() ]["points"][1:]:
                pCell = self.ui.loopTableWidget.item(point, 5)
                if self.ui.loopTableWidget.item(ii, 5).checkState():
                    pCell.setCheckState(QtCore.Qt.Checked);
                else:
                    pCell.setCheckState(QtCore.Qt.Unchecked);
 
            #print( "loops",  self.loops[ self.ui.loopTableWidget.item(ii, 0).text() ]["Tx"]) 
         
        #self.ui.loopTableWidget.itemClicked.connect(self.loopCellClicked) 

    def loopCellChanged(self):
        self.ui.loopTableWidget.cellChanged.disconnect(self.loopCellChanged) 
        
        jj = self.ui.loopTableWidget.currentColumn()
        ii = self.ui.loopTableWidget.currentRow()

        if jj == 0 and len( self.ui.loopTableWidget.item(ii, jj).text().strip()) == 0:
            for jjj in range(jj+1,jj+6): 
                pCell = self.ui.loopTableWidget.item(ii, jjj)
                pCell.setBackground( QtGui.QColor("white") )
                pCell.setFlags( QtCore.Qt.NoItemFlags | QtCore.Qt.ItemIsUserCheckable   ) # not selectable 
        elif jj == 0 and len( self.ui.loopTableWidget.item(ii, jj).text().strip() ): # ch. tag modified
            for jjj in range(jj+1,jj+5): 
                pCell = self.ui.loopTableWidget.item(ii, jjj)
                pCell.setFlags( QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled )
                pCell.setBackground( QtGui.QColor("lightblue") )
            if self.ui.loopTableWidget.item(ii, jj).text() not in self.loops.keys():
                # This is a new loop ID 
                self.loops[ self.ui.loopTableWidget.item(ii, jj).text() ] = {}
                self.loops[ self.ui.loopTableWidget.item(ii, jj).text() ]["Tx"] = self.ui.loopTableWidget.item(ii, 5).checkState()
                self.loops[ self.ui.loopTableWidget.item(ii, jj).text() ]["points"] = [ii] 
                # Transmitter cell 
                pCell = self.ui.loopTableWidget.item(ii, jj+5)
                pCell.setCheckState(QtCore.Qt.Unchecked)
                pCell.setFlags( QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled  )
                pCell.setBackground( QtGui.QColor("lightblue") ) 
            else:
                # This is an existing loop ID 
                self.loops[ self.ui.loopTableWidget.item(ii, jj).text() ]["points"].append( ii ) 
                pCell = self.ui.loopTableWidget.item(ii, jj+5)
                pCell.setFlags(QtCore.Qt.NoItemFlags) # not selectable 
                if self.loops[ self.ui.loopTableWidget.item(ii, 0).text() ]["Tx"]:
                    pCell.setCheckState(QtCore.Qt.Checked);
                else:
                    pCell.setCheckState(QtCore.Qt.Unchecked);
                #pCell.setFlags( )
                pCell.setBackground( QtGui.QColor("lightblue") )


            
 
        self.plotLoops()
        self.ui.loopTableWidget.cellChanged.connect(self.loopCellChanged) 


    def plotLoops(self):
               
        #self.ui.mplwidget_3.fig.clear() 
        self.ui.mplwidget_3.ax1.clear() 
        self.ui.mplwidget_3.ax2.clear()
        nor = dict()
        eas = dict()
        dep = dict() 
        for ii in range( self.ui.loopTableWidget.rowCount() ):
            for jj in range( self.ui.loopTableWidget.columnCount() ):
                tp = type(self.ui.loopTableWidget.item(ii, jj))
                if str(tp) == "<class 'NoneType'>":  
                    pass 
                elif not len(self.ui.loopTableWidget.item(ii, jj).text()): 
                    pass
                else:
                    if jj == 0: 
                        idx = self.ui.loopTableWidget.item(ii, 0).text()
                        if idx not in nor.keys():
                            nor[idx] = list()
                            eas[idx] = list()
                            dep[idx] = list()
                    if jj == 1: 
                        nor[idx].append( eval(self.ui.loopTableWidget.item(ii, 1).text()) )
                    elif jj == 2:
                        eas[idx].append( eval(self.ui.loopTableWidget.item(ii, 2).text()) )
                    elif jj == 3:
                        dep[idx].append( eval(self.ui.loopTableWidget.item(ii, 3).text()) )

        for ii in nor.keys():            
            try:    
                self.ui.mplwidget_3.ax1.plot(  np.array(nor[ii]), np.array(eas[ii])  )
            except:
                pass 
        #self.ui.mplwidget_3.figure.axes().set
        plt.gca().set_aspect('equal') #, adjustable='box')
        self.ui.mplwidget_3.draw()

    def about(self):
        # TODO proper popup with info
        #self.w = MyPopup("""About Akvo \n
        #    Akvo is an open source project developed primarily by Trevor Irons. 
        #""")
        #self.w.setGeometry(100, 100, 400, 200)
        #self.w.show()

        # Just a splash screen for now
        logo = pkg_resources.resource_filename(__name__, 'akvo_about.png')
        pixmap = QtGui.QPixmap(logo)
        self.splash = QtWidgets.QSplashScreen(pixmap, QtCore.Qt.WindowStaysOnTopHint)
        self.splash.show()

    def connectGMRDataProcessor(self):
        
        self.RAWDataProc = mrsurvey.GMRDataProcessor()
        self.RAWDataProc.progressTrigger.connect(self.updateProgressBar)
        self.RAWDataProc.enableDSPTrigger.connect(self.enableDSP)
        self.RAWDataProc.doneTrigger.connect(self.doneStatus)
        self.RAWDataProc.updateProcTrigger.connect(self.updateProc)

    def openGMRRAWDataset(self):
        """ Opens a GMR header file
        """
        try:
            with open('.gmr.last.path') as f: 
                fpath = f.readline()  
                pass
        except IOError as e:
            fpath = '.'

        self.headerstr = QtWidgets.QFileDialog.getOpenFileName(self, 'Open File', fpath)[0] # arg2 = File Type 'All Files (*)'
        self.ui.headerFileTextBrowser.clear()
        self.ui.headerFileTextBrowser.append(self.headerstr)
        
        if len(self.headerstr) == 0:
            return 
        
        # clear the processing log
        self.ui.logTextBrowser.clear()
        self.logText = []   #MAK 20170126

        path,filen=os.path.split(str(self.headerstr))

        f = open('.gmr.last.path', 'w')
        f.write( str(self.headerstr) ) # prompt last file      

        self.connectGMRDataProcessor()
        self.RAWDataProc.readHeaderFile(str(self.headerstr))

        # If we got this far, enable all the widgets
        self.ui.lcdNumberTauPulse1.setEnabled(True)
        self.ui.lcdNumberNuTx.setEnabled(True)
        self.ui.lcdNumberTuneuF.setEnabled(True)
        self.ui.lcdNumberSampFreq.setEnabled(True)
        self.ui.lcdNumberNQ.setEnabled(True)

        self.ui.headerFileBox.setEnabled(True)
        self.ui.inputRAWParametersBox.setEnabled(True)
        self.ui.loadDataPushButton.setEnabled(True)
         
        # make plots as you import the dataset
        self.ui.plotImportCheckBox.setEnabled(True)
        self.ui.plotImportCheckBox.setChecked(True)
 
        # Update info from the header into the GUI
        self.ui.pulseTypeTextBrowser.clear()
        self.ui.pulseTypeTextBrowser.append(self.RAWDataProc.pulseType)
        self.ui.lcdNumberNuTx.display(self.RAWDataProc.transFreq)
        self.ui.lcdNumberTauPulse1.display(1e3*self.RAWDataProc.pulseLength[0])
        self.ui.lcdNumberTuneuF.display(self.RAWDataProc.TuneCapacitance)
        self.ui.lcdNumberSampFreq.display(self.RAWDataProc.samp)
        self.ui.lcdNumberNQ.display(self.RAWDataProc.nPulseMoments)
        self.ui.DeadTimeSpinBox.setValue(1e3*self.RAWDataProc.deadTime)
        self.ui.CentralVSpinBox.setValue( self.RAWDataProc.transFreq )
       
        if self.RAWDataProc.pulseType != "FID":
            self.ui.lcdNumberTauPulse2.setEnabled(1)
            self.ui.lcdNumberTauPulse2.display(1e3*self.RAWDataProc.pulseLength[1])
            self.ui.lcdNumberTauDelay.setEnabled(1)
            self.ui.lcdNumberTauDelay.display(1e3*self.RAWDataProc.interpulseDelay)

        self.ui.FIDProcComboBox.clear() 
        if self.RAWDataProc.pulseType == "4PhaseT1":
            self.ui.FIDProcComboBox.insertItem(0, "Pulse 1") 
            self.ui.FIDProcComboBox.insertItem(1, "Pulse 2") 
            self.ui.FIDProcComboBox.insertItem(2, "Both")    
            self.ui.FIDProcComboBox.setCurrentIndex (1)
        elif self.RAWDataProc.pulseType == "FID":
            self.ui.FIDProcComboBox.insertItem(0, "Pulse 1") 
            self.ui.FIDProcComboBox.setCurrentIndex (0)
    
    def ExportPreprocess(self):
        """ This method export to YAML 
        """
        try:
            with open('.akvo.last.yaml.path') as f: 
                fpath = f.readline()  
                pass
        except IOError as e:
            fpath = '.'
        
        fdir = os.path.dirname(fpath)
        # Pickle the preprocessed data dictionary 
        SaveStr = QtWidgets.QFileDialog.getSaveFileName(self, "Save as", fdir, r"Processed data (*.yaml)")[0]
        
        spath,filen=os.path.split(str(SaveStr))
        f = open('.akvo.last.yaml.path', 'w')
        f.write( str(spath) ) # prompt last file      

        INFO = {}
        INFO["headerstr"] = str(self.headerstr)
        INFO["pulseType"] = self.RAWDataProc.pulseType
        INFO["transFreq"] = self.RAWDataProc.transFreq.tolist()
        INFO["pulseLength"] = self.RAWDataProc.pulseLength.tolist()
        INFO["TuneCapacitance"] = self.RAWDataProc.TuneCapacitance.tolist()
        #INFO["samp"] = self.RAWDataProc.samp
        INFO["nPulseMoments"] = self.RAWDataProc.nPulseMoments
        #INFO["deadTime"] = self.RAWDataProc.deadTime
        INFO["processed"] = "Akvo v. 1.0, on " + time.strftime("%d/%m/%Y")
        # Pulse current info
        ip = 0
        INFO["Pulses"] = {}
        for pulse in self.RAWDataProc.DATADICT["PULSES"]:
            qq = []
            qv = []
            for ipm in range(self.RAWDataProc.DATADICT["nPulseMoments"]):     
                #for istack in self.RAWDataProc.DATADICT["stacks"]:
                #    print ("stack q", self.RAWDataProc.DATADICT[pulse]["Q"][ipm,istack-1])
                qq.append(np.mean(    self.RAWDataProc.DATADICT[pulse]["Q"][ipm,:]) )
                qv.append(np.std(     self.RAWDataProc.DATADICT[pulse]["Q"][ipm,:]/self.RAWDataProc.pulseLength[ip] ))
            INFO["Pulses"][pulse] = {}
            INFO["Pulses"][pulse]["units"] = "A"
            INFO["Pulses"][pulse]["current"] = VectorXr(np.array(qq)/self.RAWDataProc.pulseLength[ip])
            INFO["Pulses"][pulse]["variance"] = VectorXr(np.array(qv))
            ip += 1

        # Data
        if self.RAWDataProc.gated == True:
            INFO["Gated"] = {}
            INFO["Gated"]["abscissa units"] = "ms"
            INFO["Gated"]["data units"] = "nT"
            for pulse in self.RAWDataProc.DATADICT["PULSES"]:
                INFO["Gated"][pulse] = {} 
                INFO["Gated"][pulse]["abscissa"] = VectorXr( self.RAWDataProc.GATEDABSCISSA ) 
                INFO["Gated"][pulse]["windows"] = VectorXr( self.RAWDataProc.GATEDWINDOW ) 
                for ichan in self.RAWDataProc.DATADICT[pulse]["chan"]:
                    INFO["Gated"][pulse]["Chan. " + str(ichan)] = {} 
                    INFO["Gated"][pulse]["Chan. " + str(ichan)]["STD"] =  VectorXr( np.std(self.RAWDataProc.GATED[ichan]["NR"], axis=0) )
                    for ipm in range(self.RAWDataProc.DATADICT["nPulseMoments"]):     
                        INFO["Gated"][pulse]["Chan. " + str(ichan)]["Q-"+str(ipm) + " CA"] = VectorXr(self.RAWDataProc.GATED[ichan]["CA"][ipm])   
                        INFO["Gated"][pulse]["Chan. " + str(ichan)]["Q-"+str(ipm) + " RE"] = VectorXr(self.RAWDataProc.GATED[ichan]["RE"][ipm])   
                        INFO["Gated"][pulse]["Chan. " + str(ichan)]["Q-"+str(ipm) + " IM"] = VectorXr(self.RAWDataProc.GATED[ichan]["IM"][ipm])   
                        #INFO["Gated"][pulse]["Chan. " + str(ichan)]["Q-"+str(ipm) + " IP"] = VectorXr(self.RAWDataProc.GATED[ichan]["IP"][ipm])   
                        #INFO["Gated"][pulse]["Chan. " + str(ichan)]["Q-"+str(ipm) + " NR"] = VectorXr(self.RAWDataProc.GATED[ichan]["NR"][ipm])   
                        #INFO["Gated"][pulse]["Chan. " + str(ichan)]["Q-"+str(ipm) + " STD" ] = VectorXr(self.RAWDataProc.GATED[ichan]["SIGMA"][ipm])   
            
            # we have gated data 
            # Window edges  
            # Window centres 

        with open(SaveStr, 'w') as outfile:
            #for line in self.logText:
            #    outfile.write(line+"\n")
            yaml.dump(self.YamlNode, outfile)   
            yaml.dump(INFO, outfile, default_flow_style=False)   
 
    def SavePreprocess(self):
     
        #if "Saved" not in self.YamlNode.Processing.keys():
        #    self.YamlNode.Processing["Saved"] = []
        #self.YamlNode.Processing["Saved"].append(datetime.datetime.now().isoformat()) 
        #self.Log()
 
        import pickle, os 
        try:
            with open('.akvo.last.path') as f: 
                fpath = f.readline()  
                pass
        except IOError as e:
            fpath = '.'
        
        fdir = os.path.dirname(fpath)
        # Pickle the preprocessed data dictionary 
        SaveStr = QtWidgets.QFileDialog.getSaveFileName(self, "Save as", fdir, r"Pickle (*.dmp)")
        print(SaveStr)
 
        spath,filen=os.path.split(str(SaveStr[0]))
        f = open('.akvo.last.path', 'w')
        f.write( str(spath) ) # prompt last file      
        save = open(SaveStr[0], 'wb')

        # Add some extra info 
        INFO = {}
        INFO["pulseType"] = self.RAWDataProc.pulseType
        INFO["transFreq"] = self.RAWDataProc.transFreq
        INFO["pulseLength"] = self.RAWDataProc.pulseLength
        INFO["TuneCapacitance"] = self.RAWDataProc.TuneCapacitance
        INFO["samp"] = self.RAWDataProc.samp
        INFO["nPulseMoments"] = self.RAWDataProc.nPulseMoments
        INFO["deadTime"] = self.RAWDataProc.deadTime
        INFO["transFreq"] = self.RAWDataProc.transFreq
        INFO["headerstr"] = str(self.headerstr)
        INFO["log"] = yaml.dump( self.YamlNode )  #self.logText  #MAK 20170127
    
        self.RAWDataProc.DATADICT["INFO"] = INFO 

        pickle.dump(self.RAWDataProc.DATADICT, save)
        save.close()

    # Export XML file suitable for USGS ScienceBase Data Release
    def ExportXML(self):
        """ This is a filler function for use by USGS collaborators 
        """
        return 42

    def OpenPreprocess(self):
        import pickle

        try:
            with open('.akvo.last.path') as f: 
                fpath = f.readline()  
                pass
        except IOError as e:
            fpath = '.'
        
        #filename = QtWidgets.QFileDialog.getOpenFileName(self, 'Open File', '.')
        fpath = QtWidgets.QFileDialog.getOpenFileName(self, 'Open preprocessed file', fpath, r"Pickle Files (*.dmp)")[0]
        
        f = open('.akvo.last.path', 'w')
        f.write( str(fpath) ) # prompt last file      

        self.ui.logTextBrowser.clear()
        self.logText = []

        if len(fpath) == 0:
            return 
        
        pfile = open(fpath,'rb')        

        unpickle = pickle.Unpickler(pfile)
        self.connectGMRDataProcessor()
        self.RAWDataProc.DATADICT = unpickle.load()
        
        self.RAWDataProc.readHeaderFile(self.RAWDataProc.DATADICT["INFO"]["headerstr"])
        self.headerstr = self.RAWDataProc.DATADICT["INFO"]["headerstr"]
 
        self.RAWDataProc.pulseType = self.RAWDataProc.DATADICT["INFO"]["pulseType"] 
        self.RAWDataProc.transFreq = self.RAWDataProc.DATADICT["INFO"]["transFreq"] 
        self.RAWDataProc.pulseLength = self.RAWDataProc.DATADICT["INFO"]["pulseLength"] 
        self.RAWDataProc.TuneCapacitance = self.RAWDataProc.DATADICT["INFO"]["TuneCapacitance"] 
        self.RAWDataProc.samp = self.RAWDataProc.DATADICT["INFO"]["samp"] 
        self.RAWDataProc.nPulseMoments = self.RAWDataProc.DATADICT["INFO"]["nPulseMoments"] 
        self.RAWDataProc.deadTime = self.RAWDataProc.DATADICT["INFO"]["deadTime"] 
        self.RAWDataProc.transFreq = self.RAWDataProc.DATADICT["INFO"]["transFreq"]
        self.RAWDataProc.dt = 1./self.RAWDataProc.samp 

        self.dataChan = self.RAWDataProc.DATADICT[ self.RAWDataProc.DATADICT["PULSES"][0] ]["chan"]
        # Keep backwards compatibility with prior saved pickles???
        #self.ui.logTextBrowser.clear() 
            #self.ui.logTextBrowser.append( yaml.dump(self.YamlNode)) #, default_flow_style=False)  )
            #for a in self.logText:
            #    self.ui.logTextBrowser.append(str(a))
            #self.ui.logTextBrowser
            #self.ui.logTextBrowser.clear()
            #print ( self.RAWDataProc.DATADICT["INFO"]["log"] )
        
        self.logText = self.RAWDataProc.DATADICT["INFO"]["log"] # YAML 

        self.YamlNode = AkvoYamlNode( )  #self.logText )
        self.YamlNode.Akvo_VERSION = (yaml.load( self.logText )).Akvo_VERSION
        self.YamlNode.Import = OrderedDict((yaml.load( self.logText )).Import)
        self.YamlNode.Processing = OrderedDict((yaml.load( self.logText )).Processing)
        #self.YamlNode.Akvo_VERSION =  2 #yaml.load( self.logText )["Akvo_VERSION"] #, Loader=yaml.RoundTripLoader) # offending line! 
        #self.YamlNode = AkvoYamlNode( self.logText ) # offending line! 
        #print("import type", type( self.YamlNode.Processing ))
        self.Log() 
            #self.ui.logTextBrowser.append( yaml.dump(self.YamlNode)) #, default_flow_style=False)  )
        #except KeyError:
        #    pass
       
        # Remove "Saved" and "Loaded" from processing flow 
        #if "Loaded" not in self.YamlNode.Processing.keys():
        #    self.YamlNode.Processing["Loaded"] = []
        #self.YamlNode.Processing["Loaded"].append(datetime.datetime.now().isoformat()) 
        #self.Log()
 
        # If we got this far, enable all the widgets
        self.ui.lcdNumberTauPulse1.setEnabled(True)
        self.ui.lcdNumberNuTx.setEnabled(True)
        self.ui.lcdNumberTuneuF.setEnabled(True)
        self.ui.lcdNumberSampFreq.setEnabled(True)
        self.ui.lcdNumberNQ.setEnabled(True)

        self.ui.headerFileBox.setEnabled(True)
        self.ui.inputRAWParametersBox.setEnabled(True)
        self.ui.loadDataPushButton.setEnabled(True)
        
        # make plots as you import the dataset
        self.ui.plotImportCheckBox.setEnabled(True)
        self.ui.plotImportCheckBox.setChecked(True)
 
        # Update info from the header into the GUI
        self.ui.pulseTypeTextBrowser.clear()
        self.ui.pulseTypeTextBrowser.append(self.RAWDataProc.pulseType)
        self.ui.lcdNumberNuTx.display(self.RAWDataProc.transFreq)
        self.ui.lcdNumberTauPulse1.display(1e3*self.RAWDataProc.pulseLength[0])
        self.ui.lcdNumberTuneuF.display(self.RAWDataProc.TuneCapacitance)
        self.ui.lcdNumberSampFreq.display(self.RAWDataProc.samp)
        self.ui.lcdNumberNQ.display(self.RAWDataProc.nPulseMoments)
        self.ui.DeadTimeSpinBox.setValue(1e3*self.RAWDataProc.deadTime)
        self.ui.CentralVSpinBox.setValue( self.RAWDataProc.transFreq )
       
        if self.RAWDataProc.pulseType != "FID":
            self.ui.lcdNumberTauPulse2.setEnabled(1)
            self.ui.lcdNumberTauPulse2.display(1e3*self.RAWDataProc.pulseLength[1])
            self.ui.lcdNumberTauDelay.setEnabled(1)
            self.ui.lcdNumberTauDelay.display(1e3*self.RAWDataProc.interpulseDelay)

        self.ui.FIDProcComboBox.clear() 
        if self.RAWDataProc.pulseType == "4PhaseT1":
            self.ui.FIDProcComboBox.insertItem(0, "Pulse 1") #, const QVariant & userData = QVariant() )
            self.ui.FIDProcComboBox.insertItem(1, "Pulse 2") #, const QVariant & userData = QVariant() )
            self.ui.FIDProcComboBox.insertItem(2, "Both")    #, const QVariant & userData = QVariant() )
            if len( self.RAWDataProc.DATADICT["PULSES"]) == 2:
                self.ui.FIDProcComboBox.setCurrentIndex (2)
            elif  self.RAWDataProc.DATADICT["PULSES"][0] == "Pulse 1":
                self.ui.FIDProcComboBox.setCurrentIndex (0)
            else:
                self.ui.FIDProcComboBox.setCurrentIndex (1)

        elif self.RAWDataProc.pulseType == "FID":
            self.ui.FIDProcComboBox.insertItem(0, "Pulse 1") #, const QVariant & userData = QVariant() )
            self.ui.FIDProcComboBox.setCurrentIndex (0)

#         QtCore.QObject.connect(self.RAWDataProc, QtCore.SIGNAL("updateProgress(int)"), self.updateProgressBar)
#         QtCore.QObject.connect(self.RAWDataProc, QtCore.SIGNAL("enableDSP()"), self.enableDSP)
#         QtCore.QObject.connect(self.RAWDataProc, QtCore.SIGNAL("doneStatus()"), self.doneStatus)
        self.RAWDataProc.progressTrigger.connect(self.updateProgressBar)
        self.RAWDataProc.enableDSPTrigger.connect(self.enableDSP)
        self.RAWDataProc.doneTrigger.connect(self.doneStatus)
        
        self.enableAll()
 
    def loadRAW(self):

        #################################################
        # Check to make sure we are ready to process

        # Header
        if self.RAWDataProc == None:
            err_msg = "You need to load a header first."
            reply = QtGui.QMessageBox.critical(self, 'Error', 
                err_msg) #, QtGui.QMessageBox.Yes, QtGui.QMessageBox.No)
            return
        
        # Stacks 
        try:
            self.procStacks = np.array(eval(str("np.r_["+self.ui.stacksLineEdit.text())+"]"))
        except:
            err_msg = "You need to set your stacks correctly.\n" + \
                      "This should be a Python Numpy interpretable list\n" + \
                      "of stack indices. For example 1:24 or 1:4,8:24"
            QtGui.QMessageBox.critical(self, 'Error', err_msg) 
            return

        # Data Channels
        #Chan = np.arange(0,9,1)
        try:
            self.dataChan = np.array(eval(str("np.r_["+self.ui.dataChanLineEdit.text())+"]"))
        except:
            #QMessageBox messageBox;
            #messageBox.critical(0,"Error","An error has occured !");
            #messageBox.setFixedSize(500,200);
            #quit_msg = "Are you sure you want to exit the program?"
            #reply = QtGui.QMessageBox.question(self, 'Message', 
            #    quit_msg, QtGui.QMessageBox.Yes, QtGui.QMessageBox.No)
            err_msg = "You need to set your data channels correctly.\n" + \
                      "This should be a Python Numpy interpretable list\n" + \
                      "of indices. For example 1 or 1:3 or 1:3 5\n\n" + \
                      "valid GMR data channels fall between 1 and 8. Note that\n" +\
                      "1:3 is not inclusive of 3 and is the same as 1,2 "
            reply = QtGui.QMessageBox.critical(self, 'Error', 
                err_msg) #, QtGui.QMessageBox.Yes, QtGui.QMessageBox.No)
            return
        #############################
        # Reference Channels
        # TODO make sure no overlap between data and ref channels
        self.refChan = np.array( () )
        if str(self.ui.refChanLineEdit.text()): # != "none":
            try:
                self.refChan = np.array(eval(str("np.r_["+self.ui.refChanLineEdit.text())+"]"))
            except:
                err_msg = "You need to set your reference channels correctly.\n" + \
                      "This should be a Python Numpy interpretable list\n" + \
                      "of indices. For example 1 or 1:3 or 1:3 5\n\n" + \
                      "valid GMR data channels fall between 1 and 8. Note that\n" +\
                      "1:3 is not inclusive of 3 and is the same as 1,2 "
                QtGui.QMessageBox.critical(self, 'Error', err_msg) 
                return

        #####################################################
        # Load data

        self.lock("loading RAW GMR dataset")

        if self.RAWDataProc.pulseType == "FID":
            self.procThread = thread.start_new_thread(self.RAWDataProc.loadFIDData, \
                (str(self.headerstr), self.procStacks, self.dataChan, self.refChan, \
                 str(self.ui.FIDProcComboBox.currentText()), self.ui.mplwidget, \
                1e-3 * self.ui.DeadTimeSpinBox.value( ), self.ui.plotImportCheckBox.isChecked() )) #, self)) 
            
        elif self.RAWDataProc.pulseType == "4PhaseT1":
            self.procThread = thread.start_new_thread(self.RAWDataProc.load4PhaseT1Data, \
                (str(self.headerstr), self.procStacks, self.dataChan, self.refChan, \
                 str(self.ui.FIDProcComboBox.currentText()), self.ui.mplwidget, \
                1e-3 * self.ui.DeadTimeSpinBox.value( ), self.ui.plotImportCheckBox.isChecked() )) #, self)) 

        self.YamlNode.Import["GMR Header"] = self.headerstr
        self.YamlNode.Import["opened"] = datetime.datetime.now().isoformat() 
        self.YamlNode.Import["pulse Type"] = str(self.RAWDataProc.pulseType) 
        self.YamlNode.Import["stacks"] = self.procStacks.tolist() 
        self.YamlNode.Import["data channels"] = self.dataChan.tolist()  
        self.YamlNode.Import["reference channels"] = self.refChan.tolist() 
        self.YamlNode.Import["pulse records"] = str(self.ui.FIDProcComboBox.currentText())  
        self.YamlNode.Import["instrument dead time"] = (1e-3 * self.ui.DeadTimeSpinBox.value( ))    

        self.Log (  )     

        # should be already done
#        QtCore.QObject.connect(self.RAWDataProc, QtCore.SIGNAL("updateProgress(int)"), self.updateProgressBar)
#        QtCore.QObject.connect(self.RAWDataProc, QtCore.SIGNAL("enableDSP()"), self.enableDSP)
#        QtCore.QObject.connect(self.RAWDataProc, QtCore.SIGNAL("doneStatus()"), self.doneStatus)

        self.ui.ProcessedBox.setEnabled(True)
        self.ui.lcdNumberFID1Length.setEnabled(1)
        self.ui.lcdNumberFID2Length.setEnabled(1)
        self.ui.lcdNumberResampFreq.setEnabled(1)
        self.ui.lcdTotalDeadTime.setEnabled(1)

        self.ui.lcdTotalDeadTime.display( self.ui.DeadTimeSpinBox.value( ) )
        
        #self.ui.lcdNumberFID1Length.display(0)
        #self.ui.lcdNumberFID2Length.display(0)
        #self.ui.lcdNumberResampFreq.display( self.RAWDataProc.samp )
 
        self.mpl_toolbar = NavigationToolbar2QT(self.ui.mplwidget, self.ui.mplwidget)
        self.ui.mplwidget.draw()

    def Log(self):
        #for line in yaml.dump(self.YamlNode, default_flow_style=False):
        #for line in nlogText: 
        #    self.ui.logTextBrowser.append( line )
        #    self.logText.append( line ) 
        self.ui.logTextBrowser.clear()
        self.ui.logTextBrowser.append( yaml.dump(self.YamlNode)) #, default_flow_style=False)  )

    def disable(self):
        self.ui.BandPassBox.setEnabled(False)
        self.ui.downSampleGroupBox.setEnabled(False)
        self.ui.windowFilterGroupBox.setEnabled(False)
#        self.ui.despikeGroupBox.setEnabled(False)
        self.ui.adaptBox.setEnabled(False)
        self.ui.adaptFDBox.setEnabled(False)
        self.ui.qCalcGroupBox.setEnabled(False)    
        self.ui.FDSmartStackGroupBox.setEnabled(False)    
        self.ui.sumDataBox.setEnabled(False)    
        self.ui.qdGroupBox.setEnabled(False)
        self.ui.gateBox.setEnabled(False)

    def enableAll(self):
        self.enableDSP()
        self.enableQC()

    def enableDSP(self):

        # Bandpass filter
        self.ui.BandPassBox.setEnabled(True)
        self.ui.BandPassBox.setChecked(True)
        self.ui.bandPassGO.setEnabled(False) # need to design first
        self.ui.plotBP.setEnabled(True)
        self.ui.plotBP.setChecked(True)

        # downsample 
        self.ui.downSampleGroupBox.setEnabled(True)
        self.ui.downSampleGroupBox.setChecked(True)
       
        # window
        self.ui.windowFilterGroupBox.setEnabled(True)
        self.ui.windowFilterGroupBox.setChecked(True)
 
        # Despike
#        self.ui.despikeGroupBox.setEnabled(True)
#        self.ui.despikeGroupBox.setChecked(False)

        # Adaptive filtering 
        self.ui.adaptBox.setEnabled(True)
        self.ui.adaptBox.setChecked(True)
        
        # FD Adaptive filtering 
        self.ui.adaptFDBox.setEnabled(True)
        self.ui.adaptFDBox.setChecked(True)

        # sum group box
        try:
            if len(self.dataChan) > 1:
                self.ui.sumDataBox.setEnabled(True)
                self.ui.sumDataBox.setChecked(True)
        except:
            pass

        # Quadrature Detect
        self.ui.qdGroupBox.setEnabled(True)
        self.ui.qdGroupBox.setChecked(True)

        self.enableQC() 

    def enableQC(self):
        
        # Q calc
        self.ui.qCalcGroupBox.setEnabled(True)    
        self.ui.qCalcGroupBox.setChecked(True)    

        # FD SmartStack
        self.ui.FDSmartStackGroupBox.setEnabled(True)    
        self.ui.FDSmartStackGroupBox.setChecked(True)    
        
        # Quadrature detect
        try:
            for pulse in self.RAWDataProc.DATADICT["PULSES"]: 
                np.shape(self.RAWDataProc.DATADICT[pulse]["Q"])
            self.RAWDataProc.DATADICT["stack"] 
            self.ui.qdGroupBox.setEnabled(True)   
            self.ui.qdGroupBox.setChecked(True)    
        except:
            self.ui.qdGroupBox.setEnabled(False)    
            self.ui.qdGroupBox.setChecked(False)    
        
        # Gating
        try:
            self.RAWDataProc.DATADICT["CA"] 
            self.ui.gateBox.setEnabled(True)
            self.ui.gateBox.setChecked(True)
        except:
            self.ui.gateBox.setEnabled(False)
            self.ui.gateBox.setChecked(False)

    def despikeFilter(self):
        self.lock("despike filter")
        thread.start_new_thread(self.RAWDataProc.despike, \
                (self.ui.windowSpinBox.value(), \
                self.ui.thresholdSpinBox.value(), \
                str(self.ui.replComboBox.currentText()), \
                self.ui.rollOnSpinBox.value(), \
                self.ui.despikeInterpWinSpinBox.value(),
                self.ui.mplwidget))

    def calcQ(self):
        if "Calc Q" not in self.YamlNode.Processing.keys():
            print("In CalcQ", yaml.dump(self.YamlNode.Processing)  )
            self.YamlNode.Processing["Calc Q"] = True
            print( yaml.dump(self.YamlNode.Processing)  )
            self.Log()
        else:
            err_msg = "Q values have already been calculated"
            reply =QtWidgets.QMessageBox.critical(self, 'Error', 
                err_msg) 
            return 

        self.lock("pulse moment calculation")
        thread.start_new_thread(self.RAWDataProc.effectivePulseMoment, \
                (self.ui.CentralVSpinBox.value(), \
                self.ui.mplwidget_2))

    def FDSmartStack(self):

        if "TD stack" not in self.YamlNode.Processing.keys():
            self.YamlNode.Processing["TD stack"] = {}
            self.YamlNode.Processing["TD stack"]["outlier"] = str( self.ui.outlierTestCB.currentText() ) 
            self.YamlNode.Processing["TD stack"]["cutoff"] = str( self.ui.MADCutoff.value() )
            self.Log()
        else:
            err_msg = "TD noise cancellation has already been applied!"
            reply =QtWidgets.QMessageBox.critical(self, 'Error', 
                err_msg) 
            return 
        
        self.lock("time-domain smart stack")
        thread.start_new_thread(self.RAWDataProc.TDSmartStack, \
                (str(self.ui.outlierTestCB.currentText()), \
                self.ui.MADCutoff.value(),
                self.ui.mplwidget_2))

    def adaptFilter(self):

        if "TD noise cancellation" not in self.YamlNode.Processing.keys():
            self.YamlNode.Processing["TD noise cancellation"] = {}
            self.YamlNode.Processing["TD noise cancellation"]["n_Taps"] = str(self.ui.MTapsSpinBox.value())
            self.YamlNode.Processing["TD noise cancellation"]["lambda"] = str(self.ui.adaptLambdaSpinBox.value())
            self.YamlNode.Processing["TD noise cancellation"]["truncate"] = str(self.ui.adaptTruncateSpinBox.value())
            self.YamlNode.Processing["TD noise cancellation"]["mu"] = str(self.ui.adaptMuSpinBox.value()) 
            self.YamlNode.Processing["TD noise cancellation"]["PCA"] = str(self.ui.PCAComboBox.currentText())
            self.Log()
        else:
            err_msg = "TD noise cancellation has already been applied!"
            reply =QtWidgets.QMessageBox.critical(self, 'Error', 
                err_msg) 
            return 
        
        self.lock("TD noise cancellation filter")
        thread.start_new_thread(self.RAWDataProc.adaptiveFilter, \
                (self.ui.MTapsSpinBox.value(), \
                self.ui.adaptLambdaSpinBox.value(), \
                self.ui.adaptTruncateSpinBox.value(), \
                self.ui.adaptMuSpinBox.value(), \
                str(self.ui.PCAComboBox.currentText()), \
                self.ui.mplwidget))

    def sumDataChans(self): 

        if "Data sum" not in self.YamlNode.Processing.keys():
            self.YamlNode.Processing["Data sum"] = True
            self.Log()
        else:
            err_msg = "Data channels have already been summed!"
            reply =QtWidgets.QMessageBox.critical(self, 'Error', 
                err_msg) 
            return 

        self.lock("Summing data channels")
        self.dataChan = [self.dataChan[0]]
        self.ui.sumDataBox.setEnabled(False)    
        thread.start_new_thread( self.RAWDataProc.sumData, ( self.ui.mplwidget, 7 ) )
 
    def adaptFilterFD(self):
        self.lock("FD noise cancellation filter")
        thread.start_new_thread(self.RAWDataProc.adaptiveFilterFD, \
                (str(self.ui.windowTypeComboBox.currentText()), \
                self.ui.windowBandwidthSpinBox.value(), \
                self.ui.CentralVSpinBox.value(), \
                self.ui.mplwidget))

    def bandPassFilter(self):
        if "Bandpass filter" not in self.YamlNode.Processing.keys():
            self.YamlNode.Processing["Bandpass filter"] = {}
            self.YamlNode.Processing["Bandpass filter"]["central_nu"] = str(self.ui.CentralVSpinBox.value())
            self.YamlNode.Processing["Bandpass filter"]["passband"] = str(self.ui.passBandSpinBox.value())
            self.YamlNode.Processing["Bandpass filter"]["stopband"] = str(self.ui.stopBandSpinBox.value()) 
            self.YamlNode.Processing["Bandpass filter"]["gpass"] = str(self.ui.gpassSpinBox.value())
            self.YamlNode.Processing["Bandpass filter"]["gstop"] = str(self.ui.gstopSpinBox.value())
            self.YamlNode.Processing["Bandpass filter"]["type"] = str(self.ui.fTypeComboBox.currentText())
            self.Log()
        else:
            err_msg = "Bandpass filter has already been applied!"
            reply =QtWidgets.QMessageBox.critical(self, 'Error', 
                err_msg) 
            return 
        self.lock("bandpass filter")        
        nv = self.ui.lcdTotalDeadTime.value( ) + self.ui.lcdNumberFTauDead.value()
        self.ui.lcdTotalDeadTime.display( nv )
        thread.start_new_thread(self.RAWDataProc.bandpassFilter, \
                (self.ui.mplwidget, 0, self.ui.plotBP.isChecked() ))

    def downsample(self):
        self.lock("resampling")
        
        if "Resample" not in self.YamlNode.Processing.keys():
            self.YamlNode.Processing["Resample"] = {}
            self.YamlNode.Processing["Resample"]["downsample factor"] = [] 
            self.YamlNode.Processing["Resample"]["truncate length"] = []  
        self.YamlNode.Processing["Resample"]["downsample factor"].append( str(self.ui.downSampleSpinBox.value() ) )
        self.YamlNode.Processing["Resample"]["truncate length"].append(  str( self.ui.truncateSpinBox.value() ) )
        self.Log( )
        
        thread.start_new_thread(self.RAWDataProc.downsample, \
                (self.ui.truncateSpinBox.value(), \
                self.ui.downSampleSpinBox.value(),
                self.ui.mplwidget))

    def quadDet(self):

        if "Quadrature detection" not in self.YamlNode.Processing.keys():
            self.YamlNode.Processing["Quadrature detection"] = {}
            self.YamlNode.Processing["Quadrature detection"]["trim"] = str( self.ui.trimSpin.value() )
            self.Log()
        else:
            err_msg = "Quadrature detection has already been done!"
            reply =QtWidgets.QMessageBox.critical(self, 'Error', 
                err_msg) 
            return 

        self.lock("quadrature detection")
        thread.start_new_thread(self.RAWDataProc.quadDet, \
                (self.ui.trimSpin.value(), int(self.ui.QDType.currentIndex()), self.ui.mplwidget_2))

        self.ui.plotQD.setEnabled(True)
    
    def plotQD(self):
        self.lock("plot QD")

        thread.start_new_thread(self.RAWDataProc.plotQuadDet, \
                (self.ui.trimSpin.value(), int(self.ui.QDType.currentIndex()), self.ui.mplwidget_2))


    def gateIntegrate(self):
        
        if "Gate integrate" not in self.YamlNode.Processing.keys():
            self.YamlNode.Processing["Gate integrate"] = {}
        self.YamlNode.Processing["Gate integrate"]["gpd"] = str(self.ui.GPDspinBox.value( ) )
        self.Log()
 
        self.lock("gate integration")
        thread.start_new_thread(self.RAWDataProc.gateIntegrate, \
                (self.ui.GPDspinBox.value(), self.ui.trimSpin.value(), self.ui.mplwidget_2))
        
        self.ui.actionExport_Preprocessed_Dataset.setEnabled(True)
        self.ui.plotGI.setEnabled(True)

    def plotGI(self):
        self.lock("plot gate integrate")
        thread.start_new_thread(self.RAWDataProc.plotGateIntegrate, \
                (self.ui.GPDspinBox.value(), self.ui.trimSpin.value(), \
                self.ui.QDType_2.currentIndex(),  self.ui.mplwidget_2))
 
    def designFilter(self):
        [bord, fe] = self.RAWDataProc.designFilter( \
                self.ui.CentralVSpinBox.value(), \
                self.ui.passBandSpinBox.value(), \
                self.ui.stopBandSpinBox.value(), \
                self.ui.gpassSpinBox.value(), \
                self.ui.gstopSpinBox.value(), \
                str(self.ui.fTypeComboBox.currentText()),
                self.ui.mplwidget)
        self.ui.lcdNumberFilterOrder.display(bord)
        self.ui.lcdNumberFTauDead.display(1e3*fe)
        #self.ui.lcdNumberFilterOrder.display(bord)
        self.ui.bandPassGO.setEnabled(1)
        #   self.ui.lcdNumberTauPulse2.display(1e3*self.RAWDataProc.pulseLength[1])
    
    def windowFilter(self):
        
        if "Window filter" not in self.YamlNode.Processing.keys():
            self.YamlNode.Processing["Window filter"] = {}
            self.YamlNode.Processing["Window filter"]["type"] = str(self.ui.windowTypeComboBox.currentText()) 
            self.YamlNode.Processing["Window filter"]["width"] = str(self.ui.windowBandwidthSpinBox.value()) 
            self.YamlNode.Processing["Window filter"]["centre"] = str(self.ui.CentralVSpinBox.value() )
            self.Log()
        else:
            err_msg = "FD window has already been applied!"
            reply =QtWidgets.QMessageBox.critical(self, 'Error', 
                err_msg) 
            return 

        self.lock("window filter")
        thread.start_new_thread(self.RAWDataProc.windowFilter, \
                (str(self.ui.windowTypeComboBox.currentText()), \
                self.ui.windowBandwidthSpinBox.value(), \
                self.ui.CentralVSpinBox.value(), \
                self.ui.mplwidget))

    def designFDFilter(self):
#         thread.start_new_thread(self.RAWDataProc.computeWindow, ( \
#                 "Pulse 1",
#                 self.ui.windowBandwidthSpinBox.value(), \
#                 self.ui.CentralVSpinBox.value(), \
#                 str(self.ui.windowTypeComboBox.currentText()), \
#                 self.ui.mplwidget ))
        a,b,c,d,dead = self.RAWDataProc.computeWindow( \
                "Pulse 1",
                self.ui.windowBandwidthSpinBox.value(), \
                self.ui.CentralVSpinBox.value(), \
                str(self.ui.windowTypeComboBox.currentText()), \
                self.ui.mplwidget )

        self.ui.lcdWinDead.display(dead)

    def updateProgressBar(self, percent):
        self.ui.barProgress.setValue(percent)

    def updateProc(self):
        if   str(self.ui.FIDProcComboBox.currentText()) == "Pulse 1":
            self.ui.lcdNumberFID1Length.display(self.RAWDataProc.DATADICT["Pulse 1"]["TIMES"][-1]- self.RAWDataProc.DATADICT["Pulse 1"]["TIMES"][0])
        elif str(self.ui.FIDProcComboBox.currentText()) == "Pulse 2":
            self.ui.lcdNumberFID2Length.display(self.RAWDataProc.DATADICT["Pulse 2"]["TIMES"][-1]- self.RAWDataProc.DATADICT["Pulse 2"]["TIMES"][0])
        else:
            self.ui.lcdNumberFID1Length.display(self.RAWDataProc.DATADICT["Pulse 1"]["TIMES"][-1]- self.RAWDataProc.DATADICT["Pulse 1"]["TIMES"][0])
            self.ui.lcdNumberFID2Length.display(self.RAWDataProc.DATADICT["Pulse 2"]["TIMES"][-1]- self.RAWDataProc.DATADICT["Pulse 2"]["TIMES"][0])
        self.ui.lcdNumberResampFreq.display( self.RAWDataProc.samp )
    
    def doneStatus(self): # unlocks GUI
        self.ui.statusbar.clearMessage ( )
        self.ui.barProgress.hide()
        self.updateProc()       
        self.enableAll()

    def lock(self, string):
        self.ui.statusbar.showMessage ( string )
        self.ui.barProgress.show()
        self.ui.barProgress.setValue(0)
        self.disable()

    def unlock(self):
        self.ui.statusbar.clearMessage ( )
        self.ui.barProgress.hide()
        self.enableAll()

    def done(self):
        self.ui.statusbar.showMessage ( "" )


################################################################
################################################################

# Boiler plate main function
import pkg_resources
from pkg_resources import resource_string
import matplotlib.image as mpimg 
import matplotlib.pyplot as plt 


def main():
    
    # splash screen logo 
    logo = pkg_resources.resource_filename(__name__, 'akvo.png')
    logo2 = pkg_resources.resource_filename(__name__, 'akvo2.png')
    qApp = QtWidgets.QApplication(sys.argv)

    ssplash = False
    if ssplash:
        pixmap = QtGui.QPixmap(logo)
        splash = QtWidgets.QSplashScreen(pixmap, QtCore.Qt.WindowStaysOnTopHint)
        splash.show()
    
    aw = ApplicationWindow()

    img=mpimg.imread(logo)
    for ax in [ aw.ui.mplwidget ]: 
        ax.fig.clear()
        subplot = ax.fig.add_subplot(111)
        ax.fig.patch.set_facecolor( None )
        ax.fig.patch.set_alpha( .0 )
        subplot.imshow(img) 
        subplot.xaxis.set_major_locator(plt.NullLocator()) 
        subplot.yaxis.set_major_locator(plt.NullLocator()) 
        ax.draw()

    if ssplash:
        splash.showMessage("Loading modules")
        splash.finish(aw)
        #time.sleep(1) 

    aw.setWindowTitle("Akvo v"+str(version)) 
    aw.show()
    qApp.setWindowIcon(QtGui.QIcon(logo2))
    sys.exit(qApp.exec_())

if __name__ == "__main__":
    main()
