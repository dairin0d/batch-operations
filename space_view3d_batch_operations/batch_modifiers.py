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

# =============================== MODIFIERS ================================ #
#============================================================================#
modifier_icons = {
    'MESH_CACHE':'MOD_MESHDEFORM',
    'UV_PROJECT':'MOD_UVPROJECT',
    'UV_WARP':'MOD_UVPROJECT',
    'VERTEX_WEIGHT_EDIT':'MOD_VERTEX_WEIGHT',
    'VERTEX_WEIGHT_MIX':'MOD_VERTEX_WEIGHT',
    'VERTEX_WEIGHT_PROXIMITY':'MOD_VERTEX_WEIGHT',
    'ARRAY':'MOD_ARRAY',
    'BEVEL':'MOD_BEVEL',
    'BOOLEAN':'MOD_BOOLEAN',
    'BUILD':'MOD_BUILD',
    'DECIMATE':'MOD_DECIM',
    'EDGE_SPLIT':'MOD_EDGESPLIT',
    'MASK':'MOD_MASK',
    'MIRROR':'MOD_MIRROR',
    'MULTIRES':'MOD_MULTIRES',
    'REMESH':'MOD_REMESH',
    'SCREW':'MOD_SCREW',
    'SKIN':'MOD_SKIN',
    'SOLIDIFY':'MOD_SOLIDIFY',
    'SUBSURF':'MOD_SUBSURF',
    'TRIANGULATE':'MOD_TRIANGULATE',
    'WIREFRAME':'MOD_WIREFRAME',
    'ARMATURE':'MOD_ARMATURE',
    'CAST':'MOD_CAST',
    'CURVE':'MOD_CURVE',
    'DISPLACE':'MOD_DISPLACE',
    'HOOK':'HOOK',
    'LAPLACIANSMOOTH':'MOD_SMOOTH',
    'LAPLACIANDEFORM':'MOD_MESHDEFORM',
    'LATTICE':'MOD_LATTICE',
    'MESH_DEFORM':'MOD_MESHDEFORM',
    'SHRINKWRAP':'MOD_SHRINKWRAP',
    'SIMPLE_DEFORM':'MOD_SIMPLEDEFORM',
    'SMOOTH':'MOD_SMOOTH',
    'WARP':'MOD_WARP',
    'WAVE':'MOD_WAVE',
    'CLOTH':'MOD_CLOTH',
    'COLLISION':'MOD_PHYSICS',
    'DYNAMIC_PAINT':'MOD_DYNAMICPAINT',
    'EXPLODE':'MOD_EXPLODE',
    'FLUID_SIMULATION':'MOD_FLUIDSIM',
    'OCEAN':'MOD_OCEAN',
    'PARTICLE_INSTANCE':'MOD_PARTICLES',
    'PARTICLE_SYSTEM':'MOD_PARTICLES',
    'SMOKE':'MOD_SMOKE',
    'SOFT_BODY':'MOD_SOFT',
    'SURFACE':'MODIFIER',
}

class BatchModifiers:
    clipbuffer = None
    
    @classmethod
    def clean_name(cls, md):
        return md.bl_rna.name.replace(" Modifier", "")
    
    @classmethod
    def iterate(cls, category, context=None):
        for obj in cls.iterate_objects(category, context):
            yield from obj.modifiers
    
    @classmethod
    def iterate_objects(cls, category, context=None):
        if context is None: context = bpy.context
        obj_types = BlEnums.object_types_with_modifiers
        scene = context.scene
        if category == 'SELECTION':
            for obj in context.selected_objects:
                if (obj.type in obj_types):
                    yield obj
        elif category == 'VISIBLE':
            for obj in scene.objects:
                if (obj.type in obj_types) and is_visible(obj, scene):
                    yield obj
        elif category == 'LAYER':
            for obj in scene.objects:
                if (obj.type in obj_types) and has_common_layers(obj, scene):
                    yield obj
        elif category == 'SCENE':
            for obj in scene.objects:
                if (obj.type in obj_types):
                    yield obj
        elif category == 'FILE':
            for obj in bpy.data.objects:
                if (obj.type in obj_types):
                    yield obj
    
    @classmethod
    def split_idnames(cls, idnames):
        return {n.strip() for n in idnames.split(idnames_separator)}
    
    @classmethod
    def set_attr(cls, name, value, objects, idnames):
        idnames = cls.split_idnames(idnames)
        for obj in objects:
            for md in obj.modifiers:
                if md.type in idnames:
                    setattr(md, name, value)
    
    @classmethod
    def clear(cls, objects):
        for obj in objects:
            obj.modifiers.clear()
    
    @classmethod
    def add(cls, objects, idnames):
        idnames = cls.split_idnames(idnames)
        for obj in objects:
            for idname in idnames:
                md = obj.modifiers.new(idname.capitalize(), idname)
    
    @classmethod
    def assign(cls, active_obj, objects, idnames):
        idnames = cls.split_idnames(idnames)
        
        src = {}
        if active_obj:
            for md in active_obj.modifiers:
                if md.type in idnames:
                    src[md.type] = md
        
        for obj in objects:
            missing_idnames = set(idnames)
            for md in obj.modifiers:
                if md.type in idnames:
                    missing_idnames.discard(md.type)
                    src_item = src.get(md.type)
                    if src_item: copyattrs(src_item, md)
            
            for idname in missing_idnames:
                md = obj.modifiers.new(idname.capitalize(), idname)
                src_item = src.get(idname)
                if src_item: copyattrs(src_item, md)
    
    @classmethod
    def apply(cls, objects, scene, idnames, options=()):
        idnames = cls.split_idnames(idnames)
        
        active_obj = scene.objects.active
        
        covert_to_mesh = ('CONVERT_TO_MESH' in options)
        make_single_user = ('MAKE_SINGLE_USER' in options)
        remove_disabled = ('REMOVE_DISABLED' in options)
        
        for obj in objects:
            scene.objects.active = obj
            
            if not obj.modifiers: continue
            
            if (obj.type != 'MESH') and covert_to_mesh:
                # "Error: Cannot apply constructive modifiers on curve"
                if obj.data.users > 1: obj.data = obj.data.copy() # don't affect other objects
                bpy.ops.object.convert(target='MESH')
            elif make_single_user:
                # "Error: Modifiers cannot be applied to multi-user data"
                if obj.data.users > 1: obj.data = obj.data.copy() # don't affect other objects
            
            for md in tuple(obj.modifiers):
                if md.type not in idnames: continue
                
                is_disabled = False
                try:
                    bpy.ops.object.modifier_apply(modifier=md.name) # not type or idname!
                except RuntimeError as exc:
                    #print(repr(exc))
                    exc_msg = exc.args[0].lower()
                    # "Error: Modifier is disabled, skipping apply"
                    is_disabled = ("disab" in exc_msg) or ("skip" in exc_msg)
                
                if is_disabled and remove_disabled:
                    obj.modifiers.remove(md)
        
        scene.objects.active = active_obj
    
    @classmethod
    def remove(cls, objects, idnames):
        idnames = cls.split_idnames(idnames)
        for obj in objects:
            for md in tuple(obj.modifiers):
                if md.type in idnames:
                    obj.modifiers.remove(md)
    
    @classmethod
    def select(cls, scene, idnames):
        idnames = cls.split_idnames(idnames)
        for obj in scene.objects:
            obj.select = any((md.type in idnames) for md in obj.modifiers)
    
    @classmethod
    def purge(cls, even_with_fake_users):
        pass # not applicable to modifiers (they are not ID datablocks)
    
    @classmethod
    def copy(cls, active_obj):
        if not active_obj:
            cls.clipbuffer = []
        else:
            cls.clipbuffer = [attrs_to_dict(md) for md in active_obj.modifiers]
    
    @classmethod
    def paste(cls, objects, paste_mode):
        md_infos = cls.clipbuffer
        if md_infos is None: return
        if paste_mode != 'AND':
            for obj in objects:
                if paste_mode == 'SET': obj.modifiers.clear()
                for md_info in md_infos:
                    md = obj.modifiers.new(md_info["name"], md_info["type"])
                    dict_to_attrs(md, md_info)
        else:
            idnames = {md_info["type"] for md_info in md_infos}
            for obj in objects:
                for md in tuple(obj.modifiers):
                    if md.type not in idnames:
                        obj.modifiers.remove(md)

#============================================================================#
@addon.Menu(idname="OBJECT_MT_batch_modifier_add")
def OBJECT_MT_batch_modifier_add(self, context):
    """Add modifier(s) to the selected objects"""
    layout = NestedLayout(self.layout)
    for item in ModifiersPG.remaining_items:
        idname = item[0]
        name = item[1]
        icon = modifier_icons.get(idname, 'MODIFIER')
        op = layout.operator("object.batch_modifier_add", text=name, icon=icon)
        op.modifier = idname

@addon.Operator(idname="view3d.pick_modifiers")
class Pick_Modifiers(Pick_Base):
    """Pick modifier(s) from the object under mouse"""
    
    @classmethod
    def poll(cls, context):
        return (context.mode == 'OBJECT')
    
    def obj_to_info(self, obj):
        txt = ", ".join(BatchModifiers.clean_name(md) for md in obj.modifiers)
        return (txt or "<No modifiers>")
    
    def on_confirm(self, context, obj):
        batch_modifiers = addon.external.modifiers
        bpy.ops.ed.undo_push(message="Pick Modifiers")
        BatchModifiers.copy(obj)
        self.report({'INFO'}, "Modifiers copied")
        BatchModifiers.paste(batch_modifiers.iterate_objects(context), batch_modifiers.paste_mode)

# NOTE: only when 'REGISTER' is in bl_options and {'FINISHED'} is returned,
# the operator will be recorded in wm.operators and info reports

@addon.Operator(idname="object.batch_modifier_copy", options={'INTERNAL'})
def Batch_Copy_Modifiers(self, context, event):
    """Click: Copy"""
    if not context.object: return {'CANCELLED'}
    BatchModifiers.copy(context.object)
    self.report({'INFO'}, "Modifiers copied")
    return {'FINISHED'}

@addon.Operator(idname="object.batch_modifier_paste", options={'INTERNAL', 'REGISTER'})
def Batch_Paste_Modifiers(self, context, event):
    """Click: Paste"""
    batch_modifiers = addon.external.modifiers
    bpy.ops.ed.undo_push(message="Batch Paste Modifiers")
    BatchModifiers.paste(batch_modifiers.iterate_objects(context), batch_modifiers.paste_mode)
    tag_redraw()
    return {'FINISHED'}

@addon.Operator(idname="object.batch_modifier_add", options={'INTERNAL', 'REGISTER'})
def Batch_Add_Modifiers(self, context, event, modifier=""):
    """Click: Add"""
    batch_modifiers = addon.external.modifiers
    bpy.ops.ed.undo_push(message="Batch Add Modifiers")
    BatchModifiers.add(batch_modifiers.iterate_objects(context), modifier)
    tag_redraw()
    return {'FINISHED'}

@addon.Operator(idname="object.batch_modifier_assign", options={'INTERNAL', 'REGISTER'})
def Batch_Assign_Modifiers(self, context, event, modifier="", index=0):
    """Click: Assign (+Ctrl: globally);
    Alt+Click: Apply (+Ctrl: globally);
    Shift+Click: (De)select row;
    Shift+Ctrl+Click: Select all objects with this item"""
    batch_modifiers = addon.external.modifiers
    if event.alt:
        bpy.ops.ed.undo_push(message="Batch Apply Modifiers")
        options = batch_modifiers.apply_options
        BatchModifiers.apply(batch_modifiers.iterate_objects(context, event.ctrl), context.scene, modifier, options)
    elif event.shift:
        if event.ctrl:
            bpy.ops.ed.undo_push(message="Batch Select Modifiers")
            BatchModifiers.select(context.scene, modifier)
        else:
            batch_modifiers = addon.external.modifiers
            item = batch_modifiers.items[index]
            if item.idname in ModifiersPG.excluded:
                ModifiersPG.excluded.discard(item.idname)
            else:
                ModifiersPG.excluded.add(item.idname)
            tag_redraw()
            return {'PASS_THROUGH'}
    else:
        bpy.ops.ed.undo_push(message="Batch Assign Modifiers")
        BatchModifiers.assign(context.object, batch_modifiers.iterate_objects(context, event.ctrl), modifier)
    tag_redraw()
    return {'FINISHED'}

@addon.Operator(idname="object.batch_modifier_remove", options={'INTERNAL', 'REGISTER'})
def Batch_Remove_Modifiers(self, context, event, modifier=""):
    """Click: Remove (+Ctrl: globally);
    Alt+Click: Purge (+Ctrl: even those with use_fake_users)"""
    batch_modifiers = addon.external.modifiers
    if event.alt:
        bpy.ops.ed.undo_push(message="Purge Modifiers")
        BatchModifiers.purge(event.ctrl)
    else:
        bpy.ops.ed.undo_push(message="Batch Remove Modifiers")
        BatchModifiers.remove(batch_modifiers.iterate_objects(context, event.ctrl), modifier)
    tag_redraw()
    return {'FINISHED'}

"""
TODO: something like this for add/pick/copy/paste?

* NAME button
    * Click: assign/ensure locally (in selection)
    * Ctrl+Click: assign/ensure globally (in file)
    * Alt+Click: apply / rename (for all objects in selection)
    * Alt+Ctrl+Click: apply globally (for all objects in scene? in file?)
    * Shift+Click: (de)select row (displayed as greyed-out)
    * Shift+Ctrl+Click: select all objects with this modifier/material/goup/etc.
* REMOVE button
    * Click: remove locally (in selection)
    * Ctrl+Click: remove globally (in file)
    * Alt+Click: (only for All): purge
    * Alt+Ctrl+Click: (only for All): purge even use_fake_users
"""

class ModifierAggregateInfo:
    def __init__(self, type, name, identifier):
        self.type = type
        self.name = name
        self.identifier = identifier
        self.count = 0
        self.show_expanded = Aggregator('NUMBER', {"same", "mean"}, int)
        self.show_render = Aggregator('NUMBER', {"same", "mean"}, int)
        self.show_viewport = Aggregator('NUMBER', {"same", "mean"}, int)
        self.show_in_editmode = Aggregator('NUMBER', {"same", "mean"}, int)
        self.show_on_cage = Aggregator('NUMBER', {"same", "mean"}, int)
        self.use_apply_on_spline = Aggregator('NUMBER', {"same", "mean"}, int)
    
    def fill_item(self, item):
        item.name = self.name
        item.idname = self.type
        item.count = self.count
        self.fill_aggr(item, "show_expanded", "mean", round_to_bool)
        self.fill_aggr(item, "show_render", "mean", round_to_bool)
        self.fill_aggr(item, "show_viewport", "mean", round_to_bool)
        self.fill_aggr(item, "show_in_editmode", "mean", round_to_bool)
        self.fill_aggr(item, "show_on_cage", "mean", round_to_bool)
        self.fill_aggr(item, "use_apply_on_spline", "mean", round_to_bool)
        item.user_editable = True
    
    def fill_aggr(self, item, name, query, convert=None):
        aggr = getattr(self, name)
        value = getattr(aggr, query)
        if convert is not None: value = convert(value)
        setattr(item, name, value)
        item[name+":same"] = aggr.same
    
    @classmethod
    def collect_info(cls, modifiers):
        infos = {}
        for md in modifiers:
            cls.extract_info(infos, md, "", "", "")
            cls.extract_info(infos, md)
        return infos
    
    @classmethod
    def extract_info(cls, infos, md, md_type=None, name=None, identifier=None):
        if md_type is None: md_type = md.type
        
        info = infos.get(md_type)
        
        if info is None:
            if name is None: name = BatchModifiers.clean_name(md)
            if identifier is None: identifier = md.bl_rna.identifier
            
            info = cls(md_type, name, identifier)
            infos[md_type] = info
        
        info.count += 1
        info.show_expanded.add(md.show_expanded)
        info.show_render.add(md.show_render)
        info.show_viewport.add(md.show_viewport)
        info.show_in_editmode.add(md.show_in_editmode)
        info.show_on_cage.add(md.show_on_cage)
        info.use_apply_on_spline.add(md.use_apply_on_spline)

@addon.PropertyGroup
class ModifierPG:
    sort_id = 0 | prop()
    user_editable = False | prop()
    count = 0 | prop()
    idname = "" | prop()
    
    def gen_show_update(name):
        def update(self, context):
            if not self.user_editable: return
            batch_modifiers = addon.external.modifiers
            message = self.bl_rna.properties[name].description
            value = getattr(self, name)
            bpy.ops.ed.undo_push(message=message)
            idnames = self.idname or batch_modifiers.all_idnames
            BatchModifiers.set_attr(name, value, batch_modifiers.iterate_objects(context), idnames)
        return update
    
    show_expanded = True | prop("Are modifier(s) expanded in the UI", update=gen_show_update("show_expanded"))
    show_render = True | prop("Use modifier(s) during render", update=gen_show_update("show_render"))
    show_viewport = True | prop("Display modifier(s) in viewport", update=gen_show_update("show_viewport"))
    show_in_editmode = True | prop("Display modifier(s) in edit mode", update=gen_show_update("show_in_editmode"))
    show_on_cage = True | prop("Adjust edit cage to modifier(s) result", update=gen_show_update("show_on_cage"))
    use_apply_on_spline = True | prop("Apply modifier(s) to splines' points rather than the filled curve/surface", update=gen_show_update("use_apply_on_spline"))

@addon.PropertyGroup
class ModifiersPG:
    all_types_enum = BlRna.serialize_value(bpy.ops.object.
        modifier_add.get_rna().bl_rna.
        properties["type"].enum_items)
    
    prev_idnames = set()
    excluded = set()
    
    all_idnames = property(lambda self: idnames_separator.join(
        item.idname for item in self.items
        if item.idname and (item.idname not in ModifiersPG.excluded)))
    
    items = [ModifierPG] | prop()
    
    remaining_items = []
    
    paste_mode = 'SET' | prop("Copy/Paste mode", items=[
        ('SET', "Replace", "Replace", 'ROTACTIVE'),
        ('OR', "Add", "Union", 'ROTATECOLLECTION'),
        ('AND', "Filter", "Intersection", 'ROTATECENTER'),
    ])
    show_for = 'SELECTION' | prop("Show summary for", items=[
        ('SELECTION', "Selection", "Selection", 'RESTRICT_SELECT_OFF'), # EDIT OBJECT_DATA UV_SYNC_SELECT
        ('VISIBLE', "Visible", "Visible", 'RESTRICT_VIEW_OFF'),
        ('LAYER', "Layer", "Layer", 'RENDERLAYERS'),
        ('SCENE', "Scene", "Scene", 'SCENE_DATA'),
        ('FILE', "File", "File", 'FILE_BLEND'),
        #('DATA', "Data", "Data", 'BLENDER'),
    ])
    apply_options = {'CONVERT_TO_MESH', 'MAKE_SINGLE_USER', 'REMOVE_DISABLED'} | prop("Apply Modifier options", items=[
        ('CONVERT_TO_MESH', "Convert to mesh", "Convert to mesh", 'OUTLINER_OB_MESH'),
        ('MAKE_SINGLE_USER', "Make single user", "Make single user", 'UNLINKED'), # COPY_ID UNLINKED
        ('REMOVE_DISABLED', "Remove disabled", "Remove disabled", 'GHOST_DISABLED'),
    ])
    
    def iterate(self, context=None, globally=False):
        category = ('FILE' if globally else self.show_for)
        return BatchModifiers.iterate(category, context)
    def iterate_objects(self, context=None, globally=False):
        category = ('FILE' if globally else self.show_for)
        return BatchModifiers.iterate_objects(category, context)
    
    def refresh(self, context):
        infos = ModifierAggregateInfo.collect_info(md for md in self.iterate(context))
        
        curr_idnames = set(infos.keys())
        if curr_idnames != ModifiersPG.prev_idnames:
            # remember excluded state while idnames are the same
            ModifiersPG.excluded.clear()
        ModifiersPG.prev_idnames = curr_idnames
        
        ModifiersPG.remaining_items = [enum_item
            for enum_item in ModifiersPG.all_types_enum
            if enum_item[0] not in curr_idnames]
        ModifiersPG.remaining_items.sort(key=lambda item:item[1])
        
        self.items.clear()
        for i, key in enumerate(sorted(infos.keys())):
            item = self.items.add()
            item.sort_id = i
            infos[key].fill_item(item)
    
    def draw_toggle(self, layout, item, name, icon):
        with layout.row(True)(alert=not item[name+":same"]):
            layout.prop(item, name, icon=icon, text="", toggle=True)
    
    def draw(self, layout):
        if not self.items: return
        
        all_idnames = self.all_idnames
        
        with layout.column(True):
            for item in self.items:
                with layout.row(True)(active=(item.idname not in ModifiersPG.excluded)):
                    #icon = ('TRIA_DOWN' if item.show_expanded[0] else 'TRIA_RIGHT')
                    #self.draw_toggle(layout, item, "show_expanded", icon)
                    self.draw_toggle(layout, item, "show_render", 'SCENE')
                    self.draw_toggle(layout, item, "show_viewport", 'VISIBLE_IPO_ON')
                    self.draw_toggle(layout, item, "show_in_editmode", 'EDITMODE_HLT')
                    self.draw_toggle(layout, item, "show_on_cage", 'MESH_DATA')
                    self.draw_toggle(layout, item, "use_apply_on_spline", 'SURFACE_DATA')
                    
                    icon = modifier_icons.get(item.idname, 'MODIFIER')
                    #op = layout.operator("object.batch_modifier_ensure", text="", icon=icon)
                    #op.modifier = item.idname or all_idnames
                    
                    text = "{} ({})".format(item.name or "(All)", item.count)
                    op = layout.operator("object.batch_modifier_assign", text=text)
                    op.modifier = item.idname or all_idnames
                    op.index = item.sort_id
                    
                    op = layout.operator("object.batch_modifier_remove", text="", icon='X')
                    op.modifier = item.idname or all_idnames

@addon.Menu
class VIEW3D_MT_batch_modifiers_options_paste_mode:
    bl_label = "Copy/Paste mode"
    bl_description = "Copy/Paste mode"
    def draw(self, context):
        layout = NestedLayout(self.layout)
        batch_modifiers = addon.external.modifiers
        layout.props_enum(batch_modifiers, "paste_mode")
        #layout.prop(batch_modifiers, "paste_mode", expand=True)

@addon.Menu
class VIEW3D_MT_batch_modifiers_options_show_for:
    bl_label = "Search in"
    bl_description = "Search in"
    def draw(self, context):
        layout = NestedLayout(self.layout)
        batch_modifiers = addon.external.modifiers
        layout.props_enum(batch_modifiers, "show_for")
        #layout.prop(batch_modifiers, "show_for", expand=True)

@addon.Menu
class VIEW3D_MT_batch_modifiers_options_apply_options:
    bl_label = "Apply Modifier"
    bl_description = "Apply Modifier options"
    def draw(self, context):
        layout = NestedLayout(self.layout)
        batch_modifiers = addon.external.modifiers
        layout.props_enum(batch_modifiers, "apply_options")
        #layout.prop(batch_modifiers, "apply_options", expand=True)

@addon.Menu
class VIEW3D_MT_batch_modifiers_options:
    bl_label = "Options"
    bl_description = "Options"
    def draw(self, context):
        layout = NestedLayout(self.layout)
        with layout.column():
            layout.menu("VIEW3D_MT_batch_modifiers_options_paste_mode", icon='PASTEDOWN')
            layout.menu("VIEW3D_MT_batch_modifiers_options_show_for", icon='VIEWZOOM')
            layout.menu("VIEW3D_MT_batch_modifiers_options_apply_options", icon='MODIFIER')

@LeftRightPanel
class VIEW3D_PT_batch_modifiers:
    bl_category = "Batch"
    bl_context = "objectmode"
    bl_label = "Batch Modifiers"
    bl_space_type = 'VIEW_3D'
    
    def draw(self, context):
        layout = NestedLayout(self.layout)
        batch_modifiers = addon.external.modifiers
        
        with layout.row():
            with layout.row(True):
                layout.menu("OBJECT_MT_batch_modifier_add", icon='ZOOMIN', text="")
                layout.operator("view3d.pick_modifiers", icon='EYEDROPPER', text="")
                layout.operator("object.batch_modifier_copy", icon='COPYDOWN', text="")
                layout.operator("object.batch_modifier_paste", icon='PASTEDOWN', text="")
            layout.menu("VIEW3D_MT_batch_modifiers_options", icon='SCRIPTPLUGINS', text="")
        
        batch_modifiers.draw(layout)

addon.External.modifiers = ModifiersPG | -prop()
