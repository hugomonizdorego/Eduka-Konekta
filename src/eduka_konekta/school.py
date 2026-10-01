"""Classroom features: exams and assignments, attendance, school rules and room locks.

Everything here is independent of GTK so it can be unit tested. The manager keeps
records on disk (unlike ephemeral chat) because a teacher must never lose the
answers of a class when the computer is closed. Delivery is store-and-forward:
the teacher's computer re-sends an exam to students who come online later, and
a student's computer re-sends an answer until the teacher confirms receipt.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import mimetypes
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .models import DOCUMENT_LIMIT, slug

EXAM_KINDS = ("exam", "assignment", "quiz")
TARGET_MODES = ("class", "all", "students")
QUESTION_TYPES = ("choice", "essay")
MAX_QUESTIONS = 100
MAX_OPTIONS = 6
MAX_TEXT = 4000
RESEND_INTERVAL = 30.0
LATE_GRACE = 60.0
BASE64_LIMIT = ((DOCUMENT_LIMIT + 2) // 3) * 4 + 4
OPTION_LETTERS = "ABCDEF"

DEFAULT_RULES = "default"


def _text(value: Any, limit: int) -> str:
    return str(value if value is not None else "").strip()[:limit]


def safe_file_name(name: str, fallback: str = "file") -> str:
    clean = Path(str(name)).name.replace("\x00", "")
    clean = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", clean).strip(". ")
    return clean[:120] or fallback


def grade_answers(questions: list[dict[str, Any]], answer_key: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
    """Automatically grade multiple-choice questions. Essays are graded by the teacher."""
    correct = total = 0
    points = max_points = 0.0
    essays = 0
    for question in questions:
        qid = question.get("qid")
        weight = float(question.get("points", 1) or 1)
        if question.get("type") != "choice":
            essays += 1
            continue
        total += 1
        max_points += weight
        expected = answer_key.get(qid)
        given = answers.get(qid)
        if expected is not None and given is not None and int(given) == int(expected):
            correct += 1
            points += weight
    percent = round(100.0 * points / max_points, 1) if max_points else None
    return {
        "correct": correct, "total": total, "points": points,
        "max_points": max_points, "essays": essays, "percent": percent,
    }


def normalize_questions(raw: Any) -> list[dict[str, Any]]:
    """Validate the question list that travels to students (no answer key)."""
    if not isinstance(raw, list):
        return []
    questions = []
    for index, item in enumerate(raw[:MAX_QUESTIONS]):
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        text_value = _text(item.get("text"), 2000)
        if kind not in QUESTION_TYPES or not text_value:
            continue
        question = {
            "qid": _text(item.get("qid") or f"q{index + 1}", 16),
            "type": kind,
            "text": text_value,
            "points": max(0.0, min(100.0, float(item.get("points", 1) or 1))),
        }
        if kind == "choice":
            options = [_text(option, 500) for option in item.get("options", [])[:MAX_OPTIONS] if _text(option, 500)]
            if len(options) < 2:
                continue
            question["options"] = options
        questions.append(question)
    return questions


def validate_school_payload(payload: dict[str, Any]) -> bool:
    """Bound every school event before it reaches the manager."""
    kind = payload.get("kind")
    if kind == "exam_publish":
        exam = payload.get("exam")
        return (
            isinstance(exam, dict)
            and 0 < len(_text(exam.get("exam_id"), 64)) <= 64
            and exam.get("kind") in EXAM_KINDS
            and 0 < len(_text(exam.get("title"), 200))
            and len(str(exam.get("instructions", ""))) <= MAX_TEXT
            and isinstance(exam.get("questions", []), list)
            and len(exam.get("questions", [])) <= MAX_QUESTIONS
        )
    if kind in {"exam_ack", "exam_file_request", "exam_close"}:
        return 0 < len(str(payload.get("exam_id", ""))) <= 64
    if kind == "exam_file":
        data = payload.get("file_data", "")
        return (
            0 < len(str(payload.get("exam_id", ""))) <= 64
            and isinstance(data, str) and 0 < len(data) <= BASE64_LIMIT
            and 0 < len(str(payload.get("file_name", ""))) <= 200
        )
    if kind == "exam_submit":
        answers = payload.get("answers", {})
        data = payload.get("file_data", "")
        return (
            0 < len(str(payload.get("exam_id", ""))) <= 64
            and 0 < len(str(payload.get("submission_id", ""))) <= 64
            and isinstance(answers, dict) and len(answers) <= MAX_QUESTIONS
            and all(isinstance(value, (str, int)) and len(str(value)) <= MAX_TEXT for value in answers.values())
            and isinstance(data, str) and len(data) <= BASE64_LIMIT
            and len(str(payload.get("file_name", ""))) <= 200
        )
    if kind == "exam_receipt":
        return 0 < len(str(payload.get("exam_id", ""))) <= 64 and 0 < len(str(payload.get("submission_id", ""))) <= 64
    if kind == "exam_result":
        return (
            0 < len(str(payload.get("exam_id", ""))) <= 64
            and 0 < len(str(payload.get("score", ""))) <= 40
            and len(str(payload.get("feedback", ""))) <= 2000
        )
    if kind == "attendance_open":
        return 0 < len(str(payload.get("session_id", ""))) <= 64 and len(str(payload.get("title", ""))) <= 200
    if kind in {"attendance_reply", "attendance_receipt", "attendance_close"}:
        return 0 < len(str(payload.get("session_id", ""))) <= 64
    if kind == "rules":
        return 0 < len(str(payload.get("rules_id", ""))) <= 64 and len(str(payload.get("text", ""))) <= 8000
    if kind == "room_lock":
        return 0 < len(str(payload.get("room_id", ""))) <= 200 and isinstance(payload.get("locked"), bool)
    return False


class SchoolManager:
    """State machine for classroom features on one computer (teacher or student)."""

    def __init__(
        self,
        records_dir: Path,
        user_id: str,
        profile_getter: Callable[[], Any],
        send: Callable[[dict[str, Any], list[str] | None], None],
        clock: Callable[[], float] = time.time,
    ):
        self.user_id = user_id
        self._profile_getter = profile_getter
        self._send = send
        self.clock = clock
        profile = profile_getter()
        key = f"{profile.role}-{slug(profile.full_name)}-{user_id[3:12]}"
        self.base_dir = records_dir / key
        self.files_dir = self.base_dir / "files"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.base_dir / "records.json"
        self._lock = threading.RLock()
        self._last_sent: dict[str, float] = {}
        self.peers: list[Any] = []
        self.exams: dict[str, dict[str, Any]] = {}
        self.submissions: dict[str, dict[str, dict[str, Any]]] = {}
        self.attendance: dict[str, dict[str, Any]] = {}
        self.rules: dict[str, Any] = {}
        self.room_locks: dict[str, dict[str, Any]] = {}
        self._load()

    # Persistence ---------------------------------------------------------
    @property
    def profile(self):
        return self._profile_getter()

    @property
    def is_teacher(self) -> bool:
        return self.profile.role == "teacher"

    def _load(self) -> None:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        self.exams = data.get("exams", {}) if isinstance(data.get("exams"), dict) else {}
        self.submissions = data.get("submissions", {}) if isinstance(data.get("submissions"), dict) else {}
        self.attendance = data.get("attendance", {}) if isinstance(data.get("attendance"), dict) else {}
        self.rules = data.get("rules", {}) if isinstance(data.get("rules"), dict) else {}
        self.room_locks = data.get("room_locks", {}) if isinstance(data.get("room_locks"), dict) else {}

    def save(self) -> None:
        with self._lock:
            data = {
                "version": 1, "exams": self.exams, "submissions": self.submissions,
                "attendance": self.attendance, "rules": self.rules, "room_locks": self.room_locks,
            }
            temporary = self.state_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            os.chmod(temporary, 0o600)
            temporary.replace(self.state_path)

    def _profile_public(self) -> dict[str, Any]:
        return self.profile.public(include_photo=False)

    def send(self, payload: dict[str, Any], targets: list[str] | None = None) -> None:
        payload = dict(payload)
        payload.setdefault("event_id", uuid.uuid4().hex)
        payload["profile"] = self._profile_public()
        payload["timestamp"] = self.clock()
        self._send(payload, targets)

    # Directory helpers ---------------------------------------------------
    def set_peers(self, peers: list[Any]) -> None:
        with self._lock:
            before = {peer.user_id for peer in self.peers}
            self.peers = list(peers)
            new_ids = {peer.user_id for peer in peers} - before
        self.resend(force_ids=new_ids)

    def _peer(self, user_id: str):
        return next((peer for peer in self.peers if peer.user_id == user_id), None)

    def online_students(self) -> list[Any]:
        return [peer for peer in self.peers if peer.profile.get("role") == "student"]

    def known_classes(self) -> list[str]:
        classes = {str(peer.profile.get("school_class", "")).strip() for peer in self.online_students()}
        if self.profile.school_class:
            classes.add(self.profile.school_class)
        return sorted(item for item in classes if item)

    @staticmethod
    def matches_target(target: dict[str, Any], user_id: str, profile: dict[str, Any]) -> bool:
        if profile.get("role") != "student":
            return False
        mode = target.get("mode", "class")
        if mode == "all":
            return True
        if mode == "students":
            return user_id in target.get("student_ids", [])
        return slug(str(profile.get("school_class", ""))) == slug(str(target.get("school_class", "")))

    def _throttled(self, key: str, force: bool = False) -> bool:
        now = time.monotonic()
        if not force and now - self._last_sent.get(key, 0.0) < RESEND_INTERVAL:
            return True
        self._last_sent[key] = now
        return False

    # Teacher: exams ------------------------------------------------------
    def create_exam(
        self,
        kind: str,
        title: str,
        subject: str,
        instructions: str,
        target: dict[str, Any],
        duration_minutes: int,
        questions: list[dict[str, Any]],
        answer_key: dict[str, int],
        lock_chat: bool = False,
        allow_late: bool = True,
        allow_file: bool = True,
        question_file: Path | None = None,
    ) -> dict[str, Any]:
        if not self.is_teacher:
            raise PermissionError("teacher only")
        exam_id = uuid.uuid4().hex[:20]
        questions = normalize_questions(questions)
        exam = {
            "exam_id": exam_id,
            "kind": kind if kind in EXAM_KINDS else "exam",
            "title": _text(title, 200),
            "subject": _text(subject or self.profile.subject, 120),
            "instructions": _text(instructions, MAX_TEXT),
            "teacher_id": self.user_id,
            "teacher_name": self.profile.full_name,
            "created_at": self.clock(),
            "opened_at": self.clock(),
            "duration_minutes": max(0, min(int(duration_minutes or 0), 60 * 24 * 30)),
            "target": {
                "mode": target.get("mode") if target.get("mode") in TARGET_MODES else "class",
                "school_class": _text(target.get("school_class"), 80),
                "student_ids": [str(item) for item in target.get("student_ids", [])][:500],
            },
            "lock_chat": bool(lock_chat),
            "allow_late": bool(allow_late),
            "allow_file": bool(allow_file),
            "questions": questions,
            "answer_key": {str(key): int(value) for key, value in answer_key.items()},
            "closed": False,
            "delivered_to": [],
            "role": "owner",
        }
        if question_file:
            data = question_file.read_bytes()
            if len(data) > DOCUMENT_LIMIT:
                raise ValueError("document_limit")
            destination = self.files_dir / exam_id / ("questions-" + safe_file_name(question_file.name))
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            exam["file"] = {
                "name": safe_file_name(question_file.name),
                "mime": mimetypes.guess_type(question_file.name)[0] or "application/octet-stream",
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "path": str(destination),
            }
        with self._lock:
            self.exams[exam_id] = exam
            self.submissions.setdefault(exam_id, {})
            self.save()
        self.publish_exam(exam_id, force=True)
        return exam

    def deadline(self, exam: dict[str, Any]) -> float | None:
        if exam.get("role") == "owner":
            minutes = int(exam.get("duration_minutes", 0) or 0)
            return float(exam["opened_at"]) + minutes * 60 if minutes else None
        return exam.get("deadline_local")

    def remaining_seconds(self, exam: dict[str, Any]) -> float | None:
        deadline = self.deadline(exam)
        return None if deadline is None else deadline - self.clock()

    def exam_state(self, exam: dict[str, Any]) -> str:
        """open, ended (time up but late answers allowed) or closed."""
        if exam.get("closed"):
            return "closed"
        remaining = self.remaining_seconds(exam)
        if remaining is not None and remaining <= 0:
            return "ended" if exam.get("allow_late") else "closed"
        return "open"

    def public_exam(self, exam: dict[str, Any]) -> dict[str, Any]:
        remaining = self.remaining_seconds(exam)
        public = {
            key: exam.get(key) for key in (
                "exam_id", "kind", "title", "subject", "instructions", "teacher_id", "teacher_name",
                "created_at", "duration_minutes", "lock_chat", "allow_late", "allow_file", "questions", "closed",
            )
        }
        public["remaining_seconds"] = None if remaining is None else max(0.0, remaining)
        if exam.get("file"):
            public["file"] = {key: exam["file"][key] for key in ("name", "mime", "size", "sha256")}
        return public

    def exam_targets(self, exam: dict[str, Any]) -> list[str]:
        return [
            peer.user_id for peer in self.online_students()
            if self.matches_target(exam.get("target", {}), peer.user_id, peer.profile)
        ]

    def publish_exam(self, exam_id: str, force: bool = False, only: set[str] | None = None) -> int:
        exam = self.exams.get(exam_id)
        if not exam or exam.get("role") != "owner" or exam.get("closed"):
            return 0
        delivered = set(exam.get("delivered_to", []))
        targets = [
            user_id for user_id in self.exam_targets(exam)
            if (force or user_id not in delivered) and (only is None or user_id in only)
            and not self._throttled(f"exam:{exam_id}:{user_id}", force)
        ]
        if targets:
            self.send({"kind": "exam_publish", "exam": self.public_exam(exam)}, targets)
        return len(targets)

    def close_exam(self, exam_id: str) -> None:
        exam = self.exams.get(exam_id)
        if not exam or exam.get("role") != "owner":
            return
        exam["closed"] = True
        self.save()
        targets = list(set(exam.get("delivered_to", [])) | set(self.exam_targets(exam)))
        if targets:
            self.send({"kind": "exam_close", "exam_id": exam_id}, targets)

    def delete_exam(self, exam_id: str) -> None:
        with self._lock:
            self.exams.pop(exam_id, None)
            self.submissions.pop(exam_id, None)
            self.save()
        shutil.rmtree(self.files_dir / exam_id, ignore_errors=True)

    def return_result(self, exam_id: str, student_id: str, score: str, feedback: str) -> bool:
        submission = self.submissions.get(exam_id, {}).get(student_id)
        if not submission:
            return False
        submission.update({"score": _text(score, 40), "feedback": _text(feedback, 2000), "returned_at": self.clock()})
        self.save()
        auto = submission.get("auto", {})
        self.send({
            "kind": "exam_result", "exam_id": exam_id, "score": submission["score"],
            "feedback": submission["feedback"], "correct": auto.get("correct", 0), "total": auto.get("total", 0),
        }, [student_id])
        return True

    def export_results_csv(self, exam_id: str, destination: Path) -> Path:
        exam = self.exams[exam_id]
        rows = sorted(self.submissions.get(exam_id, {}).values(), key=lambda item: item.get("student_name", "").casefold())
        with destination.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "Name", "Class", "Room", "Submitted", "Late", "Multiple choice correct",
                "Multiple choice total", "Automatic %", "Score", "Feedback", "Answer file",
            ])
            for row in rows:
                auto = row.get("auto", {})
                writer.writerow([
                    row.get("student_name", ""), row.get("school_class", ""), row.get("room", ""),
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(row.get("submitted_at", 0))),
                    "yes" if row.get("late") else "no", auto.get("correct", ""), auto.get("total", ""),
                    "" if auto.get("percent") is None else auto.get("percent"), row.get("score", ""),
                    row.get("feedback", ""), (row.get("file") or {}).get("name", ""),
                ])
            writer.writerow([])
            writer.writerow([exam.get("title", ""), exam.get("subject", ""), exam.get("teacher_name", "")])
        return destination

    def copy_answer_files(self, exam_id: str, destination: Path) -> int:
        destination.mkdir(parents=True, exist_ok=True)
        copied = 0
        for row in self.submissions.get(exam_id, {}).values():
            file_info = row.get("file") or {}
            source = Path(file_info.get("path", ""))
            if source.is_file():
                target = destination / f"{safe_file_name(row.get('student_name', 'student'))}-{safe_file_name(file_info.get('name', source.name))}"
                shutil.copy2(source, target)
                copied += 1
        return copied

    # Student: exams ------------------------------------------------------
    def request_exam_file(self, exam_id: str) -> bool:
        exam = self.exams.get(exam_id)
        if not exam or not exam.get("file") or not self._peer(exam.get("teacher_id", "")):
            return False
        self.send({"kind": "exam_file_request", "exam_id": exam_id}, [exam["teacher_id"]])
        return True

    def save_draft(self, exam_id: str, answers: dict[str, Any]) -> None:
        exam = self.exams.get(exam_id)
        if exam:
            exam["draft"] = answers
            self.save()

    def can_submit(self, exam: dict[str, Any]) -> bool:
        return exam.get("role") != "owner" and self.exam_state(exam) != "closed"

    def submit_exam(self, exam_id: str, answers: dict[str, Any], answer_file: Path | None = None) -> dict[str, Any]:
        exam = self.exams.get(exam_id)
        if not exam or exam.get("role") == "owner":
            raise KeyError(exam_id)
        if not self.can_submit(exam):
            raise PermissionError("closed")
        clean_answers: dict[str, Any] = {}
        for question in exam.get("questions", []):
            value = answers.get(question["qid"])
            if value is None or value == "":
                continue
            if question["type"] == "choice":
                clean_answers[question["qid"]] = int(value)
            else:
                clean_answers[question["qid"]] = _text(value, MAX_TEXT)
        submission = {
            "submission_id": uuid.uuid4().hex[:20],
            "answers": clean_answers,
            "submitted_at": self.clock(),
            "acked": False,
        }
        if answer_file:
            data = answer_file.read_bytes()
            if not data or len(data) > DOCUMENT_LIMIT:
                raise ValueError("document_limit")
            copy = self.files_dir / exam_id / ("answer-" + safe_file_name(answer_file.name))
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(data)
            submission["file"] = {
                "name": safe_file_name(answer_file.name),
                "mime": mimetypes.guess_type(answer_file.name)[0] or "application/octet-stream",
                "path": str(copy),
            }
        exam["submission"] = submission
        exam.pop("draft", None)
        self.save()
        self._send_submission(exam_id, force=True)
        return submission

    def _send_submission(self, exam_id: str, force: bool = False) -> bool:
        exam = self.exams.get(exam_id)
        submission = (exam or {}).get("submission")
        if not exam or not submission or submission.get("acked"):
            return False
        teacher_id = exam.get("teacher_id", "")
        if not self._peer(teacher_id) or self._throttled(f"submit:{exam_id}", force):
            return False
        payload = {
            "kind": "exam_submit", "exam_id": exam_id,
            "submission_id": submission["submission_id"], "answers": submission["answers"],
            "file_name": "", "mime": "", "file_data": "",
        }
        file_info = submission.get("file")
        if file_info:
            try:
                payload["file_data"] = base64.b64encode(Path(file_info["path"]).read_bytes()).decode("ascii")
                payload["file_name"] = file_info["name"]
                payload["mime"] = file_info["mime"]
            except OSError:
                pass
        self.send(payload, [teacher_id])
        return True

    def chat_locked(self) -> dict[str, Any] | None:
        """Return the exam that currently locks student chat, if any."""
        if self.is_teacher:
            return None
        for exam in self.exams.values():
            if exam.get("role") == "owner" or not exam.get("lock_chat"):
                continue
            if exam.get("closed"):
                continue
            remaining = self.remaining_seconds(exam)
            if remaining is None or remaining > 0:
                return exam
        return None

    # Attendance ----------------------------------------------------------
    def open_attendance(self, title: str, school_class: str, minutes: int) -> dict[str, Any]:
        if not self.is_teacher:
            raise PermissionError("teacher only")
        session_id = uuid.uuid4().hex[:20]
        session = {
            "session_id": session_id, "title": _text(title, 200) or time.strftime("%Y-%m-%d"),
            "school_class": _text(school_class, 80), "opened_at": self.clock(),
            "minutes": max(1, min(int(minutes or 10), 240)), "teacher_id": self.user_id,
            "teacher_name": self.profile.full_name, "present": {}, "closed": False, "role": "owner",
            "delivered_to": [],
        }
        self.attendance[session_id] = session
        self.save()
        self.publish_attendance(session_id, force=True)
        return session

    def attendance_open(self, session: dict[str, Any]) -> bool:
        if session.get("closed"):
            return False
        if session.get("role") == "owner":
            end = float(session["opened_at"]) + int(session.get("minutes", 10)) * 60
        else:
            end = float(session.get("deadline_local", 0))
        return self.clock() < end

    def publish_attendance(self, session_id: str, force: bool = False, only: set[str] | None = None) -> int:
        session = self.attendance.get(session_id)
        if not session or session.get("role") != "owner" or not self.attendance_open(session):
            return 0
        remaining = float(session["opened_at"]) + int(session["minutes"]) * 60 - self.clock()
        target = {"mode": "class", "school_class": session.get("school_class", "")}
        if not session.get("school_class"):
            target = {"mode": "all"}
        targets = [
            peer.user_id for peer in self.online_students()
            if self.matches_target(target, peer.user_id, peer.profile)
            and peer.user_id not in session.get("present", {})
            and (only is None or peer.user_id in only)
            and not self._throttled(f"att:{session_id}:{peer.user_id}", force)
        ]
        if targets:
            self.send({
                "kind": "attendance_open", "session_id": session_id, "title": session["title"],
                "school_class": session.get("school_class", ""), "remaining_seconds": max(0.0, remaining),
            }, targets)
        return len(targets)

    def close_attendance(self, session_id: str) -> None:
        session = self.attendance.get(session_id)
        if session and session.get("role") == "owner":
            session["closed"] = True
            self.save()
            targets = [peer.user_id for peer in self.online_students()]
            if targets:
                self.send({"kind": "attendance_close", "session_id": session_id}, targets)

    def mark_present(self, session_id: str) -> bool:
        session = self.attendance.get(session_id)
        if not session or session.get("role") == "owner" or not self.attendance_open(session):
            return False
        session["answered_at"] = self.clock()
        session.setdefault("acked", False)
        self.save()
        self._send_attendance_reply(session_id, force=True)
        return True

    def _send_attendance_reply(self, session_id: str, force: bool = False) -> None:
        session = self.attendance.get(session_id)
        if not session or not session.get("answered_at") or session.get("acked"):
            return
        teacher_id = session.get("teacher_id", "")
        if self._peer(teacher_id) and not self._throttled(f"attreply:{session_id}", force):
            self.send({"kind": "attendance_reply", "session_id": session_id}, [teacher_id])

    def export_attendance_csv(self, session_id: str, destination: Path) -> Path:
        session = self.attendance[session_id]
        with destination.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Name", "Class", "Room", "Time"])
            for row in sorted(session.get("present", {}).values(), key=lambda item: item.get("name", "").casefold()):
                writer.writerow([
                    row.get("name", ""), row.get("school_class", ""), row.get("room", ""),
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(row.get("time", 0))),
                ])
            writer.writerow([])
            writer.writerow([session.get("title", ""), session.get("school_class", ""), session.get("teacher_name", "")])
        return destination

    # Rules and room locks ------------------------------------------------
    def publish_rules(self, text_value: str) -> dict[str, Any]:
        if not self.is_teacher:
            raise PermissionError("teacher only")
        self.rules = {
            "rules_id": uuid.uuid4().hex[:20], "text": _text(text_value, 8000),
            "teacher_name": self.profile.full_name, "updated_at": self.clock(),
            "author_id": self.user_id,
        }
        self.save()
        self.send({"kind": "rules", **{key: self.rules[key] for key in ("rules_id", "text", "updated_at")}}, None)
        return self.rules

    def set_room_lock(self, room_id: str, locked: bool) -> None:
        if not self.is_teacher:
            raise PermissionError("teacher only")
        self.room_locks[room_id] = {
            "locked": locked, "teacher_name": self.profile.full_name,
            "updated_at": self.clock(), "author_id": self.user_id,
        }
        self.save()
        self.send({"kind": "room_lock", "room_id": room_id, "locked": locked}, None)

    def room_locked(self, room_id: str) -> dict[str, Any] | None:
        entry = self.room_locks.get(room_id)
        return entry if entry and entry.get("locked") else None

    # Periodic work -------------------------------------------------------
    def resend(self, force_ids: set[str] | None = None) -> None:
        """Store-and-forward: deliver pending items to peers that are now online."""
        force_ids = force_ids or set()
        if self.is_teacher:
            for exam_id, exam in list(self.exams.items()):
                if exam.get("role") == "owner" and not exam.get("closed"):
                    self.publish_exam(exam_id)
            for session_id, session in list(self.attendance.items()):
                if session.get("role") == "owner":
                    self.publish_attendance(session_id)
            if force_ids:
                if self.rules.get("author_id") == self.user_id:
                    self.send({"kind": "rules", **{key: self.rules[key] for key in ("rules_id", "text", "updated_at")}}, sorted(force_ids))
                for room_id, entry in self.room_locks.items():
                    if entry.get("author_id") == self.user_id and entry.get("locked"):
                        self.send({"kind": "room_lock", "room_id": room_id, "locked": True}, sorted(force_ids))
        else:
            for exam_id in list(self.exams):
                self._send_submission(exam_id, force=bool(force_ids))
            for session_id in list(self.attendance):
                self._send_attendance_reply(session_id, force=bool(force_ids))

    # Receiving -----------------------------------------------------------
    def handle(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Apply a verified network event. Returns a UI notice or None."""
        if not validate_school_payload(event):
            return None
        sender_id = str(event.get("sender_id", ""))
        sender = event.get("profile", {}) if isinstance(event.get("profile"), dict) else {}
        sender_name = str(sender.get("full_name", ""))
        kind = event["kind"]
        with self._lock:
            handler = getattr(self, f"_on_{kind}", None)
            if handler is None:
                return None
            try:
                return handler(event, sender_id, sender, sender_name)
            except (TypeError, ValueError, KeyError, AttributeError):
                # A malformed event from another computer must never break the UI.
                return None

    def _on_exam_publish(self, event, sender_id, sender, sender_name):
        if sender.get("role") != "teacher" or self.is_teacher:
            return None
        incoming = event["exam"]
        exam_id = _text(incoming.get("exam_id"), 64)
        if incoming.get("teacher_id") != sender_id:
            return None
        existing = self.exams.get(exam_id)
        if existing and existing.get("role") == "owner":
            return None
        is_new = existing is None
        exam = existing or {}
        remaining = incoming.get("remaining_seconds")
        exam.update({
            "exam_id": exam_id, "kind": incoming.get("kind", "exam"),
            "title": _text(incoming.get("title"), 200), "subject": _text(incoming.get("subject"), 120),
            "instructions": _text(incoming.get("instructions"), MAX_TEXT), "teacher_id": sender_id,
            "teacher_name": sender_name, "created_at": incoming.get("created_at", self.clock()),
            "duration_minutes": int(incoming.get("duration_minutes", 0) or 0),
            "lock_chat": bool(incoming.get("lock_chat")), "allow_late": bool(incoming.get("allow_late", True)),
            "allow_file": bool(incoming.get("allow_file", True)),
            "questions": normalize_questions(incoming.get("questions", [])),
            "closed": bool(incoming.get("closed")), "role": "student",
        })
        if isinstance(incoming.get("file"), dict):
            exam["file"] = {key: incoming["file"].get(key) for key in ("name", "mime", "size", "sha256")}
            exam["file"]["name"] = safe_file_name(str(exam["file"].get("name") or "questions"))
        if is_new:
            exam["received_at"] = self.clock()
            exam["deadline_local"] = None if remaining is None else self.clock() + float(remaining)
        elif remaining is not None:
            exam["deadline_local"] = self.clock() + float(remaining)
        self.exams[exam_id] = exam
        self.save()
        self.send({"kind": "exam_ack", "exam_id": exam_id}, [sender_id])
        if not is_new:
            return {"refresh": "exams"}
        return {"refresh": "exams", "notify": "new_exam", "detail": f"{sender_name}: {exam['title']}", "exam_id": exam_id}

    def _on_exam_ack(self, event, sender_id, sender, sender_name):
        exam = self.exams.get(event["exam_id"])
        if not exam or exam.get("role") != "owner":
            return None
        delivered = set(exam.get("delivered_to", []))
        if sender_id in delivered:
            return None
        delivered.add(sender_id)
        exam["delivered_to"] = sorted(delivered)
        self.save()
        return {"refresh": "exams"}

    def _on_exam_close(self, event, sender_id, sender, sender_name):
        exam = self.exams.get(event["exam_id"])
        if not exam or exam.get("role") == "owner" or exam.get("teacher_id") != sender_id:
            return None
        exam["closed"] = True
        self.save()
        return {"refresh": "exams", "notify": "exam_closed", "detail": exam.get("title", "")}

    def _on_exam_file_request(self, event, sender_id, sender, sender_name):
        exam = self.exams.get(event["exam_id"])
        if not exam or exam.get("role") != "owner" or not exam.get("file"):
            return None
        if not self.matches_target(exam.get("target", {}), sender_id, sender) and sender_id not in exam.get("delivered_to", []):
            return None
        try:
            data = Path(exam["file"]["path"]).read_bytes()
        except OSError:
            return None
        self.send({
            "kind": "exam_file", "exam_id": exam["exam_id"], "file_name": exam["file"]["name"],
            "mime": exam["file"]["mime"], "file_data": base64.b64encode(data).decode("ascii"),
        }, [sender_id])
        return None

    def _on_exam_file(self, event, sender_id, sender, sender_name):
        exam = self.exams.get(event["exam_id"])
        if not exam or exam.get("role") == "owner" or exam.get("teacher_id") != sender_id:
            return None
        try:
            data = base64.b64decode(event["file_data"], validate=True)
        except ValueError:
            return None
        expected = (exam.get("file") or {}).get("sha256")
        if expected and hashlib.sha256(data).hexdigest() != expected:
            return None
        destination = self.files_dir / exam["exam_id"] / safe_file_name(event.get("file_name", "questions"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        exam.setdefault("file", {})["path"] = str(destination)
        self.save()
        return {"refresh": "exams", "notify": "exam_file_ready", "detail": exam.get("title", ""), "exam_id": exam["exam_id"]}

    def _on_exam_submit(self, event, sender_id, sender, sender_name):
        exam = self.exams.get(event["exam_id"])
        if not exam or exam.get("role") != "owner" or sender.get("role") != "student":
            return None
        if not self.matches_target(exam.get("target", {}), sender_id, sender) and sender_id not in exam.get("delivered_to", []):
            return None
        rows = self.submissions.setdefault(exam["exam_id"], {})
        previous = rows.get(sender_id)
        if previous and previous.get("submission_id") == event["submission_id"]:
            self.send({"kind": "exam_receipt", "exam_id": exam["exam_id"], "submission_id": event["submission_id"]}, [sender_id])
            return None
        now = self.clock()
        deadline = self.deadline(exam)
        late = bool(exam.get("closed")) or (deadline is not None and now > deadline + LATE_GRACE)
        answers = {str(key): value for key, value in event.get("answers", {}).items()}
        row = {
            "student_id": sender_id, "student_name": sender_name,
            "school_class": sender.get("school_class", ""), "room": sender.get("room", ""),
            "submission_id": event["submission_id"], "submitted_at": now, "late": late,
            "answers": answers,
            "auto": grade_answers(exam.get("questions", []), exam.get("answer_key", {}), answers),
            "score": (previous or {}).get("score", ""), "feedback": (previous or {}).get("feedback", ""),
            "resubmitted": bool(previous),
        }
        if event.get("file_data"):
            try:
                data = base64.b64decode(event["file_data"], validate=True)
                folder = self.files_dir / exam["exam_id"] / "answers"
                folder.mkdir(parents=True, exist_ok=True)
                name = safe_file_name(event.get("file_name", "answer"))
                destination = folder / f"{safe_file_name(sender_name, 'student')}-{sender_id[3:12]}-{name}"
                destination.write_bytes(data)
                row["file"] = {"name": name, "mime": _text(event.get("mime"), 160), "path": str(destination)}
            except (ValueError, OSError):
                pass
        rows[sender_id] = row
        self.save()
        self.send({"kind": "exam_receipt", "exam_id": exam["exam_id"], "submission_id": event["submission_id"]}, [sender_id])
        return {"refresh": "exams", "notify": "new_submission", "detail": f"{sender_name}: {exam.get('title', '')}", "exam_id": exam["exam_id"]}

    def _on_exam_receipt(self, event, sender_id, sender, sender_name):
        exam = self.exams.get(event["exam_id"])
        submission = (exam or {}).get("submission")
        if not exam or exam.get("teacher_id") != sender_id or not submission:
            return None
        if submission.get("submission_id") != event["submission_id"] or submission.get("acked"):
            return None
        submission["acked"] = True
        submission["acked_at"] = self.clock()
        self.save()
        return {"refresh": "exams", "notify": "submission_received", "detail": exam.get("title", "")}

    def _on_exam_result(self, event, sender_id, sender, sender_name):
        exam = self.exams.get(event["exam_id"])
        if not exam or exam.get("role") == "owner" or exam.get("teacher_id") != sender_id:
            return None
        exam["result"] = {
            "score": _text(event.get("score"), 40), "feedback": _text(event.get("feedback"), 2000),
            "correct": int(event.get("correct", 0) or 0), "total": int(event.get("total", 0) or 0),
            "received_at": self.clock(),
        }
        self.save()
        return {"refresh": "exams", "notify": "result_received", "detail": f"{exam.get('title', '')}: {exam['result']['score']}"}

    def _on_attendance_open(self, event, sender_id, sender, sender_name):
        if sender.get("role") != "teacher" or self.is_teacher:
            return None
        session_id = str(event["session_id"])
        existing = self.attendance.get(session_id)
        remaining = float(event.get("remaining_seconds", 600) or 0)
        session = existing or {
            "session_id": session_id, "title": _text(event.get("title"), 200),
            "school_class": _text(event.get("school_class"), 80), "teacher_id": sender_id,
            "teacher_name": sender_name, "role": "student", "received_at": self.clock(),
        }
        session["deadline_local"] = self.clock() + remaining
        self.attendance[session_id] = session
        self.save()
        if existing:
            return {"refresh": "attendance"}
        return {"refresh": "attendance", "notify": "attendance_request", "detail": f"{sender_name}: {session['title']}"}

    def _on_attendance_reply(self, event, sender_id, sender, sender_name):
        session = self.attendance.get(event["session_id"])
        if not session or session.get("role") != "owner" or sender.get("role") != "student":
            return None
        present = session.setdefault("present", {})
        if sender_id not in present:
            late = not self.attendance_open(session)
            present[sender_id] = {
                "name": sender_name, "school_class": sender.get("school_class", ""),
                "room": sender.get("room", ""), "time": self.clock(), "late": late,
            }
            self.save()
        self.send({"kind": "attendance_receipt", "session_id": session["session_id"]}, [sender_id])
        return {"refresh": "attendance"}

    def _on_attendance_close(self, event, sender_id, sender, sender_name):
        session = self.attendance.get(event["session_id"])
        if not session or session.get("role") == "owner" or session.get("teacher_id") != sender_id or session.get("closed"):
            return None
        session["closed"] = True
        self.save()
        return {"refresh": "attendance"}

    def _on_attendance_receipt(self, event, sender_id, sender, sender_name):
        session = self.attendance.get(event["session_id"])
        if not session or session.get("teacher_id") != sender_id or session.get("acked"):
            return None
        session["acked"] = True
        self.save()
        return {"refresh": "attendance"}

    def _on_rules(self, event, sender_id, sender, sender_name):
        if sender.get("role") != "teacher" or sender_id == self.user_id:
            return None
        updated = float(event.get("updated_at", 0) or 0)
        if self.rules.get("rules_id") == event["rules_id"]:
            return None
        if self.rules and float(self.rules.get("updated_at", 0) or 0) > updated:
            return None
        self.rules = {
            "rules_id": event["rules_id"], "text": _text(event.get("text"), 8000),
            "teacher_name": sender_name, "updated_at": updated, "author_id": sender_id,
        }
        self.save()
        return {"refresh": "rules", "notify": "rules_updated", "detail": sender_name}

    def _on_room_lock(self, event, sender_id, sender, sender_name):
        if sender.get("role") != "teacher" or sender_id == self.user_id:
            return None
        room_id = str(event["room_id"])
        current = self.room_locks.get(room_id, {})
        if bool(current.get("locked")) == event["locked"]:
            return None
        self.room_locks[room_id] = {
            "locked": event["locked"], "teacher_name": sender_name,
            "updated_at": self.clock(), "author_id": sender_id,
        }
        self.save()
        return {"refresh": "chat", "notify": "room_locked" if event["locked"] else "room_unlocked", "detail": sender_name, "room_id": room_id}
