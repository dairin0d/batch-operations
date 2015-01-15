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
    "version": (0, 3, 0),
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
    imp.reload(batch_materials)
    imp.reload(batch_groups)

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
from {0}dairin0d.utils_ui import NestedLayout, find_ui_area, ui_context_under_coord
from {0}dairin0d.bpy_inspect import prop, BlRna
from {0}dairin0d.utils_addon import AddonManager
""".format(dairin0d_location))

from .batch_common import copyattrs, attrs_to_dict, dict_to_attrs, Pick_Base, LeftRightPanel, change_monitor
from . import batch_modifiers
from . import batch_materials
from . import batch_groups

addon = AddonManager()

"""
// Temporary note:
if item is property group instance and item["pi"] = 3.14,
in UI it should be displayed like this: layout.prop(item, '["pi"]')

TODO: make it possible to use separately different change-detecting mechanisms

Make sure copy/pasting doesn't crash Blender after Undo (seems like it doesn't crash, but pasted references to objects are invalid)
(TODO: clear clipbuffers on undo detection)
Make a general mechanism of serializing/deserializing links to ID blocks? (also useful for cut/copy/paste addon)

// add to addon "runtime" settings to hold python objects? (just for the convenience of accessing them from one place)


investigate if it's possible to make a shortcut to jump to certain tab in tool shelf


for copy/pasting (and other operations that work on active object),
    take into account SpaceProperties.use_pin_id and SpaceProperties.pin_id?


syncronization of batch options (show different icon when synchronized)

synchronized copy/paste? (e.g. copy/paste modifers and materials simultaneously)

also: layers (see also: Layer Management addon by Bastien Montagne)

moth3r suggested copy/pasting objects (in particular, so that pasting an object won't create duplicate materials)
copy/paste inside group? (in the selected batch groups)

* single-click parenting: show a list of top-level objects? (i.e. without parents)
    * Actually there is a nice addon http://blenderaddonlist.blogspot.com/2014/06/addon-parent-to-empty.html
    * That could be shift+click or click operation for all selected objects depending on button.
* material: apply() -> all objects in selection should become that material (or: shift+click?) -- this is a priority
* group: apply() (same behaviour)

Projected feature-set (vision):
* [REMOVED] Refresh (Hopefully, we won't need refresh-by-time, since now we have refresh on actual change)
    * [REMOVED] Auto-refresh on/off
    * [REMOVED] Auto-refresh interval
    * [REMOVED] Force refresh (manual refresh)
* Operators
    * Batch apply operator (search field)
    * operator's draw (if not defined, use automatic draw)
    * For: selection, visible, layer, scene, .blend
* Object/Transform
    * Batch rename with some sort of name pattern detection
    * Transform summary + ability to modify if possible
    * Coordinate systems?
    * Non-instant evaluation? Or, if determining the moment of change is possible, use instant evaluation?
* Modifiers
    * Control row:
        * Add
        * Pick
        * Copy
        * Paste
        * Copy/Paste mode: SET, OR (union), AND (intersection)
        * For: selection, visible, layer, scene, .blend
        * Option to convert curves to meshes / make meshes single-user before applying the modifiers?
    * Table:
        * Checkbox for specifying which items should be affected by "All"-level operations
        * Show expanded? (+Shift: globally/completely?)
        * Use in render (+Shift: globally/completely?)
        * Use in viewport (+Shift: globally/completely?)
        * Use in edit mode (+Shift: globally/completely?)
        * Use in cage (+Shift: globally/completely?)
        * Use in spline (use_apply_on_spline?) (+Shift: globally/completely?)
        * Ensure (this seems like a redundant feature, as the same effect can be done by copy-pasting specific items from the list)
        * Apply (apply_as='DATA' and/or 'SHAPE'?) (+Shift: globally/completely?)
            * This is the long "name (number of uses)" property/button
        * Remove (+Shift: globally/completely?)
* Materials
    * Control row:
        * Add (search? <Create new>? List of all materials not used in the selection?)
        * Pick
        * Copy
        * Paste
        * Copy/Paste mode: SET, OR (union), AND (intersection)
        * For: selection, visible, layer, scene, .blend
        * Option to prune all unused materials? (+option to respect/ignore use_fake_user?)
        * Option to rename listed materials by some pattern? (e.g. common name + id, or the corresponding data/object name)
        * Option: always modify only object, or affect object.data as well? (if modify-only-object, then the corresponding slot will be set to link='OBJECT' on modification)
        * Option: when removing materials, set slot.material, or remove slot completely? (probably not very useful)
        * Option: when adding material to objects, use unoccupied slots first, before creating new ones?
    * Table:
        * Checkbox for specifying which items should be affected by "All"-level operations
        * use_fake_user? ("Save this datablock even if it has no users") (+Shift: globally/completely?)
        * Replace with other material? (+Shift: globally/completely?)
        * Ensure? (this seems like a redundant feature, as the same effect can be done by copy-pasting specific items from the list)
        * make single-user copies?
        * Rename? (by double-clicking? or a text field in the table?)
        * ... ? This is the long "name (number of uses)" property/button
        * Remove (+Shift: globally/completely? +Sift+Ctrl: even those with use_fake_user?)
* Object Groups
    * Control row:
        * Add (search? <Create new>? List of all groups not used in the selection?)
        * Pick
        * Copy
        * Paste
        * Copy/Paste mode: SET, OR (union), AND (intersection)
        * For: selection, visible, layer, scene, .blend
        * Option to prune all unused groups? (+option to respect/ignore use_fake_user?)
        * Option to rename listed groups by some pattern? (e.g. common name + id, or the corresponding data/object name)
    * Table:
        * Checkbox for specifying which items should be affected by "All"-level operations
        * use_fake_user? ("Save this datablock even if it has no users") (+Shift: globally/completely?)
        * Replace with other group? (+Shift: globally/completely?)
        * Merge with other group? (+Shift: globally/completely?)
        * Ensure? (this seems like a redundant feature, as the same effect can be done by copy-pasting specific items from the list)
        * Rename? (by double-clicking? or a text field in the table?)
        * ... ? This is the long "name (number of uses)" property/button
        * Remove (+Shift: globally/completely? +Sift+Ctrl: even those with use_fake_user?)
        * Dupli visibility Layers?
        * Dupli Offset?
* Constraints
    ...
* Vertex Groups
    ...
"""

#============================================================================#

@addon.Operator(idname="object.batch_properties_copy", space_type='PROPERTIES')
def Batch_Properties_Copy(self, context):
    properties_context = context.space_data.context
    if properties_context == 'MODIFIER':
        bpy.ops.object.batch_modifier_copy()
    elif properties_context == 'MATERIAL':
        bpy.ops.object.batch_material_copy()

@addon.Operator(idname="object.batch_properties_paste", space_type='PROPERTIES')
def Batch_Properties_Copy(self, context):
    properties_context = context.space_data.context
    if properties_context == 'MODIFIER':
        bpy.ops.object.batch_modifier_paste()
    elif properties_context == 'MATERIAL':
        bpy.ops.object.batch_material_paste()

@addon.Preferences.Include
class ThisAddonPreferences:
    refresh_interval = 0.5 | prop("Auto-refresh interval", name="Refresh interval", min=0.0)
    use_panel_left = True | prop("Show in T-panel", name="T (left panel)")
    use_panel_right = False | prop("Show in N-panel", name="N (right panel)")
    
    def draw(self, context):
        layout = NestedLayout(self.layout)
        
        with layout.row():
            layout.prop(self, "refresh_interval")
            layout.prop(self, "use_panel_left")
            layout.prop(self, "use_panel_right")

def something_was_drawn():
    was_drawn = False
    was_drawn |= addon.external.modifiers.was_drawn
    was_drawn |= addon.external.materials.was_drawn
    return was_drawn

def on_change():
    addon.external.modifiers.was_drawn = False
    addon.external.modifiers.needs_refresh = True
    addon.external.modifiers.refresh(bpy.context)
    
    addon.external.materials.was_drawn = False
    addon.external.materials.needs_refresh = True
    addon.external.materials.refresh(bpy.context)

@addon.Operator(idname="wm.batch_changes_monitor")
class ChangeMonitoringOperator:
    is_running = False
    script_reload_kmis = []
    last_reset_time = 0.0
    
    def invoke(self, context, event):
        ChangeMonitoringOperator.is_running = True
        ChangeMonitoringOperator.script_reload_kmis = list(KeyMapUtils.search('script.reload'))
        
        wm = context.window_manager
        wm.modal_handler_add(self)
        
        # 'RUNNING_MODAL' MUST be present if modal_handler_add is used!
        return {'PASS_THROUGH', 'RUNNING_MODAL'}
    
    def cancel(self, context):
        ChangeMonitoringOperator.is_running = False
    
    def modal(self, context, event):
        # This doesn't seem to ever happen, but just in case:
        if addon.status != 'REGISTERED':
            self.cancel(context)
            return {'PASS_THROUGH', 'CANCELLED'}
        
        # Scripts cannot be reloaded while modal operators are running
        # Intercept the corresponding event and shut down CursorMonitor
        # (it would be relaunched automatically afterwards)
        for kc, km, kmi in ChangeMonitoringOperator.script_reload_kmis:
            if KeyMapUtils.equal(kmi, event):
                self.cancel(context)
                return {'PASS_THROUGH', 'CANCELLED'}
        
        mouse_context = ui_context_under_coord(event.mouse_x, event.mouse_y)
        if mouse_context and (mouse_context.get("area").type == 'INFO'):
            # let the user at least select info reports while the mouse is over the info area
            return {'PASS_THROUGH'}
        
        # When possible, try to use existing info area, since otherwise
        # temporary switching of area type will cause Blender to constantly update
        info_context = find_ui_area('INFO')
        
        context_override = info_context or mouse_context
        
        if (event.type == 'MOUSEMOVE'):
            if mouse_context:
                x, y = event.mouse_x, event.mouse_y
                r = mouse_context["region"]
                dx = min((x - r.x), (r.x+r.width - x))
                dy = min((y - r.y), (r.y+r.height - y))
                if time.clock() > ChangeMonitoringOperator.last_reset_time + 0.1:
                #if something_was_drawn():
                    if (dx > 3) and (dy > 3): # not too close to region's border
                        # The hope is that, if we call update only on mousemove events,
                        # crashes would happen with lesser pribability
                        if context_override and context_override.get("area"):
                            change_monitor.update(**context_override)
                            if change_monitor.something_changed:
                                on_change()
                            #elif time.clock() > ChangeMonitoringOperator.last_reset_time + 1:
                            #    on_change()
        elif 'MOUSEMOVE' in event.type:
            pass
        elif 'TIMER' in event.type:
            pass
        elif event.type == 'NONE':
            pass
        else:
            ChangeMonitoringOperator.last_reset_time = time.clock()
        
        return {'PASS_THROUGH'}

# We need to invoke batch_changes_monitor from somewhere other than
# keymap event, since keymap event can lock the batch_changes_monitor
# operator to the Preferences window. Scene update, on the other hand,
# is always in the main window.
# WARNING: if addon is saved as enabled in user preferences,
# for some reason scene_update_post/scene_update_pre callbacks
# won't be working until scripts are reloaded.
# BUT: if we put bpy.app.handlers.persistent decorator, it will work.
@bpy.app.handlers.persistent
def scene_update_post(scene):
    if not ChangeMonitoringOperator.is_running:
        ChangeMonitoringOperator.is_running = True
        bpy.ops.wm.batch_changes_monitor('INVOKE_DEFAULT')

def register():
    # I couldn't find a way to avoid the unpredictable crashes,
    # and some actions (like changing a material in material slot)
    # cannot be detected through the info log anyway.
    #addon.handler_append("scene_update_post", scene_update_post)
    
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
    
    # don't remove this, or on next addon enable the monitor will consider itself already running
    ChangeMonitoringOperator.is_running = False
