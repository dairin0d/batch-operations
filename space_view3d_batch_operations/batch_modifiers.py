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

#============================================================================#
Category_Name = "Modifier"
CATEGORY_NAME = Category_Name.upper()
category_name = Category_Name.lower()
category_icon = 'MODIFIER'

class BatchOperations:
    clipbuffer = None
    
    _all_types_enum = BlRna.serialize_value(
        bpy.ops.object.modifier_add.get_rna().
        bl_rna.properties["type"].enum_items)
    
    @classmethod
    def clean_name(cls, md):
        return md.bl_rna.name.replace(" Modifier", "")
    
    @classmethod
    def iter_names(cls, obj):
        for md in obj.modifiers: yield cls.clean_name(md)
    
    @classmethod
    def enum_all(cls):
        yield from cls._all_types_enum
    
    @classmethod
    def icon_kwargs(cls, idname):
        return {"icon": BlEnums.modifier_icons.get(idname, category_icon)}
    
    @classmethod
    def iterate(cls, search_in, context=None):
        for obj in cls.iterate_objects(search_in, context):
            yield from obj.modifiers
    
    @classmethod
    def iterate_objects(cls, search_in, context=None):
        if context is None: context = bpy.context
        obj_types = BlEnums.object_types_with_modifiers
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
        return {n for n in idnames.split(idnames_separator)}
    
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
    def copy(cls, active_obj, exclude=()):
        if not active_obj:
            cls.clipbuffer = []
        else:
            cls.clipbuffer = [attrs_to_dict(md) for md in active_obj.modifiers if md.type not in exclude]
    
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
@addon.Menu(idname="OBJECT_MT_batch_{}_add".format(category_name), description=
"Add {}(s)".format(Category_Name))
def Menu_Add(self, context):
    layout = NestedLayout(self.layout)
    for item in CategoryPG.remaining_items:
        idname = item[0]
        name = item[1]
        icon_kw = BatchOperations.icon_kwargs(idname)
        op = layout.operator("object.batch_{}_add".format(category_name), text=name, **icon_kw)
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
def Operator_Add(self, context, event, idnames=""):
    category = get_category()
    options = get_options()
    bpy.ops.ed.undo_push(message="Batch Add {}s".format(Category_Name))
    BatchOperations.add(options.iterate_objects(context), idnames)
    category.tag_refresh()
    return {'FINISHED'}

@addon.Operator(idname="object.batch_{}_assign".format(category_name), options={'INTERNAL', 'REGISTER'}, description=
"Click: Assign (+Ctrl: globally); Alt+Click: Apply (+Ctrl: globally); Shift+Click: (De)select row; Shift+Ctrl+Click: Select all objects with this item")
def Operator_Assign(self, context, event, idnames="", index=0):
    category = get_category()
    options = get_options()
    if event.alt:
        bpy.ops.ed.undo_push(message="Batch Apply {}s".format(Category_Name))
        options = category.apply_options
        BatchOperations.apply(options.iterate_objects(context, event.ctrl), context.scene, idnames, options)
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
"Click: Remove (+Ctrl: globally); Alt+Click: Purge (+Ctrl: even those with use_fake_users)")
def Operator_Remove(self, context, event, idnames=""):
    category = get_category()
    options = get_options()
    if event.alt:
        bpy.ops.ed.undo_push(message="Purge {}s".format(Category_Name))
        BatchOperations.purge(event.ctrl)
    else:
        bpy.ops.ed.undo_push(message="Batch Remove {}s".format(Category_Name))
        BatchOperations.remove(options.iterate_objects(context, event.ctrl), idnames)
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
        prop_kwargs["update"] = make_update(name)
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
    def collect_info(cls, items):
        infos = {}
        for item in items:
            cls.extract_info(infos, item, "")
            cls.extract_info(infos, item)
        return infos
    
    @classmethod
    def extract_info(cls, infos, item, idname=None):
        if idname is None: idname = getattr(item, cls.idname_attr)
        
        info = infos.get(idname)
        if info is None:
            name = (BatchOperations.clean_name(item) if idname else "")
            infos[idname] = info = cls(idname, name) # double assign
        
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

add_aggregate_attrs(AggregateInfo, CategoryItemPG, "type", [
    #("show_expanded", dict(tooltip="Are modifier(s) expanded in the UI", icons=('TRIA_DOWN', 'TRIA_RIGHT'))),
    ("show_render", dict(tooltip="Use modifier(s) during render", icons='SCENE')),
    ("show_viewport", dict(tooltip="Display modifier(s) in viewport", icons='VISIBLE_IPO_ON')),
    ("show_in_editmode", dict(tooltip="Display modifier(s) in edit mode", icons='EDITMODE_HLT')),
    ("show_on_cage", dict(tooltip="Adjust edit cage to modifier(s) result", icons='MESH_DATA')),
    ("use_apply_on_spline", dict(tooltip="Apply modifier(s) to splines' points rather than the filled curve/surface", icons='SURFACE_DATA')),
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
    
    paste_mode_icons = {'SET':'ROTACTIVE', 'OR':'ROTATECOLLECTION', 'AND':'ROTATECENTER'}
    paste_mode = 'SET' | prop("Paste mode", update=update, items=[
        ('SET', "Replace", "Replace objects' {}(s) with the copied ones".format(category_name), 'ROTACTIVE'),
        ('OR', "Add", "Add copied {}(s) to objects".format(category_name), 'ROTATECOLLECTION'),
        ('AND', "Filter", "Remove objects' {}(s) that are not among the copied".format(category_name), 'ROTATECENTER'),
    ])
    
    search_in_icons = {'SELECTION':'RESTRICT_SELECT_OFF', 'VISIBLE':'RESTRICT_VIEW_OFF',
        'LAYER':'RENDERLAYERS', 'SCENE':'SCENE_DATA', 'FILE':'FILE_BLEND'}
    search_in = 'SELECTION' | prop("Filter", update=update, items=[
        ('SELECTION', "Selection", "Display {}(s) of the selection".format(category_name), 'RESTRICT_SELECT_OFF'),
        ('VISIBLE', "Visible", "Display {}(s) of the visible objects".format(category_name), 'RESTRICT_VIEW_OFF'),
        ('LAYER', "Layer", "Display {}(s) of the objects in the visible layers".format(category_name), 'RENDERLAYERS'),
        ('SCENE', "Scene", "Display {}(s) of the objects in the current scene".format(category_name), 'SCENE_DATA'),
        ('FILE', "File", "Display all {}(s) in this file".format(category_name), 'FILE_BLEND'),
    ])
    
    apply_options = {'CONVERT_TO_MESH', 'MAKE_SINGLE_USER', 'REMOVE_DISABLED'} | prop("Apply Modifier options", update=update, items=[
        ('CONVERT_TO_MESH', "Convert to mesh", "Convert to mesh", 'OUTLINER_OB_MESH'),
        ('MAKE_SINGLE_USER', "Make single user", "Make single user", 'UNLINKED'),
        ('REMOVE_DISABLED', "Remove disabled", "Remove disabled", 'GHOST_DISABLED'),
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
        
        infos = AggregateInfo.collect_info(options.iterate(context))
        
        curr_idnames = set(infos.keys())
        if curr_idnames != cls.prev_idnames:
            # remember excluded state while idnames are the same
            cls.excluded.clear()
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
        #if processing_time > 0.05: options.autorefresh = False
        
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
                    
                    #icon_kw = BatchOperations.icon_kwargs(idname)
                    text = "{} ({})".format(item.name or "(All)", item.count)
                    op = layout.operator("object.batch_{}_assign".format(category_name), text=text)
                    op.idnames = item.idname or all_idnames
                    op.index = item.sort_id
                    
                    op = layout.operator("object.batch_{}_remove".format(category_name), text="", icon='X')
                    op.idnames = item.idname or all_idnames

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

@addon.Menu(idname="VIEW3D_MT_batch_{}s_options_apply_options".format(category_name), label="Apply Modifier")
def Menu_ApplyModifierOptions(self, context):
    """Apply Modifier options"""
    layout = NestedLayout(self.layout)
    options = get_options()
    layout.props_enum(options, "apply_options")

@addon.Menu(idname="VIEW3D_MT_batch_{}s_options".format(category_name), label="Options")
def Menu_Options(self, context):
    """Options"""
    layout = NestedLayout(self.layout)
    options = get_options()
    with layout.column():
        layout.prop(options, "synchronized")
        layout.menu("VIEW3D_MT_batch_{}s_options_paste_mode".format(category_name), icon='PASTEDOWN')
        layout.menu("VIEW3D_MT_batch_{}s_options_search_in".format(category_name), icon='VIEWZOOM')
        layout.menu("VIEW3D_MT_batch_{}s_options_apply_options".format(category_name), icon=category_icon)

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
class Panel_Category:
    def draw_header(self, context):
        layout = NestedLayout(self.layout)
        category = get_category()
        options = get_options()
        with layout.row(True):
            icon = CategoryOptionsPG.search_in_icons[options.search_in]
            layout.prop_menu_enum(options, "search_in", text="", icon=icon)
            icon = CategoryOptionsPG.paste_mode_icons[options.paste_mode]
            layout.prop_menu_enum(options, "paste_mode", text="", icon=icon)
    
    def draw(self, context):
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
            
            icon = ('SCRIPTPLUGINS' if options.synchronized else 'SCRIPTWIN')
            layout.menu("VIEW3D_MT_batch_{}s_options".format(category_name), icon=icon, text="")
        
        category.draw(layout)

addon.External.modifiers = CategoryPG | -prop()
get_category = (lambda: addon.external.modifiers)

addon.Preferences.modifiers = CategoryOptionsPG | prop()
get_options = (lambda: addon.preferences.modifiers)
