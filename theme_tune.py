# SPDX-License-Identifier: GPL-3.0-or-later
"""Adjusts the live theme: brightness, saturation, hue, opacity, widget gradients and roundness."""

import colorsys
import re

# (show_shaded, shadetop, shadedown, roundness) per widget, in the style of the "Theme 2000" theme.
WIDGET_STYLE = {
    "wcol_regular": (True, -70, 50, 0.84),
    "wcol_tool": (True, 60, -37, 0.55),
    "wcol_toolbar_item": (True, 20, -20, 0.4),
    "wcol_radio": (True, 30, 0, 0.5),
    "wcol_text": (False, 40, -40, 0.4),
    "wcol_option": (True, 10, 0, 0.4),
    "wcol_toggle": (True, 81, 0, 0.25),
    "wcol_num": (True, 20, -5, 1.0),
    "wcol_numslider": (True, -20, 50, 1.0),
    "wcol_box": (False, 23, 0, 0.4),
    "wcol_curve": (False, 0, 0, 0.4),
    "wcol_menu": (True, 0, -40, 0.5),
    "wcol_pulldown": (False, 0, 0, 0.4),
    "wcol_menu_back": (True, 0, -20, 1.0),
    "wcol_pie_menu": (True, 40, -40, 0.4),
    "wcol_tooltip": (False, 0, 0, 0.4),
    "wcol_menu_item": (False, 0, 0, 0.5),
    "wcol_scroll": (False, 0, 0, 1.0),
    "wcol_progress": (False, 0, 0, 0.4),
    "wcol_list_item": (True, 0, 15, 0.6),
    "wcol_tab": (True, 30, -30, 0.74),
}
PANEL_ROUNDNESS = 1.0

# Editors whose own (non-space) colors are interface chrome rather than scene data.
_CHROME_EDITORS = {"outliner", "properties", "preferences", "file_browser", "spreadsheet", "topbar", "statusbar"}
_SEMANTIC_ATTR = re.compile(r"^(axis_|gizmo|icon_)")
_SURFACE_ATTR = re.compile(r"back|header|inner|outline|panel_|editor_border|grid|row_alternate|"
                           r"highlight|backdrop|emboss|selected_file|^active$|match")
_OPAQUE_ATTR = {"inner", "inner_sel", "outline", "outline_sel", "header", "back", "header_back", "node_backdrop"}
# Alphas below this are deliberate overlays (hover tints, faint outlines) and stay translucent.
_OPAQUE_MIN_ALPHA = 0x40 / 255


def _color_structs(theme):
    """Yield (struct, attr names) for every interface color in scope; scene and semantic colors are skipped."""
    def colors(obj, skip=None):
        return [p.identifier for p in obj.bl_rna.properties
                if p.type == 'FLOAT' and p.subtype in {'COLOR', 'COLOR_GAMMA'}
                and not (skip and skip.match(p.identifier))]

    ui = theme.user_interface
    yield ui, colors(ui, _SEMANTIC_ATTR)
    for p in ui.bl_rna.properties:
        if p.identifier.startswith("wcol_") and p.identifier != "wcol_state":
            w = getattr(ui, p.identifier)
            yield w, colors(w)
    for p in theme.regions.bl_rna.properties:
        if p.type == 'POINTER':
            r = getattr(theme.regions, p.identifier)
            yield r, colors(r)
    for p in theme.bl_rna.properties:
        if p.type != 'POINTER' or p.identifier in {"user_interface", "regions", "common"}:
            continue
        editor = getattr(theme, p.identifier)
        space = getattr(editor, "space", None)
        if space is not None:
            yield space, colors(space)
        if p.identifier in _CHROME_EDITORS:
            yield editor, colors(editor)


def _adjust(rgb, brightness, saturation, hue_shift, keep_value):
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    h = (h + hue_shift / 360.0) % 1.0
    s = max(0.0, min(1.0, s * saturation))
    if not keep_value:
        v = max(0.0, min(1.0, v * brightness))
    return colorsys.hsv_to_rgb(h, s, v)


def apply(theme, brightness=1.0, saturation=1.0, hue_shift=0.0, opaque=True,
          gradient=True, gradient_strength=1.0, rounded=True):
    """Apply the adjustments on top of whatever theme is loaded (normally Blender's default)."""
    structs = list(_color_structs(theme))
    if brightness != 1.0 or saturation != 1.0 or hue_shift != 0.0:
        for struct, attrs in structs:
            for attr in attrs:
                value = tuple(getattr(struct, attr))
                keep_value = "text" in attr or "title" in attr or not _SURFACE_ATTR.search(attr)
                setattr(struct, attr, (*_adjust(value[:3], brightness, saturation, hue_shift, keep_value), *value[3:]))

    ui = theme.user_interface
    if opaque:
        panel = tuple(ui.panel_back)[:3]
        for struct, attrs in structs:
            # Solid colors are pre-blended over what they are drawn on, so they look the same, only without
            # see-through: widgets sit on the panel, headers on their editor's background.
            is_widget = struct.bl_rna.identifier == "ThemeWidgetColors"
            under = panel if is_widget else tuple(getattr(struct, "back", ()))[:3] or None
            for attr in attrs:
                value = tuple(getattr(struct, attr))
                if len(value) != 4 or attr not in _OPAQUE_ATTR or value[3] < _OPAQUE_MIN_ALPHA or value[3] >= 1.0:
                    continue
                rgb, a = value[:3], value[3]
                if under is not None and attr != "back":
                    rgb = tuple(c * a + u * (1.0 - a) for c, u in zip(rgb, under))
                setattr(struct, attr, (*rgb, 1.0))

    for name, (shaded, top, down, roundness) in WIDGET_STYLE.items():
        w = getattr(ui, name)
        if gradient:
            w.show_shaded = shaded
            w.shadetop = max(-100, min(100, round(top * gradient_strength)))
            w.shadedown = max(-100, min(100, round(down * gradient_strength)))
        if rounded:
            w.roundness = roundness
    if rounded:
        ui.panel_roundness = PANEL_ROUNDNESS
