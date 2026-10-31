# SPDX-License-Identifier: GPL-3.0-or-later
"""Viewport Showcase: hide guides and gizmos, and save a transparent viewport render."""

import os
import time

import bpy

GUIDE_VALUES = {
    "show_gizmo": False,
    "overlay.show_ortho_grid": False,
    "overlay.show_floor": False,
    "overlay.show_axis_x": False,
    "overlay.show_axis_y": False,
    "overlay.show_axis_z": False,
    "overlay.show_cursor": False,
    "overlay.show_annotation": False,
    "overlay.show_text": False,
    "overlay.show_stats": False,
    "overlay.show_fps": False,
}

# {3D View space pointer: {path: the user's own value}} while guides are hidden.
_saved_guides = {}


def _view3d_spaces():
    for screen in bpy.data.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    yield space


def _resolve(space, path):
    owner, _, attr = path.rpartition(".")
    obj = space
    for part in owner.split(".") if owner else ():
        obj = getattr(obj, part, None)
        if obj is None:
            return None, attr
    return (obj, attr) if hasattr(obj, attr) else (None, attr)


def guides_hidden():
    return bool(_saved_guides)


def hide_guides():
    for space in _view3d_spaces():
        saved = _saved_guides.setdefault(space.as_pointer(), {})
        for path, value in GUIDE_VALUES.items():
            obj, attr = _resolve(space, path)
            if obj is None:
                continue
            saved.setdefault(path, getattr(obj, attr))
            setattr(obj, attr, value)


def show_guides():
    for space in _view3d_spaces():
        saved = _saved_guides.get(space.as_pointer(), {})
        for path, value in saved.items():
            obj, attr = _resolve(space, path)
            # A value the user changed while hidden is theirs now and is kept.
            if obj is not None and getattr(obj, attr) == GUIDE_VALUES[path]:
                setattr(obj, attr, value)
    _saved_guides.clear()


# Saved files keep the user's guides; they are hidden again right after the save.
_rehide_after_save = False


@bpy.app.handlers.persistent
def _restore_before_save(*_args):
    global _rehide_after_save
    if _saved_guides:
        show_guides()
        _rehide_after_save = True


@bpy.app.handlers.persistent
def _rehide_after_save_handler(*_args):
    global _rehide_after_save
    if _rehide_after_save:
        _rehide_after_save = False
        hide_guides()


@bpy.app.handlers.persistent
def _forget_on_load(*_args):
    _saved_guides.clear()


def output_dir():
    return os.path.join(os.path.expanduser("~"), "Pictures", "Tomatactics")


def new_output_path():
    folder = output_dir()
    os.makedirs(folder, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(folder, "viewport_%s.png" % stamp)
    n = 1
    while os.path.exists(path):
        path = os.path.join(folder, "viewport_%s_%d.png" % (stamp, n))
        n += 1
    return path


def find_view3d(context):
    """(window, area, region) to render: the context's own 3D View, else the largest one in the window."""
    window = context.window
    area = context.area if context.area and context.area.type == 'VIEW_3D' else None
    if area is None and window is not None:
        areas = [a for a in window.screen.areas if a.type == 'VIEW_3D']
        area = max(areas, key=lambda a: a.width * a.height, default=None)
    if area is None:
        return window, None, None
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    return window, area, region


def render_transparent(context, window, area, region, path):
    render = context.scene.render
    was_transparent = render.film_transparent
    render.film_transparent = True
    try:
        with context.temp_override(window=window, screen=window.screen, area=area, region=region):
            result = bpy.ops.render.opengl(view_context=True)
        image = bpy.data.images.get("Render Result")
        if 'FINISHED' not in result or image is None:
            raise RuntimeError("Viewport render failed")
        image.save_render(path)
    finally:
        render.film_transparent = was_transparent


def _redraw(context):
    if context.screen is not None:
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


class TOMATACTICS_OT_toggle_guides(bpy.types.Operator):
    bl_idname = "tomatactics.toggle_guides"
    bl_label = "Hide Guides & Gizmos"
    bl_description = "Hide or bring back the navigation gizmo, grid, floor, axes, 3D cursor, annotations and text overlays in every 3D View"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if guides_hidden():
            show_guides()
        else:
            hide_guides()
        _redraw(context)
        return {'FINISHED'}


class TOMATACTICS_OT_show_guides(bpy.types.Operator):
    bl_idname = "tomatactics.show_guides"
    bl_label = "Show Guides"
    bl_description = "Bring back the guides and gizmos hidden by Hide Guides & Gizmos"
    bl_options = {'REGISTER'}

    def execute(self, context):
        show_guides()
        _redraw(context)
        return {'FINISHED'}


class TOMATACTICS_OT_render_viewport_image(bpy.types.Operator):
    bl_idname = "tomatactics.render_viewport_image"
    bl_label = "Render Viewport Image"
    bl_description = "Save a viewport render of the 3D View with a transparent background"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.window is not None

    def execute(self, context):
        window, area, region = find_view3d(context)
        if area is None or region is None:
            self.report({'WARNING'}, "No 3D View to render")
            return {'CANCELLED'}
        try:
            path = new_output_path()
            render_transparent(context, window, area, region, path)
        except Exception as exc:
            self.report({'ERROR'}, "Viewport render failed: %s" % exc)
            return {'CANCELLED'}
        context.window_manager.clipboard = path
        bpy.ops.wm.path_open(filepath=path)
        self.report({'INFO'}, "Saved %s (path copied to clipboard)" % path)
        return {'FINISHED'}


class TOMATACTICS_OT_open_render_folder(bpy.types.Operator):
    bl_idname = "tomatactics.open_render_folder"
    bl_label = "Open Render Folder"
    bl_description = "Open the folder viewport renders are saved to"
    bl_options = {'REGISTER'}

    def execute(self, context):
        folder = output_dir()
        os.makedirs(folder, exist_ok=True)
        bpy.ops.wm.path_open(filepath=folder)
        return {'FINISHED'}


def draw_render(layout):
    row = layout.row(align=True)
    row.operator(TOMATACTICS_OT_render_viewport_image.bl_idname, icon='RENDER_STILL')
    row.operator(TOMATACTICS_OT_open_render_folder.bl_idname, text="", icon='FILE_FOLDER')


classes = (
    TOMATACTICS_OT_toggle_guides,
    TOMATACTICS_OT_show_guides,
    TOMATACTICS_OT_render_viewport_image,
    TOMATACTICS_OT_open_render_folder,
)

_HANDLERS = (
    (bpy.app.handlers.save_pre, _restore_before_save),
    (bpy.app.handlers.save_post, _rehide_after_save_handler),
    (bpy.app.handlers.load_pre, _forget_on_load),
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    for handlers, fn in _HANDLERS:
        if fn not in handlers:
            handlers.append(fn)


def unregister():
    for handlers, fn in _HANDLERS:
        if fn in handlers:
            handlers.remove(fn)
    if _saved_guides:
        show_guides()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
