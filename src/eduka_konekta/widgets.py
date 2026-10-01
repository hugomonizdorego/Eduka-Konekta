"""Small GTK helpers shared by every page of the interface."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Callable

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import GdkPixbuf, GLib, Gtk, Pango  # noqa: E402


def asset(name: str) -> str:
    installed = Path("/usr/share/eduka-konekta/assets") / name
    if installed.exists():
        return str(installed)
    return str(Path(__file__).resolve().parents[2] / "assets" / name)


def clear_box(container: Gtk.Container) -> None:
    for child in container.get_children():
        container.remove(child)
        child.destroy()


def logo_pixbuf(size: int) -> GdkPixbuf.Pixbuf | None:
    """The application logo, or None when no SVG loader (librsvg) is installed."""
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_scale(asset("eduka-konekta.svg"), size, size, True)
    except GLib.Error:
        return None


def logo_image(name: str, width: int) -> Gtk.Widget:
    """A full logo (mark and wordmark) scaled to ``width``; falls back to text."""
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(asset(name), width, -1, True)
        image = Gtk.Image.new_from_pixbuf(pixbuf)
        image.set_halign(Gtk.Align.START)
        return image
    except GLib.Error:
        fallback = Gtk.Label(label="Eduka-Konekta", xalign=0.0)
        fallback.get_style_context().add_class("hero-title")
        return fallback


def asset_image(size: int) -> Gtk.Widget:
    pixbuf = logo_pixbuf(size)
    if pixbuf is not None:
        return Gtk.Image.new_from_pixbuf(pixbuf)
    fallback = Gtk.Label(label="🎓")
    fallback.set_size_request(size, size)
    fallback.get_style_context().add_class("logo-fallback")
    return fallback


def initials(name: str) -> str:
    parts = [part for part in str(name).split() if part]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:1].upper()
    return (parts[0][:1] + parts[-1][:1]).upper()


def profile_avatar(profile: dict[str, Any], size: int = 48) -> Gtk.Widget:
    """Circular-looking photo, or coloured initials when no photo was chosen."""
    try:
        raw = base64.b64decode(profile.get("photo_b64", ""), validate=True)
        if not raw:
            raise ValueError("no photo")
        loader = GdkPixbuf.PixbufLoader.new()
        loader.write(raw)
        loader.close()
        pixbuf = loader.get_pixbuf()
        side = min(pixbuf.get_width(), pixbuf.get_height())
        square = pixbuf.new_subpixbuf((pixbuf.get_width() - side) // 2, (pixbuf.get_height() - side) // 2, side, side)
        image = Gtk.Image.new_from_pixbuf(square.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR))
        image.set_valign(Gtk.Align.CENTER)
        image.get_style_context().add_class("profile-photo")
        return image
    except (ValueError, TypeError, GLib.Error, AttributeError):
        name = str(profile.get("full_name", ""))
        badge = Gtk.Label(label=initials(name))
        badge.set_size_request(size, size)
        badge.set_valign(Gtk.Align.CENTER)
        badge.set_halign(Gtk.Align.CENTER)
        context = badge.get_style_context()
        context.add_class("avatar-initials")
        context.add_class("avatar-teacher" if profile.get("role") == "teacher" else f"avatar-c{sum(map(ord, name)) % 6}")
        if size <= 32:
            context.add_class("avatar-small")
        elif size >= 64:
            context.add_class("avatar-large")
        return badge


def label(text: str = "", css: str | None = None, xalign: float = 0.0, wrap: bool = False) -> Gtk.Label:
    item = Gtk.Label(label=text, xalign=xalign)
    if css:
        for name in css.split():
            item.get_style_context().add_class(name)
    if wrap:
        item.set_line_wrap(True)
        item.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    return item


def add_class(widget: Gtk.Widget, *names: str) -> Gtk.Widget:
    context = widget.get_style_context()
    for name in names:
        context.add_class(name)
    return widget


def button(text: str, callback: Callable | None = None, css: str | None = None, tooltip: str | None = None) -> Gtk.Button:
    item = Gtk.Button(label=text)
    if css:
        add_class(item, *css.split())
    if tooltip:
        item.set_tooltip_text(tooltip)
    if callback:
        item.connect("clicked", callback)
    return item


def card(orientation: Gtk.Orientation = Gtk.Orientation.VERTICAL, spacing: int = 8, css: str = "card") -> Gtk.Box:
    box = Gtk.Box(orientation=orientation, spacing=spacing)
    add_class(box, *css.split())
    return box


def margins(widget: Gtk.Widget, value: int) -> Gtk.Widget:
    widget.set_margin_top(value)
    widget.set_margin_bottom(value)
    widget.set_margin_start(value)
    widget.set_margin_end(value)
    return widget


def scrolled(child: Gtk.Widget, horizontal: bool = False) -> Gtk.ScrolledWindow:
    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.AUTOMATIC if horizontal else Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.add(child)
    return scroller


def text_view(text: str = "", height: int = 90, editable: bool = True) -> Gtk.TextView:
    view = Gtk.TextView()
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    view.set_editable(editable)
    view.set_cursor_visible(editable)
    view.get_buffer().set_text(text)
    view.set_size_request(-1, height)
    view.set_left_margin(8)
    view.set_right_margin(8)
    view.set_top_margin(6)
    view.set_bottom_margin(6)
    add_class(view, "text-area")
    return view


def text_of(view: Gtk.TextView) -> str:
    buffer = view.get_buffer()
    return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)


def framed(view: Gtk.Widget) -> Gtk.Frame:
    frame = Gtk.Frame()
    add_class(frame, "text-frame")
    frame.add(view)
    return frame


def badge(text: str, tone: str = "info") -> Gtk.Label:
    item = Gtk.Label(label=text)
    item.set_valign(Gtk.Align.CENTER)
    add_class(item, "badge", f"badge-{tone}")
    return item
