"""Profile, room, identity, signing, and attachment validation."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

IMAGE_LIMIT = 10 * 1024 * 1024
VIDEO_LIMIT = 25 * 1024 * 1024
AUDIO_LIMIT = 10 * 1024 * 1024
DOCUMENT_LIMIT = 25 * 1024 * 1024
PHOTO_LIMIT = 2 * 1024 * 1024
STATUS_KINDS = frozenset({"text", "emotion", "image", "none"})


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:80] or "unknown"


@dataclass
class Profile:
    full_name: str
    school: str
    role: str
    age: int
    school_class: str
    room: str
    language: str = "en"
    subject: str = ""
    photo_b64: str = ""
    photo_mime: str = "image/jpeg"

    def public(self, include_photo: bool = True) -> dict[str, Any]:
        data = asdict(self)
        if not include_photo:
            data["photo_b64"] = ""
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Profile":
        return cls(
            full_name=str(data.get("full_name", "")).strip(),
            school=str(data.get("school", "")).strip(),
            role="teacher" if data.get("role") == "teacher" else "student",
            age=int(data.get("age", 0)),
            school_class=str(data.get("school_class", "")).strip(),
            room=str(data.get("room", "")).strip(),
            language=str(data.get("language", "en")),
            subject=str(data.get("subject", "")).strip(),
            photo_b64=str(data.get("photo_b64", "")),
            photo_mime=str(data.get("photo_mime", "image/jpeg")),
        )


def validate_profile(profile: Profile, require_photo: bool = False) -> list[str]:
    errors = []
    parts = [p for p in profile.full_name.split() if p]
    allowed = re.compile(r"^[^\W\d_][^\d_]*$", re.UNICODE)
    if len(parts) < 2 or any(len(p) < 2 or not allowed.match(p) for p in parts):
        errors.append("name_error")
    if len(profile.school) < 3:
        errors.append("school_error")
    if not 5 <= profile.age <= 100:
        errors.append("age_error")
    if not profile.school_class:
        errors.append("class_error")
    if not profile.room:
        errors.append("room_error")
    if profile.role == "teacher" and not profile.subject:
        errors.append("subject_error")
    if require_photo and not profile.photo_b64:
        errors.append("photo_required")
    return errors


def rooms_for(profile: Profile) -> list[tuple[str, str]]:
    school = slug(profile.school)
    rooms = [
        ("all-schools", "all_schools"),
        ("broadcasts", "broadcasts"),
        (f"school:{school}", "my_school"),
        (f"class:{school}:{slug(profile.school_class)}:{slug(profile.room)}", "my_class"),
    ]
    if profile.role == "teacher":
        rooms.append((f"teachers:{school}", "teachers"))
    return rooms


def validate_profile_photo(path: Path) -> tuple[bool, str | None, str]:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    try:
        size = path.stat().st_size
    except OSError:
        return False, "invalid_type", mime
    if not mime.startswith("image/"):
        return False, "invalid_type", mime
    if size <= 0 or size > PHOTO_LIMIT:
        return False, "photo_limit", mime
    return True, None, mime


class Identity:
    """Passwordless persistent Ed25519 device identity."""

    def __init__(self, private_key: Ed25519PrivateKey):
        self.private_key = private_key
        self.public_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.public_key = base64.b64encode(self.public_bytes).decode("ascii")
        digest = hashlib.sha256(self.public_bytes).hexdigest().upper()
        self.user_id = "EK-" + "-".join(digest[i:i + 4] for i in range(0, 20, 4))

    @classmethod
    def load_or_create(cls, path: Path) -> "Identity":
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raw = base64.b64decode(json.loads(path.read_text(encoding="utf-8"))["private_key"])
            return cls(Ed25519PrivateKey.from_private_bytes(raw))
        key = Ed25519PrivateKey.generate()
        raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"private_key": base64.b64encode(raw).decode("ascii")}), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(path)
        return cls(key)

    def sign(self, payload: dict[str, Any]) -> str:
        canonical = canonical_bytes(payload)
        return base64.b64encode(self.private_key.sign(canonical)).decode("ascii")


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def verify_signature(payload: dict[str, Any], signature: str, public_key: str, expected_user_id: str) -> bool:
    try:
        raw = base64.b64decode(public_key, validate=True)
        digest = hashlib.sha256(raw).hexdigest().upper()
        actual = "EK-" + "-".join(digest[i:i + 4] for i in range(0, 20, 4))
        if actual != expected_user_id:
            return False
        Ed25519PublicKey.from_public_bytes(raw).verify(base64.b64decode(signature, validate=True), canonical_bytes(payload))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def validate_ip(value: str) -> str:
    host = value.strip()
    ipaddress.ip_address(host)
    return host


def media_duration(path: Path) -> float | None:
    executable = shutil.which("ffprobe")
    if not executable:
        return None
    try:
        result = subprocess.run(
            [executable, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            check=True, capture_output=True, text=True, timeout=8,
        )
        return float(result.stdout.strip())
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


def validate_attachment(path: Path, kind: str) -> tuple[bool, str | None, str]:
    """Return allowed, localized error key, and MIME type."""
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    try:
        size = path.stat().st_size
    except OSError:
        return False, "invalid_type", mime
    if kind == "image":
        return (mime.startswith("image/") and size <= IMAGE_LIMIT, None if mime.startswith("image/") and size <= IMAGE_LIMIT else ("image_limit" if mime.startswith("image/") else "invalid_type"), mime)
    if kind == "document":
        return (0 < size <= DOCUMENT_LIMIT, None if 0 < size <= DOCUMENT_LIMIT else "document_limit", mime)
    if kind not in {"video", "audio"} or not mime.startswith(kind + "/"):
        return False, "invalid_type", mime
    limit = VIDEO_LIMIT if kind == "video" else AUDIO_LIMIT
    seconds = 30 if kind == "video" else 60
    if size > limit:
        return False, "video_limit" if kind == "video" else "audio_limit", mime
    duration = media_duration(path)
    if duration is None:
        return False, "duration_tool", mime
    if duration > seconds + 0.25:
        return False, "video_limit" if kind == "video" else "audio_limit", mime
    return True, None, mime


def validate_message_action_payload(payload: dict[str, Any]) -> bool:
    """Validate signed edit/delete events before applying them to local history."""
    action = payload.get("action")
    event_id = payload.get("event_id", "")
    message_id = payload.get("msg_id", "")
    room_id = payload.get("room_id", "")
    if action not in {"edit", "delete", "replace"}:
        return False
    if not all(isinstance(value, str) and 0 < len(value) <= 200 for value in (event_id, message_id, room_id)):
        return False
    if action == "edit":
        text = payload.get("text", "")
        return isinstance(text, str) and 0 < len(text.strip()) <= 4000
    if action == "replace":
        kind = payload.get("kind")
        limits = {
            "image": IMAGE_LIMIT,
            "video": VIDEO_LIMIT,
            "audio": AUDIO_LIMIT,
            "document": DOCUMENT_LIMIT,
        }
        encoded = payload.get("file_data", "")
        mime = payload.get("mime", "")
        name = payload.get("file_name", "")
        return (
            kind in limits
            and isinstance(encoded, str)
            and len(encoded) <= ((limits[kind] + 2) // 3) * 4 + 4
            and isinstance(mime, str) and 0 < len(mime) <= 160
            and isinstance(name, str) and 0 < len(Path(name).name) <= 160
        )
    return True


def validate_status_payload(payload: dict[str, Any]) -> bool:
    """Validate the supported status types before they enter the UI."""
    kind = payload.get("status_kind")
    if kind not in STATUS_KINDS:
        return False
    text = payload.get("text", "")
    if not isinstance(text, str) or len(text) > 180:
        return False
    if kind == "text":
        return bool(text.strip())
    if kind == "emotion":
        emotion = payload.get("emotion", "")
        return isinstance(emotion, str) and 0 < len(emotion) <= 16
    if kind == "image":
        encoded = payload.get("file_data", "")
        mime = payload.get("mime", "")
        name = payload.get("file_name", "")
        return (
            isinstance(encoded, str)
            and len(encoded) <= ((IMAGE_LIMIT + 2) // 3) * 4 + 4
            and isinstance(mime, str) and mime.startswith("image/")
            and isinstance(name, str) and 0 < len(Path(name).name) <= 160
        )
    return True
