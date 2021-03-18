import SimpleITK as sitk
import sitkUtils
import os
import getpass
import unittest
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import logging
import numpy as np
import string
from pathlib import Path
from datetime import date

#
# LandmarkFlow
#

class CleftLandmarkFlow(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Cleft Image Annotation"
        self.parent.categories = ["SCH CranIAL"]
        self.parent.dependencies = []
        self.parent.contributors = [
            "Murat Maga (UW), Sara Rolfe (UW), Ezgi Mercan (SCH)"]  # replace with "Firstname Lastname (Organization)"
        self.parent.helpText = """
This module imports an image database (csv file) from which individual images can be loaded into 3D Slicer for landmarking.
<ol> 
<li>Navigate to project folder, and then load the .csv file in by clicking the <b>Load Table</b></li>
<li>Click on the filename from the table and hit <b>Import Image</b></li>
<li>Use the fiducials markup to digitize the landmarks in the sequence agreed.</li> 
<li>Once digitization is done, hit the <b>Export Landmarks</b> button to save the 
landmarks into the correct output folder automatically. This will remove the image from the table view.</li>
<li>You can now start the next unprocessed image.</li>
</ol> 
"""
        self.parent.acknowledgementText = """
Modified by Ezgi Mercan for internal Seattle Children's Hospital Craniofacial Image Analysis Lab use. 
The original module was developed by Sara Rolfe and Murat Maga, for the NSF HDR  grant, "Biology Guided Neural Networks" (Award Number: 1939505).
"""

    #


# LandmarkFlowWidget
#

class CleftLandmarkFlowWidget(ScriptedLoadableModuleWidget):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def assignLayoutDescription(self, table):
        customLayout = """
    <layout type=\"horizontal\" split=\"true\" >
        <item splitSize=\"800\">
            <view class=\"vtkMRMLViewNode\" singletontag=\"1\">
            <property name=\"viewlabel\" action=\"default\">1</property>
            </view>
        </item>
        <item splitSize=\"200\">
        <view class=\"vtkMRMLTableViewNode\" singletontag=\"TableView1\">
        <property name=\"viewlabel\" action=\"default\">T</property>
        </view>
        </item>
    </layout>
    """

        customLayoutId = 702

        layoutManager = slicer.app.layoutManager()
        layoutManager.layoutLogic().GetLayoutNode().AddLayoutDescription(customLayoutId, customLayout)

        # Switch to the new custom layout
        layoutManager.setLayout(customLayoutId)

        # Select table in viewer
        slicer.app.applicationLogic().GetSelectionNode().SetReferenceActiveTableID(table.GetID())
        slicer.app.applicationLogic().PropagateTableSelection()

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)

        # Instantiate and connect widgets ...
        #
        # Input/Export Area
        #
        IOCollapsibleButton = ctk.ctkCollapsibleButton()
        IOCollapsibleButton.text = "Input and Export"
        self.layout.addWidget(IOCollapsibleButton)

        # Layout within the dummy collapsible button
        # IOFormLayout = qt.QFormLayout(IOCollapsibleButton)
        IOFormLayout = qt.QGridLayout(IOCollapsibleButton)
        #
        # Table volume selector
        #
        tableSelectorLable = qt.QLabel("Project File: ")
        self.tableSelector = ctk.ctkPathLineEdit()
        self.tableSelector.nameFilters = ["*.txt"]
        self.tableSelector.setToolTip("Select project file")
        # IOFormLayout.addRow("Input table: ", self.tableSelector)

        self.selectorButton = qt.QPushButton("Load")
        self.selectorButton.toolTip = "Load the project file"
        self.selectorButton.enabled = False
        # IOFormLayout.addRow(self.selectorButton)
        IOFormLayout.addWidget(tableSelectorLable, 1, 1)
        IOFormLayout.addWidget(self.tableSelector, 1, 2)
        IOFormLayout.addWidget(self.selectorButton, 1, 3)

        #
        # Import Volume Button
        #
        # TODO When to activate/deactivate this button
        self.importVolumeButton = qt.QPushButton("Import image")
        self.importVolumeButton.toolTip = "Import the image selected in the table"
        self.importVolumeButton.enabled = False
        IOFormLayout.addWidget(self.importVolumeButton, 5, 1, 1, 3)

        #
        # Annotations area
        #
        annotationsButton = ctk.ctkCollapsibleButton()
        annotationsButton.text = "Annotations"
        self.layout.addWidget(annotationsButton)
        annotationsLayout = qt.QGridLayout(annotationsButton)

        # Set up tabs to split workflow
        tabsWidget = qt.QTabWidget()
        landmarkTab = qt.QWidget()
        landmarkTabLayout = qt.QFormLayout(landmarkTab)

        tabsWidget.addTab(landmarkTab, "Landmark")
        annotationsLayout.addWidget(tabsWidget)

        exports = ctk.ctkCollapsibleButton()
        exports.text = "Export/Skip"
        landmarkTabLayout.addWidget(exports)
        exportsLayout = qt.QGridLayout(exports)

        #
        # Markups Incomplete Button
        #
        self.markIncompleteButton = qt.QPushButton("Incomplete")
        self.markIncompleteButton.toolTip = "Click if the sample cannot be landmarked - no landmark file will be saved."
        self.markIncompleteButton.enabled = False
        exportsLayout.addWidget(self.markIncompleteButton, 1, 1)

        #
        # Export Landmarks Button
        #
        self.exportLandmarksButton = qt.QPushButton("Export")
        self.exportLandmarksButton.toolTip = "Export landmarks placed on the selected image"
        self.exportLandmarksButton.enabled = False
        exportsLayout.addWidget(self.exportLandmarksButton, 1, 2)

        #
        # Skip Button
        #
        self.skipButton = qt.QPushButton("Clear Scene /Skip")
        self.skipButton.toolTip = "Clean scene and skip"
        self.skipButton.enabled = False
        exportsLayout.addWidget(self.skipButton, 1, 3)

        # connections
        self.tableSelector.connect("validInputChanged(bool)", self.onSelectTablePath)
        self.selectorButton.connect('clicked(bool)', self.onLoadTable)
        self.importVolumeButton.connect('clicked(bool)', self.onImportMesh)
        self.exportLandmarksButton.connect('clicked(bool)', self.onExportLandmarks)
        self.markIncompleteButton.connect('clicked(bool)', self.onMarkIncomplete)
        self.skipButton.connect('clicked(bool)', self.onSkip)

        # Add vertical spacer
        self.layout.addStretch(1)

    def onMarkIncomplete(self):
        # TODO ask for a reason, maybe a text box?
        self.updateTableAndGUI(False)

    def onSkip(self):
        # TODO ask for a reason, maybe a text box?
        self.cleanup()

    def updateStatus(self, index, status_string):
        # refresh table from file, update the status column, and save
        name = self.fileTable.GetName()
        slicer.mrmlScene.RemoveNode(self.fileTable)
        self.fileTable = slicer.util.loadNodeFromFile(self.tablepath, 'TableFile')
        self.fileTable.SetLocked(True)
        self.fileTable.SetName(name)
        logic = CleftLandmarkFlowLogic()
        # logic.hideCompletedSamples(self.fileTable)
        statusColumn = self.fileTable.GetTable().GetColumnByName('Status')
        statusColumn.SetValue(index - 1, status_string)

        # set the user to the lab based on an environment variable
        userColumn = self.fileTable.GetTable().GetColumnByName('User')
        userColumn.SetValue(index - 1, getpass.getuser())

        dateColumn = self.fileTable.GetTable().GetColumnByName('Date')
        dateColumn.SetValue(index - 1, str(date.today()))

        self.fileTable.GetTable().Modified()  # update table view
        slicer.util.saveNode(self.fileTable, self.tablepath)

    def onSelectTablePath(self):
        if (self.tableSelector.currentPath):
            self.selectorButton.enabled = True
        else:
            self.selectorButton.enabled = False

    def onLoadTable(self):
        if hasattr(self, 'fileTable'):
            slicer.mrmlScene.RemoveNode(self.fileTable)

        with open(self.tableSelector.currentPath, "r") as file:
            paths = file.read().splitlines()

        if len(paths) >= 4:
            self.tablepath = paths[0]
            self.fileTable = slicer.util.loadNodeFromFile(self.tablepath, 'TableFile')
            logic = CleftLandmarkFlowLogic()
            logic.checkForStatusColumn(self.fileTable,
                                       paths[0])  # if not present adds and saves to file

            with open(paths[1], "r") as file:
                self.landmarkNames = np.array(file.read().splitlines())

            self.imagedir = paths[2]
            self.landmarkdir = paths[3]

            self.importVolumeButton.enabled = True
            self.assignLayoutDescription(self.fileTable)
            # logic.hideCompletedSamples(self.fileTable)
            self.fileTable.SetLocked(True)
            self.fileTable.GetTable().Modified()  # update table view
        else:
            msg = qt.QMessageBox()
            msg.setIcon(qt.QMessageBox.Warning)
            msg.setText(
                "Check the contents of the project file.")
            msg.setWindowTitle("Project file error")
            msg.setStandardButtons(qt.QMessageBox.Ok)
            msg.exec_()
            self.importVolumeButton.enabled = False

    def onImportMesh(self):
        logic = CleftLandmarkFlowLogic()
        self.objpath, mtlpath, texdir = logic.getActiveCell(self.fileTable)

        if bool(self.objpath):

            print(self.objpath + " " + mtlpath + " " + texdir)
            self.meshNode, self.textureNode = logic.applyMultiTexture(os.path.join(self.imagedir, self.objpath),
                                                                      os.path.join(self.imagedir, mtlpath),
                                                                      os.path.join(self.imagedir, texdir))
            if bool(self.meshNode):
                # self.startSegmentationButton.enabled = True
                self.activeRow = logic.getActiveCellRow()
                # self.updateStatus(self.activeRow, 'Processing') # TODO uncomment this

                # TODO Texture

                # fiducials
                fiducialName = os.path.splitext(self.objpath)[0]
                fiducialOutput = os.path.join(self.landmarkdir, fiducialName + '.fcsv')
                print(fiducialOutput)
                try:
                    print("Loading fiducial")
                    a = slicer.util.loadMarkupsFiducialList(fiducialOutput)
                    self.fiducialNode = a[1]
                except:
                    print("failed loading fiducial")
                    self.fiducialNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", 'F')
                # print(self.fiducialNode)
                # print(self.fiducialNode.GetNumberOfControlPoints())
                # slicer.util.selectModule('Markups')

                self.enableButtons()

            else:
                msg = qt.QMessageBox()
                msg.setIcon(qt.QMessageBox.Warning)
                msg.setText(
                    "Image \"" + self.objpath + "\" is not in folder \"" + self.imagedir + ".")
                msg.setWindowTitle("Image cannot be loaded")
                msg.setStandardButtons(qt.QMessageBox.Ok)
                msg.exec_()
                logging.debug("Error loading associated files.")

        else:
            logging.debug("No valid table cell selected.")

    def onExportLandmarks(self):
        if hasattr(self, 'fiducialNode'):
            for i in range(0, self.fiducialNode.GetNumberOfControlPoints()):
                self.fiducialNode.SetNthFiducialLabel(i, self.landmarkNames[i])

            fiducialName = os.path.splitext(self.objpath)[0]
            fiducialOutput = os.path.join(self.landmarkdir, fiducialName + '.fcsv')
            if slicer.util.saveNode(self.fiducialNode, fiducialOutput):
                self.updateTableAndGUI()
            else:
                msg = qt.QMessageBox()
                msg.setIcon(qt.QMessageBox.Warning)
                msg.setText(
                    "Cannot save the landmark file.")
                msg.setWindowTitle("Landmark file cannot be saved")
                msg.setStandardButtons(qt.QMessageBox.Ok)
                # msg.buttonClicked.connect(msgbtn)
                msg.exec_()

    #
    # Call after current landmark is finished.
    #
    def updateTableAndGUI(self, complete=True):
        if complete:
            self.updateStatus(self.activeRow, 'Complete')
        else:
            self.updateStatus(self.activeRow, 'Incomplete')
        # clean up
        self.cleanup()
        # self.startSegmentationButton.enabled = False
        # self.exportSegmentationButton.enabled = False

    def cleanup(self):

        # TODO self.headNodeID etc..
        if hasattr(self, 'fiducialNode'):
            slicer.mrmlScene.RemoveNode(self.fiducialNode)
        if hasattr(self, 'meshNode'):
            slicer.mrmlScene.RemoveNode(self.meshNode)
        if hasattr(self, 'textureNode'):
            slicer.mrmlScene.RemoveNode(self.textureNode)

        # self.selectorButton.enabled = bool(self.tablepath)
        self.disableButtons()

    def enableButtons(self):
        self.markIncompleteButton.enabled = True
        self.exportLandmarksButton.enabled = True
        self.skipButton.enabled = True
        self.importVolumeButton.enabled = False

    def disableButtons(self):
        self.markIncompleteButton.enabled = False
        self.exportLandmarksButton.enabled = False
        self.skipButton.enabled = False
        self.importVolumeButton.enabled = True


class LogDataObject:
    """This class i
       """

    def __init__(self):
        self.FileType = "NULL"
        self.X = "NULL"
        self.Y = "NULL"
        self.Z = "NULL"
        self.Resolution = "NULL"
        self.Prefix = "NULL"
        self.SequenceStart = "NULL"
        self.SeqenceEnd = "NULL"


#
# LandmarkFlowLogic
#
class CleftLandmarkFlowLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def getActiveCell(self, table):
        tableView = slicer.app.layoutManager().tableWidget(0).tableView()
        if bool(tableView.selectedIndexes()):
            index = tableView.selectedIndexes()[0]
            objpath = table.GetTable().GetColumnByName('OBJFile')
            objpath = objpath.GetValue(index.row() - 1)
            mtlpath = table.GetTable().GetColumnByName('MTLFile')
            mtlpath = mtlpath.GetValue(index.row() - 1)
            texpath = table.GetTable().GetColumnByName('TextureDir')
            texpath = texpath.GetValue(index.row() - 1)
            print(objpath + " " + mtlpath + " " + texpath)
            return objpath, mtlpath, texpath
        else:
            return ""

    def getActiveCellRow(self):
        tableView = slicer.app.layoutManager().tableWidget(0).tableView()
        if bool(tableView.selectedIndexes()):
            index = tableView.selectedIndexes()[0]
            return index.row()
        else:
            return False

    def hideCompletedSamples(self, table):
        rowNumber = table.GetNumberOfRows()
        statusColumn = table.GetTable().GetColumnByName('Status')
        tableView = slicer.app.layoutManager().tableWidget(0).tableView()
        if not bool(statusColumn):
            return
        for currentRow in range(rowNumber):
            string = statusColumn.GetValue(currentRow)
            if (string):  # any status should trigger hide row
                tableView.hideRow(currentRow + 1)

        table.GetTable().Modified()  # update table view

    def checkForStatusColumn(self, table, tableFilePath):
        columnNumber = table.GetNumberOfColumns()
        statusColumn = table.GetTable().GetColumnByName('Status')
        if not bool(statusColumn):
            print("Adding column for status")
            col1 = table.AddColumn()
            col1.SetName('User')
            col2 = table.AddColumn()
            col2.SetName('Status')
            table.GetTable().Modified()  # update table view
            # Since no files have a status, write to file without reloading
            slicer.util.saveNode(table, tableFilePath)

    def applyTexture(self, modelNode, textureImageNode, addColorAsPointAttribute=False, colorAsVector=False):
        """
        Apply texture to model node
        """
        self.showTextureOnModel(modelNode, textureImageNode)
        # Show texture

    def showTextureOnModel(self, modelNode, textureImageNode):
        modelDisplayNode = modelNode.GetDisplayNode()
        modelDisplayNode.SetBackfaceCulling(0)
        textureImageFlipVert = vtk.vtkImageFlip()
        textureImageFlipVert.SetFilteredAxis(1)
        textureImageFlipVert.SetInputConnection(textureImageNode.GetImageDataConnection())
        modelDisplayNode.SetTextureImageDataConnection(textureImageFlipVert.GetOutputPort())

    def applyMultiTexture(self, objPath, mtlPath, texPath, addColorAsPointAttribute=False, colorAsVector=False):
        modelNode, textureImageNode = self.OBJtoVTP(objPath, mtlPath, texPath)
        self.applyTexture(modelNode, textureImageNode, addColorAsPointAttribute, colorAsVector)
        return modelNode, textureImageNode

    def OBJtoVTP(self, objPath, mtlPath, texPath):
        importer = vtk.vtkOBJImporter()
        importer.SetFileName(objPath)
        importer.SetFileNameMTL(mtlPath)
        importer.SetTexturePath(texPath)
        importer.Update()

        exporter = vtk.vtkSingleVTPExporter()
        exporter.SetRenderWindow(importer.GetRenderWindow())
        # exporter.SetFilePrefix(slicer.app.temporaryPath + os.path.splitext(os.path.basename(objPath))[0])
        exporter.SetFilePrefix(slicer.app.temporaryPath + os.path.sep + "multi-texture-temp")
        print(slicer.app.temporaryPath + os.path.sep + "multi-texture-temp")
        exporter.Write()

        # modelNode = slicer.util.loadModel(slicer.app.temporaryPath + os.path.splitext(os.path.basename(objPath))[0] + ".vtp")
        modelNode = slicer.util.loadModel(slicer.app.temporaryPath + os.path.sep + "multi-texture-temp.vtp")

        # textureImageNode = slicer.util.loadVolume(slicer.app.temporaryPath + os.path.splitext(os.path.basename(objPath))[0] + ".png", {'singleFile': True})
        textureImageNode = slicer.util.loadVolume(slicer.app.temporaryPath + os.path.sep + "multi-texture-temp.png",
                                                  {'singleFile': True})
        return modelNode, textureImageNode


class CleftLandmarkFlowTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear(0)

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_LandmarkFlow1()

    def test_LandmarkFlow1(self):
        """ Ideally you should have several levels of tests.  At the lowest level
        tests should exercise the functionality of the logic with different inputs
        (both valid and invalid).  At higher levels your tests should emulate the
        way the user would interact with your code and confirm that it still works
        the way you intended.
        One of the most important features of the tests is that it should alert other
        developers when their changes will have an impact on the behavior of your
        module.  For example, if a developer removes a feature that you depend on,
        your test should break so they know that the feature is needed.
        """

        self.delayDisplay("Starting the test")
        #
        # first, get some data
        #
        import urllib
        downloads = (
            ('http://slicer.kitware.com/midas3/download?items=5767', 'FA.nrrd', slicer.util.loadVolume),
        )

        for url, name, loader in downloads:
            filePath = slicer.app.temporaryPath + '/' + name
            if not os.path.exists(filePath) or os.stat(filePath).st_size == 0:
                logging.info('Requesting download %s from %s...\n' % (name, url))
                urllib.urlretrieve(url, filePath)
            if loader:
                logging.info('Loading %s...' % (name,))
                loader(filePath)
        self.delayDisplay('Finished with download and loading')

        meshNode = slicer.util.getNode(pattern="FA")
        logic = CleftLandmarkFlowLogic()
        self.assertIsNotNone(logic.hasImageData(meshNode))
        self.delayDisplay('Test passed!')
