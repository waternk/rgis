# -*- coding: utf-8 -*-

"""
/***************************************************************************
Name                 : RiverGIS
Description          : HEC-RAS tools for QGIS
Date                 : January, 2015
copyright            : (C) 2015 by RiverGIS Group
email                : rpasiok@gmail.com

The content of this file is based on
- DB Manager by Giuseppe Sucameli (2011)
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

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from qgis.gui import QgsMessageBar
from qgis.utils import showPluginHelp

import psycopg2
import psycopg2.extras

import processing
from _ui_rivergis import Ui_RiverGIS

from hecras2dFunctions import *
from hecras1dFunctions import *
from isokpFunctions import *

from rasImportRasData import WorkerRasImportRasData


class RiverGIS(QMainWindow):

  def __init__(self, iface, parent=None):
    QMainWindow.__init__(self, parent) #, Qt.WindowStaysOnTopHint)
    self.setAttribute(Qt.WA_DeleteOnClose)
    self.ui = Ui_RiverGIS()
    self.ui.setupUi(self)
    self.conn = None

    # create status bar
    self.statusBar = QStatusBar(self)
    self.setStatusBar(self.statusBar)

    # MENU
    self.ui.actionRefreshConnections.triggered.connect(self.connChanged)
    self.ui.actionImportRiverFromIsokp.triggered.connect(self.importRiverIsokp)
    self.ui.actionRASCreate2dArea.triggered.connect(self.rasCreate2dArea)
    self.ui.actionRASPreview2DMesh.triggered.connect(self.rasPreview2DMesh)
    self.ui.actionRASSaveMeshPointsToHECRASGeometry.triggered.connect(self.rasSaveMeshPtsToHecrasGeo)
    self.ui.actionRASCreateRASLayers.triggered.connect(self.rasCreateRASLayers)
    self.ui.actionRASImportRasData.triggered.connect(self.rasImportRasDataStart)
    self.ui.actionRASWaterSurfaceGeneration.triggered.connect(self.rasWaterSurfaceGeneration)
    self.ui.actionRASFloodplainDelineation.triggered.connect(self.rasFloodplainDelineation)
    self.ui.actionAbout.triggered.connect(self.about)
    self.ui.actionHelpContents.triggered.connect(self.showRGisHelp)


    # toolbar
    self.ui.toolBar = QToolBar("Default", self)
    self.ui.toolBar.setObjectName("DB_ToolBar")
    self.ui.toolBar.addAction( self.ui.actionRefreshConnections )
    self.ui.toolBar.addAction( self.ui.actionImportRiverFromIsokp )
    self.ui.toolBar.addAction( self.ui.actionRASCreate2dArea )
    self.ui.toolBar.addAction( self.ui.actionRASImportRasData )
    self.ui.toolBar.addAction( self.ui.actionRASWaterSurfaceGeneration )
    self.ui.toolBar.addAction( self.ui.actionRASFloodplainDelineation )
    self.addToolBar(self.ui.toolBar)

    # self.ui.crsWidget.crsChanged.connect(self.updateDefaultCrs)
    self.ui.connsCbo.activated.connect(self.connChanged)
    self.ui.schemasCbo.activated.connect(self.schemaChanged)

    # Some info
    self.ui.textEdit.append('<b>Welcome to RiverGIS!</b><br><br>For some operations RiverGIS needs a <b>connection to a PostGIS database</b>. Please, choose a connection and schema from the above combo boxes.<br>')
    self.ui.textEdit.append('If you can\'t see any connection, create a new one from menu Layer > Add layer > Add PostGIS layers... <br><br>')
    self.ui.textEdit.append('<b>Loading HEC-RAS 2D results</b> requires a h5py Python package ( http://www.h5py.org ).<br><br>')
    self.iface = iface
    self.mapRegistry = QgsMapLayerRegistry.instance()
    self.rivergisPath = os.path.dirname(__file__)

    # restore the window state
    settings = QSettings()
    self.restoreGeometry( settings.value("/rivergis/mainWindow/geometry", QByteArray(), type=QByteArray ) )
    self.restoreState( settings.value("/rivergis/mainWindow/windowState", QByteArray(), type=QByteArray ) )

    # get PostGIS connections details and populate connections' combo
    self.connChanged()

  def closeEvent(self, e):
    self.unregisterAllActions()

    # save the window state
    settings = QSettings()
    settings.setValue( "/rivergis/mainWindow/windowState", self.saveState() )
    settings.setValue( "/rivergis/mainWindow/geometry", self.saveGeometry() )

    QMainWindow.closeEvent(self, e)

  def finishUi(self):
    pass
    
  def showHelp(self, page='index.html'):
    helpFile = 'file:///%s/help/%s' % (self.rivergisPath, page)
    QDesktopServices.openUrl(QUrl(helpFile))
  
  def showRGisHelp(self):
    self.showHelp('index.html')

  def updateDefaultCrs(self):
    self.crs = self.ui.crsWidget.crs()
    addInfo(self, '\nDefault CRS changed to: %s\n' % self.crs.authid() )

  # Database Functions

  def connChanged(self):
    s = QSettings()
    s.beginGroup('/PostgreSQL/connections')
    connsNames = s.childGroups()
    self.curConnName = self.ui.connsCbo.currentText()
    self.ui.connsCbo.clear()
    self.ui.connsCbo.addItem('')
    for conn in connsNames:
      self.ui.connsCbo.addItem(conn)
    try:
      i = connsNames.index(self.curConnName) + 1
    except ValueError:
      i = 0
    self.ui.connsCbo.setCurrentIndex(i)
    if self.ui.connsCbo.currentIndex() == 0:
      return
    connName = self.ui.connsCbo.currentText()
    s.endGroup()
    s.beginGroup('/PostgreSQL/connections/%s' % connName)
    host = s.value('host')
    port = s.value('port')
    database = s.value('database')
    user = s.value('username')
    passwd = s.value('password')
    sslmode = s.value('sslmode')
    connParams = "host='%s' port='%s' dbname='%s' user='%s' password='%s'" % \
                 (host,port,database,user,passwd)
    sslmodesList = [0,'disable', 'allow', 'prefer', 'require']
    if sslmode:
      connParams += " sslmode='%s'" % sslmodesList[sslmode]
    self.conn = psycopg2.connect(connParams)
    addInfo(self,'Current DB Connection is: %s' % self.curConnName)

    # refresh schemas combo
    schemaName = self.ui.schemasCbo.currentText()

    cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    qry = sql = u"SELECT nspname FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname != 'information_schema' ORDER BY nspname"
    cur.execute(qry)
    schemas = cur.fetchall()
    self.ui.schemasCbo.clear()
    self.ui.schemasCbo.addItem('')
    for schema in schemas:
      self.ui.schemasCbo.addItem(schema[0])
    schemaExists = self.ui.schemasCbo.findText(schemaName)
    if schemaExists:
      self.ui.schemasCbo.setCurrentIndex(schemaExists)
    self.schemaChanged()


  def schemaChanged(self):
    if not self.ui.schemasCbo.currentText() == '':
      self.schema = self.ui.schemasCbo.currentText()
      addInfo(self,'Current DB schema is: %s' % self.schema)



  def importRiverIsokp(self):
    from dlg_importRiverFromIsokp import *
    addInfo(self, '\n<b>Running Import River Data From ISOKP Database</b>' )
    if self.curConnName is None:
      addInfo(self, "No database selected or you are not connected to it.")
      return

    importData = DlgImportRiverFromIsokp(self)
    importData.exec_()


  # 1D HEC-RAS Geometry Functions

  def rasCreateRASLayers(self):
    addInfo(self, '\n<b>Creating HEC-RAS 1D Layers as PostGIS tables.</b>' )




  # 2D HEC-RAS Geometry Functions

  def rasCreate2dArea(self):
    db = self.curConnName
    if db is '':
      QMessageBox.warning(None, "2D Area", "Please, choose a connection and schema.")
      return
    else:
      ras2dCreate2dArea(self)

  def rasPreview2DMesh(self):
    ras2dPreviewMesh(self)

  def rasSaveMeshPtsToHecrasGeo(self):
      ras2dSaveMeshPtsToGeometry(self)


  # RAS Mapping function

  def rasImportRasDataStart(self):
    messageBar = self.iface.messageBar().createMessage('Loading max water surface elevation...', )
    progressBar = QProgressBar()
    progressBar.setAlignment(Qt.AlignLeft|Qt.AlignVCenter)
    cancelButton = QPushButton()
    cancelButton.setText('Cancel')
    messageBar.layout().addWidget(progressBar)
    messageBar.layout().addWidget(cancelButton)
    self.iface.messageBar().pushWidget(messageBar, self.iface.messageBar().INFO)
    self.messageBar = messageBar
    self.workerWselHecRas = WorkerRasImportRasData(self)
    cancelButton.clicked.connect(self.workerWselHecRas.kill)

    thread = QThread()
    self.workerWselHecRas.moveToThread(thread)
    self.workerWselHecRas.finished.connect(self.rasImportRasDataFinish)
    self.workerWselHecRas.error.connect(self.loadWselError)
    self.workerWselHecRas.progress.connect(progressBar.setValue)
    thread.started.connect(self.workerWselHecRas.run)

    thread.start()
    self.threadWselHecRas = thread


  def rasImportRasDataFinish(self, res):
      if not res == None:
        # processing.load(res['OUTPUT_LAYER'], 'WSEL_temp_points')
        # processing.load(res.dataProvider().dataSourceUri(), 'WSEL_temp_points')
        processing.load(res, 'WSEL_temp_points')
      else:
        addInfo(self, 'Loading max WSEL failed or was cancelled, check the log...')
      self.iface.messageBar().popWidget(self.messageBar)
      self.workerWselHecRas.deleteLater()
      self.threadWselHecRas.quit()
      self.threadWselHecRas.wait()
      self.threadWselHecRas.deleteLater()

  def rasWaterSurfaceGeneration(self):
    from dlg_rasWaterSurfaceGeneration import *
    addInfo(self, '<br><b>Running Create Water Surface Raster</b>' )
    dlg = DlgRasWaterSurfaceGeneration(self)
    dlg.exec_()

  def loadWselError(self, e, exception_string):
    addInfo(self, 'Thread loading WSEL raised an exception:{}'.format(exception_string))
    QgsMessageLog.logMessage('Thread loading WSEL raised an exception:{}\n'.format(exception_string), level=QgsMessageLog.CRITICAL)
    
  def rasFloodplainDelineation(self):
    from dlg_rasFloodplainDelineation import *
    addInfo(self, '\n<b>Running floodplain delineation.</b>' )
    dialog = DlgRasFloodplainDelineation(self)
    dialog.exec_()

  def about(self):
    self.showHelp('index.html')


  def registerAction(self, action, menuName, callback=None):
    pass

  def invokeCallback(self, callback, params=None):
    """ Call a method passing the selected item in the database tree,
            the sender (usually a QAction), the plugin mainWindow and
            optionally additional parameters.

            This method takes care to override and restore the cursor,
            but also catches exceptions and displays the error dialog.
    """
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
      if params is None:
        callback( self.tree.currentItem(), self.sender(), self )
      else:
        callback( self.tree.currentItem(), self.sender(), self, *params )

    except BaseError, e:
      # catch database errors and display the error dialog
      DlgDbError.showError(e, self)
      return

    finally:
            QApplication.restoreOverrideCursor()

  def unregisterAction(self, action, menuName):
    if not hasattr(self, '_registeredDbActions'):
      return

    if menuName == None or menuName == "":
      self.removeAction( action )

      if self._registeredDbActions.has_key(menuName):
        if self._registeredDbActions[menuName].count( action ) > 0:
          self._registeredDbActions[menuName].remove( action )

      action.deleteLater()
      return True

    for a in self.menuBar.actions():
      if not a.menu() or a.menu().title() != menuName:
        continue

      menu = a.menu()
      menuActions = menu.actions()

      menu.removeAction( action )
      if menu.isEmpty():  # hide the menu
        a.setVisible(False)

      if self._registeredDbActions.has_key(menuName):
        if self._registeredDbActions[menuName].count( action ) > 0:
          self._registeredDbActions[menuName].remove( action )

        # hide the placeholder if there're no other registered actions
        if len(self._registeredDbActions[menuName]) <= 0:
          for i in range(len(menuActions)):
            if menuActions[i].isSeparator() and menuActions[i].objectName().endswith("_placeholder"):
              menuActions[i].setVisible(False)
              break

      action.deleteLater()
      return True

    return False

  def unregisterAllActions(self):
    if not hasattr(self, '_registeredDbActions'):
      return

    for menuName in self._registeredDbActions:
      for action in list(self._registeredDbActions[menuName]):
        self.unregisterAction( action, menuName )
    del self._registeredDbActions

  def createPgFunctionCreateIndexIfNotExists(self):
      connParams = "dbname = '%s' user = '%s' host = '%s' password = '%s'" % (self.dbname,self.user,self.host,self.passwd)
      conn = psycopg2.connect(connParams)
      cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
      qry = '''CREATE OR REPLACE FUNCTION create_st_index_if_not_exists
        (schema text, t_name text) RETURNS void AS $$
      DECLARE
        full_index_name varchar;
      BEGIN
      full_index_name = t_name || '_' || 'geom_idx';
      IF NOT EXISTS (
          SELECT 1
          FROM   pg_class c
          JOIN   pg_namespace n ON n.oid = c.relnamespace
          WHERE  c.relname = full_index_name
          AND    n.nspname = schema
          ) THEN

          execute 'CREATE INDEX ' || full_index_name || ' ON ' || schema || '.' || t_name || ' USING GIST (geom)';
      END IF;
      END
      $$
      LANGUAGE plpgsql VOLATILE;'''
      cur.execute(qry)
      conn.commit()