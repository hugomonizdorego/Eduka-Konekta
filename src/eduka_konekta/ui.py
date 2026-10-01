"""GTK 3 interface: login, application shell and school chat."""

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
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

from . import APP_NAME, CHANNEL, VERSION
from .devices import DeviceManager, MediaDevice
from .i18n import LANGUAGES, tr
from .models import IMAGE_LIMIT, Profile, rooms_for, slug, validate_attachment, validate_ip, validate_profile, validate_profile_photo
from .moderation import RateLimiter, filter_text
from .network import P2PNetwork, PeerInfo
from .school import SchoolManager
from .storage import MESSAGE_EDIT_WINDOW
from .ui_school import SchoolPagesMixin
from .widgets import (
    add_class, asset, asset_image, badge, button, card, clear_box, framed, label, logo_image, logo_pixbuf, margins,
    profile_avatar, scrolled, text_of, text_view,
)

LOG = logging.getLogger(__name__)
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
ROOM_ICONS = {"all_schools": "🏫", "broadcasts": "📣", "my_school": "🏛", "my_class": "📚", "teachers": "🧑‍🏫"}
NAV_ITEMS = (
    ("chat", "💬", "nav_chat"),
    ("exams", "📝", "nav_exams"),
    ("attendance", "✅", "nav_attendance"),
    ("rules", "📜", "nav_rules"),
    ("network", "📶", "nav_network"),
    ("settings", "⚙", "nav_settings"),
)


class EdukaWindow(SchoolPagesMixin, Gtk.ApplicationWindow):
    def __init__(self, application, storage, identity):
        super().__init__(application=application, title=f"{APP_NAME} {VERSION}")
        self.storage = storage
        self.identity = identity
        self.profile = storage.load_profile()
        self.language = self.profile.language if self.profile else self._system_language()
        self.network: P2PNetwork | None = None
        self.school: SchoolManager | None = None
        self.current_room = ""
        self.current_target_ids: list[str] = []
        self.current_page = "chat"
        self.room_buttons: dict[str, Gtk.ToggleButton] = {}
        self.room_labels: dict[str, str] = {}
        self.unread: dict[str, int] = {}
        self.nav_buttons: dict[str, Gtk.ToggleButton] = {}
        self._syncing = False
        self.peers: list[PeerInfo] = []
        self.statuses: dict[str, dict[str, Any]] = {}
        self.groups: dict[str, dict[str, Any]] = {}
        self.direct_rooms: dict[str, dict[str, str]] = {}
        self.device_manager = DeviceManager(storage.session_dir / "captures")
        self.known_peer_ids: set[str] = set()
        self.notification_count = 0
        self.active_capture = None
        self.rate_limiter = RateLimiter()
        self._tick_id = 0
        self._tick_count = 0
        self._css_provider: Gtk.CssProvider | None = None
        self._default_prefer_dark: bool | None = None
        self.selected_photo_b64 = self.profile.photo_b64 if self.profile else ""
        self.selected_photo_mime = self.profile.photo_mime if self.profile else "image/jpeg"
        self.set_default_size(1240, 780)
        self.set_size_request(920, 600)
        self.set_position(Gtk.WindowPosition.CENTER)
        icon = logo_pixbuf(128)
        if icon is not None:
            self.set_icon(icon)
        self._load_css()
        self.connect("delete-event", self._on_delete)
        if self.profile:
            self.show_chat()
        else:
            self.show_login()

    @staticmethod
    def _system_language() -> str:
        for name in GLib.get_language_names():
            code = name.split(".")[0]
            if code in LANGUAGES:
                return code
            base = code.split("_")[0]
            if base == "pt":
                return "pt_BR" if code.endswith("BR") else "pt_PT"
            if base in LANGUAGES:
                return base
        return "en"

    def t(self, key: str) -> str:
        return tr(self.language, key)

    def _appearance(self) -> str:
        """The active appearance: system (desktop theme), light or dark."""
        mode = self.storage.settings.get("appearance", "system")
        if mode == "system":
            # A theme that lacks the standard named colours cannot be followed.
            context = self.get_style_context()
            found, _colour = context.lookup_color("theme_bg_color")
            if not found:
                return "light"
        return mode if mode in {"system", "light", "dark"} else "system"

    def _load_css(self) -> None:
        mode = self._appearance()
        parts = [Path(asset(f"palette-{mode}.css")).read_text(encoding="utf-8")]
        if mode != "system":
            parts.append(Path(asset("widgets-eduka.css")).read_text(encoding="utf-8"))
        parts.append(Path(asset("style.css")).read_text(encoding="utf-8"))
        css = "\n".join(parts)
        if self.storage.settings.get("large_text"):
            css = re.sub(r"font-size:\s*(\d+(?:\.\d+)?)px", lambda m: f"font-size: {round(float(m.group(1)) * 1.2, 1)}px", css)
        settings = Gtk.Settings.get_default()
        if settings is not None:
            if self._default_prefer_dark is None:
                self._default_prefer_dark = settings.get_property("gtk-application-prefer-dark-theme")
            prefer_dark = {"dark": True, "light": False}.get(mode, self._default_prefer_dark)
            settings.set_property("gtk-application-prefer-dark-theme", prefer_dark)
        provider = Gtk.CssProvider()
        try:
            provider.load_from_data(css.encode("utf-8"))
        except GLib.Error as error:
            LOG.warning("Stylesheet could not be loaded: %s", error)
            return
        screen = Gdk.Screen.get_default()
        if not screen:
            return
        if self._css_provider:
            Gtk.StyleContext.remove_provider_for_screen(screen, self._css_provider)
        Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._css_provider = provider

    def _on_delete(self, *_args):
        if self.active_capture and self.active_capture.poll() is None:
            self.device_manager.stop_recording(self.active_capture)
            self.active_capture = None
        if self.network:
            self.network.stop()
        self.storage.close()
        return False

    # Login ---------------------------------------------------------------
    def show_login(self, values: dict[str, Any] | None = None) -> None:
        self._stop_tick()
        if self.network:
            self.network.stop()
            self.network = None
        existing = self.profile
        if values is None:
            values = {
                "full_name": existing.full_name if existing else "",
                "school": existing.school if existing else "",
                "role": existing.role if existing else "student",
                "age": existing.age if existing else 15,
                "class": existing.school_class if existing else "",
                "room": existing.room if existing else "",
                "subject": existing.subject if existing else "",
                "accepted": bool(existing),
            }
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        add_class(root, "login-root")

        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        add_class(hero, "login-hero")
        hero.set_size_request(380, -1)
        hero.pack_start(logo_image("eduka-konekta-logo-light.svg", 300), False, False, 6)
        hero.pack_start(label(self.t("welcome"), "hero-subtitle", 0.0, wrap=True), False, False, 0)
        for icon, key in (("💬", "hero_chat"), ("📝", "hero_exams"), ("✅", "hero_attendance"), ("📶", "hero_network")):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.pack_start(label(icon, "hero-icon"), False, False, 0)
            row.pack_start(label(self.t(key), "hero-feature", 0.0, wrap=True), True, True, 0)
            hero.pack_start(row, False, False, 0)
        hero.pack_end(label(f"{self.t('version')} {VERSION} {CHANNEL} • {self.t('no_password')}", "hero-footer", 0.0, wrap=True), False, False, 0)
        root.pack_start(hero, False, False, 0)

        form_side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        add_class(form_side, "login-form-side")
        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        center.set_halign(Gtk.Align.CENTER)
        margins(center, 28)
        form = card(spacing=12, css="card login-card")
        form.set_size_request(520, -1)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        titles.pack_start(label(self.t("sign_in") if not existing else self.t("edit_profile"), "login-heading"), False, False, 0)
        titles.pack_start(label(self.t("login_hint"), "muted", wrap=True), False, False, 0)
        top.pack_start(titles, True, True, 0)
        self.language_combo = Gtk.ComboBoxText()
        for code, name in LANGUAGES.items():
            self.language_combo.append(code, name)
        self.language_combo.set_active_id(self.language if self.language in LANGUAGES else "en")
        self.language_combo.set_valign(Gtk.Align.START)
        self.language_combo.connect("changed", self._language_changed)
        top.pack_end(self.language_combo, False, False, 0)
        form.pack_start(top, False, False, 0)

        role_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        add_class(role_box, "segmented")
        self.role_student = Gtk.RadioButton.new_with_label_from_widget(None, "🎒  " + self.t("student"))
        self.role_teacher = Gtk.RadioButton.new_with_label_from_widget(self.role_student, "🧑‍🏫  " + self.t("teacher"))
        for radio in (self.role_student, self.role_teacher):
            radio.set_mode(False)
            role_box.pack_start(radio, True, True, 0)
        self.role_teacher.set_active(values.get("role") == "teacher")
        self.role_student.connect("toggled", self._role_changed)
        form.pack_start(self._form_row("role", role_box), False, False, 0)

        self.name_entry = Gtk.Entry(text=values.get("full_name", ""))
        self.name_entry.set_placeholder_text(self.t("full_name_hint"))
        self.school_entry = Gtk.Entry(text=values.get("school", ""))
        self.school_entry.set_placeholder_text(self.t("school_hint"))
        self.age_spin = Gtk.SpinButton.new_with_range(5, 100, 1)
        self.age_spin.set_value(int(values.get("age", 15) or 15))
        self.class_entry = Gtk.Entry(text=values.get("class", ""))
        self.class_entry.set_placeholder_text(self.t("class_hint"))
        self.room_entry = Gtk.Entry(text=values.get("room", ""))
        self.room_entry.set_placeholder_text(self.t("room_hint"))
        self.subject_entry = Gtk.Entry(text=values.get("subject", ""))
        self.subject_entry.set_placeholder_text(self.t("subject_hint"))

        form.pack_start(self._form_row("full_name", self.name_entry), False, False, 0)
        form.pack_start(self._form_row("school", self.school_entry), False, False, 0)
        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        grid.set_column_homogeneous(True)
        grid.attach(self._form_row("class", self.class_entry), 0, 0, 1, 1)
        grid.attach(self._form_row("room", self.room_entry), 1, 0, 1, 1)
        grid.attach(self._form_row("age", self.age_spin), 0, 1, 1, 1)
        self.subject_row = self._form_row("subject", self.subject_entry)
        grid.attach(self.subject_row, 1, 1, 1, 1)
        form.pack_start(grid, False, False, 0)

        photo_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.photo_preview = profile_avatar({"photo_b64": self.selected_photo_b64, "full_name": values.get("full_name", "")}, 64)
        photo_box.pack_start(self.photo_preview, False, False, 0)
        photo_actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.photo_button = button("🖼  " + self.t("choose_photo"), self._choose_profile_photo)
        photo_actions.pack_start(self.photo_button, False, False, 0)
        self.photo_skip = Gtk.CheckButton(label=self.t("skip_photo"))
        self.photo_skip.set_active(not bool(self.selected_photo_b64))
        self.photo_skip.connect("toggled", self._photo_skip_toggled)
        photo_actions.pack_start(self.photo_skip, False, False, 0)
        photo_box.pack_start(photo_actions, True, True, 0)
        form.pack_start(self._form_row("profile_photo", photo_box), False, False, 0)

        rules_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.rules_check = Gtk.CheckButton(label=self.t("accept_rules"))
        self.rules_check.set_active(bool(values.get("accepted")))
        rules_row.pack_start(self.rules_check, True, True, 0)
        rules_row.pack_end(button(self.t("read_rules"), lambda *_: self._show_rules_dialog(), "flat-link"), False, False, 0)
        form.pack_start(rules_row, False, False, 0)

        self.form_error = label("", "error-text", 0.0, wrap=True)
        form.pack_start(self.form_error, False, False, 0)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        if existing:
            actions.pack_start(button(self.t("cancel"), lambda *_: self.show_chat()), False, False, 0)
        self.connect_button = button(self.t("continue"), self._submit_profile, "primary-button")
        actions.pack_end(self.connect_button, True, True, 0)
        form.pack_start(actions, False, False, 4)
        form.pack_start(label("🔒 " + self.t("identity_note"), "security-note", 0.0, wrap=True), False, False, 0)

        center.pack_start(form, False, False, 0)
        form_side.pack_start(scrolled(center), True, True, 0)
        root.pack_start(form_side, True, True, 0)
        self._replace_root(root)
        self._role_changed(self.role_student)
        self.photo_button.set_sensitive(not self.photo_skip.get_active())

    def _form_row(self, key: str, widget: Gtk.Widget) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        row.pack_start(label(self.t(key), "field-label"), False, False, 0)
        row.pack_start(widget, False, False, 0)
        return row

    def _login_values(self) -> dict[str, Any]:
        return {
            "full_name": self.name_entry.get_text(), "school": self.school_entry.get_text(),
            "role": "teacher" if self.role_teacher.get_active() else "student",
            "age": self.age_spin.get_value_as_int(), "class": self.class_entry.get_text(),
            "room": self.room_entry.get_text(), "subject": self.subject_entry.get_text(),
            "accepted": self.rules_check.get_active(),
        }

    def _language_changed(self, combo: Gtk.ComboBoxText) -> None:
        values = self._login_values()
        self.language = combo.get_active_id() or "en"
        self.show_login(values)

    def _role_changed(self, _radio) -> None:
        if hasattr(self, "subject_row"):
            self.subject_row.set_visible(self.role_teacher.get_active())

    def _show_rules_dialog(self) -> None:
        dialog = Gtk.Dialog(title=self.t("rules_title"), transient_for=self, modal=True)
        dialog.add_buttons(self.t("close"), Gtk.ResponseType.CLOSE)
        dialog.set_default_size(560, 520)
        box = dialog.get_content_area()
        margins(box, 16)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.pack_start(label(self.t("default_rules"), "rules-text", 0.0, wrap=True), False, False, 0)
        scroller = scrolled(content)
        scroller.set_vexpand(True)
        box.pack_start(scroller, True, True, 0)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def _choose_profile_photo(self, _button) -> None:
        path = self._choose_media_file("image", self.t("choose_photo"))
        if not path:
            return
        allowed, error_key, mime = validate_profile_photo(path)
        if not allowed:
            self._error(self.t("profile_photo"), self.t(error_key or "invalid_type"))
            return
        try:
            raw = path.read_bytes()
            GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 64, 64, True)
        except (OSError, GLib.Error) as error:
            self._error(self.t("profile_photo"), str(error))
            return
        self.selected_photo_b64 = base64.b64encode(raw).decode("ascii")
        self.selected_photo_mime = mime
        self._replace_photo_preview()
        self.photo_skip.set_active(False)

    def _replace_photo_preview(self) -> None:
        replacement = profile_avatar({"photo_b64": self.selected_photo_b64, "full_name": self.name_entry.get_text()}, 64)
        photo_box = self.photo_preview.get_parent()
        photo_box.remove(self.photo_preview)
        photo_box.pack_start(replacement, False, False, 0)
        photo_box.reorder_child(replacement, 0)
        self.photo_preview = replacement
        self.photo_preview.show()

    def _photo_skip_toggled(self, check: Gtk.CheckButton) -> None:
        skipped = check.get_active()
        self.photo_button.set_sensitive(not skipped)
        if skipped:
            self.selected_photo_b64 = ""
            self.selected_photo_mime = ""
            self._replace_photo_preview()

    def _submit_profile(self, _button) -> None:
        profile = Profile(
            full_name=" ".join(self.name_entry.get_text().split()), school=" ".join(self.school_entry.get_text().split()),
            role="teacher" if self.role_teacher.get_active() else "student", age=self.age_spin.get_value_as_int(),
            school_class=self.class_entry.get_text().strip(), room=self.room_entry.get_text().strip(),
            language=self.language, subject=self.subject_entry.get_text().strip() if self.role_teacher.get_active() else "",
            photo_b64=self.selected_photo_b64, photo_mime=self.selected_photo_mime or "image/jpeg",
        )
        errors = validate_profile(profile)
        if not self.rules_check.get_active():
            errors.append("rules_required")
        if errors:
            self.form_error.set_text(self.t("profile_error") + ":\n• " + "\n• ".join(self.t(item) for item in errors))
            return
        accepted = dict(self.storage.settings.get("rules_accepted", {}))
        accepted[slug(profile.full_name)] = time.time()
        self.storage.save_settings(rules_accepted=accepted)
        self.profile = profile
        self.storage.save_profile(profile)
        self.show_chat(restart_network=True)

    # Application shell ---------------------------------------------------
    def show_chat(self, restart_network: bool = True) -> None:
        assert self.profile is not None
        self.language = self.profile.language
        if restart_network or self.school is None:
            self.school = SchoolManager(self.storage.records_dir, self.identity.user_id, lambda: self.profile, self._send_school)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        add_class(root, "app-root")
        root.pack_start(self._build_topbar(), False, False, 0)
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        body.pack_start(self._build_navrail(), False, False, 0)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(120)
        self.stack.add_named(self._build_chat_page(), "chat")
        self.stack.add_named(self._build_exams_page(), "exams")
        self.stack.add_named(self._build_attendance_page(), "attendance")
        self.stack.add_named(self._build_rules_page(), "rules")
        self.stack.add_named(self._build_network_page(), "network")
        self.stack.add_named(self._build_settings_page(), "settings")
        body.pack_start(self.stack, True, True, 0)
        overlay = Gtk.Overlay()
        overlay.add(body)
        self.toast_revealer = Gtk.Revealer()
        self.toast_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        self.toast_revealer.set_halign(Gtk.Align.CENTER)
        self.toast_revealer.set_valign(Gtk.Align.END)
        self.toast_revealer.set_margin_bottom(24)
        self.toast_label = label("", "toast", 0.5, wrap=True)
        self.toast_label.set_max_width_chars(70)
        self.toast_revealer.add(self.toast_label)
        overlay.add_overlay(self.toast_revealer)
        root.pack_start(overlay, True, True, 0)
        root.pack_start(self._build_statusbar(), False, False, 0)
        self._replace_root(root)
        rooms = [room for room, _ in rooms_for(self.profile)]
        target_room = self.current_room if self.current_room in self.room_buttons else rooms[3]
        self.select_room(target_room)
        self._switch_page(self.current_page if self.current_page in self.nav_buttons else "chat")
        if restart_network or self.network is None:
            self._start_network()
        else:
            self._update_status_line()
            self._render_people()
        self._start_tick()

    def _build_topbar(self) -> Gtk.Box:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        add_class(bar, "topbar")
        bar.pack_start(asset_image(34), False, False, 0)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        titles.set_valign(Gtk.Align.CENTER)
        titles.pack_start(label(APP_NAME, "brand-name"), False, False, 0)
        titles.pack_start(label(self.profile.school, "brand-school"), False, False, 0)
        bar.pack_start(titles, False, False, 0)

        self.online_pill = button("● 0 " + self.t("online"), lambda *_: self._switch_page("network"), "online-pill")
        self.online_pill.set_tooltip_text(self.t("nav_network"))
        self.notification_button = button("🔔 0", self._clear_notification_count, "notification-counter", self.t("clear_notifications"))
        for widget in (self._build_profile_menu(), self.notification_button, self.online_pill):
            widget.set_valign(Gtk.Align.CENTER)
            bar.pack_end(widget, False, False, 0)
        return bar

    def _build_profile_menu(self) -> Gtk.MenuButton:
        menu_button = Gtk.MenuButton()
        add_class(menu_button, "profile-menu-button")
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        content.pack_start(profile_avatar(self.profile.public(), 30), False, False, 0)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        names.pack_start(label(self.profile.full_name, "menu-name"), False, False, 0)
        role_text = self.t(self.profile.role) + (f" • {self.profile.subject}" if self.profile.role == "teacher" else f" • {self.profile.school_class}")
        names.pack_start(label(role_text, "menu-role"), False, False, 0)
        content.pack_start(names, False, False, 0)
        content.pack_start(label("▾", "menu-caret"), False, False, 0)
        menu_button.add(content)
        menu = Gtk.Menu()
        for text_key, callback in (
            ("edit_profile", lambda *_: self._edit_profile()),
            ("set_status", self._set_status_dialog),
            ("nav_settings", lambda *_: self._switch_page("settings")),
            (None, None),
            ("about", lambda *_: self.show_about()),
            ("logout", lambda *_: self._confirm_logout()),
            ("quit", lambda *_: self.close()),
        ):
            if text_key is None:
                menu.append(Gtk.SeparatorMenuItem())
                continue
            item = Gtk.MenuItem(label=self.t(text_key))
            item.connect("activate", callback)
            menu.append(item)
        menu.show_all()
        menu_button.set_popup(menu)
        return menu_button

    def _build_navrail(self) -> Gtk.Box:
        rail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        add_class(rail, "navrail")
        self.nav_buttons = {}
        self.nav_labels: dict[str, Gtk.Label] = {}
        for name, icon, key in NAV_ITEMS:
            item = Gtk.ToggleButton()
            add_class(item, "nav-button")
            stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            stack.pack_start(label(icon, "nav-icon", 0.5), False, False, 0)
            text = label(self.t(key), "nav-label", 0.5)
            text.set_justify(Gtk.Justification.CENTER)
            text.set_line_wrap(True)
            text.set_max_width_chars(10)
            self.nav_labels[name] = text
            stack.pack_start(text, False, False, 0)
            item.add(stack)
            item.connect("toggled", self._nav_toggled, name)
            self.nav_buttons[name] = item
            rail.pack_start(item, False, False, 0)
        return rail

    def _nav_toggled(self, item: Gtk.ToggleButton, name: str) -> None:
        if self._syncing:
            return
        if item.get_active():
            self._switch_page(name)
        elif self.current_page == name:
            self._syncing = True
            item.set_active(True)
            self._syncing = False

    def _switch_page(self, name: str) -> None:
        if self.current_page == "exams" and name != "exams" and self.school:
            self._autosave_draft()
        self.current_page = name
        self._syncing = True
        for page, item in self.nav_buttons.items():
            item.set_active(page == name)
        self._syncing = False
        if hasattr(self, "stack"):
            self.stack.set_visible_child_name(name)
        renderers = {
            "exams": self._render_exams, "attendance": self._render_attendance,
            "rules": self._render_rules, "network": self._render_network,
        }
        if name in renderers:
            renderers[name]()

    def _build_statusbar(self) -> Gtk.Box:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        add_class(bar, "statusbar")
        self.status_dot = label("●", "status-dot-searching")
        self.status_text = label(self.t("connecting"), "status-text")
        self.status_text.set_ellipsize(Pango.EllipsizeMode.END)
        bar.pack_start(self.status_dot, False, False, 0)
        bar.pack_start(self.status_text, True, True, 0)
        bar.pack_end(label(f"ID {self.identity.user_id}", "fingerprint"), False, False, 0)
        return bar

    def _start_tick(self) -> None:
        self._stop_tick()
        self._tick_id = GLib.timeout_add_seconds(1, self._tick)

    def _stop_tick(self) -> None:
        if self._tick_id:
            GLib.source_remove(self._tick_id)
            self._tick_id = 0

    def _tick(self) -> bool:
        if not self.profile or not self.school:
            self._tick_id = 0
            return False
        self._tick_count += 1
        self._tick_school_pages()
        if self._tick_count % 15 == 0:
            self.school.resend()
        if self._tick_count % 10 == 0:
            self._update_status_line()
        if self._tick_count % 30 == 0:
            self._update_composer_state()
        if self.current_page == "network" and self._tick_count % 3 == 0:
            self._render_network()
        return True

    # Chat page -----------------------------------------------------------
    def _build_chat_page(self) -> Gtk.Widget:
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.pack1(self._build_rooms_panel(), False, False)
        inner = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        inner.pack1(self._build_conversation(), True, False)
        inner.pack2(self._build_people(), False, False)
        paned.pack2(inner, True, False)
        return paned

    def _build_rooms_panel(self) -> Gtk.Widget:
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        add_class(side, "rooms-panel")
        side.set_size_request(236, -1)
        self.room_buttons = {}
        self.room_labels = {}
        side.pack_start(label(self.t("rooms"), "section-label"), False, False, 0)
        self.room_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for room_id, key in rooms_for(self.profile):
            self._add_room_button(room_id, f"{ROOM_ICONS.get(key, '💬')}  {self.t(key)}", self.room_list)
        side.pack_start(self.room_list, False, False, 0)
        side.pack_start(label(self.t("groups"), "section-label"), False, False, 6)
        self.group_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for group_id, group in self.groups.items():
            self._add_room_button(group_id, "👥  " + group["name"], self.group_list)
        side.pack_start(self.group_list, False, False, 0)
        side.pack_start(label(self.t("direct_chats"), "section-label"), False, False, 6)
        self.direct_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for room_id, info in self.direct_rooms.items():
            self._add_room_button(room_id, "👤  " + info["name"], self.direct_list)
        side.pack_start(self.direct_list, False, False, 0)
        if self.profile.role == "teacher":
            tools = card(spacing=4, css="card teacher-tools")
            tools.pack_start(label(self.t("teacher_tools"), "section-label"), False, False, 0)
            for icon, key, callback in (
                ("👥", "new_group", self._new_group_dialog),
                ("📣", "broadcast", self._broadcast_dialog),
                ("📊", "send_grade", self._grade_dialog),
                ("📝", "create_exam", lambda *_: self._create_exam_dialog()),
            ):
                tools.pack_start(button(f"{icon}  {self.t(key)}", callback, "tool-button"), False, False, 0)
            side.pack_end(tools, False, False, 0)
        outer = scrolled(side)
        add_class(outer, "rooms-scroller")
        outer.set_size_request(236, -1)
        return outer

    def _add_room_button(self, room_id: str, text: str, container: Gtk.Box) -> None:
        if room_id in self.room_buttons:
            return
        item = Gtk.ToggleButton(label=text)
        add_class(item, "room-button")
        item.get_child().set_xalign(0.0)
        item.get_child().set_ellipsize(Pango.EllipsizeMode.END)
        item.connect("toggled", self._room_toggled, room_id)
        self.room_buttons[room_id] = item
        self.room_labels[room_id] = text
        container.pack_start(item, False, False, 0)
        container.show_all()
        self._refresh_room_button(room_id)

    def _add_dynamic_room_button(self, room_id: str, text: str, container: Gtk.Box) -> None:
        self._add_room_button(room_id, text, container)

    def _refresh_room_button(self, room_id: str) -> None:
        item = self.room_buttons.get(room_id)
        if not item:
            return
        count = self.unread.get(room_id, 0)
        locked = self.school.room_locked(room_id) if self.school else None
        text = self.room_labels.get(room_id, room_id) + ("  🔒" if locked else "") + (f"   ({count})" if count else "")
        item.set_label(text)
        item.get_child().set_xalign(0.0)
        item.get_child().set_ellipsize(Pango.EllipsizeMode.END)
        context = item.get_style_context()
        if count:
            context.add_class("has-unread")
        else:
            context.remove_class("has-unread")

    def _room_toggled(self, item: Gtk.ToggleButton, room_id: str) -> None:
        if self._syncing:
            return
        if item.get_active():
            self.select_room(room_id)
        elif self.current_room == room_id:
            self._syncing = True
            item.set_active(True)
            self._syncing = False

    def _build_conversation(self) -> Gtk.Box:
        area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        add_class(area, "conversation")
        area.pack_start(self._build_status_feed(), False, False, 0)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        add_class(header, "conversation-header")
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        self.room_title = label("", "room-title")
        self.room_subtitle = label("", "room-subtitle")
        self.room_subtitle.set_ellipsize(Pango.EllipsizeMode.END)
        titles.pack_start(self.room_title, False, False, 0)
        titles.pack_start(self.room_subtitle, False, False, 0)
        header.pack_start(titles, True, True, 0)
        self.lock_button = button("🔒 " + self.t("lock_room"), self._toggle_room_lock, "header-button")
        self.lock_button.set_no_show_all(True)
        self.lock_button.set_valign(Gtk.Align.CENTER)
        header.pack_end(self.lock_button, False, False, 0)
        clear = button("🧹", lambda *_: self._confirm_clear(), "header-button", self.t("clear_history"))
        clear.set_valign(Gtk.Align.CENTER)
        header.pack_end(clear, False, False, 0)
        area.pack_start(header, False, False, 0)

        self.lock_banner = label("", "lock-banner", 0.0, wrap=True)
        self.lock_banner.set_no_show_all(True)
        area.pack_start(self.lock_banner, False, False, 0)

        self.message_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        margins(self.message_list, 16)
        self.message_scroller = scrolled(self.message_list)
        add_class(self.message_scroller, "message-scroller")
        area.pack_start(self.message_scroller, True, True, 0)

        self.composer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        add_class(self.composer_box, "composer-area")
        composer_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        add_class(composer_toolbar, "composer-toolbar")
        media_actions = (
            ("😊", "emoji", self._open_emoji),
            ("🖼", "upload_image", lambda *_: self._choose_attachment("image")),
            ("🎬", "upload_video", lambda *_: self._choose_attachment("video")),
            ("🎵", "upload_audio", lambda *_: self._choose_attachment("audio")),
            ("📄", "upload_document", lambda *_: self._choose_attachment("document")),
            ("📷", "capture_photo", self._capture_photo),
            ("🎙", "record_voice", lambda *_: self._record_media("audio")),
            ("📹", "record_video", lambda *_: self._record_media("video")),
        )
        for text, tooltip, callback in media_actions:
            item = button(text, callback, "media-button", self.t(tooltip))
            item.set_relief(Gtk.ReliefStyle.NONE)
            composer_toolbar.pack_start(item, False, False, 0)
        self.composer_box.pack_start(composer_toolbar, False, False, 0)
        composer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        add_class(composer, "composer")
        self.message_entry = Gtk.Entry()
        self.message_entry.set_placeholder_text(self.t("message_placeholder"))
        self.message_entry.set_max_length(4000)
        self.message_entry.connect("activate", self._send_text)
        composer.pack_start(self.message_entry, True, True, 0)
        self.send_button = button(self.t("send") + "  ➤", self._send_text, "send-button")
        composer.pack_start(self.send_button, False, False, 0)
        self.composer_box.pack_start(composer, False, False, 0)
        area.pack_start(self.composer_box, False, False, 0)
        return area

    def _build_status_feed(self) -> Gtk.Box:
        feed = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        add_class(feed, "status-feed")
        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        heading.pack_start(label(self.t("status_feed"), "section-label"), True, True, 0)
        heading.pack_end(button("＋ " + self.t("set_status"), self._set_status_dialog, "small-button"), False, False, 0)
        feed.pack_start(heading, False, False, 0)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        scroller.set_size_request(-1, 86)
        self.status_feed_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.status_feed_box.set_margin_bottom(4)
        scroller.add(self.status_feed_box)
        feed.pack_start(scroller, False, False, 0)
        self._render_status_feed()
        return feed

    def _render_status_feed(self) -> None:
        if not hasattr(self, "status_feed_box") or not self.profile:
            return
        clear_box(self.status_feed_box)
        profile_map = {self.identity.user_id: self.profile.public()}
        profile_map.update({peer.user_id: peer.profile for peer in self.peers})
        entries = sorted(self.statuses.items(), key=lambda item: float(item[1].get("timestamp", 0)), reverse=True)
        if not entries:
            self.status_feed_box.pack_start(label(self.t("no_status_updates"), "status-empty", 0.0), False, False, 4)
        for user_id, status in entries:
            profile = profile_map.get(user_id) or status.get("profile", {})
            item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            item.set_size_request(210, 64)
            add_class(item, "status-card")
            item.pack_start(profile_avatar(profile, 36), False, False, 0)
            text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            name = label(profile.get("full_name", self.t("unknown_user")), "status-person")
            name.set_ellipsize(Pango.EllipsizeMode.END)
            name.set_max_width_chars(20)
            text_box.pack_start(name, False, False, 0)
            if status.get("status_kind") == "image" and status.get("file_path"):
                path = Path(status["file_path"])
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 120, 36, True)
                    text_box.pack_start(Gtk.Image.new_from_pixbuf(pixbuf), False, False, 0)
                except GLib.Error:
                    text_box.pack_start(label("🖼 " + path.name, "status-copy"), False, False, 0)
                event = Gtk.EventBox()
                event.add(item)
                event.set_tooltip_text(self.t("open_status_image"))
                event.connect("button-release-event", lambda *_args, selected=path: self._open_path(selected))
                item.pack_start(text_box, True, True, 0)
                self.status_feed_box.pack_start(event, False, False, 0)
                continue
            copy = label(self._status_summary(status), "status-copy", wrap=True)
            copy.set_max_width_chars(22)
            copy.set_lines(2)
            copy.set_ellipsize(Pango.EllipsizeMode.END)
            text_box.pack_start(copy, False, False, 0)
            item.pack_start(text_box, True, True, 0)
            self.status_feed_box.pack_start(item, False, False, 0)
        self.status_feed_box.show_all()

    def _build_people(self) -> Gtk.Box:
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        side.set_size_request(262, -1)
        add_class(side, "people-panel")
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.pack_start(label(self.t("online_directory"), "section-label"), True, True, 0)
        header.pack_end(button("↻", self._refresh_online, "small-button", self.t("refresh_online")), False, False, 0)
        side.pack_start(header, False, False, 0)
        self.people_search = Gtk.SearchEntry()
        self.people_search.set_placeholder_text(self.t("search_people"))
        self.people_search.connect("search-changed", lambda *_: self._render_people())
        side.pack_start(self.people_search, False, False, 0)
        lists = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.teacher_heading = label(self.t("teachers_online"), "online-group-label")
        lists.pack_start(self.teacher_heading, False, False, 0)
        self.teacher_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lists.pack_start(self.teacher_list, False, False, 0)
        self.student_heading = label(self.t("students_online"), "online-group-label")
        lists.pack_start(self.student_heading, False, False, 6)
        self.student_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lists.pack_start(self.student_list, False, False, 0)
        side.pack_start(scrolled(lists), True, True, 0)
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
                on_school=lambda event: GLib.idle_add(self._receive_school, event),
            )
            self.network.start()
            self._update_status_line()
        except OSError as error:
            self.network = None
            self.status_text.set_text(f"{self.t('disconnected')}: {error}. {self.t('port_in_use')}")
            add_class(self.status_dot, "status-dot-offline")

    def _send_school(self, payload: dict[str, Any], targets: list[str] | None) -> None:
        if self.network:
            self.network.send_school(payload, targets)

    def _update_status_line(self) -> None:
        if not hasattr(self, "status_text"):
            return
        if not self.network:
            self.status_text.set_text(self.t("disconnected"))
            return
        interfaces = self.network.local_ips
        addresses = ", ".join(
            f"{'📶' if item.get('kind') == 'wifi' else '🔌' if item.get('kind') == 'ethernet' else '🌐'} {item['address']}"
            for item in interfaces
        ) or self.t("no_network")
        count = len(self.peers)
        relayed = len([peer for peer in self.peers if not peer.direct])
        relay_text = f" ({relayed} {self.t('via_relay')})" if relayed else ""
        self.status_text.set_text(f"{self.t('online')}: {count}{relay_text}  •  {self.t('local_ip')}: {addresses}  •  TCP {self.network.tcp_port}")
        context = self.status_dot.get_style_context()
        for name in ("status-dot-online", "status-dot-searching", "status-dot-offline"):
            context.remove_class(name)
        context.add_class("status-dot-online" if count else ("status-dot-searching" if interfaces else "status-dot-offline"))
        if hasattr(self, "online_pill"):
            self.online_pill.set_label(f"● {count} {self.t('online')}")
            pill = self.online_pill.get_style_context()
            if count:
                pill.add_class("online-pill-active")
            else:
                pill.remove_class("online-pill-active")

    def select_room(self, room_id: str) -> None:
        self.current_room = room_id
        self.current_target_ids = self._targets_for_room(room_id)
        self.unread.pop(room_id, None)
        self._syncing = True
        for selected_id, item in self.room_buttons.items():
            item.set_active(selected_id == room_id)
        self._syncing = False
        self._refresh_room_button(room_id)
        title_key = dict(rooms_for(self.profile)).get(room_id)
        if title_key:
            title = self.t(title_key)
            subtitle = self.t(f"{title_key}_hint")
        elif room_id in self.direct_rooms:
            title = self.direct_rooms[room_id]["name"]
            subtitle = self.t("direct_chat")
        else:
            group = self.groups.get(room_id, {})
            title = group.get("name", room_id)
            subtitle = f"{self.t('group_room')} • {len(group.get('members', []))} {self.t('members')}"
        self.room_title.set_text(title)
        self.room_subtitle.set_text(subtitle)
        self._update_composer_state()
        self._render_messages()

    def select_direct(self, user_id: str, full_name: str) -> None:
        peer = next((item for item in self.peers if item.user_id == user_id), None)
        if not peer:
            self._error(self.t("direct_chat"), self.t("direct_unavailable"))
            return
        room_id = "direct:" + ":".join(sorted((self.identity.user_id, user_id)))
        self.direct_rooms[room_id] = {"user_id": user_id, "name": full_name}
        self._add_room_button(room_id, "👤  " + full_name, self.direct_list)
        self._switch_page("chat")
        self.select_room(room_id)

    def _send_block_reason(self, room_id: str) -> str | None:
        """Explain why the local user may not post in this room, or None."""
        if not self.profile or self.profile.role == "teacher" or not self.school:
            return None
        if room_id == "broadcasts":
            return self.t("broadcast_teacher_only")
        locked = self.school.room_locked(room_id)
        if locked:
            return self.t("room_locked_banner").format(name=locked.get("teacher_name", ""))
        exam = self.school.chat_locked()
        if exam:
            direct = self.direct_rooms.get(room_id)
            if direct:
                peer = next((item for item in self.peers if item.user_id == direct["user_id"]), None)
                if peer and peer.profile.get("role") == "teacher":
                    return None
            return self.t("exam_lock_banner").format(title=exam.get("title", ""))
        return None

    def _update_composer_state(self) -> None:
        if not hasattr(self, "composer_box") or not self.profile:
            return
        reason = self._send_block_reason(self.current_room)
        self.composer_box.set_sensitive(reason is None)
        if reason:
            self.lock_banner.set_text("🔒  " + reason)
            self.lock_banner.show()
        else:
            self.lock_banner.hide()
        shared = bool(dict(rooms_for(self.profile)).get(self.current_room)) and self.current_room != "broadcasts"
        if self.profile.role == "teacher" and shared and self.school:
            locked = self.school.room_locked(self.current_room)
            self.lock_button.set_label("🔓 " + self.t("unlock_room") if locked else "🔒 " + self.t("lock_room"))
            self.lock_button.show()
        else:
            self.lock_button.hide()

    def _toggle_room_lock(self, *_args) -> None:
        if not self.school or self.profile.role != "teacher":
            return
        locked = bool(self.school.room_locked(self.current_room))
        self.school.set_room_lock(self.current_room, not locked)
        self._refresh_room_button(self.current_room)
        self._update_composer_state()
        notice = self.t("room_unlocked") if locked else self.t("room_locked")
        self._send_message(self._make_message("text", f"🔔 {notice}: {self.room_title.get_text()}"))

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
        reason = self._send_block_reason(self.current_room)
        if reason:
            self._error(self.t("cannot_send"), reason)
            return
        if not self.rate_limiter.allow():
            self._error(self.t("cannot_send"), self.t("rate_limited"))
            return
        self.message_entry.set_text("")
        self._send_message(self._make_message("text", content[:4000]))

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
        if room_id == self.current_room:
            self._append_message(local_copy)
            GLib.idle_add(self._scroll_bottom)

    def _receive_message(self, message: dict[str, Any]) -> bool:
        if not self.profile:
            return False
        room_id = str(message.get("room_id", ""))
        profile = message.get("profile", {})
        sender_id = str(message.get("sender_id", ""))
        try:
            if validate_profile(Profile.from_dict(profile), require_photo=False):
                return False
        except (TypeError, ValueError):
            return False
        is_teacher = profile.get("role") == "teacher"
        if room_id.startswith("direct:"):
            if self.identity.user_id not in message.get("targets", []):
                return False
            if room_id != "direct:" + ":".join(sorted((self.identity.user_id, sender_id))):
                return False
        allowed_rooms = {room for room, _ in rooms_for(self.profile)} | set(self.groups) | set(self.direct_rooms)
        if room_id not in allowed_rooms and not room_id.startswith("direct:"):
            return False
        if room_id.startswith("teachers:") and not is_teacher:
            return False
        if room_id == "broadcasts" and not is_teacher:
            return False
        if not is_teacher and self.school:
            # Client-side school rules: locked rooms and exam mode drop student messages.
            if self.school.room_locked(room_id) or (self.profile.role == "student" and self.school.chat_locked()):
                return False
        kind = message.get("kind")
        if kind not in {"text", "broadcast", "grade", "image", "video", "audio", "document"}:
            return False
        if kind == "grade" and not is_teacher:
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
        if room_id.startswith("direct:"):
            sender_name = str(profile.get("full_name", self.t("unknown_user")))
            self.direct_rooms[room_id] = {"user_id": sender_id, "name": sender_name}
            self._add_room_button(room_id, "👤  " + sender_name, self.direct_list)
        if not self.storage.add_message(message):
            return False
        if room_id == self.current_room and self.current_page == "chat":
            self._append_message(message)
            GLib.idle_add(self._scroll_bottom)
        else:
            self.unread[room_id] = self.unread.get(room_id, 0) + 1
            self._refresh_room_button(room_id)
        sender = str(profile.get("full_name", self.t("unknown_user")))
        if room_id == "broadcasts":
            self._notify(self.t("announcement"), f"{sender}: {message.get('text', '')[:240]}", "broadcast")
        elif kind == "grade":
            self._notify(self.t("grade_received"), f"{sender}: {message.get('text', '')[:240]}", "message")
        else:
            body = self._display_text(message.get("text", ""))[:240] if kind == "text" else self.t(f"received_{kind}")
            self._notify(self.t("new_message"), f"{sender}: {body}", "message")
        return False

    def _display_text(self, value: str) -> str:
        if self.storage.settings.get("word_filter", True):
            return filter_text(value, self.storage.settings.get("filter_words", []))
        return value

    def _render_messages(self) -> None:
        if not hasattr(self, "message_list"):
            return
        clear_box(self.message_list)
        messages = self.storage.messages(self.current_room)
        if not messages:
            empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            add_class(empty, "empty-state")
            empty.set_margin_top(70)
            empty.pack_start(label("💬", "empty-icon", 0.5), False, False, 0)
            empty.pack_start(label(self.t("room_empty"), "empty-message", 0.5, wrap=True), False, False, 0)
            self.message_list.pack_start(empty, False, False, 0)
        else:
            previous_day = ""
            for message in messages:
                day = datetime.fromtimestamp(float(message.get("timestamp", 0))).strftime("%d/%m/%Y")
                if day != previous_day:
                    self.message_list.pack_start(label(day, "day-separator", 0.5), False, False, 4)
                    previous_day = day
                self._append_message(message, show=False)
        self.message_list.show_all()
        GLib.idle_add(self._scroll_bottom)

    def _append_message(self, message: dict[str, Any], show: bool = True) -> None:
        children = self.message_list.get_children()
        if children and children[0].get_style_context().has_class("empty-state"):
            clear_box(self.message_list)
        own = message.get("sender_id") == self.identity.user_id
        profile = message.get("profile", {})
        kind = message.get("kind")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_halign(Gtk.Align.END if own else Gtk.Align.START)
        if not own:
            avatar = profile_avatar(profile, 34)
            avatar.set_valign(Gtk.Align.START)
            row.pack_start(avatar, False, False, 0)
        bubble = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        bubble.set_size_request(200, -1)
        style = "message-own" if own else "message-peer"
        if kind == "broadcast":
            style = "message-broadcast"
        elif kind == "grade":
            style = "message-grade"
        add_class(bubble, style)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.pack_start(label(profile.get("full_name", self.t("unknown_user")), "message-name"), False, False, 0)
        role = profile.get("role", "student")
        header.pack_start(badge(self.t(role), "teacher" if role == "teacher" else "student"), False, False, 0)
        if kind == "broadcast":
            header.pack_start(badge("📣 " + self.t("announcement"), "warning"), False, False, 0)
        if kind == "grade":
            header.pack_start(badge("📊 " + self.t("grade_received"), "success"), False, False, 0)
        bubble.pack_start(header, False, False, 0)
        if message.get("text"):
            content = Gtk.Label(xalign=0.0)
            content.set_line_wrap(True)
            content.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            content.set_max_width_chars(60)
            content.set_selectable(True)
            content.set_markup(self._link_markup(self._display_text(message["text"])))
            content.connect("activate-link", self._open_link)
            add_class(content, "message-text")
            bubble.pack_start(content, False, False, 0)
        path_value = message.get("file_path")
        if path_value:
            path = Path(path_value)
            if kind == "image" and path.exists():
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 340, 240, True)
                    image = Gtk.Image.new_from_pixbuf(pixbuf)
                    image.set_halign(Gtk.Align.START)
                    event = Gtk.EventBox()
                    event.add(image)
                    event.connect("button-release-event", lambda *_args, selected=path: self._open_path(selected))
                    bubble.pack_start(event, False, False, 0)
                except GLib.Error:
                    pass
            icons = {"image": "🖼", "video": "🎬", "audio": "🎵", "document": "📄"}
            file_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            add_class(file_row, "file-chip")
            name = label(f"{icons.get(kind, '📎')}  {message.get('file_name', path.name)}", "file-name")
            name.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            name.set_max_width_chars(34)
            file_row.pack_start(name, True, True, 0)
            file_row.pack_end(button(self.t("open"), lambda _b, selected=path: self._open_path(selected), "small-button"), False, False, 0)
            if not own:
                file_row.pack_end(button(self.t("save_as"), lambda _b, selected=path: self._save_copy(selected), "small-button"), False, False, 0)
            bubble.pack_start(file_row, False, False, 0)
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        timestamp = datetime.fromtimestamp(float(message.get("timestamp", time.time()))).strftime("%H:%M")
        edited = f" • {self.t('edited')}" if message.get("edited_at") else ""
        footer.pack_end(label(f"{timestamp}{edited}" + ("  ✓" if own else ""), "message-time", 1.0), False, False, 0)
        message_age = time.time() - float(message.get("timestamp", 0))
        if own and -60 <= message_age <= MESSAGE_EDIT_WINDOW:
            if kind == "text":
                footer.pack_start(button("✎ " + self.t("edit_message"), lambda _b, msg_id=message["msg_id"]: self._edit_message_dialog(msg_id), "message-action"), False, False, 0)
            elif kind in {"image", "video", "audio", "document"}:
                footer.pack_start(button("↺ " + self.t("replace_file"), lambda _b, msg_id=message["msg_id"]: self._replace_file_dialog(msg_id), "message-action"), False, False, 0)
            footer.pack_start(button("🗑 " + self.t("delete_message"), lambda _b, msg_id=message["msg_id"]: self._delete_message_dialog(msg_id), "message-action message-action-danger"), False, False, 0)
        bubble.pack_start(footer, False, False, 0)
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
        margins(box, 14)
        entry = Gtk.Entry(text=message.get("text", ""))
        entry.set_activates_default(True)
        entry.set_size_request(420, -1)
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
        if not self._confirm(self.t("delete_message_confirm"), "", self.t("delete_message")):
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
            try:
                Gio.AppInfo.launch_default_for_uri(path.resolve().as_uri(), None)
            except GLib.Error as error:
                self._error(self.t("open"), str(error))

    def _scroll_bottom(self) -> bool:
        if hasattr(self, "message_scroller"):
            adjustment = self.message_scroller.get_vadjustment()
            adjustment.set_value(max(0, adjustment.get_upper() - adjustment.get_page_size()))
        return False

    # Directory -----------------------------------------------------------
    def _update_peers(self, peers: list[PeerInfo]) -> bool:
        if not self.profile:
            return False
        current_ids = {peer.user_id for peer in peers}
        new_ids = current_ids - self.known_peer_ids
        self.peers = peers
        self.known_peer_ids = current_ids
        self._update_status_line()
        self._render_people()
        self._render_status_feed()
        for peer in peers:
            if peer.user_id not in new_ids:
                continue
            if peer.direct and peer.ip:
                self.storage.remember_peer_ip(peer.ip)
            is_teacher = peer.profile.get("role") == "teacher"
            title = self.t("teacher_online") if is_teacher else self.t("friend_online")
            detail = f"{peer.profile.get('full_name', self.t('unknown_user'))} • {peer.profile.get('school_class', '')}"
            self._notify(title, detail, "online", sound=False)
        own_status = self.statuses.get(self.identity.user_id)
        if new_ids and own_status and self.network:
            self.network.send_status({key: value for key, value in own_status.items() if key not in {"sender_id", "file_path"}})
        if self.school:
            self.school.set_peers(peers)
        self._refresh_pages_after_peers()
        self._update_nav_badges()
        self._update_composer_state()
        return False

    def _render_people(self) -> None:
        if not hasattr(self, "student_list") or not self.profile:
            return
        clear_box(self.student_list)
        clear_box(self.teacher_list)
        query = self.people_search.get_text().strip().casefold() if hasattr(self, "people_search") else ""
        entries = [(self.identity.user_id, self.profile.public(), None)]
        entries += [(peer.user_id, peer.profile, peer) for peer in self.peers]
        counts = {"teacher": 0, "student": 0}
        for user_id, profile, peer in entries:
            role = "teacher" if profile.get("role") == "teacher" else "student"
            counts[role] += 1
            haystack = " ".join(str(profile.get(key, "")) for key in ("full_name", "school_class", "room", "subject")).casefold()
            if query and query not in haystack:
                continue
            container = self.teacher_list if role == "teacher" else self.student_list
            container.pack_start(self._person_button(user_id, profile, peer), False, False, 0)
        self.teacher_heading.set_text(f"{self.t('teachers_online')} • {counts['teacher']}")
        self.student_heading.set_text(f"{self.t('students_online')} • {counts['student']}")
        for container, empty_key in ((self.student_list, "no_students_online"), (self.teacher_list, "no_teachers_online")):
            if not container.get_children():
                container.pack_start(label(self.t(empty_key), "online-empty", 0.5), False, False, 6)
            container.show_all()

    def _person_button(self, user_id: str, profile: dict[str, Any], peer: PeerInfo | None) -> Gtk.Widget:
        own = peer is None
        chat_button = Gtk.Button()
        chat_button.set_relief(Gtk.ReliefStyle.NONE)
        add_class(chat_button, "person-button")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.pack_start(profile_avatar(profile, 36), False, False, 0)
        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        name = profile.get("full_name", self.t("unknown_user")) + (f" ({self.t('you')})" if own else "")
        name_label = label(name, "person-name")
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        details.pack_start(name_label, False, False, 0)
        extra = profile.get("subject") if profile.get("role") == "teacher" else f"{self.t('class')} {profile.get('school_class', '')}"
        detail = label(f"{extra} • {profile.get('room', '')}", "person-detail")
        detail.set_ellipsize(Pango.EllipsizeMode.END)
        details.pack_start(detail, False, False, 0)
        status = self.statuses.get(user_id)
        if status:
            status_label = label(self._status_summary(status), "person-status")
            status_label.set_ellipsize(Pango.EllipsizeMode.END)
            details.pack_start(status_label, False, False, 0)
        row.pack_start(details, True, True, 0)
        if peer is not None and not peer.direct:
            row.pack_end(label("⇄", "relay-dot"), False, False, 0)
        else:
            row.pack_end(label("●", "online-dot"), False, False, 0)
        chat_button.add(row)
        if own:
            chat_button.set_sensitive(False)
            return chat_button
        if peer.direct:
            chat_button.set_tooltip_text(f"{self.t('connection_direct')} • {peer.ip}")
        else:
            relay = next((item.profile.get("full_name", "") for item in self.peers if item.user_id == peer.via), peer.via[:15])
            chat_button.set_tooltip_text(f"{self.t('connection_relay')}: {relay}")
        chat_button.connect(
            "clicked",
            lambda _button, uid=user_id, person_name=profile.get("full_name", self.t("unknown_user")): self.select_direct(uid, person_name),
        )
        return chat_button

    def _refresh_online(self, *_args) -> None:
        if not self.network:
            self._start_network()
            return
        self.status_text.set_text(self.t("refreshing_online"))
        self.network.refresh_discovery()
        GLib.timeout_add_seconds(4, lambda: (self._update_status_line(), False)[1])

    # Status --------------------------------------------------------------
    def _status_summary(self, status: dict[str, Any]) -> str:
        kind = status.get("status_kind", "text")
        text_value = self._display_text(status.get("text", ""))
        if kind == "emotion":
            return f"{status.get('emotion', '😊')} {text_value}".strip()
        if kind == "image":
            return f"🖼 {text_value.strip() or status.get('file_name', self.t('status_image'))}"
        return text_value

    def _set_status_dialog(self, *_args) -> None:
        dialog = Gtk.Dialog(title=self.t("set_status"), transient_for=self, modal=True)
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("clear_status"), 1, self.t("publish_status"), Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(10)
        margins(box, 16)
        box.add(label(self.t("status_compose_hint"), "muted", wrap=True))
        entry = Gtk.Entry()
        entry.set_max_length(180)
        entry.set_placeholder_text(self.t("status_placeholder"))
        emotion = Gtk.ComboBoxText()
        emotion.append("", self.t("no_emotion"))
        for emotion_value in ("😊", "😀", "🤓", "😎", "🤔", "😴", "😢", "🎉", "📚", "✏️", "⚽", "🎵"):
            emotion.append(emotion_value, emotion_value)
        emotion.set_active(0)
        selected: dict[str, Path | None] = {"path": None}
        picture_label = label(self.t("no_status_image"), "muted")
        picture_button = Gtk.Button(label="🖼  " + self.t("choose_status_image"))

        def choose_picture(_button) -> None:
            path = self._choose_media_file("image", self.t("choose_status_image"), dialog)
            if path:
                selected["path"] = path
                picture_label.set_text(path.name)

        picture_button.connect("clicked", choose_picture)
        for widget in (entry, emotion, picture_button, picture_label):
            box.add(widget)
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
        if not self.profile:
            return False
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
        sender = status.get("profile", {}).get("full_name", self.t("unknown_user"))
        self._notify(self.t("new_status"), f"{sender}: {self._status_summary(status)}", "status", sound=False)
        return False

    # Teacher tools -------------------------------------------------------
    def _new_group_dialog(self, *_args) -> None:
        if self.profile.role != "teacher":
            self._error(self.t("new_group"), self.t("teacher_only"))
            return
        if not self.peers:
            self._error(self.t("new_group"), self.t("nobody_online"))
            return
        dialog = Gtk.Dialog(title=self.t("new_group"), transient_for=self, modal=True)
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("create_group"), Gtk.ResponseType.OK)
        dialog.set_default_size(420, 480)
        box = dialog.get_content_area()
        box.set_spacing(8)
        margins(box, 14)
        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text(self.t("group_name"))
        box.add(self._form_row("group_name", name_entry))
        box.add(label(self.t("group_members"), "field-label"))
        checks = []
        members_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for peer in self.peers:
            check = Gtk.CheckButton(label=f"{peer.profile.get('full_name', '')} • {self.t(peer.profile.get('role', 'student'))} • {peer.profile.get('school_class', '')}")
            checks.append((check, peer.user_id))
            members_box.pack_start(check, False, False, 0)
        members_scroller = scrolled(members_box)
        members_scroller.set_vexpand(True)
        box.pack_start(members_scroller, True, True, 0)
        dialog.show_all()
        response = dialog.run()
        group_name = name_entry.get_text().strip()[:80]
        selected = [user_id for check, user_id in checks if check.get_active()]
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        if not group_name or not selected:
            self._error(self.t("new_group"), self.t("group_members"))
            return
        group_id = f"group:{self.identity.user_id}:{uuid.uuid4().hex[:10]}"
        group = {"group_id": group_id, "name": group_name, "owner_id": self.identity.user_id, "members": [self.identity.user_id, *selected], "timestamp": time.time()}
        self.groups[group_id] = group
        self._add_room_button(group_id, "👥  " + group_name, self.group_list)
        if self.network:
            self.network.send_group_definition(group, group["members"])
        self._switch_page("chat")
        self.select_room(group_id)

    def _receive_group(self, group: dict[str, Any]) -> bool:
        sender_id = str(group.get("sender_id", ""))
        peer = next((item for item in self.peers if item.user_id == sender_id), None)
        if not peer or peer.profile.get("role") != "teacher" or group.get("owner_id") != sender_id:
            return False
        group_id = str(group.get("group_id", ""))
        name = str(group.get("name", "")).strip()[:80]
        members = group.get("members", [])
        if not group_id.startswith("group:") or not name or not isinstance(members, list) or self.identity.user_id not in members:
            return False
        self.groups[group_id] = {"group_id": group_id, "name": name, "owner_id": sender_id, "members": members}
        self._add_room_button(group_id, "👥  " + name, self.group_list)
        self._notify(self.t("group_invitation"), f"{peer.profile.get('full_name', '')}: {name}", "message")
        return False

    def _broadcast_dialog(self, *_args) -> None:
        if self.profile.role != "teacher":
            self._error(self.t("broadcast"), self.t("teacher_only"))
            return
        dialog = Gtk.Dialog(title=self.t("broadcast_title"), transient_for=self, modal=True)
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("send"), Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        margins(box, 14)
        box.add(label(self.t("broadcast_hint"), "muted", wrap=True))
        view = text_view("", 120)
        view.set_size_request(460, 120)
        box.add(framed(view))
        dialog.show_all()
        response = dialog.run()
        content = text_of(view).strip()[:1000]
        dialog.destroy()
        if response == Gtk.ResponseType.OK and content:
            self._send_message(self._make_message("broadcast", content, room_id="broadcasts"))

    def _grade_dialog(self, *_args) -> None:
        if self.profile.role != "teacher":
            self._error(self.t("send_grade"), self.t("teacher_only"))
            return
        students = [peer for peer in self.peers if peer.profile.get("role") == "student"]
        if not students:
            self._error(self.t("send_grade"), self.t("no_students_online"))
            return
        dialog = Gtk.Dialog(title=self.t("grade_title"), transient_for=self, modal=True)
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("send"), Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        margins(box, 14)
        recipient = Gtk.ComboBoxText()
        for peer in students:
            recipient.append(peer.user_id, f"{peer.profile.get('full_name', '')} • {peer.profile.get('school_class', '')}")
        recipient.set_active(0)
        exam = Gtk.Entry()
        exam.set_placeholder_text(self.t("exam_name"))
        score = Gtk.Entry()
        score.set_placeholder_text("85 / A / B+")
        notes = Gtk.Entry()
        notes.set_placeholder_text(self.t("notes"))
        for key, widget in (("recipient", recipient), ("exam_name", exam), ("score", score), ("notes", notes)):
            box.add(self._form_row(key, widget))
        dialog.show_all()
        response = dialog.run()
        target = recipient.get_active_id()
        exam_text = exam.get_text().strip()[:120]
        score_text = score.get_text().strip()[:40]
        notes_text = notes.get_text().strip()[:500]
        dialog.destroy()
        if response != Gtk.ResponseType.OK or not target or not exam_text or not score_text:
            return
        peer = next(item for item in students if item.user_id == target)
        room_id = "direct:" + ":".join(sorted((self.identity.user_id, target)))
        self.direct_rooms[room_id] = {"user_id": target, "name": peer.profile.get("full_name", "")}
        self._add_room_button(room_id, "👤  " + self.direct_rooms[room_id]["name"], self.direct_list)
        text_value = f"📊 {exam_text}\n{self.t('score')}: {score_text}"
        if notes_text:
            text_value += f"\n{self.t('notes')}: {notes_text}"
        self._send_message(self._make_message("grade", text_value, room_id=room_id, exam=exam_text, score=score_text, notes=notes_text))
        self._switch_page("chat")
        self.select_room(room_id)

    # Notifications, files and devices ------------------------------------
    def _notify(self, title: str, body: str, category: str, sound: bool = True) -> None:
        """Send a desktop notification and keep a visible in-app count."""
        self.notification_count += 1
        if hasattr(self, "notification_button"):
            self.notification_button.set_label(f"🔔 {self.notification_count}")
            add_class(self.notification_button, "notification-active")
        settings = self.storage.settings
        if self.is_active() and category != "online":
            self._show_toast(f"{title} — {body}"[:220])
        if settings.get("desktop_notifications", True) and not self.is_active():
            notification = Gio.Notification.new(title)
            notification.set_body(body or APP_NAME)
            notification.set_icon(Gio.ThemedIcon.new("tl.edukasaun.EdukaKonekta"))
            if category in {"broadcast", "exam"}:
                notification.set_priority(Gio.NotificationPriority.HIGH)
            application = self.get_application()
            if application:
                application.send_notification(f"{category}-{uuid.uuid4().hex}", notification)
            self.set_urgency_hint(True)
        if sound and settings.get("notification_sound", True):
            display = Gdk.Display.get_default()
            if display:
                display.beep()

    def _clear_notification_count(self, *_args) -> None:
        self.notification_count = 0
        if hasattr(self, "notification_button"):
            self.notification_button.set_label("🔔 0")
            self.notification_button.get_style_context().remove_class("notification-active")
        self.set_urgency_hint(False)

    def _chooser_shortcuts(self, chooser: Gtk.FileChooserDialog) -> None:
        home = Path.home()
        for shortcut in (
            home / "Documents", home / "Dokumen", home / "Pictures", home / "Videos", home / "Music", home / "Downloads",
            Path("/media") / home.name, Path("/run/media") / home.name,
        ):
            if shortcut.is_dir():
                try:
                    chooser.add_shortcut_folder(str(shortcut))
                except GLib.Error:
                    pass

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
        folder_name = {"image": "Pictures", "video": "Videos", "audio": "Music"}.get(kind, "Documents")
        initial = home / folder_name
        chooser.set_current_folder(str(initial if initial.is_dir() else home))
        self._chooser_shortcuts(chooser)
        response = chooser.run()
        filename = chooser.get_filename()
        chooser.destroy()
        if response != Gtk.ResponseType.ACCEPT or not filename:
            return None
        return Path(filename)

    def _choose_save_path(self, suggested: str, title: str | None = None) -> Path | None:
        chooser = Gtk.FileChooserDialog(
            title=title or self.t("save_as"), parent=self, action=Gtk.FileChooserAction.SAVE,
            buttons=(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("save"), Gtk.ResponseType.ACCEPT),
        )
        chooser.set_modal(True)
        chooser.set_do_overwrite_confirmation(True)
        documents = Path.home() / "Documents"
        chooser.set_current_folder(str(documents if documents.is_dir() else Path.home()))
        chooser.set_current_name(suggested)
        self._chooser_shortcuts(chooser)
        response = chooser.run()
        filename = chooser.get_filename()
        chooser.destroy()
        return Path(filename) if response == Gtk.ResponseType.ACCEPT and filename else None

    def _choose_folder(self, title: str) -> Path | None:
        chooser = Gtk.FileChooserDialog(
            title=title, parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER,
            buttons=(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("select"), Gtk.ResponseType.ACCEPT),
        )
        chooser.set_modal(True)
        chooser.set_current_folder(str(Path.home()))
        self._chooser_shortcuts(chooser)
        response = chooser.run()
        filename = chooser.get_filename()
        chooser.destroy()
        return Path(filename) if response == Gtk.ResponseType.ACCEPT and filename else None

    def _save_copy(self, source: Path) -> None:
        if not source.exists():
            return
        destination = self._choose_save_path(source.name.split("-", 1)[-1] if "-" in source.name else source.name)
        if destination:
            try:
                destination.write_bytes(source.read_bytes())
                self._info(self.t("saved"), str(destination))
            except OSError as error:
                self._error(self.t("save_as"), str(error))

    def _choose_attachment(self, kind: str) -> None:
        reason = self._send_block_reason(self.current_room)
        if reason:
            self._error(self.t("cannot_send"), reason)
            return
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
        self._info(
            self.t("media_devices"),
            f"{self.t('webcams')}:\n{camera_text}\n\n{self.t('microphones')}:\n{microphone_text}\n\n{ffmpeg_text}\n\n{self.t('device_controls_hint')}",
        )

    def _select_device(self, title: str, devices: list[MediaDevice]) -> MediaDevice | None:
        if not devices:
            return None
        if len(devices) == 1:
            return devices[0]
        dialog = Gtk.Dialog(title=title, transient_for=self, modal=True)
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("select"), Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        margins(box, 14)
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
        reason = self._send_block_reason(self.current_room)
        if reason:
            self._error(self.t("cannot_send"), reason)
            return
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
        reason = self._send_block_reason(self.current_room)
        if reason:
            self._error(self.t("cannot_send"), reason)
            return
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
        margins(box, 14)
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
        margins(progress_box, 18)
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

    def _open_emoji(self, source) -> None:
        popover = Gtk.Popover.new(source)
        grid = Gtk.Grid(column_spacing=4, row_spacing=4, margin=8)
        emotions = ["😀", "😂", "😊", "😍", "😎", "🤔", "😢", "😮", "👍", "👏", "🙏", "❤️", "🎉", "📚", "✏️", "🇹🇱", "✅", "❓", "💡", "⭐"]
        for index, emotion in enumerate(emotions):
            choice = Gtk.Button(label=emotion)
            choice.set_relief(Gtk.ReliefStyle.NONE)
            add_class(choice, "emoji-choice")
            choice.connect("clicked", lambda _button, value=emotion: self._insert_emoji(value, popover))
            grid.attach(choice, index % 10, index // 10, 1, 1)
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
        margins(box, 16)
        box.add(label(self.t("manual_ip_text"), None, 0.0, wrap=True))
        entry = Gtk.Entry()
        entry.set_placeholder_text("192.168.1.25")
        entry.set_activates_default(True)
        dialog.set_default_response(Gtk.ResponseType.OK)
        box.add(entry)
        dialog.show_all()
        response = dialog.run()
        value = entry.get_text()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        try:
            host = validate_ip(value)
        except ValueError:
            self._error(self.t("manual_ip_title"), self.t("invalid_ip") + ": " + value)
            return
        self.storage.remember_peer_ip(host)
        if self.network:
            self.network.seed_ips.add(host)
            self.network.connect_ip(host, force=True)
        self._info(self.t("manual_ip_title"), self.t("connecting_to").format(ip=host))

    def show_about(self) -> None:
        dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        dialog.set_program_name(APP_NAME)
        dialog.set_version(f"{VERSION} {CHANNEL}")
        logo = logo_pixbuf(128)
        if logo is not None:
            dialog.set_logo(logo)
        addresses = ", ".join(item["address"] for item in self.network.local_ips) if self.network else ""
        dialog.set_comments(
            self.t("about_body") + "\n\n" + self.t("session_privacy") + "\n\n" +
            self.t("network_warning") + "\n\n" + self.t("local_ip") + ": " + (addresses or "-") +
            "\n" + self.t("identity") + ": " + self.identity.user_id
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
        if not self._confirm(self.t("logout_confirm"), self.t("logout_detail"), self.t("logout")):
            return
        self._stop_tick()
        if self.network:
            self.network.stop()
            self.network = None
        self.school = None
        self.statuses.clear()
        self.groups.clear()
        self.direct_rooms.clear()
        self.unread.clear()
        self.peers = []
        self.known_peer_ids.clear()
        self.current_room = ""
        self.current_page = "chat"
        self.selected_exam_id = ""
        self.storage.logout()
        self.profile = None
        self.selected_photo_b64 = ""
        self.selected_photo_mime = ""
        self.device_manager = DeviceManager(self.storage.session_dir / "captures")
        self.show_login()

    def _confirm_clear(self) -> None:
        if self._confirm(self.t("confirm_clear"), "", self.t("clear")):
            self.storage.clear_room(self.current_room)
            self._render_messages()

    def _confirm(self, title: str, detail: str, action: str) -> bool:
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.NONE, text=title)
        if detail:
            dialog.format_secondary_text(detail)
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, action, Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.OK

    def _error(self, title: str, detail: str) -> None:
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK, text=title)
        dialog.format_secondary_text(detail)
        dialog.run()
        dialog.destroy()

    def _info(self, title: str, detail: str) -> None:
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK, text=title)
        dialog.format_secondary_text(detail)
        dialog.run()
        dialog.destroy()

    def _replace_root(self, widget: Gtk.Widget) -> None:
        child = self.get_child()
        if child:
            self.remove(child)
            child.destroy()
        self.add(widget)
        self.show_all()
