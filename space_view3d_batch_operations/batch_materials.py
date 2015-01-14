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
from {0}dairin0d.utils_ui import NestedLayout, tag_redraw
from {0}dairin0d.bpy_inspect import prop, BlRna, BlEnums
from {0}dairin0d.utils_accumulation import Aggregator, aggregated
from {0}dairin0d.utils_addon import AddonManager
""".format(dairin0d_location))

from .batch_common import (
    copyattrs, attrs_to_dict, dict_to_attrs,
    Pick_Base, LeftRightPanel,
    round_to_bool, is_visible, has_common_layers, idnames_separator
)

addon = AddonManager()

"""
It's actually the data (mesh, curve, surface, metaball, text) that dictates the number of materials.
The data has its own list of materials, but they can be overridden on object level
by changing the corresponding slot's link type to 'OBJECT'.

* options synchronization
* in edit mode, 'SELECTION' mode should be interpreted as mesh/etc. selection?
* [DONE] rename (for All: rename listed materials by some pattern, e.g. common name + id, or the corresponding data/object name)
* [DONE] replace
* merge identical?
* make single-user copies? (this is probably useless)
* Option "Affect data": can modify data materials or switch slot.link to OBJECT
* Option "Reuse slots": when adding material, use unoccupied slots first, or always creating new ones
"""

class PatternRenamer:
    before = "\u0002"
    after = "\u0003"
    
    @classmethod
    def is_pattern(cls, value):
        return (cls.before in value) or (cls.after in value)
    
    @classmethod
    def make(cls, subseq, subseq_starts, subseq_ends):
        pattern = subseq
        if (not subseq_starts): pattern = cls.before + pattern
        if (not subseq_ends) and subseq: pattern = pattern + cls.after
        return pattern
    
    @classmethod
    def apply(cls, value, src_pattern, pattern):
        middle = src_pattern.lstrip(cls.before).rstrip(cls.after)
        i_mid = value.index(middle)
        
        sL, sC, sR = "", value, ""
        
        if src_pattern.startswith(cls.before):
            if middle:
                sL = value[:i_mid]
                sC = middle
            else:
                sL = middle
        
        if src_pattern.endswith(cls.after):
            if middle:
                sR = value[i_mid+len(middle):]
                sC = middle
        
        return pattern.replace(cls.before, sL).replace(cls.after, sR)
    
    @classmethod
    def apply_to_attr(cls, obj, attr_name, pattern, src_pattern):
        setattr(obj, attr_name, cls.apply(getattr(obj, attr_name), src_pattern, pattern))

#============================================================================#
Category_Name = "Material"
CATEGORY_NAME = Category_Name.upper()
category_name = Category_Name.lower()

Material = bpy.types.Material
MaterialSlot = bpy.types.MaterialSlot

class BatchOperations:
    clipbuffer = None
    
    @classmethod
    def to_material(cls, material):
        if isinstance(material, Material): return material
        if isinstance(material, MaterialSlot): return material.material
        return bpy.data.materials.get(material)
    
    @classmethod
    def add_material_to_obj(cls, obj, idname):
        material = cls.to_material(idname)
        for ms in obj.material_slots:
            if not ms.material:
                ms.link = 'OBJECT'
                ms.material = material
                break
        else: # no free slots found
            obj.data.materials.append(None)
            ms = obj.material_slots[len(obj.material_slots)-1]
            ms.link = 'OBJECT'
            ms.material = material
    
    @classmethod
    def clear_obj_materials(cls, obj, idnames=None, check_in=True):
        for ms in obj.material_slots:
            if (idnames is None) or ((ms.name in idnames) == check_in):
                ms.link = 'OBJECT'
                ms.material = None
    
    @classmethod
    def clean_name(cls, mat):
        return mat.name
    
    @classmethod
    def iter_names(cls, obj):
        for ms in obj.material_slots:
            if not ms.material: continue
            yield cls.clean_name(ms.material)
    
    @classmethod
    def enum_all(cls):
        for mat in bpy.data.materials:
            yield (mat.name, mat.name, mat.name)
    
    @classmethod
    def icon_kwargs(cls, idname):
        if not idname: return {"icon": 'MATERIAL'}
        try:
            return {"icon_value": bpy.types.UILayout.icon(bpy.data.materials.get(idname))}
        except:
            return {"icon": 'MATERIAL'}
    
    @classmethod
    def iterate(cls, search_in, context=None):
        if search_in != 'FILE':
            for obj in cls.iterate_objects(search_in, context):
                for ms in obj.material_slots:
                    if ms.material: yield ms.material
        else:
            yield from bpy.data.materials
    
    @classmethod
    def iterate_objects(cls, search_in, context=None):
        if context is None: context = bpy.context
        obj_types = BlEnums.object_types_geometry
        scene = context.scene
        if search_in == 'SELECTION':
            for obj in context.selected_objects:
                if (obj.type in obj_types):
                    yield obj
        elif search_in == 'VISIBLE':
            for obj in scene.objects:
                if (obj.type in obj_types) and is_visible(obj, scene):
                    yield obj
        elif search_in == 'LAYER':
            for obj in scene.objects:
                if (obj.type in obj_types) and has_common_layers(obj, scene):
                    yield obj
        elif search_in == 'SCENE':
            for obj in scene.objects:
                if (obj.type in obj_types):
                    yield obj
        elif search_in == 'FILE':
            for obj in bpy.data.objects:
                if (obj.type in obj_types):
                    yield obj
    
    @classmethod
    def split_idnames(cls, idnames):
        if idnames is None: return None
        if not isinstance(idnames, str): return set(idnames)
        return {n.strip() for n in idnames.split(idnames_separator)}
    
    @classmethod
    def set_attr(cls, name, value, objects, idnames, **kwargs):
        idnames = cls.split_idnames(idnames)
        
        if name == "use_fake_user":
            mesh = None
            
            for idname in idnames:
                mat = cls.to_material(idname)
                
                if value:
                    # can't set use_fake_user if 0 users
                    if mat.users == 0:
                        if mesh is None: mesh = bpy.data.meshes.new("TmpMesh")
                        mesh.materials.append(mat)
                else:
                    # can't unset use_fake_user if fake is the only user
                    if mat.users == 1:
                        if mesh is None: mesh = bpy.data.meshes.new("TmpMesh")
                        mesh.materials.append(mat)
                
                mat.use_fake_user = value
                
                if mesh: mesh.materials.pop(0)
            
            if mesh: bpy.data.meshes.remove(mesh)
        else:
            use_kwargs = False
            
            _setattr = setattr
            if isinstance(value, str):
                if PatternRenamer.is_pattern(value):
                    _setattr = PatternRenamer.apply_to_attr
                    use_kwargs = True
            
            if not use_kwargs: kwargs = {}
            
            for obj in objects:
                if isinstance(obj, Material):
                    if obj.name in idnames:
                        _setattr(obj, name, value, **kwargs)
                else:
                    for ms in obj.material_slots:
                        if not ms.material: continue
                        if ms.name in idnames:
                            _setattr(ms.material, name, value, **kwargs)
    
    
    @classmethod
    def clear(cls, objects):
        for obj in objects:
            cls.clear_obj_materials(obj)
    
    @classmethod
    def add(cls, objects, idnames):
        idnames = cls.split_idnames(idnames)
        for obj in objects:
            for idname in idnames:
                cls.add_material_to_obj(obj, idname)
    
    @classmethod
    def assign(cls, active_obj, objects, idnames):
        idnames = cls.split_idnames(idnames)
        for obj in objects:
            for idname in idnames.difference(ms.name for ms in obj.material_slots):
                cls.add_material_to_obj(obj, idname)
    
    @classmethod
    def remove(cls, objects, idnames, from_file=False):
        cls.replace(objects, idnames, "", from_file)
    
    @classmethod
    def replace(cls, objects, src_idnames, dst_idname, from_file=False):
        idnames = cls.split_idnames(src_idnames)
        dst_material = cls.to_material(dst_idname)
        if not from_file:
            for obj in objects:
                for ms in obj.material_slots:
                    if (idnames is None) or (ms.name in idnames):
                        ms.link = 'OBJECT'
                        ms.material = dst_material
        else:
            for obj in bpy.data.objects:
                for ms in obj.material_slots:
                    if (idnames is None) or (ms.name in idnames):
                        ms.material = dst_material
            for datas in (bpy.data.meshes, bpy.data.curves, bpy.data.metaballs):
                for data in datas:
                    for i in range(len(data.materials)):
                        mat = data.materials[i]
                        if mat and ((idnames is None) or (mat.name in idnames)):
                            data.materials[i] = dst_material
    
    @classmethod
    def select(cls, scene, idnames):
        idnames = cls.split_idnames(idnames)
        for obj in scene.objects:
            obj.select = any((ms.name in idnames) for ms in obj.material_slots)
    
    @classmethod
    def purge(cls, even_with_fake_users, idnames=None):
        if idnames is None:
            if even_with_fake_users:
                fake_idnames = (mat.name for mat in bpy.data.materials if mat.use_fake_user and (mat.users == 1))
                cls.set_attr("use_fake_user", False, None, fake_idnames)
            for mat in tuple(bpy.data.materials):
                if mat.users > 0: continue
                bpy.data.materials.remove(mat)
        else:
            cls.remove(None, idnames, True)
            cls.set_attr("use_fake_user", False, None, idnames)
            idnames = cls.split_idnames(idnames)
            for mat in tuple(bpy.data.materials):
                if mat.name in idnames:
                    bpy.data.materials.remove(mat)
    
    @classmethod
    def copy(cls, active_obj, exclude=()):
        if not active_obj:
            cls.clipbuffer = []
        else:
            cls.clipbuffer = [ms.name for ms in obj.material_slots if ms.material and (ms.name not in exclude)]
    
    @classmethod
    def paste(cls, objects, paste_mode):
        idnames = cls.clipbuffer
        if idnames is None: return
        if paste_mode != 'AND':
            for obj in objects:
                if paste_mode == 'SET': cls.clear_obj_materials(obj)
                for idname in idnames:
                    cls.add_material_to_obj(idname)
        else:
            for obj in objects:
                cls.clear_obj_materials(obj, idnames, False)

#============================================================================#
@addon.Menu(idname="OBJECT_MT_batch_{}_add".format(category_name), description=
"Add {}(s)".format(Category_Name))
def Menu_Add(self, context):
    layout = NestedLayout(self.layout)
    op = layout.operator("object.batch_{}_add".format(category_name), text="<Create new>", icon='MATERIAL')
    op.create = True
    for item in CategoryPG.remaining_items:
        idname = item[0]
        name = item[1]
        #icon_kw = BatchOperations.icon_kwargs(idname)
        #op = layout.operator("object.batch_{}_add".format(category_name), text=name, **icon_kw)
        # layout.operator() doesn't support icon_value argument
        op = layout.operator("object.batch_{}_add".format(category_name), text=name, icon='MATERIAL')
        op.idnames = idname

@addon.Operator(idname="view3d.pick_{}s".format(category_name), options={'INTERNAL', 'REGISTER'}, description=
"Pick {}(s) from the object under mouse".format(Category_Name))
class Operator_Pick(Pick_Base):
    @classmethod
    def poll(cls, context):
        return (context.mode == 'OBJECT')
    
    def obj_to_info(self, obj):
        txt = ", ".join(BatchOperations.iter_names(obj))
        return (txt or "<No {}>".format(category_name))
    
    def on_confirm(self, context, obj):
        category = get_category()
        options = get_options()
        bpy.ops.ed.undo_push(message="Pick {}s".format(Category_Name))
        BatchOperations.copy(obj)
        self.report({'INFO'}, "{}s copied".format(Category_Name))
        BatchOperations.paste(options.iterate_objects(context), options.paste_mode)
        category.tag_refresh()

# NOTE: only when 'REGISTER' is in bl_options and {'FINISHED'} is returned,
# the operator will be recorded in wm.operators and info reports

@addon.Operator(idname="object.batch_{}_copy".format(category_name), options={'INTERNAL'}, description=
"Click: Copy")
def Operator_Copy(self, context, event):
    if not context.object: return
    BatchOperations.copy(context.object, CategoryPG.excluded)
    self.report({'INFO'}, "{}s copied".format(Category_Name))

@addon.Operator(idname="object.batch_{}_paste".format(category_name), options={'INTERNAL', 'REGISTER'}, description=
"Click: Paste (+Ctrl: Replace; +Shift: Add; +Alt: Filter)")
def Operator_Paste(self, context, event):
    category = get_category()
    options = get_options()
    bpy.ops.ed.undo_push(message="Batch Paste {}s".format(Category_Name))
    paste_mode = options.paste_mode
    if event.shift: paste_mode = 'OR'
    elif event.ctrl: paste_mode = 'SET'
    elif event.alt: paste_mode = 'AND'
    BatchOperations.paste(options.iterate_objects(context), paste_mode)
    category.tag_refresh()
    return {'FINISHED'}

@addon.Operator(idname="object.batch_{}_add".format(category_name), options={'INTERNAL', 'REGISTER'}, description=
"Click: Add")
def Operator_Add(self, context, event, idnames="", create=False):
    category = get_category()
    options = get_options()
    bpy.ops.ed.undo_push(message="Batch Add {}s".format(Category_Name))
    if create:
        mat = bpy.data.materials.new("Material")
        idnames = mat.name
    BatchOperations.add(options.iterate_objects(context), idnames)
    category.tag_refresh()
    return {'FINISHED'}

@addon.Operator(idname="object.batch_{}_replace".format(category_name), options={'INTERNAL', 'REGISTER'}, description=
"Click: Replace this {0} with another (+Ctrl: globally); Alt+Click: Replace {0}(s) with this one (+Ctrl: globally)".format(category_name))
def Operator_Replace(self, context, event, idnames="", index=0):
    category = get_category()
    options = get_options()
    if event.alt:
        if index > 0: # not applicable to "All"
            bpy.ops.ed.undo_push(message="Batch Replace {}s".format(Category_Name))
            BatchOperations.replace(options.iterate_objects(context, event.ctrl), None, idnames, (options.search_in == 'FILE'))
            category.tag_refresh()
            return {'FINISHED'}
    else:
        globally = event.ctrl
        def draw_popup_menu(self, context):
            layout = NestedLayout(self.layout)
            for item in BatchOperations.enum_all():
                idname = item[0]
                name = item[1]
                op = layout.operator("object.batch_{}_replace_reverse".format(category_name), text=name, icon='MATERIAL')
                op.src_idnames = idnames
                op.dst_idname = idname
                op.globally = globally
        context.window_manager.popup_menu(draw_popup_menu, title="Replace with", icon='ARROW_LEFTRIGHT')

@addon.Operator(idname="object.batch_{}_replace_reverse".format(category_name), options={'INTERNAL', 'REGISTER'}, description=
"Click: Replace this {0} with another (+Ctrl: globally)".format(category_name))
def Operator_Replace_Reverse(self, context, event, src_idnames="", dst_idname="", globally=False):
    category = get_category()
    options = get_options()
    if event is not None: globally |= event.ctrl # ? maybe XOR?
    bpy.ops.ed.undo_push(message="Batch Replace {}s".format(Category_Name))
    BatchOperations.replace(options.iterate_objects(context, globally), src_idnames, dst_idname, (options.search_in == 'FILE'))
    category.tag_refresh()
    return {'FINISHED'}

@addon.Operator(idname="object.batch_{}_assign".format(category_name), options={'INTERNAL', 'REGISTER'}, description=
"Click: Assign (+Ctrl: globally); Alt+Click: Rename; Shift+Click: (De)select row; Shift+Ctrl+Click: Select all objects with this item")
def Operator_Assign(self, context, event, idnames="", index=0):
    category = get_category()
    options = get_options()
    if event.alt:
        if CategoryPG.rename_id != index:
            if index == 0: # All -> aggregate
                if len(category.items) > 2:
                    aggr = Aggregator('STRING', {'subseq', 'subseq_starts', 'subseq_ends'})
                    for i in range(1, len(category.items)):
                        aggr.add(category.items[i].idname)
                    pattern = PatternRenamer.make(aggr.subseq, aggr.subseq_starts, aggr.subseq_ends)
                else:
                    pattern = category.items[1].idname
            else:
                pattern = category.items[index].idname
            CategoryPG.rename_id = -1 # disable side-effects
            CategoryPG.src_pattern = pattern
            category.rename = pattern
            CategoryPG.rename_id = index # side-effects are enabled now
    elif event.shift:
        if event.ctrl:
            bpy.ops.ed.undo_push(message="Batch Select {}s".format(Category_Name))
            BatchOperations.select(context.scene, idnames)
        else:
            category = get_category()
            CategoryPG.toggle_excluded(category.items[index].idname)
    else:
        bpy.ops.ed.undo_push(message="Batch Assign {}s".format(Category_Name))
        BatchOperations.assign(context.object, options.iterate_objects(context, event.ctrl), idnames)
    category.tag_refresh()
    return {'FINISHED'}

@addon.Operator(idname="object.batch_{}_remove".format(category_name), options={'INTERNAL', 'REGISTER'}, description=
"Click: Remove (+Ctrl: globally); Alt+Click: Purge")
def Operator_Remove(self, context, event, idnames="", index=0):
    category = get_category()
    options = get_options()
    if event.alt:
        bpy.ops.ed.undo_push(message="Purge {}s".format(Category_Name))
        BatchOperations.purge(True, idnames)
    else:
        bpy.ops.ed.undo_push(message="Batch Remove {}s".format(Category_Name))
        BatchOperations.remove(options.iterate_objects(context, event.ctrl), idnames, (options.search_in == 'FILE'))
    category.tag_refresh()
    return {'FINISHED'}

def add_aggregate_attrs(AggregateInfo, CategoryItemPG, idname_attr, declarations):
    AggregateInfo.idname_attr = idname_attr
    AggregateInfo.aggr_infos = {} # make sure it's not shared
    CategoryItemPG.names_icons = [] # make sure it's not shared
    
    def make_update(name):
        def update(self, context):
            if not self.user_editable: return
            category = get_category()
            options = get_options()
            message = self.bl_rna.properties[name].description
            value = getattr(self, name)
            bpy.ops.ed.undo_push(message=message)
            idnames = self.idname or category.all_idnames
            BatchOperations.set_attr(name, value, options.iterate_objects(context), idnames)
            category.tag_refresh()
        return update
    
    for name, params in declarations:
        prop_kwargs = params.get("prop")
        if prop_kwargs is None: prop_kwargs = {}
        if "default" not in prop_kwargs:
            prop_kwargs["default"] = False
        if "tooltip" in params:
            prop_kwargs["description"] = params["tooltip"]
        if "update" not in prop_kwargs:
            prop_kwargs["update"] = params.get("update") or make_update(name)
        setattr(CategoryItemPG, name, None | prop(**prop_kwargs))
        
        icons = params.get("icons")
        if icons is None: icons = ('CHECKBOX_HLT', 'CHECKBOX_DEHLT')
        elif isinstance(icons, str): icons = (icons, icons)
        CategoryItemPG.names_icons.append((name, icons))
        
        aggr = params.get("aggr")
        if aggr is None: aggr = dict(init=('BOOL', {"same", "mean"}), fill=("mean", round_to_bool))
        AggregateInfo.aggr_infos[name] = aggr

class AggregateInfo:
    aggr_infos = {}
    idname_attr = None
    
    def __init__(self, idname, name):
        self.idname = idname
        self.name = name
        self.count = 0
        self.aggrs = {}
        for name, params in self.aggr_infos.items():
            self.aggrs[name] = Aggregator(*params["init"])
    
    def fill_item(self, item):
        item.name = self.name
        item.idname = self.idname
        item.count = self.count
        for name, params in self.aggr_infos.items():
            self.fill_aggr(item, name, *params["fill"])
        item.user_editable = True
    
    def fill_aggr(self, item, name, query, convert=None):
        aggr = self.aggrs[name]
        value = getattr(aggr, query)
        if convert is not None: value = convert(value)
        setattr(item, name, value)
        item[name+":same"] = aggr.same
    
    @classmethod
    def collect_info(cls, items, count_users=False):
        infos = {}
        for item in items:
            cls.extract_info(infos, item, "", count_users=count_users)
            cls.extract_info(infos, item, count_users=count_users)
        return infos
    
    @classmethod
    def extract_info(cls, infos, item, idname=None, count_users=False):
        if idname is None: idname = getattr(item, cls.idname_attr)
        
        info = infos.get(idname)
        if info is None:
            name = (BatchOperations.clean_name(item) if idname else "")
            infos[idname] = info = cls(idname, name) # double assign
        
        if count_users:
            if not idname:
                info.count += item.users # All
            else:
                info.count = item.users
        else:
            info.count += 1
        
        for name in cls.aggr_infos:
            info.aggrs[name].add(getattr(item, name))

@addon.PropertyGroup
class CategoryItemPG:
    sort_id = 0 | prop()
    user_editable = False | prop()
    count = 0 | prop()
    idname = "" | prop()
    names_icons = []

add_aggregate_attrs(AggregateInfo, CategoryItemPG, "name", [
    ("use_fake_user", dict(tooltip="Keep this datablock even if it has no users", icons=('PINNED', 'UNPINNED'))),
])

@addon.PropertyGroup
class CategoryOptionsPG:
    def update_synchronized(self, context):
        pass
    synchronized = False | prop("Synchronized", "Synchronized", update=update_synchronized)
    
    def update_autorefresh(self, context):
        pass
    autorefresh = True | prop("Auto-refresh", update=update_autorefresh)
    
    def update(self, context):
        category = get_category()
        category.tag_refresh()
    
    paste_mode = 'SET' | prop("Copy/Paste mode", update=update, items=[
        ('SET', "Replace", "Replace objects' {}(s) with the copied ones".format(category_name), 'ROTACTIVE'),
        ('OR', "Add", "Add copied {}(s) to objects".format(category_name), 'ROTATECOLLECTION'),
        ('AND', "Filter", "Remove objects' {}(s) that are not among the copied".format(category_name), 'ROTATECENTER'),
    ])
    search_in = 'SELECTION' | prop("Show summary for", update=update, items=[
        ('SELECTION', "Selection", "Display {}(s) of the selection".format(category_name), 'RESTRICT_SELECT_OFF'),
        ('VISIBLE', "Visible", "Display {}(s) of the visible objects".format(category_name), 'RESTRICT_VIEW_OFF'),
        ('LAYER', "Layer", "Display {}(s) of the objects in the visible layers".format(category_name), 'RENDERLAYERS'),
        ('SCENE', "Scene", "Display {}(s) of the objects in the current scene".format(category_name), 'SCENE_DATA'),
        ('FILE', "File", "Display all {}(s) in this file".format(category_name), 'FILE_BLEND'),
    ])
    
    def iterate(self, context=None, globally=False):
        search_in = ('FILE' if globally else self.search_in)
        return BatchOperations.iterate(search_in, context)
    def iterate_objects(self, context=None, globally=False):
        search_in = ('FILE' if globally else self.search_in)
        return BatchOperations.iterate_objects(search_in, context)

@addon.PropertyGroup
class CategoryPG:
    prev_idnames = set()
    excluded = set()
    
    def update_rename(self, context):
        if CategoryPG.rename_id < 0: return
        category = get_category()
        options = get_options()
        bpy.ops.ed.undo_push(message="Rename {}".format(category_name))
        idnames = category.items[CategoryPG.rename_id].idname or category.all_idnames
        BatchOperations.set_attr("name", self.rename, options.iterate(context), idnames, src_pattern=CategoryPG.src_pattern)
        CategoryPG.rename_id = -1 # Auto switch off
        category.tag_refresh()
    
    rename_id = -1
    src_pattern = ""
    rename = "" | prop("Rename", "", update=update_rename)
    
    was_drawn = False | prop()
    next_refresh_time = -1.0 | prop()
    
    needs_refresh = True | prop()
    def tag_refresh(self):
        self.needs_refresh = True
        tag_redraw()
    
    all_idnames = property(lambda self: idnames_separator.join(
        item.idname for item in self.items
        if item.idname and not CategoryPG.is_excluded(item.idname)))
    
    items = [CategoryItemPG] | prop()
    
    remaining_items = []
    
    @classmethod
    def is_excluded(cls, idname):
        return idname in cls.excluded
    @classmethod
    def set_excluded(cls, idname, value):
        if value:
            cls.excluded.add(idname)
        else:
            cls.excluded.discard(idname)
    @classmethod
    def toggle_excluded(cls, idname):
        if idname in cls.excluded:
            cls.excluded.discard(idname)
        else:
            cls.excluded.add(idname)
    
    def refresh(self, context, needs_refresh=False):
        options = get_options()
        needs_refresh |= self.needs_refresh
        needs_refresh |= options.autorefresh and (time.clock() > self.next_refresh_time)
        if not needs_refresh: return
        self.next_refresh_time = time.clock() + addon.preferences.refresh_interval
        
        cls = self.__class__
        
        processing_time = time.clock()
        
        infos = AggregateInfo.collect_info(options.iterate(context), (options.search_in == 'FILE'))
        
        curr_idnames = set(infos.keys())
        if curr_idnames != cls.prev_idnames:
            # remember excluded state while idnames are the same
            cls.excluded.clear()
            CategoryPG.rename_id = -1
        cls.prev_idnames = curr_idnames
        
        cls.remaining_items = [enum_item
            for enum_item in BatchOperations.enum_all()
            if enum_item[0] not in curr_idnames]
        cls.remaining_items.sort(key=lambda item:item[1])
        
        self.items.clear()
        for i, key in enumerate(sorted(infos.keys())):
            item = self.items.add()
            item.sort_id = i
            infos[key].fill_item(item)
        
        processing_time = time.clock() - processing_time
        # Disable autorefresh if it takes too much time
        if processing_time > 0.05: options.autorefresh = False
        
        self.needs_refresh = False
    
    def draw_toggle(self, layout, item, name, icons):
        icon = (icons[0] if getattr(item, name) else icons[1])
        with layout.row(True)(alert=not item[name+":same"]):
            layout.prop(item, name, icon=icon, text="", toggle=True)
    
    def draw(self, layout):
        self.was_drawn = True
        self.refresh(bpy.context)
        
        if not self.items: return
        
        all_idnames = self.all_idnames
        
        with layout.column(True):
            for item in self.items:
                with layout.row(True)(active=(item.idname not in CategoryPG.excluded)):
                    for name, icons in item.names_icons:
                        self.draw_toggle(layout, item, name, icons)
                    
                    op = layout.operator("object.batch_{}_replace".format(category_name), text="", icon='ARROW_LEFTRIGHT')
                    op.idnames = item.idname or all_idnames
                    op.index = item.sort_id
                    
                    if CategoryPG.rename_id == item.sort_id:
                        layout.prop(self, "rename", text="")
                    else:
                        #icon_kw = BatchOperations.icon_kwargs(idname)
                        text = "{} ({})".format(item.name or "(All)", item.count)
                        op = layout.operator("object.batch_{}_assign".format(category_name), text=text)
                        op.idnames = item.idname or all_idnames
                        op.index = item.sort_id
                    
                    op = layout.operator("object.batch_{}_remove".format(category_name), text="", icon='X')
                    op.idnames = item.idname or all_idnames
                    op.index = item.sort_id

@addon.Menu(idname="VIEW3D_MT_batch_{}s_options_paste_mode".format(category_name), label="Paste mode")
def Menu_PasteMode(self, context):
    """Paste mode"""
    layout = NestedLayout(self.layout)
    options = get_options()
    layout.props_enum(options, "paste_mode")

@addon.Menu(idname="VIEW3D_MT_batch_{}s_options_search_in".format(category_name), label="Filter")
def Menu_SearchIn(self, context):
    """Filter"""
    layout = NestedLayout(self.layout)
    options = get_options()
    layout.props_enum(options, "search_in")

@addon.Operator(idname="object.batch_{}_purge_unused".format(category_name), options={'INTERNAL', 'REGISTER'}, description=
"Click: Purge unused (+Ctrl: even those with use_fake_users)", label="Purge unused")
def Operator_Purge_Unused(self, context, event, idnames="", index=0):
    category = get_category()
    options = get_options()
    bpy.ops.ed.undo_push(message="Purge Unused {}s".format(Category_Name))
    BatchOperations.purge(event.ctrl)
    category.tag_refresh()
    return {'FINISHED'}

@addon.Menu(idname="VIEW3D_MT_batch_{}s_options".format(category_name), label="Options")
def Menu_Options(self, context):
    """Options"""
    layout = NestedLayout(self.layout)
    options = get_options()
    with layout.column():
        layout.prop(options, "synchronized")
        layout.menu("VIEW3D_MT_batch_{}s_options_paste_mode".format(category_name), icon='PASTEDOWN')
        layout.menu("VIEW3D_MT_batch_{}s_options_search_in".format(category_name), icon='VIEWZOOM')
        layout.operator("object.batch_{}_purge_unused".format(category_name), icon='GHOST_DISABLED')

@addon.Operator(idname="object.batch_{}_refresh".format(category_name), options={'INTERNAL', 'REGISTER'}, description=
"Click: Force refresh; Ctrl+Click: Toggle auto-refresh")
def Operator_Refresh(self, context, event):
    category = get_category()
    options = get_options()
    if event.ctrl:
        options.autorefresh = not options.autorefresh
    else:
        category.refresh(context, True)
    return {'FINISHED'}

@LeftRightPanel(idname="VIEW3D_PT_batch_{}s".format(category_name), context="objectmode", space_type='VIEW_3D', category="Batch", label="Batch {}s".format(Category_Name))
def Panel_Category(self, context):
    layout = NestedLayout(self.layout)
    category = get_category()
    options = get_options()
    
    with layout.row():
        with layout.row(True):
            layout.menu("OBJECT_MT_batch_{}_add".format(category_name), icon='ZOOMIN', text="")
            layout.operator("view3d.pick_{}s".format(category_name), icon='EYEDROPPER', text="")
            layout.operator("object.batch_{}_copy".format(category_name), icon='COPYDOWN', text="")
            layout.operator("object.batch_{}_paste".format(category_name), icon='PASTEDOWN', text="")
        
        icon = ('PREVIEW_RANGE' if options.autorefresh else 'FILE_REFRESH')
        layout.operator("object.batch_{}_refresh".format(category_name), icon=icon, text="")
        
        #icon = ('SCRIPTWIN' if options.synchronized else 'SCRIPTPLUGINS')
        icon = ('SCRIPTPLUGINS' if options.synchronized else 'SCRIPTWIN')
        #icon = ('SOLO_ON' if options.synchronized else 'SOLO_OFF')
        #icon = ('LOCKVIEW_ON' if options.synchronized else 'LOCKVIEW_OFF')
        #icon = ('COLOR_GREEN' if options.synchronized else 'COLOR_BLUE')
        layout.menu("VIEW3D_MT_batch_{}s_options".format(category_name), icon=icon, text="")
    
    category.draw(layout)

addon.External.materials = CategoryPG | -prop()
get_category = (lambda: addon.external.materials)

addon.Preferences.materials = CategoryOptionsPG | prop()
get_options = (lambda: addon.preferences.materials)
