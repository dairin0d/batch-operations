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

from .batch_common import copyattrs, attrs_to_dict, dict_to_attrs, Pick_Base, LeftRightPanel

addon = AddonManager()

# =============================== GROUPS ================================ #
#============================================================================#
class GroupManager:
    @classmethod
    def get_attr(cls, ms, name, use_ms=False):
        getattr((ms if use_ms else ms.group), name)
    
    @classmethod
    def set_attr(cls, ms, name, value, use_ms=False):
        setattr((ms if use_ms else ms.group), name, value)
    
    @classmethod
    def to_group(cls, group):
        if isinstance(group, Group): return group
        if isinstance(group, GroupSlot): return group.group
        return bpy.data.groups.get(group)
    
    @classmethod
    def group_index(cls, obj, group):
        if isinstance(group, int): return group
        if isinstance(group, GroupSlot): group = group.group
        if isinstance(group, Group): group = group.name
        for i, ms in enumerate(obj.group_slots):
            if ms.name == group: return i
        return -1
    
    @classmethod
    def add(cls, obj, group, link='DATA'):
        bpy.context.scene.objects.active = obj
        group = cls.to_group(group)
        bpy.ops.object.group_slot_add()
        ms = obj.group_slots[-1]
        ms.group = group
        ms.link = link
        return ms
    
    @classmethod
    def remove(cls, obj, group):
        bpy.context.scene.objects.active = obj
        
        id = cls.group_index(obj, group)
        if id < 0: return False
        prev_id = obj.active_group_index
        
        obj.active_group_index = id
        bpy.ops.object.group_slot_remove()
        
        if prev_id > id: prev_id -= 1
        obj.active_group_index = max(prev_id, 0)
        
        return True
    
    @classmethod
    def clear(cls, obj):
        bpy.context.scene.objects.active = obj
        while len(obj.group_slots) > 0:
            obj.active_group_index = 0
            bpy.ops.object.group_slot_remove()

class BatchGroups:
    clipbuffer = None
    
    @classmethod
    def set_attr(cls, name, value, objects, group="", use_ms=False):
        group = GroupManager.to_group(group)
        for obj in objects:
            for ms in obj.group_slots:
                if (not group) or (ms.group == group):
                    GroupManager.set_attr(ms, name, value, use_ms)
    
    @classmethod
    def clear(cls, objects):
        prev_obj = bpy.context.scene.objects.active
        for obj in objects:
            GroupManager.clear(obj)
        bpy.context.scene.objects.active = prev_obj
    
    @classmethod
    def add(cls, objects, group):
        prev_obj = bpy.context.scene.objects.active
        group = GroupManager.to_group(group)
        if not group: group = bpy.data.groups.new("Group")
        for obj in objects:
            GroupManager.add(obj, group)
        bpy.context.scene.objects.active = prev_obj
    
    @classmethod
    def ensure(cls, active_obj, objects, group=""):
        if "\n" in group:
            groups = [m.strip() for m in group.split("\n")]
        else:
            groups = [group.strip()]
        
        for group in groups:
            if not group:
                continue
            
            group = GroupManager.to_group(group)
            
            src = None
            if active_obj:
                for ms in active_obj.group_slots:
                    if ms.group == group:
                        src = ms
                        break
            
            for obj in objects:
                has_group = False
                for ms in obj.group_slots:
                    if ms.group == group:
                        has_group = True
                        break
                
                if not has_group:
                    ms = GroupManager.add(obj, group)
                    if src: ms.link = src.link
    
    @classmethod
    def remove(cls, objects, group=""):
        prev_obj = bpy.context.scene.objects.active
        if not group:
            for obj in objects:
                GroupManager.clear(obj)
        else:
            group = GroupManager.to_group(group)
            for obj in objects:
                id = len(obj.group_slots)-1
                for ms in reversed(tuple(obj.group_slots)):
                    if ms.group == group:
                        GroupManager.remove(obj, id)
                    id -= 1
        bpy.context.scene.objects.active = prev_obj
    
    @classmethod
    def copy(cls, active_obj):
        if not active_obj:
            cls.clipbuffer = []
        else:
            cls.clipbuffer = [(ms.group, ms.link) for ms in active_obj.group_slots]
    
    @classmethod
    def paste(cls, objects):
        ms_infos = cls.clipbuffer
        if ms_infos is None: return
        
        cls.clear(objects)
        
        prev_obj = bpy.context.scene.objects.active
        for obj in objects:
            for group, link in ms_infos:
                GroupManager.add(obj, group, link)
        bpy.context.scene.objects.active = prev_obj

#============================================================================#
@addon.Menu(idname="OBJECT_MT_batch_group_add")
def OBJECT_MT_batch_group_add(self, context):
    """Add group(s) to the selected objects"""
    layout = NestedLayout(self.layout)
    op = layout.operator("object.batch_group_add", text="<Create new>", icon='GROUP')
    op.group = "" # Add new
    for item in GroupsPG.remaining_items:
        idname = item[0]
        name = item[1]
        op = layout.operator("object.batch_group_add", text=name, icon='GROUP')
        op.group = idname

@addon.Operator(idname="view3d.pick_groups")
class Pick_Groups(Pick_Base):
    """Pick group(s) from the object under mouse"""
    
    @classmethod
    def poll(cls, context):
        return (context.mode == 'OBJECT')
    
    def obj_to_info(self, obj):
        txt = ", ".join(ms.name for ms in obj.group_slots)
        return (txt or "<No groups>")
    
    def on_confirm(self, context, obj):
        bpy.ops.ed.undo_push(message="Pick Groups")
        
        BatchGroups.copy(obj)
        self.report({'INFO'}, "Groups copied")
        
        BatchGroups.paste(context.selected_objects)

@addon.Operator(idname="object.batch_group_copy")
def Batch_Copy_Groups(self, context, event):
    """Copy group(s) from the selected objects"""
    if not context.object: return
    BatchGroups.copy(context.object)
    self.report({'INFO'}, "Groups copied")

@addon.Operator(idname="object.batch_group_paste", options={'REGISTER', 'UNDO'})
def Batch_Paste_Groups(self, context, event):
    """Paste group(s) to the selected objects"""
    bpy.ops.ed.undo_push(message="Batch Paste Groups")
    BatchGroups.paste(context.selected_objects)

@addon.Operator(idname="object.batch_group_add", options={'REGISTER', 'UNDO'})
def Batch_Add_Groups(self, context, event, group=""):
    """Add group(s) to the selected objects"""
    bpy.ops.ed.undo_push(message="Batch Add Groups")
    BatchGroups.add(context.selected_objects, group)

@addon.Operator(idname="object.batch_group_ensure", options={'REGISTER', 'UNDO'})
def Batch_Ensure_Groups(self, context, event, group=""):
    """Ensure group(s) for the selected objects"""
    bpy.ops.ed.undo_push(message="Batch Ensure Groups")
    BatchGroups.ensure(context.object, context.selected_objects, group)

@addon.Operator(idname="object.batch_group_apply", options={'REGISTER', 'UNDO'})
def Batch_Apply_Groups(self, context, event, group=""):
    """Apply group(s) and remove from the stack(s)"""
    bpy.ops.ed.undo_push(message="Batch Apply Groups")
    #BatchGroups.apply(context.selected_objects, context.scene, group)

@addon.Operator(idname="object.batch_group_remove", options={'REGISTER', 'UNDO'})
def Batch_Remove_Groups(self, context, event, group=""):
    """Remove group(s) from the selected objects"""
    bpy.ops.ed.undo_push(message="Batch Remove Groups")
    BatchGroups.remove(context.selected_objects, group)

@addon.PropertyGroup
class GroupPG:
    idname = "" | prop()
    
    count = 0 | prop()
    
    initialized = False | prop()
    
    def update(self, context):
        if not self.initialized: return
        message = self.bl_rna.properties["link_to_obj"].description
        value = self.link_to_obj[0]
        bpy.ops.ed.undo_push(message=message)
        value = ('OBJECT' if value else 'DATA')
        BatchGroups.set_attr("link", value, context.selected_objects, self.idname, use_ms=True)
    link_to_obj = (True, True) | prop("Link group to object or data", update=update)
    
    def from_info_toggle(self, info, name):
        ivalue = info[name]
        value = ((ivalue[0] >= 0), ivalue[1])
        setattr(self, name, value)

@addon.PropertyGroup
class GroupsPG:
    items = [GroupPG] | prop()
    
    all_idnames = "" | prop()
    
    remaining_items = []
    
    add_group = "" | prop()
    
    def refresh(self, context):
        infos = {}
        for obj in context.selected_objects:
            for ms in obj.group_slots:
                if not ms.group: continue
                self.extract_info(infos, ms, "")
                self.extract_info(infos, ms)
        if not infos:
            self.extract_info(infos, None, "")
        
        sorted_keys = sorted(infos.keys())
        self.all_idnames = "\n".join(sorted_keys)
        
        current_keys = set(infos.keys())
        GroupsPG.remaining_items = [(mat.name, mat.name, mat.name)
            for mat in bpy.data.groups
            if mat.name not in current_keys]
        GroupsPG.remaining_items.sort(key=lambda item:item[1])
        
        self.items.clear()
        for key in sorted_keys:
            info = infos[key]
            item = self.items.add()
            item.name = info["name"]
            item.idname = info["name"]
            item.count = info["count"]
            item.from_info_toggle(info, "link_to_obj")
            item.initialized = True
    
    def extract_info(self, infos, ms, name=None):
        if name is None:
            name = ms.name
        
        info = infos.get(name)
        
        if info is None:
            info = dict(name=name, count=0)
            infos[name] = info
        
        info["count"] = info["count"] + 1
        
        self.extract_info_toggle(info, ms, "link_to_obj")
    
    def extract_info_toggle(self, info, ms, name):
        if ms is None:
            info[name] = [False, False]
            return
        
        if name == "link_to_obj":
            value = (1 if ms.link == 'OBJECT' else -1)
        else:
            value = (1 if getattr(ms, name) else -1)
        
        ivalue = info.get(name)
        if ivalue is None:
            info[name] = [value, True]
        else:
            if (value * ivalue[0]) < 0:
                ivalue[1] = False
            ivalue[0] += value
    
    def draw_toggle(self, layout, item, name, icon):
        with layout.row(True)(alert=not getattr(item, name)[1]):
            layout.prop(item, name, icon=icon, text="", index=0, toggle=True)
    
    def draw(self, layout):
        all_enabled = (len(self.items) > 1)
        with layout.column(True)(enabled=all_enabled):
            for item in self.items:
                with layout.row(True):
                    icon_value = 0
                    if item.idname:
                        icon_value = layout.icon(bpy.data.groups[item.idname])
                    layout.prop(item, "link_to_obj", text="", icon_value=icon_value, index=0)
                    
                    op = layout.operator("object.batch_group_ensure", text="", icon='GROUP')
                    op.group = item.idname or self.all_idnames
                    
                    count = (item.count if all_enabled else 0)
                    text = "{} ({})".format(item.name or "(All)", count)
                    op = layout.operator("object.batch_group_apply", text=text)
                    op.group = item.idname
                    
                    op = layout.operator("object.batch_group_remove", icon='X', text="")
                    op.group = item.idname

@LeftRightPanel
class VIEW3D_PT_batch_groups:
    bl_category = "Batch"
    bl_context = "objectmode"
    bl_label = "Batch Groups"
    bl_space_type = 'VIEW_3D'
    
    def draw(self, context):
        layout = NestedLayout(self.layout)
        batch_groups = addon.external.groups
        
        with layout.row(True):
            layout.menu("OBJECT_MT_batch_group_add", icon='ZOOMIN', text="")
            layout.operator("view3d.pick_groups", icon='EYEDROPPER', text="")
            layout.operator("object.batch_group_copy", icon='COPYDOWN', text="")
            layout.operator("object.batch_group_paste", icon='PASTEDOWN', text="")
        
        batch_groups.draw(layout)

addon.External.groups = GroupsPG | -prop()
