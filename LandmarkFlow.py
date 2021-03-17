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
        self.parent.title = "CranIAL CT Annotation TEST"
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
    <layout type=\"horizontal\" split=\"true\" >
        <item splitSize=\"800\">
        <layout type=\"vertical\"  split=\"true\" >
            <item splitSize=\"500\">
            <view class=\"vtkMRMLViewNode\" singletontag=\"1\">
            <property name=\"viewlabel\" action=\"default\">1</property>
            </view>
            </item>
            <item splitSize=\"500\">
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

        self.headSegmentID = None
        self.skullSegmentId = None
        self.segmentationNode = None
        self.segmentEditorWidget = None
        self.segmentEditorNode = None

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
        tabsWidget.addTab(segmentTab, "Segment")
        annotationsLayout.addWidget(tabsWidget)

        windowing = ctk.ctkCollapsibleButton()
        windowing.text = "Window/Level for Slices"
        landmarkTabLayout.addWidget(windowing)
        windowingLayout = qt.QGridLayout(windowing)

        #
        # Bone Button
        #
        self.boneWindow = qt.QPushButton("Bone")
        self.boneWindow.toolTip = "Set Window/Level to Bone Window"
        self.boneWindow.enabled = False
        windowingLayout.addWidget(self.boneWindow, 1, 1)

        #
        # Soft Tissue
        #
        self.softTissueWindow = qt.QPushButton("Brain")
        self.softTissueWindow.toolTip = "Set Window/Level to Soft Tissue Window"
        self.softTissueWindow.enabled = False
        windowingLayout.addWidget(self.softTissueWindow, 1, 2)

        rendering = ctk.ctkCollapsibleButton()
        rendering.text = "3D rendering"
        landmarkTabLayout.addWidget(rendering)
        renderingLayout = qt.QGridLayout(rendering)

        #
        # Bone Button
        #
        self.boneRender = qt.QPushButton("Bone")
        self.boneRender.toolTip = "Set Window/Level to Bone Window"
        self.boneRender.enabled = False
        renderingLayout.addWidget(self.boneRender, 1, 1)

        #
        # Bone Button
        #
        self.boneRender2 = qt.QPushButton("Bone (infant)")
        self.boneRender2.toolTip = "Set Window/Level to Bone Window"
        self.boneRender2.enabled = False
        renderingLayout.addWidget(self.boneRender2, 1, 2)

        #
        # Soft Tissue
        #
        self.softTissueRender = qt.QPushButton("Soft")
        self.softTissueRender.toolTip = "Set Window/Level to Soft Tissue Window"
        self.softTissueRender.enabled = False
        renderingLayout.addWidget(self.softTissueRender, 1, 3)

        #
        # Remove Tube Button
        #
        self.removeTubeButton = qt.QPushButton("Remove Tube")
        # self.removeTubeButton.toolTip = "Set Window/Level to Bone Window"
        self.removeTubeButton.enabled = False
        renderingLayout.addWidget(self.removeTubeButton, 2, 1)

        #
        # Remove noise button
        #
        self.removeNoiseButton = qt.QPushButton("Remove Noise")
        # self.removeNoiseButton.toolTip = "Set Window/Level to Bone Window"
        self.removeNoiseButton.enabled = False
        renderingLayout.addWidget(self.removeNoiseButton, 2, 2)

        #
        # Original button
        #
        self.originalVolumeButton = qt.QPushButton("Original Volume")
        # self.removeNoiseButton.toolTip = "Set Window/Level to Bone Window"
        self.originalVolumeButton.enabled = False
        renderingLayout.addWidget(self.originalVolumeButton, 2, 3)

        alignments = ctk.ctkCollapsibleButton()
        alignments.text = "Alignments"
        landmarkTabLayout.addWidget(alignments)
        alignmentLayout = qt.QGridLayout(alignments)

        #
        # Left Frankfort Alignment Button
        #
        self.frankfortAlignment = qt.QPushButton("Frankfort (L)")
        self.frankfortAlignment.toolTip = "Align to Frankfort"
        self.frankfortAlignment.enabled = False
        alignmentLayout.addWidget(self.frankfortAlignment, 1, 1)

        #
        # Right Frankfort Alignment Button
        #
        self.frankfortAlignmentR = qt.QPushButton("Frankfort (R)")
        self.frankfortAlignmentR.toolTip = "Align to Frankfort"
        self.frankfortAlignmentR.enabled = False
        alignmentLayout.addWidget(self.frankfortAlignmentR, 1, 2)

        #
        # Se-Na Alignment Button
        #
        self.oSeAlignment = qt.QPushButton("O-Se")
        self.oSeAlignment.toolTip = "Align to Opisthion-Sella"
        self.oSeAlignment.enabled = False
        alignmentLayout.addWidget(self.oSeAlignment, 1, 3)

        #
        # O-Na Alignment Button
        #
        self.oNaAlignment = qt.QPushButton("O-Na")
        self.oNaAlignment.toolTip = "Align to Opisthion-Nasion"
        self.oNaAlignment.enabled = False
        alignmentLayout.addWidget(self.oNaAlignment, 1, 4)

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
        self.skipButton.connect('clicked(bool)', self.onSkip)
        self.startSegmentationButton.connect('clicked(bool)', self.onStartSegmentation)
        self.exportSegmentationButton.connect('clicked(bool)', self.onExportSegmentation)
        self.frankfortAlignment.connect('clicked(bool)', self.onFrankfort)
        self.frankfortAlignmentR.connect('clicked(bool)', self.onFrankfort2)
        self.oSeAlignment.connect('clicked(bool)', self.onOSeaAlignment)
        self.oNaAlignment.connect('clicked(bool)', self.onONaAlignment)
        self.boneWindow.connect('clicked(bool)', self.onBoneWindow)
        self.softTissueWindow.connect('clicked(bool)', self.onSoftTissueWindow)
        self.boneRender.connect('clicked(bool)', self.onBoneRender)
        self.boneRender2.connect('clicked(bool)', self.onBoneRender2)
        self.softTissueRender.connect('clicked(bool)', self.onSoftTissueRender)

        self.removeTubeButton.connect('clicked(bool)', self.onRemoveTube)
        self.removeNoiseButton.connect('clicked(bool)', self.onRemoveNoise)
        self.originalVolumeButton.connect('clicked(bool)', self.onOriginalVolume)

        # Add vertical spacer
        self.layout.addStretch(1)
        self.softTissueVP = slicer.util.loadNodeFromFile("/opt/Slicer-Extensions-29025/CranialModules/CT-SoftTissue.vp",
                                                         "TransferFunctionFile")
        self.boneVP = slicer.util.loadNodeFromFile("/opt/Slicer-Extensions-29025/CranialModules/CT-Bone.vp",
                                                   "TransferFunctionFile")

        self.boneVP2 = slicer.util.loadNodeFromFile("/opt/Slicer-Extensions-29025/CranialModules/CT-Bone2.vp",
                                                    "TransferFunctionFile")

        self.startSegmentationButton.connect('clicked(bool)', self.onStartSegmentation)
        self.exportSegmentationButton.connect('clicked(bool)', self.onExportSegmentation)

    def removeTube(self):
        if self.headSegmentID is None:
            self.cleaningSegmentation = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
            self.cleaningSegmentation.CreateDefaultDisplayNodes()
            self.cleaningSegmentation.SetDisplayVisibility(0)
            self.cleaningSegmentation.SetReferenceImageGeometryParameterFromVolumeNode(self.volumeNode)
            self.cleaningSegmentation.SetAndObserveTransformNodeID(self.transformNode.GetID())

            self.segmentEditorWidget = slicer.qMRMLSegmentEditorWidget()
            # To show segment editor widget (useful for debugging): segmentEditorWidget.show()
            self.segmentEditorWidget.setMRMLScene(slicer.mrmlScene)
            self.segmentEditorNode = slicer.vtkMRMLSegmentEditorNode()
            self.segmentEditorNode.SetOverwriteMode(slicer.vtkMRMLSegmentEditorNode.OverwriteNone)
            slicer.mrmlScene.AddNode(self.segmentEditorNode)
            self.segmentEditorWidget.setMRMLSegmentEditorNode(self.segmentEditorNode)
            self.segmentEditorWidget.setSegmentationNode(self.cleaningSegmentation)
            self.segmentEditorWidget.setMasterVolumeNode(self.volumeNode)

            self.headSegmentID = self.cleaningSegmentation.GetSegmentation().AddEmptySegment("head")
            self.segmentEditorNode.SetSelectedSegmentID(self.headSegmentID)
            self.segmentEditorWidget.setActiveEffectByName("Threshold")

            volumeScalarRange = self.volumeNode.GetImageData().GetScalarRange()

            effect = self.segmentEditorWidget.activeEffect()
            effect.setParameter("MinimumThreshold", str(-200))
            effect.setParameter("MaximumThreshold", str(volumeScalarRange[1]))
            effect.self().onApply()

            self.segmentEditorWidget.setActiveEffectByName("Islands")
            effect = self.segmentEditorWidget.activeEffect()
            effect.setParameterDefault("Operation", "KEEP_LARGEST_ISLAND")
            effect.self().onApply()

    def removeNoise(self):
        if self.headSegmentID is None:
            self.removeTube()
        if self.skullSegmentId is None:
            self.skullSegmentId = self.cleaningSegmentation.GetSegmentation().AddEmptySegment("bone")
            self.segmentEditorNode.SetSelectedSegmentID(self.skullSegmentId)
            self.segmentEditorWidget.setActiveEffectByName("Threshold")

            volumeScalarRange = self.volumeNode.GetImageData().GetScalarRange()

            effect = self.segmentEditorWidget.activeEffect()
            effect.setParameter("MinimumThreshold", str(143))
            effect.setParameter("MaximumThreshold", str(volumeScalarRange[1]))
            effect.self().onApply()

            self.segmentEditorWidget.setActiveEffectByName("Islands")
            effect = self.segmentEditorWidget.activeEffect()
            effect.setParameter("Operation", "REMOVE_SMALL_ISLANDS")
            effect.setParameter("MinimumSize", "1000")
            effect.self().onApply()

            self.segmentEditorWidget.setActiveEffectByName("Logical operators")
            effect = self.segmentEditorWidget.activeEffect()
            effect.setParameter("Operation", "INTERSECT")
            effect.setParameter("ModifierSegmentID", self.headSegmentID)
            effect.self().onApply()

    def onRemoveTube(self):

        self.removeTube()

        self.segmentEditorNode.SetSelectedSegmentID(self.headSegmentID)
        self.segmentEditorWidget.setActiveEffectByName("Mask volume")
        effect = self.segmentEditorWidget.activeEffect()
        effect.setParameter("FillValue", str(-200))
        # Blank out voxels that are outside the segment
        effect.setParameter("Operation", "FILL_OUTSIDE")
        # Create a volume that will store temporary masked volumes

        effect.self().outputVolumeSelector.setCurrentNode(self.maskedVolume)
        effect.self().onApply()

        self.turnOffRender(self.volumeNode)
        self.turnOnRender(self.maskedVolume)
        slicer.util.setSliceViewerLayers(background=self.volumeNode)

    def onRemoveNoise(self):
        self.removeNoise()

        self.segmentEditorNode.SetSelectedSegmentID(self.skullSegmentId)
        self.segmentEditorWidget.setActiveEffectByName("Mask volume")
        effect = self.segmentEditorWidget.activeEffect()
        effect.setParameter("FillValue", str(-200))
        # Blank out voxels that are outside the segment
        effect.setParameter("Operation", "FILL_OUTSIDE")
        # Create a volume that will store temporary masked volumes

        effect.self().outputVolumeSelector.setCurrentNode(self.maskedVolume)
        effect.self().onApply()

        self.turnOffRender(self.volumeNode)
        self.turnOnRender(self.maskedVolume)
        slicer.util.setSliceViewerLayers(background=self.volumeNode)

    def onOriginalVolume(self):
        self.turnOffRender(self.maskedVolume)
        self.turnOnRender(self.volumeNode)

    def onBoneWindow(self):
        # Set window/level of the volume to bone
        displayNode = self.volumeNode.GetDisplayNode()
        displayNode.AutoWindowLevelOff()
        displayNode.SetWindow(1000)
        displayNode.SetLevel(400)

    def onSoftTissueWindow(self):
        # Set window/level of the volume to bone
        displayNode = self.volumeNode.GetDisplayNode()
        displayNode.AutoWindowLevelOff()
        displayNode.SetWindow(100)
        displayNode.SetLevel(50)

    def onBoneRender(self):
        volRenLogic = slicer.modules.volumerendering.logic()
        volRenLogic.GetFirstVolumeRenderingDisplayNode(self.volumeNode).GetVolumePropertyNode().Copy(self.boneVP)
        volRenLogic.GetFirstVolumeRenderingDisplayNode(self.maskedVolume).GetVolumePropertyNode().Copy(self.boneVP)

    def onBoneRender2(self):
        volRenLogic = slicer.modules.volumerendering.logic()
        volRenLogic.GetFirstVolumeRenderingDisplayNode(self.volumeNode).GetVolumePropertyNode().Copy(self.boneVP2)
        volRenLogic.GetFirstVolumeRenderingDisplayNode(self.maskedVolume).GetVolumePropertyNode().Copy(self.boneVP2)

    def onSoftTissueRender(self):
        # Set window/level of the volume to bone
        volRenLogic = slicer.modules.volumerendering.logic()
        volRenLogic.GetFirstVolumeRenderingDisplayNode(self.volumeNode).GetVolumePropertyNode().Copy(
            self.softTissueVP)
        volRenLogic.GetFirstVolumeRenderingDisplayNode(self.maskedVolume).GetVolumePropertyNode().Copy(
            self.softTissueVP)

    def onStartSegmentation(self):
        if self.segmentEditorNode is None:
            self.segmentEditorWidget = slicer.qMRMLSegmentEditorWidget()
            self.segmentEditorWidget.setMRMLScene(slicer.mrmlScene)
            self.segmentEditorNode = slicer.vtkMRMLSegmentEditorNode()
            self.segmentEditorNode.SetOverwriteMode(slicer.vtkMRMLSegmentEditorNode.OverwriteNone)
            slicer.mrmlScene.AddNode(self.segmentEditorNode)

        if self.segmentationNode is None:
            logic = LandmarkFlowLogic()
            self.segmentationNode = logic.initializeSegmentation(self.volumeNode)
            self.segmentationNode.SetAndObserveTransformNodeID(self.transformNode.GetID())
            self.exportSegmentationButton.enabled = True
            logic.segmentSkull(self.segmentationNode, self.segmentEditorNode, self.segmentEditorWidget, self.volumeNode)
            self.startSegmentationButton.enabled = False
            self.turnOffRender(self.volumeNode)

        slicer.util.selectModule(slicer.modules.segmenteditor)
        editor = slicer.util.getNode("SegmentEditor_1")
        editor.SetSelectedSegmentID("Intraop Material")
        editor.SetOverwriteMode(2)
        editor.SetMasterVolumeIntensityMask(1)
        editor.SetMasterVolumeIntensityMaskRange(143, 5000)
        editor.SetAttribute('BrushSphere', '1')

    def onExportSegmentation(self):
        if self.segmentationNode is not None:
            shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
            exportFolderItemId = shNode.CreateFolderItem(shNode.GetSceneItemID(), "Segments")
            slicer.modules.segmentations.logic().ExportAllSegmentsToModels(self.segmentationNode, exportFolderItemId)

            if slicer.util.saveNode(self.segmentationNode,
                                    os.path.join(self.landmarkdir, self.segmentationNode.GetName() + ".seg.nrrd")) and \
                    slicer.util.saveNode(slicer.util.getNode("Skull"), os.path.join(self.landmarkdir,
                                                                                    self.segmentationNode.GetName() + ".skull.ply")) and \
                    slicer.util.saveNode(slicer.util.getNode("Intraop Material"), os.path.join(self.landmarkdir,
                                                                                               self.segmentationNode.GetName() + ".material.ply")):

                self.updateTableAndGUI("Segmentation")

            else:
                msg = qt.QMessageBox()
                msg.setIcon(qt.QMessageBox.Warning)
                msg.setText(
                    "Cannot save the segmentation file.")
                msg.setWindowTitle("File cannot be saved")
                msg.setStandardButtons(qt.QMessageBox.Ok)
                msg.exec_()

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

        self.transformNode.SetAndObserveMatrixTransformToParent(mat)

        self.resetViews()

        print("Frankfort Alignment")

    def onFrankfort2(self):

        for i in range(0, self.fiducialNode.GetNumberOfControlPoints()):
            self.fiducialNode.SetNthFiducialLabel(i, self.landmarkNames[i])

        logic = LandmarkFlowLogic()

        zyoR_id = np.where(self.landmarkNames == "zyoR")[0][0]
        poR_id = np.where(self.landmarkNames == "poR")[0][0]
        poL_id = np.where(self.landmarkNames == "poL")[0][0]

        if (self.fiducialNode.GetNumberOfFiducials() <= zyoR_id) | (
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
        zyoR = [0, 0, 0]

        self.fiducialNode.GetNthFiducialPosition(poR_id, poR)
        self.fiducialNode.GetNthFiducialPosition(poL_id, poL)
        self.fiducialNode.GetNthFiducialPosition(zyoR_id, zyoR)
        mat = logic.getFrankfortAlignment(poR, poL, zyoR)

        self.transformNode.SetAndObserveMatrixTransformToParent(mat)

        self.resetViews()

        print("Frankfort Alignment right")

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

        self.transformNode.SetAndObserveMatrixTransformToParent(mat)

        self.resetViews()

        print("O-Se Alignment")

    def onONaAlignment(self):
        for i in range(0, self.fiducialNode.GetNumberOfControlPoints()):
            self.fiducialNode.SetNthFiducialLabel(i, self.landmarkNames[i])

        logic = LandmarkFlowLogic()

        o_id = np.where(self.landmarkNames == "o")[0][0]
        na_id = np.where(self.landmarkNames == "n")[0][0]
        poR_id = np.where(self.landmarkNames == "poR")[0][0]
        poL_id = np.where(self.landmarkNames == "poL")[0][0]

        if (self.fiducialNode.GetNumberOfFiducials() <= na_id) | (self.fiducialNode.GetNumberOfFiducials() <= o_id) | (
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

        self.transformNode.SetAndObserveMatrixTransformToParent(mat)

        self.resetViews()

        print("O-Na Alignment")

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
        logic = LandmarkFlowLogic()
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
            logic = LandmarkFlowLogic()
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

    def onImportVolume(self):
        logic = LandmarkFlowLogic()
        self.activeCellString = logic.getActiveCell()
        if bool(self.activeCellString):
            volumePath = os.path.join(self.imagedir, self.activeCellString)
            self.volumeNode = logic.runImport(volumePath)
            if bool(self.volumeNode):
                # self.startSegmentationButton.enabled = True
                self.activeRow = logic.getActiveCellRow()
                # self.updateStatus(self.activeRow, 'Processing') # TODO uncomment this

                # Set window/level of the volume to bone
                displayNode = self.volumeNode.GetDisplayNode()
                displayNode.AutoWindowLevelOff()
                displayNode.SetWindow(1000)
                displayNode.SetLevel(400)

                # center slice view
                slicer.util.resetSliceViews()

                # 3D render
                self.render3d(self.volumeNode)

                self.maskedVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode",
                                                                       "Temporary masked volume")
                self.maskedVolume.CopyContent(self.volumeNode)
                self.render3d(self.maskedVolume)
                self.turnOffRender(self.maskedVolume)

                # fiducials
                fiducialName = os.path.splitext(self.activeCellString)[0]
                fiducialName = os.path.splitext(fiducialName)[0]
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

                matrix = vtk.vtkMatrix4x4()
                matrix.Identity()
                transform = vtk.vtkTransform()
                transform.SetMatrix(matrix)
                self.transformNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLTransformNode', 'Alignment Transform')
                self.transformNode.SetAndObserveTransformToParent(transform)

                self.volumeNode.SetAndObserveTransformNodeID(self.transformNode.GetID())
                self.maskedVolume.SetAndObserveTransformNodeID(self.transformNode.GetID())
                self.fiducialNode.SetAndObserveTransformNodeID(self.transformNode.GetID())
                self.turnOnRender(self.volumeNode)

                self.enableButtons()

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
            for i in range(0, self.fiducialNode.GetNumberOfControlPoints()):
                self.fiducialNode.SetNthFiducialLabel(i, self.landmarkNames[i])

            fiducialName = os.path.splitext(self.activeCellString)[0]
            fiducialName = os.path.splitext(fiducialName)[0]
            fiducialOutput = os.path.join(self.landmarkdir, fiducialName + '.fcsv')
            if slicer.util.saveNode(self.fiducialNode, fiducialOutput):
                self.updateTableAndGUI("Landmark")
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
    def updateTableAndGUI(self, statusColumn, complete=True):
        if complete:
            self.updateStatus(self.activeRow, statusColumn, 'Complete')
        else:
            self.updateStatus(self.activeRow, statusColumn, 'Incomplete')
        # self.checkAndCleanup(self.activeRow)
        # clean up
        # self.startSegmentationButton.enabled = False
        # self.exportSegmentationButton.enabled = False

    def updateStatus(self, index, statusColumName, status_string):
        # refresh table from file, update the status column, and save
        name = self.fileTable.GetName()
        slicer.mrmlScene.RemoveNode(self.fileTable)
        self.fileTable = slicer.util.loadNodeFromFile(self.tablepath, 'TableFile')
        self.fileTable.SetLocked(True)
        self.fileTable.SetName(name)
        # logic = MandibleNerveFlowLogic()
        # logic.hideCompletedSamples(self.fileTable)
        statusColumn = self.fileTable.GetTable().GetColumnByName(statusColumName)
        statusColumn.SetValue(index - 1,
                              status_string + "," + getpass.getuser() + "," + str(date.today()))

        self.fileTable.GetTable().Modified()  # update table view
        slicer.util.saveNode(self.fileTable, self.tablepath)

    def checkAndCleanup(self, index):
        name = self.fileTable.GetName()
        slicer.mrmlScene.RemoveNode(self.fileTable)
        self.fileTable = slicer.util.loadNodeFromFile(self.tablepath, 'TableFile')
        self.fileTable.SetLocked(True)
        self.fileTable.SetName(name)

        if (self.fileTable.GetTable().GetColumnByName("Segmentation").GetValue(index - 1) is not ""):
            self.cleanup()

    def cleanup(self):

        if hasattr(self, 'fiducialNode'):
            slicer.mrmlScene.RemoveNode(self.fiducialNode)
        if hasattr(self, 'volumeNode'):
            slicer.mrmlScene.RemoveNode(self.volumeNode)
        if hasattr(self, 'maskedVolume'):
            slicer.mrmlScene.RemoveNode(self.maskedVolume)
        if hasattr(self, 'segmentationNode'):
            slicer.mrmlScene.RemoveNode(self.segmentationNode)
        if hasattr(self, 'labelMap'):
            slicer.mrmlScene.RemoveNode(self.labelMap)
        if hasattr(self, 'transformNode'):
            slicer.mrmlScene.RemoveNode(self.transformNode)
        if hasattr(self, 'cleaningSegmentation'):
            slicer.mrmlScene.RemoveNode(self.cleaningSegmentation)
        # if hasattr(self, 'segmentEditorNode'):
        #     slicer.mrmlScene.RemoveNode(self.segmentEditorNode)
        if hasattr(self, 'planeNode'):
            slicer.mrmlScene.RemoveNode(self.planeNode)

        self.headSegmentID = None
        self.skullSegmentId = None
        self.segmentationNode = None
        self.planeNode = None

        annotationROIs = slicer.mrmlScene.GetNodesByClass("vtkMRMLAnnotationROINode")
        for roi in annotationROIs:
            slicer.mrmlScene.RemoveNode(roi)

        shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
        shNode.RemoveItem(shNode.GetItemByName("Segments"))
        segments = slicer.mrmlScene.GetNodesByClass("vtkMRMLModelNode")
        for segment in segments:
            slicer.mrmlScene.RemoveNode(segment)

        vps = slicer.mrmlScene.GetNodesByClass("vtkMRMLVolumePropertyNode")
        for vp in vps:
            slicer.mrmlScene.RemoveNode(vp)

        self.disableButtons()

    def enableButtons(self):
        self.markIncompleteButton.enabled = True
        self.exportLandmarksButton.enabled = True
        self.boneWindow.enabled = True
        self.softTissueWindow.enabled = True
        self.boneRender.enabled = True
        self.boneRender2.enabled = True
        self.softTissueRender.enabled = True
        self.removeNoiseButton.enabled = True
        self.removeTubeButton.enabled = True
        self.originalVolumeButton.enabled = True
        self.frankfortAlignment.enabled = True
        self.frankfortAlignmentR.enabled = True
        self.oSeAlignment.enabled = True
        self.oNaAlignment.enabled = True
        self.skipButton.enabled = True
        self.importVolumeButton.enabled = False

        self.startSegmentationButton.enabled = True
        self.exportSegmentationButton.enabled = True

    def disableButtons(self):
        self.markIncompleteButton.enabled = False
        self.exportLandmarksButton.enabled = False
        self.boneWindow.enabled = False
        self.softTissueWindow.enabled = False
        self.boneRender.enabled = False
        self.boneRender2.enabled = False
        self.softTissueRender.enabled = False
        self.removeNoiseButton.enabled = False
        self.removeTubeButton.enabled = False
        self.originalVolumeButton.enabled = False
        self.frankfortAlignment.enabled = False
        self.frankfortAlignmentR.enabled = False
        self.oSeAlignment.enabled = False
        self.oNaAlignment.enabled = False
        self.skipButton.enabled = False
        self.importVolumeButton.enabled = True

        self.startSegmentationButton.enabled = False
        self.exportSegmentationButton.enabled = False

    def render3d(self, volumeNode):
        # 3D render volume
        volRenLogic = slicer.modules.volumerendering.logic()
        displayNode = volRenLogic.CreateDefaultVolumeRenderingNodes(volumeNode)
        # displayNode.SetVisibility(True)
        displayNode.GetVolumePropertyNode().Copy(self.boneVP2)

        displayNode.CroppingEnabledOn()
        # displayNode.GetROINode().GetDisplayNode().SetVisibility(True)
        volRenLogic.FitROIToVolume(displayNode)

        layoutManager = slicer.app.layoutManager()
        threeDWidget = layoutManager.threeDWidget(0)
        threeDView = threeDWidget.threeDView()
        threeDView.resetFocalPoint()
        threeDView.lookFromAxis(5)

    def turnOnRender(self, volumeNode):
        volRenLogic = slicer.modules.volumerendering.logic()
        displayNode = volRenLogic.GetFirstVolumeRenderingDisplayNode(volumeNode)
        displayNode.Visibility3DOn()
        displayNode.GetROINode().GetDisplayNode().SetVisibility(True)

    def turnOffRender(self, volumeNode):
        volRenLogic = slicer.modules.volumerendering.logic()
        displayNode = volRenLogic.GetFirstVolumeRenderingDisplayNode(volumeNode)
        displayNode.Visibility3DOff()
        displayNode.GetROINode().GetDisplayNode().SetVisibility(False)

    def resetViews(self):
        # Reset ROI
        volRenLogic = slicer.modules.volumerendering.logic()
        volRenLogic.FitROIToVolume(volRenLogic.GetFirstVolumeRenderingDisplayNode(self.volumeNode))
        volRenLogic.FitROIToVolume(volRenLogic.GetFirstVolumeRenderingDisplayNode(self.maskedVolume))

        # center view
        threeDView = slicer.app.layoutManager().threeDWidget(0).threeDView()
        threeDView.resetFocalPoint()
        threeDView.lookFromAxis(5)

        # center slice view
        slicer.util.resetSliceViews()


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

    def segmentSkull(self, segmentationNode, segmentEditorNode, segmentEditorWidget, volumeNode):

        segmentEditorWidget.setMRMLSegmentEditorNode(segmentEditorNode)
        segmentEditorWidget.setSegmentationNode(segmentationNode)
        segmentEditorWidget.setMasterVolumeNode(volumeNode)

        headSegmentID = segmentationNode.GetSegmentation().AddEmptySegment("head")
        segmentEditorNode.SetSelectedSegmentID(headSegmentID)
        segmentEditorWidget.setActiveEffectByName("Threshold")

        volumeScalarRange = volumeNode.GetImageData().GetScalarRange()

        effect = segmentEditorWidget.activeEffect()
        effect.setParameter("MinimumThreshold", str(-200))
        effect.setParameter("MaximumThreshold", str(volumeScalarRange[1]))
        effect.self().onApply()

        segmentEditorWidget.setActiveEffectByName("Islands")
        effect = segmentEditorWidget.activeEffect()
        effect.setParameterDefault("Operation", "KEEP_LARGEST_ISLAND")
        effect.self().onApply()

        skullSegmentID = segmentationNode.GetSegmentation().GetSegmentIdBySegmentName("Skull")
        segmentEditorNode.SetSelectedSegmentID(skullSegmentID)

        segmentEditorWidget.setActiveEffectByName("Threshold")
        effect = segmentEditorWidget.activeEffect()
        effect.setParameter("MinimumThreshold", str(243))
        effect.setParameter("MaximumThreshold", str(volumeScalarRange[1]))
        effect.self().onApply()

        segmentEditorWidget.setActiveEffectByName("Islands")
        effect = segmentEditorWidget.activeEffect()
        effect.setParameter("Operation", "REMOVE_SMALL_ISLANDS")
        effect.setParameter("MinimumSize", "1000")
        effect.self().onApply()

        segmentEditorWidget.setActiveEffectByName("Logical operators")
        effect = segmentEditorWidget.activeEffect()
        effect.setParameter("Operation", "INTERSECT")
        effect.setParameter("ModifierSegmentID", headSegmentID)
        effect.self().onApply()

        mandibleSegmentID = segmentationNode.GetSegmentation().GetSegmentIdBySegmentName("Intraop Material")
        segmentEditorNode.SetSelectedSegmentID(mandibleSegmentID)

        # segmentEditorWidget.setActiveEffectByName("Logical operators")
        # effect = segmentEditorWidget.activeEffect()
        # effect.setParameter("Operation", "COPY")
        # effect.setParameter("ModifierSegmentID", skullSegmentID)
        # effect.self().onApply()

        segmentationNode.GetDisplayNode().SetSegmentVisibility(skullSegmentID, False)
        segmentationNode.GetDisplayNode().SetSegmentVisibility(headSegmentID, False)

    def initializeSegmentation(self, masterVolumeNode):
        # Create segmentation
        segmentationName = masterVolumeNode.GetName()
        segmentationNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLSegmentationNode',
                                                              segmentationName)
        segmentationNode.CreateDefaultDisplayNodes()  # only needed for display
        segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(masterVolumeNode)
        segmentation = segmentationNode.GetSegmentation()
        # Add template segments
        # self.addNewSegment(segmentation, "Skull", (0,0,0.3))
        # self.addNewSegment(segmentation, "Mandible", (0,0,0.3))
        # self.addNewSegment(segmentation, "inf.alv.nerve.right", (0,0,0.3))
        # self.addNewSegment(segmentation, "inf.alv.nerve.left", (0,0,0.3))
        segmentID = segmentation.AddEmptySegment("Skull")
        segmentID = segmentation.AddEmptySegment("Intraop Material")

        return segmentationNode


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
