import os
import ast
import qt
import slicer
import vtk
from base import SliceTrackerLogicBase, SliceTrackerStep
from SlicerProstateUtils.helpers import SliceAnnotation
from SlicerProstateUtils.decorators import onModuleSelected
from plugins.targeting import SliceTrackerTargetingPlugin
from plugins.segmentation.manual import SliceTrackerManualSegmentationPlugin
from plugins.segmentation.automatic import SliceTrackerAutomaticSegmentationPlugin
from ..constants import SliceTrackerConstants


class SliceTrackerSegmentationStepLogic(SliceTrackerLogicBase):

  def __init__(self):
    super(SliceTrackerSegmentationStepLogic, self).__init__()

  def cleanup(self):
    pass


class SliceTrackerSegmentationStep(SliceTrackerStep):

  NAME = "Segmentation"
  LogicClass = SliceTrackerSegmentationStepLogic

  def __init__(self):
    self.modulePath = os.path.dirname(slicer.util.modulePath(self.MODULE_NAME)).replace(".py", "")
    super(SliceTrackerSegmentationStep, self).__init__()
    self.resetAndInitialize()

  def resetAndInitialize(self):
    self.session.retryMode = False

  def setupIcons(self):
    self.greenCheckIcon = self.createIcon('icon-greenCheck.png')

  def setup(self):
    self.setupTargetingPlugin()
    self.setupManualSegmentationPlugin()
    self.setupAutomaticSegmentationPlugin()
    self.setupFinishButton()

  def setupTargetingPlugin(self):
    self.targetingPlugin = SliceTrackerTargetingPlugin()
    self.targetingPlugin.addEventObserver(self.targetingPlugin.TargetingStartedEvent, self.onTargetingStarted)
    self.targetingPlugin.addEventObserver(self.targetingPlugin.TargetingFinishedEvent, self.onTargetingFinished)
    self.addPlugin(self.targetingPlugin)
    self.layout().addWidget(self.targetingPlugin)

  def setupManualSegmentationPlugin(self):
    self.manualSegmentationPlugin = SliceTrackerManualSegmentationPlugin()
    self.manualSegmentationPlugin.addEventObserver(self.manualSegmentationPlugin.SegmentationStartedEvent,
                                                   self.onSegmentationStarted)
    self.manualSegmentationPlugin.addEventObserver(self.manualSegmentationPlugin.SegmentationFinishedEvent,
                                                   self.onSegmentationFinished)
    self.addPlugin(self.manualSegmentationPlugin)
    self.layout().addWidget(self.manualSegmentationPlugin)

  def setupAutomaticSegmentationPlugin(self):
    self.automaticSegmentationPlugin = SliceTrackerAutomaticSegmentationPlugin()
    self.automaticSegmentationPlugin.addEventObserver(self.automaticSegmentationPlugin.SegmentationStartedEvent,
                                                      self.onSegmentationStarted)
    self.automaticSegmentationPlugin.addEventObserver(self.automaticSegmentationPlugin.SegmentationFinishedEvent,
                                                      self.onSegmentationFinished)
    self.addPlugin(self.automaticSegmentationPlugin)
    # self.layout().addWidget(self.automaticSegmentationPlugin)

  def setupFinishButton(self):
    iconSize = qt.QSize(24, 24)
    self.finishedSegmentationStepButton = self.createButton("Apply Registration", icon=self.greenCheckIcon,
                                                            iconSize=iconSize, toolTip="Run Registration.")
    self.finishedSegmentationStepButton.setFixedHeight(45)
    self.layout().addWidget(self.finishedSegmentationStepButton, 2, 0)

  def setupConnections(self):
    super(SliceTrackerSegmentationStep, self).setupConnections()
    self.finishedSegmentationStepButton.clicked.connect(self.onFinishedStep)

  @vtk.calldata_type(vtk.VTK_STRING)
  def onInitiateSegmentation(self, caller, event, callData):
    self.resetAndInitialize()
    self.session.retryMode = ast.literal_eval(callData)
    self.configureUIElements()
    if self.getSetting("COVER_PROSTATE") in self.session.currentSeries:
      if self.session.data.usePreopData:
        if self.session.retryMode:
          if not self.loadLatestCoverProstateResultData():
            self.loadInitialData()
        else:
          self.loadInitialData()
      else:
        self.session.movingVolume = self.session.currentSeriesVolume
    else:
      self.loadLatestCoverProstateResultData()
    self.active = True

  def configureUIElements(self):
    text = "Apply Registration"
    if self.getSetting("COVER_PROSTATE") in self.session.currentSeries and not self.session.data.usePreopData:
      text = "Finish"
    self.finishedSegmentationStepButton.text = text
    self.finishedSegmentationStepButton.setEnabled(1 if self.inputsAreSet() else 0)

  def loadInitialData(self):
    self.session.movingLabel = self.session.data.initialLabel
    self.session.movingVolume = self.session.data.initialVolume
    self.session.movingTargets = self.session.data.initialTargets

  def onActivation(self):
    self.finishedSegmentationStepButton.enabled = False
    self.session.fixedVolume = self.session.currentSeriesVolume
    if not self.session.fixedVolume:
      return
    super(SliceTrackerSegmentationStep, self).onActivation()

  def onDeactivation(self):
    super(SliceTrackerSegmentationStep, self).onDeactivation()

  @onModuleSelected(SliceTrackerStep.MODULE_NAME)
  def onLayoutChanged(self, layout=None):
    if self.layoutManager.layout == SliceTrackerConstants.LAYOUT_SIDE_BY_SIDE:
      self.setupSideBySideSegmentationView()
    elif self.layoutManager.layout in [SliceTrackerConstants.LAYOUT_FOUR_UP,
                                       SliceTrackerConstants.LAYOUT_RED_SLICE_ONLY]:
      self.removeMissingPreopDataAnnotation()
      self.setBackgroundToVolumeID(self.session.currentSeriesVolume.GetID(), clearLabels=False)

  def setupSideBySideSegmentationView(self):
    # TODO: red slice view should not be possible to set target
    coverProstate = self.session.data.getMostRecentApprovedCoverProstateRegistration()
    redVolume = coverProstate.volumes.fixed if self.session.retryMode and coverProstate else self.session.data.initialVolume
    redLabel = coverProstate.labels.fixed if self.session.retryMode and coverProstate else self.session.data.initialLabel

    if redVolume and redLabel:
      self.redCompositeNode.SetBackgroundVolumeID(redVolume.GetID())
      self.redCompositeNode.SetLabelVolumeID(redLabel.GetID())
      self.redCompositeNode.SetLabelOpacity(1)
    else:
      self.redCompositeNode.SetBackgroundVolumeID(None)
      self.redCompositeNode.SetLabelVolumeID(None)
      self.addMissingPreopDataAnnotation(self.redWidget)
    self.yellowCompositeNode.SetBackgroundVolumeID(self.session.currentSeriesVolume.GetID())
    self.setAxialOrientation()

    if redVolume and redLabel:
      self.redSliceNode.SetUseLabelOutline(True)
      self.redSliceNode.RotateToVolumePlane(redVolume)

  def removeMissingPreopDataAnnotation(self):
    self.segmentationNoPreopAnnotation = getattr(self, "segmentationNoPreopAnnotation", None)
    if self.segmentationNoPreopAnnotation:
      self.segmentationNoPreopAnnotation.remove()
      self.segmentationNoPreopAnnotation = None

  def addMissingPreopDataAnnotation(self, widget):
    self.removeMissingPreopDataAnnotation()
    self.segmentationNoPreopAnnotation = SliceAnnotation(widget, SliceTrackerConstants.MISSING_PREOP_ANNOTATION_TEXT,
                                                         opacity=0.7, color=(1, 0, 0))

  def loadLatestCoverProstateResultData(self):
    coverProstate = self.session.data.getMostRecentApprovedCoverProstateRegistration()
    if coverProstate:
      self.session.movingVolume = coverProstate.volumes.fixed
      self.session.movingLabel = coverProstate.labels.fixed
      self.session.movingTargets = coverProstate.targets.approved
      return True
    return False

  def onFinishedStep(self):
    self.manualSegmentationPlugin.disableEditorWidgetButton()
    self.session.data.clippingModelNode = self.manualSegmentationPlugin.clippingModelNode
    self.session.data.inputMarkupNode = self.manualSegmentationPlugin.inputMarkupNode
    if not self.session.data.usePreopData and not self.session.retryMode:
      self.createCoverProstateRegistrationResultManually()
    else:
      self.session.onInvokeRegistration(initial=True, retryMode=self.session.retryMode)

  def createCoverProstateRegistrationResultManually(self):
    fixedVolume = self.session.currentSeriesVolume
    result = self.session.generateNameAndCreateRegistrationResult(fixedVolume)
    approvedRegistrationType = "bSpline"
    result.targets.original = self.session.movingTargets
    targetName = str(result.seriesNumber) + '-TARGETS-' + approvedRegistrationType + result.suffix
    clone = self.logic.cloneFiducials(self.session.movingTargets, targetName)
    self.session.applyDefaultTargetDisplayNode(clone)
    result.setTargets(approvedRegistrationType, clone)
    result.volumes.fixed = fixedVolume
    result.labels.fixed = self.session.fixedLabel
    result.approve(approvedRegistrationType)

  def setupSessionObservers(self):
    super(SliceTrackerSegmentationStep, self).setupSessionObservers()
    self.session.addEventObserver(self.session.InitiateSegmentationEvent, self.onInitiateSegmentation)

  def removeSessionEventObservers(self):
    super(SliceTrackerSegmentationStep, self).removeSessionEventObservers()
    self.session.removeEventObserver(self.session.InitiateSegmentationEvent, self.onInitiateSegmentation)

  def onSegmentationStarted(self, caller, event):
    self.targetingPlugin.enabled = False
    self.finishedSegmentationStepButton.enabled = False

  @vtk.calldata_type(vtk.VTK_OBJECT)
  def onSegmentationFinished(self, caller, event, labelNode):
    _, suffix = self.session.getRegistrationResultNameAndGeneratedSuffix(self.session.currentSeries)
    labelNode.SetName(labelNode.GetName() + suffix)
    self.session.fixedLabel = labelNode
    if self.session.data.usePreopData or self.session.retryMode:
      self.setAxialOrientation()
    self.openSegmentationComparisonStep()
    self.finishedSegmentationStepButton.setEnabled(1 if self.inputsAreSet() else 0)

  def openSegmentationComparisonStep(self):
    self.removeMissingPreopDataAnnotation()
    self.targetingPlugin.enabled = True
    if self.session.data.usePreopData or self.session.retryMode:
      self.layoutManager.setLayout(SliceTrackerConstants.LAYOUT_SIDE_BY_SIDE)
      self.setupScreenForSegmentationComparison("red", self.session.movingVolume, self.session.movingLabel)
      self.setupScreenForSegmentationComparison("yellow", self.session.fixedVolume, self.session.fixedLabel)
      self.manualSegmentationPlugin.enableEditorWidgetButton()
      self.centerLabelsOnVisibleSliceWidgets()
    elif not self.session.movingTargets:
      self.targetingPlugin.onStartTargetingButtonClicked()
    else:
      for sliceNode in self._sliceNodes:
        sliceNode.SetUseLabelOutline(True)

  def setupScreenForSegmentationComparison(self, viewName, volume, label):
    compositeNode = getattr(self, viewName+"CompositeNode")
    compositeNode.SetReferenceBackgroundVolumeID(volume.GetID())
    compositeNode.SetLabelVolumeID(label.GetID())
    compositeNode.SetLabelOpacity(1)
    sliceNode = getattr(self, viewName+"SliceNode")
    sliceNode.SetOrientationToAxial()
    sliceNode.RotateToVolumePlane(volume)
    sliceNode.SetUseLabelOutline(True)

  def centerLabelsOnVisibleSliceWidgets(self):
    for widget in self.getAllVisibleWidgets():
      compositeNode = widget.mrmlSliceCompositeNode()
      sliceNode = widget.sliceLogic().GetSliceNode()
      labelID = compositeNode.GetLabelVolumeID()
      if labelID:
        label =  slicer.mrmlScene.GetNodeByID(labelID)
        centroid = self.logic.getCentroidForLabel(label, self.session.segmentedLabelValue)
        if centroid:
          sliceNode.JumpSliceByCentering(centroid[0], centroid[1], centroid[2])

  def inputsAreSet(self):
    if self.session.data.usePreopData:
      return self.session.movingVolume is not None and self.session.fixedVolume is not None and \
             self.session.movingLabel is not None and self.session.fixedLabel is not None and \
             self.session.movingTargets is not None
    else:
      return self.session.fixedVolume is not None and self.session.fixedLabel is not None \
             and self.session.movingTargets is not None

  def onTargetingStarted(self, caller, event):
    self.manualSegmentationPlugin.enabled = False

  def onTargetingFinished(self, caller, event):
    self.finishedSegmentationStepButton.setEnabled(1 if self.inputsAreSet() else 0)
    self.manualSegmentationPlugin.enabled = True