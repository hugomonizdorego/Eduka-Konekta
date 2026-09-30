"""Local profile, settings, downloads, and SQLite chat history."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from .models import Profile

MESSAGE_EDIT_WINDOW = 30 * 60


class Storage:
    def __init__(self, base_dir: Path | None = None):
        config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        self.config_dir = base_dir or config_root / "eduka-konekta"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if base_dir:
            self.session_dir = Path(tempfile.mkdtemp(prefix="session-", dir=base_dir))
        else:
            self.session_dir = Path(tempfile.mkdtemp(prefix=f"eduka-konekta-{os.getuid()}-"))
        self.data_dir = self.session_dir
        self.download_dir = self.session_dir / "received"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.identity_path = self.config_dir / "identity.json"
        self.profile_path = self.config_dir / "profile.json"
        self.known_peers_path = self.config_dir / "known-peers.json"
        self._profile: Profile | None = self._read_profile()
        self._closed = False
        self._lock = threading.RLock()
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY, room_id TEXT NOT NULL, timestamp REAL NOT NULL,
                sender_id TEXT NOT NULL, sender_name TEXT NOT NULL, role TEXT NOT NULL,
                kind TEXT NOT NULL, text TEXT NOT NULL DEFAULT '', file_path TEXT,
                file_name TEXT, mime TEXT, profile_json TEXT NOT NULL,
                edited_at REAL
            )"""
        )
        self.db.execute("CREATE INDEX IF NOT EXISTS messages_room_time ON messages(room_id, timestamp)")
        self.db.commit()

    def _read_profile(self) -> Profile | None:
        try:
            data = json.loads(self.profile_path.read_text(encoding="utf-8"))
            return Profile.from_dict(data) if isinstance(data, dict) else None
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def load_profile(self) -> Profile | None:
        return self._profile

    def save_profile(self, profile: Profile) -> None:
        self._profile = profile
        temporary = self.profile_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(profile.public(), ensure_ascii=False), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self.profile_path)

    def known_peer_ips(self) -> list[str]:
        try:
            values = json.loads(self.known_peers_path.read_text(encoding="utf-8"))
            return [str(value) for value in values if isinstance(value, str)][:128]
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return []

    def remember_peer_ip(self, ip: str) -> None:
        values = self.known_peer_ips()
        if ip in values:
            values.remove(ip)
        values.insert(0, ip)
        temporary = self.known_peers_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(values[:128]), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self.known_peers_path)

    def add_message(self, message: dict[str, Any]) -> bool:
        profile = message.get("profile", {})
        with self._lock:
            try:
                self.db.execute(
                    """INSERT INTO messages
                       (id, room_id, timestamp, sender_id, sender_name, role, kind, text,
                        file_path, file_name, mime, profile_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        message["msg_id"], message["room_id"], float(message["timestamp"]),
                        message["sender_id"], str(profile.get("full_name", "Unknown")),
                        str(profile.get("role", "student")), message.get("kind", "text"),
                        message.get("text", ""), message.get("file_path"), message.get("file_name"),
                        message.get("mime"), json.dumps(profile, ensure_ascii=False),
                    ),
                )
                self.db.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def messages(self, room_id: str, limit: int = 250) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.db.execute(
                "SELECT * FROM messages WHERE room_id=? ORDER BY timestamp DESC LIMIT ?",
                (room_id, limit),
            ).fetchall()
        return [self._row_to_message(row) for row in reversed(rows)]

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["msg_id"] = item.pop("id")
        item["profile"] = json.loads(item.pop("profile_json"))
        return item

    def message(self, message_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.db.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        return self._row_to_message(row) if row else None

    def edit_message(self, message_id: str, sender_id: str, text: str, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        with self._lock:
            row = self.db.execute(
                "SELECT timestamp, sender_id, kind FROM messages WHERE id=?", (message_id,)
            ).fetchone()
            if not row or row["sender_id"] != sender_id or row["kind"] != "text":
                return False
            if now - float(row["timestamp"]) > MESSAGE_EDIT_WINDOW or now < float(row["timestamp"]) - 60:
                return False
            self.db.execute("UPDATE messages SET text=?, edited_at=? WHERE id=?", (text[:4000], now, message_id))
            self.db.commit()
        return True

    def delete_message(self, message_id: str, sender_id: str, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        with self._lock:
            row = self.db.execute(
                "SELECT timestamp, sender_id, file_path FROM messages WHERE id=?", (message_id,)
            ).fetchone()
            if not row or row["sender_id"] != sender_id:
                return False
            if now - float(row["timestamp"]) > MESSAGE_EDIT_WINDOW or now < float(row["timestamp"]) - 60:
                return False
            self.db.execute("DELETE FROM messages WHERE id=?", (message_id,))
            self.db.commit()
        file_value = row["file_path"]
        if file_value:
            try:
                path = Path(file_value).resolve()
                if path.is_relative_to(self.session_dir.resolve()):
                    path.unlink(missing_ok=True)
            except OSError:
                pass
        return True

    def replace_message_file(
        self,
        message_id: str,
        sender_id: str,
        kind: str,
        file_path: str,
        file_name: str,
        mime: str,
        now: float | None = None,
    ) -> bool:
        now = now if now is not None else time.time()
        with self._lock:
            row = self.db.execute(
                "SELECT timestamp, sender_id, kind, file_path FROM messages WHERE id=?", (message_id,)
            ).fetchone()
            if not row or row["sender_id"] != sender_id or row["kind"] != kind:
                return False
            if kind not in {"image", "video", "audio", "document"}:
                return False
            if now - float(row["timestamp"]) > MESSAGE_EDIT_WINDOW or now < float(row["timestamp"]) - 60:
                return False
            old_file = row["file_path"]
            self.db.execute(
                "UPDATE messages SET file_path=?, file_name=?, mime=?, edited_at=? WHERE id=?",
                (file_path, file_name, mime, now, message_id),
            )
            self.db.commit()
        if old_file and old_file != file_path:
            try:
                old_path = Path(old_file).resolve()
                if old_path.is_relative_to(self.session_dir.resolve()):
                    old_path.unlink(missing_ok=True)
            except OSError:
                pass
        return True

    def clear_room(self, room_id: str) -> None:
        with self._lock:
            self.db.execute("DELETE FROM messages WHERE room_id=?", (room_id,))
            self.db.commit()

    def clear_session(self) -> None:
        with self._lock:
            self.db.execute("DELETE FROM messages")
            self.db.commit()
        for child in (self.download_dir, self.session_dir / "captures"):
            shutil.rmtree(child, ignore_errors=True)
            child.mkdir(parents=True, exist_ok=True)

    def logout(self) -> None:
        self._profile = None
        self.profile_path.unlink(missing_ok=True)
        self.clear_session()

    def safe_download_path(self, message_id: str, original_name: str) -> Path:
        clean = Path(original_name).name.replace("\x00", "")[:160] or "attachment"
        destination = self.download_dir / f"{message_id[:8]}-{clean}"
        counter = 1
        while destination.exists():
            destination = self.download_dir / f"{message_id[:8]}-{counter}-{clean}"
            counter += 1
        return destination

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with self._lock:
            self.db.close()
        shutil.rmtree(self.session_dir, ignore_errors=True)
