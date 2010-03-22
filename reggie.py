#!/usr/bin/python
# -*- coding: latin-1 -*-

# Reggie! - New Super Mario Bros. Wii Level Editor
# Copyright (C) 2009-2010 Treeki, Tempus

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import archive
import lz77
import os.path
import pickle
import sprites
import struct
import sys
import time
import warnings

from ctypes import create_string_buffer
from PyQt4 import QtCore, QtGui
from xml.dom import minidom

ReggieID = 'Reggie r1 by Treeki, Tempus'

# enable path support
# disabled in the public builds because it's
# almost completely unimplemented right now
EnablePaths = False

# pre-Qt4.6 compatibility
QtCompatVersion = QtCore.QT_VERSION

if QtCompatVersion < 0x40600 or not hasattr(QtGui.QGraphicsItem, 'ItemSendsGeometryChanges'):
    # enables itemChange being called on QGraphicsItem
    QtGui.QGraphicsItem.ItemSendsGeometryChanges = QtGui.QGraphicsItem.GraphicsItemFlag(0x800)

# use psyco for optimisation if available
try:
    import psyco
    HavePsyco = True
except ImportError:
    HavePsyco = False

# use nsmblib if possible
try:
    import nsmblib
    HaveNSMBLib = True
except ImportError:
    HaveNSMBLib = False


app = None
mainWindow = None
settings = None

gamePath = None

def module_path():
    """This will get us the program's directory, even if we are frozen using py2exe"""
    if hasattr(sys, 'frozen'):
        return os.path.dirname(sys.executable)
    if __name__ == '__main__':
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    return None

def IsNSMBLevel(filename):
    """Does some basic checks to confirm a file is a NSMB level"""
    if not os.path.isfile(filename): return False
    f = open(filename, 'rb')
    data = f.read()
    
    if not data.startswith('U\xAA8-'):
        return False
    
    if 'course\0' not in data and 'course1.bin\0' not in data and '\0\0\0\x80' not in data:
        return False
    
    return True

def FilesAreMissing():
    """Checks to see if any of the required files for Reggie are missing"""
    
    if not os.path.isdir('reggiedata'):
        QtGui.QMessageBox.warning(None, 'Error',  'Sorry, you seem to be missing the required data files for Reggie! to work. Please redownload your copy of the editor.')
        return True
    
    required = ['entrances.png', 'entrancetypes.txt', 'icon.png', 'levelnames.txt', 'overrides.png',
                'spritedata.xml', 'tilesets.txt', 'bga/000A.png', 'bga.txt', 'bgb/000A.png', 'bgb.txt',
                'about.html', 'spritecategories.xml']
    
    missing = []
    
    for check in required:
        if not os.path.isfile('reggiedata/' + check):
            missing.append(check)
    
    if len(missing) > 0:
        QtGui.QMessageBox.warning(None, 'Error',  'Sorry, you seem to be missing some of the required data files for Reggie! to work. Please redownload your copy of the editor. These are the files you are missing: ' + ', '.join(missing))
        return True
    
    return False


def GetIcon(name):
    """Helper function to grab a specific icon"""
    return QtGui.QIcon('reggiedata/icon_%s.png' % name)


def SetGamePath(newpath):
    """Sets the NSMBWii game path"""
    
    global gamePath
    
    # you know what's fun?
    # isValidGamePath crashes in os.path.join if QString is used..
    # so we must change it to a Python string manually
    gamePath = unicode(newpath)


def isValidGamePath(check='ug'):
    """Checks to see if the path for NSMBWii contains a valid game"""
    if check == 'ug': check = gamePath
    
    if check == None or check == '': return False
    if not os.path.isdir(check): return False
    if not os.path.isdir(os.path.join(check, 'Texture')): return False
    if not os.path.isfile(os.path.join(check, '01-01.arc')): return False
    
    return True



LevelNames = None
def LoadLevelNames():
    """Ensures that the level name info is loaded"""
    global LevelNames
    if LevelNames != None: return
    
    f = open('reggiedata/levelnames.txt')
    raw = [x.strip() for x in f.readlines()]
    f.close()
    
    LevelNames = []
    CurrentWorldName = None
    CurrentWorld = None
    
    for line in raw:
        if line == '': continue
        if line.startswith('-'):
            if CurrentWorld != None:
                LevelNames.append((CurrentWorldName,CurrentWorld))
            
            CurrentWorldName = line[1:]
            CurrentWorld = []
        else:
            d = line.split('|')
            CurrentWorld.append((d[0], d[1]))
    
    if CurrentWorld != None:
        LevelNames.append((CurrentWorldName,CurrentWorld))


TilesetNames = None
def LoadTilesetNames():
    """Ensures that the tileset name info is loaded"""
    global TilesetNames
    if TilesetNames != None: return
    
    f = open('reggiedata/tilesets.txt')
    raw = [x.strip() for x in f.readlines()]
    f.close()
    
    TilesetNames = []
    StandardSuite = []
    StageSuite = []
    BackgroundSuite = []
    InteractiveSuite = []
    
    for line in raw:
        if line.startswith('Pa0'):
            w = line.split('=')
            StandardSuite.append((w[0], w[1]))
        if line.startswith('Pa1'):
            w = line.split('=')
            StageSuite.append((w[0], w[1]))
        if line.startswith('Pa2'):
            w = line.split('=')
            BackgroundSuite.append((w[0], w[1]))
        if line.startswith('Pa3'):
            w = line.split('=')
            InteractiveSuite.append((w[0], w[1]))
    TilesetNames.append(StandardSuite)
    TilesetNames.append(StageSuite)
    TilesetNames.append(BackgroundSuite)
    TilesetNames.append(InteractiveSuite)


ObjDesc = None
def LoadObjDescriptions():
    """Ensures that the object description is loaded"""
    global ObjDesc
    if ObjDesc != None: return
    
    f = open('reggiedata/ts1_descriptions.txt')
    raw = [x.strip() for x in f.readlines()]
    f.close()
    
    ObjDesc = {}
    for line in raw:
        w = line.split('=')
        ObjDesc[int(w[0])] = w[1]


BgANames = None
def LoadBgANames():
    """Ensures that the background name info is loaded"""
    global BgANames
    if BgANames != None: return
    
    f = open('reggiedata/bga.txt')
    raw = [x.strip() for x in f.readlines()]
    f.close()
    
    BgANames = []

    for line in raw:
        w = line.split('=')
        BgANames.append([w[0], w[1]])


BgBNames = None
def LoadBgBNames():
    """Ensures that the background name info is loaded"""
    global BgBNames
    if BgBNames != None: return
    
    f = open('reggiedata/bgb.txt')
    raw = [x.strip() for x in f.readlines()]
    f.close()
    
    BgBNames = []

    for line in raw:
        w = line.split('=')
        BgBNames.append([w[0], w[1]])


        

BgScrollRates = [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0, 0.0, 1.2, 1.5, 2.0, 4.0]
BgScrollRateStrings = ['None', '0.125x', '0.25x', '0.375x', '0.5x', '0.625x', '0.75x', '0.875x', '1x', 'None', '1.2x', '1.5x', '2x', '4x']

ZoneThemeValues = [
    'Overworld', 'Underground', 'Underwater', 'Lava/Volcano [reddish]',
    'Desert', 'Beach*', 'Forest*', 'Snow Overworld*',
    'Sky/Bonus*', 'Mountains*', 'Tower', 'Castle',
    'Ghost House', 'River Cave', 'Ghost House Exit', 'Underwater Cave',
    'Desert Cave', 'Icy Cave*', 'Lava/Volcano', 'Final Battle',
    'World 8 Castle', 'World 8 Doomship*', 'Lit Tower'
]

ZoneTerrainThemeValues = [
    'Normal/Overworld', 'Underground', 'Underwater', 'Lava/Volcano',
]

Sprites = None
SpriteCategories = None

class SpriteDefinition():
    """Stores and manages the data info for a specific sprite"""
    
    class ListPropertyModel(QtCore.QAbstractListModel):
        """Contains all the possible values for a list property on a sprite"""
        
        def __init__(self, entries, existingLookup, max):
            """Constructor"""
            QtCore.QAbstractListModel.__init__(self)
            self.entries = entries
            self.existingLookup = existingLookup
            self.max = max
        
        def rowCount(self, parent=None):
            """Required by Qt"""
            #return self.max
            return len(self.entries)
        
        def data(self, index, role=QtCore.Qt.DisplayRole):
            """Get what we have for a specific row"""
            if not index.isValid(): return None
            n = index.row()
            if n < 0: return None
            #if n >= self.max: return None
            if n >= len(self.entries): return None
            
            if role == QtCore.Qt.DisplayRole:
                #entries = self.entries
                #if entries.has_key(n):
                #    return '%d: %s' % (n, entries[n])
                #else:
                #    return '%d: <unknown/unused>' % n
                return '%d: %s' % self.entries[n]
            
            return None
    
    
    def loadFrom(self, elem):
        """Loads in all the field data from an XML node"""
        self.fields = []
        fields = self.fields
        
        for field in elem.childNodes:
            if field.nodeType != field.ELEMENT_NODE: continue
            
            attribs = field.attributes
            
            if attribs.has_key('comment'):
                comment = '<b>%s</b>: %s' % (attribs['title'].nodeValue, attribs['comment'].nodeValue)
            else:
                comment = None
            
            if field.nodeName == 'checkbox':
                # parameters: title, nybble, mask, comment
                snybble = attribs['nybble'].nodeValue
                if '-' not in snybble:
                    nybble = int(snybble) - 1
                else:
                    getit = snybble.split('-')
                    nybble = (int(getit[0]) - 1, int(getit[1]))
                
                fields.append((0, attribs['title'].nodeValue, nybble, int(attribs['mask'].nodeValue) if attribs.has_key('mask') else 1, comment))
            elif field.nodeName == 'list':
                # parameters: title, nybble, model, comment
                snybble = attribs['nybble'].nodeValue
                if '-' not in snybble:
                    nybble = int(snybble) - 1
                    max = 16
                else:
                    getit = snybble.split('-')
                    nybble = (int(getit[0]) - 1, int(getit[1]))
                    max = (16 << ((nybble[1] - nybble[0] - 1) * 4))
                
                entries = []
                existing = [None for i in xrange(max)]
                for e in field.childNodes:
                    if e.nodeType != e.ELEMENT_NODE: continue
                    if e.nodeName != 'entry': continue
                    
                    i = int(e.attributes['value'].nodeValue)
                    entries.append((i, e.childNodes[0].nodeValue))
                    existing[i] = True
                
                fields.append((1, attribs['title'].nodeValue, nybble, SpriteDefinition.ListPropertyModel(entries, existing, max), comment))
            elif field.nodeName == 'value':
                # parameters: title, nybble, max, comment
                snybble = attribs['nybble'].nodeValue
                
                # if it's 5-12 skip it
                # fixes tobias's crashy "unknown values"
                if snybble == '5-12': continue
                
                if '-' not in snybble:
                    nybble = int(snybble) - 1
                    max = 16
                else:
                    getit = snybble.split('-')
                    nybble = (int(getit[0]) - 1, int(getit[1]))
                    max = (16 << ((nybble[1] - nybble[0] - 1) * 4))
                
                fields.append((2, attribs['title'].nodeValue, nybble, max, comment))


def LoadSpriteData():
    """Ensures that the sprite data info is loaded"""
    global Sprites
    if Sprites != None: return
    
    Sprites = [None] * 483
    
    sd = minidom.parse('reggiedata/spritedata.xml')
    root = sd.documentElement
    errors = []
    errortext = []
    
    for sprite in root.childNodes:
        if sprite.nodeType != sprite.ELEMENT_NODE: continue
        if sprite.nodeName != 'sprite': continue
        
        spriteid = int(sprite.attributes['id'].nodeValue)
        spritename = str(sprite.attributes['name'].nodeValue)
        notes = None
        
        if sprite.attributes.has_key('notes'):
            notes = '<b>Sprite Notes:</b> ' + sprite.attributes['notes'].nodeValue
        
        sdef = SpriteDefinition()
        sdef.id = spriteid
        sdef.name = spritename
        sdef.notes = notes
        try:
            sdef.loadFrom(sprite)
        except Exception, e:
            errors.append(str(spriteid))
            errortext.append(str(e))
        
        Sprites[spriteid] = sdef
    
    sd.unlink()
    
    if len(errors) > 0:
        QtGui.QMessageBox.warning(None, 'Warning',  'The sprite data file didn\'t load correctly. The following sprites have incorrect and/or broken data in them, and may not be editable correctly in the editor: ' + (', '.join(errors)), QtGui.QMessageBox.Ok)
        QtGui.QMessageBox.warning(None, 'Errors', repr(errortext))


def LoadSpriteCategories():
    """Ensures that the sprite category info is loaded"""
    global Sprites, SpriteCategories
    if SpriteCategories != None: return
    
    SpriteCategories = []
    
    sd = minidom.parse('reggiedata/spritecategories.xml')
    root = sd.documentElement
    
    CurrentView = None
    for view in root.childNodes:
        if view.nodeType != view.ELEMENT_NODE: continue
        if view.nodeName != 'view': continue
        
        viewname = str(view.attributes['name'].nodeValue)
        CurrentView = []
        SpriteCategories.append((viewname, CurrentView, []))
        
        CurrentCategory = None
        for category in view.childNodes:
            if category.nodeType != category.ELEMENT_NODE: continue
            if category.nodeName != 'category': continue
            
            catname = str(category.attributes['name'].nodeValue)
            CurrentCategory = []
            CurrentView.append((catname, CurrentCategory))
            
            for attach in category.childNodes:
                if attach.nodeType != attach.ELEMENT_NODE: continue
                if attach.nodeName != 'attach': continue
                
                sprite = attach.attributes['sprite'].nodeValue
                if '-' not in sprite:
                    CurrentCategory.append(int(sprite))
                else:
                    x = sprite.split('-')
                    for i in xrange(int(x[0]), int(x[1])+1):
                        CurrentCategory.append(i)
    
    sd.unlink()
    
    SpriteCategories.append(('Search', [('Search Results', range(0,483))], []))
    SpriteCategories[-1][1][0][1].append(9999) # "no results" special case


EntranceTypeNames = None
def LoadEntranceNames():
    """Ensures that the entrance names are loaded"""
    global EntranceTypeNames
    if EntranceTypeNames != None: return
    
    getit = open('reggiedata/entrancetypes.txt', 'r')
    EntranceTypeNames = [x.strip() for x in getit.readlines()]


class ChooseLevelNameDialog(QtGui.QDialog):
    """Dialog which lets you choose a level from a list"""
    
    def __init__(self):
        """Creates and initialises the dialog"""
        QtGui.QDialog.__init__(self)
        self.setWindowTitle('Choose Level')
        LoadLevelNames()
        self.currentlevel = None
        
        # create the tree
        tree = QtGui.QTreeWidget()
        tree.setColumnCount(1)
        tree.setHeaderHidden(True)
        tree.setIndentation(16)
        tree.currentItemChanged.connect(self.HandleItemChange)
        tree.itemActivated.connect(self.HandleItemActivated)
        
        for worldname, world in LevelNames:
            wnode = QtGui.QTreeWidgetItem()
            wnode.setText(0, worldname)
            
            for levelname, level in world:
                lnode = QtGui.QTreeWidgetItem()
                lnode.setText(0, levelname)
                lnode.setData(0, QtCore.Qt.UserRole, level)
                lnode.setToolTip(0, level + '.arc')
                wnode.addChild(lnode)
            
            tree.addTopLevelItem(wnode)
        
        self.leveltree = tree
        
        # create the buttons
        self.buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        self.buttonBox.button(QtGui.QDialogButtonBox.Ok).setEnabled(False)
        
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        
        # create the layout
        layout = QtGui.QVBoxLayout()
        layout.addWidget(self.leveltree)
        layout.addWidget(self.buttonBox)
        
        self.setLayout(layout)
        self.layout = layout
    
    @QtCore.pyqtSlot(QtGui.QTreeWidgetItem, QtGui.QTreeWidgetItem)
    def HandleItemChange(self, current, previous):
        """Catch the selected level and enable/disable OK button as needed"""
        self.currentlevel = current.data(0, QtCore.Qt.UserRole)
        if self.currentlevel == None:
            self.buttonBox.button(QtGui.QDialogButtonBox.Ok).setEnabled(False)
        else:
            self.buttonBox.button(QtGui.QDialogButtonBox.Ok).setEnabled(True)
            self.currentlevel = str(self.currentlevel.toPyObject())
    
    
    @QtCore.pyqtSlot(QtGui.QTreeWidgetItem, int)
    def HandleItemActivated(self, item, column):
        """Handle a doubleclick on a level"""
        self.currentlevel = item.data(0, QtCore.Qt.UserRole)
        if self.currentlevel != None:
            self.currentlevel = str(self.currentlevel.toPyObject())
            self.accept()


Tiles = None # 256 tiles per tileset, plus 64 for each type of override
Overrides = None # 320 tiles, this is put into Tiles usually
TileBehaviours = None
ObjectDefinitions = None # 4 tilesets

class ObjectDef():
    """Class for the object definitions"""
    
    def __init__(self):
        """Constructor"""
        self.width = 0
        self.height = 0
        self.rows = []
    
    def load(self, source, offset, tileoffset):
        """Load an object definition"""
        i = offset
        row = []
        
        while True:
            cbyte = ord(source[i])
            
            if cbyte == 0xFE:
                self.rows.append(row)
                i += 1
                row = []
            elif cbyte == 0xFF:
                return
            elif (cbyte & 0x80) != 0:
                row.append((cbyte,))
                i += 1
            else:
                extra = ord(source[i+2])
                tile = (cbyte, ord(source[i+1]) | ((extra & 3) << 8), extra >> 2)
                row.append(tile)
                i += 3


def RenderObject(tileset, objnum, width, height, fullslope=False):
    """Render a tileset object into an array"""
    # allocate an array
    dest = []
    for i in xrange(height): dest.append([0]*width)
    
    # ignore non-existent objects
    tileset_defs = ObjectDefinitions[tileset]
    if tileset_defs == None: return dest
    obj = tileset_defs[objnum]
    if obj == None: return dest
    if len(obj.rows) == 0: return dest
    
    # diagonal objects are rendered differently
    if (obj.rows[0][0][0] & 0x80) != 0:
        RenderDiagonalObject(dest, obj, width, height, fullslope)
    else:
        # standard object
        repeatFound = False
        beforeRepeat = []
        inRepeat = []
        afterRepeat = []
        
        for row in obj.rows:
            if len(row) == 0: continue
            if (row[0][0] & 2) != 0:
                repeatFound = True
                inRepeat.append(row)
            else:
                if repeatFound:
                    afterRepeat.append(row)
                else:
                    beforeRepeat.append(row)
        
        bc = len(beforeRepeat); ic = len(inRepeat); ac = len(afterRepeat)
        if ic == 0:
            for y in xrange(height):
                RenderStandardRow(dest[y], beforeRepeat[y % bc], y, width)
        else:
            afterthreshold = height - ac - 1
            for y in xrange(height):
                if y < bc:
                    RenderStandardRow(dest[y], beforeRepeat[y], y, width)
                elif y > afterthreshold:
                    RenderStandardRow(dest[y], afterRepeat[y - height + ac], y, width)
                else:
                    RenderStandardRow(dest[y], inRepeat[(y - bc) % ic], y, width)
    
    return dest


def RenderStandardRow(dest, row, y, width):
    """Render a row from an object"""
    repeatFound = False
    beforeRepeat = []
    inRepeat = []
    afterRepeat = []
    
    for tile in row:
        if (tile[0] & 1) != 0:
            repeatFound = True
            inRepeat.append(tile)
        else:
            if repeatFound:
                afterRepeat.append(tile)
            else:
                beforeRepeat.append(tile)
    
    bc = len(beforeRepeat); ic = len(inRepeat); ac = len(afterRepeat)
    if ic == 0:
        for x in xrange(width):
            dest[x] = beforeRepeat[x % bc][1]
    else:
        afterthreshold = width - ac - 1
        for x in xrange(width):
            if x < bc:
                dest[x] = beforeRepeat[x][1]
            elif x > afterthreshold:
                dest[x] = afterRepeat[x - width + ac][1]
            else:
                dest[x] = inRepeat[(x - bc) % ic][1]


def RenderDiagonalObject(dest, obj, width, height, fullslope):
    """Render a diagonal object"""
    # set all to empty tiles
    for row in dest:
        for x in xrange(width):
            row[x] = -1
    
    # get sections
    mainBlock,subBlock = GetSlopeSections(obj)
    cbyte = obj.rows[0][0][0]
    
    # get direction
    goLeft = ((cbyte & 1) != 0)
    goDown = ((cbyte & 2) != 0)
    
    # base the amount to draw by seeing how much we can fit in each direction
    if fullslope:
        drawAmount = max(height // len(mainBlock), width // len(mainBlock[0]))
    else:
        drawAmount = min(height // len(mainBlock), width // len(mainBlock[0]))
    
    # if it's not goingLeft and not goingDown:
    if not goLeft and not goDown:
        # slope going from SW => NE
        # start off at the bottom left
        x = 0
        y = height - len(mainBlock) - (0 if subBlock == None else len(subBlock))
        xi = len(mainBlock[0])
        yi = -len(mainBlock)
        
    # ... and if it's goingLeft and not goingDown:
    elif goLeft and not goDown:
        # slope going from SE => NW
        # start off at the top left
        x = 0
        y = 0
        xi = len(mainBlock[0])
        yi = len(mainBlock)
        
    # ... and if it's not goingLeft but it's goingDown:
    elif not goLeft and goDown:
        # slope going from NW => SE
        # start off at the top left
        x = 0
        y = (0 if subBlock == None else len(subBlock))
        xi = len(mainBlock[0])
        yi = len(mainBlock)
        
    # ... and finally, if it's goingLeft and goingDown:
    else:
        # slope going from SW => NE
        # start off at the bottom left
        x = 0
        y = height - len(mainBlock)
        xi = len(mainBlock[0])
        yi = -len(mainBlock)
    
    
    # finally draw it
    for i in xrange(drawAmount):
        PutObjectArray(dest, x, y, mainBlock, width, height)
        if subBlock != None:
            xb = x
            if goLeft: xb = x + len(mainBlock[0]) - len(subBlock[0])
            if goDown:
                PutObjectArray(dest, xb, y - len(subBlock), subBlock, width, height)
            else:
                PutObjectArray(dest, xb, y + len(mainBlock), subBlock, width, height)
        x += xi
        y += yi


def PutObjectArray(dest, xo, yo, block, width, height):
    """Places a tile array into an object"""
    #for y in xrange(yo,min(yo+len(block),height)):
    for y in xrange(yo,yo+len(block)):
        if y < 0: continue
        if y >= height: continue
        drow = dest[y]
        srow = block[y-yo]
        #for x in xrange(xo,min(xo+len(srow),width)):
        for x in xrange(xo,xo+len(srow)):
            if x < 0: continue
            if x >= width: continue
            drow[x] = srow[x-xo][1]


def GetSlopeSections(obj):
    """Sorts the slope data into sections"""
    sections = []
    currentSection = None
    
    for row in obj.rows:
        if len(row) > 0 and (row[0][0] & 0x80) != 0: # begin new section
            if currentSection != None:
                sections.append(CreateSection(currentSection))
            currentSection = []
        currentSection.append(row)
    
    if currentSection != None: # end last section
        sections.append(CreateSection(currentSection))
    
    if len(sections) == 1:
        return (sections[0],None)
    else:
        return (sections[0],sections[1])


def CreateSection(rows):
    """Create a slope section"""
    # calculate width
    width = 0
    for row in rows:
        thiswidth = CountTiles(row)
        if width < thiswidth: width = thiswidth
    
    # create the section
    section = []
    for row in rows:
        drow = [0] * width
        x = 0
        for tile in row:
            if (tile[0] & 0x80) == 0:
                drow[x] = tile
                x += 1
        section.append(drow)
    
    return section


def CountTiles(row):
    """Counts the amount of real tiles in an object row"""
    res = 0
    for tile in row:
        if (tile[0] & 0x80) == 0:
            res += 1
    return res


def CreateTilesets():
    """Blank out the tileset arrays"""
    global Tiles, TileBehaviours, ObjectDefinitions
    
    Tiles = [None]*1024
    Tiles += Overrides
    #TileBehaviours = [0]*1024
    ObjectDefinitions = [None]*4
    sprites.Tiles = Tiles


def LoadTileset(idx, name):
    try:
        return _LoadTileset(idx, name)
    except:
        QtGui.QMessageBox.warning(None, 'Error',  'An error occurred while trying to load %s.arc. Check your Texture folder to make sure it is complete and not corrupted. The editor may run in a broken state or crash after this.' % name)
        return False


def _LoadTileset(idx, name):
    """Load in a tileset into a specific slot"""
    # read the archive
    arcname = os.path.join(gamePath, 'Texture', name+'.arc')
    
    if not os.path.isfile(arcname):
        QtGui.QMessageBox.warning(None, 'Error',  'Cannot find the required tileset file %s.arc for this level. Check your Texture folder and make sure it contains the required file.' % name)
        return False
    
    arcf = open(arcname,'rb')
    arcdata = arcf.read()
    arcf.close()
    
    arc = archive.U8()
    arc._load(arcdata)
    
    # decompress the textures
    try:
        comptiledata = arc['BG_tex/%s_tex.bin.LZ' % name]
    except KeyError:
        QtGui.QMessageBox.warning(None, 'Error',  'Cannot find the required texture within the tileset file %s.arc, so it will not be loaded. Keep in mind that the tileset file cannot be renamed without changing the names of the texture/object files within the archive as well!' % name)
        return False
    
    # load in the textures - uses a different method if nsmblib exists
    if HaveNSMBLib:
        tiledata = nsmblib.decompress11LZS(comptiledata)
        rgbdata = nsmblib.decodeTileset(tiledata)
        img = QtGui.QImage(rgbdata, 1024, 256, 4096, QtGui.QImage.Format_ARGB32_Premultiplied)
    else:
        lz = lz77.LZS11()
        img = LoadTextureUsingOldMethod(lz.Decompress11LZS(comptiledata))
    
    # crop the tiles out
    dest = QtGui.QPixmap.fromImage(img)
    
    sourcex = 4
    sourcey = 4
    tileoffset = idx*256
    for i in xrange(tileoffset,tileoffset+256):
        Tiles[i] = dest.copy(sourcex,sourcey,24,24)
        sourcex += 32
        if sourcex >= 1024:
            sourcex = 4
            sourcey += 32
    
    # tile behaviours aren't needed yet?
    
    # load the object definitions
    defs = [None]*256
    
    indexfile = arc['BG_unt/%s_hd.bin' % name]
    deffile = arc['BG_unt/%s.bin' % name]
    objcount = len(indexfile) / 4
    indexstruct = struct.Struct('>HBB')
    
    for i in xrange(objcount):
        data = indexstruct.unpack_from(indexfile, i << 2)
        obj = ObjectDef()
        obj.width = data[1]
        obj.height = data[2]
        obj.load(deffile,data[0],tileoffset)
        defs[i] = obj
    
    ObjectDefinitions[idx] = defs
    
    ProcessOverrides(idx, name)


def LoadTextureUsingOldMethod(tiledata):
    tx = 0; ty = 0
    iter = tiledata.__iter__()
    dest = QtGui.QImage(1024,256,QtGui.QImage.Format_ARGB32)
    dest.fill(QtCore.Qt.transparent)
    
    # this is for optimisation
    if EnableAlpha:
        for i in xrange(16384):
            for y in xrange(ty,ty+4):
                for x in xrange(tx,tx+4):
                    d = iter.next() << 8
                    d |= iter.next()
                    if (d & 0x8000) == 0:
                        argb = ((d & 0x7000) << 17) | ((d & 0xf00) << 12) | ((d & 0xf0) << 8) | ((d & 0xf) << 4)
                    else:
                        argb = 0xFF000000 | ((d & 0x7c00) << 9) | ((d & 0x3e0) << 6) | ((d & 0x1f) << 3)
                    dest.setPixel(x,y,argb)
            
            tx += 4
            if tx >= 1024: tx = 0; ty += 4
    else:
        for i in xrange(16384):
            for y in xrange(ty,ty+4):
                for x in xrange(tx,tx+4):
                    d = iter.next() << 8
                    d |= iter.next()
                    if (d & 0x8000) == 0:
                        argb = 0xFF000000 | ((d & 0xf00) << 12) | ((d & 0xf0) << 8) | ((d & 0xf) << 4)
                    else:
                        argb = 0xFF000000 | ((d & 0x7c00) << 9) | ((d & 0x3e0) << 6) | ((d & 0x1f) << 3)
                    dest.setPixel(x,y,argb)
            
            tx += 4
            if tx >= 1024: tx = 0; ty += 4
    
    return dest


def UnloadTileset(idx):
    """Unload the tileset from a specific slot"""
    for i in xrange(idx*256, idx*256+256):
        Tiles[i] = None
    
    ObjectDefinitions[idx] = None


def ProcessOverrides(idx, name):
    """Load overridden tiles if there are any"""
    
    try:
        tsindexes = ['Pa0_jyotyu', 'Pa0_jyotyu_chika', 'Pa0_jyotyu_setsugen', 'Pa0_jyotyu_yougan', 'Pa0_jyotyu_staffRoll']
        if name in tsindexes:
            offset = 1024 + tsindexes.index(name) * 64
            # Setsugen/Snow is unused for some reason? but we still override it
            # StaffRoll is the same as plain Jyotyu, so if it's used, let's be lazy and treat it as the normal one
            if offset == 1280: offset = 1024
            
            defs = ObjectDefinitions[idx]
            t = Tiles
            
            # Invisible blocks
            # these are all the same so let's just load them from the first row
            replace = 1024
            for i in [3,4,5,6,7,8,9,10,13]:
                t[i] = t[replace]
                replace += 1
            
            # Question and brick blocks
            # these don't have their own tiles so we have to do them by objects
            replace = offset + 9
            for i in xrange(38, 49):
                defs[i].rows[0][0] = (0, replace, 0)
                replace += 1
            for i in xrange(26, 38):
                defs[i].rows[0][0] = (0, replace, 0)
                replace += 1
            
            # now the extra stuff (invisible collisions etc)
            t[1] = t[1280] # solid
            t[2] = t[1311] # vine stopper
            t[11] = t[1310] # jumpthrough platform
            t[12] = t[1309] # 16x8 roof platform
            
            t[16] = t[1291] # 1x1 slope going up
            t[17] = t[1292] # 1x1 slope going down
            t[18] = t[1281] # 2x1 slope going up (part 1)
            t[19] = t[1282] # 2x1 slope going up (part 2)
            t[20] = t[1283] # 2x1 slope going down (part 1)
            t[21] = t[1284] # 2x1 slope going down (part 2)
            t[22] = t[1301] # 4x1 slope going up (part 1)
            t[23] = t[1302] # 4x1 slope going up (part 2)
            t[24] = t[1303] # 4x1 slope going up (part 3)
            t[25] = t[1304] # 4x1 slope going up (part 4)
            t[26] = t[1305] # 4x1 slope going down (part 1)
            t[27] = t[1306] # 4x1 slope going down (part 2)
            t[28] = t[1307] # 4x1 slope going down (part 3)
            t[29] = t[1308] # 4x1 slope going down (part 4)
            t[30] = t[1062] # coin
            
            t[32] = t[1289] # 1x1 roof going down
            t[33] = t[1290] # 1x1 roof going up
            t[34] = t[1285] # 2x1 roof going down (part 1)
            t[35] = t[1286] # 2x1 roof going down (part 2)
            t[36] = t[1287] # 2x1 roof going up (part 1)
            t[37] = t[1288] # 2x1 roof going up (part 2)
            t[38] = t[1293] # 4x1 roof going down (part 1)
            t[39] = t[1294] # 4x1 roof going down (part 2)
            t[40] = t[1295] # 4x1 roof going down (part 3)
            t[41] = t[1296] # 4x1 roof going down (part 4)
            t[42] = t[1297] # 4x1 roof going up (part 1)
            t[43] = t[1298] # 4x1 roof going up (part 2)
            t[44] = t[1299] # 4x1 roof going up (part 3)
            t[45] = t[1300] # 4x1 roof going up (part 4)
            t[46] = t[1312] # P-switch coins
            
            t[53] = t[1314] # donut lift
            t[61] = t[1063] # multiplayer coin
            t[63] = t[1313] # instant death tile
        
        elif name == 'Pa1_nohara' or name == 'Pa1_nohara2' or name == 'Pa1_daishizen':
            # flowers
            t = Tiles
            t[416] = t[1092] # grass
            t[417] = t[1093]
            t[418] = t[1094]
            t[419] = t[1095]
            t[420] = t[1096]
            
            if name == 'Pa1_nohara' or name == 'Pa1_nohara2':
                t[432] = t[1068] # flowers
                t[433] = t[1069] # flowers
                t[434] = t[1070] # flowers
                
                t[448] = t[1158] # flowers on grass
                t[449] = t[1159]
                t[450] = t[1160]
            elif name == 'Pa1_daishizen':
                # forest flowers
                t[432] = t[1071] # flowers
                t[433] = t[1072] # flowers
                t[434] = t[1073] # flowers
                
                t[448] = t[1222] # flowers on grass
                t[449] = t[1223]
                t[450] = t[1224]
        
        elif name == 'Pa3_rail' or name == 'Pa3_rail_white' or name == 'Pa3_daishizen':
            # These are the line guides
            # Pa3_daishizen has less though
            
            t = Tiles
            
            t[768] = t[1088] # horizontal line
            t[769] = t[1089] # vertical line
            t[770] = t[1090] # bottomright corner
            t[771] = t[1091] # topleft corner
            
            t[784] = t[1152] # left red blob (part 1)
            t[785] = t[1153] # top red blob (part 1)
            t[786] = t[1154] # top red blob (part 2)
            t[787] = t[1155] # right red blob (part 1)
            t[788] = t[1156] # topleft red blob
            t[789] = t[1157] # topright red blob
            
            t[800] = t[1216] # left red blob (part 2)
            t[801] = t[1217] # bottom red blob (part 1)
            t[802] = t[1218] # bottom red blob (part 2)
            t[803] = t[1219] # right red blob (part 2)
            t[804] = t[1220] # bottomleft red blob
            t[805] = t[1221] # bottomright red blob
            
            # Those are all for Pa3_daishizen
            if name == 'Pa3_daishizen': return

            t[816] = t[1056] # 1x2 diagonal going up (top edge)
            t[817] = t[1057] # 1x2 diagonal going down (top edge)

            t[832] = t[1120] # 1x2 diagonal going up (part 1)
            t[833] = t[1121] # 1x2 diagonal going down (part 1)
            t[834] = t[1186] # 1x1 diagonal going up
            t[835] = t[1187] # 1x1 diagonal going down
            t[836] = t[1058] # 2x1 diagonal going up (part 1)
            t[837] = t[1059] # 2x1 diagonal going up (part 2)
            t[838] = t[1060] # 2x1 diagonal going down (part 1)
            t[839] = t[1061] # 2x1 diagonal going down (part 2)

            t[848] = t[1184] # 1x2 diagonal going up (part 2)
            t[849] = t[1185] # 1x2 diagonal going down (part 2)
            t[850] = t[1250] # 1x1 diagonal going up
            t[851] = t[1251] # 1x1 diagonal going down
            t[852] = t[1122] # 2x1 diagonal going up (part 1)
            t[853] = t[1123] # 2x1 diagonal going up (part 2)
            t[854] = t[1124] # 2x1 diagonal going down (part 1)
            t[855] = t[1125] # 2x1 diagonal going down (part 2)

            t[866] = t[1065] # big circle piece 1st row
            t[867] = t[1066] # big circle piece 1st row
            t[870] = t[1189] # medium circle piece 1st row
            t[871] = t[1190] # medium circle piece 1st row

            t[881] = t[1128] # big circle piece 2nd row
            t[882] = t[1129] # big circle piece 2nd row
            t[883] = t[1130] # big circle piece 2nd row
            t[884] = t[1131] # big circle piece 2nd row
            t[885] = t[1252] # medium circle piece 2nd row
            t[886] = t[1253] # medium circle piece 2nd row
            t[887] = t[1254] # medium circle piece 2nd row
            t[888] = t[1188] # small circle

            t[896] = t[1191] # big circle piece 3rd row
            t[897] = t[1192] # big circle piece 3rd row
            t[900] = t[1195] # big circle piece 3rd row
            t[901] = t[1316] # medium circle piece 3rd row
            t[902] = t[1317] # medium circle piece 3rd row
            t[903] = t[1318] # medium circle piece 3rd row

            t[912] = t[1255] # big circle piece 4th row
            t[913] = t[1256] # big circle piece 4th row
            t[916] = t[1259] # big circle piece 4th row

            t[929] = t[1320] # big circle piece 5th row
            t[930] = t[1321] # big circle piece 5th row
            t[931] = t[1322] # big circle piece 5th row
            t[932] = t[1323] # big circle piece 5th row
            
        elif name == 'Pa3_MG_house_ami_rail':
            t = Tiles
            
            t[832] = t[1088] # horizontal line
            t[833] = t[1090] # bottomright corner
            t[834] = t[1088] # horizontal line

            t[848] = t[1089] # vertical line
            t[849] = t[1089] # vertical line
            t[850] = t[1091] # topleft corner
            
            t[835] = t[1152] # left red blob (part 1)
            t[836] = t[1153] # top red blob (part 1)
            t[837] = t[1154] # top red blob (part 2)
            t[838] = t[1155] # right red blob (part 1)
            
            t[851] = t[1216] # left red blob (part 2)
            t[852] = t[1217] # bottom red blob (part 1)
            t[853] = t[1218] # bottom red blob (part 2)
            t[854] = t[1219] # right red blob (part 2)
            
            t[866] = t[1065] # big circle piece 1st row
            t[867] = t[1066] # big circle piece 1st row
            t[870] = t[1189] # medium circle piece 1st row
            t[871] = t[1190] # medium circle piece 1st row

            t[881] = t[1128] # big circle piece 2nd row
            t[882] = t[1129] # big circle piece 2nd row
            t[883] = t[1130] # big circle piece 2nd row
            t[884] = t[1131] # big circle piece 2nd row
            t[885] = t[1252] # medium circle piece 2nd row
            t[886] = t[1253] # medium circle piece 2nd row
            t[887] = t[1254] # medium circle piece 2nd row

            t[896] = t[1191] # big circle piece 3rd row
            t[897] = t[1192] # big circle piece 3rd row
            t[900] = t[1195] # big circle piece 3rd row
            t[901] = t[1316] # medium circle piece 3rd row
            t[902] = t[1317] # medium circle piece 3rd row
            t[903] = t[1318] # medium circle piece 3rd row

            t[912] = t[1255] # big circle piece 4th row
            t[913] = t[1256] # big circle piece 4th row
            t[916] = t[1259] # big circle piece 4th row

            t[929] = t[1320] # big circle piece 5th row
            t[930] = t[1321] # big circle piece 5th row
            t[931] = t[1322] # big circle piece 5th row
            t[932] = t[1323] # big circle piece 5th row
    except:
        # Fail silently
        pass


def LoadOverrides():
    """Load overrides"""
    global Overrides
    Overrides = [None]*320
    
    OverrideBitmap = QtGui.QPixmap('reggiedata/overrides.png')
    idx = 0
    xcount = OverrideBitmap.width() / 24
    ycount = OverrideBitmap.height() / 24
    sourcex = 0
    sourcey = 0
    
    for y in xrange(ycount):
        for x in xrange(xcount):
            Overrides[idx] = OverrideBitmap.copy(sourcex, sourcey, 24, 24)
            idx += 1
            sourcex += 24
        sourcex = 0
        sourcey += 24
        if idx % 64 != 0:
            idx -= (idx % 64)
            idx += 64


Level = None
Dirty = False
DirtyOverride = 0
AutoSaveDirty = False
OverrideSnapping = False
CurrentPaintType = 0
CurrentObject = -1
CurrentSprite = -1
CurrentLayer = 1
ShowLayer0 = True
ShowLayer1 = True
ShowLayer2 = True
ObjectsNonFrozen = True
SpritesNonFrozen = True
EntrancesNonFrozen = True
LocationsNonFrozen = False
PaintingEntrance = None
PaintingEntranceListIndex = None
NumberFont = None
GridEnabled = False
RestoredFromAutoSave = False
AutoSavePath = ''
AutoSaveData = ''

def createHorzLine():
    f = QtGui.QFrame()
    f.setFrameStyle(QtGui.QFrame.HLine | QtGui.QFrame.Sunken)
    return f

def LoadNumberFont():
    """Creates a valid font we can use to display the item numbers"""
    global NumberFont
    if NumberFont != None: return
    
    # this is a really crappy method, but I can't think of any other way
    # normal Qt defines Q_WS_WIN and Q_WS_MAC but we don't have that here
    s = QtCore.QSysInfo()
    if hasattr(s, 'WindowsVersion'):
        NumberFont = QtGui.QFont('Tahoma', 7)
    elif hasattr(s, 'MacintoshVersion'):
        NumberFont = QtGui.QFont('Lucida Grande', 9)
    else:
        NumberFont = QtGui.QFont('Sans', 8)


def SetDirty(noautosave=False):
    global Dirty, DirtyOverride, AutoSaveDirty
    if DirtyOverride > 0: return
    
    if not noautosave: AutoSaveDirty = True
    if Dirty: return
    
    Dirty = True
    try:
        mainWindow.UpdateTitle()
    except:
        pass


def MapPositionToZoneID(zones, x, y):
    """Returns the zone ID containing or nearest the specified position"""
    id = 0
    minimumdist = -1
    rval = -1
    
    for zone in zones:
        r = zone.ZoneRect
        if r.contains(x,y): return id
        
        xdist = 0
        ydist = 0
        if x <= r.left(): xdist = r.left() - x
        if x >= r.right(): xdist = x - r.right()
        if y <= r.top(): ydist = r.top() - y
        if y >= r.bottom(): ydist = y - r.bottom()
        
        dist = (xdist**2+ydist**2)**0.5
        if dist < minimumdist or minimumdist == -1:
            minimumdist = dist
            rval = zone.zoneID
        
        id += 1
    
    return rval


class LevelUnit():
    """Class for a full NSMBWii level archive"""
    def newLevel(self):
        """Creates a completely new level"""
        self.arcname = None
        self.filename = 'untitled'
        self.hasName = False
        arc = archive.U8()
        arc['course'] = None
        arc['course/course1.bin'] = ''
        self.arc = arc
        self.areanum = 1
        self.areacount = 1
        
        mainWindow.levelOverview.maxX = 100
        mainWindow.levelOverview.maxY = 40

        # we don't parse blocks 4, 11, 12, 13, 14
        # we can create the rest manually
        self.blocks = [None]*14
        self.blocks[3] = '\0\0\0\0\0\0\0\0'
        # other known values for block 4: 0000 0002 0042 0000,
        #            0000 0002 0002 0000, 0000 0003 0003 0000
        self.blocks[11] = '' # never used
        self.blocks[12] = '' # paths
        self.blocks[13] = '' # path points
        
        # prepare all data
        self.tileset0 = 'Pa0_jyotyu'
        self.tileset1 = 'Pa1_nohara'
        self.tileset2 = ''
        self.tileset3 = ''
        
        self.defEvents = 0
        self.wrapFlag = 0
        self.timeLimit = 300
        self.unk1 = 0
        self.startEntrance = 0
        self.unk2 = 0
        self.unk3 = 0
        
        self.entrances = []
        self.sprites = []
        self.zones = []
        self.locations = []
        
        self.LoadReggieInfo(None)
        
        CreateTilesets()
        LoadTileset(0, 'Pa0_jyotyu')
        LoadTileset(1, 'Pa1_nohara')
        
        self.layers = [[], [], []]
    
    
    def loadLevel(self, name, fullpath, area, progress=None):
        """Loads a specific level and area"""
        startTime = time.clock()
        
        # read the archive
        if fullpath:
            self.arcname = name
        else:
            self.arcname = os.path.join(gamePath, name+'.arc')
        
        if name == 'AUTO_FLAG':
            if AutoSavePath == 'None':
                self.arcname = None
                self.filename = 'untitled'
                self.hasName = False
            else:
                self.arcname = AutoSavePath
                self.filename = os.path.basename(self.arcname)
                self.hasName = True
            
            arcdata = AutoSaveData
            SetDirty(noautosave=True)
        else:
            if not os.path.isfile(self.arcname):
                QtGui.QMessageBox.warning(None, 'Error',  'Cannot find the required level file %s.arc. Check your Stage folder and make sure it exists.' % name)
                return False
            
            self.filename = os.path.basename(self.arcname)
            self.hasName = True
            
            arcf = open(self.arcname,'rb')
            arcdata = arcf.read()
            arcf.close()
        
        self.arc = archive.U8()
        self.arc._load(arcdata)
        
        # this is a hackish method but let's go through the U8 files
        reqcourse = 'course%d.bin' % area
        reql0 = 'course%d_bgdatL0.bin' % area
        reql1 = 'course%d_bgdatL1.bin' % area
        reql2 = 'course%d_bgdatL2.bin' % area
        
        course = None
        l0 = None
        l1 = None
        l2 = None
        self.areanum = area
        self.areacount = 0
        
        for item,val in self.arc.files:
            if val != None:
                # it's a file
                fname = item[item.rfind('/')+1:]
                if fname == reqcourse:
                    course = val
                elif fname == reql0:
                    l0 = val
                elif fname == reql1:
                    l1 = val
                elif fname == reql2:
                    l2 = val
                
                if fname.startswith('course'):
                    maxarea = int(fname[6])
                    if maxarea > self.areacount: self.areacount = maxarea
        
        # load in the course file and blocks
        self.blocks = [None]*14
        getblock = struct.Struct('>II')
        for i in xrange(14):
            data = getblock.unpack_from(course, i*8)
            self.blocks[i] = course[data[0]:data[0]+data[1]]
        
        # load stuff from individual blocks
        self.LoadMetadata() # block 1
        self.LoadOptions() #block 2
        self.LoadEntrances() # block 7
        self.LoadSprites() # block 8
        self.LoadZones() # block 10 (also blocks 3, 5, and 6)
        self.LoadLocations() # block 11
        
        # load the editor metadata
        block1pos = getblock.unpack_from(course, 0)
        if block1pos[0] != 0x70:
            rdsize = block1pos[0] - 0x70
            rddata = course[0x70:block1pos[0]]
            self.LoadReggieInfo(rddata)
        else:
            self.LoadReggieInfo(None)
        
        # load the tilesets
        if progress != None: progress.setLabelText('Loading tilesets...')
        
        CreateTilesets()
        if progress != None: progress.setValue(1)
        if self.tileset0 != '': LoadTileset(0, self.tileset0)
        if progress != None: progress.setValue(2)
        if self.tileset1 != '': LoadTileset(1, self.tileset1)
        if progress != None: progress.setValue(3)
        if self.tileset2 != '': LoadTileset(2, self.tileset2)
        if progress != None: progress.setValue(4)
        if self.tileset3 != '': LoadTileset(3, self.tileset3)
        
        # load the object layers
        if progress != None:
            progress.setLabelText('Loading layers...')
            progress.setValue(5)
        
        self.layers = [[],[],[]]
        
        if l0 != None:
            self.LoadLayer(0,l0)
        
        if l1 != None:
            self.LoadLayer(1,l1)
        
        if l2 != None:
            self.LoadLayer(2,l2)
        
        endTime = time.clock()
        total = endTime - startTime
        #print 'Level loaded in %f seconds' % total
        
        return True
    
    def save(self):
        """Save the level back to a file"""
        # prepare this because else the game shits itself and refuses to load some sprites
        self.SortSpritesByZone()
        
        # save each block first
        success = True
        warnings.simplefilter('ignore') # blocks DeprecationWarnings from struct module
        self.SaveMetadata() # block 1
        self.SaveOptions() # block 2
        self.SaveEntrances() # block 7
        self.SaveSprites() # block 8
        self.SaveLoadedSprites() # block 9
        self.SaveZones() # block 10 (and 3, 5 and 6)
        self.SaveLocations() # block 11
        warnings.resetwarnings()
        rdata = self.SaveReggieInfo()
        
        # save the main course file
        # we'll be passing over the blocks array two times
        # using ctypes.create_string_buffer here because it offers mutable strings
        # and works directly with struct.pack_into(), so it's a win-win situation for me
        FileLength = (14 * 8) + len(rdata)
        for block in self.blocks:
            FileLength += len(block)
        
        course = create_string_buffer(FileLength)
        saveblock = struct.Struct('>II')
        
        HeaderOffset = 0
        FileOffset = (14 * 8) + len(rdata)
        struct.pack_into('{0}s'.format(len(rdata)), course, 0x70, rdata)
        for block in self.blocks:
            blocksize = len(block)
            saveblock.pack_into(course, HeaderOffset, FileOffset, blocksize)
            course[FileOffset:FileOffset+blocksize] = block
            HeaderOffset += 8
            FileOffset += blocksize
        

        
        # place it into the U8 archive
        arc = self.arc
        areanum = self.areanum
        arc['course/course%d.bin' % areanum] = course.raw
        arc['course/course%d_bgdatL0.bin' % areanum] = self.SaveLayer(0)
        arc['course/course%d_bgdatL1.bin' % areanum] = self.SaveLayer(1)
        arc['course/course%d_bgdatL2.bin' % areanum] = self.SaveLayer(2)
        
        # save the U8 archive
        #arcf = open(self.arcname,'wb')
        #arcf.write(arc._dump())
        #arcf.close()
        return arc._dump()
    
    def LoadMetadata(self):
        """Loads block 1, the tileset names"""
        data = struct.unpack_from('32s32s32s32s', self.blocks[0])
        self.tileset0 = data[0].strip('\0')
        self.tileset1 = data[1].strip('\0')
        self.tileset2 = data[2].strip('\0')
        self.tileset3 = data[3].strip('\0')
    
    def LoadOptions(self):
        """Loads block 2, the general options"""
        optdata = self.blocks[1]
        optstruct = struct.Struct('>IxxxxHhLBBBx')
        offset = 0
        data = optstruct.unpack_from(optdata,offset)
        self.defEvents, self.wrapFlag, self.timeLimit, self.unk1, self.startEntrance, self.unk2, self.unk3 = data

    def LoadEntrances(self):
        """Loads block 7, the entrances"""
        entdata = self.blocks[6]
        entcount = len(entdata) / 20
        entstruct = struct.Struct('>HHxxxxBBBBxBBBHxx')
        offset = 0
        entrances = []
        for i in xrange(entcount):
            data = entstruct.unpack_from(entdata,offset)
            entrances.append(EntranceEditorItem(data[0], data[1], data[2], data[3], data[4], data[5], data[6], data[7], data[8], data[9]))
            offset += 20
        self.entrances = entrances
    
    def LoadSprites(self):
        """Loads block 8, the sprites"""
        spritedata = self.blocks[7]
        sprcount = len(spritedata) / 16
        sprstruct = struct.Struct('>HHH8sxx')
        offset = 0
        sprites = []
        
        unpack = sprstruct.unpack_from
        append = sprites.append
        obj = SpriteEditorItem
        for i in xrange(sprcount):
            data = unpack(spritedata,offset)
            append(obj(data[0], data[1], data[2], data[3]))
            offset += 16
        self.sprites = sprites

    def LoadZones(self):
        """Loads block 3, the bounding preferences"""
        bdngdata = self.blocks[2]
        count = len(bdngdata) / 24
        bdngstruct = struct.Struct('>llllxBxBxxxx')
        offset = 0
        bounding = []
        for i in xrange(count):
            datab = bdngstruct.unpack_from(bdngdata,offset)
            bounding.append([datab[0], datab[1], datab[2], datab[3], datab[4], datab[5]])
            offset += 24
        self.bounding = bounding
        
        """Loads block 5, the top level background values"""
        bgAdata = self.blocks[4]
        bgAcount = len(bgAdata) / 24
        bgAstruct = struct.Struct('>xBhhhhHHHxxxBxxxx')
        offset = 0
        bgA = []
        for i in xrange(bgAcount):
            data = bgAstruct.unpack_from(bgAdata,offset)
            bgA.append([data[0], data[1], data[2], data[3], data[4], data[5], data[6], data[7], data[8]])
            offset += 24
        self.bgA = bgA

        """Loads block 6, the bottom level background values"""
        bgBdata = self.blocks[5]
        bgBcount = len(bgBdata) / 24
        bgBstruct = struct.Struct('>xBhhhhHHHxxxBxxxx')
        offset = 0
        bgB = []
        for i in xrange(bgBcount):
            datab = bgBstruct.unpack_from(bgBdata,offset)
            bgB.append([datab[0], datab[1], datab[2], datab[3], datab[4], datab[5], datab[6], datab[7], datab[8]])
            offset += 24
        self.bgB = bgB        

        """Loads block 10, the zone data"""
        zonedata = self.blocks[9]
        zonestruct = struct.Struct('>HHHHHHBBBBxBBBBxBB')
        count = len(zonedata) / 24
        offset = 0
        zones = []
        for i in xrange(count):
            dataz = zonestruct.unpack_from(zonedata,offset)
            zones.append(ZoneItem(dataz[0], dataz[1], dataz[2], dataz[3], dataz[4], dataz[5], dataz[6], dataz[7], dataz[8], dataz[9], dataz[10], dataz[11], dataz[12], dataz[13], dataz[14], dataz[15], bounding, bgA, bgB, i))
            offset += 24
        self.zones = zones

    def LoadLocations(self):
        """Loads block 11, the sprite locations"""
        locdata = self.blocks[10]
        locstruct = struct.Struct('>HHHHBxxx')
        count = len(locdata) / 12
        offset = 0
        locations = []
        for i in xrange(count):
            data = locstruct.unpack_from(locdata, offset)
            locations.append(SpriteLocationItem(data[0], data[1], data[2], data[3], data[4]))
            offset += 12
        self.locations = locations
    
    
    def LoadLayer(self, idx, layerdata):
        """Loads a specific object layer from a string"""
        objcount = len(layerdata) / 10
        objstruct = struct.Struct('>HHHHH')
        offset = 0
        z = (2 - idx) * 8192
        
        layer = self.layers[idx]
        append = layer.append
        obj = LevelObjectEditorItem
        unpack = objstruct.unpack_from
        for i in xrange(objcount):
            data = unpack(layerdata,offset)
            append(obj(data[0] >> 12, data[0] & 4095, idx, data[1], data[2], data[3], data[4], z))
            z += 1
            offset += 10
    
    def SaveMetadata(self):
        """Saves the tileset names back to block 1"""
        self.blocks[0] = ''.join([self.tileset0.ljust(32,'\0'), self.tileset1.ljust(32,'\0'), self.tileset2.ljust(32,'\0'), self.tileset3.ljust(32,'\0')])
    
    def SaveOptions(self):
        """Saves block 2, the general options"""
        optstruct = struct.Struct('>IxxxxHhLBBBx')
        buffer = create_string_buffer(20)
        optstruct.pack_into(buffer, 0, self.defEvents, self.wrapFlag, self.timeLimit, self.unk1, self.startEntrance, self.unk2, self.unk3)
        self.blocks[1] = buffer.raw

    def SaveLayer(self, idx):
        """Saves an object layer to a string"""
        layer = self.layers[idx]
        offset = 0
        objstruct = struct.Struct('>HHHHH')
        buffer = create_string_buffer((len(layer) * 10) + 2)
        f_int = int
        for obj in layer:
            objstruct.pack_into(buffer, offset, f_int((obj.tileset << 12) | obj.type), f_int(obj.objx), f_int(obj.objy), f_int(obj.width), f_int(obj.height))
            offset += 10
        buffer[offset] = '\xff'
        buffer[offset+1] = '\xff'
        return buffer.raw
    
    def SaveEntrances(self):
        """Saves the entrances back to block 7"""
        offset = 0
        entstruct = struct.Struct('>HHxxxxBBBBxBBBHxx')
        buffer = create_string_buffer(len(self.entrances) * 20)
        zonelist = self.zones
        for entrance in self.entrances:
            zoneID = MapPositionToZoneID(zonelist, entrance.objx, entrance.objy)
            entstruct.pack_into(buffer, offset, int(entrance.objx), int(entrance.objy), int(entrance.entid), int(entrance.destarea), int(entrance.destentrance), int(entrance.enttype), zoneID, int(entrance.entlayer), int(entrance.entpath), int(entrance.entsettings))
            offset += 20
        self.blocks[6] = buffer.raw
    
    def SaveSprites(self):
        """Saves the sprites back to block 8"""
        offset = 0
        sprstruct = struct.Struct('>HHH6sB1sxx')
        buffer = create_string_buffer((len(self.sprites) * 16) + 4)
        f_int = int
        for sprite in self.sprites:
            sprstruct.pack_into(buffer, offset, f_int(sprite.type), f_int(sprite.objx), f_int(sprite.objy), sprite.spritedata[:6], sprite.zoneID, sprite.spritedata[7])
            offset += 16
        buffer[offset] = '\xff'
        buffer[offset+1] = '\xff'
        buffer[offset+2] = '\xff'
        buffer[offset+3] = '\xff'
        self.blocks[7] = buffer.raw
    
    def SaveLoadedSprites(self):
        """Saves the list of loaded sprites back to block 9"""
        ls = []
        for sprite in self.sprites:
            if sprite.type not in ls: ls.append(sprite.type)
        ls.sort()
        
        offset = 0
        sprstruct = struct.Struct('>Hxx')
        buffer = create_string_buffer(len(ls) * 4)
        for s in ls:
            sprstruct.pack_into(buffer, offset, int(s))
            offset += 4
        self.blocks[8] = buffer.raw
    
    
    def SaveZones(self):
        """Saves blocks 10, 3, 5 and 6, the zone data, boundings, bgA and bgB data respectively"""
        bdngstruct = struct.Struct('>llllxBxBxxxx')
        bgAstruct = struct.Struct('>xBhhhhHHHxxxBxxxx')
        bgBstruct = struct.Struct('>xBhhhhHHHxxxBxxxx')
        zonestruct = struct.Struct('>HHHHHHBBBBxBBBBxBB')
        offset = 0
        i = 0
        zcount = len(Level.zones)
        buffer2 = create_string_buffer(24*zcount)
        buffer4 = create_string_buffer(24*zcount)
        buffer5 = create_string_buffer(24*zcount)
        buffer9 = create_string_buffer(24*zcount)
        for z in Level.zones:
            bdngstruct.pack_into(buffer2, offset, z.yupperbound, z.ylowerbound, z.unkbound1, z.unkbound2, i, 0xF)
            bgAstruct.pack_into(buffer4, offset, i, z.XscrollA, z.YscrollA, z.YpositionA, z.XpositionA, z.bg1A, z.bg2A, z.bg3A, z.ZoomA)
            bgBstruct.pack_into(buffer5, offset, i, z.XscrollB, z.YscrollB, z.YpositionB, z.XpositionB, z.bg1B, z.bg2B, z.bg3B, z.ZoomB)
            zonestruct.pack_into(buffer9, offset, z.objx, z.objy, z.width, z.height, z.modeldark, z.terraindark, i, i, z.cammode, z.camzoom, z.visibility, i, i, z.unknownz, z.music, z.sfxmod)
            offset += 24
            i += 1
        
        self.blocks[2] = buffer2.raw
        self.blocks[4] = buffer4.raw
        self.blocks[5] = buffer5.raw
        self.blocks[9] = buffer9.raw
    
    
    def SaveLocations(self):
        """Saves block 11, the location data"""
        locstruct = struct.Struct('>HHHHBxxx')
        offset = 0
        zcount = len(Level.locations)
        buffer = create_string_buffer(12*zcount)
        
        for z in Level.locations:
            locstruct.pack_into(buffer, offset, int(z.objx), int(z.objy), int(z.width), int(z.height), int(z.id))
            offset += 12
        
        self.blocks[10] = buffer.raw
    
    
    def RemoveFromLayer(self, obj):
        """Removes a specific object from the level and updates Z indexes accordingly"""
        layer = self.layers[obj.layer]
        idx = layer.index(obj)
        del layer[idx]
        for i in xrange(idx,len(layer)):
            upd = layer[i]
            upd.setZValue(upd.zValue() - 1)
    
    def SortSpritesByZone(self):
        """Sorts the sprite list by zone ID so it will work in-game"""
        
        split = {}
        zones = []
        
        f_MapPositionToZoneID = MapPositionToZoneID
        zonelist = self.zones
        
        for sprite in self.sprites:
            zone = f_MapPositionToZoneID(zonelist, sprite.objx, sprite.objy)
            sprite.zoneID = zone
            if not split.has_key(zone):
                split[zone] = []
                zones.append(zone)
            split[zone].append(sprite)
        
        newlist = []
        zones.sort()
        for z in zones:
            newlist += split[z]
        
        self.sprites = newlist
    
    
    def LoadReggieInfo(self, data):
        info = {
            'Creator': '(unknown)',
            'Title': '-',
            'Author': '-',
            'Group': '-',
            'Webpage': '-',
            'Password': ''
        }
        
        if data != None:
            try:
                level_info = pickle.loads(data)
                for k,v in level_info.iteritems():
                    if k in info: info[k] = v
            except Exception:
                pass
        
        for k,v in info.iteritems():
            self.__dict__[k] = v
    
    def SaveReggieInfo(self):
        info = {
            'Creator': ReggieID,
            'Title': self.Title,
            'Author': self.Author,
            'Group': self.Group,
            'Webpage': self.Webpage,
            'Password': self.Password
        }
        return pickle.dumps(info, 2)


class LevelEditorItem(QtGui.QGraphicsItem):
    """Class for any type of item that can show up in the level editor control"""
    positionChanged = None # Callback: positionChanged(LevelEditorItem obj, int oldx, int oldy, int x, int y)
    
    def __init__(self):
        """Generic constructor for level editor items"""
        QtGui.QGraphicsItem.__init__(self)
        self.setFlag(self.ItemSendsGeometryChanges, True)
    
    def itemChange(self, change, value):
        """Makes sure positions don't go out of bounds and updates them as necessary"""
        
        if change == QtGui.QGraphicsItem.ItemPositionChange:
            # snap to 24x24
            newpos = value.toPyObject()
            
            # snap even further if Shift isn't held
            # but -only- if OverrideSnapping is off
            if not OverrideSnapping:
                if QtGui.QApplication.keyboardModifiers() == QtCore.Qt.AltModifier:
                    newpos.setX(int(int((newpos.x() + 0.75) / 1.5) * 1.5))
                    newpos.setY(int(int((newpos.y() + 0.75) / 1.5) * 1.5))
                else:
                    newpos.setX(int(int((newpos.x() + 6) / 12) * 12))
                    newpos.setY(int(int((newpos.y() + 6) / 12) * 12))
            
            x = newpos.x()
            y = newpos.y()
            
            # don't let it get out of the boundaries
            if x < 0: newpos.setX(0)
            if x > 24552: newpos.setX(24552)
            if y < 0: newpos.setY(0)
            if y > 12264: newpos.setY(12264)
            
            # update the data
            x = int(newpos.x() / 1.5)
            y = int(newpos.y() / 1.5)
            if x != self.objx or y != self.objy:
                updRect = QtCore.QRectF(self.x(), self.y(), self.BoundingRect.width(), self.BoundingRect.height())
                if self.scene() != None:
                    self.scene().update(updRect)
                
                oldx = self.objx
                oldy = self.objy
                self.objx = x
                self.objy = y
                if self.positionChanged != None:
                    self.positionChanged(self, oldx, oldy, x, y)
            
                SetDirty()
            
            return newpos
        
        return QtGui.QGraphicsItem.itemChange(self, change, value)
    
    def boundingRect(self):
        """Required for Qt"""
        return self.BoundingRect


class LevelObjectEditorItem(LevelEditorItem):
    """Level editor item that represents an ingame object"""
    
    def __init__(self, tileset, type, layer, x, y, width, height, z):
        """Creates an object with specific data"""
        LevelEditorItem.__init__(self)
        
        self.tileset = tileset
        self.type = type
        self.objx = x
        self.objy = y
        self.layer = layer
        self.width = width
        self.height = height
        self.objdata = None
        
        self.setFlag(self.ItemIsMovable, ObjectsNonFrozen)
        self.setFlag(self.ItemIsSelectable, ObjectsNonFrozen)
        self.UpdateRects()
        
        self.dragging = False
        self.dragstartx = -1
        self.dragstarty = -1
        
        global DirtyOverride
        DirtyOverride += 1
        self.setPos(x*24,y*24)
        DirtyOverride -= 1
        
        self.setZValue(z)
        self.setToolTip('Tileset %d object %d' % (tileset+1, type))
        
        if layer == 0:
            self.setVisible(ShowLayer0)
        elif layer == 1:
            self.setVisible(ShowLayer1)
        elif layer == 2:
            self.setVisible(ShowLayer2)
        
        self.updateObjCache()
    
    
    def SetType(self, tileset, type):
        """Sets the type of the object"""
        self.setToolTip('Tileset %d object %d' % (tileset+1, type))
        self.tileset = tileset
        self.type = type
        self.updateObjCache()
        self.update()
    
    
    def updateObjCache(self):
        """Updates the rendered object data"""
        self.objdata = RenderObject(self.tileset, self.type, self.width, self.height)
    
    
    def UpdateRects(self):
        """Recreates the bounding and selection rects"""
        self.prepareGeometryChange()
        self.BoundingRect = QtCore.QRectF(0,0,24*self.width,24*self.height)
        self.SelectionRect = QtCore.QRectF(0,0,24*self.width-1,24*self.height-1)
        self.GrabberRect = QtCore.QRectF(24*self.width-5,24*self.height-5,5,5)
        self.LevelRect = QtCore.QRectF(self.objx,self.objy,self.width,self.height)
    
    
    def itemChange(self, change, value):
        """Makes sure positions don't go out of bounds and updates them as necessary"""
        
        if change == QtGui.QGraphicsItem.ItemPositionChange:
            scene = self.scene()
            if scene == None: return value
            
            # snap to 24x24
            newpos = value.toPyObject()
            newpos.setX(int((newpos.x() + 12) / 24) * 24)
            newpos.setY(int((newpos.y() + 12) / 24) * 24)
            x = newpos.x()
            y = newpos.y()
            
            # don't let it get out of the boundaries
            if x < 0: newpos.setX(0)
            if x > 24576: newpos.setX(24576)
            if y < 0: newpos.setY(0)
            if y > 12288: newpos.setY(12288)
            
            # update the data
            x = int(newpos.x() / 24)
            y = int(newpos.y() / 24)
            if x != self.objx or y != self.objy:
                self.LevelRect.moveTo(x,y)
                
                oldx = self.objx
                oldy = self.objy
                self.objx = x
                self.objy = y
                if self.positionChanged != None:
                    self.positionChanged(self, oldx, oldy, x, y)
                
                SetDirty()
                
                #updRect = QtCore.QRectF(self.x(), self.y(), self.BoundingRect.width(), self.BoundingRect.height())
                #scene.invalidate(updRect)
                
                scene.invalidate(self.x(), self.y(), self.width*24, self.height*24, QtGui.QGraphicsScene.BackgroundLayer)
                #scene.invalidate(newpos.x(), newpos.y(), self.width*24, self.height*24, QtGui.QGraphicsScene.BackgroundLayer)
            
            return newpos
        
        return QtGui.QGraphicsItem.itemChange(self, change, value)
    
    
    def paint(self, painter, option, widget):
        """Paints the object"""
        if self.isSelected():
            painter.setPen(QtGui.QPen(QtCore.Qt.white, 1, QtCore.Qt.DotLine))
            painter.drawRect(self.SelectionRect)
            painter.fillRect(self.SelectionRect, QtGui.QColor.fromRgb(255,255,255,64))
            
            painter.fillRect(self.GrabberRect, QtGui.QColor.fromRgb(255,255,255,255))
    
    
    def mousePressEvent(self, event):
        """Overrides mouse pressing events if needed for resizing"""
        if event.button() == QtCore.Qt.LeftButton:
            if QtGui.QApplication.keyboardModifiers() == QtCore.Qt.ControlModifier:
                layer = Level.layers[self.layer]
                if len(layer) == 0:
                    newZ = (2 - self.layer) * 8192
                else:
                    newZ = layer[-1].zValue() + 1
                
                currentZ = self.zValue()
                self.setZValue(newZ) # swap the Z values so it doesn't look like the cloned item is the old one
                newitem = LevelObjectEditorItem(self.tileset, self.type, self.layer, self.objx, self.objy, self.width, self.height, currentZ)
                layer.append(newitem)
                mainWindow.scene.addItem(newitem)
                mainWindow.scene.clearSelection()
                self.setSelected(True)
                
                SetDirty()
        
        if self.isSelected() and self.GrabberRect.contains(event.pos()):
            # start dragging
            self.dragging = True
            self.dragstartx = int((event.pos().x() - 10) / 24)
            self.dragstarty = int((event.pos().y() - 10) / 24)
            event.accept()
        else:
            LevelEditorItem.mousePressEvent(self, event)
            self.dragging = False
    
    
    def mouseMoveEvent(self, event):
        """Overrides mouse movement events if needed for resizing"""
        if event.buttons() != QtCore.Qt.NoButton and self.dragging:
            # resize it
            dsx = self.dragstartx
            dsy = self.dragstarty
            clickedx = int((event.pos().x() - 10) / 24)
            clickedy = int((event.pos().y() - 10) / 24)
            
            cx = self.objx
            cy = self.objy
            
            if clickedx < 0: clickedx = 0
            if clickedy < 0: clickedy = 0
            
            #print '%d %d' % (clickedx - dsx, clickedy - dsy)
            
            if clickedx != dsx or clickedy != dsy:
                self.dragstartx = clickedx
                self.dragstarty = clickedy
                
                self.width += clickedx - dsx
                self.height += clickedy - dsy
                
                self.updateObjCache()
                
                oldrect = self.BoundingRect
                oldrect.translate(cx * 24, cy * 24)
                newrect = QtCore.QRectF(self.x(), self.y(), self.width * 24, self.height * 24)
                updaterect = oldrect.unite(newrect)
                
                self.UpdateRects()
                self.scene().update(updaterect)
                SetDirty()
            
            event.accept()
        else:
            LevelEditorItem.mouseMoveEvent(self, event)
    
    
    def delete(self):
        """Delete the object from the level"""
        Level.RemoveFromLayer(self)
        self.scene().update(self.x(), self.y(), self.BoundingRect.width(), self.BoundingRect.height())


class ZoneItem(LevelEditorItem):
    """Level editor item that represents a zone"""

    def __init__(self, a, b, c, d, e, f, g, h, i, j, k, l, m, n, o, p, boundings, bgA, bgB, id):
        """Creates a zone with specific data"""
        LevelEditorItem.__init__(self)
        
        self.font = NumberFont
        self.id = id
        self.TitlePos = QtCore.QPointF(10,18)
        self.UpdateTitle()
        
        self.objx = a
        self.objy = b
        self.width = c
        self.height = d
        self.modeldark = e
        self.terraindark = f
        self.zoneID = g
        self.block3id = h
        self.cammode = i
        self.camzoom = j
        self.visibility = k
        self.block5id = l
        self.block6id = m
        self.unknownz = n
        self.music = o
        self.sfxmod = p
        self.UpdateRects()
        
        bounding = None
        id = self.block3id
        for block in boundings:
            if block[4] == id: bounding = block
        
        self.yupperbound = bounding[0]
        self.ylowerbound = bounding[1]
        self.unkbound1 = bounding[2]
        self.unkbound2 = bounding[3]
        self.entryid = bounding[4]
        self.unknownbnf = bounding[5]
        
        bgABlock = None
        id = self.block5id
        for block in bgA:
            if block[0] == id: bgABlock = block
        
        self.entryidA = bgABlock[0]
        self.XscrollA = bgABlock[1]
        self.YscrollA = bgABlock[2]
        self.YpositionA = bgABlock[3]
        self.XpositionA = bgABlock[4]
        self.bg1A = bgABlock[5]
        self.bg2A = bgABlock[6]
        self.bg3A = bgABlock[7]
        self.ZoomA = bgABlock[8]

        bgBBlock = None
        id = self.block6id
        for block in bgB:
            if block[0] == id: bgBBlock = block
        
        self.entryidB = bgBBlock[0]
        self.XscrollB = bgBBlock[1]
        self.YscrollB = bgBBlock[2]
        self.YpositionB = bgBBlock[3]
        self.XpositionB = bgBBlock[4]
        self.bg1B = bgBBlock[5]
        self.bg2B = bgBBlock[6]
        self.bg3B = bgBBlock[7]
        self.ZoomB = bgBBlock[8]

        self.dragging = False
        self.dragstartx = -1
        self.dragstarty = -1
        
        global DirtyOverride
        DirtyOverride += 1
        self.setPos(int(a*1.5),int(b*1.5))
        DirtyOverride -= 1
        self.setZValue(50000)
    
    
    def UpdateTitle(self):
        """Updates the zone's title"""
        self.title = 'Zone %d' % (self.id+1)
    
    
    def UpdateRects(self):
        """Updates the zone's bounding rectangle"""
        self.prepareGeometryChange()
        self.BoundingRect = QtCore.QRectF(0,0,self.width*1.5,self.height*1.5)
        self.ZoneRect = QtCore.QRectF(self.objx,self.objy,self.width,self.height)
        self.DrawRect = QtCore.QRectF(3,3,int(self.width*1.5)-6,int(self.height*1.5)-6)
        self.GrabberRectTL = QtCore.QRectF(0,0,5,5)
        self.GrabberRectTR = QtCore.QRectF(int(self.width*1.5)-5,0,5,5)
        self.GrabberRectBL = QtCore.QRectF(0,int(self.height*1.5)-5,5,5)
        self.GrabberRectBR = QtCore.QRectF(int(self.width*1.5)-5,int(self.height*1.5)-5,5,5)
    
    
    def paint(self, painter, option, widget):
        """Paints the zone on screen"""
        #painter.setClipRect(option.exposedRect)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        painter.setPen(QtGui.QPen(QtGui.QColor.fromRgba(0xB093C9FF), 3))
        painter.drawRect(self.DrawRect)
        
        painter.setPen(QtGui.QPen(QtGui.QColor.fromRgba(0xFF2C4054), 3))
        painter.setFont(self.font)
        painter.drawText(self.TitlePos, self.title)
        
        GrabberColour = QtGui.QColor.fromRgb(255,255,255,255)
        painter.fillRect(self.GrabberRectTL, GrabberColour)
        painter.fillRect(self.GrabberRectTR, GrabberColour)
        painter.fillRect(self.GrabberRectBL, GrabberColour)
        painter.fillRect(self.GrabberRectBR, GrabberColour)
    
    
    def mousePressEvent(self, event):
        """Overrides mouse pressing events if needed for resizing"""
        
        if self.GrabberRectTL.contains(event.pos()):
            # start dragging
            self.dragging = True
            self.dragstartx = int(event.pos().x() / 1.5)
            self.dragstarty = int(event.pos().y() / 1.5)
            self.dragcorner = 1
            event.accept()
        elif self.GrabberRectTR.contains(event.pos()):
            self.dragging = True
            self.dragstartx = int(event.pos().x() / 1.5)
            self.dragstarty = int(event.pos().y() / 1.5)
            self.dragcorner = 2
            event.accept()
        elif self.GrabberRectBL.contains(event.pos()):
            self.dragging = True
            self.dragstartx = int(event.pos().x() / 1.5)
            self.dragstarty = int(event.pos().y() / 1.5)
            self.dragcorner = 3
            event.accept()
        elif self.GrabberRectBR.contains(event.pos()):
            self.dragging = True
            self.dragstartx = int(event.pos().x() / 1.5)
            self.dragstarty = int(event.pos().y() / 1.5)
            self.dragcorner = 4
            event.accept()
        else:
            LevelEditorItem.mousePressEvent(self, event)
            self.dragging = False
    
    
    def mouseMoveEvent(self, event):
        """Overrides mouse movement events if needed for resizing"""
        
        if event.buttons() != QtCore.Qt.NoButton and self.dragging:
            # resize it
            dsx = self.dragstartx
            dsy = self.dragstarty
            clickedx = int(event.pos().x() / 1.5)
            clickedy = int(event.pos().y() / 1.5)
            corner = self.dragcorner
            
            cx = self.objx
            cy = self.objy
            
            checkwidth = self.width - 128
            checkheight = self.height - 128
            if corner == 1:
                if clickedx >= checkwidth: clickedx = checkwidth - 1
                if clickedy >= checkheight: clickedy = checkheight - 1
            elif corner == 2:
                if clickedx < 0: clickedx = 0
                if clickedy >= checkheight: clickedy = checkheight - 1
            elif corner == 3:
                if clickedx >= checkwidth: clickedx = checkwidth - 1
                if clickedy < 0: clickedy = 0
            elif corner == 4:
                if clickedx < 0: clickedx = 0
                if clickedy < 0: clickedy = 0
            
            if clickedx != dsx or clickedy != dsy:
                #if (cx + clickedx - dsx) < 16: clickedx += (16 - (cx + clickedx - dsx))
                #if (cy + clickedy - dsy) < 16: clickedy += (16 - (cy + clickedy - dsy))
                
                self.dragstartx = clickedx
                self.dragstarty = clickedy
                xdelta = clickedx - dsx
                ydelta = clickedy - dsy
                
                if corner == 1:
                    self.objx += xdelta
                    self.objy += ydelta
                    self.dragstartx -= xdelta
                    self.dragstarty -= ydelta
                    self.width -= xdelta
                    self.height -= ydelta
                elif corner == 2:
                    self.objy += ydelta
                    self.dragstarty -= ydelta
                    self.width += xdelta
                    self.height -= ydelta
                elif corner == 3:
                    self.objx += xdelta
                    self.dragstartx -= xdelta
                    self.width -= xdelta
                    self.height += ydelta
                elif corner == 4:
                    self.width += xdelta
                    self.height += ydelta
                
                if self.objx < 16:
                    self.width -= (16 - self.objx)
                    self.objx = 16
                if self.objy < 16:
                    self.height -= (16 - self.objy)
                    self.objy = 16
                
                if self.width < 300:
                    self.objx -= (300 - self.width)
                    self.width = 300
                if self.height < 200:
                    self.objy -= (200 - self.height)
                    self.height = 200
                
                oldrect = self.BoundingRect
                oldrect.translate(cx * 1.5, cy * 1.5)
                newrect = QtCore.QRectF(self.x(), self.y(), self.width * 1.5, self.height * 1.5)
                updaterect = oldrect.unite(newrect)
                updaterect.setTop(updaterect.top() - 3)
                updaterect.setLeft(updaterect.left() - 3)
                updaterect.setRight(updaterect.right() + 3)
                updaterect.setBottom(updaterect.bottom() + 3)
                
                self.UpdateRects()
                self.setPos(int(self.objx * 1.5), int(self.objy * 1.5))
                self.scene().update(updaterect)
                
                mainWindow.levelOverview.update()
                SetDirty()
            
            event.accept()
        else:
            LevelEditorItem.mouseMoveEvent(self, event)
    
    def itemChange(self, change, value):
        """Avoids snapping for zones"""
        return QtGui.QGraphicsItem.itemChange(self, change, value)

class SpriteLocationItem(LevelEditorItem):
    """Level editor item that represents a sprite location"""
    sizeChanged = None # Callback: sizeChanged(SpriteEditorItem obj, int width, int height)
    
    def __init__(self, x, y, width, height, id):
        """Creates a location with specific data"""
        LevelEditorItem.__init__(self)
        
        self.font = NumberFont
        self.TitlePos = QtCore.QPointF(4,12)
        self.objx = x
        self.objy = y
        self.width = width
        self.height = height
        self.id = id
        self.UpdateTitle()
        self.UpdateRects()
        
        self.setFlag(self.ItemIsMovable, LocationsNonFrozen)
        self.setFlag(self.ItemIsSelectable, LocationsNonFrozen)
        
        global DirtyOverride
        DirtyOverride += 1
        self.setPos(int(x*1.5),int(y*1.5))
        DirtyOverride -= 1
        
        self.dragging = False
        self.setZValue(24000)
    
    
    def UpdateTitle(self):
        """Updates the location's title"""
        self.title = '%d' % (self.id)
    
    
    def UpdateRects(self):
        """Updates the location's bounding rectangle"""
        self.prepareGeometryChange()
        self.BoundingRect = QtCore.QRectF(0,0,self.width*1.5,self.height*1.5)
        self.SelectionRect = QtCore.QRectF(self.objx*1.5,self.objy*1.5,self.width*1.5,self.height*1.5)
        self.ZoneRect = QtCore.QRectF(self.objx,self.objy,self.width,self.height)
        self.DrawRect = QtCore.QRectF(1,1,self.width*1.5-2,self.height*1.5-2)
        self.GrabberRect = QtCore.QRectF(1.5*self.width-6,1.5*self.height-6,5,5)
    
    
    def paint(self, painter, option, widget):
        """Paints the location on screen"""
        painter.setClipRect(option.exposedRect)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        painter.setBrush(QtGui.QBrush(QtGui.QColor.fromRgb(114,42,188,70)))
        painter.setPen(QtGui.QPen(QtCore.Qt.black, 2))
        painter.drawRect(self.DrawRect)
        
        painter.setPen(QtGui.QPen(QtCore.Qt.white, 1))
        painter.setFont(self.font)
        painter.drawText(self.TitlePos, self.title)
        
        if self.isSelected():
            painter.setPen(QtGui.QPen(QtCore.Qt.white, 1, QtCore.Qt.DotLine))
            painter.drawRect(self.DrawRect)
            painter.fillRect(self.DrawRect, QtGui.QColor.fromRgb(255,255,255,40))
            
            painter.fillRect(self.GrabberRect, QtGui.QColor.fromRgb(255,255,255,255))
    
    
    def mousePressEvent(self, event):
        """Overrides mouse pressing events if needed for resizing"""
        if self.isSelected() and self.GrabberRect.contains(event.pos()):
            # start dragging
            self.dragging = True
            self.dragstartx = int(event.pos().x() / 1.5)
            self.dragstarty = int(event.pos().y() / 1.5)
            event.accept()
        else:
            LevelEditorItem.mousePressEvent(self, event)
            self.dragging = False
    
    
    def mouseMoveEvent(self, event):
        """Overrides mouse movement events if needed for resizing"""
        if event.buttons() != QtCore.Qt.NoButton and self.dragging:
            # resize it
            dsx = self.dragstartx
            dsy = self.dragstarty
            clickedx = event.pos().x() / 1.5
            clickedy = event.pos().y() / 1.5
            
            cx = self.objx
            cy = self.objy
            
            if clickedx < 0: clickedx = 0
            if clickedy < 0: clickedy = 0
            
            #print '%d %d' % (clickedx - dsx, clickedy - dsy)
            
            if clickedx != dsx or clickedy != dsy:
                self.dragstartx = clickedx
                self.dragstarty = clickedy
                
                self.width += clickedx - dsx
                self.height += clickedy - dsy
                
                oldrect = self.BoundingRect
                oldrect.translate(cx*1.5, cy*1.5)
                newrect = QtCore.QRectF(self.x(), self.y(), self.width*1.5, self.height*1.5)
                updaterect = oldrect.unite(newrect)
                
                self.UpdateRects()
                self.scene().update(updaterect)
                SetDirty()
                
                if self.sizeChanged != None:
                    self.sizeChanged(self, self.width, self.height)
            
            event.accept()
        else:
            LevelEditorItem.mouseMoveEvent(self, event)
    
    
    def delete(self):
        """Delete the zone from the level"""
        Level.locations.remove(self)
        self.scene().update(self.x(), self.y(), self.BoundingRect.width(), self.BoundingRect.height())




class SpriteEditorItem(LevelEditorItem):
    """Level editor item that represents a sprite"""
    BoundingRect = QtCore.QRectF(0,0,24,24)
    SelectionRect = QtCore.QRectF(0,0,23,23)
    RoundedRect = QtCore.QRectF(1,1,22,22)
    
    def __init__(self, type, x, y, data):
        """Creates a sprite with specific data"""
        LevelEditorItem.__init__(self)
        
        self.font = NumberFont
        self.type = type
        self.objx = x
        self.objy = y
        self.spritedata = data
        self.LevelRect = (QtCore.QRectF(self.objx/16, self.objy/16, 24/16, 24/16))
        self.ChangingPos = False
        
        self.InitialiseSprite()
        
        self.setFlag(self.ItemIsMovable, SpritesNonFrozen)
        self.setFlag(self.ItemIsSelectable, SpritesNonFrozen)
        
        global DirtyOverride
        DirtyOverride += 1
        self.setPos(int((x+self.xoffset)*1.5),int((y+self.yoffset)*1.5))
        DirtyOverride -= 1
        
        sname = Sprites[type].name
        self.name = sname
        self.setToolTip('<b>Sprite %d:</b><br>%s' % (type,sname))
    
    def SetType(self, type):
        """Sets the type of the sprite"""
        self.name = Sprites[type].name
        self.setToolTip('<b>Sprite %d:</b><br>%s' % (type, self.name))
        self.type = type
        
        #CurrentRect = QtCore.QRectF(self.x(), self.y(), self.BoundingRect.width(), self.BoundingRect.height())
        
        self.InitialiseSprite()
        
        #self.scene().update(CurrentRect)
        #self.scene().update(self.x(), self.y(), self.BoundingRect.width(), self.BoundingRect.height())
    
    def InitialiseSprite(self):
        """Initialises sprite and creates any auxiliary objects needed"""
        if hasattr(self, 'aux'):
            self.aux.scene().removeItem(self.aux)
            del self.aux
        
        type = self.type
        
        self.setZValue(25000)
        self.resetTransform()
        
        xo = 0
        yo = 0
        xs = 16
        ys = 16
        self.dynamicSize = False
        self.customPaint = False
        
        try:
            init = sprites.Initialisers[type]
            xo, yo, xs, ys = init(self)
        except KeyError:
            pass
        
        self.xoffset = xo
        self.yoffset = yo
        self.xsize = xs
        self.ysize = ys
        
        self.UpdateDynamicSizing()
        self.UpdateRects()
        self.ChangingPos = True
        self.setPos(int((self.objx+self.xoffset)*1.5),int((self.objy+self.yoffset)*1.5))
        self.ChangingPos = False
    
    def UpdateDynamicSizing(self):
        """Updates the sizes for dynamically sized sprites"""
        if self.dynamicSize:
            #CurrentRect = QtCore.QRectF(self.x(), self.y(), self.BoundingRect.width(), self.BoundingRect.height())
            
            self.dynSizer(self)
            self.UpdateRects()
            
            self.ChangingPos = True
            self.setPos(int((self.objx+self.xoffset)*1.5),int((self.objy+self.yoffset)*1.5))
            self.ChangingPos = False
            
            #if self.scene() != None:
            #    self.scene().update(CurrentRect)
            #    self.scene().update(self.x(), self.y(), self.BoundingRect.width(), self.BoundingRect.height())
    
    def UpdateRects(self):
        """Creates all the rectangles for the sprite"""
        type = self.type
        
        self.prepareGeometryChange()
        
        xs = self.xsize
        ys = self.ysize
        
        self.BoundingRect = QtCore.QRectF(0,0,xs*1.5,ys*1.5)
        self.SelectionRect = QtCore.QRectF(0,0,int(xs*1.5-1),int(ys*1.5-1))
        self.RoundedRect = QtCore.QRectF(1,1,xs*1.5-2,ys*1.5-2)
        self.LevelRect = (QtCore.QRectF((self.objx + self.xoffset) / 16, (self.objy + self.yoffset) / 16, self.xsize/16, self.ysize/16))

    def itemChange(self, change, value):
        """Makes sure positions don't go out of bounds and updates them as necessary"""
        
        if change == QtGui.QGraphicsItem.ItemPositionChange:
            if self.scene() == None: return value
            if self.ChangingPos: return value
            
            xOffset = self.xoffset
            yOffset = self.yoffset
            
            # snap to 24x24
            newpos = value.toPyObject()
            
            # snap even further if Shift isn't held
            # but -only- if OverrideSnapping is off
            if not OverrideSnapping:
                if QtGui.QApplication.keyboardModifiers() == QtCore.Qt.AltModifier:
                    newpos.setX((int((newpos.x() + 0.75) / 1.5) * 1.5))
                    newpos.setY((int((newpos.y() + 0.75) / 1.5) * 1.5))
                else:
                    #xCompensation = (xOffset % 16) * 1.5
                    #yCompensation = (yOffset % 16) * 1.5
                    #newpos.setX((int((newpos.x() + 6 - xCompensation) / 12) * 12) + xCompensation)
                    #newpos.setY((int((newpos.y() + 6 - yCompensation) / 12) * 12) + yCompensation)
                    
                    newpos.setX((int((int(newpos.x() / 1.5) - xOffset) / 8) * 8 + xOffset) * 1.5)
                    newpos.setY((int((int(newpos.y() / 1.5) - yOffset) / 8) * 8 + yOffset) * 1.5)
            
            x = newpos.x()
            y = newpos.y()
            
            # don't let it get out of the boundaries
            if x < 0: newpos.setX(0)
            if x > 24552: newpos.setX(24552)
            if y < 0: newpos.setY(0)
            if y > 12264: newpos.setY(12264)
            
            # update the data
            x = int(newpos.x() / 1.5 - xOffset)
            y = int(newpos.y() / 1.5 - yOffset)
            
            if x != self.objx or y != self.objy:
                #oldrect = self.BoundingRect
                #oldrect.translate(self.objx*1.5, self.objy*1.5)
                updRect = QtCore.QRectF(self.x(), self.y(), self.BoundingRect.width(), self.BoundingRect.height())
                #self.scene().update(updRect.unite(oldrect))
                self.scene().update(updRect)
                
                self.LevelRect.moveTo((x+xOffset) / 16, (y+yOffset) / 16)
                
                if hasattr(self, 'aux'):
                    auxUpdRect = QtCore.QRectF(self.x()+self.aux.x(), self.y()+self.aux.y(), self.aux.BoundingRect.width(), self.aux.BoundingRect.height())
                    self.scene().update(auxUpdRect)
                
                oldx = self.objx
                oldy = self.objy
                self.objx = x
                self.objy = y
                if self.positionChanged != None:
                    self.positionChanged(self, oldx, oldy, x, y)
                
                SetDirty()
            
            return newpos
        
        return QtGui.QGraphicsItem.itemChange(self, change, value)
    
    def mousePressEvent(self, event):
        """Overrides mouse pressing events if needed for cloning"""
        if event.button() == QtCore.Qt.LeftButton:
            if QtGui.QApplication.keyboardModifiers() == QtCore.Qt.ControlModifier:
                newitem = SpriteEditorItem(self.type, self.objx, self.objy, self.spritedata)
                Level.sprites.append(newitem)
                mainWindow.scene.addItem(newitem)
                mainWindow.scene.clearSelection()
                self.setSelected(True)
                SetDirty()
                return
        
        LevelEditorItem.mousePressEvent(self, event)
    
    def paint(self, painter, option, widget):
        """Paints the object"""
        painter.setClipRect(option.exposedRect)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        if self.customPaint:
            self.customPainter(self, painter)
            if self.isSelected():
                painter.setPen(QtGui.QPen(QtCore.Qt.white, 1, QtCore.Qt.DotLine))
                painter.drawRect(self.SelectionRect)
                painter.fillRect(self.SelectionRect, QtGui.QColor.fromRgb(255,255,255,64))
        else:
            if self.isSelected():
                painter.setBrush(QtGui.QBrush(QtGui.QColor.fromRgb(0,92,196,240)))
                painter.setPen(QtGui.QPen(QtCore.Qt.white, 1))
            else:
                painter.setBrush(QtGui.QBrush(QtGui.QColor.fromRgb(0,92,196,120)))
                painter.setPen(QtGui.QPen(QtCore.Qt.black, 1))
            painter.drawRoundedRect(self.RoundedRect, 4, 4)
            
            painter.setFont(self.font)
            painter.drawText(self.BoundingRect,QtCore.Qt.AlignCenter,str(self.type))
    
    def delete(self):
        """Delete the sprite from the level"""
        Level.sprites.remove(self)
        self.scene().update(self.x(), self.y(), self.BoundingRect.width(), self.BoundingRect.height())


class EntranceEditorItem(LevelEditorItem):
    """Level editor item that represents an entrance"""
    BoundingRect = QtCore.QRectF(0,0,24,24)
    SelectionRect = QtCore.QRectF(0,0,23,23)
    RoundedRect = QtCore.QRectF(1,1,22,22)
    EntranceImages = None
    
    def __init__(self, x, y, id, destarea, destentrance, type, zone, layer, path, settings):
        """Creates an entrance with specific data"""
        if EntranceEditorItem.EntranceImages == None:
            ei = []
            src = QtGui.QPixmap('reggiedata/entrances.png')
            for i in xrange(18):
                ei.append(src.copy(i*24,0,24,24))
            EntranceEditorItem.EntranceImages = ei
        
        LevelEditorItem.__init__(self)
        
        self.font = NumberFont
        self.objx = x
        self.objy = y
        self.entid = id
        self.destarea = destarea
        self.destentrance = destentrance
        self.enttype = type
        self.entzone = zone
        self.entsettings = settings
        self.entlayer = layer
        self.entpath = path
        self.listitem = None
        self.LevelRect = (QtCore.QRectF(self.objx/16, self.objy/16, 24/16, 24/16))

        self.setFlag(self.ItemIsMovable, EntrancesNonFrozen)
        self.setFlag(self.ItemIsSelectable, EntrancesNonFrozen)
        
        global DirtyOverride
        DirtyOverride += 1
        self.setPos(int(x*1.5),int(y*1.5))
        DirtyOverride -= 1
        
        self.setZValue(25001)
        self.UpdateTooltip()
    
    def UpdateTooltip(self):
        """Updates the entrance object's tooltip"""
        if self.enttype >= len(EntranceTypeNames):
            name = 'Unknown'
        else:
            name = EntranceTypeNames[self.enttype]
        
        if (self.entsettings & 0x80) != 0:
            destination = '(cannot be entered)'
        else:
            if self.destarea == 0:
                destination = '(arrives at entry point %d in this area)' % self.destentrance
            else:
                destination = '(arrives at entry point %d in area %d)' % (self.destentrance,self.destarea)
        
        self.name = name
        self.destination = destination
        self.setToolTip('<b>Entry Point %d:</b><br>Type: %s<br><i>%s</i>' % (self.entid,name,destination))
    
    def ListString(self):
        """Returns a string that can be used to describe the entrance in a list"""
        if self.enttype >= len(EntranceTypeNames):
            name = 'Unknown'
        else:
            name = EntranceTypeNames[self.enttype]
        
        if (self.entsettings & 0x80) != 0:
            return '%d: %s (cannot be entered; at %d,%d)' % (self.entid,name,self.objx,self.objy)
        else:
            return '%d: %s (enterable; at %d,%d)' % (self.entid,name,self.objx,self.objy)
    
    def paint(self, painter, option, widget):
        """Paints the object"""
        painter.setClipRect(option.exposedRect)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        if self.isSelected():
            painter.setBrush(QtGui.QBrush(QtGui.QColor.fromRgb(190,0,0,240)))
            painter.setPen(QtGui.QPen(QtCore.Qt.white, 1))
        else:
            painter.setBrush(QtGui.QBrush(QtGui.QColor.fromRgb(190,0,0,120)))
            painter.setPen(QtGui.QPen(QtCore.Qt.black, 1))
        painter.drawRoundedRect(self.RoundedRect, 4, 4)
        
        icontype = 0
        enttype = self.enttype
        if enttype == 0 or enttype == 1: icontype = 1 # normal
        if enttype == 2: icontype = 2 # door exit
        if enttype == 3: icontype = 4 # pipe up
        if enttype == 4: icontype = 5 # pipe down
        if enttype == 5: icontype = 6 # pipe left
        if enttype == 6: icontype = 7 # pipe right
        if enttype == 8: icontype = 12 # ground pound
        if enttype == 9: icontype = 13 # sliding
        #0F/15 is unknown?
        if enttype == 16: icontype = 8 # mini pipe up
        if enttype == 17: icontype = 9 # mini pipe down
        if enttype == 18: icontype = 10 # mini pipe left
        if enttype == 19: icontype = 11 # mini pipe right
        if enttype == 20: icontype = 15 # jump out facing right
        if enttype == 21: icontype = 17 # vine entrance
        if enttype == 23: icontype = 14 # boss battle entrance
        if enttype == 24: icontype = 16 # jump out facing left
        if enttype == 27: icontype = 3 # door entrance
        
        painter.drawPixmap(0,0,EntranceEditorItem.EntranceImages[icontype])
        
        #painter.drawText(self.BoundingRect,QtCore.Qt.AlignLeft,str(self.entid))
        painter.setFont(self.font)
        painter.drawText(3,12,str(self.entid))
        
        if self.isSelected():
            #painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
            #painter.setPen(QtGui.QPen(QtCore.Qt.black, 1, QtCore.Qt.DotLine))
            #painter.drawRect(self.SelectionRect)
            pass
    
    def delete(self):
        """Delete the entrance from the level"""
        elist = mainWindow.entranceList
        mainWindow.UpdateFlag = True
        elist.takeItem(elist.row(self.listitem))
        mainWindow.UpdateFlag = False
        elist.selectionModel().clearSelection()
        Level.entrances.remove(self)
        self.scene().update(self.x(), self.y(), self.BoundingRect.width(), self.BoundingRect.height())


class LevelOverviewWidget(QtGui.QWidget):
    """Widget that shows an overview of the level and can be clicked to move the view"""
    moveIt = QtCore.pyqtSignal(int, int)
    
    def __init__(self):
        """Constructor for the level overview widget"""
        QtGui.QWidget.__init__(self)
        self.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.MinimumExpanding, QtGui.QSizePolicy.MinimumExpanding))
            
        self.bgbrush = QtGui.QBrush(QtGui.QColor.fromRgb(119,136,153))
        self.objbrush = QtGui.QBrush(QtGui.QColor.fromRgb(255,255,255))
        self.viewbrush = QtGui.QBrush(QtGui.QColor.fromRgb(47,79,79,120))
        self.view = QtCore.QRectF(0,0,0,0)
        self.spritebrush = QtGui.QBrush(QtGui.QColor.fromRgb(0,92,196))
        self.entrancebrush = QtGui.QBrush(QtGui.QColor.fromRgb(255,0,0))
        self.locationbrush = QtGui.QBrush(QtGui.QColor.fromRgb(114,42,188,50))
        
        self.scale = 0.375
        self.maxX = 1
        self.maxY = 1
        self.CalcSize()
        self.Rescale()

        self.Xposlocator = 0
        self.Yposlocator = 0
        self.Hlocator = 50
        self.Wlocator = 80
        self.mainWindowScale = 1
    
    def Reset(self):
        """Resets the max and scale variables"""
        self.scale = 0.375
        self.maxX = 1
        self.maxY = 1
        self.CalcSize()
        self.Rescale()
    
    def CalcSize(self):
        """Calculates all the required sizes for this scale"""
        self.posmult = 24.0 / self.scale
    
    def mouseMoveEvent(self, event):
        """Handles mouse movement over the widget"""
        QtGui.QWidget.mouseMoveEvent(self, event)
        
        if event.buttons() == QtCore.Qt.LeftButton:
            self.moveIt.emit(event.pos().x() * self.posmult, event.pos().y() * self.posmult)
    
    def mousePressEvent(self, event):
        """Handles mouse pressing events over the widget"""
        QtGui.QWidget.mousePressEvent(self, event)
        
        if event.button() == QtCore.Qt.LeftButton:
            self.moveIt.emit(event.pos().x() * self.posmult, event.pos().y() * self.posmult)
    
    def paintEvent(self, event):
        """Paints the level overview widget"""

        if not hasattr(Level, 'layers'):
            # fixes race condition where this widget is painted after
            # the level is created, but before it's loaded
            return
        
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        self.Rescale()
        painter.scale(self.scale, self.scale)
        painter.fillRect(0, 0, 1024, 512, self.bgbrush)
        
        maxX = self.maxX
        maxY = self.maxY
        dr = painter.drawRect
        fr = painter.fillRect
        
        maxX = 0
        maxY = 0
        
        
        b = self.viewbrush
        painter.setPen(QtGui.QPen(QtGui.QColor.fromRgb(0,255,255), 1))
                        
        for zone in Level.zones:
            x = zone.objx / 16
            y = zone.objy / 16
            width = zone.width / 16
            height = zone.height / 16
            fr(x, y, width, height, b)
            dr(x, y, width, height)
            if x+width > maxX:
                maxX = x+width
            if y+height > maxY:
                maxY = y+height
        
        b = self.objbrush
        
        for layer in Level.layers:
            for obj in layer:
                fr(obj.LevelRect, b)
                if obj.objx > maxX:
                    maxX = obj.objx
                if obj.objy > maxY:
                    maxY = obj.objy


        b = self.spritebrush
                    
        for sprite in Level.sprites:
            fr(sprite.LevelRect, b)
            if sprite.objx/16 > maxX:
                maxX = sprite.objx/16
            if sprite.objy/16 > maxY:
                maxY = sprite.objy/16

    
        b = self.entrancebrush
        
        for ent in Level.entrances:
            fr(ent.LevelRect, b)
            if ent.objx/16 > maxX:
                maxX = ent.objx/16
            if ent.objy/16 > maxY:
                maxY = ent.objy/16


        b = self.locationbrush
        painter.setPen(QtGui.QPen(QtCore.Qt.black, 1))
        
        for location in Level.locations:
            x = location.objx / 16
            y = location.objy / 16
            width = location.width / 16
            height = location.height / 16
            fr(x, y, width, height, b)
            dr(x, y, width, height)
            if x+width > maxX:
                maxX = x+width
            if y+height > maxY:
                maxY = y+height        
        
        self.maxX = maxX
        self.maxY = maxY
        
        b = self.locationbrush
        painter.setPen(QtGui.QPen(QtCore.Qt.blue, 1))
        painter.drawRect(self.Xposlocator/24/self.mainWindowScale, self.Yposlocator/24/self.mainWindowScale, self.Wlocator/24/self.mainWindowScale, self.Hlocator/24/self.mainWindowScale)

    
    def Rescale(self):            
        self.Xscale = (float(self.width())/float(self.maxX+45))
        self.Yscale = (float(self.height())/float(self.maxY+25))

        if self.Xscale <= self.Yscale:
            self.scale = self.Xscale
        else:
            self.scale = self.Yscale
        
        if self.scale == 0: self.scale = 1
        
        self.CalcSize()
        
        
    
       
class ObjectPickerWidget(QtGui.QListView):
    """Widget that shows a list of available objects"""
    
    def __init__(self):
        """Initialises the widget"""
        
        QtGui.QListView.__init__(self)
        self.setFlow(QtGui.QListView.LeftToRight)
        self.setLayoutMode(QtGui.QListView.SinglePass)
        self.setMovement(QtGui.QListView.Static)
        self.setResizeMode(QtGui.QListView.Adjust)
        self.setWrapping(True)
        
        self.m0 = ObjectPickerWidget.ObjectListModel()
        self.m1 = ObjectPickerWidget.ObjectListModel()
        self.m2 = ObjectPickerWidget.ObjectListModel()
        self.m3 = ObjectPickerWidget.ObjectListModel()
        self.setModel(self.m0)
        
        self.setItemDelegate(ObjectPickerWidget.ObjectItemDelegate())
        
        self.clicked.connect(self.HandleObjReplace)
    
    def LoadFromTilesets(self):
        """Renders all the object previews"""
        self.m0.LoadFromTileset(0)
        self.m1.LoadFromTileset(1)
        self.m2.LoadFromTileset(2)
        self.m3.LoadFromTileset(3)
    
    def ShowTileset(self, id):
        """Shows a specific tileset in the picker"""
        sel = self.currentIndex().row()
        if id == 0: self.setModel(self.m0)
        if id == 1: self.setModel(self.m1)
        if id == 2: self.setModel(self.m2)
        if id == 3: self.setModel(self.m3)
        self.setCurrentIndex(self.model().index(sel, 0, QtCore.QModelIndex()))
    
    @QtCore.pyqtSlot(QtCore.QModelIndex, QtCore.QModelIndex)
    def currentChanged(self, current, previous):
        """Throws a signal when the selected object changed"""
        self.ObjChanged.emit(current.row())
    
    @QtCore.pyqtSlot(QtCore.QModelIndex)
    def HandleObjReplace(self, index):
        """Throws a signal when the selected object is used as a replacement"""
        if QtGui.QApplication.keyboardModifiers() == QtCore.Qt.AltModifier:
            self.ObjReplace.emit(index.row())
    
    ObjChanged = QtCore.pyqtSignal(int)
    ObjReplace = QtCore.pyqtSignal(int)
    
    
    class ObjectItemDelegate(QtGui.QAbstractItemDelegate):
        """Handles tileset objects and their rendering"""
        
        def __init__(self):
            """Initialises the delegate"""
            QtGui.QAbstractItemDelegate.__init__(self)
        
        def paint(self, painter, option, index):
            """Paints an object"""
            if option.state & QtGui.QStyle.State_Selected:
                painter.fillRect(option.rect, option.palette.highlight())
            
            p = index.model().data(index, QtCore.Qt.DecorationRole)
            painter.drawPixmap(option.rect.x()+2, option.rect.y()+2, p)
            #painter.drawText(option.rect, str(index.row()))
        
        def sizeHint(self, option, index):
            """Returns the size for the object"""
            p = index.model().data(index, QtCore.Qt.UserRole)
            return p
            #return QtCore.QSize(76,76)
    
    
    class ObjectListModel(QtCore.QAbstractListModel):
        """Model containing all the objects in a tileset"""
        
        def __init__(self):
            """Initialises the model"""
            self.items = []
            self.ritems = []
            self.itemsize = []
            QtCore.QAbstractListModel.__init__(self)
            
            #for i in xrange(256):
            #    self.items.append(None)
            #    self.ritems.append(None)
        
        def rowCount(self, parent=None):
            """Required by Qt"""
            return len(self.items)
        
        def data(self, index, role=QtCore.Qt.DisplayRole):
            """Get what we have for a specific row"""
            if not index.isValid(): return None
            n = index.row()
            if n < 0: return None
            if n >= len(self.items): return None
            
            if role == QtCore.Qt.DecorationRole:
                return self.ritems[n]
            
            if role == QtCore.Qt.BackgroundRole:
                return QtGui.qApp.palette().base()
            
            if role == QtCore.Qt.UserRole:
                return self.itemsize[n]
            
            if role == QtCore.Qt.ToolTipRole:
                return self.tooltips[n]
            
            return None
        
        def LoadFromTileset(self, idx):
            """Renders all the object previews for the model"""
            if ObjectDefinitions[idx] == None: return
            
            # begin/endResetModel are only in Qt 4.6...
            if QtCompatVersion >= 0x40600:
                self.beginResetModel()
            
            self.items = []
            self.ritems = []
            self.itemsize = []
            self.tooltips = []
            defs = ObjectDefinitions[idx]
            
            for i in xrange(256):
                if defs[i] == None: break
                obj = RenderObject(idx, i, defs[i].width, defs[i].height, True)
                self.items.append(obj)
                
                pm = QtGui.QPixmap(defs[i].width * 24, defs[i].height * 24)
                pm.fill(QtCore.Qt.transparent)
                p = QtGui.QPainter()
                p.begin(pm)
                y = 0
                
                for row in obj:
                    x = 0
                    for tile in row:
                        if tile != -1:
                            if isinstance(Tiles[tile], QtGui.QImage):
                                p.drawImage(x, y, Tiles[tile])
                            else:
                                p.drawPixmap(x, y, Tiles[tile])
                        x += 24
                    y += 24
                p.end()
                
                self.ritems.append(pm)
                self.itemsize.append(QtCore.QSize(defs[i].width * 24 + 4, defs[i].height * 24 + 4))
                if idx == 0 and i in ObjDesc:
                    self.tooltips.append('<b>Object %d:</b><br>%s' % (i, ObjDesc[i]))
                else:
                    self.tooltips.append('Object %d' % i)
            
            if QtCompatVersion >= 0x40600:
                self.endResetModel()
            else:
                self.reset()


class SpritePickerWidget(QtGui.QTreeWidget):
    """Widget that shows a list of available sprites"""
    
    def __init__(self):
        """Initialises the widget"""
        
        QtGui.QTreeWidget.__init__(self)
        self.setColumnCount(1)
        self.setHeaderHidden(True)
        self.setIndentation(16)
        self.currentItemChanged.connect(self.HandleItemChange)
        
        LoadSpriteData()
        LoadSpriteCategories()
        
        sprarea = QtGui.QTreeWidgetItem()
        sprarea.setText(0, "Paint New Sprite Area/Location")
        sprarea.setData(0, QtCore.Qt.UserRole, 1000)
        self.addTopLevelItem(sprarea)
        
        for viewname, view, nodelist in SpriteCategories:
            for catname, category in view:
                cnode = QtGui.QTreeWidgetItem()
                cnode.setText(0, catname)
                cnode.setData(0, QtCore.Qt.UserRole, -1)
                
                isSearch = (catname == 'Search Results')
                if isSearch:
                    self.SearchResultsCategory = cnode
                    SearchableItems = []
                
                for id in category:
                    snode = QtGui.QTreeWidgetItem()
                    if id == 9999:
                        snode.setText(0, 'No sprites found')
                        snode.setData(0, QtCore.Qt.UserRole, -2)
                        self.NoSpritesFound = snode
                    else:
                        snode.setText(0, '%d: %s' % (id, Sprites[id].name))
                        snode.setData(0, QtCore.Qt.UserRole, id)
                    
                    if isSearch:
                        SearchableItems.append(snode)
                    
                    cnode.addChild(snode)
                
                self.addTopLevelItem(cnode)
                cnode.setHidden(True)
                nodelist.append(cnode)
        
        self.ShownSearchResults = SearchableItems
        self.NoSpritesFound.setHidden(True)
        
        self.itemClicked.connect(self.HandleSprReplace)
    
    
    def SwitchView(self, view):
        """Changes the selected sprite view"""
        
        for i in xrange(1, self.topLevelItemCount()):
            self.topLevelItem(i).setHidden(True)
        
        for node in view[2]:
            node.setHidden(False)
    
    
    @QtCore.pyqtSlot(QtGui.QTreeWidgetItem, QtGui.QTreeWidgetItem)
    def HandleItemChange(self, current, previous):
        """Throws a signal when the selected object changed"""
        id = current.data(0, QtCore.Qt.UserRole).toPyObject()
        if id != -1:
            self.SpriteChanged.emit(id)
    
    
    def SetSearchString(self, searchfor):
        """Shows the items containing that string"""
        check = self.SearchResultsCategory
        
        rawresults = self.findItems(searchfor, QtCore.Qt.MatchContains | QtCore.Qt.MatchRecursive)
        results = filter((lambda x: x.parent() == check), rawresults)
        
        for x in self.ShownSearchResults: x.setHidden(True)
        for x in results: x.setHidden(False)
        self.ShownSearchResults = results
        
        self.NoSpritesFound.setHidden((len(results) != 0))
        self.SearchResultsCategory.setExpanded(True)
    
    
    @QtCore.pyqtSlot(QtGui.QTreeWidgetItem, int)
    def HandleSprReplace(self, item, column):
        """Throws a signal when the selected sprite is used as a replacement"""
        if QtGui.QApplication.keyboardModifiers() == QtCore.Qt.AltModifier:
            id = item.data(0, QtCore.Qt.UserRole).toPyObject()
            if id != -1:
                self.SpriteReplace.emit(id)
    
    SpriteChanged = QtCore.pyqtSignal(int)
    SpriteReplace = QtCore.pyqtSignal(int)


class SpriteEditorWidget(QtGui.QWidget):
    """Widget for editing sprite data"""
    DataUpdate = QtCore.pyqtSignal('PyQt_PyObject')
    
    def __init__(self, defaultmode=False):
        """Constructor"""
        QtGui.QWidget.__init__(self)
        self.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Fixed))
        
        # create the raw editor
        font = QtGui.QFont()
        font.setPointSize(8)
        editbox = QtGui.QLabel("Modify Raw Data:")
        editbox.setFont(font)
        edit = QtGui.QLineEdit()
        edit.textEdited.connect(self.HandleRawDataEdited)
        self.raweditor = edit
        
        editboxlayout = QtGui.QHBoxLayout()
        editboxlayout.addWidget(editbox)        
        editboxlayout.addWidget(edit)
        editboxlayout.setStretch(1, 1)
        
        # "Editing Sprite #" label
        self.spriteLabel = QtGui.QLabel('-')
        self.spriteLabel.setWordWrap(True)
        
        self.noteButton = QtGui.QToolButton()
        self.noteButton.setIcon(GetIcon('note'))
        self.noteButton.setText('Notes')
        self.noteButton.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.noteButton.setAutoRaise(True)
        self.noteButton.clicked.connect(self.ShowNoteTooltip)
        
        toplayout = QtGui.QHBoxLayout()
        toplayout.addWidget(self.spriteLabel)
        toplayout.addWidget(self.noteButton)
        toplayout.setStretch(0, 1)
        
        subLayout = QtGui.QVBoxLayout()
        subLayout.setMargin(0)
        
        # create a layout         
        mainLayout = QtGui.QVBoxLayout()
        mainLayout.addLayout(toplayout)
        mainLayout.addLayout(subLayout)
        
        layout = QtGui.QGridLayout()
        self.editorlayout = layout
        subLayout.addLayout(layout)
        subLayout.addLayout(editboxlayout)
        
        self.setLayout(mainLayout)
        
        self.spritetype = -1
        self.data = '\0\0\0\0\0\0\0\0'
        self.fields = []
        self.UpdateFlag = False
        self.DefaultMode = defaultmode
    
    
    class PropertyDecoder(QtCore.QObject):
        """Base class for all the sprite data decoder/encoders"""
        updateData = QtCore.pyqtSignal('PyQt_PyObject')
        
        def __init__(self):
            """Generic constructor"""
            QtCore.QObject.__init__(self)
        
        def retrieve(self, data):
            """Extracts the value from the specified nybble(s)"""
            nybble = self.nybble
            
            if isinstance(nybble, tuple):
                if nybble[1] == (nybble[0] + 2) and (nybble[0] | 1) == 0:
                    # optimise if it's just one byte
                    return ord(data[nybble[0] >> 1])
                else:
                    # we have to calculate it sadly
                    # just do it by looping, shouldn't be that bad
                    value = 0
                    for n in xrange(nybble[0], nybble[1]):
                        value <<= 4
                        value |= (ord(data[n >> 1]) >> (0 if (n & 1) == 1 else 4)) & 15
                    return value
            else:
                # we just want one nybble
                return (ord(data[nybble >> 1]) >> (0 if (nybble & 1) == 1 else 4)) & 15
        
        
        def insertvalue(self, data, value):
            """Assigns a value to the specified nybble(s)"""
            nybble = self.nybble
            sdata = list(data)
            
            if isinstance(nybble, tuple):
                if nybble[1] == (nybble[0] + 2) and (nybble[0] | 1) == 0:
                    # just one byte, this is easier
                    sdata[nybble[0] >> 1] = chr(value & 255)
                else:
                    # AAAAAAAAAAA
                    for n in reversed(xrange(nybble[0], nybble[1])):
                        cbyte = ord(sdata[n >> 1])
                        if (n & 1) == 1:
                            cbyte = (cbyte & 240) | (value & 15)
                        else:
                            cbyte = ((value & 15) << 4) | (cbyte & 15)
                        sdata[n >> 1] = chr(cbyte)
                        value >>= 4
            else:
                # only overwrite one nybble
                cbyte = ord(sdata[nybble >> 1])
                if (nybble & 1) == 1:
                    cbyte = (cbyte & 240) | (value & 15)
                else:
                    cbyte = ((value & 15) << 4) | (cbyte & 15)
                sdata[nybble >> 1] = chr(cbyte)
            
            return ''.join(sdata)
    
    
    class CheckboxPropertyDecoder(PropertyDecoder):
        """Class that decodes/encodes sprite data to/from a checkbox"""
        
        def __init__(self, title, nybble, mask, comment, layout, row):
            """Creates the widget"""
            SpriteEditorWidget.PropertyDecoder.__init__(self)
            
            self.widget = QtGui.QCheckBox(title)
            if comment != None: self.widget.setToolTip(comment)
            self.widget.clicked.connect(self.HandleClick)
            
            if isinstance(nybble, tuple):
                length = nybble[1] - nybble[0] + 1
            else:
                length = 1
            
            xormask = 0
            for i in xrange(length):
                xormask |= 0xF << (i * 4)
            
            self.nybble = nybble
            self.mask = mask
            self.xormask = xormask
            layout.addWidget(self.widget, row, 0, 1, 2)
        
        def update(self, data):
            """Updates the value shown by the widget"""
            value = ((self.retrieve(data) & self.mask) == self.mask)
            self.widget.setChecked(value)
        
        def assign(self, data):
            """Assigns the selected value to the data"""
            value = self.retrieve(data) & (self.mask ^ self.xormask)
            if self.widget.isChecked():
                value |= self.mask
            return self.insertvalue(data, value)
        
        @QtCore.pyqtSlot(bool)
        def HandleClick(self, clicked=False):
            """Handles clicks on the checkbox"""
            self.updateData.emit(self)
    
    
    class ListPropertyDecoder(PropertyDecoder):
        """Class that decodes/encodes sprite data to/from a combobox"""
        
        def __init__(self, title, nybble, model, comment, layout, row):
            """Creates the widget"""
            SpriteEditorWidget.PropertyDecoder.__init__(self)
            
            self.model = model
            self.widget = QtGui.QComboBox()
            self.widget.setModel(model)
            if comment != None: self.widget.setToolTip(comment)
            self.widget.currentIndexChanged.connect(self.HandleIndexChanged)
            
            self.nybble = nybble
            layout.addWidget(QtGui.QLabel(title+':'), row, 0, QtCore.Qt.AlignRight)
            layout.addWidget(self.widget, row, 1)
        
        def update(self, data):
            """Updates the value shown by the widget"""
            value = self.retrieve(data)
            if not self.model.existingLookup[value]:
                self.widget.setCurrentIndex(-1)
                return
            
            i = 0
            for x in self.model.entries:
                if x[0] == value:
                    self.widget.setCurrentIndex(i)
                    break
                i += 1
        
        def assign(self, data):
            """Assigns the selected value to the data"""
            return self.insertvalue(data, self.model.entries[self.widget.currentIndex()][0])
        
        @QtCore.pyqtSlot(int)
        def HandleIndexChanged(self, index):
            """Handle the current index changing in the combobox"""
            self.updateData.emit(self)
    
    
    class ValuePropertyDecoder(PropertyDecoder):
        """Class that decodes/encodes sprite data to/from a spinbox"""
        
        def __init__(self, title, nybble, max, comment, layout, row):
            """Creates the widget"""
            SpriteEditorWidget.PropertyDecoder.__init__(self)
            
            self.widget = QtGui.QSpinBox()
            self.widget.setRange(0, max - 1)
            if comment != None: self.widget.setToolTip(comment)
            self.widget.valueChanged.connect(self.HandleValueChanged)
            
            self.nybble = nybble
            layout.addWidget(QtGui.QLabel(title+':'), row, 0, QtCore.Qt.AlignRight)
            layout.addWidget(self.widget, row, 1)
        
        def update(self, data):
            """Updates the value shown by the widget"""
            value = self.retrieve(data)
            self.widget.setValue(value)
        
        def assign(self, data):
            """Assigns the selected value to the data"""
            return self.insertvalue(data, self.widget.value())
        
        @QtCore.pyqtSlot(int)
        def HandleValueChanged(self, value):
            """Handle the value changing in the spinbox"""
            self.updateData.emit(self)
    
    
    def setSprite(self, type):
        """Change the sprite type used by the data editor"""
        if self.spritetype == type: return
        
        self.spritetype = type
        if type != 1000:
            sprite = Sprites[type]
        else:
            sprite = None
        
        # remove all the existing widgets in the layout
        layout = self.editorlayout
        for row in xrange(2, layout.rowCount()):
            for column in xrange(0, layout.columnCount()):
                w = layout.itemAtPosition(row, column)
                if w != None:
                    widget = w.widget()
                    layout.removeWidget(widget)
                    widget.setParent(None)
        
        if sprite == None:
            self.spriteLabel.setText('<b>Unidentified/Unknown Sprite (%d)</b>' % type)
            self.noteButton.setVisible(False)
            
            # use the raw editor if nothing is there
            self.raweditor.setVisible(True)
            if len(self.fields) > 0: self.fields = []
            
        else:
            self.spriteLabel.setText('<b>%s (%d)</b>' % (sprite.name, type))
            self.noteButton.setVisible((sprite.notes != None))
            self.notes = sprite.notes
            
            # create all the new fields
            fields = []
            row = 2
            
            for f in sprite.fields:
                if f[0] == 0:
                    nf = SpriteEditorWidget.CheckboxPropertyDecoder(f[1], f[2], f[3], f[4], layout, row)
                elif f[0] == 1:
                    nf = SpriteEditorWidget.ListPropertyDecoder(f[1], f[2], f[3], f[4], layout, row)
                elif f[0] == 2:
                    nf = SpriteEditorWidget.ValuePropertyDecoder(f[1], f[2], f[3], f[4], layout, row)
                
                nf.updateData.connect(self.HandleFieldUpdate)
                fields.append(nf)
                row += 1
            
            self.fields = fields
        
        # done
    
    
    def update(self):
        """Updates all the fields to display the appropriate info"""
        self.UpdateFlag = True
        
        data = self.data
        self.raweditor.setText('%02x%02x %02x%02x %02x%02x %02x%02x' % (ord(data[0]), ord(data[1]), ord(data[2]), ord(data[3]), ord(data[4]), ord(data[5]), ord(data[6]), ord(data[7])))
        #self.raweditor.setText(data.encode('hex'))
        self.raweditor.setStyleSheet('')
        
        # Go through all the data
        for f in self.fields:
            f.update(data)
        
        self.UpdateFlag = False
    
    
    @QtCore.pyqtSlot()
    def ShowNoteTooltip(self):
        QtGui.QToolTip.showText(QtGui.QCursor.pos(), self.notes, self)
    
    
    @QtCore.pyqtSlot('PyQt_PyObject')
    def HandleFieldUpdate(self, field):
        """Triggered when a field's data is updated"""
        if self.UpdateFlag: return
        
        data = field.assign(self.data)
        self.data = data
        
        self.raweditor.setText('%02x%02x %02x%02x %02x%02x %02x%02x' % (ord(data[0]), ord(data[1]), ord(data[2]), ord(data[3]), ord(data[4]), ord(data[5]), ord(data[6]), ord(data[7])))
        #self.raweditor.setText(data.encode('hex'))
        self.raweditor.setStyleSheet('')
        
        for f in self.fields:
            if f != field: f.update(data)
        
        self.DataUpdate.emit(data)
    
    
    @QtCore.pyqtSlot(QtCore.QString)
    def HandleRawDataEdited(self, text):
        """Triggered when the raw data textbox is edited"""
        
        raw = text.replace(' ', '')
        valid = False
        
        if len(text) == 16:
            try:
                data = str(raw).decode('hex')
                valid = True
            except:
                pass
        
        # if it's valid, let it go
        if valid:
            self.raweditor.setStyleSheet('')
            self.data = data
            
            self.UpdateFlag = True
            for f in self.fields: f.update(data)
            self.UpdateFlag = False
            
            self.DataUpdate.emit(data)
        else:
            self.raweditor.setStyleSheet('QLineEdit { background-color: #ffd2d2; }')


class EntranceEditorWidget(QtGui.QWidget):
    """Widget for editing entrance properties"""
    
    def __init__(self, defaultmode=False):
        """Constructor"""
        QtGui.QWidget.__init__(self)
        self.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Fixed))
        
        self.CanUseFlag8 = set([3,4,5,6,16,17,18,19])
        self.CanUseFlag4 = set([3,4,5,6])
        
        # create widgets
        self.entranceID = QtGui.QSpinBox()
        self.entranceID.setRange(0, 255)
        self.entranceID.setToolTip('Must be different from all other IDs')
        self.entranceID.valueChanged.connect(self.HandleEntranceIDChanged)
        
        self.entranceType = QtGui.QComboBox()
        LoadEntranceNames()
        self.entranceType.addItems(EntranceTypeNames)
        self.entranceType.setToolTip('Must be different from all other IDs')
        self.entranceType.activated.connect(self.HandleEntranceTypeChanged)
        
        self.destArea = QtGui.QSpinBox()
        self.destArea.setRange(0, 4)
        self.destArea.setToolTip('If this entrance leads nowhere or the destination is in this area, set this to 0.')
        self.destArea.valueChanged.connect(self.HandleDestAreaChanged)
        
        self.destEntrance = QtGui.QSpinBox()
        self.destEntrance.setRange(0, 255)
        self.destEntrance.setToolTip('If this entrance leads nowhere, set this to 0.')
        self.destEntrance.valueChanged.connect(self.HandleDestEntranceChanged)
        
        self.allowEntryCheckbox = QtGui.QCheckBox('Enterable')
        self.allowEntryCheckbox.setToolTip('<b>Enterable:</b> If this box is checked on a pipe or door entry point, Mario will be able to enter the pipe/door. If it\'s not checked, he won\'t be able to enter it. Behaviour on other types of entrances is unknown/undefined.')
        self.allowEntryCheckbox.clicked.connect(self.HandleAllowEntryClicked)
        
        self.unknownFlagCheckbox = QtGui.QCheckBox('Unknown Flag')
        self.unknownFlagCheckbox.setToolTip('<b>Unknown Flag:</b> This box is checked on a few entry/exit points in the game, but we haven\'t managed to figure out what it does (or if it does anything).')
        self.unknownFlagCheckbox.clicked.connect(self.HandleUnknownFlagClicked)
        
        self.connectedPipeCheckbox = QtGui.QCheckBox('Connected Pipe')
        self.connectedPipeCheckbox.setToolTip('<b>Connected Pipe:</b> This box allows you to enable an unused/broken feature in the game. It allows the pipe to function like the pipes in SMB3 where Mario simply goes through the pipe. However, it doesn\'t work correctly and the paths involved can\'t be edited by Reggie yet.')
        self.connectedPipeCheckbox.clicked.connect(self.HandleConnectedPipeClicked)
        
        self.connectedPipeReverseCheckbox = QtGui.QCheckBox('Connected Pipe Reverse')
        self.connectedPipeReverseCheckbox.setToolTip('<b>Connected Pipe Reverse:</b> If you\'re using connected pipes, this flag must be set on the opposite end (the one located at the end of the path).')
        self.connectedPipeReverseCheckbox.clicked.connect(self.HandleConnectedPipeReverseClicked)
        
        self.pathID = QtGui.QSpinBox()
        self.pathID.setRange(0, 255)
        self.pathID.setToolTip('<b>Path ID:</b> Use this option to set the path number that the connected pipe will follow.')
        self.pathID.valueChanged.connect(self.HandlePathIDChanged)
        
        self.forwardPipeCheckbox = QtGui.QCheckBox('Links to Forward Pipe')
        self.forwardPipeCheckbox.setToolTip('<b>Links to Forward Pipe:</b> If this option is set on a pipe, the destination entrance/area values will be ignored - Mario will pass through the pipe and then reappear several tiles ahead, coming out of a forward-facing pipe.')
        self.forwardPipeCheckbox.clicked.connect(self.HandleForwardPipeClicked)
        
        self.activeLayer = QtGui.QComboBox()
        self.activeLayer.addItems(['Layer 1', 'Layer 2', 'Layer 0'])
        self.activeLayer.setToolTip('<b>Active Layer:</b> Allows you to change the collision layer which this entrance is active on. This option is very glitchy and not used in the default levels - for almost all normal cases, you will want to use layer 1.')
        self.activeLayer.activated.connect(self.HandleActiveLayerChanged)
        
        # create a layout
        layout = QtGui.QGridLayout()
        self.setLayout(layout)
        
        # "Editing Entrance #" label
        self.editingLabel = QtGui.QLabel('-')
        layout.addWidget(self.editingLabel, 0, 0, 1, 4, QtCore.Qt.AlignTop)
        
        # add labels
        layout.addWidget(QtGui.QLabel('ID:'), 3, 0, 1, 1, QtCore.Qt.AlignRight)
        layout.addWidget(QtGui.QLabel('Type:'), 1, 0, 1, 1, QtCore.Qt.AlignRight)
        
        layout.addWidget(createHorzLine(), 2, 0, 1, 4)
        
        layout.addWidget(QtGui.QLabel('Dest. ID:'), 3, 2, 1, 1, QtCore.Qt.AlignRight)
        layout.addWidget(QtGui.QLabel('Dest. Area:'), 4, 2, 1, 1, QtCore.Qt.AlignRight)
        
        layout.addWidget(QtGui.QLabel('Active on:'), 4, 0, 1, 1, QtCore.Qt.AlignRight)
        
        self.pathIDLabel = QtGui.QLabel('Path ID:')
        
        # add the widgets
        layout.addWidget(self.entranceID, 3, 1, 1, 1)
        layout.addWidget(self.entranceType, 1, 1, 1, 3)
        
        layout.addWidget(self.destEntrance, 3, 3, 1, 1)
        layout.addWidget(self.destArea, 4, 3, 1, 1)
        
        layout.addWidget(self.allowEntryCheckbox, 5, 0, 1, 2, QtCore.Qt.AlignRight)
        layout.addWidget(self.unknownFlagCheckbox, 5, 2, 1, 2, QtCore.Qt.AlignRight)
        layout.addWidget(self.forwardPipeCheckbox, 6, 0, 1, 2, QtCore.Qt.AlignRight)
        layout.addWidget(self.connectedPipeCheckbox, 6, 2, 1, 2, QtCore.Qt.AlignRight)
        layout.addWidget(self.connectedPipeReverseCheckbox, 7, 0, 1, 2, QtCore.Qt.AlignRight)
        layout.addWidget(self.pathID, 7, 3, 1, 1, QtCore.Qt.AlignRight)
        layout.addWidget(self.pathIDLabel, 7, 2, 1, 1, QtCore.Qt.AlignRight)

        layout.addWidget(self.activeLayer, 4, 1, 1, 1, QtCore.Qt.AlignLeft)
        
        self.ent = None
        self.UpdateFlag = False
    
    
    def setEntrance(self, ent):
        """Change the entrance being edited by the editor, update all fields"""
        if self.ent == ent: return
        
        self.editingLabel.setText('<b>Editing Entry/Exit Point %d:</b>' % (ent.entid))
        self.ent = ent
        self.UpdateFlag = True
        
        self.entranceID.setValue(ent.entid)
        self.entranceType.setCurrentIndex(ent.enttype)
        self.destArea.setValue(ent.destarea)
        self.destEntrance.setValue(ent.destentrance)
        
        self.allowEntryCheckbox.setChecked(((ent.entsettings & 0x80) == 0))
        self.unknownFlagCheckbox.setChecked(((ent.entsettings & 2) != 0))
        
        self.connectedPipeCheckbox.setVisible(ent.enttype in self.CanUseFlag8)
        self.connectedPipeCheckbox.setChecked(((ent.entsettings & 8) != 0))
        
        self.connectedPipeReverseCheckbox.setVisible(ent.enttype in self.CanUseFlag8 and ((ent.entsettings & 8) != 0))
        self.connectedPipeReverseCheckbox.setChecked(((ent.entsettings & 1) != 0))
        
        self.forwardPipeCheckbox.setVisible(ent.enttype in self.CanUseFlag4)
        self.forwardPipeCheckbox.setChecked(((ent.entsettings & 4) != 0))
        
        self.pathID.setVisible(ent.enttype in self.CanUseFlag8 and ((ent.entsettings & 8) != 0))
        self.pathID.setValue(ent.entpath)
        self.pathIDLabel.setVisible(ent.enttype in self.CanUseFlag8 and ((ent.entsettings & 8) != 0))
        
        self.activeLayer.setCurrentIndex(ent.entlayer)
        
        self.UpdateFlag = False
    
    
    @QtCore.pyqtSlot(int)
    def HandleEntranceIDChanged(self, i):
        """Handler for the entrance ID changing"""
        if self.UpdateFlag: return
        SetDirty()
        self.ent.entid = i
        self.ent.update()
        self.ent.UpdateTooltip()
        self.ent.listitem.setText(self.ent.ListString())
    
    
    @QtCore.pyqtSlot(int)
    def HandleEntranceTypeChanged(self, i):
        """Handler for the entrance type changing"""
        self.connectedPipeCheckbox.setVisible(i in self.CanUseFlag8)
        self.connectedPipeReverseCheckbox.setVisible(i in self.CanUseFlag8 and ((self.ent.entsettings & 8) != 0))
        self.pathIDLabel.setVisible(i and ((self.ent.entsettings & 8) != 0))
        self.pathID.setVisible(i and ((self.ent.entsettings & 8) != 0))
        self.forwardPipeCheckbox.setVisible(i in self.CanUseFlag4)
        if self.UpdateFlag: return
        SetDirty()
        self.ent.enttype = i
        self.ent.update()
        self.ent.UpdateTooltip()
        self.ent.listitem.setText(self.ent.ListString())
    
    
    @QtCore.pyqtSlot(int)
    def HandleDestAreaChanged(self, i):
        """Handler for the destination area changing"""
        if self.UpdateFlag: return
        SetDirty()
        self.ent.destarea = i
        self.ent.UpdateTooltip()
        self.ent.listitem.setText(self.ent.ListString())
    
    
    @QtCore.pyqtSlot(int)
    def HandleDestEntranceChanged(self, i):
        """Handler for the destination entrance changing"""
        if self.UpdateFlag: return
        SetDirty()
        self.ent.destentrance = i
        self.ent.UpdateTooltip()
        self.ent.listitem.setText(self.ent.ListString())
    
    
    @QtCore.pyqtSlot(bool)
    def HandleAllowEntryClicked(self, checked):
        """Handle for the Allow Entry checkbox being clicked"""
        if self.UpdateFlag: return
        SetDirty()
        if not checked:
            self.ent.entsettings |= 0x80
        else:
            self.ent.entsettings &= ~0x80
        self.ent.UpdateTooltip()
        self.ent.listitem.setText(self.ent.ListString())
    
    
    @QtCore.pyqtSlot(bool)
    def HandleUnknownFlagClicked(self, checked):
        """Handle for the Unknown Flag checkbox being clicked"""
        if self.UpdateFlag: return
        SetDirty()
        if checked:
            self.ent.entsettings |= 2
        else:
            self.ent.entsettings &= ~2
    
    
    @QtCore.pyqtSlot(bool)
    def HandleConnectedPipeClicked(self, checked):
        """Handle for the connected pipe checkbox being clicked"""
        self.connectedPipeReverseCheckbox.setVisible(checked)
        self.pathID.setVisible(checked)
        self.pathIDLabel.setVisible(checked)
        if self.UpdateFlag: return
        SetDirty()
        if checked:
            self.ent.entsettings |= 8
        else:
            self.ent.entsettings &= ~8
    
    @QtCore.pyqtSlot(bool)
    def HandleConnectedPipeReverseClicked(self, checked):
        """Handle for the connected pipe reverse checkbox being clicked"""
        if self.UpdateFlag: return
        SetDirty()
        if checked:
            self.ent.entsettings |= 1
        else:
            self.ent.entsettings &= ~1
    
    @QtCore.pyqtSlot(int)
    def HandlePathIDChanged(self, i):
        """Handler for the path ID changing"""
        if self.UpdateFlag: return
        SetDirty()
        self.ent.entpath = i
    
    @QtCore.pyqtSlot(bool)
    def HandleForwardPipeClicked(self, checked):
        """Handle for the forward pipe checkbox being clicked"""
        if self.UpdateFlag: return
        SetDirty()
        if checked:
            self.ent.entsettings |= 4
        else:
            self.ent.entsettings &= ~4
    
    @QtCore.pyqtSlot(int)
    def HandleActiveLayerChanged(self, i):
        """Handler for the active layer changing"""
        if self.UpdateFlag: return
        SetDirty()
        self.ent.entlayer = i


class LocationEditorWidget(QtGui.QWidget):
    """Widget for editing sprite area properties"""
    
    def __init__(self, defaultmode=False):
        """Constructor"""
        QtGui.QWidget.__init__(self)
        self.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Fixed))
        
        # create widgets
        self.locationID = QtGui.QSpinBox()
        self.locationID.setToolTip('Must be different from all other IDs')
        self.locationID.setRange(0, 255)
        self.locationID.valueChanged.connect(self.HandleLocationIDChanged)

        self.locationX = QtGui.QSpinBox()
        self.locationX.setToolTip('Specifies the X position of the Sprite location')
        self.locationX.setRange(16, 65535)
        self.locationX.valueChanged.connect(self.HandleLocationXChanged)
        
        self.locationY = QtGui.QSpinBox()
        self.locationY.setToolTip('Specifies the Y position of the Sprite location')
        self.locationY.setRange(16, 65535)
        self.locationY.valueChanged.connect(self.HandleLocationYChanged)
        
        self.locationWidth = QtGui.QSpinBox()
        self.locationWidth.setToolTip('Specifies the width of the Sprite location')
        self.locationWidth.setRange(0, 65535)
        self.locationWidth.valueChanged.connect(self.HandleLocationWidthChanged)
        
        self.locationHeight = QtGui.QSpinBox()
        self.locationHeight.setToolTip('Specifies the height of the Sprite location')
        self.locationHeight.setRange(0, 65535)
        self.locationHeight.valueChanged.connect(self.HandleLocationHeightChanged)
        
        self.snapButton = QtGui.QPushButton('Snap to Grid')
        self.snapButton.clicked.connect(self.HandleSnapToGrid)
        
        # create a layout
        layout = QtGui.QGridLayout()
        self.setLayout(layout)
        
        # "Editing Location #" label
        self.editingLabel = QtGui.QLabel('-')
        layout.addWidget(self.editingLabel, 0, 0, 1, 4, QtCore.Qt.AlignTop)
        
        # add labels
        layout.addWidget(QtGui.QLabel('ID:'), 1, 0, 1, 1, QtCore.Qt.AlignRight)
        
        layout.addWidget(createHorzLine(), 2, 0, 1, 4)
        
        layout.addWidget(QtGui.QLabel('X pos:'), 3, 0, 1, 1, QtCore.Qt.AlignRight)
        layout.addWidget(QtGui.QLabel('Y pos:'), 4, 0, 1, 1, QtCore.Qt.AlignRight)
        
        layout.addWidget(QtGui.QLabel('Width:'), 3, 2, 1, 1, QtCore.Qt.AlignRight)
        layout.addWidget(QtGui.QLabel('Height:'), 4, 2, 1, 1, QtCore.Qt.AlignRight)
        
        # add the widgets
        layout.addWidget(self.locationID, 1, 1, 1, 1)
        layout.addWidget(self.snapButton, 1, 3, 1, 1)
        
        layout.addWidget(self.locationX, 3, 1, 1, 1)
        layout.addWidget(self.locationY, 4, 1, 1, 1)
        
        layout.addWidget(self.locationWidth, 3, 3, 1, 1)
        layout.addWidget(self.locationHeight, 4, 3, 1, 1)
        
        
        self.loc = None
        self.UpdateFlag = False
    
    
    def setLocation(self, loc):
        """Change the location being edited by the editor, update all fields"""
        self.loc = loc
        self.UpdateFlag = True
        
        self.FixTitle()
        self.locationID.setValue(loc.id)
        self.locationX.setValue(loc.objx)
        self.locationY.setValue(loc.objy)
        self.locationWidth.setValue(loc.width)
        self.locationHeight.setValue(loc.height)
        
        self.UpdateFlag = False
    
    
    def FixTitle(self):
        self.editingLabel.setText('<b>Editing Sprite Area/Location %d:</b>' % (self.loc.id))
    
    
    @QtCore.pyqtSlot(int)
    def HandleLocationIDChanged(self, i):
        """Handler for the location ID changing"""
        if self.UpdateFlag: return
        SetDirty()
        self.loc.id = i
        self.loc.update()
        self.loc.UpdateTitle()
        self.FixTitle()
    
    @QtCore.pyqtSlot(int)
    def HandleLocationXChanged(self, i):
        """Handler for the location Xpos changing"""
        if self.UpdateFlag: return
        SetDirty()
        self.loc.objx = i
        self.loc.setX(int(i*1.5))
        self.loc.UpdateRects()
        self.loc.update()
    
    @QtCore.pyqtSlot(int)
    def HandleLocationYChanged(self, i):
        """Handler for the location Y pos changing"""
        if self.UpdateFlag: return
        SetDirty()
        self.loc.objy = i
        self.loc.setY(int(i*1.5))
        self.loc.UpdateRects()
        self.loc.update()
        
    @QtCore.pyqtSlot(int)
    def HandleLocationWidthChanged(self, i):
        """Handler for the location width changing"""
        if self.UpdateFlag: return
        SetDirty()
        self.loc.width = i
        self.loc.UpdateRects()
        self.loc.update()
        
    @QtCore.pyqtSlot(int)
    def HandleLocationHeightChanged(self, i):
        """Handler for the location height changing"""
        if self.UpdateFlag: return
        SetDirty()
        self.loc.height = i
        self.loc.UpdateRects()
        self.loc.update()
    
    @QtCore.pyqtSlot()
    def HandleSnapToGrid(self):
        """Snaps the current location to an 8x8 grid"""
        SetDirty()
        
        loc = self.loc
        left = loc.objx
        top = loc.objy
        right = left+loc.width
        bottom = top+loc.height
        
        if left % 8 < 4:
            left -= (left % 8)
        else:
            left += 8 - (left % 8)
        
        if top % 8 < 4:
            top -= (top % 8)
        else:
            top += 8 - (top % 8)
        
        if right % 8 < 4:
            right -= (right % 8)
        else:
            right += 8 - (right % 8)
        
        if bottom % 8 < 4:
            bottom -= (bottom % 8)
        else:
            bottom += 8 - (bottom % 8)
        
        if right <= left: right += 8
        if bottom <= top: bottom += 8
        
        loc.objx = left
        loc.objy = top
        loc.width = right - left
        loc.height = bottom - top
        
        loc.setPos(int(left*1.5), int(top*1.5))
        loc.UpdateRects()
        loc.update()
        self.setLocation(loc) # updates the fields


class LevelScene(QtGui.QGraphicsScene):
    """GraphicsView subclass for the level scene"""
    def __init__(self, *args):
        self.bgbrush = QtGui.QBrush(QtGui.QColor.fromRgb(119,136,153))
        QtGui.QGraphicsScene.__init__(self, *args)
    
    def drawBackground(self, painter, rect):
        """Draws all visible tiles"""
        painter.fillRect(rect, self.bgbrush)
        if not hasattr(Level, 'layers'): return
        
        drawrect = QtCore.QRectF(rect.x() / 24, rect.y() / 24, rect.width() / 24 + 1, rect.height() / 24 + 1)
        #print 'painting ' + repr(drawrect)
        isect = drawrect.intersects
        
        layer0 = []; l0add = layer0.append
        layer1 = []; l1add = layer1.append
        layer2 = []; l2add = layer2.append
        
        type_obj = LevelObjectEditorItem
        ii = isinstance
        
        x1 = 1024
        y1 = 512
        x2 = 0
        y2 = 0
        
        # iterate through each object
        funcs = [layer0.append, layer1.append, layer2.append]
        show = [ShowLayer0, ShowLayer1, ShowLayer2]
        for layer, add, process in zip(Level.layers, funcs, show):
            if not process: continue
            for item in layer:
                if not isect(item.LevelRect): continue
                add(item)
                xs = item.objx
                xe = xs+item.width
                ys = item.objy
                ye = ys+item.height
                if xs < x1: x1 = xs
                if xe > x2: x2 = xe
                if ys < y1: y1 = ys
                if ye > y2: y2 = ye
        
        width = x2 - x1
        height = y2 - y1
        tiles = Tiles
        
        # create and draw the tilemaps
        for layer in [layer2, layer1, layer0]:
            if len(layer) > 0:
                tmap = []
                i = 0
                while i < height:
                    tmap.append([-1] * width)
                    i += 1
                
                for item in layer:
                    startx = item.objx - x1
                    desty = item.objy - y1
                    
                    for row in item.objdata:
                        destrow = tmap[desty]
                        destx = startx
                        for tile in row:
                            if tile > 0:
                                destrow[destx] = tile
                            destx += 1
                        desty += 1
                
                painter.save()
                painter.translate(x1*24, y1*24)
                drawPixmap = painter.drawPixmap
                desty = 0
                for row in tmap:
                    destx = 0
                    for tile in row:
                        if tile > 0:
                            r = tiles[tile]
                            drawPixmap(destx, desty, r)
                        destx += 24
                    desty += 24
                painter.restore()


class LevelViewWidget(QtGui.QGraphicsView):
    """GraphicsView subclass for the level view"""
    PositionHover = QtCore.pyqtSignal(int, int)
    FrameSize = QtCore.pyqtSignal(int, int)
    
    def __init__(self, scene, parent):
        """Constructor"""
        QtGui.QGraphicsView.__init__(self, scene, parent)
        
        self.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        #self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor.fromRgb(119,136,153)))
        self.setDragMode(QtGui.QGraphicsView.RubberBandDrag)
        #self.setDragMode(QtGui.QGraphicsView.ScrollHandDrag)
        self.setMouseTracking(True)
        #self.setOptimizationFlags(QtGui.QGraphicsView.IndirectPainting)
        self.YScrollBar = QtGui.QScrollBar(QtCore.Qt.Vertical, parent)
        self.XScrollBar = QtGui.QScrollBar(QtCore.Qt.Horizontal, parent)
        self.setVerticalScrollBar(self.YScrollBar)
        self.setHorizontalScrollBar(self.XScrollBar)
            
        self.currentobj = None    
    
    def mousePressEvent(self, event):
        """Overrides mouse pressing events if needed"""
        if event.button() == QtCore.Qt.RightButton:
            if CurrentPaintType <= 3 and CurrentObject != -1:
                # paint an object
                clicked = mainWindow.view.mapToScene(event.x(), event.y())
                if clicked.x() < 0: clicked.setX(0)
                if clicked.y() < 0: clicked.setY(0)
                clickedx = int(clicked.x() / 24)
                clickedy = int(clicked.y() / 24)
                
                ln = CurrentLayer
                layer = Level.layers[CurrentLayer]
                if len(layer) == 0:
                    z = (2 - ln) * 8192
                else:
                    z = layer[-1].zValue() + 1
                
                obj = LevelObjectEditorItem(CurrentPaintType, CurrentObject, ln, clickedx, clickedy, 1, 1, z)
                layer.append(obj)
                mw = mainWindow
                obj.positionChanged = mw.HandleObjPosChange
                mw.scene.addItem(obj)
                
                self.currentobj = obj
                self.dragstartx = clickedx
                self.dragstarty = clickedy
                SetDirty()
                
            elif CurrentPaintType == 4 and CurrentSprite != -1:
                # common stuff
                clicked = mainWindow.view.mapToScene(event.x(), event.y())
                if clicked.x() < 0: clicked.setX(0)
                if clicked.y() < 0: clicked.setY(0)

                if CurrentSprite == 1000:
                    # paint a sprite area
                    clickedx = int(clicked.x() / 1.5)
                    clickedy = int(clicked.y() / 1.5)
                    
                    allID = []
                    newID = 1
                    for i in Level.locations:
                        allID.append(i.id)
                    
                    allID = set(allID) # faster "x in y" lookups for sets
                    
                    while newID <= 255:
                        if newID not in allID:
                            break
                        newID += 1
                    
                    global OverrideSnapping
                    OverrideSnapping = True
                    loc = SpriteLocationItem(clickedx, clickedy, 4, 4, newID)
                    OverrideSnapping = False
                    
                    mw = mainWindow
                    loc.positionChanged = mw.HandleLocPosChange
                    loc.sizeChanged = mw.HandleLocSizeChange
                    mw.scene.addItem(loc)
                    
                    Level.locations.append(loc)
                
                    self.currentobj = loc
                    self.dragstartx = clickedx
                    self.dragstarty = clickedy
                                            
                else:
                    # paint a sprite
                    #clickedx = int((clicked.x()) / 1.5)
                    #clickedy = int((clicked.y()) / 1.5)
                    #print 'clicked on %d,%d divided to %d,%d' % (clicked.x(),clicked.y(),clickedx,clickedy)
                    
                    clickedx = int((clicked.x() - 12) / 12) * 8
                    clickedy = int((clicked.y() - 12) / 12) * 8
                    
                    data = mainWindow.defaultDataEditor.data
                    spr = SpriteEditorItem(CurrentSprite, clickedx, clickedy, data)
                    
                    #clickedx -= int(spr.xsize / 2)
                    #clickedy -= int(spr.ysize / 2)
                    #print 'subtracted %d,%d for %d,%d' % (int(spr.xsize/2),int(spr.ysize/2),clickedx,clickedy)
                    #newX = int((int(clickedx / 8) * 12) + (spr.xoffset * 1.5))
                    #newY = int((int(clickedy / 8) * 12) + (spr.yoffset * 1.5))
                    #print 'offset is %d,%d' % (spr.xoffset,spr.yoffset)
                    #print 'moving to %d,%d' % (newX,newY)
                    #spr.setPos(newX, newY)
                    #print 'ended up at %d,%d' % (spr.x(),spr.y())
                    
                    mw = mainWindow
                    spr.positionChanged = mw.HandleSprPosChange
                    mw.scene.addItem(spr)
                    
                    Level.sprites.append(spr)
                
                    self.currentobj = spr
                    self.dragstartx = clickedx
                    self.dragstarty = clickedy
                    
                    
                SetDirty()
                
            elif CurrentPaintType == 5:
                # paint an entrance
                clicked = mainWindow.view.mapToScene(event.x(), event.y())
                if clicked.x() < 0: clicked.setX(0)
                if clicked.y() < 0: clicked.setY(0)
                clickedx = int((clicked.x() - 12) / 1.5)
                clickedy = int((clicked.y() - 12) / 1.5)
                #print '%d,%d %d,%d' % (clicked.x(), clicked.y(), clickedx, clickedy)
                
                getids = [False for x in xrange(256)]
                for ent in Level.entrances: getids[ent.entid] = True
                minimumID = getids.index(False)
                
                ent = EntranceEditorItem(clickedx, clickedy, minimumID, 0, 0, 0, 0, 0, 0, 0)
                mw = mainWindow
                ent.positionChanged = mw.HandleEntPosChange
                mw.scene.addItem(ent)
                
                elist = mw.entranceList
                # if it's the first available ID, all the other indexes should match right?
                # so I can just use the ID to insert
                ent.listitem = QtGui.QListWidgetItem(ent.ListString())
                elist.insertItem(minimumID, ent.listitem)
                
                global PaintingEntrance, PaintingEntranceListIndex
                PaintingEntrance = ent
                PaintingEntranceListIndex = minimumID
                
                Level.entrances.insert(minimumID, ent)
                
                self.currentobj = ent
                self.dragstartx = clickedx
                self.dragstarty = clickedy
                SetDirty()
            
            event.accept()
            
        elif (event.button() == QtCore.Qt.LeftButton) and (QtGui.QApplication.keyboardModifiers() == QtCore.Qt.ShiftModifier):
            mw = mainWindow
            
            pos = mw.view.mapToScene(event.x(), event.y())
            addsel = mw.scene.items(pos)
            for i in addsel:
                if (int(i.flags()) & i.ItemIsSelectable) != 0:
                    i.setSelected(not i.isSelected())
                    break
        
        else:
            QtGui.QGraphicsView.mousePressEvent(self, event)
        mainWindow.levelOverview.update()

    
    def resizeEvent(self, event):
        """Catches resize events"""
        self.FrameSize.emit(event.size().width(), event.size().height())
        event.accept()
        QtGui.QGraphicsView.resizeEvent(self, event)
        

    def mouseMoveEvent(self, event):
        """Overrides mouse movement events if needed"""
        
        pos = mainWindow.view.mapToScene(event.x(), event.y())
        if pos.x() < 0: pos.setX(0)
        if pos.y() < 0: pos.setY(0)
        self.PositionHover.emit(int(pos.x()), int(pos.y()))
        
        if event.buttons() == QtCore.Qt.RightButton and self.currentobj != None:
            obj = self.currentobj
            
            # possibly a small optimisation
            type_obj = LevelObjectEditorItem
            type_spr = SpriteEditorItem
            type_ent = EntranceEditorItem
            type_loc = SpriteLocationItem
            
            if isinstance(obj, type_obj):
                # resize/move the current object
                cx = obj.objx
                cy = obj.objy
                cwidth = obj.width
                cheight = obj.height
                
                dsx = self.dragstartx
                dsy = self.dragstarty
                clicked = mainWindow.view.mapToScene(event.x(), event.y())
                if clicked.x() < 0: clicked.setX(0)
                if clicked.y() < 0: clicked.setY(0)
                clickx = int(clicked.x() / 24)
                clicky = int(clicked.y() / 24)
                
                # allow negative width/height and treat it properly :D
                if clickx >= dsx:
                    x = dsx
                    width = clickx - dsx + 1
                else:
                    x = clickx
                    width = dsx - clickx + 1
                
                if clicky >= dsy:
                    y = dsy
                    height = clicky - dsy + 1
                else:
                    y = clicky
                    height = dsy - clicky + 1
                
                # if the position changed, set the new one
                if cx != x or cy != y:
                    obj.objx = x
                    obj.objy = y
                    obj.setPos(x * 24, y * 24)
                
                # if the size changed, recache it and update the area
                if cwidth != width or cheight != height:
                    obj.width = width
                    obj.height = height
                    obj.updateObjCache()
                    
                    oldrect = obj.BoundingRect
                    oldrect.translate(cx * 24, cy * 24)
                    newrect = QtCore.QRectF(obj.x(), obj.y(), obj.width * 24, obj.height * 24)
                    updaterect = oldrect.unite(newrect)
                    
                    obj.UpdateRects()
                    obj.scene().update(updaterect)

            elif isinstance(obj, type_loc):
                # resize/move the current location
                cx = obj.objx
                cy = obj.objy
                cwidth = obj.width
                cheight = obj.height
                
                dsx = self.dragstartx
                dsy = self.dragstarty
                clicked = mainWindow.view.mapToScene(event.x(), event.y())
                if clicked.x() < 0: clicked.setX(0)
                if clicked.y() < 0: clicked.setY(0)
                clickx = int(clicked.x() / 1.5)
                clicky = int(clicked.y() / 1.5)
                
                # allow negative width/height and treat it properly :D
                if clickx >= dsx:
                    x = dsx
                    width = clickx - dsx + 1
                else:
                    x = clickx
                    width = dsx - clickx + 1
                
                if clicky >= dsy:
                    y = dsy
                    height = clicky - dsy + 1
                else:
                    y = clicky
                    height = dsy - clicky + 1
                
                # if the position changed, set the new one
                if cx != x or cy != y:
                    obj.objx = x
                    obj.objy = y
                    
                    global OverrideSnapping
                    OverrideSnapping = True
                    obj.setPos(x * 1.5, y * 1.5)
                    OverrideSnapping = False
                
                # if the size changed, recache it and update the area
                if cwidth != width or cheight != height:
                    obj.width = width
                    obj.height = height
#                    obj.updateObjCache()
                    
                    oldrect = obj.BoundingRect
                    oldrect.translate(cx * 1.5, cy * 1.5)
                    newrect = QtCore.QRectF(obj.x(), obj.y(), obj.width * 1.5, obj.height * 1.5)
                    updaterect = oldrect.unite(newrect)
                    
                    obj.UpdateRects()
                    obj.scene().update(updaterect)


            elif isinstance(obj, type_spr):
                # move the created sprite
                clicked = mainWindow.view.mapToScene(event.x(), event.y())
                if clicked.x() < 0: clicked.setX(0)
                if clicked.y() < 0: clicked.setY(0)
                clickedx = int((clicked.x() - 12) / 12) * 8
                clickedy = int((clicked.y() - 12) / 12) * 8
                
                if obj.objx != clickedx or obj.objy != clickedy:
                    obj.objx = clickedx
                    obj.objy = clickedy
                    obj.setPos(int((clickedx+obj.xoffset) * 1.5), int((clickedy+obj.yoffset) * 1.5))
                
            elif isinstance(obj, type_ent):
                # move the created entrance
                clicked = mainWindow.view.mapToScene(event.x(), event.y())
                if clicked.x() < 0: clicked.setX(0)
                if clicked.y() < 0: clicked.setY(0)
                clickedx = int((clicked.x() - 12) / 1.5)
                clickedy = int((clicked.y() - 12) / 1.5)
                
                if obj.objx != clickedx or obj.objy != clickedy:
                    obj.objx = clickedx
                    obj.objy = clickedy
                    obj.setPos(int(clickedx * 1.5), int(clickedy * 1.5))
            
            event.accept()
        else:
            QtGui.QGraphicsView.mouseMoveEvent(self, event)
    
    
    def mouseReleaseEvent(self, event):
        """Overrides mouse release events if needed"""
        if event.button() == QtCore.Qt.RightButton:
            self.currentobj = None
            event.accept()
        else:
            QtGui.QGraphicsView.mouseReleaseEvent(self, event)
    
    
    def drawForeground(self, painter, rect):
        """Draws a grid"""
        if not GridEnabled: return
        
        Zoom = mainWindow.ZoomLevel
        drawLine = painter.drawLine
        
        if Zoom >= 50:
            startx = rect.x()
            startx -= (startx % 24)
            endx = startx + rect.width() + 24
            
            starty = rect.y()
            starty -= (starty % 24)
            endy = starty + rect.height() + 24
            
            painter.setPen(QtGui.QPen(QtGui.QColor.fromRgb(255,255,255,100), 1, QtCore.Qt.DotLine))
            
            x = startx
            y1 = rect.top()
            y2 = rect.bottom()
            while x <= endx:
                drawLine(x, starty, x, endy)
                x += 24
            
            y = starty
            x1 = rect.left()
            x2 = rect.right()
            while y <= endy:
                drawLine(startx, y, endx, y)
                y += 24
        
        
        if Zoom >= 25:
            startx = rect.x()
            startx -= (startx % 96)
            endx = startx + rect.width() + 96
            
            starty = rect.y()
            starty -= (starty % 96)
            endy = starty + rect.height() + 96
            
            painter.setPen(QtGui.QPen(QtGui.QColor.fromRgb(255,255,255,100), 1, QtCore.Qt.DashLine))
            
            x = startx
            y1 = rect.top()
            y2 = rect.bottom()
            while x <= endx:
                drawLine(x, starty, x, endy)
                x += 96
            
            y = starty
            x1 = rect.left()
            x2 = rect.right()
            while y <= endy:
                drawLine(startx, y, endx, y)
                y += 96
        
        
        startx = rect.x()
        startx -= (startx % 192)
        endx = startx + rect.width() + 192
        
        starty = rect.y()
        starty -= (starty % 192)
        endy = starty + rect.height() + 192
        
        painter.setPen(QtGui.QPen(QtGui.QColor.fromRgb(255,255,255,100), 2, QtCore.Qt.DashLine))
        
        x = startx
        y1 = rect.top()
        y2 = rect.bottom()
        while x <= endx:
            drawLine(x, starty, x, endy)
            x += 192
        
        y = starty
        x1 = rect.left()
        x2 = rect.right()
        while y <= endy:
            drawLine(startx, y, endx, y)
            y += 192
    


####################################################################
####################################################################
####################################################################

class HexSpinBox(QtGui.QSpinBox):
    class HexValidator(QtGui.QValidator):
        def __init__(self, min, max):
            QtGui.QValidator.__init__(self)
            self.valid = set('0123456789abcdef')
            self.min = min
            self.max = max
        
        def validate(self, input, pos):
            try:
                input = str(input).lower()
            except:
                return (self.Invalid, pos)
            valid = self.valid
            
            for char in input:
                if char not in valid:
                    return (self.Invalid, pos)
            
            value = int(input, 16)
            if value < self.min or value > self.max:
                return (self.Intermediate, pos)
            
            return (self.Acceptable, pos)
    
    
    def __init__(self, format='%04X', *args):
        self.format = format
        QtGui.QSpinBox.__init__(self, *args)
        self.validator = self.HexValidator(self.minimum(), self.maximum())
    
    def setMinimum(self, value):
        self.validator.min = value
        QtGui.QSpinBox.setMinimum(self, value)
    
    def setMaximum(self, value):
        self.validator.max = value
        QtGui.QSpinBox.setMaximum(self, value)
    
    def setRange(self, min, max):
        self.validator.min = min
        self.validator.max = max
        QtGui.QSpinBox.setMinimum(self, min)
        QtGui.QSpinBox.setMaximum(self, max)
    
    def validate(self, text, pos):
        return self.validator.validate(text, pos)
    
    def textFromValue(self, value):
        return self.format % value
    
    def valueFromText(self, value):
        return int(str(value), 16)

class InputBox(QtGui.QDialog):
    Type_TextBox = 1
    Type_SpinBox = 2
    Type_HexSpinBox = 3
    
    def __init__(self, type=Type_TextBox):
        QtGui.QDialog.__init__(self)
        
        self.label = QtGui.QLabel('-')
        self.label.setWordWrap(True)
        
        if type == InputBox.Type_TextBox:
            self.textbox = QtGui.QLineEdit()
            widget = self.textbox
        elif type == InputBox.Type_SpinBox:
            self.spinbox = QtGui.QSpinBox()
            widget = self.spinbox
        elif type == InputBox.Type_HexSpinBox:
            self.spinbox = HexSpinBox()
            widget = self.spinbox
        
        self.buttons = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        
        self.layout = QtGui.QVBoxLayout()
        self.layout.addWidget(self.label)
        self.layout.addWidget(widget)
        self.layout.addWidget(self.buttons)
        self.setLayout(self.layout)


class AboutDialog(QtGui.QDialog):
    """Shows the About info for Reggie"""
    def __init__(self):
        """Creates and initialises the dialog"""
        QtGui.QDialog.__init__(self)
        self.setFixedWidth(550)
        self.setFixedHeight(350)
        self.setWindowTitle('About Reggie!')
        
        f = open('reggiedata/about.html', 'r')
        data = f.read()
        f.close()
        
        self.pageWidget = QtGui.QTextBrowser()
        self.pageWidget.setHtml(data)
        
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok)
        buttonBox.accepted.connect(self.accept)

        mainLayout = QtGui.QVBoxLayout()
        mainLayout.addWidget(self.pageWidget)
        mainLayout.addWidget(buttonBox)
        self.setLayout(mainLayout)


class ObjectShiftDialog(QtGui.QDialog):
    """Lets you pick an amount to shift the selected objects by"""
    def __init__(self):
        """Creates and initialises the dialog"""
        QtGui.QDialog.__init__(self)
        self.setWindowTitle('Shift Objects')
        
        self.XOffset = QtGui.QSpinBox()
        self.XOffset.setRange(-16384, 16383)
        
        self.YOffset = QtGui.QSpinBox()
        self.YOffset.setRange(-8192, 8191)
        
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        
        moveLayout = QtGui.QFormLayout()
        offsetlabel = QtGui.QLabel('Enter an offset in pixels - each block is 16 pixels wide/high. Note that normal objects can only be placed on 16x16 boundaries, so if the offset you enter isn\'t a multiple of 16, they won\'t be moved correctly.')
        offsetlabel.setWordWrap(True)
        moveLayout.addWidget(offsetlabel)
        moveLayout.addRow('X:', self.XOffset)
        moveLayout.addRow('Y:', self.YOffset)
        
        moveGroupBox = QtGui.QGroupBox('Move objects by:')
        moveGroupBox.setLayout(moveLayout)
        
        mainLayout = QtGui.QVBoxLayout()
        mainLayout.addWidget(moveGroupBox)
        mainLayout.addWidget(buttonBox)
        self.setLayout(mainLayout)


class MetaInfoDialog(QtGui.QDialog):
    """Allows the user to enter in various meta-info to be kept in the level for display"""
    def __init__(self):
        """Creates and initialises the dialog"""
        QtGui.QDialog.__init__(self)
        self.setWindowTitle('Level Information')
        
        self.levelName = QtGui.QLineEdit()
        self.levelName.setMaxLength(32)
        self.levelName.setReadOnly(True)
        self.levelName.setMinimumWidth(320)
        self.levelName.setText(Level.Title)
        
        self.Author = QtGui.QLineEdit()
        self.Author.setMaxLength(32)
        self.Author.setReadOnly(True)
        self.Author.setMinimumWidth(320)
        self.Author.setText(Level.Author)

        self.Group = QtGui.QLineEdit()
        self.Group.setMaxLength(32)
        self.Group.setReadOnly(True)
        self.Group.setMinimumWidth(320)
        self.Group.setText(Level.Group)

        self.Website = QtGui.QLineEdit()
        self.Website.setMaxLength(64)
        self.Website.setReadOnly(True)
        self.Website.setMinimumWidth(320)
        self.Website.setText(Level.Webpage)

        self.Password = QtGui.QLineEdit()
        self.Password.setMaxLength(32)
        self.Password.textChanged.connect(self.PasswordEntry)
        self.Password.setMinimumWidth(320)

        self.changepw = QtGui.QPushButton("Add/Change Password")


        if Level.Password == '':
            self.levelName.setReadOnly(False)
            self.Author.setReadOnly(False)
            self.Group.setReadOnly(False)
            self.Website.setReadOnly(False)
            self.changepw.setDisabled(False)

        
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        buttonBox.addButton(self.changepw, buttonBox.ActionRole)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        self.changepw.clicked.connect(self.ChangeButton)
        self.changepw.setDisabled(True)
        
        self.lockedLabel = QtGui.QLabel('This level\'s information is locked.<br>Please enter the password below in order to modify it.')
        
        infoLayout = QtGui.QFormLayout()
        infoLayout.addWidget(self.lockedLabel)
        infoLayout.addRow('Password:', self.Password)
        infoLayout.addRow('Title:', self.levelName)
        infoLayout.addRow('Author:', self.Author)
        infoLayout.addRow('Group:', self.Group)
        infoLayout.addRow('Website:', self.Website)
        
        self.PasswordLabel = infoLayout.labelForField(self.Password)
        
        levelIsLocked = Level.Password != ''
        self.lockedLabel.setVisible(levelIsLocked)
        self.PasswordLabel.setVisible(levelIsLocked)
        self.Password.setVisible(levelIsLocked)
        
        infoGroupBox = QtGui.QGroupBox('Created with ' + Level.Creator)
        infoGroupBox.setLayout(infoLayout)
        
        mainLayout = QtGui.QVBoxLayout()
        mainLayout.addWidget(infoGroupBox)
        mainLayout.addWidget(buttonBox)
        self.setLayout(mainLayout)
        
        self.PasswordEntry('')

    @QtCore.pyqtSlot(str)
    def PasswordEntry(self, text):
        if text == Level.Password:
            self.levelName.setReadOnly(False)
            self.Author.setReadOnly(False)
            self.Group.setReadOnly(False)
            self.Website.setReadOnly(False)
            self.changepw.setDisabled(False)
        else:
            self.levelName.setReadOnly(True)
            self.Author.setReadOnly(True)
            self.Group.setReadOnly(True)
            self.Website.setReadOnly(True)
            self.changepw.setDisabled(True)
            
            
#   To all would be crackers who are smart enough to reach here:
#
#   Make your own damn levels.
#
#
#
#       - The management
#


    def ChangeButton(self):
        """Allows the changing of a given password"""
                
        class ChangePWDialog(QtGui.QDialog):
            """Dialog"""
            def __init__(self):
                QtGui.QDialog.__init__(self)
                self.setWindowTitle('Change Password')
                
                self.New = QtGui.QLineEdit()
                self.New.setMaxLength(64)
                self.New.textChanged.connect(self.PasswordMatch)
                self.New.setMinimumWidth(320)
                
                self.Verify = QtGui.QLineEdit()
                self.Verify.setMaxLength(64)
                self.Verify.textChanged.connect(self.PasswordMatch)
                self.Verify.setMinimumWidth(320)
                
                self.Ok = QtGui.QPushButton("OK")
                self.Cancel = QtGui.QDialogButtonBox.Cancel

                buttonBox = QtGui.QDialogButtonBox()
                buttonBox.addButton(self.Ok, buttonBox.AcceptRole)
                buttonBox.addButton(self.Cancel)

                buttonBox.accepted.connect(self.accept)
                buttonBox.rejected.connect(self.reject)
                self.Ok.setDisabled(True)
                
                infoLayout = QtGui.QFormLayout()
                infoLayout.addRow('New Password:', self.New)
                infoLayout.addRow('Verify Password:', self.Verify)
                        
                infoGroupBox = QtGui.QGroupBox('Level Information')
                
                infoLabel = QtGui.QVBoxLayout()
                infoLabel.addWidget(QtGui.QLabel("Password may be composed of any ASCII character,\nand up to 64 characters long.\n"), 0, QtCore.Qt.AlignCenter)
                infoLabel.addLayout(infoLayout)
                infoGroupBox.setLayout(infoLabel)
                
                mainLayout = QtGui.QVBoxLayout()
                mainLayout.addWidget(infoGroupBox)
                mainLayout.addWidget(buttonBox)
                self.setLayout(mainLayout)
        
            @QtCore.pyqtSlot(str)
            def PasswordMatch(self, text):
                self.Ok.setDisabled(self.New.text() != self.Verify.text() and self.New.text() != '')

        dlg = ChangePWDialog()
        if dlg.exec_() == QtGui.QDialog.Accepted:
            self.lockedLabel.setVisible(True)
            self.Password.setVisible(True)
            self.PasswordLabel.setVisible(True)
            Level.Password = dlg.Verify.text()
            self.Password.setText(Level.Password)
            SetDirty()
            
            self.levelName.setReadOnly(False)
            self.Author.setReadOnly(False)
            self.Group.setReadOnly(False)
            self.Website.setReadOnly(False)
            self.changepw.setDisabled(False)


        
#Sets up the Area Options Menu
class AreaOptionsDialog(QtGui.QDialog):
    """Dialog which lets you choose among various area options from tabs"""    
    def __init__(self):
        """Creates and initialises the tab dialog"""
        QtGui.QDialog.__init__(self)
        self.setWindowTitle('Area Options')
        
        self.tabWidget = QtGui.QTabWidget()
        self.LoadingTab = LoadingTab()
        self.TilesetsTab = TilesetsTab()
        self.tabWidget.addTab(self.TilesetsTab, "Tilesets")
        self.tabWidget.addTab(self.LoadingTab, "Settings")

        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)

        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        mainLayout = QtGui.QVBoxLayout()
        mainLayout.addWidget(self.tabWidget)
        mainLayout.addWidget(buttonBox)
        self.setLayout(mainLayout)


class LoadingTab(QtGui.QWidget):
    def __init__(self):
        QtGui.QWidget.__init__(self)
        
        self.timer = QtGui.QSpinBox()
        self.timer.setRange(0, 999)
        self.timer.setToolTip("Sets the countdown timer on load from the world map. It's possible to set different times for the midpoint area.")
        timerLabel = QtGui.QLabel("Timer:")
        self.timer.setValue(Level.timeLimit + 200)
                
        self.entrance = QtGui.QSpinBox()
        self.entrance.setRange(0, 255)
        self.entrance.setToolTip("Sets the entrance ID to load into when loading from the World Map")
        entranceLabel = QtGui.QLabel("Entrance ID:")
        self.entrance.setValue(Level.startEntrance)

        self.wrap = QtGui.QCheckBox("Wrap across Edges")
        self.wrap.setToolTip("Makes the stage edges wrap<br>Warning: This option may cause the game to crash or behave weirdly. Wrapping only works correctly where the area is set up in the right way; see Coin Battle 1 for an example.")
        self.wrap.setChecked((Level.wrapFlag & 1) != 0)
        
        settingsLayout = QtGui.QFormLayout()
        settingsLayout.addRow('Timer:', self.timer)
        settingsLayout.addRow('Entrance ID:', self.entrance)
        settingsLayout.addRow(self.wrap)
        
        self.eventChooser = QtGui.QListWidget()
        defEvent = Level.defEvents
        item = QtGui.QListWidgetItem
        checked = QtCore.Qt.Checked
        unchecked = QtCore.Qt.Unchecked
        flags = QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled
        
        for id in xrange(32):
            i = item('Event %d' % (id+1))
            value = 1 << id
            i.setCheckState(checked if (defEvent & value) != 0 else unchecked)
            i.setFlags(flags)
            self.eventChooser.addItem(i)
        
        eventLayout = QtGui.QVBoxLayout()
        eventLayout.addWidget(self.eventChooser)
        
        eventBox = QtGui.QGroupBox('Default Events')
        eventBox.setLayout(eventLayout)
        
        Layout = QtGui.QVBoxLayout()
        Layout.addLayout(settingsLayout)
        Layout.addWidget(eventBox)
        Layout.addStretch(1)
        self.setLayout(Layout)


class TilesetsTab(QtGui.QWidget):
    def __init__(self):
        QtGui.QWidget.__init__(self)
        
        self.tile0 = QtGui.QComboBox()
        self.tile1 = QtGui.QComboBox()
        self.tile2 = QtGui.QComboBox()
        self.tile3 = QtGui.QComboBox()
        
        self.widgets = [self.tile0, self.tile1, self.tile2, self.tile3]
        names = [Level.tileset0, Level.tileset1, Level.tileset2, Level.tileset3]
        slots = [self.HandleTileset0Choice, self.HandleTileset1Choice, self.HandleTileset2Choice, self.HandleTileset3Choice]
        
        self.currentChoices = [None, None, None, None]
        
        for idx, widget, name, data, slot in zip(range(4), self.widgets, names, TilesetNames, slots):
            if name == '':
                ts_index = 'None'
                custom = ''
                custom_fname = '[CUSTOM]'
            else:
                ts_index = 'Custom filename... (%s)' % name
                custom = ' (%s)' % name
                custom_fname = '[CUSTOM]' + name
            
            widget.addItem('None', '')
            for tfile, tname in data:
                text = '%s (%s)' % (tname,tfile)
                widget.addItem(text, tfile)
                if name == tfile:
                    ts_index = text
                    custom = ''
            widget.addItem('Custom filename...%s' % custom, custom_fname)
            
            item_idx = widget.findText(ts_index)
            self.currentChoices[idx] = item_idx
            
            widget.setCurrentIndex(item_idx)
            widget.activated.connect(slot)
        
        # don't allow ts0 to be removable
        self.tile0.removeItem(0)
        
        mainLayout = QtGui.QVBoxLayout()
        tile0Box = QtGui.QGroupBox("Standard Suite")
        tile1Box = QtGui.QGroupBox("Stage Suite")
        tile2Box = QtGui.QGroupBox("Background Suite")
        tile3Box = QtGui.QGroupBox("Interactive Suite")
        
        t0 = QtGui.QVBoxLayout()
        t0.addWidget(self.tile0)
        t1 = QtGui.QVBoxLayout()
        t1.addWidget(self.tile1)
        t2 = QtGui.QVBoxLayout()
        t2.addWidget(self.tile2)
        t3 = QtGui.QVBoxLayout()
        t3.addWidget(self.tile3)
        
        tile0Box.setLayout(t0)
        tile1Box.setLayout(t1)
        tile2Box.setLayout(t2)
        tile3Box.setLayout(t3)
        
        mainLayout.addWidget(tile0Box)
        mainLayout.addWidget(tile1Box)
        mainLayout.addWidget(tile2Box)
        mainLayout.addWidget(tile3Box)
        mainLayout.addStretch(1)
        self.setLayout(mainLayout)
    
    @QtCore.pyqtSlot(int)
    def HandleTileset0Choice(self, index):
        self.HandleTilesetChoice(0, index)
    
    @QtCore.pyqtSlot(int)
    def HandleTileset1Choice(self, index):
        self.HandleTilesetChoice(1, index)
    
    @QtCore.pyqtSlot(int)
    def HandleTileset2Choice(self, index):
        self.HandleTilesetChoice(2, index)
    
    @QtCore.pyqtSlot(int)
    def HandleTileset3Choice(self, index):
        self.HandleTilesetChoice(3, index)
    
    def HandleTilesetChoice(self, tileset, index):
        w = self.widgets[tileset]
        
        if index == (w.count() - 1):
            fname = str(w.itemData(index).toPyObject())
            fname = fname[8:]
            
            dbox = InputBox()
            dbox.setWindowTitle('Enter a Filename')
            dbox.label.setText('Enter the name of a custom tileset file to use. It must be placed in the game\'s Stage\\Texture folder in order for Reggie to recognise it. Do not add the ".arc" extension at the end of the filename.')
            dbox.textbox.setMaxLength(31)
            dbox.textbox.setText(fname)
            result = dbox.exec_()
            
            if result == QtGui.QDialog.Accepted:
                fname = unicode(dbox.textbox.text())
                if fname.endswith('.arc'): fname = fname[:-4]
                
                w.setItemText(index, 'Custom filename... (%s)' % fname)
                w.setItemData(index, '[CUSTOM]'+fname)
            else:
                w.setCurrentIndex(self.currentChoices[tileset])
                return
        
        self.currentChoices[tileset] = index


#Sets up the Zones Menu
class ZonesDialog(QtGui.QDialog):
    """Dialog which lets you choose among various from tabs"""    
    def __init__(self):
        """Creates and initialises the tab dialog"""
        QtGui.QDialog.__init__(self)
        self.setWindowTitle('Zones')
        
        self.tabWidget = QtGui.QTabWidget()
        
        i = 0
        self.zoneTabs = []
        for z in Level.zones:
            i = i+1
            ZoneTabName = "Zone " + str(i)
            tab = ZoneTab(z)
            self.zoneTabs.append(tab)
            self.tabWidget.addTab(tab, ZoneTabName)
                
        
        if self.tabWidget.count() > 5:
            for tab in range(0, self.tabWidget.count()):
                self.tabWidget.setTabText(tab, str(tab + 1))
                
        
        self.NewButton = QtGui.QPushButton("New")
        self.DeleteButton = QtGui.QPushButton("Delete")
        
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        buttonBox.addButton(self.NewButton, buttonBox.ActionRole);
        buttonBox.addButton(self.DeleteButton, buttonBox.ActionRole);

        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        #self.NewButton.setEnabled(len(self.zoneTabs) < 8)
        self.NewButton.clicked.connect(self.NewZone)
        self.DeleteButton.clicked.connect(self.DeleteZone)

        mainLayout = QtGui.QVBoxLayout()
        mainLayout.addWidget(self.tabWidget)
        mainLayout.addWidget(buttonBox)
        self.setLayout(mainLayout)

    @QtCore.pyqtSlot(bool)
    def NewZone(self):
        if len(self.zoneTabs) >= 8:
            result = QtGui.QMessageBox.warning(self, 'Warning', 'You are trying to add more than 8 zones to a level - keep in mind that without the proper fix to the game, this will cause your level to <b>crash</b> or have other strange issues!<br><br>Are you sure you want to do this?', QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
            if result == QtGui.QMessageBox.No:
                return
        
        a = []
        b = []

        a.append([0, 0, 0, 0, 0, 0])
        b.append([0, 0, 0, 0, 0, 10, 10, 10, 0])
        id = len(self.zoneTabs)
        z = ZoneItem(16, 16, 448, 224, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, a, b, b, id)
        ZoneTabName = "Zone " + str(id+1)
        tab = ZoneTab(z)
        self.zoneTabs.append(tab)
        self.tabWidget.addTab(tab, ZoneTabName)
        if self.tabWidget.count() > 5:
            for tab in range(0, self.tabWidget.count()):
                self.tabWidget.setTabText(tab, str(tab + 1))
        
        #self.NewButton.setEnabled(len(self.zoneTabs) < 8)
    
    
    @QtCore.pyqtSlot(bool)
    def DeleteZone(self):
        curindex = self.tabWidget.currentIndex()
        tabamount = self.tabWidget.count()
        self.tabWidget.removeTab(curindex)
        
        for tab in range(curindex, tabamount):
            if self.tabWidget.count() < 6:
                self.tabWidget.setTabText(tab, "Zone " + str(tab + 1))
            if self.tabWidget.count() > 5:
                self.tabWidget.setTabText(tab, str(tab + 1))
        
        self.zoneTabs.pop(curindex)
        if self.tabWidget.count() < 6:
            for tab in range(0, self.tabWidget.count()):
                self.tabWidget.setTabText(tab, "Zone " + str(tab + 1))
        
        #self.NewButton.setEnabled(len(self.zoneTabs) < 8)



class ZoneTab(QtGui.QWidget):
    def __init__(self, z):
        QtGui.QWidget.__init__(self)
        
        self.zoneObj = z
        
        self.createDimensions(z)
        self.createVisibility(z)
        self.createBounds(z)        
        self.createAudio(z)

        mainLayout = QtGui.QVBoxLayout()
        mainLayout.addWidget(self.Dimensions)
        mainLayout.addWidget(self.Visibility)
        mainLayout.addWidget(self.Bounds)
        mainLayout.addWidget(self.Audio)
        self.setLayout(mainLayout)



    def createDimensions(self, z):
            self.Dimensions = QtGui.QGroupBox("Dimensions")

            self.Zone_xpos = QtGui.QSpinBox()
            self.Zone_xpos.setRange(16, 65535)
            self.Zone_xpos.setToolTip("Sets the X Position of the upper left corner")
            self.Zone_xpos.setValue(z.objx)
            
            self.Zone_ypos = QtGui.QSpinBox()
            self.Zone_ypos.setRange(16, 65535)
            self.Zone_ypos.setToolTip("Sets the Y Position of the upper left corner")
            self.Zone_ypos.setValue(z.objy)
    
            self.Zone_width = QtGui.QSpinBox()
            self.Zone_width.setRange(300, 65535)
            self.Zone_width.setToolTip("Sets the width of the zone")
            self.Zone_width.setValue(z.width)
    
            self.Zone_height = QtGui.QSpinBox()
            self.Zone_height.setRange(200, 65535)
            self.Zone_height.setToolTip("Sets the height of the zone")
            self.Zone_height.setValue(z.height)
    
    
            ZonePositionLayout = QtGui.QFormLayout()
            ZonePositionLayout.addRow("X position:", self.Zone_xpos)
            ZonePositionLayout.addRow("Y position:", self.Zone_ypos)
    
            ZoneSizeLayout = QtGui.QFormLayout()
            ZoneSizeLayout.addRow("X size:", self.Zone_width)
            ZoneSizeLayout.addRow("Y size:", self.Zone_height)
    
    
            innerLayout = QtGui.QHBoxLayout()
            
            innerLayout.addLayout(ZonePositionLayout)
            innerLayout.addLayout(ZoneSizeLayout)
            self.Dimensions.setLayout(innerLayout)
    
    
    
    def createVisibility(self, z):
            self.Visibility = QtGui.QGroupBox("Rendering and Camera")
    
            self.Zone_modeldark = QtGui.QComboBox()
            self.Zone_modeldark.addItems(ZoneThemeValues)
            self.Zone_modeldark.setToolTip('<b>Zone Theme:</b> Changes the way models and parts of the background are rendered (for blurring, darkness, lava effects, and so on). Themes with * next to them are used in the game, but look the same as the overworld theme.')
            if z.modeldark < 0: z.modeldark = 0
            if z.modeldark >= len(ZoneThemeValues): z.modeldark = len(ZoneThemeValues)
            self.Zone_modeldark.setCurrentIndex(z.modeldark)
            
            self.Zone_terraindark = QtGui.QComboBox()
            self.Zone_terraindark.addItems(ZoneTerrainThemeValues)
            self.Zone_terraindark.setToolTip('<b>Terrain Theme:</b> Changes the way the terrain is rendered. It also affects the parts of the background which the normal theme doesn\'t change.')
            if z.terraindark < 0: z.terraindark = 0
            if z.terraindark >= len(ZoneTerrainThemeValues): z.terraindark = len(ZoneTerrainThemeValues)
            self.Zone_terraindark.setCurrentIndex(z.terraindark)
            
            
            self.Zone_vnormal = QtGui.QRadioButton("Normal")
            self.Zone_vnormal.setToolTip("Sets the visibility mode to normal.")
            
            self.Zone_vspotlight = QtGui.QRadioButton("Layer 0 Spotlight")
            self.Zone_vspotlight.setToolTip("Sets the visibility mode to spotlight. In Spotlight mode,\nmoving behind layer 0 objects enables a spotlight that\nfollows Mario around.")
            
            self.Zone_vfulldark = QtGui.QRadioButton("Full Darkness")
            self.Zone_vfulldark.setToolTip("Sets the visibility mode to full darkness. In full dark mode,\nthe screen is completely black and visibility is only provided\nby the available spotlight effect. Stars and some sprites\ncan enhance the default visibility.")
            
            self.Zone_visibility = QtGui.QComboBox()

            self.zv = z.visibility
            VRadioDiv = self.zv / 16

            if VRadioDiv == 0:
                self.Zone_vnormal.setChecked(True)
            elif VRadioDiv == 1:
                self.Zone_vspotlight.setChecked(True)
            elif VRadioDiv == 2:
                self.Zone_vfulldark.setChecked(True)
            elif VRadioDiv == 3:
                self.Zone_vfulldark.setChecked(True)
            
            
            self.ChangeList()
            self.Zone_vnormal.clicked.connect(self.ChangeList)
            self.Zone_vspotlight.clicked.connect(self.ChangeList)
            self.Zone_vfulldark.clicked.connect(self.ChangeList)

            
            self.Zone_xtrack = QtGui.QCheckBox()
            self.Zone_xtrack.setToolTip("Allows the camera to track Mario across the X dimension.\nTurning off this option centers the screen horizontally in\nthe view, producing a stationary camera mode.")
            if z.cammode in [0, 3, 6]:
                self.Zone_xtrack.setChecked(True)
            self.Zone_ytrack = QtGui.QCheckBox()
            self.Zone_ytrack.setToolTip("Allows the camera to track Mario across the Y dimension.\nTurning off this option centers the screen vertically in\nthe view, producing very vertically limited stages.")
            if z.cammode in [0, 1, 3, 4]:
                self.Zone_ytrack.setChecked(True)
            
   
            self.Zone_camerazoom = QtGui.QComboBox()
            self.Zone_camerazoom.setToolTip("Changes the camera zoom functionality\n   Negative values: Zoom In\n   Positive values: Zoom Out\n\nZoom Level 4 is rather glitchy")
            newItems1 = ["-2", "-1", "0", "1", "2", "3", "4"]
            self.Zone_camerazoom.addItems(newItems1)
            if z.camzoom == 8:
                self.Zone_camerazoom.setCurrentIndex(0)
            elif (z.camzoom == 9 and z.cammode in [3, 4]) or (z.camzoom in [19, 20] and z.cammode == 9):
                self.Zone_camerazoom.setCurrentIndex(1)
            elif (z.camzoom in [0, 1, 2] and z.cammode in [0, 1, 6]) or (z.camzoom in [10, 11] and z.cammode in [3, 4]) or (z.camzoom == 13 and z.cammode == 9):
                self.Zone_camerazoom.setCurrentIndex(2)
            elif z.camzoom in [5, 6, 7, 9, 10] and z.cammode in [0, 1, 6] or (z.camzoom == 12 and z.cammode == 9):
                self.Zone_camerazoom.setCurrentIndex(3)
            elif (z.camzoom in [4, 11] and z.cammode in [0, 1, 6]) or (z.camzoom in [1, 5] and z.cammode in [3, 4])  or (z.camzoom == 14 and z.cammode == 9):
                self.Zone_camerazoom.setCurrentIndex(4)
            elif (z.camzoom == 3 and z.cammode in [0, 1, 6]) or (z.camzoom == 2 and z.cammode in [3, 4]) or (z.camzoom == 15 and z.cammode == 9):
                self.Zone_camerazoom.setCurrentIndex(5)
            elif (z.camzoom == 16 and z.cammode in [0, 1, 6]) or (z.camzoom in [3, 7] and z.cammode in [3, 4]) or (z.camzoom == 16 and z.cammode == 9):
                self.Zone_camerazoom.setCurrentIndex(6)
            else:
                self.Zone_camerazoom.setCurrentIndex(2)    
                        
            self.Zone_camerabias = QtGui.QCheckBox()
            self.Zone_camerabias.setToolTip("Sets the screen bias to the left edge on load, preventing initial scrollback.\nUseful for pathed levels\n    Note: Not all zoom/mode combinations support bias")
            if z.camzoom in [1, 2, 3, 4, 5, 6, 9, 10]:
                self.Zone_camerabias.setChecked(True)
            

            ZoneZoomLayout = QtGui.QFormLayout()
            ZoneZoomLayout.addRow("Zoom Level:", self.Zone_camerazoom)
            ZoneZoomLayout.addRow("Zone Theme:", self.Zone_modeldark)
            ZoneZoomLayout.addRow("Terrain Lighting:", self.Zone_terraindark)

            ZoneCameraLayout = QtGui.QFormLayout()
            ZoneCameraLayout.addRow("X Tracking:", self.Zone_xtrack)
            ZoneCameraLayout.addRow("Y Tracking:", self.Zone_ytrack)
            ZoneCameraLayout.addRow("Bias:", self.Zone_camerabias)    

            ZoneVisibilityLayout = QtGui.QHBoxLayout()
            ZoneVisibilityLayout.addWidget(self.Zone_vnormal)
            ZoneVisibilityLayout.addWidget(self.Zone_vspotlight)
            ZoneVisibilityLayout.addWidget(self.Zone_vfulldark)
            
            
            
            TopLayout = QtGui.QHBoxLayout()
            TopLayout.addLayout(ZoneCameraLayout)
            TopLayout.addLayout(ZoneZoomLayout)
            
            InnerLayout = QtGui.QVBoxLayout()
            InnerLayout.addLayout(TopLayout)
            InnerLayout.addLayout(ZoneVisibilityLayout)
            InnerLayout.addWidget(self.Zone_visibility)
            self.Visibility.setLayout(InnerLayout)
    
    @QtCore.pyqtSlot(bool)
    def ChangeList(self):
        VRadioMod = self.zv % 16
    
        if self.Zone_vnormal.isChecked():
            self.Zone_visibility.clear()
            addList = ["Hidden", "On Top"]
            self.Zone_visibility.addItems(addList)
            self.Zone_visibility.setToolTip("Hidden - Mario is hidden when moving behind objects on Layer 0\nOn Top - Mario is displayed above Layer 0 at all times.\n\nNote: Entities behind layer 0 other than Mario are never visible")
            self.Zone_visibility.setCurrentIndex(VRadioMod)
        elif self.Zone_vspotlight.isChecked():
            self.Zone_visibility.clear()
            addList = ["Small", "Large", "Full Screen"]
            self.Zone_visibility.addItems(addList)
            self.Zone_visibility.setToolTip("Small - A small, centered spotlight affords visibility through layer 0.\nLarge - A large, centered spotlight affords visibility through layer 0\nFull Screen - the entire screen is revealed whenever Mario walks behind layer 0")
            self.Zone_visibility.setCurrentIndex(VRadioMod)
        elif self.Zone_vfulldark.isChecked():
            self.Zone_visibility.clear()
            addList = ["Large Foglight", "Lightbeam", "Large Focus Light", "Small Foglight", "Small Focus Light", "Absolute Black"]
            self.Zone_visibility.addItems(addList)
            self.Zone_visibility.setToolTip("Large Foglight - A large, organic lightsource surrounds Mario\nLightbeam - Mario is able to aim a conical lightbeam through use of the Wiimote\nLarge Focus Light - A large spotlight which changes size based upon player movement\nSmall Foglight - A small, organic lightsource surrounds Mario\nSmall Focuslight - A small spotlight which changes size based on player movement\nAbsolute Black - Visibility is provided only by fireballs, stars, and certain sprites")
            self.Zone_visibility.setCurrentIndex(VRadioMod)

        
    def createBounds(self, z):        
            self.Bounds = QtGui.QGroupBox("Bounds")
    
            #Block3 = Level.bounding[z.block3id]
            
            self.Zone_yboundup = QtGui.QSpinBox()
            self.Zone_yboundup.setRange(-32766, 32767)
            self.Zone_yboundup.setToolTip("Positive Values: Easier to scroll upwards (110 is centered)\nNegative Values: Harder to scroll upwards (30 is the top edge of the screen)\n\nValues higher than 240 can cause instant death upon screen scrolling")
            self.Zone_yboundup.setSpecialValueText("32")
            self.Zone_yboundup.setValue(z.yupperbound)
    
            self.Zone_ybounddown = QtGui.QSpinBox()
            self.Zone_ybounddown.setRange(-32766, 32767)
            self.Zone_ybounddown.setToolTip("Positive Values: Harder to scroll downwards (65 is the bottom edge of the screen)\nNegative Values: Easier to scroll downwards (95 is centered)\n\nValues higher than 100 will prevent the sceen from scrolling while Mario until Mario is offscreen")
            self.Zone_ybounddown.setValue(z.ylowerbound)
    
    
            ZoneBoundsLayout = QtGui.QFormLayout()

            ZoneBoundsLayout.addRow("Upper Bounds:", self.Zone_yboundup)
            ZoneBoundsLayout.addRow("Lower Bounds:", self.Zone_ybounddown)
    
            self.Bounds.setLayout(ZoneBoundsLayout)
    
    
    def createAudio(self, z):
            self.Audio = QtGui.QGroupBox("Audio")
    
            self.Zone_music = QtGui.QComboBox()
            self.Zone_music.setToolTip("Changes the background music")
            newItems2 = ["None", "Overworld", "Underground", "Underwater", "Mushrooms/Athletic", "Ghost House", "Pyramids", "Snow", "Lava", "Tower", "Castle", "Airship", "Bonus Area", "Drum Rolls", "Tower Boss", "Castle Boss", "Toad House", "Airship Boss", "Forest", "Enemy Ambush", "Beach", "Volcano", "Peach's Castle", "Credits Jazz", "Airship Drums", "Bowser", "Mega Bowser", "Epilogue"]
            self.Zone_music.addItems(newItems2)
            self.Zone_music.setCurrentIndex(z.music)
    
            self.Zone_sfx = QtGui.QComboBox()
            self.Zone_sfx.setToolTip("Changes the sound effect modulation")
            newItems3 = ["Normal", "Wall Echo", "Room Echo", "Double Echo", "Cave Echo", "Underwater Echo", "Triple Echo", "High Pitch Echo", "Tinny Echo", "Flat", "Dull", "Hollow Echo", "Rich", "Triple Underwater", "Ring Echo"]
            self.Zone_sfx.addItems(newItems3)
            self.Zone_sfx.setCurrentIndex(z.sfxmod / 16)
            
            self.Zone_boss = QtGui.QCheckBox()
            self.Zone_boss.setToolTip("Set for bosses to allow proper music switching by sprites")
            self.Zone_boss.setChecked(z.sfxmod % 16)
    
    
            ZoneAudioLayout = QtGui.QFormLayout()
            ZoneAudioLayout.addRow("Background Music:", self.Zone_music)
            ZoneAudioLayout.addRow("Sound Modulation:", self.Zone_sfx)
            ZoneAudioLayout.addRow("Boss Flag:", self.Zone_boss)
            
            self.Audio.setLayout(ZoneAudioLayout)



#Sets up the Background Dialog
class BGDialog(QtGui.QDialog):
    """Dialog which lets you choose among various from tabs"""    
    def __init__(self):
        """Creates and initialises the tab dialog"""
        QtGui.QDialog.__init__(self)
        self.setWindowTitle('Backgrounds')
        
        self.tabWidget = QtGui.QTabWidget()
        
        i = 0
        self.BGTabs = []
        for z in Level.zones:
            i = i+1
            BGTabName = "Zone " + str(i)
            tab = BGTab(z)
            self.BGTabs.append(tab)
            self.tabWidget.addTab(tab, BGTabName)
                
        
        if self.tabWidget.count() > 5:
            for tab in range(0, self.tabWidget.count()):
                self.tabWidget.setTabText(tab, str(tab + 1))
                
                        
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)

        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        mainLayout = QtGui.QVBoxLayout()
        mainLayout.addWidget(self.tabWidget)
        mainLayout.addWidget(buttonBox)
        self.setLayout(mainLayout)
        

class BGTab(QtGui.QWidget):
    def __init__(self, z):
        QtGui.QWidget.__init__(self)
        
        self.createBGa(z)
        self.createBGb(z)
        self.createBGaViewer(z)
        self.createBGbViewer(z)

        mainLayout = QtGui.QGridLayout()
        mainLayout.addWidget(self.BGa, 0, 0)
        mainLayout.addWidget(self.BGb, 1, 0)
        mainLayout.addWidget(self.BGaViewer, 0, 1)
        mainLayout.addWidget(self.BGbViewer, 1, 1)
        self.setLayout(mainLayout)


    def createBGa(self, z):
            self.BGa = QtGui.QGroupBox("Scenery")
            
            
                        
            self.xposA = QtGui.QSpinBox()
            self.xposA.setToolTip("Sets the horizontal offset of your background")
            self.xposA.setRange(-256, 255)
            self.xposA.setValue(z.XpositionA)
            
            self.yposA = QtGui.QSpinBox()
            self.yposA.setToolTip("Sets the vertical offset of your background")
            self.yposA.setRange(-255, 256)
            self.yposA.setValue(-z.YpositionA)

            self.scrollrate = QtGui.QLabel("Scroll Rate:")
            self.positionlabel = QtGui.QLabel("Position:")

            self.xscrollA = QtGui.QComboBox()
            self.xscrollA.addItems(BgScrollRateStrings)
            self.xscrollA.setToolTip("Changes the rate that the background moves in\nrelation to Mario when he moves horizontally.\nValues higher than 1x may be glitchy!")
            if z.XscrollA < 0: z.XscrollA = 0
            if z.XscrollA >= len(BgScrollRates): z.XscrollA = len(BgScrollRates)
            self.xscrollA.setCurrentIndex(z.XscrollA)

            self.yscrollA = QtGui.QComboBox()
            self.yscrollA.addItems(BgScrollRateStrings)
            self.yscrollA.setToolTip("Changes the rate that the background moves in\nrelation to Mario when he moves vertically.\nValues higher than 1x may be glitchy!")
            if z.YscrollA < 0: z.YscrollA = 0
            if z.YscrollA >= len(BgScrollRates): z.YscrollA = len(BgScrollRates)
            self.yscrollA.setCurrentIndex(z.YscrollA)


            self.zoomA = QtGui.QComboBox()
            addstr = ["100%", "125%", "150%", "200%"]
            self.zoomA.addItems(addstr)
            self.zoomA.setToolTip("Sets the zoom level of the background image")
            self.zoomA.setCurrentIndex(z.ZoomA)
            
            self.toscreenA = QtGui.QRadioButton()
            self.toscreenA.setToolTip("Aligns the background baseline to the bottom of the screen")
            self.toscreenLabel = QtGui.QLabel("Screen")
            self.tozoneA = QtGui.QRadioButton()
            self.tozoneA.setToolTip("Aligns the background baseline to the bottom of the zone")
            self.tozoneLabel = QtGui.QLabel("Zone")
            if z.bg2A == 0x000A:
                self.tozoneA.setChecked(1)
            else:
                self.toscreenA.setChecked(1)
            
            self.alignLabel = QtGui.QLabel("Align to: ")
            
            Lone = QtGui.QFormLayout()
            Lone.addRow("Zoom: ", self.zoomA)
            
            Ltwo = QtGui.QHBoxLayout()
            Ltwo.addWidget(self.toscreenLabel)
            Ltwo.addWidget(self.toscreenA)
            Ltwo.addWidget(self.tozoneLabel)
            Ltwo.addWidget(self.tozoneA)

            Lthree = QtGui.QFormLayout()
            Lthree.addRow("X:", self.xposA)
            Lthree.addRow("Y:", self.yposA)

            Lfour = QtGui.QFormLayout()
            Lfour.addRow("X: ", self.xscrollA)
            Lfour.addRow("Y: ", self.yscrollA)
            
            
            mainLayout = QtGui.QGridLayout()
            mainLayout.addWidget(self.positionlabel, 0, 0)
            mainLayout.addLayout(Lthree, 1, 0)
            mainLayout.addWidget(self.scrollrate, 0, 1)
            mainLayout.addLayout(Lfour, 1, 1)
            mainLayout.addLayout(Lone, 2, 0, 1, 2)
            mainLayout.addWidget(self.alignLabel, 3, 0, 1, 2)
            mainLayout.addLayout(Ltwo, 4, 0, 1, 2)
            mainLayout.setRowStretch(5, 1)
            self.BGa.setLayout(mainLayout)
            

    def createBGb(self, z):
            self.BGb = QtGui.QGroupBox("Backdrop")
            
                        
            self.xposB = QtGui.QSpinBox()
            self.xposB.setToolTip("Sets the horizontal offset of your background")
            self.xposB.setRange(-256, 255)
            self.xposB.setValue(z.XpositionB)
            
            self.yposB = QtGui.QSpinBox()
            self.yposB.setToolTip("Sets the vertical offset of your background")
            self.yposB.setRange(-255, 256)
            self.yposB.setValue(-z.YpositionB)

            self.scrollrate = QtGui.QLabel("Scroll Rate:")
            self.positionlabel = QtGui.QLabel("Position:")

            self.xscrollB = QtGui.QComboBox()
            self.xscrollB.addItems(BgScrollRateStrings)
            self.xscrollB.setToolTip("Changes the rate that the background moves in\nrelation to Mario when he moves horizontally.\nValues higher than 1x may be glitchy!")
            if z.XscrollB < 0: z.XscrollB = 0
            if z.XscrollB >= len(BgScrollRates): z.XscrollB = len(BgScrollRates)
            self.xscrollB.setCurrentIndex(z.XscrollB)

            self.yscrollB = QtGui.QComboBox()
            self.yscrollB.addItems(BgScrollRateStrings)
            self.yscrollB.setToolTip("Changes the rate that the background moves in\nrelation to Mario when he moves vertically.\nValues higher than 1x may be glitchy!")
            if z.YscrollB < 0: z.YscrollB = 0
            if z.YscrollB >= len(BgScrollRates): z.YscrollB = len(BgScrollRates)
            self.yscrollB.setCurrentIndex(z.YscrollB)


            self.zoomB = QtGui.QComboBox()
            addstr = ["100%", "125%", "150%", "200%"]
            self.zoomB.addItems(addstr)
            self.zoomB.setToolTip("Sets the zoom level of the background image")
            self.zoomB.setCurrentIndex(z.ZoomB)
            
            self.toscreenB = QtGui.QRadioButton()
            self.toscreenB.setToolTip("Aligns the background baseline to the bottom of the screen")
            self.toscreenLabel = QtGui.QLabel("Screen")
            self.tozoneB = QtGui.QRadioButton()
            self.tozoneB.setToolTip("Aligns the background baseline to the bottom of the zone")
            self.tozoneLabel = QtGui.QLabel("Zone")
            if z.bg2B == 0x000A:
                self.tozoneB.setChecked(1)
            else:
                self.toscreenB.setChecked(1)
            
            self.alignLabel = QtGui.QLabel("Align to: ")
            
            Lone = QtGui.QFormLayout()
            Lone.addRow("Zoom: ", self.zoomB)
            
            Ltwo = QtGui.QHBoxLayout()
            Ltwo.addWidget(self.toscreenLabel)
            Ltwo.addWidget(self.toscreenB)
            Ltwo.addWidget(self.tozoneLabel)
            Ltwo.addWidget(self.tozoneB)

            Lthree = QtGui.QFormLayout()
            Lthree.addRow("X:", self.xposB)
            Lthree.addRow("Y:", self.yposB)

            Lfour = QtGui.QFormLayout()
            Lfour.addRow("X: ", self.xscrollB)
            Lfour.addRow("Y: ", self.yscrollB)
            
            
            mainLayout = QtGui.QGridLayout()
            mainLayout.addWidget(self.positionlabel, 0, 0)
            mainLayout.addLayout(Lthree, 1, 0)
            mainLayout.addWidget(self.scrollrate, 0, 1)
            mainLayout.addLayout(Lfour, 1, 1)
            mainLayout.addLayout(Lone, 2, 0, 1, 2)
            mainLayout.addWidget(self.alignLabel, 3, 0, 1, 2)
            mainLayout.addLayout(Ltwo, 4, 0, 1, 2)
            mainLayout.setRowStretch(5, 1)
            self.BGb.setLayout(mainLayout)


    def createBGaViewer(self, z):
            self.BGaViewer = QtGui.QGroupBox("Preview")
            
            self.background_nameA = QtGui.QComboBox()
            self.previewA = QtGui.QLabel()

            #image = QtGui.QImage('reggiedata/bga/000A.png')
            #self.previewA.setPixmap(QtGui.QPixmap.fromImage(image))

            if z.bg1A == 0x000A:
                currentBG = z.bg2A
            else: 
                currentBG = z.bg1A
            
            found_it = False

            for bfile_raw, bname in BgANames:
                bfile = int(bfile_raw, 16)
                self.background_nameA.addItem('%s (%04X)' % (bname,bfile), bfile)
                
                if currentBG == bfile:
                    self.background_nameA.setCurrentIndex(self.background_nameA.count() - 1)
                    found_it = True
            
            if found_it:
                custom = ''
            else:
                custom = ' (%04X)' % currentBG
            
            self.background_nameA.addItem('Custom background ID...%s' % custom, currentBG)
            if not found_it:
                self.background_nameA.setCurrentIndex(self.background_nameA.count() - 1)
            
            self.currentIndexA = self.background_nameA.currentIndex()
            
            self.background_nameA.activated.connect(self.viewboxA)
            self.viewboxA(self.background_nameA.currentIndex(), True)

            mainLayout = QtGui.QVBoxLayout()
            mainLayout.addWidget(self.background_nameA)
            mainLayout.addWidget(self.previewA)
            self.BGaViewer.setLayout(mainLayout)


    @QtCore.pyqtSlot(int)
    def viewboxA(self, indexid, loadFlag=False):
        if not loadFlag:
            if indexid == (self.background_nameA.count() - 1):
                w = self.background_nameA
                id = w.itemData(indexid).toPyObject()
                
                dbox = InputBox(InputBox.Type_HexSpinBox)
                dbox.setWindowTitle('Choose a Background ID')
                dbox.label.setText('Enter the hex ID of a custom background to use. The file must be named using the bgA_12AB.arc format and located within the game\'s Object folder.')
                dbox.spinbox.setRange(0, 0xFFFF)
                if id != None: dbox.spinbox.setValue(id)
                result = dbox.exec_()
                
                if result == QtGui.QDialog.Accepted:
                    id = dbox.spinbox.value()
                    w.setItemText(indexid, 'Custom background ID... (%04X)' % id)
                    w.setItemData(indexid, id)
                else:
                    w.setCurrentIndex(self.currentIndexA)
                    return
        
        id = self.background_nameA.itemData(indexid).toPyObject()
        filename = 'reggiedata/bga/%04X.png' % id
        
        if not os.path.isfile(filename):
            filename = 'reggiedata/bga/no_preview.png'
        
        image = QtGui.QImage(filename)
        self.previewA.setPixmap(QtGui.QPixmap.fromImage(image))
        
        self.currentIndexA = indexid



    def createBGbViewer(self, z):
            self.BGbViewer = QtGui.QGroupBox("Preview")
            
            self.background_nameB = QtGui.QComboBox()
            self.previewB = QtGui.QLabel()

            #image = QtGui.QImage('reggiedata/bgb/000A.png')
            #self.previewB.setPixmap(QtGui.QPixmap.fromImage(image))

            if z.bg1B == 0x000A:
                currentBG = z.bg2B
            else: 
                currentBG = z.bg1B
            
            found_it = False

            for bfile_raw, bname in BgBNames:
                bfile = int(bfile_raw, 16)
                self.background_nameB.addItem('%s (%04X)' % (bname,bfile), bfile)
                
                if currentBG == bfile:
                    self.background_nameB.setCurrentIndex(self.background_nameB.count() - 1)
                    found_it = True
            
            if found_it:
                custom = ''
            else:
                custom = ' (%04X)' % currentBG
            
            self.background_nameB.addItem('Custom background ID...%s' % custom, currentBG)
            if not found_it:
                self.background_nameB.setCurrentIndex(self.background_nameB.count() - 1)
            
            self.currentIndexB = self.background_nameB.currentIndex()
            
            self.background_nameB.activated.connect(self.viewboxB)
            self.viewboxB(self.background_nameB.currentIndex())

            mainLayout = QtGui.QVBoxLayout()
            mainLayout.addWidget(self.background_nameB)
            mainLayout.addWidget(self.previewB)
            self.BGbViewer.setLayout(mainLayout)


    @QtCore.pyqtSlot(int)
    def viewboxB(self, indexid, loadFlag=False):
        if not loadFlag:
            if indexid == (self.background_nameB.count() - 1):
                w = self.background_nameB
                id = w.itemData(indexid).toPyObject()
                
                dbox = InputBox(InputBox.Type_HexSpinBox)
                dbox.setWindowTitle('Choose a Background ID')
                dbox.label.setText('Enter the hex ID of a custom background to use. The file must be named using the bgB_12AB.arc format and located within the game\'s Object folder.')
                dbox.spinbox.setRange(0, 0xFFFF)
                if id != None: dbox.spinbox.setValue(id)
                result = dbox.exec_()
                
                if result == QtGui.QDialog.Accepted:
                    id = dbox.spinbox.value()
                    w.setItemText(indexid, 'Custom background ID... (%04X)' % id)
                    w.setItemData(indexid, id)
                else:
                    w.setCurrentIndex(self.currentIndexB)
                    return
        
        id = self.background_nameB.itemData(indexid).toPyObject()
        filename = 'reggiedata/bgb/%04X.png' % id
        
        if not os.path.isfile(filename):
            filename = 'reggiedata/bgb/no_preview.png'
        
        image = QtGui.QImage(filename)
        self.previewB.setPixmap(QtGui.QPixmap.fromImage(image))
        
        self.currentIndexB = indexid



#Sets up the Screen Cap Choice Dialog
class ScreenCapChoiceDialog(QtGui.QDialog):
    """Dialog which lets you choose which zone to take a pic of"""
    def __init__(self):
        """Creates and initialises the dialog"""
        QtGui.QDialog.__init__(self)
        self.setWindowTitle('Choose a Screenshot source')
        
        i=0
        self.zoneCombo = QtGui.QComboBox()
        self.zoneCombo.addItem("Current Screen")
        self.zoneCombo.addItem("All Zones")
        for z in Level.zones:
            i = i+1
            self.zoneCombo.addItem("Zone " + str(i))
                
                        
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)

        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        mainLayout = QtGui.QVBoxLayout()
        mainLayout.addWidget(self.zoneCombo)
        mainLayout.addWidget(buttonBox)
        self.setLayout(mainLayout)



class AutoSavedInfoDialog(QtGui.QDialog):
    """Dialog which lets you know that an auto saved level exists"""
    
    def __init__(self, filename):
        """Creates and initialises the dialog"""
        QtGui.QDialog.__init__(self)
        self.setWindowTitle('Auto-saved backup found')
        
        mainlayout = QtGui.QVBoxLayout(self)
        
        hlayout = QtGui.QHBoxLayout()
        
        icon = QtGui.QLabel()
        hlayout.addWidget(icon)
        
        label = QtGui.QLabel('Reggie! has found some level data which wasn\'t saved - possibly due to a crash within the editor or by your computer. Do you want to restore this level?<br><br>If you pick No, the autosaved level data will be deleted and will no longer be accessible.<br><br>Original file path: ' + filename)
        label.setWordWrap(True)
        hlayout.addWidget(label)
        hlayout.setStretch(1, 1)
        
        buttonbox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.No | QtGui.QDialogButtonBox.Yes)
        buttonbox.accepted.connect(self.accept)
        buttonbox.rejected.connect(self.reject)
        
        mainlayout.addLayout(hlayout)
        mainlayout.addWidget(buttonbox)


class AreaChoiceDialog(QtGui.QDialog):
    """Dialog which lets you choose an area"""
    
    def __init__(self, areacount):
        """Creates and initialises the dialog"""
        QtGui.QDialog.__init__(self)
        self.setWindowTitle('Choose an Area')
        
        self.areaCombo = QtGui.QComboBox()
        for i in xrange(areacount):
            self.areaCombo.addItem('Area %d' % (i+1))
        
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)

        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        mainLayout = QtGui.QVBoxLayout()
        mainLayout.addWidget(self.areaCombo)
        mainLayout.addWidget(buttonBox)
        self.setLayout(mainLayout)


####################################################################
####################################################################
####################################################################



class ReggieWindow(QtGui.QMainWindow):
    """Reggie main level editor window"""
    
    def CreateAction(self, shortname, function, icon, text, statustext, shortcut, toggle=False):
        """Helper function to create an action"""
        
        if icon != None:
            act = QtGui.QAction(icon, text, self)
        else:
            act = QtGui.QAction(text, self)
        
        if shortcut != None: act.setShortcut(shortcut)
        if statustext != None: act.setStatusTip(statustext)
        if toggle:
            act.setCheckable(True)
        act.triggered.connect(function)
        
        self.actions[shortname] = act
    
    
    def __init__(self):
        """Editor window constructor"""
        
        # Reggie Version number goes below here. 64 char max (32 if non-ascii).
        self.ReggieInfo = ReggieID
        
        self.ZoomLevels = [12.5, 25.0, 50.0, 75.0, 100.0, 150.0, 200.0]
        
        self.AutosaveTimer = QtCore.QTimer()
        self.AutosaveTimer.timeout.connect(self.Autosave)
        self.AutosaveTimer.start(20000)
        
        # required variables
        self.UpdateFlag = False
        self.SelectionUpdateFlag = False
        self.selObj = None
        self.CurrentSelection = []
        
        # set up the window
        QtGui.QMainWindow.__init__(self, None)
        self.setWindowTitle('Reggie! Level Editor')
        self.setWindowIcon(QtGui.QIcon('reggiedata/icon.png'))
        self.setIconSize(QtCore.QSize(16, 16))
        
        # create the actions
        self.SetupActionsAndMenus()
        
        # set up the status bar
        self.posLabel = QtGui.QLabel()
        self.statusBar().addWidget(self.posLabel)
        
        # create the various panels
        self.SetupDocksAndPanels()
        
        # create the level view
        self.scene = LevelScene(0, 0, 1024*24, 512*24, self)
        self.scene.setItemIndexMethod(QtGui.QGraphicsScene.NoIndex)
        self.scene.selectionChanged.connect(self.ChangeSelectionHandler)
        
        self.view = LevelViewWidget(self.scene, self)
        self.view.centerOn(0,0) # this scrolls to the top left
        self.view.PositionHover.connect(self.PositionHovered)
        self.view.XScrollBar.valueChanged.connect(self.XScrollChange)
        self.view.YScrollBar.valueChanged.connect(self.YScrollChange)
        self.view.FrameSize.connect(self.HandleWindowSizeChange)
        
        # done creating the window!
        self.setCentralWidget(self.view)
        
        # set up the clipboard stuff
        self.clipboard = None
        self.systemClipboard = QtGui.QApplication.clipboard()
        self.systemClipboard.dataChanged.connect(self.TrackClipboardUpdates)
        
        # we might have something there already, activate Paste if so
        self.TrackClipboardUpdates()
        
        # let's restore the geometry
        if settings.contains('MainWindowState'):
            self.restoreState(settings.value('MainWindowState').toPyObject(), 0)
        if settings.contains('MainWindowGeometry'):
            self.restoreGeometry(settings.value('MainWindowGeometry').toPyObject())
        
        # now get stuff ready
        loaded = False
        if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]) and IsNSMBLevel(sys.argv[1]):
            loaded = self.LoadLevel(sys.argv[1], True, 1)
        elif settings.contains('LastLevel'):
            lastlevel = unicode(settings.value('LastLevel').toPyObject())
            settings.remove('LastLevel')
            
            if lastlevel != 'None':
                loaded = self.LoadLevel(lastlevel, True, 1)
        
        if not loaded:
            self.LoadLevel('01-01', False, 1)
        
        QtCore.QTimer.singleShot(100, self.levelOverview.update)
    
    
    def SetupActionsAndMenus(self):
        """Sets up Reggie's actions, menus and toolbars"""
        self.actions = {}
        self.CreateAction('newlevel', self.HandleNewLevel, GetIcon('new'), 'New Level', 'Create a new, blank level', QtGui.QKeySequence.New)
        self.CreateAction('openfromname', self.HandleOpenFromName, GetIcon('open'), 'Open Level by Name...', 'Open a level based on its in-game world/number', QtGui.QKeySequence.Open)
        self.CreateAction('openfromfile', self.HandleOpenFromFile, GetIcon('openfromfile'), 'Open Level by File...', 'Open a level based on its filename', QtGui.QKeySequence('Ctrl+Shift+O'))
        self.CreateAction('save', self.HandleSave, GetIcon('save'), 'Save Level', 'Save a level back to the archive file', QtGui.QKeySequence.Save)
        self.CreateAction('saveas', self.HandleSaveAs, GetIcon('saveas'), 'Save Level As...', 'Save a level with a new filename', QtGui.QKeySequence.SaveAs)
        self.CreateAction('screenshot', self.HandleScreenshot, GetIcon('screenshot'), 'Level Screenshot...', 'Takes a full size screenshot of your level for you to share.', QtGui.QKeySequence('Ctrl+Shift+3'))
        self.CreateAction('changegamepath', self.HandleChangeGamePath, None, 'Change Game Path...', 'Set a different folder to load the game files from', QtGui.QKeySequence('Ctrl+Alt+G'))
        self.CreateAction('exit', self.HandleExit, None, 'Exit Reggie!', 'Exit the editor', QtGui.QKeySequence('Ctrl+Q'))
        
        self.CreateAction('showlayer0', self.HandleUpdateLayer0, None, 'Layer 0', 'Toggle viewing of object layer 0', QtGui.QKeySequence('Ctrl+1'), True)
        self.CreateAction('showlayer1', self.HandleUpdateLayer1, None, 'Layer 1', 'Toggle viewing of object layer 1', QtGui.QKeySequence('Ctrl+2'), True)
        self.CreateAction('showlayer2', self.HandleUpdateLayer2, None, 'Layer 2', 'Toggle viewing of object layer 2', QtGui.QKeySequence('Ctrl+3'), True)
        self.CreateAction('grid', self.HandleShowGrid, GetIcon('grid'), 'Show Grid', 'Show a grid over the level view', QtGui.QKeySequence('Ctrl+G'), True)
        self.actions['grid'].setChecked(GridEnabled)
        
        self.CreateAction('freezeobjects', self.HandleObjectsFreeze, None, 'Freeze Objects', 'Make objects non-selectable', QtGui.QKeySequence('Ctrl+Shift+1'), True)
        self.actions['freezeobjects'].setChecked(not ObjectsNonFrozen)
        self.CreateAction('freezesprites', self.HandleSpritesFreeze, None, 'Freeze Sprites', 'Make sprites non-selectable', QtGui.QKeySequence('Ctrl+Shift+2'), True)
        self.actions['freezesprites'].setChecked(not SpritesNonFrozen)
        self.CreateAction('freezeentrances', self.HandleEntrancesFreeze, None, 'Freeze Entrances', 'Make entrances non-selectable', QtGui.QKeySequence('Ctrl+Shift+3'), True)
        self.actions['freezeentrances'].setChecked(not EntrancesNonFrozen)
        self.CreateAction('freezelocations', self.HandleLocationsFreeze, None, 'Freeze Locations', 'Make locations non-selectable', QtGui.QKeySequence('Ctrl+Shift+4'), True)
        self.actions['freezelocations'].setChecked(not LocationsNonFrozen)
        
        self.CreateAction('zoomin', self.HandleZoomIn, GetIcon('zoomin'), 'Zoom In', 'Zoom into the main level view', QtGui.QKeySequence.ZoomIn, False)
        self.CreateAction('zoomactual', self.HandleZoomActual, GetIcon('zoomactual'), 'Zoom 100%', 'Show the level at the default zoom', QtGui.QKeySequence('Ctrl+='), False)
        self.CreateAction('zoomout', self.HandleZoomOut, GetIcon('zoomout'), 'Zoom Out', 'Zoom out of the main level view', QtGui.QKeySequence.ZoomOut, False)
        
        self.CreateAction('areaoptions', self.HandleAreaOptions, GetIcon('area'), 'Area Settings...', 'Controls tileset swapping, stage timer, entrance on load, and stage wrap', QtGui.QKeySequence('Ctrl+Alt+A'))
        self.CreateAction('zones', self.HandleZones, GetIcon('zones'), 'Zones...', 'Zone creation, deletion, and preference editing', QtGui.QKeySequence('Ctrl+Alt+Z'))
        self.CreateAction('backgrounds', self.HandleBG, GetIcon('background'), 'Backgrounds...', 'Apply backgrounds to individual zones in the current area', QtGui.QKeySequence('Ctrl+Alt+B'))
        self.CreateAction('metainfo', self.HandleInfo, None, 'Level Information...', 'Add title and author information to the metadata', QtGui.QKeySequence('Ctrl+Alt+I'))
        self.CreateAction('paths', self.HandlePaths, GetIcon('paths'), 'Path Editor...', 'Create and modify paths', QtGui.QKeySequence('Ctrl+P'))
        
        self.CreateAction('aboutqt', QtGui.qApp.aboutQt, None, 'About PyQt...', 'About the Qt library Reggie! is based on', QtGui.QKeySequence('Ctrl+Shift+Y'))
        self.CreateAction('infobox', self.InfoBox, GetIcon('about'), 'About Reggie!', 'Info about the program, and the team behind it', QtGui.QKeySequence('Ctrl+Shift+I'))
        self.CreateAction('helpbox', self.HelpBox, GetIcon('help'), 'Reggie! Help...', 'Help Documentation for the needy newbie', QtGui.QKeySequence('Ctrl+Shift+H'))
        self.CreateAction('tipbox', self.TipBox, GetIcon('tips'), 'Reggie! Tips...', 'Tips and controls for beginners and power users', QtGui.QKeySequence('Ctrl+Shift+T'))
        
#        self.CreateAction('undo', self.Undo, None, 'Undo', 'Undoes a single action', QtGui.QKeySequence('Ctrl+Z'))
#        self.CreateAction('redo', self.Redo, None, 'Redo', 'Redoes a single action', QtGui.QKeySequence('Ctrl+Shift+Z'))

        self.CreateAction('selectall', self.SelectAll, None, 'Select All', 'Selects all items on screen', QtGui.QKeySequence.SelectAll)
        self.CreateAction('cut', self.Cut, GetIcon('cut'), 'Cut', 'Cut out the current selection to the clipboard', QtGui.QKeySequence.Cut)
        self.CreateAction('copy', self.Copy, GetIcon('copy'), 'Copy', 'Copies the current selection to the clipboard', QtGui.QKeySequence.Copy)
        self.CreateAction('paste', self.Paste, GetIcon('paste'), 'Paste', 'Pastes the current selection from the clipboard', QtGui.QKeySequence.Paste)
        self.CreateAction('shiftobjects', self.ShiftObjects, None, 'Shift Objects...', 'Moves all the selected objects by an offset', QtGui.QKeySequence('Ctrl+Shift+S'))
        self.CreateAction('mergelocations', self.MergeLocations, None, 'Merge Sprite Areas', 'Merges selected Sprite Areas into a single large box', QtGui.QKeySequence('Ctrl+Shift+E'))
        
        self.actions['cut'].setEnabled(False)
        self.actions['copy'].setEnabled(False)
        self.actions['paste'].setEnabled(False)
        self.actions['shiftobjects'].setEnabled(False)
        self.actions['mergelocations'].setEnabled(False)
        
        self.CreateAction('addarea', self.HandleAddNewArea, GetIcon('add'), 'Add New Area', 'Adds a new area/sublevel to this level', QtGui.QKeySequence('Ctrl+Alt+N'))
        self.CreateAction('importarea', self.HandleImportArea, None, 'Import Area from Level...', 'Imports an area/sublevel from another level file', QtGui.QKeySequence('Ctrl+Alt+O'))
        self.CreateAction('deletearea', self.HandleDeleteArea, GetIcon('delete'), 'Delete Current Area...', 'Deletes the area/sublevel currently open from the level', QtGui.QKeySequence('Ctrl+Alt+D'))
        
        self.CreateAction('reloadgfx', self.ReloadTilesets, GetIcon('reload'), 'Reload Tilesets', 'Reloads the tileset data files, including any changes made since the level was loaded', QtGui.QKeySequence('Ctrl+Shift+R'))
        
        # create a menubar
        menubar = self.menuBar()
        
        fmenu = menubar.addMenu('&File')
        fmenu.addAction(self.actions['newlevel'])
        fmenu.addAction(self.actions['openfromname'])
        fmenu.addAction(self.actions['openfromfile'])
        fmenu.addSeparator()
        fmenu.addAction(self.actions['save'])
        fmenu.addAction(self.actions['saveas'])
        fmenu.addAction(self.actions['metainfo'])
        fmenu.addSeparator()
        fmenu.addAction(self.actions['screenshot'])
        fmenu.addAction(self.actions['changegamepath'])
        fmenu.addSeparator()
        fmenu.addAction(self.actions['exit'])

        emenu = menubar.addMenu('&Edit')
#        emenu.addAction(self.actions['undo'])
#        emenu.addAction(self.actions['redo'])
#        emenu.addSeparator()
        emenu.addAction(self.actions['selectall'])
        emenu.addSeparator()
        emenu.addAction(self.actions['cut'])
        emenu.addAction(self.actions['copy'])
        emenu.addAction(self.actions['paste'])
        emenu.addSeparator()
        emenu.addAction(self.actions['shiftobjects'])
        emenu.addAction(self.actions['mergelocations'])
        emenu.addSeparator()
        emenu.addAction(self.actions['freezeobjects'])
        emenu.addAction(self.actions['freezesprites'])
        emenu.addAction(self.actions['freezeentrances'])
        emenu.addAction(self.actions['freezelocations'])
        
        vmenu = menubar.addMenu('&View')
        vmenu.addAction(self.actions['showlayer0'])
        vmenu.addAction(self.actions['showlayer1'])
        vmenu.addAction(self.actions['showlayer2'])
        vmenu.addSeparator()
        vmenu.addAction(self.actions['grid'])
        vmenu.addSeparator()
        vmenu.addAction(self.actions['zoomin'])
        vmenu.addAction(self.actions['zoomactual'])
        vmenu.addAction(self.actions['zoomout'])
        vmenu.addSeparator()
        # self.levelOverviewDock.toggleViewAction() is added here later
        # so we assign it to self.vmenu
        self.vmenu = vmenu
        
        lmenu = menubar.addMenu('&Settings')
        lmenu.addAction(self.actions['areaoptions'])
        lmenu.addAction(self.actions['zones'])
        lmenu.addAction(self.actions['backgrounds'])
        if EnablePaths: lmenu.addAction(self.actions['paths'])
        lmenu.addSeparator()
        lmenu.addAction(self.actions['addarea'])
        lmenu.addAction(self.actions['importarea'])
        lmenu.addAction(self.actions['deletearea'])
        lmenu.addSeparator()
        lmenu.addAction(self.actions['reloadgfx'])
        
        hmenu = menubar.addMenu('&Help')
        hmenu.addAction(self.actions['infobox'])
        hmenu.addAction(self.actions['helpbox'])
        hmenu.addAction(self.actions['tipbox'])
        hmenu.addSeparator()
        hmenu.addAction(self.actions['aboutqt'])
        
        # create a toolbar
        self.toolbar = self.addToolBar('Level Editor')
        self.toolbar.setObjectName('maintoolbar') #needed for the state to save/restore correctly
        self.toolbar.addAction(self.actions['newlevel'])
        self.toolbar.addAction(self.actions['openfromname'])
        self.toolbar.addAction(self.actions['save'])
        self.toolbar.addAction(self.actions['screenshot'])
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.actions['cut'])
        self.toolbar.addAction(self.actions['copy'])
        self.toolbar.addAction(self.actions['paste'])
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.actions['zoomin'])
        self.toolbar.addAction(self.actions['zoomactual'])
        self.toolbar.addAction(self.actions['zoomout'])
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.actions['grid'])
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.actions['showlayer0'])
        self.toolbar.addAction(self.actions['showlayer1'])
        self.toolbar.addAction(self.actions['showlayer2'])
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.actions['areaoptions'])
        self.toolbar.addAction(self.actions['zones'])
        self.toolbar.addAction(self.actions['backgrounds'])
        if EnablePaths: self.toolbar.addAction(self.actions['paths'])
        self.toolbar.addSeparator()
        
        self.areaComboBox = QtGui.QComboBox()
        self.areaComboBox.activated.connect(self.HandleSwitchArea)
        self.toolbar.addWidget(self.areaComboBox)
    
    
    def SetupDocksAndPanels(self):
        """Sets up the dock widgets and panels"""
        # level overview
        dock = QtGui.QDockWidget('Level Overview', self)
        dock.setFeatures(QtGui.QDockWidget.DockWidgetMovable | QtGui.QDockWidget.DockWidgetFloatable | QtGui.QDockWidget.DockWidgetClosable)
        #dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        dock.setObjectName('leveloverview') #needed for the state to save/restore correctly
        
        self.levelOverview = LevelOverviewWidget()
        self.levelOverview.moveIt.connect(self.HandleOverviewClick)
        self.levelOverviewDock = dock
        dock.setWidget(self.levelOverview)

        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
        dock.setVisible(True)
        act = dock.toggleViewAction()
        act.setShortcut(QtGui.QKeySequence('Ctrl+M'))
        self.vmenu.addAction(act)
        
        # create the sprite editor panel
        dock = QtGui.QDockWidget('Modify Selected Sprite Properties', self)
        dock.setVisible(False)
        dock.setFeatures(QtGui.QDockWidget.DockWidgetMovable | QtGui.QDockWidget.DockWidgetFloatable)
        dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        dock.setObjectName('spriteeditor') #needed for the state to save/restore correctly
        
        self.spriteDataEditor = SpriteEditorWidget()
        self.spriteDataEditor.DataUpdate.connect(self.SpriteDataUpdated)
        dock.setWidget(self.spriteDataEditor)
        self.spriteEditorDock = dock
        
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
        dock.setFloating(True)
        
        # create the entrance editor panel
        dock = QtGui.QDockWidget('Modify Selected Entry Point Properties', self)
        dock.setVisible(False)
        dock.setFeatures(QtGui.QDockWidget.DockWidgetMovable | QtGui.QDockWidget.DockWidgetFloatable)
        dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        dock.setObjectName('entranceeditor') #needed for the state to save/restore correctly
        
        self.entranceEditor = EntranceEditorWidget()
        dock.setWidget(self.entranceEditor)
        self.entranceEditorDock = dock
        
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
        dock.setFloating(True)
        
        # create the location editor panel
        dock = QtGui.QDockWidget('Modify Selected Location Properties', self)
        dock.setVisible(False)
        dock.setFeatures(QtGui.QDockWidget.DockWidgetMovable | QtGui.QDockWidget.DockWidgetFloatable)
        dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        dock.setObjectName('locationeditor') #needed for the state to save/restore correctly
        
        self.locationEditor = LocationEditorWidget()
        dock.setWidget(self.locationEditor)
        self.locationEditorDock = dock
        
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
        dock.setFloating(True)

        # create the palette
        dock = QtGui.QDockWidget('Palette', self)
        dock.setFeatures(QtGui.QDockWidget.DockWidgetMovable | QtGui.QDockWidget.DockWidgetFloatable)
        dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        dock.setObjectName('palette') #needed for the state to save/restore correctly
        self.creationDock = dock
        
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
        dock.setVisible(True)
        
        # add tabs to it
        tabs = QtGui.QTabWidget()
        tabs.setIconSize(QtCore.QSize(16, 16))
        tabs.currentChanged.connect(self.CreationTabChanged)
        dock.setWidget(tabs)
        self.creationTabs = tabs
        
        # object choosing tabs
        tsicon = GetIcon('objects')
        
        self.objTS0Tab = QtGui.QWidget()
        self.objTS1Tab = QtGui.QWidget()
        self.objTS2Tab = QtGui.QWidget()
        self.objTS3Tab = QtGui.QWidget()
        tabs.addTab(self.objTS0Tab, tsicon, '1')
        tabs.addTab(self.objTS1Tab, tsicon, '2')
        tabs.addTab(self.objTS2Tab, tsicon, '3')
        tabs.addTab(self.objTS3Tab, tsicon, '4')
        
        oel = QtGui.QVBoxLayout(self.objTS0Tab)
        self.createObjectLayout = oel
        
        ll = QtGui.QHBoxLayout()
        self.objUseLayer0 = QtGui.QRadioButton('0')
        self.objUseLayer0.setToolTip('<b>Layer 0:</b><br>This layer is mostly used for the hidden Yoshi\'s Island-style caves, but can also be used to overlay tiles to create effects. The flashlight effect will occur if Mario walks behind a tile on layer 0 and the zone has it enabled.')
        self.objUseLayer1 = QtGui.QRadioButton('1')
        self.objUseLayer1.setToolTip('<b>Layer 1:</b><br>All or most of your normal level objects should be placed on this layer. This is the only layer where tile interactions (solids, slopes, etc) will work.')
        self.objUseLayer2 = QtGui.QRadioButton('2')
        self.objUseLayer2.setToolTip('<b>Layer 2:</b><br>Background/wall tiles (such as those in the hidden caves) should be placed on this layer. Tiles on layer 2 have no effect on collisions.')
        ll.addWidget(QtGui.QLabel('Paint on Layer:'))
        ll.addWidget(self.objUseLayer0)
        ll.addWidget(self.objUseLayer1)
        ll.addWidget(self.objUseLayer2)
        ll.addStretch(1)
        oel.addLayout(ll)
        
        lbg = QtGui.QButtonGroup(self)
        lbg.addButton(self.objUseLayer0, 0)
        lbg.addButton(self.objUseLayer1, 1)
        lbg.addButton(self.objUseLayer2, 2)
        lbg.buttonClicked[int].connect(self.LayerChoiceChanged)
        self.LayerButtonGroup = lbg
        
        self.objPicker = ObjectPickerWidget()
        self.objPicker.ObjChanged.connect(self.ObjectChoiceChanged)
        self.objPicker.ObjReplace.connect(self.ObjectReplace)
        oel.addWidget(self.objPicker, 1)
        
        # sprite choosing tabs
        self.sprPickerTab = QtGui.QWidget()
        tabs.addTab(self.sprPickerTab, GetIcon('sprites'), '')
        
        spl = QtGui.QVBoxLayout(self.sprPickerTab)
        self.sprPickerLayout = spl
        
        svpl = QtGui.QHBoxLayout()
        svpl.addWidget(QtGui.QLabel('View:'))
        
        sspl = QtGui.QHBoxLayout()
        sspl.addWidget(QtGui.QLabel('Search:'))
        
        LoadSpriteCategories()
        viewpicker = QtGui.QComboBox()
        for view in SpriteCategories:
            viewpicker.addItem(view[0])
        viewpicker.currentIndexChanged.connect(self.SelectNewSpriteView)
        
        self.spriteViewPicker = viewpicker
        svpl.addWidget(viewpicker, 1)
        
        self.spriteSearchTerm = QtGui.QLineEdit()
        self.spriteSearchTerm.textChanged.connect(self.NewSearchTerm)
        sspl.addWidget(self.spriteSearchTerm, 1)
        
        spl.addLayout(svpl)
        spl.addLayout(sspl)
        
        self.spriteSearchLayout = sspl
        sspl.itemAt(0).widget().setVisible(False)
        sspl.itemAt(1).widget().setVisible(False)
        
        self.sprPicker = SpritePickerWidget()
        self.sprPicker.SpriteChanged.connect(self.SpriteChoiceChanged)
        self.sprPicker.SpriteReplace.connect(self.SpriteReplace)
        self.sprPicker.SwitchView(SpriteCategories[0])
        spl.addWidget(self.sprPicker, 1)
        
        self.defaultPropButton = QtGui.QPushButton('Set Default Properties')
        self.defaultPropButton.setEnabled(False)
        self.defaultPropButton.clicked.connect(self.ShowDefaultProps)
        
        sdpl = QtGui.QHBoxLayout()
        sdpl.addStretch(1)
        sdpl.addWidget(self.defaultPropButton)
        sdpl.addStretch(1)
        spl.addLayout(sdpl)
        
        # default data editor
        ddock = QtGui.QDockWidget('Default Properties', self)
        ddock.setFeatures(QtGui.QDockWidget.DockWidgetMovable | QtGui.QDockWidget.DockWidgetFloatable | QtGui.QDockWidget.DockWidgetClosable)
        ddock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        ddock.setObjectName('defaultprops') #needed for the state to save/restore correctly
        
        self.defaultDataEditor = SpriteEditorWidget(True)
        self.defaultDataEditor.setVisible(False)
        ddock.setWidget(self.defaultDataEditor)
        
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, ddock)
        ddock.setVisible(False)
        ddock.setFloating(True)
        self.defaultPropDock = ddock
        
        # entrance tab
        self.entEditorTab = QtGui.QWidget()
        tabs.addTab(self.entEditorTab, GetIcon('entrances'), '')
        
        eel = QtGui.QVBoxLayout(self.entEditorTab)
        self.entEditorLayout = eel
        
        elabel = QtGui.QLabel('Entrances currently in the level:<br>(Double-click one to jump to it instantly)')
        elabel.setWordWrap(True)
        self.entranceList = QtGui.QListWidget()
        self.entranceList.itemActivated.connect(self.HandleEntranceSelectByList)
        
        eel.addWidget(elabel)
        eel.addWidget(self.entranceList)
    
    
    @QtCore.pyqtSlot()
    def Autosave(self):
        """Auto saves the level"""
        #print 'Saving!'
        global AutoSaveDirty
        if not AutoSaveDirty: return
        
        data = Level.save()
        settings.setValue('AutoSaveFilePath', Level.arcname)
        settings.setValue('AutoSaveFileData', QtCore.QByteArray(data))
        AutoSaveDirty = False
        #print 'Level autosaved'
    
    
    @QtCore.pyqtSlot()
    def TrackClipboardUpdates(self):
        """Catches systemwide clipboard updates"""
        clip = self.systemClipboard.text()
        if clip != None and clip != '':
            try:
                clip = unicode(clip)
            except UnicodeEncodeError:
                # HELLO MY NAME IS PYTHON 2.X.
                # I AM OLD AND THEREFORE I FAIL AT PUTTING ANYTHING
                # HIGHER THAN \x7F INTO A STR. THANKS!
                self.clipboard = None
                self.actions['paste'].setEnabled(False)
                return
            
            if clip.startswith('ReggieClip|') and clip.endswith('|%'):
                self.clipboard = clip.replace(' ', '').replace('\n', '').replace('\r', '').replace('\t', '')
                self.actions['paste'].setEnabled(True)
            else:
                self.clipboard = None
                self.actions['paste'].setEnabled(False)
    
    
    @QtCore.pyqtSlot(int)
    def XScrollChange(self, pos):
        """Moves the Overview current position box based on X scroll bar value"""
        self.levelOverview.Xposlocator = pos
        self.levelOverview.update()

    @QtCore.pyqtSlot(int)
    def YScrollChange(self, pos):
        """Moves the Overview current position box based on Y scroll bar value"""
        self.levelOverview.Yposlocator = pos
        self.levelOverview.update()

    @QtCore.pyqtSlot(int, int)
    def HandleWindowSizeChange(self, w, h):
        self.levelOverview.Hlocator = h
        self.levelOverview.Wlocator = w
        self.levelOverview.update()
          
    def UpdateTitle(self):
        """Sets the window title accordingly"""
        self.setWindowTitle('Reggie! Level Editor - %s%s' % (Level.filename, ' [unsaved]' if Dirty else ''))
    
    
    def CheckDirty(self):
        """Checks if the level is unsaved and asks for a confirmation if so - if it returns True, Cancel was picked"""
        if not Dirty: return False
        
        msg = QtGui.QMessageBox()
        msg.setText('The level has unsaved changes in it.')
        msg.setInformativeText('Do you want to save them?')
        msg.setStandardButtons(QtGui.QMessageBox.Save | QtGui.QMessageBox.Discard | QtGui.QMessageBox.Cancel)
        msg.setDefaultButton(QtGui.QMessageBox.Save)
        ret = msg.exec_()
        
        if ret == QtGui.QMessageBox.Save:
            if not self.HandleSave():
                # save failed
                return True
            return False
        elif ret == QtGui.QMessageBox.Discard:
            return False
        elif ret == QtGui.QMessageBox.Cancel:
            return True
    
    @QtCore.pyqtSlot()
    def InfoBox(self):
        """Shows the about box"""
        AboutDialog().exec_()
        return

    @QtCore.pyqtSlot()    
    def HandlePaths(self):
        """Creates the Path Editing mode"""
        
        # Step 1: Freeze all scene items
        # Step 2: Gray out the scene
        # Step 3: Exchange the palette dock with a path palette
        # Step 4: Allow the creation of path nodes on scene through right-clicking
        # Step 5: Floating Palette to allow editing of the numerical values manually
        # Step 6: Chain path nodes together in order
        # Step 7: Smart handling of node creation and deletion
        # Step 8: UI intuitive visualization of accel/speed
        # Step 9: Mouse controls for the above
        # Step 10: Attaching an instance of the path to all sprites which refer to it
        
        return


    @QtCore.pyqtSlot()    
    def HandleInfo(self):
        """Records the Level Meta Information"""
        if Level.areanum == 1:
            dlg = MetaInfoDialog()
            if dlg.exec_() == QtGui.QDialog.Accepted:
                Level.Title = dlg.levelName.text()
                Level.Author = dlg.Author.text()
                Level.Group = dlg.Group.text()
                Level.Webpage = dlg.Website.text()
                
                SetDirty()
                return
        else:
            dlg = QtGui.QMessageBox()
            dlg.setText("Sorry!\n\nYou can only view or edit Level Information in Area 1.")
            dlg.exec_()

    @QtCore.pyqtSlot()
    def HelpBox(self):
        """Shows the help box"""
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(os.path.join(module_path(), 'reggiedata', 'help', 'index.html')))


    @QtCore.pyqtSlot()
    def TipBox(self):
        """Reggie! Tips and Commands"""
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(os.path.join(module_path(), 'reggiedata', 'help', 'tips.html')))


    @QtCore.pyqtSlot()
    def SelectAll(self):
        """Selects all objects in the level"""
        paintRect = QtGui.QPainterPath()
        paintRect.addRect(float(0), float(0), float(1024*24), float(512*24))
        self.scene.setSelectionArea(paintRect)
    
    
    @QtCore.pyqtSlot()
    def Cut(self):
        """Cuts the selected items"""
        self.SelectionUpdateFlag = True
        selitems = self.scene.selectedItems()
        self.scene.clearSelection()
        
        if len(selitems) > 0:
            clipboard_o = []
            clipboard_s = []
            ii = isinstance
            type_obj = LevelObjectEditorItem
            type_spr = SpriteEditorItem
            
            for obj in selitems:
                if ii(obj, type_obj):
                    obj.delete()
                    obj.setSelected(False)
                    self.scene.removeItem(obj)
                    clipboard_o.append(obj)
                elif ii(obj, type_spr):
                    obj.delete()
                    obj.setSelected(False)
                    self.scene.removeItem(obj)
                    clipboard_s.append(obj)
            
            if len(clipboard_o) > 0 or len(clipboard_s) > 0:
                SetDirty()
                self.actions['cut'].setEnabled(False)
                self.actions['paste'].setEnabled(True)
                self.clipboard = self.encodeObjects(clipboard_o, clipboard_s)
                self.systemClipboard.setText(self.clipboard)
        
        self.levelOverview.update()
        self.SelectionUpdateFlag = False
        self.ChangeSelectionHandler()
        
    @QtCore.pyqtSlot()
    def Copy(self):
        """Copies the selected items"""
        selitems = self.scene.selectedItems()
        if len(selitems) > 0:
            clipboard_o = []
            clipboard_s = []
            ii = isinstance
            type_obj = LevelObjectEditorItem
            type_spr = SpriteEditorItem
            
            for obj in selitems:
                if ii(obj, type_obj):
                    clipboard_o.append(obj)
                elif ii(obj, type_spr):
                    clipboard_s.append(obj)
            
            if len(clipboard_o) > 0 or len(clipboard_s) > 0:
                self.actions['paste'].setEnabled(True)
                self.clipboard = self.encodeObjects(clipboard_o, clipboard_s)
                self.systemClipboard.setText(self.clipboard)
    
    @QtCore.pyqtSlot()
    def Paste(self):
        """Paste the selected items"""
        if self.clipboard != None:
            self.placeEncodedObjects(self.clipboard)
    
    def encodeObjects(self, clipboard_o, clipboard_s):
        """Encode a set of objects and sprites into a string"""
        convclip = ['ReggieClip']
        
        # get objects
        clipboard_o.sort(key=lambda x: x.zValue())
        
        for item in clipboard_o:
            convclip.append('0:%d:%d:%d:%d:%d:%d:%d' % (item.tileset, item.type, item.layer, item.objx, item.objy, item.width, item.height))
        
        # get sprites
        o = ord
        for item in clipboard_s:
            data = item.spritedata
            convclip.append('1:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d' % (item.type, item.objx, item.objy, o(data[0]), o(data[1]), o(data[2]), o(data[3]), o(data[4]), o(data[5]), o(data[7])))
        
        convclip.append('%')
        return '|'.join(convclip)
    
    def placeEncodedObjects(self, encoded):
        """Decode and place a set of objects"""
        self.SelectionUpdateFlag = True
        self.scene.clearSelection()
        layer0 = []
        layer1 = []
        layer2 = []
        added = []
        
        x1 = 1024
        x2 = 0
        y1 = 512
        y2 = 0
        
        global OverrideSnapping
        OverrideSnapping = True
        
        # possibly a small optimisation
        type_obj = LevelObjectEditorItem
        type_spr = SpriteEditorItem
        func_len = len
        func_chr = chr
        func_map = map
        func_int = int
        func_ii = isinstance
        layers = Level.layers
        sprites = Level.sprites
        scene = self.scene
        
        try:
            clip = encoded[11:-2].split('|')
            
            if func_len(clip) > 300:
                result = QtGui.QMessageBox.warning(self, 'Reggie!', 'You\'re trying to paste over 300 items at once.\nThis may take a while (depending on your computer speed), are you sure you want to continue?', QtGui.QMessageBox.Yes, QtGui.QMessageBox.No)
                if result == QtGui.QMessageBox.No:
                    return
            
            for item in clip:
                # Check to see whether it's an object or sprite
                # and add it to the correct stack
                split = item.split(':')
                if split[0] == '0':
                    # object
                    if func_len(split) != 8: continue
                    
                    tileset = func_int(split[1])
                    type = func_int(split[2])
                    layer = func_int(split[3])
                    objx = func_int(split[4])
                    objy = func_int(split[5])
                    width = func_int(split[6])
                    height = func_int(split[7])
                    
                    # basic sanity checks
                    if tileset < 0 or tileset > 3: continue
                    if type < 0 or type > 255: continue
                    if layer < 0 or layer > 2: continue
                    if objx < 0 or objx > 1023: continue
                    if objy < 0 or objy > 511: continue
                    if width < 1 or width > 1023: continue
                    if height < 1 or height > 511: continue
                    
                    xs = objx
                    xe = objx+width-1
                    ys = objy
                    ye = objy+height-1
                    if xs < x1: x1 = xs
                    if xe > x2: x2 = xe
                    if ys < y1: y1 = ys
                    if ye > y2: y2 = ye
                    
                    newitem = type_obj(tileset, type, layer, objx, objy, width, height, 1)
                    added.append(newitem)
                    scene.addItem(newitem)
                    newitem.setSelected(True)
                    if layer == 0:
                        layer0.append(newitem)
                    elif layer == 1:
                        layer1.append(newitem)
                    else:
                        layer2.append(newitem)
                    
                elif split[0] == '1':
                    # sprite
                    if func_len(split) != 11: continue
                    
                    objx = func_int(split[2])
                    objy = func_int(split[3])
                    data = ''.join(func_map(func_chr, func_map(func_int, [split[4], split[5], split[6], split[7], split[8], split[9], '0', split[10]])))
                    
                    x = objx / 16
                    y = objy / 16
                    if x < x1: x1 = x
                    if x > x2: x2 = x
                    if y < y1: y1 = y
                    if y > y2: y2 = y
                    
                    newitem = type_spr(func_int(split[1]), objx, objy, data)
                    sprites.append(newitem)
                    added.append(newitem)
                    scene.addItem(newitem)
                    newitem.setSelected(True)
                
        except ValueError:
            # an int() probably failed somewhere
            pass
        
        if func_len(layer0) > 0:
            layer = layers[0]
            if func_len(layer) > 0:
                z = layer[-1].zValue() + 1
            else:
                z = 16384
            for obj in layer0:
                layer.append(obj)
                obj.setZValue(z)
                z += 1
        
        if func_len(layer1) > 0:
            layer = layers[1]
            if func_len(layer) > 0:
                z = layer[-1].zValue() + 1
            else:
                z = 8192
            for obj in layer1:
                layer.append(obj)
                obj.setZValue(z)
                z += 1
        
        if func_len(layer2) > 0:
            layer = layers[2]
            if func_len(layer) > 0:
                z = layer[-1].zValue() + 1
            else:
                z = 0
            for obj in layer2:
                layer.append(obj)
                obj.setZValue(z)
                z += 1
        
        # now center everything
        zoomscaler = (self.ZoomLevel / 100.0)
        width = x2 - x1 + 1
        height = y2 - y1 + 1
        viewportx = (self.view.XScrollBar.value() / zoomscaler) / 24
        viewporty = (self.view.YScrollBar.value() / zoomscaler) / 24
        viewportwidth = (self.view.width() / zoomscaler) / 24
        viewportheight = (self.view.height() / zoomscaler) / 24
        
        # tiles
        xoffset = int(0 - x1 + viewportx + ((viewportwidth / 2) - (width / 2)))
        yoffset = int(0 - y1 + viewporty + ((viewportheight / 2) - (height / 2)))
        xpixeloffset = int(0 - x1 + viewportx + ((viewportwidth / 2) - (width / 2))) * 16
        ypixeloffset = int(0 - y1 + viewporty + ((viewportheight / 2) - (height / 2))) * 16
        
        for item in added:
            if func_ii(item, type_spr):
                item.setPos((item.objx + xpixeloffset + item.xoffset) * 1.5, (item.objy + ypixeloffset + item.yoffset) * 1.5)
            elif func_ii(item, type_obj):
                item.setPos((item.objx + xoffset) * 24, (item.objy + yoffset) * 24)
        
        OverrideSnapping = False
        
        self.levelOverview.update()
        SetDirty()
        self.SelectionUpdateFlag = False
        self.ChangeSelectionHandler()
    
    
    @QtCore.pyqtSlot()
    def ShiftObjects(self):
        """Shifts the selected object(s)"""
        items = self.scene.selectedItems()
        if len(items) == 0: return
        
        dlg = ObjectShiftDialog()
        if dlg.exec_() == QtGui.QDialog.Accepted:
            xoffset = dlg.XOffset.value()
            yoffset = dlg.YOffset.value()
            if xoffset == 0 and yoffset == 0: return
            
            type_obj = LevelObjectEditorItem
            type_spr = SpriteEditorItem
            type_ent = EntranceEditorItem
            type_loc = SpriteLocationItem
            
            if ((xoffset % 16) != 0) or ((yoffset % 16) != 0):
                # warn if any objects exist
                objectsExist = False
                spritesExist = False
                for obj in items:
                    if isinstance(obj, type_obj):
                        objectsExist = True
                    elif isinstance(obj, type_spr) or isinstance(obj, type_ent):
                        spritesExist = True
                
                if objectsExist and spritesExist:
                    # no point in warning them if there are only objects
                    # since then, it will just silently reduce the offset and it won't be noticed
                    result = QtGui.QMessageBox.information(None, 'Warning',  'You are trying to move object(s) by an offset which isn\'t a multiple of 16. It will work, but the objects will not be able to move exactly the same amount as the sprites. Are you sure you want to do this?', QtGui.QMessageBox.Yes, QtGui.QMessageBox.No)
                    if result == QtGui.QMessageBox.No:
                        return
            
            xpoffset = xoffset * 1.5
            ypoffset = yoffset * 1.5
            
            global OverrideSnapping
            OverrideSnapping = True
            
            for obj in items:
                obj.setPos(obj.x() + xpoffset, obj.y() + ypoffset)
            
            OverrideSnapping = False
            
            SetDirty()    

    @QtCore.pyqtSlot()
    def MergeLocations(self):
        """Merges selected sprite locations"""
        items = self.scene.selectedItems()
        if len(items) == 0: return

        newx = 999999
        newy = 999999
        neww = 0
        newh = 0

        type_loc = SpriteLocationItem
        for obj in items:
            if isinstance(obj, type_loc):
                if obj.objx < newx:
                    newx = obj.objx
                if obj.objy < newy:
                    newy = obj.objy
                if obj.width + obj.objx > neww:
                    neww = obj.width + obj.objx
                if obj.height + obj.objy > newh:
                    newh = obj.height + obj.objy
                obj.delete()
                obj.setSelected(False)
                self.scene.removeItem(obj)
                self.levelOverview.update()
                SetDirty()

        if newx != 999999 and newy != 999999:
            allID = []
            newID = 1
            for i in Level.locations:
                allID.append(i.id)
            
            allID = set(allID) # faster "x in y" lookups for sets
            
            while newID <= 255:
                if newID not in allID:
                    break
                newID += 1
            
            loc = SpriteLocationItem(newx, newy, neww - newx, newh - newy, newID)
            
            mw = mainWindow
            loc.positionChanged = mw.HandleObjPosChange
            mw.scene.addItem(loc)
            
            Level.locations.append(loc)
            loc.setSelected(True)


    @QtCore.pyqtSlot()
    def HandleAddNewArea(self):
        """Adds a new area to the level"""
        if Level.areacount >= 4:
            QtGui.QMessageBox.warning(self, 'Reggie!', 'You have reached the maximum amount of areas in this level.\nDue to the game\'s limitations, Reggie! only allows you to add up to 4 areas to a level.')
            return
        
        if self.CheckDirty():
            return
        
        getit = open('reggiedata/blankcourse.bin', 'rb')
        blank = getit.read()
        getit.close()
        
        newID = Level.areacount + 1
        Level.arc['course/course%d.bin' % newID] = blank
        
        if not self.HandleSave(): return
        self.LoadLevel(Level.arcname, True, newID)
    
    
    @QtCore.pyqtSlot()
    def HandleImportArea(self):
        """Imports an area from another level"""
        if Level.areacount >= 4:
            QtGui.QMessageBox.warning(self, 'Reggie!', 'You have reached the maximum amount of areas in this level.\nDue to the game\'s limitations, Reggie! only allows you to add up to 4 areas to a level.')
            return
        
        if self.CheckDirty():
            return
        
        fn = QtGui.QFileDialog.getOpenFileName(self, 'Choose a level archive', '', 'Level archives (*.arc);;All Files(*)')
        if fn == '': return
        
        getit = open(unicode(fn), 'rb')
        arcdata = getit.read()
        getit.close()
        
        arc = archive.U8()
        arc._load(arcdata)
        
        # get the area count
        areacount = 0
        
        for item,val in arc.files:
            if val != None:
                # it's a file
                fname = item[item.rfind('/')+1:]
                if fname.startswith('course'):
                    maxarea = int(fname[6])
                    if maxarea > areacount: areacount = maxarea
        
        # choose one
        dlg = AreaChoiceDialog(areacount)
        if dlg.exec_() == QtGui.QDialog.Rejected:
            return
        
        area = dlg.areaCombo.currentIndex()+1
        
        # get the required files
        reqcourse = 'course%d.bin' % area
        reql0 = 'course%d_bgdatL0.bin' % area
        reql1 = 'course%d_bgdatL1.bin' % area
        reql2 = 'course%d_bgdatL2.bin' % area
        
        course = None
        l0 = None
        l1 = None
        l2 = None
        
        for item,val in arc.files:
            if val != None:
                fname = item[item.rfind('/')+1:]
                if fname == reqcourse:
                    course = val
                elif fname == reql0:
                    l0 = val
                elif fname == reql1:
                    l1 = val
                elif fname == reql2:
                    l2 = val
        
        # add them to our U8
        newID = Level.areacount + 1
        Level.arc['course/course%d.bin' % newID] = course
        if l0 != None: Level.arc['course/course%d_bgdatL0.bin' % newID] = l0
        if l1 != None: Level.arc['course/course%d_bgdatL1.bin' % newID] = l1
        if l2 != None: Level.arc['course/course%d_bgdatL2.bin' % newID] = l2
        
        if not self.HandleSave(): return
        self.LoadLevel(Level.arcname, True, newID)
    
    
    @QtCore.pyqtSlot()
    def HandleDeleteArea(self):
        """Deletes the current area"""
        result = QtGui.QMessageBox.warning(self, 'Reggie!', 'Are you <b>sure</b> you want to delete this area?<br><br>The level will automatically save afterwards - there is no way<br>you can undo the deletion or get it back afterwards!', QtGui.QMessageBox.Yes | QtGui.QMessageBox.No, QtGui.QMessageBox.No)
        if result == QtGui.QMessageBox.No: return
        
        if not self.HandleSave(): return
        
        # this is really going to be annoying >_<
        deleting = Level.areanum
        
        newfiles = []
        for item,val in Level.arc.files:
            if val != None:
                if item.startswith('course/course'):
                    id = int(item[13])
                    if id < deleting:
                        # pass it through anyway
                        newfiles.append((item,val))
                    elif id == deleting:
                        # remove it
                        continue
                    else:
                        # push the number down by one
                        fname = 'course/course%d%s' % (id - 1, item[14:])
                        newfiles.append((fname,val))
            else:
                newfiles.append((item,val))
        
        Level.arc.files = newfiles
        
        # no error checking. if it saved last time, it will probably work now
        f = open(Level.arcname, 'wb')
        f.write(Level.arc._dump())
        f.close()
        self.LoadLevel(Level.arcname, True, 1)
    
    
    @QtCore.pyqtSlot()
    def HandleChangeGamePath(self):
        """Change the game path used"""
        if self.CheckDirty(): return
        
        path = None
        while not isValidGamePath(path):
            path = QtGui.QFileDialog.getExistingDirectory(None, 'Choose the game\'s Stage folder')
            if path == '':
                return
            
            path = unicode(path)
            
            if not isValidGamePath(path):
                QtGui.QMessageBox.information(None, 'Error',  'This folder doesn\'t have all of the files from the extracted NSMBWii Stage folder.')
            else:
                settings.setValue('GamePath', path)
                break
        
        SetGamePath(path)
        self.LoadLevel('01-01', False, 1)
    
    
    @QtCore.pyqtSlot()
    def HandleNewLevel(self):
        """Create a new level"""
        if self.CheckDirty(): return
        self.LoadLevel(None, False, 1)
    
    
    @QtCore.pyqtSlot()
    def HandleOpenFromName(self):
        """Open a level using the level picker"""
        if self.CheckDirty(): return
        
        dlg = ChooseLevelNameDialog()
        if dlg.exec_() == QtGui.QDialog.Accepted:
            #start = time.clock()
            self.LoadLevel(dlg.currentlevel, False, 1)
            #end = time.clock()
            #print 'Loaded in ' + str(end - start)
    
    
    @QtCore.pyqtSlot()
    def HandleOpenFromFile(self):
        """Open a level using the filename"""
        if self.CheckDirty(): return
        
        fn = QtGui.QFileDialog.getOpenFileName(self, 'Choose a level archive', '', 'Level archives (*.arc);;All Files(*)')
        if fn == '': return
        self.LoadLevel(unicode(fn), True, 1)
    
    
    @QtCore.pyqtSlot()
    def HandleSave(self):
        """Save a level back to the archive"""
        if not Level.hasName:
            self.HandleSaveAs()
            return
        
        global Dirty, AutoSaveDirty
        data = Level.save()
        try:
            f = open(Level.arcname, 'wb')
            f.write(data)
            f.close()
        except IOError, e:
            QtGui.QMessageBox.warning(None, 'Error', 'Error while Reggie was trying to save the level:\n(#%d) %s\n\n(Your work has not been saved! Try saving it under a different filename or in a different folder.)' % (e.args[0], e.args[1]))
            return False
        
        Dirty = False
        AutoSaveDirty = False
        self.UpdateTitle()
        
        settings.setValue('AutoSaveFilePath', Level.arcname)
        settings.setValue('AutoSaveFileData', 'x')
        return True
    
    
    @QtCore.pyqtSlot()
    def HandleSaveAs(self):
        """Save a level back to the archive, with a new filename"""
        fn = QtGui.QFileDialog.getSaveFileName(self, 'Choose a new filename', '', 'Level archives (*.arc);;All Files(*)')
        if fn == '': return
        fn = unicode(fn)
        
        global Dirty, AutoSaveDirty
        Dirty = False
        AutoSaveDirty = False
        Dirty = False
        
        Level.arcname = fn
        Level.filename = os.path.basename(fn)
        Level.hasName = True
        
        data = Level.save()
        f = open(fn, 'wb')
        f.write(data)
        f.close()
        settings.setValue('AutoSaveFilePath', fn)
        settings.setValue('AutoSaveFileData', 'x')
        
        self.UpdateTitle()
    
    
    @QtCore.pyqtSlot()
    def HandleExit(self):
        """Exit the editor. Why would you want to do this anyway?"""
        self.close()
    
    
    @QtCore.pyqtSlot(int)
    def HandleSwitchArea(self, idx):
        """Handle activated signals for areaComboBox"""
        if self.CheckDirty():
            self.areaComboBox.setCurrentIndex(Level.areanum)
            return
        
        if Level.areanum != idx+1:
            self.LoadLevel(Level.arcname, True, idx+1)
    
    
    @QtCore.pyqtSlot(bool)
    def HandleUpdateLayer0(self, checked):
        """Handle toggling of layer 0 being showed"""
        global ShowLayer0
        ShowLayer0 = checked
        
        for obj in Level.layers[0]:
            obj.setVisible(checked)
        
        self.scene.update()
    
    
    @QtCore.pyqtSlot(bool)
    def HandleUpdateLayer1(self, checked):
        """Handle toggling of layer 1 being showed"""
        global ShowLayer1
        ShowLayer1 = checked
        
        for obj in Level.layers[1]:
            obj.setVisible(checked)
        
        self.scene.update()
    
    
    @QtCore.pyqtSlot(bool)
    def HandleUpdateLayer2(self, checked):
        """Handle toggling of layer 2 being showed"""
        global ShowLayer2
        ShowLayer2 = checked
        
        for obj in Level.layers[2]:
            obj.setVisible(checked)
        
        self.scene.update()
    
    
    @QtCore.pyqtSlot(bool)
    def HandleObjectsFreeze(self, checked):
        """Handle toggling of objects being frozen"""
        settings.setValue('FreezeObjects', checked)
        
        checked = not checked
        
        global ObjectsNonFrozen
        ObjectsNonFrozen = checked
        flag1 = QtGui.QGraphicsItem.ItemIsSelectable
        flag2 = QtGui.QGraphicsItem.ItemIsMovable
        
        for layer in Level.layers:
            for obj in layer:
                obj.setFlag(flag1, checked)
                obj.setFlag(flag2, checked)
        
        self.scene.update()
    
    
    @QtCore.pyqtSlot(bool)
    def HandleSpritesFreeze(self, checked):
        """Handle toggling of sprites being frozen"""
        settings.setValue('FreezeSprites', checked)
        
        checked = not checked
        
        global SpritesNonFrozen
        SpritesNonFrozen = checked
        flag1 = QtGui.QGraphicsItem.ItemIsSelectable
        flag2 = QtGui.QGraphicsItem.ItemIsMovable
        
        for spr in Level.sprites:
            spr.setFlag(flag1, checked)
            spr.setFlag(flag2, checked)
        
        self.scene.update()
    
    
    @QtCore.pyqtSlot(bool)
    def HandleEntrancesFreeze(self, checked):
        """Handle toggling of entrances being frozen"""
        settings.setValue('FreezeEntrances', checked)
        
        checked = not checked
        
        global EntrancesNonFrozen
        EntrancesNonFrozen = checked
        flag1 = QtGui.QGraphicsItem.ItemIsSelectable
        flag2 = QtGui.QGraphicsItem.ItemIsMovable
        
        for ent in Level.entrances:
            ent.setFlag(flag1, checked)
            ent.setFlag(flag2, checked)
        
        self.scene.update()
    
    
    @QtCore.pyqtSlot(bool)
    def HandleLocationsFreeze(self, checked):
        """Handle toggling of locations being frozen"""
        settings.setValue('FreezeLocations', checked)
        
        checked = not checked
        
        global LocationsNonFrozen
        LocationsNonFrozen = checked
        flag1 = QtGui.QGraphicsItem.ItemIsSelectable
        flag2 = QtGui.QGraphicsItem.ItemIsMovable
        
        for loc in Level.locations:
            loc.setFlag(flag1, checked)
            loc.setFlag(flag2, checked)
        
        self.scene.update()
    
    
    @QtCore.pyqtSlot(bool)
    def HandleShowGrid(self, checked):
        """Handle toggling of the grid being showed"""
        settings.setValue('GridEnabled', checked)
        
        global GridEnabled
        GridEnabled = checked
        self.scene.update()
    
    
    @QtCore.pyqtSlot()
    def HandleZoomIn(self):
        """Handle zooming in"""
        z = self.ZoomLevel
        zi = self.ZoomLevels.index(z)
        zi += 1
        if zi < len(self.ZoomLevels):
            self.ZoomTo(self.ZoomLevels[zi])
    
    
    @QtCore.pyqtSlot()
    def HandleZoomOut(self):
        """Handle zooming out"""
        z = self.ZoomLevel
        zi = self.ZoomLevels.index(z)
        zi -= 1
        if zi >= 0:
            self.ZoomTo(self.ZoomLevels[zi])
    
    
    @QtCore.pyqtSlot()
    def HandleZoomActual(self):
        """Handle zooming to the actual size"""
        self.ZoomTo(100.0)
    
    
    def ZoomTo(self, z):
        """Zoom to a specific level"""
        tr = QtGui.QTransform()
        tr.scale(z / 100.0, z / 100.0)
        self.ZoomLevel = z
        self.view.setTransform(tr)
        self.levelOverview.mainWindowScale = z/100.0
        
        zi = self.ZoomLevels.index(z)
        self.actions['zoomin'].setEnabled(zi < len(self.ZoomLevels) - 1)
        self.actions['zoomactual'].setEnabled(z != 100.0)
        self.actions['zoomout'].setEnabled(zi > 0)
        
        self.scene.update()
    
    
    @QtCore.pyqtSlot(int, int)
    def HandleOverviewClick(self, x, y):
        """Handle position changes from the level overview"""
        self.view.centerOn(x, y)
        self.levelOverview.update()
        
    
    def closeEvent(self, event):
        """Handler for the main window close event"""
        
        if self.CheckDirty():
            event.ignore()
        else:
            # save our state
            self.spriteEditorDock.setVisible(False)
            self.entranceEditorDock.setVisible(False)
            self.locationEditorDock.setVisible(False)
            self.defaultPropDock.setVisible(False)
            
            settings.setValue('MainWindowGeometry', self.saveGeometry())
            settings.setValue('MainWindowState', self.saveState(0))
            
            if hasattr(self, 'HelpBoxInstance'):
                self.HelpBoxInstance.close()
            
            if hasattr(self, 'TipsBoxInstance'):
                self.TipsBoxInstance.close()
            
            settings.setValue('LastLevel', unicode(Level.arcname))
            
            settings.setValue('AutoSaveFilePath', 'none')
            settings.setValue('AutoSaveFileData', 'x')
            
            event.accept()
    
    
    def LoadLevel(self, name, fullpath, area):
        """Load a level into the editor"""
        
        if name != None:
            if fullpath:
                checkname = name
            else:
                checkname = os.path.join(gamePath, name+'.arc')
            
            if not IsNSMBLevel(checkname):
                QtGui.QMessageBox.warning(self, 'Reggie!', 'This file doesn\'t seem to be a valid level.', QtGui.QMessageBox.Ok)
                return False
        
        global Dirty, DirtyOverride
        Dirty = False
        DirtyOverride += 1
        
        # first clear out what we have
        self.scene.clearSelection()
        self.CurrentSelection = []
        self.scene.clear()
        
        # reset these here, because if the showlayer variables are set
        # after creating the objects, it uses the old values
        global CurrentLayer, ShowLayer0, ShowLayer1, ShowLayer2
        CurrentLayer = 1
        ShowLayer0 = True
        ShowLayer1 = True
        ShowLayer2 = True
        
        
        # track progress.. but we'll only do this if we don't have
        # the NSMBLib because otherwise it's far too fast
        if HaveNSMBLib:
            progress = None
        else:
            progress = QtGui.QProgressDialog(self)
            # yes, I did alphabetise the setX calls on purpose..
            # code OCD is wonderful x_x
            progress.setCancelButton(None)
            progress.setMinimumDuration(0)
            progress.setRange(0,7)
            progress.setWindowModality(QtCore.Qt.WindowModal)
            progress.setWindowTitle('Reggie!')
        
        # this tracks progress
        # current stages:
        # - 0: Loading level data
        # [LevelUnit.__init__ is entered here]
        # - 1: Loading tilesets [1/2/3/4 allocated for each tileset]
        # - 5: Loading layers
        # [Control is returned to LoadLevel]
        # - 6: Loading objects
        # - 7: Preparing editor
        
        # stop it from snapping when created...
        global OverrideSnapping
        OverrideSnapping = True
        
        if progress != None:
            progress.setLabelText('Loading level data...')
            progress.setValue(0)
        
        global Level
        Level = LevelUnit()
        
        if name == None:
            Level.newLevel()
        else:
            global RestoredFromAutoSave
            if RestoredFromAutoSave:
                RestoredFromAutoSave = False
                Level.loadLevel('AUTO_FLAG', True, 1, progress)
            else:
                Level.loadLevel(name, fullpath, area, progress)

        OverrideSnapping = False
        
        # prepare the object picker
        if progress != None:
            progress.setLabelText('Loading objects...')
            progress.setValue(6)
        
        self.objUseLayer1.setChecked(True)
        
        self.objPicker.LoadFromTilesets()
        
        self.creationTabs.setCurrentIndex(0)
        self.creationTabs.setTabEnabled(0, (Level.tileset0 != ''))
        self.creationTabs.setTabEnabled(1, (Level.tileset1 != ''))
        self.creationTabs.setTabEnabled(2, (Level.tileset2 != ''))
        self.creationTabs.setTabEnabled(3, (Level.tileset3 != ''))
        
        # add all the objects to the scene
        if progress != None:
            progress.setLabelText('Preparing editor...')
            progress.setValue(7)
        
        scene = self.scene
        scene.clear()
        
        entlist = self.entranceList
        entlist.clear()
        entlist.selectionModel().setCurrentIndex(QtCore.QModelIndex(), QtGui.QItemSelectionModel.Clear)
        #entlist.selectionModel().clearSelection()
        
        addItem = scene.addItem
        
        pcEvent = self.HandleObjPosChange
        for layer in reversed(Level.layers):
            for obj in layer:
                obj.positionChanged = pcEvent
                addItem(obj)
        
        pcEvent = self.HandleSprPosChange
        for spr in Level.sprites:
            spr.positionChanged = pcEvent
            addItem(spr)
        
        pcEvent = self.HandleEntPosChange
        for ent in Level.entrances:
            addItem(ent)
            ent.positionChanged = pcEvent
            ent.listitem = QtGui.QListWidgetItem(ent.ListString())
            entlist.addItem(ent.listitem)
        
        for zone in Level.zones:
            addItem(zone)
        
        pcEvent = self.HandleLocPosChange
        scEvent = self.HandleLocSizeChange
        for location in Level.locations:
            addItem(location)
            location.positionChanged = pcEvent
            location.sizeChanged = scEvent
        
        # fill up the area list
        self.areaComboBox.clear()
        for i in xrange(1,Level.areacount+1):
            self.areaComboBox.addItem('Area '+str(i))
        
        self.areaComboBox.setCurrentIndex(area-1)
        self.levelOverview.update()
        
        # scroll to the initial entrance
        startEntID = Level.startEntrance
        startEnt = None
        for ent in Level.entrances:
            if ent.entid == startEntID: startEnt = ent
        
        self.view.centerOn(0,0)
        if startEnt != None: self.view.centerOn(startEnt.objx*1.5, startEnt.objy*1.5)
        self.ZoomTo(100.0)
        
        # reset some editor things
        self.actions['showlayer0'].setChecked(True)
        self.actions['showlayer1'].setChecked(True)
        self.actions['showlayer2'].setChecked(True)
        self.actions['addarea'].setEnabled(Level.areacount < 4)
        self.actions['importarea'].setEnabled(Level.areacount < 4)
        self.actions['deletearea'].setEnabled(Level.areacount > 1)
        DirtyOverride -= 1
        self.UpdateTitle()
        
        self.scene.update()
        
        self.levelOverview.Reset()
        self.levelOverview.update()
        QtCore.QTimer.singleShot(20, self.levelOverview.update)
        
        return True
    
    
    @QtCore.pyqtSlot()
    def ReloadTilesets(self):
        tilesets = [Level.tileset0, Level.tileset1, Level.tileset2, Level.tileset3]
        for idx, name in zip(xrange(4), tilesets):
            if name != None and name != '':
                LoadTileset(idx, name)
        
        self.objPicker.LoadFromTilesets()
        
        for layer in Level.layers:
            for obj in layer:
                obj.updateObjCache()
        
        self.scene.update()
        
        
        global Sprites
        Sprites = None
        LoadSpriteData()
    
    
    @QtCore.pyqtSlot()
    def ChangeSelectionHandler(self):
        """Update the visible panels whenever the selection changes"""
        if self.SelectionUpdateFlag: return
        
        try:
            selitems = self.scene.selectedItems()
        except RuntimeError:
            # must catch this error: if you close the app while something is selected,
            # you get a RuntimeError about the "underlying C++ object being deleted"
            return
        
        # do this to avoid flicker
        showSpritePanel = False
        showEntrancePanel = False
        showLocationPanel = False
        updateModeInfo = False
        
        # clear our variables
        self.selObj = None
        self.selObjs = None
        
        self.entranceList.setCurrentItem(None)
        
        # possibly a small optimisation
        func_ii = isinstance
        type_obj = LevelObjectEditorItem
        type_spr = SpriteEditorItem
        type_ent = EntranceEditorItem
        type_loc = SpriteLocationItem

        if len(selitems) == 0:
            # nothing is selected
            self.actions['cut'].setEnabled(False)
            self.actions['copy'].setEnabled(False)
            self.actions['shiftobjects'].setEnabled(False)
            self.actions['mergelocations'].setEnabled(False)
            
        elif len(selitems) == 1:
            # only one item, check the type
            self.actions['cut'].setEnabled(True)
            self.actions['copy'].setEnabled(True)
            self.actions['shiftobjects'].setEnabled(True)
            self.actions['mergelocations'].setEnabled(True)

            item = selitems[0]
            self.selObj = item
            if func_ii(item, type_spr):
                showSpritePanel = True
                updateModeInfo = True
            elif func_ii(item, type_ent):
                self.creationTabs.setCurrentIndex(5)
                self.UpdateFlag = True
                self.entranceList.setCurrentItem(item.listitem)
                self.UpdateFlag = False
                showEntrancePanel = True
                updateModeInfo = True
            elif func_ii(item, type_loc):
                showLocationPanel = True
                updateModeInfo = True

        else:
            updateModeInfo = True
            
            # more than one item
            self.actions['cut'].setEnabled(True)
            self.actions['copy'].setEnabled(True)
            self.actions['shiftobjects'].setEnabled(True)
            self.actions['mergelocations'].setEnabled(True)
        
        #for x in self.CurrentSelection:
        #    s = x.scene()
        #    if s != None:
        #        s.update(x.x(), x.y(), x.BoundingRect.width(), x.BoundingRect.height())
        #
        #for x in selitems:
        #    x.scene().update(x.x(), x.y(), x.BoundingRect.width(), x.BoundingRect.height())
        
        self.CurrentSelection = selitems
        
        self.spriteEditorDock.setVisible(showSpritePanel)
        self.entranceEditorDock.setVisible(showEntrancePanel)
        self.locationEditorDock.setVisible(showLocationPanel)
        if updateModeInfo: self.UpdateModeInfo()
    
    
    def HandleObjPosChange(self, obj, oldx, oldy, x, y):
        """Handle the object being dragged"""
        if obj == self.selObj:
            if oldx == x and oldy == y: return
            SetDirty()
        self.levelOverview.update()
    
    
    @QtCore.pyqtSlot(int)
    def CreationTabChanged(self, nt):
        """Handles the selected tab in the creation panel changing"""
        if hasattr(self, 'objPicker'):
            if nt >= 0 and nt <= 3:
                self.objPicker.ShowTileset(nt)
                self.creationTabs.widget(nt).setLayout(self.createObjectLayout)
            self.defaultPropDock.setVisible(False)
        global CurrentPaintType
        CurrentPaintType = nt
    
    
    @QtCore.pyqtSlot(int)
    def LayerChoiceChanged(self, nl):
        """Handles the selected layer changing"""
        global CurrentLayer
        CurrentLayer = nl
        
        # should we replace?
        if QtGui.QApplication.keyboardModifiers() == QtCore.Qt.AltModifier:
            items = self.scene.selectedItems()
            type_obj = LevelObjectEditorItem
            tileset = CurrentPaintType
            level = Level
            change = []
            
            if nl == 0:
                newLayer = level.layers[0]
            elif nl == 1:
                newLayer = level.layers[1]
            else:
                newLayer = level.layers[2]
            
            for x in items:
                if isinstance(x, type_obj) and x.layer != nl:
                    change.append(x)
            
            if len(change) > 0:
                change.sort(key=lambda x: x.zValue())
                
                if len(newLayer) == 0:
                    z = (2 - nl) * 8192
                else:
                    z = newLayer[-1].zValue() + 1
                
                if nl == 0:
                    newVisibility = ShowLayer0
                elif nl == 1:
                    newVisibility = ShowLayer1
                else:
                    newVisibility = ShowLayer2
                
                for item in change:
                    level.RemoveFromLayer(item)
                    item.layer = nl
                    newLayer.append(item)
                    item.setZValue(z)
                    item.setVisible(newVisibility)
                    item.update()
                    z += 1
            
            self.scene.update()
            SetDirty()
    
    
    @QtCore.pyqtSlot(int)
    def ObjectChoiceChanged(self, type):
        """Handles a new object being chosen"""
        global CurrentObject
        CurrentObject = type
    
    
    @QtCore.pyqtSlot(int)
    def ObjectReplace(self, type):
        """Handles a new object being chosen to replace the selected objects"""
        items = self.scene.selectedItems()
        type_obj = LevelObjectEditorItem
        tileset = CurrentPaintType
        changed = False
        
        for x in items:
            if isinstance(x, type_obj) and (x.tileset != tileset or x.type != type):
                x.SetType(tileset, type)
                x.update()
                changed = True
        
        if changed:
            SetDirty()
    
    
    @QtCore.pyqtSlot(int)
    def SpriteChoiceChanged(self, type):
        """Handles a new sprite being chosen"""
        global CurrentSprite
        CurrentSprite = type
        if type != 1000:
            self.defaultDataEditor.setSprite(type)
            self.defaultDataEditor.data = '\0\0\0\0\0\0\0\0\0\0'
            self.defaultDataEditor.update()
            self.defaultPropButton.setEnabled(True)
        else:
            self.defaultPropButton.setEnabled(False)
            self.defaultPropDock.setVisible(False)
            self.defaultDataEditor.update()
    
    
    @QtCore.pyqtSlot(int)
    def SpriteReplace(self, type):
        """Handles a new sprite type being chosen to replace the selected sprites"""
        items = self.scene.selectedItems()
        type_spr = SpriteEditorItem
        changed = False
        
        for x in items:
            if isinstance(x, type_spr):
                x.SetType(type)
                x.spritedata = self.defaultDataEditor.data
                x.update()
                changed = True
        
        if changed:
            SetDirty()
        
        self.ChangeSelectionHandler()
    
    
    @QtCore.pyqtSlot(int)
    def SelectNewSpriteView(self, type):
        """Handles a new sprite view being chosen"""
        cat = SpriteCategories[type]
        self.sprPicker.SwitchView(cat)
        
        isSearch = (type == len(SpriteCategories) - 1)
        layout = self.spriteSearchLayout
        layout.itemAt(0).widget().setVisible(isSearch)
        layout.itemAt(1).widget().setVisible(isSearch)
    
    
    @QtCore.pyqtSlot(str)
    def NewSearchTerm(self, text):
        """Handles a new sprite search term being entered"""
        self.sprPicker.SetSearchString(text)
    
    
    @QtCore.pyqtSlot()
    def ShowDefaultProps(self):
        """Handles the Show Default Properties button being clicked"""
        self.defaultPropDock.setVisible(True)
    
    
    def HandleSprPosChange(self, obj, oldx, oldy, x, y):
        """Handle the sprite being dragged"""
        if obj == self.selObj:
            if oldx == x and oldy == y: return
            SetDirty()
    
    
    @QtCore.pyqtSlot('PyQt_PyObject')
    def SpriteDataUpdated(self, data):
        """Handle the current sprite's data being updated"""
        if self.spriteEditorDock.isVisible():
            obj = self.selObj
            obj.spritedata = data
            SetDirty()
            
            if obj.dynamicSize:
                obj.UpdateDynamicSizing()
    
    
    def HandleEntPosChange(self, obj, oldx, oldy, x, y):
        """Handle the entrance being dragged"""
        if oldx == x and oldy == y: return
        obj.listitem.setText(obj.ListString())
        if obj == self.selObj:
            SetDirty()
    
    
    @QtCore.pyqtSlot(QtGui.QListWidgetItem)
    def HandleEntranceSelectByList(self, item):
        """Handle an entrance being selected from the list"""
        if self.UpdateFlag: return
        
        # can't really think of any other way to do this
        #item = self.entranceList.item(row)
        ent = None
        for check in Level.entrances:
            if check.listitem == item:
                ent = check
                break
        if ent == None: return
        
        ent.ensureVisible(QtCore.QRectF(), 192, 192)
        self.scene.clearSelection()
        ent.setSelected(True)
    
    
    def HandleLocPosChange(self, loc, oldx, oldy, x, y):
        """Handle the location being dragged"""
        if loc == self.selObj:
            if oldx == x and oldy == y: return
            self.locationEditor.setLocation(loc)
            SetDirty()
        self.levelOverview.update()
    
    
    def HandleLocSizeChange(self, loc, width, height):
        """Handle the location being resized"""
        if loc == self.selObj:
            self.locationEditor.setLocation(loc)
            SetDirty()
        self.levelOverview.update()
    
    
    def UpdateModeInfo(self):
        """Change the info in the currently visible panel"""
        self.UpdateFlag = True
        
        if self.spriteEditorDock.isVisible():
            obj = self.selObj
            self.spriteDataEditor.setSprite(obj.type)
            self.spriteDataEditor.data = obj.spritedata
            self.spriteDataEditor.update()
        elif self.entranceEditorDock.isVisible():
            self.entranceEditor.setEntrance(self.selObj)
        elif self.locationEditorDock.isVisible():
            self.locationEditor.setLocation(self.selObj)
        
        self.UpdateFlag = False
    
    
    @QtCore.pyqtSlot(int, int)
    def PositionHovered(self, x, y):
        """Handle a position being hovered in the view"""
        info = ''
        hovereditems = self.scene.items(QtCore.QPointF(x,y))
        hovered = None
        type_zone = ZoneItem
        type_loc = SpriteLocationItem
        for item in hovereditems:
            if not isinstance(item, type_zone) and not isinstance(item, type_loc):
                hovered = item
                break
        
        if hovered != None:
            if isinstance(hovered, LevelObjectEditorItem):
                info = ' - Object under mouse: size %dx%d at %d,%d on layer %d; type %d from tileset %d' % (hovered.width, hovered.height, hovered.objx, hovered.objy, hovered.layer, hovered.type, hovered.tileset+1)
            elif isinstance(hovered, SpriteEditorItem):
                info = ' - Sprite under mouse: %s at %d,%d' % (hovered.name, hovered.objx, hovered.objy)
            elif isinstance(hovered, EntranceEditorItem):
                info = ' - Entrance under mouse: %s at %d,%d %s' % (hovered.name, hovered.objx, hovered.objy, hovered.destination)
            elif isinstance(hovered, EntranceEditorItem):
                info = ' - Sprite Area under mouse: %s at %d,%d - width %d / height %d,  %s' % (hovered.name, hovered.objx, hovered.objy, hovered.width, hovered.height, hovered.destination)
        
        self.posLabel.setText('(%d,%d) - (%d,%d)%s' % (int(x/24),int(y/24),int(x/1.5),int(y/1.5),info))
    
    
    def keyPressEvent(self, event):
        """Handles key press events for the main window if needed"""
        if event.key() == QtCore.Qt.Key_Delete or event.key() == QtCore.Qt.Key_Backspace:
            sel = self.scene.selectedItems()
            self.SelectionUpdateFlag = True
            if len(sel) > 0:
                for obj in sel:
                    obj.delete()
                    obj.setSelected(False)
                    self.scene.removeItem(obj)
                    self.levelOverview.update()
                SetDirty()
                event.accept()
                self.SelectionUpdateFlag = False
                self.ChangeSelectionHandler()
                return
        self.levelOverview.update()
        
        QtGui.QMainWindow.keyPressEvent(self, event)

        
    @QtCore.pyqtSlot()
    def HandleAreaOptions(self):
        """Pops up the options for Area Dialogue"""        
        dlg = AreaOptionsDialog()
        if dlg.exec_() == QtGui.QDialog.Accepted:
            SetDirty()
            Level.timeLimit = dlg.LoadingTab.timer.value() - 200
            Level.startEntrance = dlg.LoadingTab.entrance.value()
            
            if dlg.LoadingTab.wrap.isChecked():
                Level.wrapFlag |= 1
            else:
                Level.wrapFlag &= ~1
            
            tileset0tmp = Level.tileset0
            tileset1tmp = Level.tileset1
            tileset2tmp = Level.tileset2
            tileset3tmp = Level.tileset3
            
            oldnames = [Level.tileset0, Level.tileset1, Level.tileset2, Level.tileset3]
            assignments = ['Level.tileset0', 'Level.tileset1', 'Level.tileset2', 'Level.tileset3']
            widgets = [dlg.TilesetsTab.tile0, dlg.TilesetsTab.tile1, dlg.TilesetsTab.tile2, dlg.TilesetsTab.tile3]
            
            toUnload = []
            
            for idx, oldname, assignment, widget in zip(xrange(4), oldnames, assignments, widgets):
                ts_idx = widget.currentIndex()
                fname = unicode(widget.itemData(ts_idx).toPyObject())
                
                if fname == '':
                    toUnload.append(idx)
                    continue
                elif fname.startswith('[CUSTOM]'):
                    fname = fname[8:]
                    if fname == '': continue
                
                exec (assignment + ' = fname')
                LoadTileset(idx, fname)
            
            for idx in toUnload:
                exec ('Level.tileset%d = ""' % idx)
                UnloadTileset(idx)
            
            defEvents = 0
            eventChooser = dlg.LoadingTab.eventChooser
            checked = QtCore.Qt.Checked
            for i in xrange(32):
                if eventChooser.item(i).checkState() == checked:
                    defEvents |= (1 << i)
            
            Level.defEvents = defEvents
            
            mainWindow.objPicker.LoadFromTilesets()
            self.creationTabs.setCurrentIndex(0)
            self.creationTabs.setTabEnabled(0, (Level.tileset0 != ''))
            self.creationTabs.setTabEnabled(1, (Level.tileset1 != ''))
            self.creationTabs.setTabEnabled(2, (Level.tileset2 != ''))
            self.creationTabs.setTabEnabled(3, (Level.tileset3 != ''))
            
            for layer in Level.layers:
                for obj in layer:
                    obj.updateObjCache()
            
            self.scene.update()

    @QtCore.pyqtSlot()
    def HandleZones(self):
        """Pops up the options for Zone dialogue"""        
        dlg = ZonesDialog()
        if dlg.exec_() == QtGui.QDialog.Accepted:
            SetDirty()
            i = 0
            
            # resync the zones
            items = self.scene.items()
            func_ii = isinstance
            type_zone = ZoneItem
            
            for item in items:
                if func_ii(item, type_zone):
                    self.scene.removeItem(item)
            
            Level.zones = []
            
            for tab in dlg.zoneTabs:
                z = tab.zoneObj
                z.id = i
                z.UpdateTitle()
                Level.zones.append(z)
                self.scene.addItem(z)
                
                if tab.Zone_xpos.value() < 16:
                    z.objx = 16
                elif tab.Zone_xpos.value() > 24560:
                    z.objx = 24560
                else:
                    z.objx = tab.Zone_xpos.value()
                
                if tab.Zone_ypos.value() < 16:
                    z.objy = 16
                elif tab.Zone_ypos.value() > 12272:
                    z.objy = 12272
                else:
                    z.objy = tab.Zone_ypos.value()
                    
                if (tab.Zone_width.value() + tab.Zone_xpos.value()) > 24560:
                    z.width = 24560 - tab.Zone_xpos.value()
                else:
                    z.width = tab.Zone_width.value()
                
                if (tab.Zone_height.value() + tab.Zone_ypos.value()) > 12272:
                    z.height = 12272 - tab.Zone_ypos.value()
                else:
                    z.height = tab.Zone_height.value()
                
                z.prepareGeometryChange()
                z.UpdateRects()
                z.setPos(z.objx*1.5, z.objy*1.5)
                
                z.modeldark = tab.Zone_modeldark.currentIndex()
                z.terraindark = tab.Zone_terraindark.currentIndex()
                
                if tab.Zone_xtrack.isChecked():
                    if tab.Zone_ytrack.isChecked():
                        if tab.Zone_camerabias.isChecked():
                            #Xtrack, YTrack, Bias
                            if tab.Zone_camerazoom.currentIndex() == 0:
                                z.cammode = 0
                                z.camzoom = 8
                                QtGui.QMessageBox.warning(None, 'Error', 'Zoom level -2 does not support bias modes.')
                            elif tab.Zone_camerazoom.currentIndex() == 1:
                                z.cammode = 3
                                z.camzoom = 9
                                QtGui.QMessageBox.warning(None, 'Error', 'Zoom level -1 does not support bias modes.')
                            elif tab.Zone_camerazoom.currentIndex() == 2:
                                z.cammode = 0
                                z.camzoom = 1
                            elif tab.Zone_camerazoom.currentIndex() == 3:
                                z.cammode = 0
                                z.camzoom = 6
                            elif tab.Zone_camerazoom.currentIndex() == 4:
                                z.cammode = 0
                                z.camzoom = 4
                            elif tab.Zone_camerazoom.currentIndex() == 5:
                                z.cammode = 0
                                z.camzoom = 3
                            elif tab.Zone_camerazoom.currentIndex() == 6:
                                z.cammode = 3
                                z.camzoom = 3
                        else:
                            #Xtrack, YTrack, No Bias
                            if tab.Zone_camerazoom.currentIndex() == 0:
                                z.cammode = 0
                                z.camzoom = 8
                            elif tab.Zone_camerazoom.currentIndex() == 1:
                                z.cammode = 3
                                z.camzoom = 9
                            elif tab.Zone_camerazoom.currentIndex() == 2:
                                z.cammode = 0
                                z.camzoom = 0
                            elif tab.Zone_camerazoom.currentIndex() == 3:
                                z.cammode = 0
                                z.camzoom = 7
                            elif tab.Zone_camerazoom.currentIndex() == 4:
                                z.cammode = 0
                                z.camzoom = 11
                            elif tab.Zone_camerazoom.currentIndex() == 5:
                                z.cammode = 3
                                z.camzoom = 2
                            elif tab.Zone_camerazoom.currentIndex() == 6:
                                z.cammode = 3
                                z.camzoom = 7
                    else:
                        if tab.Zone_camerabias.isChecked():
                            #Xtrack, No YTrack, Bias
                            z.cammode = 6
                            if tab.Zone_camerazoom.currentIndex() == 0:
                                z.camzoom = 8
                                QtGui.QMessageBox.warning(None, 'Error', 'Zoom level -2 does not support bias modes.')
                            elif tab.Zone_camerazoom.currentIndex() == 1:
                                z.camzoom = 1
                                QtGui.QMessageBox.warning(None, 'Error', 'Zoom level -1 is not supported with these Tracking modes. Set to Zoom level 0')
                            elif tab.Zone_camerazoom.currentIndex() == 2:
                                z.camzoom = 2
                            elif tab.Zone_camerazoom.currentIndex() == 3:
                                z.camzoom = 6
                            elif tab.Zone_camerazoom.currentIndex() == 4:
                                z.camzoom = 4
                            elif tab.Zone_camerazoom.currentIndex() == 5:
                                z.camzoom = 3
                            elif tab.Zone_camerazoom.currentIndex() == 6:
                                z.camzoom = 16
                                QtGui.QMessageBox.warning(None, 'Error', 'Zoom mode 4 can be glitchy with these settings.')
                        else:
                            #Xtrack, No YTrack, No Bias
                            z.cammode = 6
                            if tab.Zone_camerazoom.currentIndex() == 0:
                                z.camzoom = 8
                            elif tab.Zone_camerazoom.currentIndex() == 1:
                                z.camzoom = 0
                                QtGui.QMessageBox.warning(None, 'Error', 'Zoom level -1 is not supported with these Tracking modes. Set to Zoom level 0')
                            elif tab.Zone_camerazoom.currentIndex() == 2:
                                z.camzoom = 0
                            elif tab.Zone_camerazoom.currentIndex() == 3:
                                z.camzoom = 7
                            elif tab.Zone_camerazoom.currentIndex() == 4:
                                z.camzoom = 11
                            elif tab.Zone_camerazoom.currentIndex() == 5:
                                z.camzoom = 3
                            elif tab.Zone_camerazoom.currentIndex() == 6:
                                z.camzoom = 16
                                QtGui.QMessageBox.warning(None, 'Error', 'Zoom mode 4 can be glitchy with these settings.')
                else:
                    if tab.Zone_ytrack.isChecked():
                        if tab.Zone_camerabias.isChecked():
                            #No Xtrack, YTrack, Bias
                            if tab.Zone_camerazoom.currentIndex() == 0:
                                z.cammode = 1
                                z.camzoom = 8
                                QtGui.QMessageBox.warning(None, 'Error', 'Zoom level -2 does not support bias modes.')
                            elif tab.Zone_camerazoom.currentIndex() == 1:
                                z.cammode = 4
                                z.camzoom = 9
                                QtGui.QMessageBox.warning(None, 'Error', 'Zoom level -1 does not support bias modes.')
                            elif tab.Zone_camerazoom.currentIndex() == 2:
                                z.cammode = 1
                                z.camzoom = 1
                            elif tab.Zone_camerazoom.currentIndex() == 3:
                                z.cammode = 1
                                z.camzoom = 10
                            elif tab.Zone_camerazoom.currentIndex() == 4:
                                z.cammode = 1
                                z.camzoom = 4
                            elif tab.Zone_camerazoom.currentIndex() == 5:
                                z.cammode = 1
                                z.camzoom = 3
                            elif tab.Zone_camerazoom.currentIndex() == 6:
                                z.cammode = 4
                                z.camzoom = 3
                        else:
                            #No Xtrack, YTrack, No Bias
                            if tab.Zone_camerazoom.currentIndex() == 0:
                                z.cammode = 4
                                z.camzoom = 8
                            elif tab.Zone_camerazoom.currentIndex() == 1:
                                z.cammode = 4
                                z.camzoom = 9
                            elif tab.Zone_camerazoom.currentIndex() == 2:
                                z.cammode = 1
                                z.camzoom = 0
                            elif tab.Zone_camerazoom.currentIndex() == 3:
                                z.cammode = 1
                                z.camzoom = 7
                            elif tab.Zone_camerazoom.currentIndex() == 4:
                                z.cammode = 1
                                z.camzoom = 11
                            elif tab.Zone_camerazoom.currentIndex() == 5:
                                z.cammode = 4
                                z.camzoom = 2
                            elif tab.Zone_camerazoom.currentIndex() == 6:
                                z.cammode = 4
                                z.camzoom = 7
                    else:
                        if tab.Zone_camerabias.isChecked():
                            #No Xtrack, No YTrack, Bias (glitchy)
                            if tab.Zone_camerazoom.currentIndex() == 0:
                                z.cammode = 9
                                z.camzoom = 8
                                QtGui.QMessageBox.warning(None, 'Error', 'No tracking mode is consistently glitchy and does not support bias.')
                            elif tab.Zone_camerazoom.currentIndex() == 1:
                                z.cammode = 9
                                z.camzoom = 20
                                QtGui.QMessageBox.warning(None, 'Error', 'No tracking mode is consistently glitchy and does not support bias.')
                            elif tab.Zone_camerazoom.currentIndex() == 2:
                                z.cammode = 9
                                z.camzoom = 13
                                QtGui.QMessageBox.warning(None, 'Error', 'No tracking mode is consistently glitchy and does not support bias.')
                            elif tab.Zone_camerazoom.currentIndex() == 3:
                                z.cammode = 9
                                z.camzoom = 12
                                QtGui.QMessageBox.warning(None, 'Error', 'No tracking mode is consistently glitchy and does not support bias.')
                            elif tab.Zone_camerazoom.currentIndex() == 4:
                                z.cammode = 9
                                z.camzoom = 14
                                QtGui.QMessageBox.warning(None, 'Error', 'No tracking mode is consistently glitchy and does not support bias.')
                            elif tab.Zone_camerazoom.currentIndex() == 5:
                                z.cammode = 9
                                z.camzoom = 15
                                QtGui.QMessageBox.warning(None, 'Error', 'No tracking mode is consistently glitchy and does not support bias.')
                            elif tab.Zone_camerazoom.currentIndex() == 6:
                                z.cammode = 9
                                z.camzoom = 16
                                QtGui.QMessageBox.warning(None, 'Error', 'No tracking mode is consistently glitchy and does not support bias.')
                        else:
                            #No Xtrack, No YTrack, No Bias (glitchy)
                            if tab.Zone_camerazoom.currentIndex() == 0:
                                z.cammode = 9
                                z.camzoom = 8
                                QtGui.QMessageBox.warning(None, 'Error', 'No tracking mode is consistently glitchy.')
                            elif tab.Zone_camerazoom.currentIndex() == 1:
                                z.cammode = 9
                                z.camzoom = 19
                                QtGui.QMessageBox.warning(None, 'Error', 'No tracking mode is consistently glitchy.')
                            elif tab.Zone_camerazoom.currentIndex() == 2:
                                z.cammode = 9
                                z.camzoom = 13
                                QtGui.QMessageBox.warning(None, 'Error', 'No tracking mode is consistently glitchy.')
                            elif tab.Zone_camerazoom.currentIndex() == 3:
                                z.cammode = 9
                                z.camzoom = 12
                                QtGui.QMessageBox.warning(None, 'Error', 'No tracking mode is consistently glitchy.')
                            elif tab.Zone_camerazoom.currentIndex() == 4:
                                z.cammode = 9
                                z.camzoom = 14
                                QtGui.QMessageBox.warning(None, 'Error', 'No tracking mode is consistently glitchy.')
                            elif tab.Zone_camerazoom.currentIndex() == 5:
                                z.cammode = 9
                                z.camzoom = 15
                                QtGui.QMessageBox.warning(None, 'Error', 'No tracking mode is consistently glitchy.')
                            elif tab.Zone_camerazoom.currentIndex() == 6:
                                z.cammode = 9
                                z.camzoom = 16
                                QtGui.QMessageBox.warning(None, 'Error', 'No tracking mode is consistently glitchy.')
                
                                
                if tab.Zone_vnormal.isChecked():
                    z.visibility = 0
                    z.visibility = z.visibility + tab.Zone_visibility.currentIndex()
                if tab.Zone_vspotlight.isChecked():
                    z.visibility = 16
                    z.visibility = z.visibility + tab.Zone_visibility.currentIndex()
                if tab.Zone_vfulldark.isChecked():
                    z.visibility = 32
                    z.visibility = z.visibility + tab.Zone_visibility.currentIndex()
                   

                z.yupperbound = tab.Zone_yboundup.value()
                z.ylowerbound = tab.Zone_ybounddown.value()
                
                z.music = tab.Zone_music.currentIndex()
                z.sfxmod = (tab.Zone_sfx.currentIndex() * 16)
                if tab.Zone_boss.isChecked():
                    z.sfxmod = z.sfxmod + 1

                i = i + 1
        self.levelOverview.update()

    #Handles setting the backgrounds
    @QtCore.pyqtSlot()
    def HandleBG(self):
        """Pops up the Background settings Dialog"""        
        dlg = BGDialog()
        if dlg.exec_() == QtGui.QDialog.Accepted:
            SetDirty()
            i = 0
            for z in Level.zones:
                tab = dlg.BGTabs[i]
                
                z.XpositionA = tab.xposA.value()
                z.YpositionA = -tab.yposA.value()
                z.XscrollA = tab.xscrollA.currentIndex()
                z.YscrollA = tab.yscrollA.currentIndex()
                
                z.ZoomA = tab.zoomA.currentIndex()

                id = tab.background_nameA.itemData(tab.background_nameA.currentIndex()).toPyObject()
                if tab.toscreenA.isChecked():
                    # mode 5
                    z.bg1A = id
                    z.bg2A = id
                    z.bg3A = id
                else:
                    # mode 2
                    z.bg1A = id
                    z.bg2A = 0x000A
                    z.bg3A = 0x000A


                z.XpositionB = tab.xposB.value()
                z.YpositionB = -tab.yposB.value()
                z.XscrollB = tab.xscrollB.currentIndex()
                z.YscrollB = tab.yscrollB.currentIndex()
                
                z.ZoomB = tab.zoomB.currentIndex()

                id = tab.background_nameB.itemData(tab.background_nameB.currentIndex()).toPyObject()
                if tab.toscreenB.isChecked():
                    # mode 5
                    z.bg1B = id
                    z.bg2B = id
                    z.bg3B = id
                else:
                    # mode 2
                    z.bg1B = id
                    z.bg2B = 0x000A
                    z.bg3B = 0x000A

                i = i + 1

    @QtCore.pyqtSlot()
    def HandleScreenshot(self):
        """Takes a screenshot of the entire level and saves it"""
        
        dlg = ScreenCapChoiceDialog()
        if dlg.exec_() == QtGui.QDialog.Accepted:
            fn = QtGui.QFileDialog.getSaveFileName(mainWindow, 'Choose a new filename', '/untitled.png', 'Portable Network Graphics (*.png)')
            if fn == '': return
            fn = unicode(fn)

            if dlg.zoneCombo.currentIndex() == 0:
                ScreenshotImage = QtGui.QImage(mainWindow.view.width(), mainWindow.view.height(), QtGui.QImage.Format_ARGB32)
                ScreenshotImage.fill(QtCore.Qt.transparent)
                
                RenderPainter = QtGui.QPainter(ScreenshotImage)
                mainWindow.view.render(RenderPainter, QtCore.QRectF(0,0,mainWindow.view.width(),  mainWindow.view.height()), QtCore.QRect(QtCore.QPoint(0,0), QtCore.QSize(mainWindow.view.width(),  mainWindow.view.height())))
                RenderPainter.end()
            elif dlg.zoneCombo.currentIndex() == 1:
                maxX = maxY = 0
                minX = minY = 0x0ddba11
                for z in Level.zones:
                    if maxX < ((z.objx*1.5) + (z.width*1.5)):
                        maxX = ((z.objx*1.5) + (z.width*1.5))
                    if maxY < ((z.objy*1.5) + (z.height*1.5)):
                        maxY = ((z.objy*1.5) + (z.height*1.5))
                    if minX > z.objx*1.5:
                        minX = z.objx*1.5
                    if minY > z.objy*1.5:
                        minY = z.objy*1.5
                maxX = (1024*24 if 1024*24 < maxX+40 else maxX+40)
                maxY = (512*24 if 512*24 < maxY+40 else maxY+40)
                minX = (0 if 40 > minX else minX-40)
                minY = (40 if 40 > minY else minY-40)
                
                ScreenshotImage = QtGui.QImage(int(maxX - minX), int(maxY - minY), QtGui.QImage.Format_ARGB32)
                ScreenshotImage.fill(QtCore.Qt.transparent)
                
                RenderPainter = QtGui.QPainter(ScreenshotImage)
                mainWindow.scene.render(RenderPainter, QtCore.QRectF(0,0,int(maxX - minX) ,int(maxY - minY)), QtCore.QRectF(int(minX), int(minY), int(maxX - minX), int(maxY - minY)))
                RenderPainter.end()
                
                    
            else:
                i = dlg.zoneCombo.currentIndex() - 2
                ScreenshotImage = QtGui.QImage(Level.zones[i].width*1.5, Level.zones[i].height*1.5, QtGui.QImage.Format_ARGB32)
                ScreenshotImage.fill(QtCore.Qt.transparent)
                
                RenderPainter = QtGui.QPainter(ScreenshotImage)
                mainWindow.scene.render(RenderPainter, QtCore.QRectF(0,0,Level.zones[i].width*1.5, Level.zones[i].height*1.5), QtCore.QRectF(int(Level.zones[i].objx)*1.5, int(Level.zones[i].objy)*1.5, Level.zones[i].width*1.5, Level.zones[i].height*1.5))
                RenderPainter.end()
               
            ScreenshotImage.save(fn, 'PNG', 50)
            
            

def main():
    """Main startup function for Reggie"""
    
    global app, mainWindow, settings
    
    # create an application
    app = QtGui.QApplication(sys.argv)
    
    # go to the script path
    path = module_path()
    if path != None:
        os.chdir(module_path())
    
    # check if required files are missing
    if FilesAreMissing():
        sys.exit(1)
    
    # load required stuff
    LoadLevelNames()
    LoadTilesetNames()
    LoadObjDescriptions()
    LoadBgANames()
    LoadBgBNames()
    LoadSpriteData()
    LoadEntranceNames()
    LoadNumberFont()
    LoadOverrides()
    sprites.Setup()
    
    # load the settings
    settings = QtCore.QSettings('Reggie', 'Reggie Level Editor')
    
    global EnableAlpha, GridEnabled
    global ObjectsNonFrozen, SpritesNonFrozen, EntrancesNonFrozen, LocationsNonFrozen
    
    GridEnabled = (settings.value('GridEnabled', 'false').toPyObject() == 'true')
    ObjectsNonFrozen = (settings.value('FreezeObjects', 'false').toPyObject() == 'false')
    SpritesNonFrozen = (settings.value('FreezeSprites', 'false').toPyObject() == 'false')
    EntrancesNonFrozen = (settings.value('FreezeEntrances', 'false').toPyObject() == 'false')
    LocationsNonFrozen = (settings.value('FreezeLocations', 'false').toPyObject() == 'false')
    
    if settings.contains('GamePath'):
        SetGamePath(settings.value('GamePath').toPyObject())
    
    # choose a folder for the game
    # let the user pick a folder without restarting the editor if they fail
    while not isValidGamePath():
        path = QtGui.QFileDialog.getExistingDirectory(None, 'Choose the game\'s Stage folder')
        if path == '':
            sys.exit(0)
        
        SetGamePath(path)
        if not isValidGamePath():
            QtGui.QMessageBox.information(None, 'Error',  'This folder doesn\'t seem to have the required files. In order to use Reggie, you need the Stage folder from the game, including the Texture folder and the level files contained within it.')
        else:
            settings.setValue('GamePath', gamePath)
            break
    
    # check to see if we have anything saved
    autofile = unicode(settings.value('AutoSaveFilePath', 'none').toPyObject())
    if autofile != 'none':
        autofiledata = unicode(settings.value('AutoSaveFileData', 'x').toPyObject())
        if autofiledata != 'x':
            result = AutoSavedInfoDialog(autofile).exec_()
            if result == QtGui.QDialog.Accepted:
                global RestoredFromAutoSave, AutoSavePath, AutoSaveData
                RestoredFromAutoSave = True
                AutoSavePath = autofile
                AutoSaveData = autofiledata
            else:
                settings.setValue('AutoSaveFilePath', 'none')
                settings.setValue('AutoSaveFileData', 'x')

    if sys.argv[1:]:
        for argfile in sys.argv[1:]:
            if os.path.exists(argfile):
                mainWindow = ReggieWindow()
                mainWindow.LoadLevel(argfile, True, 1)
                mainWindow.show()
    else:
        # create and show the main window
        mainWindow = ReggieWindow()
        mainWindow.show()
    sys.exit(app.exec_())

EnableAlpha = True
if '-alpha' in sys.argv:
    EnableAlpha = False
    
    # nsmblib doesn't support -alpha so if it's enabled
    # then don't use it
    HaveNSMBLib = False

# check version
if HaveNSMBLib:
    version = nsmblib.getVersion()
    if version < 4:
        HaveNSMBLib = False

if '-nolib' in sys.argv:
    HaveNSMBLib = False

if __name__ == '__main__':
    if HavePsyco:
        psyco.full()
    int(main())
