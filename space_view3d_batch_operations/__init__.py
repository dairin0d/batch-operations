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

bl_info = {
    "name": "Batch Operations",
    "description": "Batch control of modifiers, etc.",
    "author": "dairin0d, moth3r",
    "version": (0, 1, 2),
    "blender": (2, 7, 0),
    "location": "View3D > Batch category in Tools panel",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "3D View"}
#============================================================================#

if "dairin0d" in locals():
    import imp
    imp.reload(dairin0d)
    imp.reload(batch_common)
    imp.reload(batch_modifiers)

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
from {0}dairin0d.utils_userinput import KeyMapUtils
from {0}dairin0d.utils_ui import NestedLayout
from {0}dairin0d.bpy_inspect import prop, BlRna
from {0}dairin0d.utils_addon import AddonManager
""".format(dairin0d_location))

from .batch_common import copyattrs, attrs_to_dict, dict_to_attrs, Pick_Base
from . import batch_modifiers

addon = AddonManager()

"""
TODO:
Some feedback from twitter:
  "I like the multi-edit feature, would be nice if I the user could checkmark modifiers on the list to be copied and paste additively"
  That could be a nice feature.
Make sure copy/pasting doesn't crash Blender after Undo (seems like it doesn't crash, but pasted references to objects are invalid)
  make a general mechanism of serializing/deserializing links to ID blocks?
Materials (+completely remove immediately)
Batch apply operator (+operator search field)
Constraints

Materials:
Add (only existing? on also new?), Pick, Copy, Paste
Batch set "Link to": Data or Object
use_fake_user on/off?
Replace with other material in selected/.blend
Remove from selected/.blend
Rename materials in selected objects by pattern?
"""

@addon.Operator(idname="object.batch_properties_copy", space_type='PROPERTIES')
def Batch_Properties_Copy(self, context):
    properties_context = context.space_data.context
    if properties_context == 'MODIFIER':
        bpy.ops.object.batch_modifier_copy()
        #Batch_Copy_Modifiers(self, context)
    #print(context.space_data.type)
    #print(context.space_data.context)

@addon.Operator(idname="object.batch_properties_paste", space_type='PROPERTIES')
def Batch_Properties_Copy(self, context):
    properties_context = context.space_data.context
    if properties_context == 'MODIFIER':
        bpy.ops.object.batch_modifier_paste()
        #Batch_Paste_Modifiers(self, context)
    #print(context.space_data.type)
    #print(context.space_data.context)

@addon.Preferences.Include
class ThisAddonPreferences:
    use_panel_left = True | prop("Show in T-panel", name="T (left panel)")
    use_panel_right = False | prop("Show in N-panel", name="N (right panel)")
    
    def draw(self, context):
        layout = NestedLayout(self.layout)
        
        with layout.row():
            layout.label("Show in:")
            layout.prop(self, "use_panel_left")
            layout.prop(self, "use_panel_right")

def register():
    addon.register()
    
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="Window")
        kmi = km.keymap_items.new("object.batch_properties_copy", 'C', 'PRESS', ctrl=True)
        kmi = km.keymap_items.new("object.batch_properties_paste", 'V', 'PRESS', ctrl=True)

def unregister():
    KeyMapUtils.remove("object.batch_properties_copy")
    KeyMapUtils.remove("object.batch_properties_paste")
    
    addon.unregister()
