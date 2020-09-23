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
labs = os.environ.get('labs', 'unknown_lab')


class LandmarkFlow(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "CranIAL CT Annotation"
        self.parent.categories = ["SlicerMorph.SlicerMorph Labs"]
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

class LandmarkFlowWidget(ScriptedLoadableModuleWidget):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def assignLayoutDescription(self, table):
        customLayout = """
    	<layout type=\"vertical\" split=\"true\" >
     <item splitSize=\"800\">
      <layout type=\"vertical\">
       <item>
        <view class=\"vtkMRMLViewNode\" singletontag=\"1\">
         <property name=\"viewlabel\" action=\"default\">1</property>
        </view>
       </item>
       <item>
        <layout type=\"horizontal\">
         <item>
          <view class=\"vtkMRMLSliceNode\" singletontag=\"Red\">
           <property name=\"orientation\" action=\"default\">Axial</property>
           <property name=\"viewlabel\" action=\"default\">R</property>
           <property name=\"viewcolor\" action=\"default\">#F34A33</property>
          </view>
         </item>
		 <item>
          <view class=\"vtkMRMLSliceNode\" singletontag=\"Green\">
           <property name=\"orientation\" action=\"default\">Coronal</property>
           <property name=\"viewlabel\" action=\"default\">G</property>
           <property name=\"viewcolor\" action=\"default\">#6EB04B</property>
          </view>
         </item>
         <item>
          <view class=\"vtkMRMLSliceNode\" singletontag=\"Yellow\">
           <property name=\"orientation\" action=\"default\">Sagittal</property>
           <property name=\"viewlabel\" action=\"default\">Y</property>
           <property name=\"viewcolor\" action=\"default\">#EDD54C</property>
          </view>
         </item>
        </layout>
       </item>
      </layout>
     </item>
     <item splitSize=\"200\">
      <view class=\"vtkMRMLTableViewNode\" singletontag=\"TableView1\">
        <property name=\"viewlabel\" action=\"default\">T</property>
      </view>
     </item>
    </layout>
    """

        customLayoutId = 701

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
        segmentTab = qt.QWidget()
        segmentTabLayout = qt.QFormLayout(segmentTab)

        tabsWidget.addTab(landmarkTab, "Landmark")
        # tabsWidget.addTab(segmentTab, "Segment")
        annotationsLayout.addWidget(tabsWidget)

        #
        # Frankfort Alignment Button
        #
        self.frankfortAlignment = qt.QPushButton("Frankfort Alignment")
        self.frankfortAlignment.toolTip = "Align to Frankfort"
        self.frankfortAlignment.enabled = False
        landmarkTabLayout.addRow(self.frankfortAlignment)

        #
        # Se-Na Alignment Button
        #
        self.oSeAlignment = qt.QPushButton("O-Se Alignment")
        self.oSeAlignment.toolTip = "Align to Opisthion-Sella"
        self.oSeAlignment.enabled = False
        landmarkTabLayout.addRow(self.oSeAlignment)

        #
        # O-Na Alignment Button
        #
        self.oNaAlignment = qt.QPushButton("O-Na Alignment")
        self.oNaAlignment.toolTip = "Align to Opisthion-Nasion"
        self.oNaAlignment.enabled = False
        landmarkTabLayout.addRow(self.oNaAlignment)
        #
        # Markups Incomplete Button
        #
        self.markIncompleteButton = qt.QPushButton("Marked Incomplete")
        self.markIncompleteButton.toolTip = "Click if the sample cannot be landmarked - no landmark file will be saved."
        self.markIncompleteButton.enabled = False
        landmarkTabLayout.addRow(self.markIncompleteButton)

        #
        # Export Landmarks Button
        #
        self.exportLandmarksButton = qt.QPushButton("Export landmarks")
        self.exportLandmarksButton.toolTip = "Export landmarks placed on the selected image"
        self.exportLandmarksButton.enabled = False
        landmarkTabLayout.addRow(self.exportLandmarksButton)

        #
        # Initiate Segmentation
        #
        self.startSegmentationButton = qt.QPushButton("Start segmenation")
        self.startSegmentationButton.toolTip = "Initialize segmentation and view Segment Editor"
        self.startSegmentationButton.enabled = False
        segmentTabLayout.addRow(self.startSegmentationButton)

        #
        # Export Segmentation
        #
        self.exportSegmentationButton = qt.QPushButton("Export segmenation")
        self.exportSegmentationButton.toolTip = "Export segmentation as a model"
        self.exportSegmentationButton.enabled = False
        segmentTabLayout.addRow(self.exportSegmentationButton)

        # connections
        self.tableSelector.connect("validInputChanged(bool)", self.onSelectTablePath)
        self.selectorButton.connect('clicked(bool)', self.onLoadTable)
        self.importVolumeButton.connect('clicked(bool)', self.onImportVolume)
        self.exportLandmarksButton.connect('clicked(bool)', self.onExportLandmarks)
        self.markIncompleteButton.connect('clicked(bool)', self.onMarkIncomplete)
        self.startSegmentationButton.connect('clicked(bool)', self.onStartSegmentation)
        self.exportSegmentationButton.connect('clicked(bool)', self.onExportSegmentation)
        self.frankfortAlignment.connect('clicked(bool)', self.onFrankfort)
        self.oSeAlignment.connect('clicked(bool)', self.onOSeaAlignment)
        self.oNaAlignment.connect('clicked(bool)', self.onONaAlignment)

        # Add vertical spacer
        self.layout.addStretch(1)

    def cleanup(self):
        pass

    def onStartSegmentation(self):
        logic = LandmarkFlowLogic()
        self.segmentationNode = logic.initializeSegmentation(self.volumeNode)
        self.exportSegmentationButton.enabled = True
        slicer.util.selectModule(slicer.modules.segmenteditor)

    def onExportSegmentation(self):
        if hasattr(self, 'segmentationNode'):
            segmentationName = os.path.splitext(self.activeCellString)[0]
            segmentationOutput = os.path.join(self.landmarkDirSelector.currentPath, segmentationName + '.nrrd')
            slicer.util.saveNode(self.segmentationNode, segmentationOutput)
            self.updateTableAndGUI()
        else:
            logging.debug("No valid segmentation to export.")

    def onFrankfort(self):

        for i in range(0, self.fiducialNode.GetNumberOfControlPoints()):
            self.fiducialNode.SetNthFiducialLabel(i, self.landmarkNames[i])

        logic = LandmarkFlowLogic()

        zyoL_id = np.where(self.landmarkNames == "zyoL")[0][0]
        poR_id = np.where(self.landmarkNames == "poR")[0][0]
        poL_id = np.where(self.landmarkNames == "poL")[0][0]

        if (self.fiducialNode.GetNumberOfFiducials() <= zyoL_id) | (
                self.fiducialNode.GetNumberOfFiducials() <= poR_id) | (
                self.fiducialNode.GetNumberOfFiducials() <= poL_id):
            msg = qt.QMessageBox()
            msg.setIcon(qt.QMessageBox.Warning)
            msg.setText("All necessary landmarks not marked yet")
            msg.setWindowTitle("Missing landmark")
            msg.setStandardButtons(qt.QMessageBox.Ok)
            msg.exec_()
            logging.debug("Error loading associated files.")
            return

        poR = [0, 0, 0]
        poL = [0, 0, 0]
        zyoL = [0, 0, 0]

        self.fiducialNode.GetNthFiducialPosition(poR_id, poR)
        self.fiducialNode.GetNthFiducialPosition(poL_id, poL)
        self.fiducialNode.GetNthFiducialPosition(zyoL_id, zyoL)
        mat = logic.getFrankfortAlignment(poR, poL, zyoL)

        print(mat)

        self.transformNode.SetAndObserveMatrixTransformToParent(mat)

        # Reset ROI
        volRenLogic = slicer.modules.volumerendering.logic()
        volRenLogic.FitROIToVolume(volRenLogic.GetFirstVolumeRenderingDisplayNode(self.volumeNode))

        # center view
        threeDView = slicer.app.layoutManager().threeDWidget(0).threeDView()
        threeDView.resetFocalPoint()
        threeDView.lookFromAxis(5)

        # center slice view
        slicer.util.resetSliceViews()

        print("Frankfort Alignment")

    def onOSeaAlignment(self):

        for i in range(0, self.fiducialNode.GetNumberOfControlPoints()):
            self.fiducialNode.SetNthFiducialLabel(i, self.landmarkNames[i])

        logic = LandmarkFlowLogic()

        o_id = np.where(self.landmarkNames == "o")[0][0]
        se_id = np.where(self.landmarkNames == "se")[0][0]
        poR_id = np.where(self.landmarkNames == "poR")[0][0]
        poL_id = np.where(self.landmarkNames == "poL")[0][0]

        if (self.fiducialNode.GetNumberOfFiducials() <= se_id) | (self.fiducialNode.GetNumberOfFiducials() <= o_id) | (
                self.fiducialNode.GetNumberOfFiducials() <= poR_id) | (
                self.fiducialNode.GetNumberOfFiducials() <= poL_id):
            msg = qt.QMessageBox()
            msg.setIcon(qt.QMessageBox.Warning)
            msg.setText("All necessary landmarks not marked yet")
            msg.setWindowTitle("Missing landmark")
            msg.setStandardButtons(qt.QMessageBox.Ok)
            msg.exec_()
            logging.debug("Error loading associated files.")
            return

        poR = [0, 0, 0]
        poL = [0, 0, 0]
        se = [0, 0, 0]
        o = [0, 0, 0]

        self.fiducialNode.GetNthFiducialPosition(poR_id, poR)
        self.fiducialNode.GetNthFiducialPosition(poL_id, poL)
        self.fiducialNode.GetNthFiducialPosition(se_id, se)
        self.fiducialNode.GetNthFiducialPosition(o_id, o)
        mat = logic.getOSeAlignment(poR, poL, se, o)

        print(mat)

        self.transformNode.SetAndObserveMatrixTransformToParent(mat)

        # Reset ROI
        volRenLogic = slicer.modules.volumerendering.logic()
        volRenLogic.FitROIToVolume(volRenLogic.GetFirstVolumeRenderingDisplayNode(self.volumeNode))

        # center view
        threeDView = slicer.app.layoutManager().threeDWidget(0).threeDView()
        threeDView.resetFocalPoint()
        threeDView.lookFromAxis(5)

        # center slice view
        slicer.util.resetSliceViews()

        print("O-Se Alignment")

    def onONaAlignment(self):
        for i in range(0, self.fiducialNode.GetNumberOfControlPoints()):
            self.fiducialNode.SetNthFiducialLabel(i, self.landmarkNames[i])

        logic = LandmarkFlowLogic()

        o_id = np.where(self.landmarkNames == "o")[0][0]
        na_id = np.where(self.landmarkNames == "n")[0][0]
        poR_id = np.where(self.landmarkNames == "poR")[0][0]
        poL_id = np.where(self.landmarkNames == "poL")[0][0]

        if (self.fiducialNode.GetNumberOfFiducials() <= se_id) | (self.fiducialNode.GetNumberOfFiducials() <= o_id) | (
                self.fiducialNode.GetNumberOfFiducials() <= poR_id) | (
                self.fiducialNode.GetNumberOfFiducials() <= poL_id):
            msg = qt.QMessageBox()
            msg.setIcon(qt.QMessageBox.Warning)
            msg.setText("All necessary landmarks not marked yet")
            msg.setWindowTitle("Missing landmark")
            msg.setStandardButtons(qt.QMessageBox.Ok)
            msg.exec_()
            logging.debug("Error loading associated files.")
            return

        poR = [0, 0, 0]
        poL = [0, 0, 0]
        na = [0, 0, 0]
        o = [0, 0, 0]

        self.fiducialNode.GetNthFiducialPosition(poR_id, poR)
        self.fiducialNode.GetNthFiducialPosition(poL_id, poL)
        self.fiducialNode.GetNthFiducialPosition(na_id, na)
        self.fiducialNode.GetNthFiducialPosition(o_id, o)
        mat = logic.getOSeAlignment(poR, poL, na, o)

        print(mat)

        self.transformNode.SetAndObserveMatrixTransformToParent(mat)

        # Reset ROI
        volRenLogic = slicer.modules.volumerendering.logic()
        volRenLogic.FitROIToVolume(volRenLogic.GetFirstVolumeRenderingDisplayNode(self.volumeNode))

        # center view
        threeDView = slicer.app.layoutManager().threeDWidget(0).threeDView()
        threeDView.resetFocalPoint()
        threeDView.lookFromAxis(5)

        # center slice view
        slicer.util.resetSliceViews()
        print("O-Na Alignment")

    def onMarkIncomplete(self):
        # TODO ask for a reason, maybe a text box?
        self.updateTableAndGUI(False)

    def updateStatus(self, index, status_string):
        # refresh table from file, update the status column, and save
        name = self.fileTable.GetName()
        slicer.mrmlScene.RemoveNode(self.fileTable)
        self.fileTable = slicer.util.loadNodeFromFile(self.tablepath, 'TableFile')
        self.fileTable.SetLocked(True)
        self.fileTable.SetName(name)
        logic = LandmarkFlowLogic()
        logic.hideCompletedSamples(self.fileTable)
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
            logic = LandmarkFlowLogic()
            logic.checkForStatusColumn(self.fileTable,
                                       paths[0])  # if not present adds and saves to file

            with open(paths[1], "r") as file:
                self.landmarkNames = np.array(file.read().splitlines())

            self.imagedir = paths[2]
            self.landmarkdir = paths[3]

            self.importVolumeButton.enabled = True
            self.assignLayoutDescription(self.fileTable)
            logic.hideCompletedSamples(self.fileTable)
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

    def onImportVolume(self):
        logic = LandmarkFlowLogic()
        self.activeCellString = logic.getActiveCell()
        if bool(self.activeCellString):
            volumePath = os.path.join(self.imagedir, self.activeCellString)
            self.volumeNode = logic.runImport(volumePath)
            if bool(self.volumeNode):
                self.markIncompleteButton.enabled = True
                # self.startSegmentationButton.enabled = True
                self.activeRow = logic.getActiveCellRow()
                # self.updateStatus(self.activeRow, 'Processing') # TODO uncomment this

                # Set window/level of the volume to bone
                displayNode = self.volumeNode.GetDisplayNode()
                displayNode.AutoWindowLevelOff()
                displayNode.SetWindow(1000)
                displayNode.SetLevel(400)

                # 3D render volume
                volRenLogic = slicer.modules.volumerendering.logic()
                displayNode = volRenLogic.CreateDefaultVolumeRenderingNodes(self.volumeNode)
                displayNode.SetVisibility(True)
                displayNode.GetVolumePropertyNode().Copy(volRenLogic.GetPresetByName('CT-AAA'))

                roi = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLAnnotationROINode")
                displayNode.SetAndObserveROINodeID(roi.GetID())
                displayNode.CroppingEnabledOn()
                roi.GetDisplayNode().SetVisibility(1)
                volRenLogic.FitROIToVolume(displayNode)

                layoutManager = slicer.app.layoutManager()
                threeDWidget = layoutManager.threeDWidget(0)
                threeDView = threeDWidget.threeDView()
                threeDView.resetFocalPoint()
                threeDView.lookFromAxis(5)

                self.fiducialNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", 'F')
                slicer.util.selectModule('Markups')
                self.exportLandmarksButton.enabled = True
                self.frankfortAlignment.enabled = True
                self.oSeAlignment.enabled = True
                self.oNaAlignment.enabled = True

                matrix = vtk.vtkMatrix4x4()
                matrix.Identity()
                transform = vtk.vtkTransform()
                transform.SetMatrix(matrix)
                self.transformNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLTransformNode', 'Alignment Transform')
                self.transformNode.SetAndObserveTransformToParent(transform)

                self.volumeNode.SetAndObserveTransformNodeID(self.transformNode.GetID())
                self.fiducialNode.SetAndObserveTransformNodeID(self.transformNode.GetID())

            else:
                msg = qt.QMessageBox()
                msg.setIcon(qt.QMessageBox.Warning)
                msg.setText(
                    "Image \"" + logic.getActiveCell() + "\" is not in folder \"" + self.imagedir + ".")
                msg.setWindowTitle("Image cannot be loaded")
                msg.setStandardButtons(qt.QMessageBox.Ok)
                msg.exec_()
                logging.debug("Error loading associated files.")

        else:
            logging.debug("No valid table cell selected.")

    def onExportLandmarks(self):
        if hasattr(self, 'fiducialNode'):
            fiducialName = os.path.splitext(self.activeCellString)[0]
            fiducialName = os.path.splitext(fiducialName)[0]
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
        if hasattr(self, 'fiducialNode'):
            slicer.mrmlScene.RemoveNode(self.fiducialNode)
        if hasattr(self, 'volumeNode'):
            slicer.mrmlScene.RemoveNode(self.volumeNode)
        if hasattr(self, 'segmentationNode'):
            slicer.mrmlScene.RemoveNode(self.segmentationNode)
        if hasattr(self, 'labelMap'):
            slicer.mrmlScene.RemoveNode(self.labelMap)
        annotationROIs = slicer.mrmlScene.GetNodesByClass("vtkMRMLAnnotationROINode")
        for roi in annotationROIs:
            slicer.mrmlScene.RemoveNode(roi)

        self.selectorButton.enabled = bool(self.tablepath)
        self.importVolumeButton.enabled = True
        self.markIncompleteButton.enabled = False
        self.exportLandmarksButton.enabled = False
        # self.startSegmentationButton.enabled = False
        # self.exportSegmentationButton.enabled = False


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
class LandmarkFlowLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def run(self, inputFile, spacingX, spacingY, spacingZ):
        """
        Run the actual algorithm
        """
        spacing = [spacingX, spacingY, spacingZ]
        inputFile.SetSpacing(spacing)

    def takeScreenshot(self, name, description, type=-1):
        # show the message even if not taking a screen shot
        slicer.util.delayDisplay(
            'Take screenshot: ' + description + '.\nResult is available in the Annotations module.', 3000)

        lm = slicer.app.layoutManager()
        # switch on the type to get the requested window
        widget = 0
        if type == slicer.qMRMLScreenShotDialog.FullLayout:
            # full layout
            widget = lm.viewport()
        elif type == slicer.qMRMLScreenShotDialog.ThreeD:
            # just the 3D window
            widget = lm.threeDWidget(0).threeDView()
        elif type == slicer.qMRMLScreenShotDialog.Red:
            # red slice window
            widget = lm.sliceWidget("Red")
        elif type == slicer.qMRMLScreenShotDialog.Yellow:
            # yellow slice window
            widget = lm.sliceWidget("Yellow")
        elif type == slicer.qMRMLScreenShotDialog.Green:
            # green slice window
            widget = lm.sliceWidget("Green")
        else:
            # default to using the full window
            widget = slicer.util.mainWindow()
            # reset the type so that the node is set correctly
            type = slicer.qMRMLScreenShotDialog.FullLayout

        # grab and convert to vtk image data
        qimage = ctk.ctkWidgetsUtils.grabWidget(widget)
        imageData = vtk.vtkImageData()
        slicer.qMRMLUtils().qImageToVtkImageData(qimage, imageData)

        annotationLogic = slicer.modules.annotations.logic()
        annotationLogic.CreateSnapShot(name, description, type, 1, imageData)

    def initializeSegmentation(self, masterVolumeNode):
        # Create segmentation
        segmentationName = masterVolumeNode.GetName()
        segmentationNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLSegmentationNode',
                                                              segmentationName + '_segmentation')
        segmentationNode.CreateDefaultDisplayNodes()  # only needed for display
        segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(masterVolumeNode)
        segmentation = segmentationNode.GetSegmentation()
        # Add template segments
        self.addNewSegment(segmentation, "Dorsal Fin", (1.0, 1.0, 0.0))
        self.addNewSegment(segmentation, "Adipose Fin", (0.172549, 0.764706, 0.945098))
        self.addNewSegment(segmentation, "Caudal Fin", (0.396078, 0.027451, 0.447059))
        self.addNewSegment(segmentation, "Anal Fin", (0.513725, 0.764706, 0.180392))
        self.addNewSegment(segmentation, "Pelvic Fin", (1.0, 0.0, 0.0))
        self.addNewSegment(segmentation, "Pectoral Fin", (0.121569, 0.823529, 0.203922))
        self.addNewSegment(segmentation, "HeadEye", (0.0235294, 0.333333, 1.0))
        self.addNewSegment(segmentation, "Eye", (1.0, 0.0, 0.498039))
        self.addNewSegment(segmentation, "Caudal Fin Ray",
                           (0.6392156862745098, 0.24705882352941178, 0.9607843137254902))
        self.addNewSegment(segmentation, "Alt Fin Ray", (0.9764705882352941, 0.5215686274509804, 0.19215686274509805))
        self.addNewSegment(segmentation, "Alt Fin Spine",
                           (0.13725490196078433, 0.4588235294117647, 0.21568627450980393))
        return segmentationNode

    def addNewSegment(self, segmentation, name, color):
        segmentID = segmentation.AddEmptySegment(name)
        segmentation.GetSegment(segmentID).SetColor(color)

    def getActiveCell(self):
        tableView = slicer.app.layoutManager().tableWidget(0).tableView()
        if bool(tableView.selectedIndexes()):
            index = tableView.selectedIndexes()[0]
            indexTuple = [index.row(), index.column()]
            tableString = tableView.mrmlTableNode().GetCellText(index.row() - 1, index.column())
            return tableString
        else:
            return ""

    def getActiveCellRow(self):
        tableView = slicer.app.layoutManager().tableWidget(0).tableView()
        if bool(tableView.selectedIndexes()):
            index = tableView.selectedIndexes()[0]
            return index.row()
        else:
            return False

    def runImport(self, volumePath):
        print(volumePath)
        properties = {'singleFile': True}
        try:
            volumeNode = slicer.util.loadVolume(volumePath, properties)
            return volumeNode
        except:
            False

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

    # Frankfort alignment
    def getFrankfortAlignment(self, poR, poL, zyoL):

        po = [poR[0] - poL[0], poR[1] - poL[1], poR[2] - poL[2]]

        vTransform = vtk.vtkTransform()
        vTransform.RotateZ(-np.arctan2(po[1], po[0]) * 180 / np.pi)

        po1 = vTransform.TransformPoint(poR)
        po2 = vTransform.TransformPoint(poL)
        zyo = vTransform.TransformPoint(zyoL)

        po = [po1[0] - po2[0], po1[1] - po2[1], po1[2] - po2[2]]

        vTransform2 = vtk.vtkTransform()
        vTransform2.RotateY(np.arctan2(po[2], po[0]) * 180 / np.pi)

        po1 = vTransform2.TransformPoint(po1)
        po2 = vTransform2.TransformPoint(po2)
        zyo = vTransform2.TransformPoint(zyo)

        po_zyo = [zyo[0] - (po1[0] + po2[0]) / 2, zyo[1] - (po1[1] + po2[1]) / 2, zyo[2] - (po1[2] + po2[2]) / 2]

        vTransform3 = vtk.vtkTransform()
        vTransform3.RotateX(-np.arctan2(po_zyo[2], po_zyo[1]) * 180 / np.pi)

        vTransform3.Concatenate(vTransform2)
        vTransform3.Concatenate(vTransform)
        return vTransform3.GetMatrix()

    def getOSeAlignment(self, poR, poL, se, o):

        po = [poR[0] - poL[0], poR[1] - poL[1], poR[2] - poL[2]]

        vTransform = vtk.vtkTransform()
        vTransform.RotateZ(-np.arctan2(po[1], po[0]) * 180 / np.pi)

        po1 = vTransform.TransformPoint(poR)
        po2 = vTransform.TransformPoint(poL)
        se1 = vTransform.TransformPoint(se)
        o1 = vTransform.TransformPoint(o)

        po = [po1[0] - po2[0], po1[1] - po2[1], po1[2] - po2[2]]

        vTransform2 = vtk.vtkTransform()
        vTransform2.RotateY(np.arctan2(po[2], po[0]) * 180 / np.pi)

        se1 = vTransform2.TransformPoint(se1)
        o1 = vTransform2.TransformPoint(o1)

        o_se = [se1[0] - o1[0], se1[1] - o1[1], se1[2] - o1[2]]

        vTransform3 = vtk.vtkTransform()
        vTransform3.RotateX(-np.arctan2(o_se[2], o_se[1]) * 180 / np.pi)

        vTransform3.Concatenate(vTransform2)
        vTransform3.Concatenate(vTransform)
        return vTransform3.GetMatrix()

class LandmarkFlowTest(ScriptedLoadableModuleTest):
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

        volumeNode = slicer.util.getNode(pattern="FA")
        logic = LandmarkFlowLogic()
        self.assertIsNotNone(logic.hasImageData(volumeNode))
        self.delayDisplay('Test passed!')
