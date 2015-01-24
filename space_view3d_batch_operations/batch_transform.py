#  ***** BEGIN GPL LICENSE BLOCK *****
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#  ***** END GPL LICENSE BLOCK *****

#============================================================================#

import bpy

import time
import json

from mathutils import Vector

try:
    import dairin0d
    dairin0d_location = ""
except ImportError:
    dairin0d_location = "."

exec("""
from {0}dairin0d.utils_view3d import SmartView3D
from {0}dairin0d.utils_blender import Selection
from {0}dairin0d.utils_userinput import KeyMapUtils
from {0}dairin0d.utils_ui import NestedLayout, tag_redraw
from {0}dairin0d.bpy_inspect import prop, BlRna, BlEnums, bpy_struct
from {0}dairin0d.utils_accumulation import Aggregator, aggregated
from {0}dairin0d.utils_addon import AddonManager
""".format(dairin0d_location))

from .batch_common import (
    copyattrs, attrs_to_dict, dict_to_attrs, PatternRenamer,
    Pick_Base, LeftRightPanel, make_category,
    round_to_bool, is_visible, has_common_layers, idnames_separator
)

addon = AddonManager()

"""
Batch Transform:
* orientations / coordinate systems (is it possible to make them independent for each View3D?)
** base (shown by Blender by default)
** global
** local / parent
** object / self ? (useful for transformations relative to current matrix)
** active
** individual (same as object/self coordinate system?)
** gimbal?
** surface?
** normal?
** view
** custom
* actually, users might want to choose orientation, scale and origin independently
** in addition to options listed for coordinate systems, origins may include cursor, bookmark and some aggregate value of selection's positions
* coordinate systems are combinations of origin, orientation and scale. Make it possible to make custom combinations for quick access?
* (batch) "dimensions" property for all modes that can have selected elements
* (batch) set layers // no, this belongs to Batch Object
* (batch) apply rotation/scale/etc.
* (batch) change origin of geometry
* (batch) add/remove drivers/keyframes?
* batch editing modes (how the change is applied to multiple objects):
** set same value
** add (offset)
** multiply (proportional)
* vector editing modes / "uniformity" (when changing one component, how the others change):
** no change (independent)
** set same value (copy)
** add (offset/relative) (in Modo it's called "relative")
** multiply (proportional)
* Extra operations:
** Lock axis? (the corresponding axis won't participate in uniformity)
** Vector swizzle?
** Copy/Paste (option: using units or the raw values)

* "local grid" rendering (around object / cursor / etc.)

From http://wiki.blender.org/index.php/Dev:Doc/Quick_Hacks
- Use of 3d manipulator to move and scale Texture Space?

fusion 360 has a lot of cool features (moth3r says it's the most user-friendly CAD)

CAD-like guides?

* Spatial queries? ("select all objects wich satisfy the following conditions")
* Copy/Paste transform or its components? (respecting axis locks)
* Pick transform? (respecting axis locks)
* auto-refresh? (or maybe incremental refresh?)

* Stateless/incremental Selection walker?
* In addition to aggregating origins, also provide options for geometry aggregation?
  (e.g. min/max/range in certain coord system)
  maybe it's easier to just convert the objects to mesh(es), apply transforms,
  and then use Blender-calculated bbox?

* ability to set accumulation mode for each property independently?
* coordsystem / aggregation / etc. should be independent for each View3D?
  (convenient for cases when one wants to see same property in different coordsystems,
  or even use different views for different coordsystems)
  Theoretically it's possible to implement (UI elements keep their pointers
  while a file is opened, and their order is preserved even after reload
  BUT: for each different coordsystem, we'll need to use the same amount
  of aggregators and update them simultaneously.


Queries/statistics (within a single coord system):
* Object/element level
** count, same (on general level)
** value of active object/element
** min, max
** range, center
** mean, stddev
** median, mode (BUT: these consume space)
* Sub-element level
** min, max
** range, center
** mean, stddev
** median, mode (BUT: these consume space)

* Option to treat isolated islands as separate objects?

moth3r suggests making it an option for where to "store" the coordinates system:
* view3d
* scene
* screen
* file

See Modo's Absolute Scaling
https://www.youtube.com/watch?v=79BAHXLX9JQ
http://community.thefoundry.co.uk/discussion/topic.aspx?f=33&t=34229


In general, for each parameter, the user might want to see several aggregate characteristics simultaneously
Use table: each row is a separate attribute, and each column is a certain characteristic

Example:

// [*] is "fold this parameter"
// [+] is "add another statistic"
// [&] is "lock this axis"

[active][ min  ][ max  ][range ][center][ mean ][stddev][median][ mode ][+]

[*] Location
(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)[&]
(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)[&]
(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)[&]

[*] Rotation
(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)[&]
(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)[&]
(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)[&]

[*] Scale
(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)[&]
(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)[&]
(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)[&]

[*] Dimensions
(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)[&]
(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)[&]
(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)(0.0000)[&]





_numerical_queries = frozenset([
    'count', 'same', 'min', 'max', 'range', 'center',
    'sum', 'sum_log', 'sum_rec', 'product',
    'mean', 'geometric_mean', 'harmonic_mean', 'variance', 'stddev',
    'sorted', 'median', 'freq_map', 'freq_max', 'modes',
])

def Accumulation(default='NONE'):
    return default | prop("Accumulation type", items=[
        ('NONE', "Active Only", "", 'ROTACTIVE'),
        ('AVERAGE', "Average", "", 'ROTATECENTER'),
        ('MEDIAN', "Median", "", 'SORTSIZE'),
        ('MODE', "Mode", "", 'GROUP_VERTEX'),
        ('STDDEV', "Deviation", "", 'SMOOTHCURVE'),
        ('RANGE', "Range", "", 'STICKY_UVS_VERT'),
        ('CENTER', "Center", "", 'ROTATE'),
        ('MIN', "Min", "", 'MOVE_DOWN_VEC'),
        ('MAX', "Max", "", 'MOVE_UP_VEC'),
    ], on_item_invoke=accumulation_on_item_invoke)

def Uniformity(default='INDEPENDENT'):
    return default | prop("Uniformity", items=[
        ('INDEPENDENT', "Independent", "", 'UNLINKED'),
        ('SET', "Set", "", 'LINKED'),
        ('ADD', "Add", "", 'ZOOMIN'), # PLUS
        ('PROPORTIONAL', "Proportional", "", 'PROP_CON'), # X CURVE_PATH
    ])

@addon.PropertyGroup
class Transformed_PropertyProxies:
    # Currently Blender doesn't support user-defined properties
    # for SpaceView3D -> we have to maintain a separate mapping.
    v3d_key = 0 | prop()
    
    object = Object_Transformed | prop()
    pose = Pose_Transformed | prop()
    mesh = Mesh_Transformed | prop()
    curve = Curve_Transformed | prop()
    bone = Bone_Transformed | prop()
    meta = Meta_Transformed | prop()
    cursor = Cursor_Transformed | prop()

@addon.PropertyGroup
class CoordinateSystemSettings:
    presets_common = [
        ('UCS', "UCS Object", "", 'OBJECT_DATA'),
        ('CUSTOM', "Custom", "", 'SCRIPTWIN'),
        ('VIEW', "View", "", 'CAMERA_DATA'),
        ('WORLD', "World", "", 'WORLD'),
        ('PARENT', "Parent", "", 'GROUP_BONE'),
        ('OBJECT', "Object", "", 'MANIPUL'),
        ('ACTIVE', "Active", "", 'ROTACTIVE'),
        ('INDIVIDUAL', "Individual", "", 'ROTATECOLLECTION'),
    ]
    presets_axes_origin = presets_common + [
        ('SURFACE', "Surface", "", 'SNAP_NORMAL'),
    ]
    presets_axes = presets_axes_origin + [
        ('NORMAL', "Normal", "", 'EDITMODE_HLT'),
        ('GIMBAL', "Gimbal", "", 'NDOF_DOM'),
    ]
    presets_origin = presets_axes_origin + [
        ('AVERAGE', "Average", "", 'ROTATECENTER'),
        ('CENTER', "Center", "", 'ROTATE'),
        ('MIN', "Min", "", 'MOVE_DOWN_VEC'),
        ('MAX', "Max", "", 'MOVE_UP_VEC'),
        ('CURSOR', "Cursor", "", 'CURSOR'),
        ('BOOKMARK', "Boomark", "", 'SOLO_ON'), # follows a bookmark?
    ]
    presets_space = presets_common + [
    ]

def get_transformed(context):
    v3d = context.space_data
    if (not v3d) or (v3d.type != 'VIEW_3D'):
        return
    
    v3d_key = v3d.as_pointer()
    
    transformeds = addon.internal.transformeds
    for transformed in transformeds:
        if transformed.v3d_key == v3d_key:
            return transformed
    
    transformed = transformeds.add()
    transformed.v3d_key = v3d_key
    return transformed

def iter_transformeds(context):
    spaces = set(space.as_pointer()
                 for area in context.screen.areas
                 for space in area.spaces
                 if space.type == 'VIEW_3D')
    
    transformeds = addon.internal.transformeds
    for transformed in transformeds:
        if transformed.v3d_key in spaces:
            yield transformed
"""

#============================================================================#
Category_Name = "Transform"
CATEGORY_NAME = Category_Name.upper()
category_name = Category_Name.lower()
Category_Name_Plural = "Transforms"
CATEGORY_NAME_PLURAL = Category_Name_Plural.upper()
category_name_plural = Category_Name_Plural.lower()
category_icon = 'MANIPUL'

#============================================================================#

@addon.PropertyGroup
class ObjectTransformPG:
    pass

@addon.PropertyGroup
class MeshTransformPG:
    pass

@addon.PropertyGroup
class CurveTransformPG:
    pass

@addon.PropertyGroup
class MetaTransformPG:
    pass

@addon.PropertyGroup
class LatticeTransformPG:
    pass

@addon.PropertyGroup
class PoseTransformPG:
    pass

@addon.PropertyGroup
class BoneTransformPG:
    pass

@addon.PropertyGroup
class GreaseTransformPG:
    pass

@addon.PropertyGroup
class CursorTransformPG:
    pass

# Should probably be stored in each Screen?
@addon.PropertyGroup
class ContextTransformPG:
    # Currently Blender doesn't support user-defined properties
    # for SpaceView3D -> we have to maintain a separate mapping.
    v3d_key = 0 | prop()
    
    object = ObjectTransformPG | prop()
    mesh = MeshTransformPG | prop()
    curve = CurveTransformPG | prop()
    meta = MetaTransformPG | prop()
    lattice = LatticeTransformPG | prop()
    pose = PoseTransformPG | prop()
    bone = BoneTransformPG | prop()
    
    # Since Blender 2.73, grease pencil data is editable too
    grease = GreaseTransformPG | prop()
    
    # Cursor isn't aggregated, but it still might be useful
    # to see/manipulate it in non-global coordsystem
    cursor = CursorTransformPG | prop()

@addon.PropertyGroup
class CategoryPG:
    was_drawn = False | prop()
    next_refresh_time = -1.0 | prop()
    
    needs_refresh = True | prop()
    def tag_refresh(self):
        self.needs_refresh = True
        tag_redraw()
    
    transforms = [ContextTransformPG] | prop()
    
    selection_info = None
    default_select_state = None
    
    def refresh(self, context, needs_refresh=False):
        cls = self.__class__
        options = get_options()
        preferences = addon.preferences
        
        selection_info = Selection().stateless_info
        needs_refresh |= (selection_info != cls.selection_info)
        
        needs_refresh |= self.needs_refresh
        needs_refresh |= options.autorefresh and (time.clock() > self.next_refresh_time)
        if not needs_refresh: return
        self.next_refresh_time = time.clock() + preferences.refresh_interval
        cls.selection_info = selection_info
        
        processing_time = time.clock()
        
        # TODO
        
        processing_time = time.clock() - processing_time
        # Disable autorefresh if it takes too much time
        #if processing_time > 0.05: options.autorefresh = False
        
        self.needs_refresh = False
    
    def draw(self, layout):
        self.was_drawn = True
        self.refresh(bpy.context)
        
        options = get_options()
        
        # TODO: search for current context's SpaceView3D
        #for transform in self.transforms:
        #    transform.draw(layout)

@addon.PropertyGroup
class CategoryOptionsPG:
    autorefresh = True | prop("Auto-refresh")

@addon.Menu(idname="VIEW3D_MT_batch_{}_options".format(category_name_plural), label="Options", description="Options")
def Menu_Options(self, context):
    layout = NestedLayout(self.layout)
    options = get_options()
    layout.prop(options, "autorefresh", text="Auto refresh")

@addon.Operator(idname="object.batch_{}_refresh".format(category_name), options={'INTERNAL', 'REGISTER'}, description=
"Click: Force refresh, Ctrl+Click: Toggle auto-refresh")
def Operator_Refresh(self, context, event):
    category = get_category()
    options = get_options()
    if event.ctrl:
        options.autorefresh = not options.autorefresh
    else:
        category.refresh(context, True)
    return {'FINISHED'}

@LeftRightPanel(idname="VIEW3D_PT_batch_{}".format(category_name_plural), context="objectmode", space_type='VIEW_3D', category="Batch", label="Batch {}".format(Category_Name_Plural))
class Panel_Category:
    def draw_header(self, context):
        layout = NestedLayout(self.layout)
        category = get_category()
        options = get_options()
        #with layout.row(True)(scale_x=0.9):
        #    icon = CategoryOptionsPG.search_in_icons[options.search_in]
        #    layout.prop_menu_enum(options, "search_in", text="", icon=icon)
        #    icon = CategoryOptionsPG.paste_mode_icons[options.paste_mode]
        #    layout.prop_menu_enum(options, "paste_mode", text="", icon=icon)
    
    def draw(self, context):
        layout = NestedLayout(self.layout)
        category = get_category()
        options = get_options()
        
        with layout.row():
            #with layout.row(True):
            #    layout.menu("OBJECT_MT_batch_{}_add".format(category_name), icon='ZOOMIN', text="")
            #    layout.operator("view3d.pick_{}".format(category_name_plural), icon='EYEDROPPER', text="")
            #    layout.operator("object.batch_{}_copy".format(category_name), icon='COPYDOWN', text="")
            #    layout.operator("object.batch_{}_paste".format(category_name), icon='PASTEDOWN', text="")
            
            icon = ('PREVIEW_RANGE' if options.autorefresh else 'FILE_REFRESH')
            layout.operator("object.batch_{}_refresh".format(category_name), icon=icon, text="")
            
            #icon = ('SCRIPTPLUGINS' if options.synchronized else 'SCRIPTWIN')
            icon = 'SCRIPTWIN'
            layout.menu("VIEW3D_MT_batch_{}_options".format(category_name_plural), icon=icon, text="")
        
        category.draw(layout)

setattr(addon.External, category_name_plural, CategoryPG | -prop())
get_category = eval("lambda: addon.external.{}".format(category_name_plural))

setattr(addon.Preferences, category_name_plural, CategoryOptionsPG | prop())
get_options = eval("lambda: addon.preferences.{}".format(category_name_plural))
