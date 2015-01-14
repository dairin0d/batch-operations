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
from {0}dairin0d.utils_blender import ChangeMonitor
from {0}dairin0d.utils_addon import AddonManager
""".format(dairin0d_location))

addon = AddonManager()

idnames_separator = "\t"

def round_to_bool(v):
    return (v > 0.5) # bool(round(v))

def has_common_layers(obj, scene):
    return any(l0 and l1 for l0, l1 in zip(obj.layers, scene.layers))

def is_visible(obj, scene):
    return (not obj.hide) and has_common_layers(obj, scene)

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

def LeftRightPanel(cls=None, **kwargs):
    def AddPanels(cls, kwargs):
        doc = cls.__doc__
        name = kwargs.get("bl_idname") or kwargs.get("idname") or cls.__name__
        
        # expected either class or function
        if not isinstance(cls, type):
            cls = type(name, (), dict(__doc__=doc, draw=cls))
        
        poll = getattr(cls, "poll", None)
        if poll:
            poll_left = classmethod(lambda cls, context: addon.preferences.use_panel_left and poll(cls, context))
            poll_right = classmethod(lambda cls, context: addon.preferences.use_panel_right and poll(cls, context))
        else:
            poll_left = classmethod(lambda cls, context: addon.preferences.use_panel_left)
            poll_right = classmethod(lambda cls, context: addon.preferences.use_panel_right)
        
        @addon.Panel(**kwargs)
        class LeftPanel(cls):
            bl_idname = name + "_left"
            bl_region_type = 'TOOLS'
            poll = poll_left
        
        @addon.Panel(**kwargs)
        class RightPanel(cls):
            bl_idname = name + "_right"
            bl_region_type = 'UI'
            poll = poll_right
        
        return cls
    
    if cls: return AddPanels(cls, kwargs)
    return (lambda cls: AddPanels(cls, kwargs))

change_monitor = ChangeMonitor(update=False)
