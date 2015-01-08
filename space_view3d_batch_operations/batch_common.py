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
from {0}dairin0d.utils_userinput import KeyMapUtils
from {0}dairin0d.utils_ui import NestedLayout
from {0}dairin0d.bpy_inspect import prop, BlRna
from {0}dairin0d.utils_addon import AddonManager
""".format(dairin0d_location))

addon = AddonManager()

# adapted from the Copy Attributes Menu addon
def copyattrs(src, dst, filter=""):
    for attr in dir(src):
        if attr.find(filter) > -1:
            try:
                setattr(dst, attr, getattr(src, attr))
            except:
                pass

def attrs_to_dict(obj):
    d = {}
    for name in dir(obj):
        if not name.startswith("_"):
            d[name] = getattr(obj, name)
    return d

def dict_to_attrs(obj, d):
    for name, value in d.items():
        if not name.startswith("_"):
            try:
                setattr(obj, name, value)
            except:
                pass

class Pick_Base:
    def invoke(self, context, event):
        context.window.cursor_modal_set('EYEDROPPER')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        cancel = (event.type in {'ESC', 'RIGHTMOUSE'})
        confirm = (event.type == 'LEFTMOUSE') and (event.value == 'PRESS')
        
        mouse = Vector((event.mouse_x, event.mouse_y))
        
        raycast_result = None
        sv = SmartView3D((mouse.x, mouse.y, 0))
        if sv:
            #raycast_result = sv.ray_cast(mouse, coords='WINDOW')
            select_result = sv.select(mouse, coords='WINDOW')
            raycast_result = (bool(select_result[0]), select_result[0])
        
        obj = None
        if raycast_result and raycast_result[0]:
            obj = raycast_result[1]
        
        txt = (self.obj_to_info(obj) if obj else "")
        context.area.header_text_set(txt)
        
        if cancel or confirm:
            if confirm:
                self.on_confirm(context, obj)
            context.area.header_text_set()
            context.window.cursor_modal_restore()
            return ({'FINISHED'} if confirm else {'CANCELLED'})
        return {'RUNNING_MODAL'}

class TemplateLeft:
    bl_region_type = 'TOOLS'
    @classmethod
    def poll(cls, context):
        return addon.preferences.use_panel_left

class TemplateRight:
    bl_region_type = 'UI'
    @classmethod
    def poll(cls, context):
        return addon.preferences.use_panel_right

def LeftRightPanel(panel_class):
    @addon.Panel
    class LeftPanel(panel_class, TemplateLeft):
        bl_idname = panel_class.__name__ + "_left"
    
    @addon.Panel
    class RightPanel(panel_class, TemplateRight):
        bl_idname = panel_class.__name__ + "_right"
    
    return panel_class

# ============================== AUTOREFRESH =============================== #
#============================================================================#
@addon.Operator(idname="object.batch_refresh")
def batch_refresh(self, context):
    """Force batch UI refresh"""
    addon.external.modifiers.refresh(context, True)

@addon.PropertyGroup
class AutorefreshPG:
    autorefresh = True | prop("Enable auto-refresh")
    refresh_interval = 0.5 | prop("Auto-refresh Interval", name="Refresh Interval", min=0.0)

@LeftRightPanel
class VIEW3D_PT_batch_autorefresh:
    bl_category = "Batch"
    bl_context = "objectmode"
    bl_label = "Batch Refresh"
    bl_space_type = 'VIEW_3D'
    
    def draw(self, context):
        layout = NestedLayout(self.layout)
        batch_autorefresh = addon.preferences.autorefresh
        
        with layout.row():
            with layout.row(True):
                layout.prop(batch_autorefresh, "autorefresh", text="", icon='PREVIEW_RANGE', toggle=True)
                layout.row(True)(active=batch_autorefresh.autorefresh).prop(batch_autorefresh, "refresh_interval", text="Interval", icon='PREVIEW_RANGE')
            layout.operator("object.batch_refresh", text="", icon='FILE_REFRESH')

addon.Preferences.autorefresh = AutorefreshPG | prop()
#============================================================================#

