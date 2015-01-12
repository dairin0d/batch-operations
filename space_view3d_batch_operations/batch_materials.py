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

# =============================== MATERIALS ================================ #
#============================================================================#
"""
It's actually the data (mesh, curve, surface, metaball, text) that dictates the number of materials.
The data has its own list of materials, but they can be overridden on object level
by changing the corresponding slot's link type to 'OBJECT'.


bpy.ops.object.material_slot_add()
Add a new material slot

bpy.ops.object.material_slot_assign()
Assign active material slot to selection

bpy.ops.object.material_slot_copy()
Copies materials to other selected objects

bpy.ops.object.material_slot_deselect()
Deselect by active material slot

bpy.ops.object.material_slot_remove()
Remove the selected material slot

bpy.ops.object.material_slot_select()
Select by active material slot
"""

Material = bpy.types.Material
MaterialSlot = bpy.types.MaterialSlot

class MaterialManager:
    @classmethod
    def get_attr(cls, ms, name, use_ms=False):
        getattr((ms if use_ms else ms.material), name)
    
    @classmethod
    def set_attr(cls, ms, name, value, use_ms=False):
        setattr((ms if use_ms else ms.material), name, value)
    
    @classmethod
    def to_material(cls, material):
        if isinstance(material, Material): return material
        if isinstance(material, MaterialSlot): return material.material
        return bpy.data.materials.get(material)
    
    @classmethod
    def material_index(cls, obj, material):
        if isinstance(material, int): return material
        if isinstance(material, MaterialSlot): material = material.material
        if isinstance(material, Material): material = material.name
        for i, ms in enumerate(obj.material_slots):
            if ms.name == material: return i
        return -1
    
    @classmethod
    def add(cls, obj, material, link='DATA'):
        bpy.context.scene.objects.active = obj
        material = cls.to_material(material)
        bpy.ops.object.material_slot_add()
        ms = obj.material_slots[-1]
        ms.material = material
        ms.link = link
        return ms
    
    @classmethod
    def remove(cls, obj, material):
        bpy.context.scene.objects.active = obj
        
        id = cls.material_index(obj, material)
        if id < 0: return False
        prev_id = obj.active_material_index
        
        obj.active_material_index = id
        bpy.ops.object.material_slot_remove()
        
        if prev_id > id: prev_id -= 1
        obj.active_material_index = max(prev_id, 0)
        
        return True
    
    @classmethod
    def clear(cls, obj):
        bpy.context.scene.objects.active = obj
        while len(obj.material_slots) > 0:
            obj.active_material_index = 0
            bpy.ops.object.material_slot_remove()

class BatchMaterials:
    clipbuffer = None
    
    @classmethod
    def set_attr(cls, name, value, objects, material="", use_ms=False):
        material = MaterialManager.to_material(material)
        for obj in objects:
            for ms in obj.material_slots:
                if (not material) or (ms.material == material):
                    MaterialManager.set_attr(ms, name, value, use_ms)
    
    @classmethod
    def clear(cls, objects):
        prev_obj = bpy.context.scene.objects.active
        for obj in objects:
            MaterialManager.clear(obj)
        bpy.context.scene.objects.active = prev_obj
    
    @classmethod
    def add(cls, objects, material):
        prev_obj = bpy.context.scene.objects.active
        material = MaterialManager.to_material(material)
        if not material: material = bpy.data.materials.new("Material")
        for obj in objects:
            MaterialManager.add(obj, material)
        bpy.context.scene.objects.active = prev_obj
    
    @classmethod
    def ensure(cls, active_obj, objects, material=""):
        if "\n" in material:
            materials = [m.strip() for m in material.split("\n")]
        else:
            materials = [material.strip()]
        
        for material in materials:
            if not material:
                continue
            
            material = MaterialManager.to_material(material)
            
            src = None
            if active_obj:
                for ms in active_obj.material_slots:
                    if ms.material == material:
                        src = ms
                        break
            
            for obj in objects:
                has_material = False
                for ms in obj.material_slots:
                    if ms.material == material:
                        has_material = True
                        break
                
                if not has_material:
                    ms = MaterialManager.add(obj, material)
                    if src: ms.link = src.link
    
    @classmethod
    def remove(cls, objects, material=""):
        prev_obj = bpy.context.scene.objects.active
        if not material:
            for obj in objects:
                MaterialManager.clear(obj)
        else:
            material = MaterialManager.to_material(material)
            for obj in objects:
                id = len(obj.material_slots)-1
                for ms in reversed(tuple(obj.material_slots)):
                    if ms.material == material:
                        MaterialManager.remove(obj, id)
                    id -= 1
        bpy.context.scene.objects.active = prev_obj
    
    @classmethod
    def copy(cls, active_obj):
        if not active_obj:
            cls.clipbuffer = []
        else:
            cls.clipbuffer = [(ms.material, ms.link) for ms in active_obj.material_slots]
    
    @classmethod
    def paste(cls, objects):
        ms_infos = cls.clipbuffer
        if ms_infos is None: return
        
        cls.clear(objects)
        
        prev_obj = bpy.context.scene.objects.active
        for obj in objects:
            for material, link in ms_infos:
                MaterialManager.add(obj, material, link)
        bpy.context.scene.objects.active = prev_obj

#============================================================================#
@addon.Menu(idname="OBJECT_MT_batch_material_add")
def OBJECT_MT_batch_material_add(self, context):
    """Add material(s) to the selected objects"""
    layout = NestedLayout(self.layout)
    op = layout.operator("object.batch_material_add", text="<Create new>", icon='MATERIAL')
    op.material = "" # Add new
    for item in MaterialsPG.remaining_items:
        idname = item[0]
        name = item[1]
        op = layout.operator("object.batch_material_add", text=name, icon='MATERIAL')
        op.material = idname

@addon.Operator(idname="view3d.pick_materials")
class Pick_Materials(Pick_Base):
    """Pick material(s) from the object under mouse"""
    
    @classmethod
    def poll(cls, context):
        return (context.mode == 'OBJECT')
    
    def obj_to_info(self, obj):
        txt = ", ".join(ms.name for ms in obj.material_slots)
        return (txt or "<No materials>")
    
    def on_confirm(self, context, obj):
        bpy.ops.ed.undo_push(message="Pick Materials")
        
        BatchMaterials.copy(obj)
        self.report({'INFO'}, "Materials copied")
        
        BatchMaterials.paste(context.selected_objects)

@addon.Operator(idname="object.batch_material_copy")
def Batch_Copy_Materials(self, context, event):
    """Copy material(s) from the selected objects"""
    if not context.object: return
    BatchMaterials.copy(context.object)
    self.report({'INFO'}, "Materials copied")

@addon.Operator(idname="object.batch_material_paste", options={'REGISTER', 'UNDO'})
def Batch_Paste_Materials(self, context, event):
    """Paste material(s) to the selected objects"""
    bpy.ops.ed.undo_push(message="Batch Paste Materials")
    BatchMaterials.paste(context.selected_objects)

@addon.Operator(idname="object.batch_material_add", options={'REGISTER', 'UNDO'})
def Batch_Add_Materials(self, context, event, material=""):
    """Add material(s) to the selected objects"""
    bpy.ops.ed.undo_push(message="Batch Add Materials")
    BatchMaterials.add(context.selected_objects, material)

@addon.Operator(idname="object.batch_material_ensure", options={'REGISTER', 'UNDO'})
def Batch_Ensure_Materials(self, context, event, material=""):
    """Ensure material(s) for the selected objects"""
    bpy.ops.ed.undo_push(message="Batch Ensure Materials")
    BatchMaterials.ensure(context.object, context.selected_objects, material)

@addon.Operator(idname="object.batch_material_apply", options={'REGISTER', 'UNDO'})
def Batch_Apply_Materials(self, context, event, material=""):
    """Apply material(s) and remove from the stack(s)"""
    bpy.ops.ed.undo_push(message="Batch Apply Materials")
    #BatchMaterials.apply(context.selected_objects, context.scene, material)

@addon.Operator(idname="object.batch_material_remove", options={'REGISTER', 'UNDO'})
def Batch_Remove_Materials(self, context, event, material=""):
    """Remove material(s) from the selected objects"""
    bpy.ops.ed.undo_push(message="Batch Remove Materials")
    BatchMaterials.remove(context.selected_objects, material)

@addon.PropertyGroup
class MaterialPG:
    idname = "" | prop()
    
    count = 0 | prop()
    
    initialized = False | prop()
    
    def update(self, context):
        if not self.initialized: return
        message = self.bl_rna.properties["link_to_obj"].description
        value = self.link_to_obj[0]
        bpy.ops.ed.undo_push(message=message)
        value = ('OBJECT' if value else 'DATA')
        BatchMaterials.set_attr("link", value, context.selected_objects, self.idname, use_ms=True)
    link_to_obj = (True, True) | prop("Link material to object or data", update=update)
    
    def from_info_toggle(self, info, name):
        ivalue = info[name]
        value = ((ivalue[0] >= 0), ivalue[1])
        setattr(self, name, value)

@addon.PropertyGroup
class MaterialsPG:
    items = [MaterialPG] | prop()
    
    all_idnames = "" | prop()
    
    remaining_items = []
    
    add_material = "" | prop()
    
    def refresh(self, context):
        infos = {}
        for obj in context.selected_objects:
            for ms in obj.material_slots:
                if not ms.material: continue
                self.extract_info(infos, ms, "")
                self.extract_info(infos, ms)
        if not infos:
            self.extract_info(infos, None, "")
        
        sorted_keys = sorted(infos.keys())
        self.all_idnames = "\n".join(sorted_keys)
        
        current_keys = set(infos.keys())
        MaterialsPG.remaining_items = [(mat.name, mat.name, mat.name)
            for mat in bpy.data.materials
            if mat.name not in current_keys]
        MaterialsPG.remaining_items.sort(key=lambda item:item[1])
        
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
                    # No, this is actually wrong. link is a property of MaterialSlot and has no relation to material.
                    #self.draw_toggle(layout, item, "link_to_obj", 'EDITMODE_HLT')
                    
                    icon_value = 0
                    if item.idname:
                        icon_value = layout.icon(bpy.data.materials[item.idname])
                    layout.prop(item, "link_to_obj", text="", icon_value=icon_value, index=0)
                    
                    op = layout.operator("object.batch_material_ensure", text="", icon='MATERIAL')
                    op.material = item.idname or self.all_idnames
                    
                    count = (item.count if all_enabled else 0)
                    text = "{} ({})".format(item.name or "(All)", count)
                    op = layout.operator("object.batch_material_apply", text=text)
                    op.material = item.idname
                    
                    op = layout.operator("object.batch_material_remove", icon='X', text="")
                    op.material = item.idname

@LeftRightPanel
class VIEW3D_PT_batch_materials:
    bl_category = "Batch"
    bl_context = "objectmode"
    bl_label = "Batch Materials"
    bl_space_type = 'VIEW_3D'
    
    def draw(self, context):
        layout = NestedLayout(self.layout)
        batch_materials = addon.external.materials
        
        with layout.row(True):
            layout.menu("OBJECT_MT_batch_material_add", icon='ZOOMIN', text="")
            layout.operator("view3d.pick_materials", icon='EYEDROPPER', text="")
            layout.operator("object.batch_material_copy", icon='COPYDOWN', text="")
            layout.operator("object.batch_material_paste", icon='PASTEDOWN', text="")
        
        batch_materials.draw(layout)

addon.External.materials = MaterialsPG | -prop()
