# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
import shutil

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import showcase, theme_tune

THEME_NAME = "Tomatactics"
TUNE_DEFAULTS = dict(
    theme_brightness=1.0, theme_saturation=1.0, theme_hue=0.0, theme_opaque=True,
    theme_gradient=True, theme_gradient_strength=1.0, theme_rounded=True,
)

# Font styles Blender exposes, with their native values: shadow type, offset, alpha, gray value, weight, size.
TEXT_STYLES = (("widget", "Widget Text"), ("panel_title", "Panel Titles"), ("tooltip", "Tooltips"))
TEXT_NATIVE = {
    "widget": dict(shadow='1', shadow_offset_x=0, shadow_offset_y=-1, shadow_alpha=0.5, shadow_value=0.0,
                   character_weight=400, points=11.0),
    "panel_title": dict(shadow='3', shadow_offset_x=0, shadow_offset_y=-1, shadow_alpha=0.5, shadow_value=0.0,
                        character_weight=400, points=11.0),
    "tooltip": dict(shadow='1', shadow_offset_x=0, shadow_offset_y=-1, shadow_alpha=0.5, shadow_value=0.0,
                    character_weight=400, points=11.0),
}
SHADOW_ITEMS = [
    ('0', "None", "No shadow"),
    ('1', "Shadow", "Sharp drop shadow"),
    ('3', "Blur", "Blurred shadow"),
    ('5', "Soft Blur", "Wider blurred shadow"),
    ('6', "Outline", "Outline around every character"),
]
for _style, _label in TEXT_STYLES:
    for _field, _value in TEXT_NATIVE[_style].items():
        TUNE_DEFAULTS["text_%s_%s" % (_style, _field)] = _value

THEME_MENU = "USERPREF_MT_interface_theme_presets"
VIEWPORT_FILE_TYPE = "tomatactics.viewport_background"

BUILTIN_VIEWPORT_PRESETS = {
    "Blue Vignette": dict(background_type="RADIAL", high="#3166bb", low="#000000"),
    "Blender Default": dict(background_type="SINGLE_COLOR", high="#3d3d3d", low="#303030"),
}

# Set while values are written programmatically, so update callbacks neither reload presets nor re-apply.
_loading = False


def _hex(c):
    return "#" + "".join("%02x" % round(max(0.0, min(1.0, v)) * 255) for v in c[:3])


def _rgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) / 255 for i in (0, 2, 4))


# -----------------------------------------------------------------------------
# Theme


def tuned_theme_path():
    return os.path.join(bpy.utils.extension_path_user(__package__, create=True),
                        THEME_NAME.replace(" ", "_") + ".xml")


def user_theme_dir():
    return bpy.utils.user_resource('SCRIPTS', path=os.path.join("presets", "interface_theme"), create=True)


def is_tuned_theme_active(context):
    current = os.path.normcase(os.path.abspath(context.preferences.themes[0].filepath or ""))
    return current == os.path.normcase(os.path.abspath(tuned_theme_path()))


def apply_tuned_theme(context):
    """Rebuild the theme as Blender's default plus the current tuning."""
    prefs = get_prefs(context)
    if prefs is None:
        return
    _keep_viewport_background(context, bpy.ops.preferences.reset_default_theme)
    theme = context.preferences.themes[0]
    theme_tune.apply(
        theme, brightness=prefs.theme_brightness, saturation=prefs.theme_saturation,
        hue_shift=prefs.theme_hue, opaque=prefs.theme_opaque, gradient=prefs.theme_gradient,
        gradient_strength=prefs.theme_gradient_strength, rounded=prefs.theme_rounded,
    )
    # Marks the theme as ours for the active checkmark; the file itself is only written on export.
    theme.filepath = tuned_theme_path()
    apply_text_styles(context, {
        style: {f: getattr(prefs, "text_%s_%s" % (style, f)) for f in TEXT_NATIVE[style]}
        for style, _label in TEXT_STYLES
    })


def apply_text_styles(context, values):
    ui_style = context.preferences.ui_styles[0]
    for style, fields in values.items():
        font = getattr(ui_style, style)
        for field, value in fields.items():
            setattr(font, field, int(value) if field == "shadow" else value)


def write_tuned_theme(context):
    import _rna_xml
    path = tuned_theme_path()
    _rna_xml.xml_file_write(context, path, getattr(bpy.types, THEME_MENU).preset_xml_map)
    return path


def tune_values(prefs):
    return {k: getattr(prefs, k) for k in TUNE_DEFAULTS}


def set_tune_values(prefs, values):
    global _loading
    _loading = True
    try:
        for k, default in TUNE_DEFAULTS.items():
            setattr(prefs, k, values.get(k, default))
    finally:
        _loading = False


def _on_tune_change(self, context):
    if not _loading:
        apply_tuned_theme(context)


def _viewport_gradients(context):
    return context.preferences.themes[0].view_3d.space.gradients


def _keep_viewport_background(context, fn):
    g = _viewport_gradients(context)
    saved = (g.background_type, tuple(g.high_gradient), tuple(g.gradient))
    fn()
    g = _viewport_gradients(context)
    g.background_type, g.high_gradient, g.gradient = saved


class TOMATACTICS_OT_apply_theme(bpy.types.Operator):
    bl_idname = "tomatactics.apply_theme"
    bl_label = "Apply Theme"
    bl_description = "Apply the theme with the current tuning, keeping the viewport background"
    bl_options = {'REGISTER'}

    def execute(self, context):
        apply_tuned_theme(context)
        self.report({'INFO'}, "Applied theme: " + THEME_NAME)
        return {'FINISHED'}


class TOMATACTICS_OT_save_theme(bpy.types.Operator):
    bl_idname = "tomatactics.save_theme"
    bl_label = "Save Theme"
    bl_description = "Keep the current tuning; only saved tuning is restored after restarting Blender"
    bl_options = {'REGISTER'}

    def execute(self, context):
        prefs = get_prefs(context)
        apply_tuned_theme(context)
        write_state(theme=tune_values(prefs))
        self.report({'INFO'}, "Saved theme tuning")
        return {'FINISHED'}


class TOMATACTICS_OT_reset_tuning(bpy.types.Operator):
    bl_idname = "tomatactics.reset_tuning"
    bl_label = "Reset Tuning"
    bl_description = "Return every tuning control to its default"
    bl_options = {'REGISTER'}

    def execute(self, context):
        set_tune_values(get_prefs(context), TUNE_DEFAULTS)
        apply_tuned_theme(context)
        return {'FINISHED'}


class TOMATACTICS_OT_reset_theme(bpy.types.Operator):
    bl_idname = "tomatactics.reset_theme"
    bl_label = "Reset to Blender Default"
    bl_description = "Restore Blender's default interface theme, keeping the viewport background"
    bl_options = {'REGISTER'}

    def execute(self, context):
        _keep_viewport_background(context, bpy.ops.preferences.reset_default_theme)
        context.preferences.themes[0].filepath = ""
        apply_text_styles(context, TEXT_NATIVE)
        write_state(theme=None)
        self.report({'INFO'}, "Restored the default theme")
        return {'FINISHED'}


class TOMATACTICS_OT_install_themes(bpy.types.Operator):
    bl_idname = "tomatactics.install_themes"
    bl_label = "Add to Preferences Theme List"
    bl_description = "Copy the theme with the current tuning into Preferences > Themes"
    bl_options = {'REGISTER'}

    def execute(self, context):
        apply_tuned_theme(context)
        target = user_theme_dir()
        shutil.copy2(write_tuned_theme(context), target)
        self.report({'INFO'}, "Copied %s to %s" % (THEME_NAME, target))
        return {'FINISHED'}


# -----------------------------------------------------------------------------
# Viewport background presets


def preset_dir():
    return bpy.utils.extension_path_user(__package__, path=os.path.join("presets", "viewport"), create=True)


def _state_path():
    return os.path.join(bpy.utils.extension_path_user(__package__, create=True), "state.json")


def read_state():
    try:
        with open(_state_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_state(**changes):
    state = read_state()
    state.update(changes)
    with open(_state_path(), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def user_presets():
    folder = preset_dir()
    return sorted(os.path.splitext(f)[0] for f in os.listdir(folder) if f.lower().endswith(".json"))


def _validate(data):
    if not isinstance(data, dict) or data.get("type") != VIEWPORT_FILE_TYPE:
        raise ValueError("not a Tomatactics viewport preset")
    for k in ("high", "low"):
        _rgb(data[k])
    if data.get("background_type") not in {'SINGLE_COLOR', 'LINEAR', 'RADIAL'}:
        raise ValueError("unknown background type")
    return data


def read_preset(name):
    if name in BUILTIN_VIEWPORT_PRESETS:
        return dict(BUILTIN_VIEWPORT_PRESETS[name], type=VIEWPORT_FILE_TYPE)
    with open(os.path.join(preset_dir(), name + ".json"), encoding="utf-8") as f:
        return _validate(json.load(f))


def write_preset_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def current_values(context):
    g = _viewport_gradients(context)
    return dict(background_type=g.background_type, high=_hex(g.high_gradient), low=_hex(g.gradient),
                type=VIEWPORT_FILE_TYPE)


def load_values(context, data):
    g = _viewport_gradients(context)
    g.background_type = data["background_type"]
    g.high_gradient = _rgb(data["high"])
    g.gradient = _rgb(data["low"])


_enum_cache = []


def _preset_items(self, context):
    global _enum_cache
    # Blender keeps only references to these strings, so the list must outlive the callback.
    items = [(n, n, "Built-in preset", 'LOCKED', i) for i, n in enumerate(BUILTIN_VIEWPORT_PRESETS)]
    offset = len(items)
    items += [(n, n, "Saved preset", 'PRESET', offset + i) for i, n in enumerate(user_presets())]
    _enum_cache = items
    return items


def _on_preset_change(self, context):
    if _loading:
        return
    try:
        load_values(context, read_preset(self.viewport_preset))
    except (OSError, ValueError, KeyError) as ex:
        print("Tomatactics: could not load preset %r: %s" % (self.viewport_preset, ex))


class TomatacticsPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    theme_brightness: FloatProperty(
        name="Brightness", description="Brightness of backgrounds, panels and buttons; text is not affected",
        default=TUNE_DEFAULTS["theme_brightness"], min=0.3, max=1.5, step=1, update=_on_tune_change,
    )
    theme_saturation: FloatProperty(
        name="Saturation", description="Color intensity of the whole interface",
        default=TUNE_DEFAULTS["theme_saturation"], min=0.0, max=2.0, step=1, update=_on_tune_change,
    )
    theme_hue: FloatProperty(
        name="Hue", description="Rotate every interface color around the color wheel, in degrees",
        default=TUNE_DEFAULTS["theme_hue"], min=-180.0, max=180.0, step=100, update=_on_tune_change,
    )
    theme_opaque: BoolProperty(
        name="Opaque", description="Make menus, buttons, panels and headers solid instead of see-through",
        default=TUNE_DEFAULTS["theme_opaque"], update=_on_tune_change,
    )
    theme_gradient: BoolProperty(
        name="Gradient", description="Shade buttons, menus and tabs with a top-to-bottom gradient",
        default=TUNE_DEFAULTS["theme_gradient"], update=_on_tune_change,
    )
    theme_gradient_strength: FloatProperty(
        name="Gradient Strength", description="How strong the button gradient is",
        default=TUNE_DEFAULTS["theme_gradient_strength"], min=0.0, max=2.0, step=1, update=_on_tune_change,
    )
    theme_rounded: BoolProperty(
        name="Rounded", description="Use rounder buttons, menus and panels",
        default=TUNE_DEFAULTS["theme_rounded"], update=_on_tune_change,
    )

    viewport_preset: EnumProperty(
        name="Viewport Preset", description="Load a viewport background preset",
        items=_preset_items, update=_on_preset_change,
    )

    def draw(self, context):
        box = self.layout.box()
        box.label(text="Interface Theme", icon='COLOR')
        theme_on = is_tuned_theme_active(context)
        _quick_row(box, TOMATACTICS_OT_apply_theme.bl_idname, "Set Theme",
                   'CHECKMARK' if theme_on else 'COLOR', theme_on, TOMATACTICS_OT_reset_theme.bl_idname)
        draw_theme(box, context, self)
        box = self.layout.box()
        box.label(text="Viewport Background", icon='WORLD')
        draw_viewport_background(box, context, self)


def _text_props(label):
    return dict(
        shadow=lambda d: EnumProperty(name="Shadow", description="Shadow or outline drawn behind %s" % label.lower(),
                                      items=SHADOW_ITEMS, default=d, update=_on_tune_change),
        shadow_offset_x=lambda d: IntProperty(name="X", description="Horizontal shadow offset in pixels",
                                              default=d, min=-10, max=10, update=_on_tune_change),
        shadow_offset_y=lambda d: IntProperty(name="Y", description="Vertical shadow offset in pixels",
                                              default=d, min=-10, max=10, update=_on_tune_change),
        shadow_alpha=lambda d: FloatProperty(name="Opacity", description="Shadow or outline opacity",
                                             default=d, min=0.0, max=1.0, update=_on_tune_change),
        shadow_value=lambda d: FloatProperty(name="Brightness", description="Shadow or outline gray, from black to white",
                                             default=d, min=0.0, max=1.0, update=_on_tune_change),
        character_weight=lambda d: IntProperty(name="Weight", description="Character weight; 400 is normal, 700 is bold",
                                               default=d, min=100, max=900, step=100, update=_on_tune_change),
        points=lambda d: FloatProperty(name="Size", description="Font size in points",
                                       default=d, min=6.0, max=32.0, update=_on_tune_change),
    )


for _style, _label in TEXT_STYLES:
    for _field, _make in _text_props(_label).items():
        TomatacticsPreferences.__annotations__["text_%s_%s" % (_style, _field)] = _make(TEXT_NATIVE[_style][_field])


def get_prefs(context):
    addon = context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


def select_preset(prefs, name):
    """Select a preset in the dropdown without loading its values."""
    global _loading
    _preset_items(None, None)
    _loading = True
    try:
        prefs.viewport_preset = name
    finally:
        _loading = False


class TOMATACTICS_OT_preset_save(bpy.types.Operator):
    bl_idname = "tomatactics.preset_save"
    bl_label = "Save Preset"
    bl_description = "Save the current viewport background to the selected preset; only saved presets are restored after restarting Blender"
    bl_options = {'REGISTER', 'INTERNAL'}

    name: StringProperty(name="Name", description="Preset name")
    save_as: BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        current = get_prefs(context).viewport_preset
        is_builtin = current in BUILTIN_VIEWPORT_PRESETS
        if not self.save_as and current and not is_builtin:
            self.name = current
            return self.execute(context)
        self.name = "" if is_builtin else current
        return context.window_manager.invoke_props_dialog(self, title="Save Preset As")

    def execute(self, context):
        name = bpy.path.clean_name(self.name.strip()).strip("_")
        if not name:
            self.report({'ERROR'}, "Enter a preset name")
            return {'CANCELLED'}
        if name in BUILTIN_VIEWPORT_PRESETS:
            self.report({'ERROR'}, "'%s' is a built-in preset; choose another name" % name)
            return {'CANCELLED'}
        write_preset_file(os.path.join(preset_dir(), name + ".json"), current_values(context))
        select_preset(get_prefs(context), name)
        write_state(viewport=name)
        self.report({'INFO'}, "Saved preset: " + name)
        return {'FINISHED'}


class TOMATACTICS_OT_preset_delete(bpy.types.Operator):
    bl_idname = "tomatactics.preset_delete"
    bl_label = "Delete Preset"
    bl_description = "Delete the selected saved preset"
    bl_options = {'REGISTER', 'INTERNAL'}

    def invoke(self, context, event):
        name = get_prefs(context).viewport_preset
        return context.window_manager.invoke_confirm(self, event, message="Delete preset '%s'?" % name)

    def execute(self, context):
        prefs = get_prefs(context)
        name = prefs.viewport_preset
        if name in BUILTIN_VIEWPORT_PRESETS:
            self.report({'ERROR'}, "Built-in presets cannot be deleted")
            return {'CANCELLED'}
        os.remove(os.path.join(preset_dir(), name + ".json"))
        if read_state().get("viewport") == name:
            write_state(viewport=None)
        select_preset(prefs, next(iter(BUILTIN_VIEWPORT_PRESETS)))
        self.report({'INFO'}, "Deleted preset: " + name)
        return {'FINISHED'}


class TOMATACTICS_OT_preset_import(bpy.types.Operator, ImportHelper):
    bl_idname = "tomatactics.preset_import"
    bl_label = "Import Preset"
    bl_description = "Import a viewport background preset file and preview it"
    bl_options = {'REGISTER', 'INTERNAL'}

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def execute(self, context):
        try:
            with open(self.filepath, encoding="utf-8") as f:
                data = _validate(json.load(f))
        except (OSError, ValueError, KeyError) as ex:
            self.report({'ERROR'}, "Could not import: %s" % ex)
            return {'CANCELLED'}
        base = bpy.path.clean_name(os.path.splitext(os.path.basename(self.filepath))[0])
        existing = set(user_presets()) | set(BUILTIN_VIEWPORT_PRESETS)
        name, n = base, 2
        while name in existing:
            name, n = "%s_%d" % (base, n), n + 1
        write_preset_file(os.path.join(preset_dir(), name + ".json"), data)
        select_preset(get_prefs(context), name)
        load_values(context, data)
        self.report({'INFO'}, "Imported preset: " + name)
        return {'FINISHED'}


class TOMATACTICS_OT_preset_export(bpy.types.Operator, ExportHelper):
    bl_idname = "tomatactics.preset_export"
    bl_label = "Export Preset"
    bl_description = "Export the current viewport background to a preset file"
    bl_options = {'REGISTER', 'INTERNAL'}

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def invoke(self, context, event):
        self.filepath = get_prefs(context).viewport_preset + ".json"
        return super().invoke(context, event)

    def execute(self, context):
        write_preset_file(self.filepath, current_values(context))
        self.report({'INFO'}, "Exported preset to " + self.filepath)
        return {'FINISHED'}


def draw_viewport_background(layout, context, prefs):
    g = _viewport_gradients(context)
    row = layout.row(align=True)
    row.prop(prefs, "viewport_preset", text="")
    row.operator(TOMATACTICS_OT_preset_save.bl_idname, text="", icon='FILE_TICK')
    row.operator(TOMATACTICS_OT_preset_save.bl_idname, text="", icon='ADD').save_as = True
    sub = row.row(align=True)
    sub.enabled = prefs.viewport_preset not in BUILTIN_VIEWPORT_PRESETS
    sub.operator(TOMATACTICS_OT_preset_delete.bl_idname, text="", icon='REMOVE')

    layout.prop(g, "background_type", text="")
    col = layout.column(align=True)
    col.prop(g, "high_gradient", text="Color" if g.background_type == 'SINGLE_COLOR' else "High")
    if g.background_type != 'SINGLE_COLOR':
        col.prop(g, "gradient", text="Low")

    row = layout.row(align=True)
    row.operator(TOMATACTICS_OT_preset_import.bl_idname, text="Import", icon='IMPORT')
    row.operator(TOMATACTICS_OT_preset_export.bl_idname, text="Export", icon='EXPORT')


def draw_theme(layout, context, prefs):
    col = layout.column(align=True)
    col.prop(prefs, "theme_brightness", slider=True)
    col.prop(prefs, "theme_saturation", slider=True)
    col.prop(prefs, "theme_hue", slider=True)
    col = layout.column(align=True)
    row = col.row(align=True)
    row.prop(prefs, "theme_gradient", toggle=True)
    sub = row.row(align=True)
    sub.active = prefs.theme_gradient
    sub.prop(prefs, "theme_gradient_strength", text="Strength", slider=True)
    row = col.row(align=True)
    row.prop(prefs, "theme_opaque", toggle=True)
    row.prop(prefs, "theme_rounded", toggle=True)

    header, body = layout.panel("tomatactics_text_style", default_closed=True)
    header.label(text="Text Style", icon='FONT_DATA')
    if body is not None:
        for style, label in TEXT_STYLES:
            key = "text_%s_" % style
            box = body.box()
            box.label(text=label)
            box.prop(prefs, key + "shadow", text="")
            col = box.column(align=True)
            col.active = getattr(prefs, key + "shadow") != '0'
            row = col.row(align=True)
            row.prop(prefs, key + "shadow_offset_x")
            row.prop(prefs, key + "shadow_offset_y")
            col.prop(prefs, key + "shadow_alpha", slider=True)
            col.prop(prefs, key + "shadow_value", slider=True)
            col = box.column(align=True)
            col.prop(prefs, key + "character_weight")
            col.prop(prefs, key + "points")

    row = layout.row(align=True)
    row.operator(TOMATACTICS_OT_save_theme.bl_idname, icon='FILE_TICK')
    row.operator(TOMATACTICS_OT_reset_tuning.bl_idname, text="", icon='LOOP_BACK')


# -----------------------------------------------------------------------------
# Display


QUICK_UI_SCALE = 1.3


def is_quick_scale(context):
    return abs(context.preferences.view.ui_scale - QUICK_UI_SCALE) < 1e-3


class TOMATACTICS_OT_toggle_ui_scale(bpy.types.Operator):
    bl_idname = "tomatactics.toggle_ui_scale"
    bl_label = "UI Scale 1.3"
    bl_description = "Toggle the interface Resolution Scale between 1.3 and 1.0"
    bl_options = {'REGISTER'}

    def execute(self, context):
        view = context.preferences.view
        view.ui_scale = 1.0 if is_quick_scale(context) else QUICK_UI_SCALE
        self.report({'INFO'}, "Resolution Scale: %.2f" % view.ui_scale)
        return {'FINISHED'}


class TOMATACTICS_OT_reset_ui_scale(bpy.types.Operator):
    bl_idname = "tomatactics.reset_ui_scale"
    bl_label = "Reset UI Scale"
    bl_description = "Set the interface Resolution Scale back to 1.0"
    bl_options = {'REGISTER'}

    def execute(self, context):
        context.preferences.view.ui_scale = 1.0
        return {'FINISHED'}


# Blender does not report whether a window is fullscreen, so only toggles made here are known.
_fullscreen_windows = set()


def is_fullscreen(context):
    return context.window is not None and context.window.as_pointer() in _fullscreen_windows


class TOMATACTICS_OT_toggle_fullscreen(bpy.types.Operator):
    bl_idname = "tomatactics.toggle_fullscreen"
    bl_label = "Toggle Fullscreen"
    bl_description = "Toggle the window between fullscreen and normal"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.window is not None

    def execute(self, context):
        bpy.ops.wm.window_fullscreen_toggle()
        _fullscreen_windows.symmetric_difference_update({context.window.as_pointer()})
        return {'FINISHED'}


class TOMATACTICS_OT_exit_fullscreen(bpy.types.Operator):
    bl_idname = "tomatactics.exit_fullscreen"
    bl_label = "Exit Fullscreen"
    bl_description = "Leave the fullscreen entered with Toggle Fullscreen"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.window is not None

    def execute(self, context):
        if is_fullscreen(context):
            bpy.ops.wm.window_fullscreen_toggle()
            _fullscreen_windows.discard(context.window.as_pointer())
        return {'FINISHED'}


# -----------------------------------------------------------------------------
# Panels


def _quick_row(layout, op, text, icon, on, reset_op):
    """A main button that shows whether it is on, with a small reset button at the far right."""
    row = layout.row(align=True)
    row.operator(op, text=text, icon=icon, depress=on)
    reset = row.row(align=True)
    reset.active = on
    reset.operator(reset_op, text="", icon='LOOP_BACK')


def draw_quick(layout, context):
    col = layout.column()
    col.scale_y = 1.3
    theme_on = is_tuned_theme_active(context)
    _quick_row(col, TOMATACTICS_OT_apply_theme.bl_idname, "Set Theme",
               'CHECKMARK' if theme_on else 'COLOR', theme_on, TOMATACTICS_OT_reset_theme.bl_idname)
    full = is_fullscreen(context)
    _quick_row(col, TOMATACTICS_OT_toggle_fullscreen.bl_idname, "Toggle Fullscreen",
               'FULLSCREEN_EXIT' if full else 'FULLSCREEN_ENTER', full, TOMATACTICS_OT_exit_fullscreen.bl_idname)
    hidden = showcase.guides_hidden()
    _quick_row(col, showcase.TOMATACTICS_OT_toggle_guides.bl_idname,
               "Show Guides & Gizmos" if hidden else "Hide Guides & Gizmos",
               'HIDE_ON' if hidden else 'HIDE_OFF', hidden, showcase.TOMATACTICS_OT_show_guides.bl_idname)
    _quick_row(col, TOMATACTICS_OT_toggle_ui_scale.bl_idname, "UI Scale %.1f" % QUICK_UI_SCALE,
               'ZOOM_IN', is_quick_scale(context), TOMATACTICS_OT_reset_ui_scale.bl_idname)


class _SidebarPanel:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Theme"


class _SectionPanel(_SidebarPanel):
    bl_parent_id = "TOMATACTICS_PT_main"
    bl_options = {'DEFAULT_CLOSED'}


class TOMATACTICS_PT_main(_SidebarPanel, bpy.types.Panel):
    bl_idname = "TOMATACTICS_PT_main"
    bl_label = THEME_NAME

    def draw(self, context):
        draw_quick(self.layout, context)


class TOMATACTICS_PT_theme(_SectionPanel, bpy.types.Panel):
    bl_idname = "TOMATACTICS_PT_theme"
    bl_label = "Theme Tuning"

    def draw(self, context):
        prefs = get_prefs(context)
        if prefs is not None:
            draw_theme(self.layout, context, prefs)


class TOMATACTICS_PT_viewport_background(_SectionPanel, bpy.types.Panel):
    bl_idname = "TOMATACTICS_PT_viewport_background"
    bl_label = "Viewport Background"

    def draw(self, context):
        prefs = get_prefs(context)
        if prefs is not None:
            draw_viewport_background(self.layout, context, prefs)


class TOMATACTICS_PT_render(_SectionPanel, bpy.types.Panel):
    bl_idname = "TOMATACTICS_PT_render"
    bl_label = "Viewport Render"

    def draw(self, context):
        showcase.draw_render(self.layout)


class TOMATACTICS_PT_display(_SectionPanel, bpy.types.Panel):
    bl_idname = "TOMATACTICS_PT_display"
    bl_label = "Preferences"

    def draw(self, context):
        layout = self.layout
        layout.prop(context.preferences.view, "ui_scale", text="Resolution Scale")
        col = layout.column(align=True)
        col.operator(TOMATACTICS_OT_install_themes.bl_idname, icon='PRESET_NEW')
        col.operator("wm.save_userpref", text="Save Preferences", icon='FILE_TICK')


# -----------------------------------------------------------------------------
# Startup


def restore_saved():
    """Re-apply the last saved theme tuning and viewport preset so unsaved live edits never survive a restart."""
    context = bpy.context
    prefs = get_prefs(context)
    if prefs is None:
        return None
    state = read_state()
    if isinstance(state.get("theme"), dict):
        set_tune_values(prefs, state["theme"])
        apply_tuned_theme(context)
    name = state.get("viewport")
    if name:
        try:
            data = read_preset(name)
        except (OSError, ValueError, KeyError):
            return None
        select_preset(prefs, name)
        load_values(context, data)
    return None


classes = (
    TomatacticsPreferences,
    TOMATACTICS_OT_apply_theme,
    TOMATACTICS_OT_save_theme,
    TOMATACTICS_OT_reset_tuning,
    TOMATACTICS_OT_reset_theme,
    TOMATACTICS_OT_install_themes,
    TOMATACTICS_OT_preset_save,
    TOMATACTICS_OT_preset_delete,
    TOMATACTICS_OT_preset_import,
    TOMATACTICS_OT_preset_export,
    TOMATACTICS_OT_toggle_ui_scale,
    TOMATACTICS_OT_reset_ui_scale,
    TOMATACTICS_OT_toggle_fullscreen,
    TOMATACTICS_OT_exit_fullscreen,
    TOMATACTICS_PT_main,
    TOMATACTICS_PT_theme,
    TOMATACTICS_PT_viewport_background,
    TOMATACTICS_PT_render,
    TOMATACTICS_PT_display,
)


def register():
    showcase.register()
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.app.timers.register(restore_saved, first_interval=0.1)


def unregister():
    if bpy.app.timers.is_registered(restore_saved):
        bpy.app.timers.unregister(restore_saved)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    showcase.unregister()
