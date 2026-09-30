"""GTK application entry point."""

from __future__ import annotations

import logging
import signal

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import APP_ID
from .models import Identity
from .storage import Storage
from .ui import EdukaWindow


class EdukaApplication(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None
        self.storage = None

    def do_activate(self):
        if not self.window:
            self.storage = Storage()
            identity = Identity.load_or_create(self.storage.identity_path)
            self.window = EdukaWindow(self, self.storage, identity)
        self.window.present()

    def do_shutdown(self):
        if self.window and self.window.active_capture and self.window.active_capture.poll() is None:
            self.window.device_manager.stop_recording(self.window.active_capture)
            self.window.active_capture = None
        if self.window and self.window.network:
            self.window.network.stop()
        if self.storage:
            self.storage.close()
        Gtk.Application.do_shutdown(self)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    application = EdukaApplication()
    for signum in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signum, application.quit)
    return application.run(argv)
