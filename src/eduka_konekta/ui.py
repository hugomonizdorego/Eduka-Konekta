"""GTK 3 interface inspired by the friendly blue-and-white era of classic messengers."""

from __future__ import annotations

import base64
import html
import logging
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

from . import APP_NAME, CHANNEL, VERSION
from .devices import DeviceManager, MediaDevice
from .i18n import LANGUAGES, tr
from .models import IMAGE_LIMIT, Profile, rooms_for, validate_attachment, validate_ip, validate_profile, validate_profile_photo
from .network import P2PNetwork, PeerInfo
from .storage import MESSAGE_EDIT_WINDOW

LOG = logging.getLogger(__name__)
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)


def asset(name: str) -> str:
    installed = Path("/usr/share/eduka-konekta/assets") / name
    if installed.exists():
        return str(installed)
    return str(Path(__file__).resolve().parents[2] / "assets" / name)


def clear_box(container: Gtk.Container) -> None:
    for child in container.get_children():
        container.remove(child)


def asset_image(size: int) -> Gtk.Image:
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(asset("eduka-konekta.svg"), size, size, True)
    return Gtk.Image.new_from_pixbuf(pixbuf)


def profile_avatar(profile: dict[str, Any], size: int = 48) -> Gtk.Image:
    try:
        raw = base64.b64decode(profile.get("photo_b64", ""), validate=True)
        loader = GdkPixbuf.PixbufLoader.new()
        loader.write(raw)
        loader.close()
        pixbuf = loader.get_pixbuf().scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
        image = Gtk.Image.new_from_pixbuf(pixbuf)
        image.get_style_context().add_class("profile-photo")
        return image
    except (ValueError, TypeError, GLib.Error, AttributeError):
        return Gtk.Image.new_from_icon_name("avatar-default-symbolic", Gtk.IconSize.DIALOG)


def label(text: str = "", css: str | None = None, xalign: float = 0.0) -> Gtk.Label:
    item = Gtk.Label(label=text, xalign=xalign)
    if css:
        item.get_style_context().add_class(css)
    return item


class EdukaWindow(Gtk.ApplicationWindow):
    def __init__(self, application, storage, identity):
        super().__init__(application=application, title=f"{APP_NAME} {VERSION} {CHANNEL}")
        self.storage = storage
        self.identity = identity
        self.profile = storage.load_profile()
        self.language = self.profile.language if self.profile else "en"
        self.network: P2PNetwork | None = None
        self.current_room = ""
        self.current_target_ids: list[str] = []
        self.room_buttons: dict[str, Gtk.ToggleButton] = {}
        self.peers: list[PeerInfo] = []
        self.statuses: dict[str, dict[str, Any]] = {}
        self.groups: dict[str, dict[str, Any]] = {}
        self.direct_rooms: dict[str, dict[str, str]] = {}
        self.device_manager = DeviceManager(storage.session_dir / "captures")
        self.known_peer_ids: set[str] = set()
        self.notification_count = 0
        self.active_capture = None
        self.selected_photo_b64 = self.profile.photo_b64 if self.profile else ""
        self.selected_photo_mime = self.profile.photo_mime if self.profile else "image/jpeg"
        self.set_default_size(1100, 720)
        self.set_size_request(860, 580)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_icon_from_file(asset("eduka-konekta.svg"))
        self._load_css()
        self.connect("delete-event", self._on_delete)
        if self.profile:
            self.show_chat()
        else:
            self.show_login()

    def t(self, key: str) -> str:
        return tr(self.language, key)

    def _load_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_path(asset("style.css"))
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _on_delete(self, *_args):
        if self.active_capture and self.active_capture.poll() is None:
            self.device_manager.stop_recording(self.active_capture)
            self.active_capture = None
        if self.network:
            self.network.stop()
        self.storage.close()
        return False

    # Login ---------------------------------------------------------------
    def show_login(self) -> None:
        if self.network:
            self.network.stop()
            self.network = None
        self.language = self.profile.language if self.profile else self.language
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.get_style_context().add_class("login-root")

        titlebar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        titlebar.get_style_context().add_class("classic-titlebar")
        mini = asset_image(28)
        titlebar.pack_start(mini, False, False, 0)
        brand = label(f"{APP_NAME}  •  {VERSION} {CHANNEL}", "window-title")
        titlebar.pack_start(brand, True, True, 0)
        root.pack_start(titlebar, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        center.set_halign(Gtk.Align.CENTER)
        center.set_valign(Gtk.Align.CENTER)
        center.set_margin_top(28)
        center.set_margin_bottom(28)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.set_size_request(500, -1)
        card.get_style_context().add_class("login-card")

        logo = asset_image(112)
        card.pack_start(logo, False, False, 0)
        self.login_heading = label(self.t("sign_in"), "login-heading", 0.5)
        card.pack_start(self.login_heading, False, False, 0)
        self.login_subheading = label(self.t("welcome"), "muted", 0.5)
        self.login_subheading.set_line_wrap(True)
        card.pack_start(self.login_subheading, False, False, 0)

        self.language_combo = Gtk.ComboBoxText()
        for code, name in LANGUAGES.items():
            self.language_combo.append(code, name)
        self.language_combo.set_active_id(self.language if self.language in LANGUAGES else "en")
        self.language_combo.connect("changed", self._language_changed)
        self.language_row = self._form_row("language", self.language_combo)
        card.pack_start(self.language_row, False, False, 0)

        existing = self.profile
        self.name_entry = Gtk.Entry(text=existing.full_name if existing else "")
        self.name_entry.set_placeholder_text(self.t("full_name_hint"))
        self.school_entry = Gtk.Entry(text=existing.school if existing else "")
        self.role_combo = Gtk.ComboBoxText()
        self.role_combo.append("student", self.t("student"))
        self.role_combo.append("teacher", self.t("teacher"))
        self.role_combo.set_active_id(existing.role if existing else "student")
        self.role_combo.connect("changed", self._role_changed)
        self.age_spin = Gtk.SpinButton.new_with_range(5, 100, 1)
        self.age_spin.set_value(existing.age if existing else 15)
        self.class_entry = Gtk.Entry(text=existing.school_class if existing else "")
        self.room_entry = Gtk.Entry(text=existing.room if existing else "")
        self.subject_entry = Gtk.Entry(text=existing.subject if existing else "")
        self.subject_entry.set_placeholder_text(self.t("subject_hint"))

        self.form_widgets = {
            "full_name": self.name_entry, "school": self.school_entry, "role": self.role_combo,
            "age": self.age_spin, "class": self.class_entry, "room": self.room_entry, "subject": self.subject_entry,
        }
        self.form_rows = {}
        for key, widget in self.form_widgets.items():
            row = self._form_row(key, widget)
            self.form_rows[key] = row
            card.pack_start(row, False, False, 0)

        photo_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.photo_preview = profile_avatar(existing.public() if existing else {}, 72)
        photo_box.pack_start(self.photo_preview, False, False, 0)
        self.photo_button = Gtk.Button(label=self.t("choose_photo"))
        self.photo_button.connect("clicked", self._choose_profile_photo)
        photo_box.pack_start(self.photo_button, True, True, 0)
        self.photo_row = self._form_row("profile_photo", photo_box)
        self.form_rows["profile_photo"] = self.photo_row
        card.pack_start(self.photo_row, False, False, 0)
        self.photo_skip = Gtk.CheckButton(label=self.t("skip_photo"))
        self.photo_skip.set_active(not bool(existing and existing.photo_b64))
        self.photo_skip.connect("toggled", self._photo_skip_toggled)
        card.pack_start(self.photo_skip, False, False, 0)
        self.photo_note = label(self.t("photo_source_note"), "security-note")
        self.photo_note.set_line_wrap(True)
        card.pack_start(self.photo_note, False, False, 0)

        self.form_error = label("", "error-text", 0.0)
        self.form_error.set_line_wrap(True)
        card.pack_start(self.form_error, False, False, 0)
        self.connect_button = Gtk.Button(label=self.t("continue"))
        self.connect_button.get_style_context().add_class("primary-button")
        self.connect_button.connect("clicked", self._submit_profile)
        card.pack_start(self.connect_button, False, False, 4)
        self.no_password_label = label(self.t("no_password"), "security-note", 0.5)
        card.pack_start(self.no_password_label, False, False, 0)

        center.pack_start(card, False, False, 0)
        scroller.add(center)
        root.pack_start(scroller, True, True, 0)
        self._replace_root(root)
        self._role_changed(self.role_combo)
        self._photo_skip_toggled(self.photo_skip)

    def _form_row(self, key: str, widget: Gtk.Widget) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        heading = label(self.t(key), "field-label")
        heading.set_name("field-title")
        row.pack_start(heading, False, False, 0)
        row.pack_start(widget, False, False, 0)
        return row

    def _language_changed(self, combo: Gtk.ComboBoxText) -> None:
        self.language = combo.get_active_id() or "en"
        self.login_heading.set_text(self.t("sign_in"))
        self.login_subheading.set_text(self.t("welcome"))
        self.no_password_label.set_text(self.t("no_password"))
        self.photo_button.set_label(self.t("choose_photo"))
        self.photo_skip.set_label(self.t("skip_photo"))
        self.photo_note.set_text(self.t("photo_source_note"))
        self.name_entry.set_placeholder_text(self.t("full_name_hint"))
        self.subject_entry.set_placeholder_text(self.t("subject_hint"))
        self.connect_button.set_label(self.t("continue"))
        for key, row in {"language": self.language_row, **self.form_rows}.items():
            heading = row.get_children()[0]
            heading.set_text(self.t(key))
        selected_role = self.role_combo.get_active_id() or "student"
        self.role_combo.remove_all()
        self.role_combo.append("student", self.t("student"))
        self.role_combo.append("teacher", self.t("teacher"))
        self.role_combo.set_active_id(selected_role)

    def _role_changed(self, combo: Gtk.ComboBoxText) -> None:
        if hasattr(self, "form_rows") and "subject" in self.form_rows:
            self.form_rows["subject"].set_visible(combo.get_active_id() == "teacher")

    def _choose_profile_photo(self, _button) -> None:
        chooser = Gtk.FileChooserDialog(
            title=self.t("choose_photo"), parent=self, action=Gtk.FileChooserAction.OPEN,
            buttons=(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("open"), Gtk.ResponseType.ACCEPT),
        )
        chooser.set_modal(True)
        chooser.set_select_multiple(False)
        file_filter = Gtk.FileFilter()
        file_filter.set_name(self.t("profile_photo"))
        file_filter.add_mime_type("image/*")
        file_filter.add_pattern("*.jpg"); file_filter.add_pattern("*.jpeg")
        file_filter.add_pattern("*.png"); file_filter.add_pattern("*.webp")
        chooser.add_filter(file_filter)
        response = chooser.run()
        filename = chooser.get_filename()
        chooser.destroy()
        if response != Gtk.ResponseType.ACCEPT or not filename:
            return
        path = Path(filename)
        allowed, error_key, mime = validate_profile_photo(path)
        if not allowed:
            self._error(self.t("profile_photo"), self.t(error_key or "invalid_type"))
            return
        try:
            raw = path.read_bytes()
            GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 72, 72, True)
            self.selected_photo_b64 = base64.b64encode(raw).decode("ascii")
            self.selected_photo_mime = mime
            replacement = profile_avatar({"photo_b64": self.selected_photo_b64}, 72)
            photo_box = self.photo_preview.get_parent()
            photo_box.remove(self.photo_preview)
            photo_box.pack_start(replacement, False, False, 0)
            photo_box.reorder_child(replacement, 0)
            self.photo_preview = replacement
            self.photo_preview.show()
            self.photo_skip.set_active(False)
        except (OSError, GLib.Error) as error:
            self._error(self.t("profile_photo"), str(error))

    def _photo_skip_toggled(self, button: Gtk.CheckButton) -> None:
        skipped = button.get_active()
        self.photo_button.set_sensitive(not skipped)
        if not skipped:
            return
        self.selected_photo_b64 = ""
        self.selected_photo_mime = ""
        photo_box = self.photo_preview.get_parent()
        replacement = profile_avatar({}, 72)
        photo_box.remove(self.photo_preview)
        photo_box.pack_start(replacement, False, False, 0)
        photo_box.reorder_child(replacement, 0)
        self.photo_preview = replacement
        self.photo_preview.show()

    def _submit_profile(self, _button) -> None:
        profile = Profile(
            full_name=self.name_entry.get_text().strip(), school=self.school_entry.get_text().strip(),
            role=self.role_combo.get_active_id() or "student", age=self.age_spin.get_value_as_int(),
            school_class=self.class_entry.get_text().strip(), room=self.room_entry.get_text().strip(),
            language=self.language, subject=self.subject_entry.get_text().strip(),
            photo_b64=self.selected_photo_b64, photo_mime=self.selected_photo_mime,
        )
        errors = validate_profile(profile)
        if errors:
            self.form_error.set_text(self.t("profile_error") + ":\n• " + "\n• ".join(self.t(item) for item in errors))
            return
        self.profile = profile
        self.storage.save_profile(profile)
        self.show_chat()

    # Main chat -----------------------------------------------------------
    def show_chat(self) -> None:
        assert self.profile is not None
        self.language = self.profile.language
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.get_style_context().add_class("app-root")
        root.pack_start(self._build_menubar(), False, False, 0)
        root.pack_start(self._build_toolbar(), False, False, 0)
        privacy = label("🔒  " + self.t("session_privacy"), "privacy-banner", 0.5)
        privacy.set_line_wrap(True)
        root.pack_start(privacy, False, False, 0)

        body = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        body.set_wide_handle(False)
        sidebar = self._build_sidebar()
        body.pack1(sidebar, False, False)
        content_and_people = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        content_and_people.pack1(self._build_conversation(), True, False)
        content_and_people.pack2(self._build_people(), False, False)
        body.pack2(content_and_people, True, False)
        root.pack_start(body, True, True, 0)

        status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        status.get_style_context().add_class("statusbar")
        self.status_dot = label("●", "online-dot")
        self.status_text = label(self.t("connecting"), "status-text")
        status.pack_start(self.status_dot, False, False, 0)
        status.pack_start(self.status_text, True, True, 0)
        status.pack_end(label(f"ID: {self.identity.user_id}", "fingerprint"), False, False, 0)
        root.pack_start(status, False, False, 0)

        self._replace_root(root)
        first_room = rooms_for(self.profile)[0][0]
        self.select_room(first_room)
        self._start_network()

    def _build_menubar(self) -> Gtk.MenuBar:
        menubar = Gtk.MenuBar()
        file_item = Gtk.MenuItem(label=self.t("file"))
        file_menu = Gtk.Menu()
        edit = Gtk.MenuItem(label=self.t("edit_profile"))
        edit.connect("activate", lambda *_: self._edit_profile())
        clear = Gtk.MenuItem(label=self.t("clear_history"))
        clear.connect("activate", lambda *_: self._confirm_clear())
        logout = Gtk.MenuItem(label=self.t("logout"))
        logout.connect("activate", lambda *_: self._confirm_logout())
        quit_item = Gtk.MenuItem(label=self.t("quit"))
        quit_item.connect("activate", lambda *_: self.close())
        for item in (edit, clear, Gtk.SeparatorMenuItem(), logout, quit_item):
            file_menu.append(item)
        file_item.set_submenu(file_menu)
        tools_item = Gtk.MenuItem(label=self.t("connection_tools"))
        tools_menu = Gtk.Menu()
        refresh = Gtk.MenuItem(label=self.t("refresh_online"))
        refresh.connect("activate", self._refresh_online)
        connect_ip = Gtk.MenuItem(label=self.t("connect_ip"))
        connect_ip.connect("activate", self._connect_ip_dialog)
        devices = Gtk.MenuItem(label=self.t("media_devices"))
        devices.connect("activate", self._show_devices_dialog)
        for item in (refresh, connect_ip, devices):
            tools_menu.append(item)
        tools_item.set_submenu(tools_menu)
        help_item = Gtk.MenuItem(label=self.t("help"))
        help_menu = Gtk.Menu()
        about = Gtk.MenuItem(label=self.t("about"))
        about.connect("activate", lambda *_: self.show_about())
        help_menu.append(about)
        help_item.set_submenu(help_menu)
        menubar.append(file_item)
        menubar.append(tools_item)
        menubar.append(help_item)
        return menubar

    def _build_toolbar(self) -> Gtk.Box:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        bar.get_style_context().add_class("main-toolbar")
        logo = asset_image(38)
        bar.pack_start(logo, False, False, 4)
        brandbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        brandbox.pack_start(label(APP_NAME, "brand-name"), False, False, 0)
        brandbox.pack_start(label(f"{VERSION} {CHANNEL}  •  P2P School Messenger", "brand-version"), False, False, 0)
        bar.pack_start(brandbox, False, False, 4)
        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 12)
        for icon_name, text_key, callback in (
            ("user-available-symbolic", "set_status", self._set_status_dialog),
        ):
            button = Gtk.Button()
            button.set_relief(Gtk.ReliefStyle.NONE)
            stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            stack.pack_start(Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.LARGE_TOOLBAR), False, False, 0)
            stack.pack_start(label(self.t(text_key), "toolbar-label", 0.5), False, False, 0)
            button.add(stack)
            button.connect("clicked", callback)
            bar.pack_start(button, False, False, 1)
        if self.profile.role == "teacher":
            for text_key, callback in (
                ("new_group", self._new_group_dialog),
                ("broadcast", self._broadcast_dialog),
                ("send_grade", self._grade_dialog),
            ):
                button = Gtk.Button(label=self.t(text_key))
                button.set_relief(Gtk.ReliefStyle.NONE)
                button.connect("clicked", callback)
                bar.pack_start(button, False, False, 1)
        about_button = Gtk.Button(label=self.t("about"))
        about_button.set_relief(Gtk.ReliefStyle.NONE)
        about_button.connect("clicked", lambda *_: self.show_about())
        bar.pack_end(about_button, False, False, 4)
        logout_button = Gtk.Button(label=self.t("logout"))
        logout_button.set_relief(Gtk.ReliefStyle.NONE)
        logout_button.connect("clicked", lambda *_: self._confirm_logout())
        bar.pack_end(logout_button, False, False, 2)
        self.notification_button = Gtk.Button(label="🔔 0")
        self.notification_button.set_relief(Gtk.ReliefStyle.NONE)
        self.notification_button.get_style_context().add_class("notification-counter")
        self.notification_button.set_tooltip_text(self.t("clear_notifications"))
        self.notification_button.connect("clicked", self._clear_notification_count)
        bar.pack_end(self.notification_button, False, False, 8)
        return bar

    def _build_sidebar(self) -> Gtk.Box:
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        side.set_size_request(236, -1)
        side.get_style_context().add_class("sidebar")
        profile_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        profile_card.get_style_context().add_class("profile-card")
        avatar = profile_avatar(self.profile.public(), 72)
        profile_card.pack_start(avatar, False, False, 0)
        profile_card.pack_start(label(self.profile.full_name, "profile-name", 0.5), False, False, 0)
        role_text = self.t(self.profile.role)
        if self.profile.role == "teacher":
            role_text += " • " + self.profile.subject
        profile_card.pack_start(label(role_text, "role-badge", 0.5), False, False, 0)
        profile_card.pack_start(label(f"{self.profile.school}\n{self.t('class')} {self.profile.school_class} • {self.profile.room}", "profile-school", 0.5), False, False, 0)
        side.pack_start(profile_card, False, False, 0)
        side.pack_start(label(self.t("rooms"), "section-label"), False, False, 0)
        self.room_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.room_buttons = {}
        icons = {"all_schools": "🌐", "broadcasts": "📣", "my_school": "🏫", "my_class": "📚", "teachers": "👩‍🏫"}
        for room_id, key in rooms_for(self.profile):
            button = Gtk.ToggleButton(label=f"{icons.get(key, '💬')}   {self.t(key)}")
            button.set_halign(Gtk.Align.FILL)
            button.get_child().set_xalign(0.0)
            button.connect("clicked", lambda _button, selected=room_id: self.select_room(selected))
            self.room_buttons[room_id] = button
            self.room_list.pack_start(button, False, False, 0)
        side.pack_start(self.room_list, False, False, 0)
        self.group_heading = label(self.t("new_group").upper(), "section-label")
        side.pack_start(self.group_heading, False, False, 0)
        self.group_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        side.pack_start(self.group_list, False, False, 0)
        side.pack_start(label(self.t("direct_chats"), "section-label"), False, False, 0)
        self.direct_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        side.pack_start(self.direct_list, False, False, 0)
        note = label(self.t("session_privacy"), "sidebar-note")
        note.set_line_wrap(True)
        side.pack_end(note, False, False, 0)
        return side

    def _build_conversation(self) -> Gtk.Box:
        area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        area.get_style_context().add_class("conversation")
        area.pack_start(self._build_status_feed(), False, False, 0)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.get_style_context().add_class("conversation-header")
        self.room_title = label("", "room-title")
        self.room_subtitle = label(self.t("automatic_discovery"), "room-subtitle")
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        titles.pack_start(self.room_title, False, False, 0)
        titles.pack_start(self.room_subtitle, False, False, 0)
        header.pack_start(titles, True, True, 0)
        area.pack_start(header, False, False, 0)

        self.message_scroller = Gtk.ScrolledWindow()
        self.message_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.message_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.message_list.set_margin_top(14)
        self.message_list.set_margin_bottom(14)
        self.message_list.set_margin_start(14)
        self.message_list.set_margin_end(14)
        self.message_scroller.add(self.message_list)
        area.pack_start(self.message_scroller, True, True, 0)

        composer_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        composer_toolbar.get_style_context().add_class("composer-toolbar")
        media_actions = (
            ("😊", "emoji", self._open_emoji),
            ("🖼", "upload_image", lambda *_: self._choose_attachment("image")),
            ("🎬", "upload_video", lambda *_: self._choose_attachment("video")),
            ("📎", "upload_audio", lambda *_: self._choose_attachment("audio")),
            ("📄", "upload_document", lambda *_: self._choose_attachment("document")),
            ("📷", "capture_photo", self._capture_photo),
            ("🎙", "record_voice", lambda *_: self._record_media("audio")),
            ("📹", "record_video", lambda *_: self._record_media("video")),
        )
        for text, tooltip, callback in media_actions:
            button = Gtk.Button(label=text)
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.get_style_context().add_class("media-button")
            button.set_tooltip_text(self.t(tooltip))
            button.connect("clicked", callback)
            composer_toolbar.pack_start(button, False, False, 0)
        area.pack_start(composer_toolbar, False, False, 0)
        composer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        composer.get_style_context().add_class("composer")
        self.message_entry = Gtk.Entry()
        self.message_entry.set_placeholder_text(self.t("message_placeholder"))
        self.message_entry.connect("activate", self._send_text)
        composer.pack_start(self.message_entry, True, True, 0)
        send = Gtk.Button(label=self.t("send"))
        send.get_style_context().add_class("send-button")
        send.connect("clicked", self._send_text)
        composer.pack_start(send, False, False, 0)
        area.pack_start(composer, False, False, 0)
        return area

    def _build_status_feed(self) -> Gtk.Box:
        feed = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        feed.get_style_context().add_class("status-feed")
        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        heading.pack_start(label(self.t("status_feed"), "section-label"), True, True, 0)
        add_status = Gtk.Button(label="＋ " + self.t("set_status"))
        add_status.get_style_context().add_class("status-add-button")
        add_status.connect("clicked", self._set_status_dialog)
        heading.pack_end(add_status, False, False, 0)
        feed.pack_start(heading, False, False, 0)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        scroller.set_size_request(-1, 112)
        self.status_feed_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.status_feed_box.set_margin_bottom(5)
        scroller.add_with_viewport(self.status_feed_box)
        feed.pack_start(scroller, False, False, 0)
        self._render_status_feed()
        return feed

    def _render_status_feed(self) -> None:
        if not hasattr(self, "status_feed_box"):
            return
        clear_box(self.status_feed_box)
        profile_map = {self.identity.user_id: self.profile.public()}
        profile_map.update({peer.user_id: peer.profile for peer in self.peers})
        entries = sorted(self.statuses.items(), key=lambda item: float(item[1].get("timestamp", 0)), reverse=True)
        if not entries:
            empty = label(self.t("no_status_updates"), "status-empty", 0.5)
            empty.set_size_request(260, 80)
            self.status_feed_box.pack_start(empty, False, False, 0)
        for user_id, status in entries:
            profile = status.get("profile") or profile_map.get(user_id, {})
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            card.set_size_request(190, 88)
            card.get_style_context().add_class("status-card")
            person = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            person.pack_start(profile_avatar(profile, 28), False, False, 0)
            name = profile.get("full_name", self.t("unknown_user"))
            person.pack_start(label(name, "status-person"), True, True, 0)
            card.pack_start(person, False, False, 0)
            if status.get("status_kind") == "image" and status.get("file_path"):
                path = Path(status["file_path"])
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 176, 48, True)
                    image = Gtk.Image.new_from_pixbuf(pixbuf)
                    image.set_halign(Gtk.Align.START)
                    card.pack_start(image, True, True, 0)
                except GLib.Error:
                    card.pack_start(label("🖼 " + path.name, "status-copy"), False, False, 0)
                card.set_tooltip_text(self.t("open_status_image"))
                event = Gtk.EventBox()
                event.add(card)
                event.connect("button-release-event", lambda *_args, selected=path: self._open_path(selected))
                self.status_feed_box.pack_start(event, False, False, 0)
            else:
                copy = label(self._status_summary(status), "status-copy")
                copy.set_line_wrap(True)
                copy.set_max_width_chars(24)
                card.pack_start(copy, True, True, 0)
                self.status_feed_box.pack_start(card, False, False, 0)
        self.status_feed_box.show_all()

    def _build_people(self) -> Gtk.Box:
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        side.set_size_request(250, -1)
        side.get_style_context().add_class("people-panel")
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.pack_start(label(self.t("online_directory"), "section-label"), True, True, 0)
        refresh = Gtk.Button(label="↻")
        refresh.set_tooltip_text(self.t("refresh_online"))
        refresh.get_style_context().add_class("refresh-button")
        refresh.connect("clicked", self._refresh_online)
        header.pack_end(refresh, False, False, 0)
        side.pack_start(header, False, False, 0)

        lists = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        student_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        student_area.pack_start(label(self.t("students_online"), "online-group-label"), False, False, 0)
        student_scroller = Gtk.ScrolledWindow()
        student_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.student_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        student_scroller.add(self.student_list)
        student_area.pack_start(student_scroller, True, True, 0)
        teacher_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        teacher_area.pack_start(label(self.t("teachers_online"), "online-group-label"), False, False, 0)
        teacher_scroller = Gtk.ScrolledWindow()
        teacher_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.teacher_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        teacher_scroller.add(self.teacher_list)
        teacher_area.pack_start(teacher_scroller, True, True, 0)
        lists.pack1(student_area, True, False)
        lists.pack2(teacher_area, True, False)
        side.pack_start(lists, True, True, 0)
        self._render_people()
        return side

    def _start_network(self) -> None:
        if self.network:
            self.network.stop()
        try:
            self.network = P2PNetwork(
                self.identity, self.profile,
                lambda message: GLib.idle_add(self._receive_message, message),
                lambda peers: GLib.idle_add(self._update_peers, peers),
                lambda status: GLib.idle_add(self._receive_status, status),
                lambda group: GLib.idle_add(self._receive_group, group),
                lambda action: GLib.idle_add(self._receive_message_action, action),
                self.storage.known_peer_ips(),
            )
            self.network.start()
            addresses = ", ".join(item["address"] for item in self.network.local_ips) or "127.0.0.1"
            self.status_text.set_text(f"{self.t('automatic_discovery')} • {self.t('local_ip')}: {addresses} • TCP {self.network.tcp_port}")
        except OSError as error:
            self.network = None
            self.status_text.set_text(f"{self.t('disconnected')}: {error}")

    def select_room(self, room_id: str) -> None:
        self.current_room = room_id
        self.current_target_ids = []
        if room_id in self.direct_rooms:
            self.current_target_ids = [self.direct_rooms[room_id]["user_id"]]
        elif room_id in self.groups:
            self.current_target_ids = [item for item in self.groups[room_id]["members"] if item != self.identity.user_id]
        for selected_id, button in self.room_buttons.items():
            if button.get_active() != (selected_id == room_id):
                button.set_active(selected_id == room_id)
        title_key = dict(rooms_for(self.profile)).get(room_id)
        dynamic_title = self.direct_rooms.get(room_id, {}).get("name") or self.groups.get(room_id, {}).get("name", room_id)
        self.room_title.set_text(self.t(title_key) if title_key else dynamic_title)
        self.room_subtitle.set_text(self.t("direct_chat") if room_id in self.direct_rooms else self.t("automatic_discovery"))
        self._render_messages()

    def select_direct(self, user_id: str, full_name: str) -> None:
        peer = next((item for item in self.peers if item.user_id == user_id), None)
        if not peer:
            self._error(self.t("direct_chat"), self.t("direct_unavailable"))
            return
        room_id = "direct:" + ":".join(sorted((self.identity.user_id, user_id)))
        self.direct_rooms[room_id] = {"user_id": user_id, "name": full_name}
        self._add_dynamic_room_button(room_id, "👤 " + full_name, self.direct_list)
        self.current_room = room_id
        self.current_target_ids = [user_id]
        for selected_id, button in self.room_buttons.items():
            button.set_active(selected_id == room_id)
        self.room_title.set_text(full_name)
        self.room_subtitle.set_text(self.t("direct_chat"))
        self._render_messages()

    def _add_dynamic_room_button(self, room_id: str, text: str, container: Gtk.Box) -> None:
        if room_id in self.room_buttons:
            return
        button = Gtk.ToggleButton(label=text)
        button.get_child().set_xalign(0.0)
        button.connect("clicked", lambda _button, selected=room_id: self.select_room(selected))
        self.room_buttons[room_id] = button
        container.pack_start(button, False, False, 0)
        container.show_all()

    def _make_message(self, kind: str, text_value: str = "", **extra) -> dict[str, Any]:
        message = {
            "msg_id": uuid.uuid4().hex, "room_id": self.current_room, "timestamp": time.time(),
            "sender_id": self.identity.user_id, "profile": self.profile.public(include_photo=False), "kind": kind,
            "text": text_value, "verified": True,
        }
        message.update(extra)
        return message

    def _send_text(self, _widget) -> None:
        content = self.message_entry.get_text().strip()
        if not content or not self.current_room:
            return
        if len(content) > 4000:
            content = content[:4000]
        self.message_entry.set_text("")
        self._send_message(self._make_message("text", content))

    def _send_message(self, message: dict[str, Any]) -> None:
        local_copy = {key: value for key, value in message.items() if key != "file_data"}
        self.storage.add_message(local_copy)
        room_id = message["room_id"]
        target_ids = self._targets_for_room(room_id)
        if self.network:
            self.network.send_chat(
                {key: value for key, value in message.items() if key not in {"sender_id", "file_path"}},
                target_ids or None,
            )
        if message["room_id"] == self.current_room:
            self._append_message(local_copy)
            self._scroll_bottom()

    def _receive_message(self, message: dict[str, Any]) -> bool:
        room_id = str(message.get("room_id", ""))
        if room_id.startswith("direct:"):
            targets = message.get("targets", [])
            if self.identity.user_id not in targets:
                return False
            sender_name = str(message.get("profile", {}).get("full_name", "Unknown"))
            self.direct_rooms[room_id] = {"user_id": message.get("sender_id", ""), "name": sender_name}
            self._add_dynamic_room_button(room_id, "👤 " + sender_name, self.direct_list)
        allowed_rooms = {room for room, _ in rooms_for(self.profile)} | set(self.groups) | set(self.direct_rooms)
        if message.get("room_id") not in allowed_rooms:
            return False
        profile = message.get("profile", {})
        try:
            if validate_profile(Profile.from_dict(profile), require_photo=False):
                return False
        except (TypeError, ValueError):
            return False
        if message["room_id"].startswith("teachers:") and profile.get("role") != "teacher":
            return False
        if message["room_id"] == "broadcasts" and profile.get("role") != "teacher":
            return False
        kind = message.get("kind")
        if kind not in {"text", "broadcast", "grade", "image", "video", "audio", "document"}:
            return False
        if kind in {"text", "broadcast", "grade"}:
            if not isinstance(message.get("text"), str) or len(message["text"]) > 4000:
                return False
        if kind in {"image", "video", "audio", "document"}:
            encoded = message.pop("file_data", "")
            limits = {"image": 14_000_000, "video": 34_000_000, "audio": 14_000_000, "document": 34_000_000}
            if not isinstance(encoded, str) or len(encoded) > limits[kind]:
                return False
            try:
                raw = base64.b64decode(encoded, validate=True)
                path = self.storage.safe_download_path(message["msg_id"], message.get("file_name", "attachment"))
                path.write_bytes(raw)
                allowed, _error_key, _mime = validate_attachment(path, kind)
                if not allowed:
                    path.unlink(missing_ok=True)
                    return False
                message["file_path"] = str(path)
            except (ValueError, OSError):
                return False
        if not self.storage.add_message(message):
            return False
        if message["room_id"] == self.current_room:
            self._append_message(message)
            self._scroll_bottom()
        sender = str(profile.get("full_name", self.t("unknown_user")))
        if message["room_id"] == "broadcasts":
            self._notify(self.t("announcement"), f"{sender}: {message.get('text', '')[:240]}", "broadcast")
        else:
            body = message.get("text", "")[:240] if kind in {"text", "grade"} else self.t(f"received_{kind}")
            self._notify(self.t("new_message"), f"{sender}: {body}", "message")
        return False

    def _render_messages(self) -> None:
        clear_box(self.message_list)
        messages = self.storage.messages(self.current_room)
        if not messages:
            empty = label(self.t("room_empty"), "empty-message", 0.5)
            empty.set_margin_top(80)
            self.message_list.pack_start(empty, False, False, 0)
        else:
            for message in messages:
                self._append_message(message, show=False)
        self.message_list.show_all()
        GLib.idle_add(self._scroll_bottom)

    def _append_message(self, message: dict[str, Any], show: bool = True) -> None:
        if self.message_list.get_children() and self.message_list.get_children()[0].get_style_context().has_class("empty-message"):
            clear_box(self.message_list)
        own = message.get("sender_id") == self.identity.user_id
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        row.set_halign(Gtk.Align.END if own else Gtk.Align.START)
        bubble = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        bubble.set_size_request(180, -1)
        bubble.get_style_context().add_class("message-own" if own else "message-peer")
        profile = message.get("profile", {})
        name_text = f"{'✓ ' if message.get('verified', True) else ''}{profile.get('full_name', 'Unknown')}  •  {self.t(profile.get('role', 'student'))}"
        bubble.pack_start(label(name_text, "message-name"), False, False, 0)
        if message.get("text"):
            content = Gtk.Label(xalign=0.0)
            content.set_line_wrap(True)
            content.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            content.set_selectable(True)
            content.set_markup(self._link_markup(message["text"]))
            content.connect("activate-link", self._open_link)
            bubble.pack_start(content, False, False, 0)
        path_value = message.get("file_path")
        if path_value:
            path = Path(path_value)
            if message.get("kind") == "image" and path.exists():
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 360, 240, True)
                    image = Gtk.Image.new_from_pixbuf(pixbuf)
                    image.set_halign(Gtk.Align.START)
                    bubble.pack_start(image, False, False, 0)
                except GLib.Error:
                    pass
            file_button = Gtk.Button(label=f"📎  {message.get('file_name', path.name)}  •  {self.t('open')}")
            file_button.set_halign(Gtk.Align.START)
            file_button.connect("clicked", lambda _button, selected=path: self._open_path(selected))
            bubble.pack_start(file_button, False, False, 0)
        timestamp = datetime.fromtimestamp(float(message.get("timestamp", time.time()))).strftime("%H:%M")
        edited = f" • {self.t('edited')}" if message.get("edited_at") else ""
        bubble.pack_start(label(f"{timestamp}{edited}  •  {str(message.get('sender_id', ''))[:12]}", "message-time", 1.0), False, False, 0)
        message_age = time.time() - float(message.get("timestamp", 0))
        if own and -60 <= message_age <= MESSAGE_EDIT_WINDOW:
            controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            if message.get("kind") == "text":
                edit = Gtk.Button(label="✎ " + self.t("edit_message"))
                edit.get_style_context().add_class("message-action")
                edit.connect("clicked", lambda _button, msg_id=message["msg_id"]: self._edit_message_dialog(msg_id))
                controls.pack_start(edit, False, False, 0)
            elif message.get("kind") in {"image", "video", "audio", "document"}:
                replace = Gtk.Button(label="↺ " + self.t("replace_file"))
                replace.get_style_context().add_class("message-action")
                replace.connect("clicked", lambda _button, msg_id=message["msg_id"]: self._replace_file_dialog(msg_id))
                controls.pack_start(replace, False, False, 0)
            delete = Gtk.Button(label="🗑 " + self.t("delete_message"))
            delete.get_style_context().add_class("message-action-danger")
            delete.connect("clicked", lambda _button, msg_id=message["msg_id"]: self._delete_message_dialog(msg_id))
            controls.pack_end(delete, False, False, 0)
            bubble.pack_start(controls, False, False, 0)
        row.pack_start(bubble, False, False, 0)
        self.message_list.pack_start(row, False, False, 0)
        if show:
            row.show_all()

    def _targets_for_room(self, room_id: str) -> list[str]:
        if room_id in self.direct_rooms:
            return [self.direct_rooms[room_id]["user_id"]]
        if room_id in self.groups:
            return [item for item in self.groups[room_id]["members"] if item != self.identity.user_id]
        return []

    def _edit_message_dialog(self, message_id: str) -> None:
        message = self.storage.message(message_id)
        if not message or message.get("sender_id") != self.identity.user_id or message.get("kind") != "text":
            return
        dialog = Gtk.Dialog(title=self.t("edit_message"), transient_for=self, modal=True)
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("save_changes"), Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_margin_top(14); box.set_margin_bottom(14); box.set_margin_start(14); box.set_margin_end(14)
        entry = Gtk.Entry(text=message.get("text", ""))
        entry.set_activates_default(True)
        box.add(entry)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.show_all()
        response = dialog.run()
        new_text = entry.get_text().strip()[:4000]
        dialog.destroy()
        if response != Gtk.ResponseType.OK or not new_text or new_text == message.get("text", ""):
            return
        if not self.storage.edit_message(message_id, self.identity.user_id, new_text):
            self._error(self.t("edit_message"), self.t("edit_window_expired"))
            return
        self._send_message_action(message, "edit", text=new_text)
        self._render_messages()

    def _replace_file_dialog(self, message_id: str) -> None:
        message = self.storage.message(message_id)
        kind = message.get("kind") if message else ""
        if not message or message.get("sender_id") != self.identity.user_id or kind not in {"image", "video", "audio", "document"}:
            return
        path = self._choose_media_file(kind, self.t("replace_file"))
        if not path:
            return
        allowed, error_key, mime = validate_attachment(path, kind)
        if not allowed:
            self._error(self.t("attachment_error"), self.t(error_key or "invalid_type"))
            return
        try:
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        except OSError as error:
            self._error(self.t("attachment_error"), str(error))
            return
        if not self.storage.replace_message_file(message_id, self.identity.user_id, kind, str(path), path.name, mime):
            self._error(self.t("replace_file"), self.t("edit_window_expired"))
            return
        self._send_message_action(message, "replace", kind=kind, file_name=path.name, mime=mime, file_data=encoded)
        self._render_messages()

    def _delete_message_dialog(self, message_id: str) -> None:
        message = self.storage.message(message_id)
        if not message or message.get("sender_id") != self.identity.user_id:
            return
        dialog = Gtk.MessageDialog(
            self, Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.NONE,
            self.t("delete_message_confirm"),
        )
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("delete_message"), Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        if not self.storage.delete_message(message_id, self.identity.user_id):
            self._error(self.t("delete_message"), self.t("edit_window_expired"))
            return
        self._send_message_action(message, "delete")
        self._render_messages()

    def _send_message_action(self, original: dict[str, Any], action: str, **values) -> None:
        payload = {
            "event_id": uuid.uuid4().hex,
            "action": action,
            "msg_id": original["msg_id"],
            "room_id": original["room_id"],
            "timestamp": time.time(),
            "profile": self.profile.public(include_photo=False),
            **values,
        }
        if self.network:
            self.network.send_message_action(payload, self._targets_for_room(original["room_id"]) or None)

    def _receive_message_action(self, action: dict[str, Any]) -> bool:
        message_id = str(action.get("msg_id", ""))
        sender_id = str(action.get("sender_id", ""))
        original = self.storage.message(message_id)
        if not original or original.get("sender_id") != sender_id:
            return False
        applied = False
        if action.get("action") == "edit":
            applied = self.storage.edit_message(message_id, sender_id, str(action.get("text", "")))
        elif action.get("action") == "delete":
            applied = self.storage.delete_message(message_id, sender_id)
        elif action.get("action") == "replace":
            kind = str(action.get("kind", ""))
            encoded = action.pop("file_data", "")
            try:
                path = self.storage.safe_download_path(action["event_id"], action.get("file_name", "replacement"))
                path.write_bytes(base64.b64decode(encoded, validate=True))
                allowed, _error_key, mime = validate_attachment(path, kind)
                if allowed:
                    applied = self.storage.replace_message_file(
                        message_id, sender_id, kind, str(path), action.get("file_name", path.name), mime,
                    )
                if not applied:
                    path.unlink(missing_ok=True)
            except (OSError, ValueError):
                applied = False
        if applied and original.get("room_id") == self.current_room:
            self._render_messages()
        return False

    def _link_markup(self, value: str) -> str:
        output, position = [], 0
        for match in URL_RE.finditer(value):
            output.append(html.escape(value[position:match.start()]))
            url = match.group(0).rstrip(".,);]")
            suffix = match.group(0)[len(url):]
            output.append(f'<a href="{html.escape(url, quote=True)}">{html.escape(url)}</a>{html.escape(suffix)}')
            position = match.end()
        output.append(html.escape(value[position:]))
        return "".join(output)

    def _open_link(self, _label, uri: str) -> bool:
        if uri.startswith(("http://", "https://")):
            Gio.AppInfo.launch_default_for_uri(uri, None)
        return True

    def _open_path(self, path: Path) -> None:
        if path.exists():
            Gio.AppInfo.launch_default_for_uri(path.resolve().as_uri(), None)

    def _scroll_bottom(self) -> bool:
        adjustment = self.message_scroller.get_vadjustment()
        adjustment.set_value(max(0, adjustment.get_upper() - adjustment.get_page_size()))
        return False

    def _update_peers(self, peers: list[PeerInfo]) -> bool:
        current_ids = {peer.user_id for peer in peers}
        new_ids = current_ids - self.known_peer_ids
        self.peers = peers
        self.known_peer_ids = current_ids
        addresses = ", ".join(item["address"] for item in self.network.local_ips) if self.network else ""
        self.status_text.set_text(f"{self.t('online')} • {len(peers)} • {self.t('local_ip')}: {addresses or '127.0.0.1'} • TCP {self.network.tcp_port if self.network else '-'}")
        self._render_people()
        self._render_status_feed()
        for peer in peers:
            self.storage.remember_peer_ip(peer.ip)
            if peer.user_id not in new_ids:
                continue
            is_teacher = peer.profile.get("role") == "teacher"
            title = self.t("teacher_online") if is_teacher else self.t("friend_online")
            detail = f"{peer.profile.get('full_name', self.t('unknown_user'))} • {peer.profile.get('school_class', '')}/{peer.profile.get('room', '')}"
            self._notify(title, detail, "online")
        own_status = self.statuses.get(self.identity.user_id)
        if new_ids and own_status and self.network:
            self.network.send_status({key: value for key, value in own_status.items() if key not in {"sender_id", "file_path"}})
        return False

    def _render_people(self) -> None:
        if not hasattr(self, "student_list") or not hasattr(self, "teacher_list"):
            return
        clear_box(self.student_list)
        clear_box(self.teacher_list)
        own_ip = self.network.local_ips[0]["address"] if self.network and self.network.local_ips else "127.0.0.1"
        entries = [(self.identity.user_id, self.profile.public(), own_ip, True)]
        entries += [(peer.user_id, peer.profile, peer.ip, False) for peer in self.peers]
        for user_id, profile, ip, own in entries:
            container = self.teacher_list if profile.get("role") == "teacher" else self.student_list
            container.pack_start(self._person_button(user_id, profile, ip, own), False, False, 0)
        for container, empty_key in ((self.student_list, "no_students_online"), (self.teacher_list, "no_teachers_online")):
            if not container.get_children():
                container.pack_start(label(self.t(empty_key), "online-empty", 0.5), False, False, 8)
            container.show_all()

    def _person_button(self, user_id: str, profile: dict[str, Any], ip: str, own: bool) -> Gtk.Widget:
        chat_button = Gtk.Button()
        chat_button.set_relief(Gtk.ReliefStyle.NONE)
        chat_button.set_sensitive(not own)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        row.get_style_context().add_class("person-row")
        row.pack_start(profile_avatar(profile, 40), False, False, 0)
        row.pack_start(label("●", "online-dot"), False, False, 0)
        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        name = profile.get("full_name", self.t("unknown_user")) + (f" ({self.t('you')})" if own else "")
        details.pack_start(label(name, "person-name"), False, False, 0)
        extra = profile.get("subject") if profile.get("role") == "teacher" else profile.get("school_class", "")
        detail_text = f"{extra} • {profile.get('room', '')}\n{ip} • {user_id[:15]}"
        details.pack_start(label(detail_text, "person-detail"), False, False, 0)
        row.pack_start(details, True, True, 0)
        chat_button.add(row)
        if not own:
            chat_button.connect(
                "clicked",
                lambda _button, uid=user_id, person_name=profile.get("full_name", self.t("unknown_user")): self.select_direct(uid, person_name),
            )
        return chat_button

    def _refresh_online(self, *_args) -> None:
        if not self.network:
            return
        self.status_text.set_text(self.t("refreshing_online"))
        self.network.refresh_discovery()

        def finish_refresh() -> bool:
            if self.network:
                addresses = ", ".join(item["address"] for item in self.network.local_ips) or "127.0.0.1"
                self.status_text.set_text(f"{self.t('online')} • {len(self.peers)} • {self.t('local_ip')}: {addresses} • TCP {self.network.tcp_port}")
            return False

        GLib.timeout_add_seconds(3, finish_refresh)

    def _status_summary(self, status: dict[str, Any]) -> str:
        kind = status.get("status_kind", "text")
        if kind == "emotion":
            return f"{self.t('status_by')}: {status.get('emotion', '😊')} {status.get('text', '')}"
        if kind == "image":
            caption = status.get("text", "").strip()
            return f"🖼 {caption or status.get('file_name', self.t('status_image'))}"
        return f"{self.t('status_by')}: {status.get('text', '')}"

    def _set_status_dialog(self, *_args) -> None:
        dialog = Gtk.Dialog(title=self.t("set_status"), transient_for=self, modal=True)
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("clear_status"), 1, self.t("publish_status"), Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(10); box.set_margin_top(16); box.set_margin_bottom(16); box.set_margin_start(16); box.set_margin_end(16)
        box.add(label(self.t("status_compose_hint"), "muted"))
        entry = Gtk.Entry()
        entry.set_placeholder_text(self.t("status_placeholder"))
        emotion = Gtk.ComboBoxText()
        emotion.append("", self.t("no_emotion"))
        for emotion_value in ("😊", "😀", "🤓", "😎", "🤔", "😴", "😢", "🎉", "📚"):
            emotion.append(emotion_value, emotion_value)
        emotion.set_active(0)
        selected: dict[str, Path | None] = {"path": None}
        picture_label = label(self.t("no_status_image"), "status-selected-file")
        picture_button = Gtk.Button(label="🖼  " + self.t("choose_status_image"))

        def choose_picture(_button) -> None:
            path = self._choose_media_file("image", self.t("choose_status_image"), dialog)
            if path:
                selected["path"] = path
                picture_label.set_text(path.name)

        picture_button.connect("clicked", choose_picture)
        box.add(entry)
        box.add(emotion)
        box.add(picture_button)
        box.add(picture_label)
        dialog.show_all()
        response = dialog.run()
        text_value = entry.get_text().strip()[:180]
        emotion_value = emotion.get_active_id() or ""
        dialog.destroy()
        if response == 1:
            self.statuses.pop(self.identity.user_id, None)
            if self.network:
                self.network.send_status({"status_id": uuid.uuid4().hex, "status_kind": "none", "timestamp": time.time(), "profile": self.profile.public(include_photo=False)})
            self._render_people()
            self._render_status_feed()
        elif response == Gtk.ResponseType.OK and selected["path"]:
            self._publish_status_image(selected["path"], text_value)
        elif response == Gtk.ResponseType.OK and emotion_value:
            self._publish_status("emotion", text=text_value, emotion=emotion_value)
        elif response == Gtk.ResponseType.OK and text_value:
            self._publish_status("text", text=text_value)

    def _publish_status(self, status_kind: str, **values) -> None:
        status = {
            "status_id": uuid.uuid4().hex, "status_kind": status_kind, "timestamp": time.time(),
            "sender_id": self.identity.user_id, "profile": self.profile.public(include_photo=False), **values,
        }
        self.statuses[self.identity.user_id] = dict(status)
        if self.network:
            self.network.send_status({key: value for key, value in status.items() if key not in {"sender_id", "file_path"}})
        self._render_people()
        self._render_status_feed()

    def _choose_status_image(self) -> None:
        path = self._choose_media_file("image", self.t("choose_status_image"))
        if path:
            self._publish_status_image(path)

    def _publish_status_image(self, path: Path, caption: str = "") -> None:
        allowed, error_key, mime = validate_attachment(path, "image")
        if not allowed:
            self._error(self.t("attachment_error"), self.t(error_key or "invalid_type"))
            return
        try:
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        except OSError as error:
            self._error(self.t("attachment_error"), str(error))
            return
        self._publish_status("image", text=caption[:180], file_name=path.name, mime=mime, file_data=encoded, file_path=str(path))

    def _receive_status(self, status: dict[str, Any]) -> bool:
        sender_id = str(status.get("sender_id", ""))
        if status.get("status_kind") == "none":
            self.statuses.pop(sender_id, None)
            self._render_people()
            self._render_status_feed()
            return False
        if status.get("status_kind") == "image":
            encoded = status.pop("file_data", "")
            if not isinstance(encoded, str) or len(encoded) > ((IMAGE_LIMIT + 2) // 3) * 4 + 4:
                return False
            try:
                raw = base64.b64decode(encoded, validate=True)
                if len(raw) > IMAGE_LIMIT:
                    return False
                path = self.storage.safe_download_path(status["status_id"], status.get("file_name", "status-image"))
                path.write_bytes(raw)
                allowed, _error_key, _mime = validate_attachment(path, "image")
                if not allowed:
                    path.unlink(missing_ok=True)
                    return False
                status["file_path"] = str(path)
            except (OSError, ValueError):
                return False
        self.statuses[sender_id] = status
        self._render_people()
        self._render_status_feed()
        profile = status.get("profile", {})
        sender = profile.get("full_name", self.t("unknown_user"))
        self._notify(self.t("new_status"), f"{sender}: {self._status_summary(status)}", "status")
        return False

    def _new_group_dialog(self, *_args) -> None:
        if self.profile.role != "teacher":
            self._error(self.t("new_group"), self.t("teacher_only")); return
        dialog = Gtk.Dialog(title=self.t("new_group"), transient_for=self, modal=True)
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("create_group"), Gtk.ResponseType.OK)
        box = dialog.get_content_area(); box.set_spacing(8); box.set_margin_top(12); box.set_margin_bottom(12); box.set_margin_start(12); box.set_margin_end(12)
        name_entry = Gtk.Entry(); name_entry.set_placeholder_text(self.t("group_name")); box.add(name_entry)
        box.add(label(self.t("group_members"), "field-label"))
        checks = []
        for peer in self.peers:
            check = Gtk.CheckButton(label=f"{peer.profile.get('full_name', 'Unknown')} • {self.t(peer.profile.get('role', 'student'))}")
            checks.append((check, peer.user_id)); box.add(check)
        dialog.show_all(); response = dialog.run()
        group_name = name_entry.get_text().strip()[:80]
        selected = [user_id for check, user_id in checks if check.get_active()]
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        if not group_name or not selected:
            self._error(self.t("new_group"), self.t("group_members")); return
        group_id = f"group:{self.identity.user_id}:{uuid.uuid4().hex[:10]}"
        group = {"group_id": group_id, "name": group_name, "owner_id": self.identity.user_id, "members": [self.identity.user_id, *selected], "timestamp": time.time()}
        self.groups[group_id] = group
        self._add_dynamic_room_button(group_id, "👥 " + group_name, self.group_list)
        if self.network:
            self.network.send_group_definition(group, group["members"])
        self.select_room(group_id)

    def _receive_group(self, group: dict[str, Any]) -> bool:
        sender_id = str(group.get("sender_id", ""))
        peer = next((item for item in self.peers if item.user_id == sender_id), None)
        if not peer or peer.profile.get("role") != "teacher" or group.get("owner_id") != sender_id:
            return False
        group_id = str(group.get("group_id", "")); name = str(group.get("name", "")).strip()[:80]
        members = group.get("members", [])
        if not group_id.startswith("group:") or not name or not isinstance(members, list) or self.identity.user_id not in members:
            return False
        self.groups[group_id] = {"group_id": group_id, "name": name, "owner_id": sender_id, "members": members}
        self._add_dynamic_room_button(group_id, "👥 " + name, self.group_list)
        self._notify(self.t("new_group"), name, "message")
        return False

    def _broadcast_dialog(self, *_args) -> None:
        if self.profile.role != "teacher":
            self._error(self.t("broadcast"), self.t("teacher_only")); return
        dialog = Gtk.Dialog(title=self.t("broadcast_title"), transient_for=self, modal=True)
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("send"), Gtk.ResponseType.OK)
        box = dialog.get_content_area(); box.set_margin_top(14); box.set_margin_bottom(14); box.set_margin_start(14); box.set_margin_end(14)
        entry = Gtk.Entry(); entry.set_placeholder_text(self.t("broadcast_text")); box.add(entry)
        dialog.show_all(); response = dialog.run(); content = entry.get_text().strip()[:1000]; dialog.destroy()
        if response == Gtk.ResponseType.OK and content:
            self._send_message(self._make_message("broadcast", content, room_id="broadcasts"))

    def _grade_dialog(self, *_args) -> None:
        if self.profile.role != "teacher":
            self._error(self.t("send_grade"), self.t("teacher_only")); return
        students = [peer for peer in self.peers if peer.profile.get("role") == "student"]
        if not students:
            self._error(self.t("send_grade"), self.t("direct_unavailable")); return
        dialog = Gtk.Dialog(title=self.t("grade_title"), transient_for=self, modal=True)
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("send"), Gtk.ResponseType.OK)
        box = dialog.get_content_area(); box.set_spacing(8); box.set_margin_top(12); box.set_margin_bottom(12); box.set_margin_start(12); box.set_margin_end(12)
        recipient = Gtk.ComboBoxText()
        for peer in students:
            recipient.append(peer.user_id, peer.profile.get("full_name", "Unknown"))
        recipient.set_active(0)
        exam = Gtk.Entry(); exam.set_placeholder_text(self.t("exam_name"))
        score = Gtk.Entry(); score.set_placeholder_text(self.t("score"))
        notes = Gtk.Entry(); notes.set_placeholder_text(self.t("notes"))
        for key, widget in (("recipient", recipient), ("exam_name", exam), ("score", score), ("notes", notes)):
            box.add(self._form_row(key, widget))
        dialog.show_all(); response = dialog.run()
        target = recipient.get_active_id(); exam_text = exam.get_text().strip()[:120]; score_text = score.get_text().strip()[:40]; notes_text = notes.get_text().strip()[:500]
        dialog.destroy()
        if response != Gtk.ResponseType.OK or not target or not exam_text or not score_text:
            return
        peer = next(item for item in students if item.user_id == target)
        room_id = "direct:" + ":".join(sorted((self.identity.user_id, target)))
        self.direct_rooms[room_id] = {"user_id": target, "name": peer.profile.get("full_name", "Unknown")}
        self._add_dynamic_room_button(room_id, "👤 " + self.direct_rooms[room_id]["name"], self.direct_list)
        text_value = f"📊 {exam_text}\n{self.t('score')}: {score_text}"
        if notes_text:
            text_value += f"\n{self.t('notes')}: {notes_text}"
        self._send_message(self._make_message("grade", text_value, room_id=room_id, exam=exam_text, score=score_text, notes=notes_text))
        self.select_room(room_id)

    # Dialogs, notifications, local files, and hardware capture ----------
    def _notify(self, title: str, body: str, category: str) -> None:
        """Send a desktop notification and keep a visible in-app count."""
        self.notification_count += 1
        if hasattr(self, "notification_button"):
            self.notification_button.set_label(f"🔔 {self.notification_count}")
        notification = Gio.Notification.new(title)
        notification.set_body(body or APP_NAME)
        notification.set_icon(Gio.ThemedIcon.new("tl.edukasaun.EdukaKonekta"))
        if category in {"broadcast", "online"}:
            notification.set_priority(Gio.NotificationPriority.HIGH)
        application = self.get_application()
        if application:
            application.send_notification(f"{category}-{uuid.uuid4().hex}", notification)
        self.set_urgency_hint(True)

    def _clear_notification_count(self, *_args) -> None:
        self.notification_count = 0
        if hasattr(self, "notification_button"):
            self.notification_button.set_label("🔔 0")
        self.set_urgency_hint(False)

    def _choose_media_file(self, kind: str, title: str | None = None, parent: Gtk.Window | None = None) -> Path | None:
        """Use GTK's in-process chooser so folders, mounted drives, and USB work."""
        chooser = Gtk.FileChooserDialog(
            title=title or f"{self.t('upload_local')} • {self.t(kind)}",
            parent=parent or self,
            action=Gtk.FileChooserAction.OPEN,
            buttons=(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("open"), Gtk.ResponseType.ACCEPT),
        )
        chooser.set_modal(True)
        chooser.set_local_only(True)
        chooser.set_select_multiple(False)
        file_filter = Gtk.FileFilter()
        file_filter.set_name(self.t(kind))
        if kind != "document":
            file_filter.add_mime_type(kind + "/*")
        patterns = {
            "image": ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.gif"),
            "video": ("*.mp4", "*.webm", "*.mkv", "*.mov", "*.avi"),
            "audio": ("*.ogg", "*.opus", "*.mp3", "*.wav", "*.m4a", "*.flac"),
        }
        for pattern in patterns.get(kind, ("*",)):
            file_filter.add_pattern(pattern)
            file_filter.add_pattern(pattern.upper())
        chooser.add_filter(file_filter)

        home = Path.home()
        folder_name = {"image": "Pictures", "video": "Videos", "audio": "Music"}.get(kind, "Downloads")
        initial = home / folder_name
        if initial.is_dir():
            chooser.set_current_folder(str(initial))
        shortcut_candidates = [
            home / "Pictures", home / "Videos", home / "Music", home / "Downloads",
            Path("/media") / home.name, Path("/run/media") / home.name,
        ]
        for shortcut in shortcut_candidates:
            if not shortcut.is_dir():
                continue
            try:
                chooser.add_shortcut_folder(str(shortcut))
            except GLib.Error:
                pass
        response = chooser.run()
        filename = chooser.get_filename()
        chooser.destroy()
        if response != Gtk.ResponseType.ACCEPT or not filename:
            return None
        return Path(filename)

    def _choose_attachment(self, kind: str) -> None:
        path = self._choose_media_file(kind)
        if path:
            self._send_file_path(path, kind)

    def _send_file_path(self, path: Path, kind: str) -> bool:
        allowed, error_key, mime = validate_attachment(path, kind)
        if not allowed:
            self._error(self.t("attachment_error"), self.t(error_key or "invalid_type"))
            return False
        try:
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        except OSError as error:
            self._error(self.t("attachment_error"), str(error))
            return False
        message = self._make_message(kind, file_name=path.name, mime=mime, file_data=encoded, file_path=str(path))
        self._send_message(message)
        return True

    def _show_devices_dialog(self, *_args) -> None:
        cameras = self.device_manager.video_devices()
        microphones = self.device_manager.audio_devices()
        camera_text = "\n".join(f"• {item.name} ({item.source})" for item in cameras) or self.t("no_webcam")
        microphone_text = "\n".join(f"• {item.name}" for item in microphones) or self.t("no_microphone")
        ffmpeg_text = self.t("capture_ready") if self.device_manager.ffmpeg_available else self.t("ffmpeg_missing")
        detail = (
            f"{self.t('webcams')}:\n{camera_text}\n\n"
            f"{self.t('microphones')}:\n{microphone_text}\n\n{ffmpeg_text}\n\n"
            f"{self.t('device_controls_hint')}"
        )
        dialog = Gtk.MessageDialog(
            self, Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.OK,
            self.t("media_devices"),
        )
        dialog.format_secondary_text(detail)
        dialog.run()
        dialog.destroy()

    def _select_device(self, title: str, devices: list[MediaDevice]) -> MediaDevice | None:
        if not devices:
            return None
        if len(devices) == 1:
            return devices[0]
        dialog = Gtk.Dialog(title=title, transient_for=self, modal=True)
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("select"), Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_margin_top(14); box.set_margin_bottom(14); box.set_margin_start(14); box.set_margin_end(14)
        combo = Gtk.ComboBoxText()
        for index, device in enumerate(devices):
            combo.append(str(index), f"{device.name} • {device.source}")
        combo.set_active(0)
        box.add(combo)
        dialog.show_all()
        response = dialog.run()
        selected = combo.get_active()
        dialog.destroy()
        if response != Gtk.ResponseType.OK or selected < 0:
            return None
        return devices[selected]

    def _capture_photo(self, *_args) -> None:
        cameras = self.device_manager.video_devices()
        if not cameras:
            self._error(self.t("capture_photo"), self.t("no_webcam"))
            return
        camera = self._select_device(self.t("select_webcam"), cameras)
        if camera is None:
            return
        output = self.device_manager.capture_path(datetime.now().strftime("webcam-photo-%Y%m%d-%H%M%S"), ".jpg")
        success, detail = self.device_manager.capture_photo(camera, output)
        if not success:
            output.unlink(missing_ok=True)
            self._error(self.t("capture_failed"), detail or self.t("capture_failed"))
            return
        self._send_file_path(output, "image")

    def _record_media(self, kind: str) -> None:
        cameras = self.device_manager.video_devices() if kind == "video" else []
        microphones = self.device_manager.audio_devices()
        if kind == "video" and not cameras:
            self._error(self.t("record_video"), self.t("no_webcam"))
            return
        if kind == "audio" and not microphones:
            self._error(self.t("record_voice"), self.t("no_microphone"))
            return
        if not self.device_manager.ffmpeg_available:
            self._error(self.t("media_devices"), self.t("ffmpeg_missing"))
            return

        title = self.t("record_video") if kind == "video" else self.t("record_voice")
        setup = Gtk.Dialog(title=title, transient_for=self, modal=True)
        setup.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("start_recording"), Gtk.ResponseType.OK)
        box = setup.get_content_area()
        box.set_spacing(8)
        box.set_margin_top(14); box.set_margin_bottom(14); box.set_margin_start(14); box.set_margin_end(14)
        camera_combo = None
        if kind == "video":
            camera_combo = Gtk.ComboBoxText()
            for index, camera in enumerate(cameras):
                camera_combo.append(str(index), f"{camera.name} • {camera.source}")
            camera_combo.set_active(0)
            box.add(self._form_row("webcam", camera_combo))
        microphone_combo = Gtk.ComboBoxText()
        if kind == "video":
            microphone_combo.append("-1", self.t("video_without_audio"))
        for index, microphone in enumerate(microphones):
            microphone_combo.append(str(index), microphone.name)
        microphone_combo.set_active(1 if kind == "video" and microphones else 0)
        box.add(self._form_row("microphone", microphone_combo))
        maximum = 30 if kind == "video" else 60
        duration = Gtk.SpinButton.new_with_range(1, maximum, 1)
        duration.set_value(10 if kind == "video" else 30)
        box.add(self._form_row("recording_seconds", duration))
        setup.show_all()
        response = setup.run()
        seconds = duration.get_value_as_int()
        camera_index = camera_combo.get_active() if camera_combo else -1
        microphone_id = microphone_combo.get_active_id()
        setup.destroy()
        if response != Gtk.ResponseType.OK:
            return
        camera = cameras[camera_index] if kind == "video" and camera_index >= 0 else None
        microphone = microphones[int(microphone_id)] if microphone_id not in {None, "-1"} else None
        suffix = ".mp4" if kind == "video" else ".ogg"
        stem = datetime.now().strftime("webcam-video-%Y%m%d-%H%M%S" if kind == "video" else "voice-%Y%m%d-%H%M%S")
        output = self.device_manager.capture_path(stem, suffix)
        try:
            process = self.device_manager.start_recording(kind, output, seconds, camera, microphone)
        except (OSError, RuntimeError, ValueError) as error:
            self._error(self.t("capture_failed"), str(error))
            return
        self.active_capture = process
        progress = Gtk.Dialog(title=title, transient_for=self, modal=True)
        progress.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("stop_and_send"), Gtk.ResponseType.OK)
        progress.set_deletable(False)
        progress_box = progress.get_content_area()
        progress_box.set_spacing(10)
        progress_box.set_margin_top(18); progress_box.set_margin_bottom(18); progress_box.set_margin_start(18); progress_box.set_margin_end(18)
        recording_label = label("", "recording-label", 0.5)
        progress_box.add(recording_label)
        started = time.monotonic()
        timer_state = {"active": True}

        def update_recording() -> bool:
            elapsed = min(seconds, int(time.monotonic() - started))
            recording_label.set_text(f"●  {self.t('recording')}  {elapsed}/{seconds} {self.t('seconds')}")
            if process.poll() is not None or elapsed >= seconds:
                timer_state["active"] = False
                progress.response(Gtk.ResponseType.OK)
                return False
            return True

        timer_id = GLib.timeout_add(250, update_recording)
        recording_label.set_text(f"●  {self.t('recording')}  0/{seconds} {self.t('seconds')}")
        progress.show_all()
        result = progress.run()
        if timer_state["active"]:
            GLib.source_remove(timer_id)
            timer_state["active"] = False
        detail = self.device_manager.stop_recording(process)
        self.active_capture = None
        progress.destroy()
        if result != Gtk.ResponseType.OK:
            output.unlink(missing_ok=True)
            return
        if not output.is_file() or output.stat().st_size == 0:
            output.unlink(missing_ok=True)
            self._error(self.t("capture_failed"), detail or self.t("capture_failed"))
            return
        self._send_file_path(output, kind)

    def _open_emoji(self, button) -> None:
        popover = Gtk.Popover.new(button)
        grid = Gtk.Grid(column_spacing=5, row_spacing=5, margin=10)
        for index, emotion in enumerate(["😀", "😂", "😊", "😍", "😎", "🤔", "😢", "😮", "👍", "👏", "🙏", "❤️", "🎉", "📚", "✏️", "🇹🇱"]):
            choice = Gtk.Button(label=emotion)
            choice.set_relief(Gtk.ReliefStyle.NONE)
            choice.connect("clicked", lambda _button, value=emotion: self._insert_emoji(value, popover))
            grid.attach(choice, index % 8, index // 8, 1, 1)
        popover.add(grid)
        popover.show_all()

    def _insert_emoji(self, value: str, popover: Gtk.Popover) -> None:
        position = self.message_entry.get_position()
        current = self.message_entry.get_text()
        self.message_entry.set_text(current[:position] + value + current[position:])
        self.message_entry.set_position(position + len(value))
        self.message_entry.grab_focus()
        popover.popdown()

    def _connect_ip_dialog(self, *_args) -> None:
        dialog = Gtk.Dialog(title=self.t("manual_ip_title"), transient_for=self, modal=True)
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("connect"), Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_margin_top(16); box.set_margin_bottom(16); box.set_margin_start(16); box.set_margin_end(16)
        text = label(self.t("manual_ip_text"))
        text.set_line_wrap(True)
        box.add(text)
        entry = Gtk.Entry()
        entry.set_placeholder_text("192.168.1.25")
        box.add(entry)
        dialog.show_all()
        response = dialog.run()
        value = entry.get_text()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            try:
                host = validate_ip(value)
                if self.network:
                    self.network.connect_ip(host)
            except ValueError:
                self._error(self.t("manual_ip_title"), self.t("ip_address") + ": " + value)

    def show_about(self) -> None:
        dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        dialog.set_program_name(APP_NAME)
        dialog.set_version(f"{VERSION} {CHANNEL}")
        dialog.set_logo(Gtk.IconTheme.get_default().load_icon("tl.edukasaun.EdukaKonekta", 96, 0) if Gtk.IconTheme.get_default().has_icon("tl.edukasaun.EdukaKonekta") else GdkPixbuf.Pixbuf.new_from_file_at_scale(asset("eduka-konekta.svg"), 96, 96, True))
        addresses = ", ".join(item["address"] for item in self.network.local_ips) if self.network else ""
        dialog.set_comments(
            self.t("about_body") + "\n\n" + self.t("session_privacy") + "\n\n" +
            self.t("network_warning") + "\n\n" + self.t("local_ip") + ": " + (addresses or "127.0.0.1") +
            "\n" + self.t("identity") + ": " + self.identity.user_id + "\n" + self.t("identity_note")
        )
        dialog.set_authors([self.t("developed_by")])
        dialog.set_copyright(self.t("copyright"))
        dialog.set_website("https://edukasaunos.tl")
        dialog.set_website_label("edukasaunos.tl")
        dialog.run()
        dialog.destroy()

    def _edit_profile(self) -> None:
        self.show_login()

    def _confirm_logout(self) -> None:
        dialog = Gtk.MessageDialog(
            self, Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.NONE,
            self.t("logout_confirm"),
        )
        dialog.format_secondary_text(self.t("logout_detail"))
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("logout"), Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        if self.network:
            self.network.stop()
            self.network = None
        self.statuses.clear()
        self.groups.clear()
        self.direct_rooms.clear()
        self.peers.clear()
        self.known_peer_ids.clear()
        self.storage.logout()
        self.profile = None
        self.selected_photo_b64 = ""
        self.selected_photo_mime = ""
        self.device_manager = DeviceManager(self.storage.session_dir / "captures")
        self.show_login()

    def _confirm_clear(self) -> None:
        dialog = Gtk.MessageDialog(self, Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.NONE, self.t("confirm_clear"))
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("clear"), Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.storage.clear_room(self.current_room)
            self._render_messages()

    def _error(self, title: str, detail: str) -> None:
        dialog = Gtk.MessageDialog(self, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, title)
        dialog.format_secondary_text(detail)
        dialog.run()
        dialog.destroy()

    def _replace_root(self, widget: Gtk.Widget) -> None:
        child = self.get_child()
        if child:
            self.remove(child)
        self.add(widget)
        self.show_all()
