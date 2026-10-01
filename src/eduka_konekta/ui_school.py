"""School pages: exams and assignments, attendance, rules, network and settings."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from .i18n import LANGUAGES
from .models import DOCUMENT_LIMIT
from .moderation import DEFAULT_BLOCKED_WORDS, parse_word_list
from .school import OPTION_LETTERS
from .widgets import (
    add_class, badge, button, card, clear_box, framed, label, margins, scrolled, text_of, text_view,
)


def format_clock(timestamp: float | None) -> str:
    if not timestamp:
        return "-"
    return datetime.fromtimestamp(float(timestamp)).strftime("%d/%m/%Y %H:%M")


def format_remaining(seconds: float | None) -> str:
    if seconds is None:
        return "∞"
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


class SchoolPagesMixin:
    """Mixed into EdukaWindow; relies on its helpers (t, _error, _notify, ...)."""

    selected_exam_id: str = ""
    selected_attendance_id: str = ""

    # Shared page scaffolding ---------------------------------------------
    def _page(self, title_key: str, subtitle_key: str) -> tuple[Gtk.Box, Gtk.Box, Gtk.Box]:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        add_class(page, "page")
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        add_class(header, "page-header")
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        titles.pack_start(label(self.t(title_key), "page-title"), False, False, 0)
        titles.pack_start(label(self.t(subtitle_key), "page-subtitle", wrap=True), False, False, 0)
        header.pack_start(titles, True, True, 0)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        actions.set_valign(Gtk.Align.CENTER)
        header.pack_end(actions, False, False, 0)
        page.pack_start(header, False, False, 0)
        return page, header, actions

    def _refresh_pages_after_peers(self) -> None:
        if self.current_page == "network":
            self._render_network()
        elif self.current_page == "exams":
            self._render_exam_list()
        elif self.current_page == "attendance":
            self._render_attendance()

    def _update_nav_badges(self) -> None:
        if not getattr(self, "nav_labels", None) or not self.school:
            return
        pending_exams = 0
        pending_attendance = 0
        if self.profile.role == "student":
            pending_exams = sum(
                1 for exam in self.school.exams.values()
                if not exam.get("submission") and self.school.exam_state(exam) != "closed"
            )
            pending_attendance = sum(
                1 for session in self.school.attendance.values()
                if not session.get("answered_at") and self.school.attendance_open(session)
            )
        else:
            pending_exams = sum(
                1 for exam_id, rows in self.school.submissions.items()
                for row in rows.values() if not row.get("score")
                if exam_id in self.school.exams
            )
        for name, count, key in (("exams", pending_exams, "nav_exams"), ("attendance", pending_attendance, "nav_attendance")):
            text = self.t(key) + (f" ({count})" if count else "")
            self.nav_labels[name].set_text(text)

    def _receive_school(self, event: dict[str, Any]) -> bool:
        if not self.school or not self.profile:
            return False
        notice = self.school.handle(event)
        if not notice:
            return False
        refresh = notice.get("refresh")
        if refresh == "exams":
            if self.current_page == "exams":
                exam_id = notice.get("exam_id")
                self._render_exam_list()
                # Only rebuild the open exam when it is safe (no answers being typed).
                if exam_id and exam_id == self.selected_exam_id and (self.profile.role == "teacher" or notice.get("notify") in {"exam_file_ready", "result_received", "submission_received", "exam_closed"}):
                    self._render_exam_detail()
        elif refresh == "attendance" and self.current_page == "attendance":
            self._render_attendance()
        elif refresh == "rules" and self.current_page == "rules":
            self._render_rules()
        elif refresh == "chat":
            room_id = notice.get("room_id")
            if room_id:
                self._refresh_room_button(room_id)
        self._update_composer_state()
        self._update_nav_badges()
        key = notice.get("notify")
        if key:
            category = "exam" if key in {"new_exam", "attendance_request"} else "message"
            self._notify(self.t(key), notice.get("detail", ""), category)
        return False

    def _tick_school_pages(self) -> None:
        if self.current_page == "exams" and getattr(self, "exam_countdown", None) and self.selected_exam_id:
            exam = self.school.exams.get(self.selected_exam_id)
            if exam:
                state = self.school.exam_state(exam)
                self.exam_countdown.set_text(f"⏱ {format_remaining(self.school.remaining_seconds(exam))}  •  {self.t('state_' + state)}")
                if getattr(self, "submit_button", None) is not None and state == "closed":
                    self.submit_button.set_sensitive(False)
        if self._tick_count % 5 == 0:
            self._update_nav_badges()
            if self.current_page == "exams":
                self._render_exam_list()

    # Exams page ----------------------------------------------------------
    def _build_exams_page(self) -> Gtk.Widget:
        page, _header, actions = self._page("exams_title", "exams_subtitle_teacher" if self.profile.role == "teacher" else "exams_subtitle_student")
        if self.profile.role == "teacher":
            actions.pack_start(button("＋ " + self.t("create_exam"), lambda *_: self._create_exam_dialog(), "primary-button"), False, False, 0)
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.exam_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        margins(self.exam_list, 12)
        list_scroller = scrolled(self.exam_list)
        list_scroller.set_size_request(320, -1)
        add_class(list_scroller, "list-pane")
        paned.pack1(list_scroller, False, False)
        self.exam_detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        margins(self.exam_detail, 18)
        paned.pack2(scrolled(self.exam_detail), True, False)
        page.pack_start(paned, True, True, 0)
        self._render_exams()
        return page

    def _render_exams(self) -> None:
        self._render_exam_list()
        self._render_exam_detail()

    def _sorted_exams(self) -> list[dict[str, Any]]:
        return sorted(self.school.exams.values(), key=lambda item: float(item.get("created_at", 0)), reverse=True)

    def _render_exam_list(self) -> None:
        if not hasattr(self, "exam_list") or not self.school:
            return
        clear_box(self.exam_list)
        exams = self._sorted_exams()
        if not exams:
            empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            empty.set_margin_top(40)
            empty.pack_start(label("📝", "empty-icon", 0.5), False, False, 0)
            empty.pack_start(label(self.t("no_exams_teacher" if self.profile.role == "teacher" else "no_exams_student"), "empty-message", 0.5, wrap=True), False, False, 0)
            self.exam_list.pack_start(empty, False, False, 0)
        for exam in exams:
            self.exam_list.pack_start(self._exam_list_item(exam), False, False, 0)
        self.exam_list.show_all()

    def _exam_list_item(self, exam: dict[str, Any]) -> Gtk.Widget:
        item = Gtk.Button()
        item.set_relief(Gtk.ReliefStyle.NONE)
        add_class(item, "list-item")
        if exam["exam_id"] == self.selected_exam_id:
            add_class(item, "list-item-selected")
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        top.pack_start(badge(self.t("kind_" + exam.get("kind", "exam")), "info"), False, False, 0)
        state = self.school.exam_state(exam)
        top.pack_end(badge(self.t("state_" + state), {"open": "success", "ended": "warning", "closed": "muted"}[state]), False, False, 0)
        content.pack_start(top, False, False, 0)
        title = label(exam.get("title", ""), "list-title")
        title.set_ellipsize(Pango.EllipsizeMode.END)
        content.pack_start(title, False, False, 0)
        if exam.get("role") == "owner":
            rows = self.school.submissions.get(exam["exam_id"], {})
            target = exam.get("target", {})
            target_text = {
                "all": self.t("target_all"),
                "students": self.t("target_students"),
            }.get(target.get("mode"), f"{self.t('class')} {target.get('school_class', '')}")
            detail = f"{target_text} • {len(rows)} {self.t('answers_count')} • {len(exam.get('delivered_to', []))} {self.t('received_count')}"
        else:
            detail = f"{exam.get('subject', '')} • {exam.get('teacher_name', '')}"
            if exam.get("result"):
                content.pack_start(badge(f"{self.t('score')}: {exam['result']['score']}", "success"), False, False, 0)
            elif exam.get("submission"):
                content.pack_start(badge("✓ " + self.t("answer_sent" if not exam["submission"].get("acked") else "answer_received"), "info"), False, False, 0)
        meta = label(detail, "list-meta")
        meta.set_ellipsize(Pango.EllipsizeMode.END)
        content.pack_start(meta, False, False, 0)
        item.add(content)
        item.connect("clicked", lambda *_: self._select_exam(exam["exam_id"]))
        return item

    def _autosave_draft(self) -> None:
        exam = self.school.exams.get(self.selected_exam_id) if self.school else None
        if exam and exam.get("role") != "owner" and getattr(self, "_answer_widgets", None) and self.school.can_submit(exam):
            self._save_exam_draft(exam["exam_id"])

    def _select_exam(self, exam_id: str) -> None:
        self._autosave_draft()
        self.selected_exam_id = exam_id
        self._render_exams()

    def _render_exam_detail(self) -> None:
        if not hasattr(self, "exam_detail") or not self.school:
            return
        clear_box(self.exam_detail)
        self._answer_widgets = {}
        self.exam_countdown = None
        self.submit_button = None
        exam = self.school.exams.get(self.selected_exam_id)
        if not exam:
            hint = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            hint.set_margin_top(60)
            hint.pack_start(label("👈", "empty-icon", 0.5), False, False, 0)
            hint.pack_start(label(self.t("select_exam_hint"), "empty-message", 0.5, wrap=True), False, False, 0)
            if self.profile.role == "teacher":
                how = card(css="card info-card")
                how.pack_start(label(self.t("exam_howto_title"), "card-title"), False, False, 0)
                how.pack_start(label(self.t("exam_howto_teacher"), "card-body", wrap=True), False, False, 0)
                hint.pack_start(how, False, False, 16)
            else:
                how = card(css="card info-card")
                how.pack_start(label(self.t("exam_howto_title"), "card-title"), False, False, 0)
                how.pack_start(label(self.t("exam_howto_student"), "card-body", wrap=True), False, False, 0)
                hint.pack_start(how, False, False, 16)
            self.exam_detail.pack_start(hint, False, False, 0)
        elif exam.get("role") == "owner":
            self._render_teacher_exam(exam)
        else:
            self._render_student_exam(exam)
        self.exam_detail.show_all()

    def _exam_header(self, exam: dict[str, Any]) -> Gtk.Box:
        header = card(css="card exam-header")
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        top.pack_start(badge(self.t("kind_" + exam.get("kind", "exam")), "info"), False, False, 0)
        if exam.get("lock_chat"):
            top.pack_start(badge("🔒 " + self.t("exam_mode"), "warning"), False, False, 0)
        self.exam_countdown = label("", "countdown")
        top.pack_end(self.exam_countdown, False, False, 0)
        header.pack_start(top, False, False, 0)
        header.pack_start(label(exam.get("title", ""), "exam-title", wrap=True), False, False, 0)
        meta = f"{exam.get('subject', '')} • {exam.get('teacher_name', '')} • {format_clock(exam.get('created_at'))}"
        minutes = int(exam.get("duration_minutes", 0) or 0)
        meta += f" • {minutes} {self.t('minutes')}" if minutes else f" • {self.t('no_time_limit')}"
        header.pack_start(label(meta, "muted", wrap=True), False, False, 0)
        if exam.get("instructions"):
            header.pack_start(label(exam["instructions"], "exam-instructions", wrap=True), False, False, 4)
        state = self.school.exam_state(exam)
        self.exam_countdown.set_text(f"⏱ {format_remaining(self.school.remaining_seconds(exam))}  •  {self.t('state_' + state)}")
        return header

    def _render_teacher_exam(self, exam: dict[str, Any]) -> None:
        exam_id = exam["exam_id"]
        self.exam_detail.pack_start(self._exam_header(exam), False, False, 0)
        rows = self.school.submissions.get(exam_id, {})
        targets = self.school.exam_targets(exam)
        stats = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        graded = len([row for row in rows.values() if row.get("score")])
        for value, key in (
            (len(exam.get("delivered_to", [])), "stat_received"),
            (len(rows), "stat_answered"),
            (graded, "stat_graded"),
            (len(targets), "stat_online"),
        ):
            tile = card(spacing=2, css="card stat-tile")
            tile.pack_start(label(str(value), "stat-value", 0.5), False, False, 0)
            tile.pack_start(label(self.t(key), "stat-label", 0.5, wrap=True), False, False, 0)
            stats.pack_start(tile, True, True, 0)
        self.exam_detail.pack_start(stats, False, False, 0)

        actions = Gtk.FlowBox()
        actions.set_selection_mode(Gtk.SelectionMode.NONE)
        actions.set_max_children_per_line(6)
        for text, callback, css in (
            ("📤 " + self.t("resend_exam"), lambda *_: self._resend_exam(exam_id), None),
            ("📊 " + self.t("export_csv"), lambda *_: self._export_exam(exam_id), None),
            ("📁 " + self.t("save_answer_files"), lambda *_: self._save_answer_files(exam_id), None),
            ("⏹ " + self.t("close_exam"), lambda *_: self._close_exam(exam_id), "danger-button"),
            ("🗑 " + self.t("delete"), lambda *_: self._delete_exam(exam_id), "danger-button"),
        ):
            item = button(text, callback, css)
            if "close_exam" in text and exam.get("closed"):
                item.set_sensitive(False)
            actions.add(item)
        if exam.get("file"):
            actions.add(button("📄 " + self.t("open_question_file"), lambda *_: self._open_path(Path(exam["file"]["path"]))))
        self.exam_detail.pack_start(actions, False, False, 0)

        self.exam_detail.pack_start(label(self.t("submissions"), "section-label"), False, False, 6)
        if not rows:
            self.exam_detail.pack_start(label(self.t("no_submissions"), "muted", wrap=True), False, False, 0)
        for row in sorted(rows.values(), key=lambda item: item.get("student_name", "").casefold()):
            line = card(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css="card submission-row")
            names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            names.pack_start(label(row.get("student_name", ""), "list-title"), False, False, 0)
            names.pack_start(label(f"{self.t('class')} {row.get('school_class', '')} • {format_clock(row.get('submitted_at'))}", "list-meta"), False, False, 0)
            line.pack_start(names, True, True, 0)
            if row.get("late"):
                line.pack_start(badge(self.t("late"), "warning"), False, False, 0)
            auto = row.get("auto", {})
            if auto.get("total"):
                line.pack_start(badge(f"{self.t('auto_score')}: {auto.get('correct')}/{auto.get('total')}", "info"), False, False, 0)
            if row.get("score"):
                line.pack_start(badge(f"{self.t('score')}: {row['score']}", "success"), False, False, 0)
            grade = button(self.t("review_and_grade"), lambda *_args, sid=row["student_id"]: self._grade_submission_dialog(exam_id, sid), "small-button primary-small")
            grade.set_valign(Gtk.Align.CENTER)
            line.pack_end(grade, False, False, 0)
            self.exam_detail.pack_start(line, False, False, 0)
        waiting = [
            peer for peer in self.school.online_students()
            if peer.user_id in targets and peer.user_id not in rows
        ]
        if waiting:
            self.exam_detail.pack_start(label(self.t("not_submitted_online"), "section-label"), False, False, 6)
            names = ", ".join(peer.profile.get("full_name", "") for peer in waiting)
            self.exam_detail.pack_start(label(names, "muted", wrap=True), False, False, 0)

    def _render_student_exam(self, exam: dict[str, Any]) -> None:
        exam_id = exam["exam_id"]
        self.exam_detail.pack_start(self._exam_header(exam), False, False, 0)
        result = exam.get("result")
        if result:
            result_card = card(css="card result-card")
            result_card.pack_start(label(f"🏆 {self.t('your_score')}: {result['score']}", "result-score"), False, False, 0)
            if result.get("total"):
                result_card.pack_start(label(f"{self.t('auto_score')}: {result.get('correct')}/{result.get('total')}", "muted"), False, False, 0)
            if result.get("feedback"):
                result_card.pack_start(label(f"{self.t('teacher_feedback')}: {result['feedback']}", "card-body", wrap=True), False, False, 0)
            self.exam_detail.pack_start(result_card, False, False, 0)
        if exam.get("file"):
            file_card = card(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css="card file-card")
            info = exam["file"]
            size = f"{int(info.get('size') or 0) / 1024 / 1024:.1f} MB" if info.get("size") else ""
            file_card.pack_start(label(f"📄  {info.get('name', '')}  {size}", "list-title"), True, True, 0)
            if info.get("path") and Path(info["path"]).exists():
                file_card.pack_end(button("💾 " + self.t("save_as"), lambda *_: self._save_copy(Path(info["path"])), "small-button"), False, False, 0)
                file_card.pack_end(button("📖 " + self.t("open"), lambda *_: self._open_path(Path(info["path"])), "small-button primary-small"), False, False, 0)
            else:
                file_card.pack_end(button("⬇ " + self.t("download_questions"), lambda *_: self._download_exam_file(exam_id), "small-button primary-small"), False, False, 0)
            self.exam_detail.pack_start(file_card, False, False, 0)

        submission = exam.get("submission")
        draft = exam.get("draft") or (submission or {}).get("answers") or {}
        can_submit = self.school.can_submit(exam)
        self._answer_widgets: dict[str, Any] = {}
        for number, question in enumerate(exam.get("questions", []), start=1):
            box = card(spacing=6, css="card question-card")
            head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            head.pack_start(label(f"{number}.", "question-number"), False, False, 0)
            head.pack_start(label(question["text"], "question-text", wrap=True), True, True, 0)
            head.pack_end(label(f"{question.get('points', 1):g} {self.t('points')}", "muted"), False, False, 0)
            box.pack_start(head, False, False, 0)
            if question["type"] == "choice":
                group = None
                radios = []
                for index, option in enumerate(question.get("options", [])):
                    radio = Gtk.RadioButton.new_with_label_from_widget(group, f"{OPTION_LETTERS[index]}.  {option}")
                    radio.get_child().set_line_wrap(True)
                    group = group or radio
                    radios.append(radio)
                    box.pack_start(radio, False, False, 0)
                # A hidden extra radio represents "not answered yet".
                none_radio = Gtk.RadioButton.new_from_widget(group)
                none_radio.set_no_show_all(True)
                none_radio.set_active(True)
                chosen = draft.get(question["qid"])
                if chosen is not None and 0 <= int(chosen) < len(radios):
                    radios[int(chosen)].set_active(True)
                for radio in radios:
                    radio.set_sensitive(can_submit)
                self._answer_widgets[question["qid"]] = ("choice", radios)
            else:
                view = text_view(str(draft.get(question["qid"], "")), 110, editable=can_submit)
                box.pack_start(framed(view), False, False, 0)
                self._answer_widgets[question["qid"]] = ("essay", view)
            self.exam_detail.pack_start(box, False, False, 0)

        self._answer_file: Path | None = None
        if exam.get("allow_file", True):
            attach = card(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, css="card file-card")
            existing = (submission or {}).get("file", {})
            self.answer_file_label = label(existing.get("name") or self.t("no_answer_file"), "muted")
            self.answer_file_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            attach.pack_start(label("📎", "list-title"), False, False, 0)
            attach.pack_start(self.answer_file_label, True, True, 0)
            choose = button(self.t("attach_answer_file"), lambda *_: self._choose_answer_file(), "small-button")
            choose.set_sensitive(can_submit)
            attach.pack_end(choose, False, False, 0)
            self.exam_detail.pack_start(attach, False, False, 0)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        status_text = self.t("not_submitted")
        if submission:
            status_text = (self.t("answer_received") if submission.get("acked") else self.t("answer_sent_waiting")) + f" • {format_clock(submission.get('submitted_at'))}"
        footer.pack_start(label(status_text, "muted", wrap=True), True, True, 0)
        save = button("💾 " + self.t("save_draft"), lambda *_: self._save_exam_draft(exam_id, notify=True))
        save.set_sensitive(can_submit)
        footer.pack_end(save, False, False, 0)
        self.submit_button = button("📨 " + (self.t("resubmit") if submission else self.t("submit_answers")), lambda *_: self._submit_exam(exam_id), "primary-button")
        self.submit_button.set_sensitive(can_submit)
        footer.pack_end(self.submit_button, False, False, 0)
        self.exam_detail.pack_start(footer, False, False, 8)

    def _collect_answers(self) -> dict[str, Any]:
        answers: dict[str, Any] = {}
        for qid, (kind, widget) in getattr(self, "_answer_widgets", {}).items():
            if kind == "choice":
                for index, radio in enumerate(widget):
                    if radio.get_active():
                        answers[qid] = index
            else:
                value = text_of(widget).strip()
                if value:
                    answers[qid] = value
        return answers

    def _save_exam_draft(self, exam_id: str, notify: bool = False) -> None:
        self.school.save_draft(exam_id, self._collect_answers())
        if notify:
            self._show_toast(self.t("draft_saved"))

    def _choose_answer_file(self) -> None:
        path = self._choose_media_file("document", self.t("attach_answer_file"))
        if not path:
            return
        try:
            size = path.stat().st_size
        except OSError:
            return
        if size <= 0 or size > DOCUMENT_LIMIT:
            self._error(self.t("attachment_error"), self.t("document_limit"))
            return
        self._answer_file = path
        self.answer_file_label.set_text(path.name)

    def _download_exam_file(self, exam_id: str) -> None:
        if self.school.request_exam_file(exam_id):
            self._show_toast(self.t("download_requested"))
        else:
            self._error(self.t("download_questions"), self.t("teacher_offline"))

    def _submit_exam(self, exam_id: str) -> None:
        exam = self.school.exams.get(exam_id)
        if not exam:
            return
        answers = self._collect_answers()
        questions = exam.get("questions", [])
        unanswered = len([q for q in questions if q["qid"] not in answers])
        detail = self.t("submit_confirm_detail")
        if unanswered:
            detail = self.t("unanswered_warning").format(count=unanswered) + "\n\n" + detail
        if not answers and not self._answer_file and not (exam.get("submission") or {}).get("file"):
            self._error(self.t("submit_answers"), self.t("empty_submission"))
            return
        if not self._confirm(self.t("submit_confirm"), detail, self.t("submit_answers")):
            return
        answer_file = self._answer_file
        if answer_file is None and exam.get("submission", {}).get("file"):
            answer_file = Path(exam["submission"]["file"]["path"])
        try:
            self.school.submit_exam(exam_id, answers, answer_file)
        except PermissionError:
            self._error(self.t("submit_answers"), self.t("exam_is_closed"))
            return
        except (OSError, ValueError) as error:
            self._error(self.t("submit_answers"), self.t(str(error)) if str(error) == "document_limit" else str(error))
            return
        teacher_online = any(peer.user_id == exam.get("teacher_id") for peer in self.peers)
        self._show_toast(self.t("answer_sent") if teacher_online else self.t("answer_queued"))
        self._render_exams()
        self._update_nav_badges()

    def _resend_exam(self, exam_id: str) -> None:
        count = self.school.publish_exam(exam_id, force=True)
        self._show_toast(self.t("exam_sent_to").format(count=count))

    def _close_exam(self, exam_id: str) -> None:
        if self._confirm(self.t("close_exam_confirm"), self.t("close_exam_detail"), self.t("close_exam")):
            self.school.close_exam(exam_id)
            self._render_exams()

    def _delete_exam(self, exam_id: str) -> None:
        if self._confirm(self.t("delete_exam_confirm"), self.t("delete_exam_detail"), self.t("delete")):
            self.school.delete_exam(exam_id)
            self.selected_exam_id = ""
            self._render_exams()

    def _export_exam(self, exam_id: str) -> None:
        exam = self.school.exams.get(exam_id, {})
        suggested = f"{exam.get('title', 'exam')}-{datetime.now():%Y%m%d}.csv".replace("/", "-")
        destination = self._choose_save_path(suggested, self.t("export_csv"))
        if destination:
            try:
                self.school.export_results_csv(exam_id, destination)
                self._show_toast(self.t("saved") + ": " + destination.name)
            except OSError as error:
                self._error(self.t("export_csv"), str(error))

    def _save_answer_files(self, exam_id: str) -> None:
        folder = self._choose_folder(self.t("save_answer_files"))
        if folder:
            try:
                count = self.school.copy_answer_files(exam_id, folder)
                self._info(self.t("save_answer_files"), self.t("files_copied").format(count=count, folder=folder))
            except OSError as error:
                self._error(self.t("save_answer_files"), str(error))

    def _create_exam_dialog(self) -> None:
        if self.profile.role != "teacher":
            self._error(self.t("create_exam"), self.t("teacher_only"))
            return
        dialog = Gtk.Dialog(title=self.t("create_exam"), transient_for=self, modal=True)
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, "📤 " + self.t("publish_exam"), Gtk.ResponseType.OK)
        dialog.set_default_size(720, 680)
        area = dialog.get_content_area()
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        margins(content, 16)
        scroller = scrolled(content)
        scroller.set_vexpand(True)
        area.pack_start(scroller, True, True, 0)

        kind = Gtk.ComboBoxText()
        for value in ("exam", "assignment", "quiz"):
            kind.append(value, self.t("kind_" + value))
        kind.set_active_id("exam")
        title = Gtk.Entry()
        title.set_placeholder_text(self.t("exam_title_hint"))
        subject = Gtk.Entry(text=self.profile.subject)
        row = Gtk.Grid(column_spacing=10, row_spacing=8)
        row.set_column_homogeneous(True)
        row.attach(self._form_row("exam_kind", kind), 0, 0, 1, 1)
        row.attach(self._form_row("subject", subject), 1, 0, 1, 1)
        content.pack_start(row, False, False, 0)
        content.pack_start(self._form_row("exam_title", title), False, False, 0)
        instructions = text_view("", 70)
        content.pack_start(self._form_row("instructions", framed(instructions)), False, False, 0)

        target_grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        target_grid.set_column_homogeneous(True)
        mode = Gtk.ComboBoxText()
        for value, key in (("class", "target_class"), ("all", "target_all"), ("students", "target_students")):
            mode.append(value, self.t(key))
        mode.set_active_id("class")
        class_combo = Gtk.ComboBoxText.new_with_entry()
        for item in self.school.known_classes():
            class_combo.append_text(item)
        class_combo.get_child().set_text(self.profile.school_class)
        duration = Gtk.SpinButton.new_with_range(0, 600, 5)
        duration.set_value(60)
        target_grid.attach(self._form_row("target", mode), 0, 0, 1, 1)
        target_grid.attach(self._form_row("class", class_combo), 1, 0, 1, 1)
        target_grid.attach(self._form_row("duration_minutes", duration), 2, 0, 1, 1)
        content.pack_start(target_grid, False, False, 0)
        student_box = Gtk.FlowBox()
        student_box.set_selection_mode(Gtk.SelectionMode.NONE)
        student_box.set_max_children_per_line(3)
        student_checks = []
        for peer in self.school.online_students():
            check = Gtk.CheckButton(label=f"{peer.profile.get('full_name', '')} ({peer.profile.get('school_class', '')})")
            student_checks.append((check, peer.user_id))
            student_box.add(check)
        student_row = self._form_row("choose_students", student_box)
        student_row.set_no_show_all(True)
        content.pack_start(student_row, False, False, 0)

        def mode_changed(*_args):
            selected = mode.get_active_id()
            class_combo.set_sensitive(selected == "class")
            if selected == "students":
                student_row.set_no_show_all(False)
                student_row.show_all()
            else:
                student_row.hide()

        mode.connect("changed", mode_changed)

        file_state: dict[str, Path | None] = {"path": None}
        file_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        file_label = label(self.t("no_question_file"), "muted")
        file_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)

        def choose_file(*_args):
            path = self._choose_media_file("document", self.t("question_file"), dialog)
            if path:
                try:
                    if path.stat().st_size > DOCUMENT_LIMIT:
                        self._error(self.t("attachment_error"), self.t("document_limit"))
                        return
                except OSError:
                    return
                file_state["path"] = path
                file_label.set_text(path.name)

        file_row.pack_start(button("📄 " + self.t("choose_question_file"), choose_file), False, False, 0)
        file_row.pack_start(file_label, True, True, 0)
        content.pack_start(self._form_row("question_file", file_row), False, False, 0)

        options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lock_chat = Gtk.CheckButton(label=self.t("option_lock_chat"))
        lock_chat.set_active(True)
        allow_late = Gtk.CheckButton(label=self.t("option_allow_late"))
        allow_file = Gtk.CheckButton(label=self.t("option_allow_file"))
        allow_file.set_active(True)
        for check in (lock_chat, allow_late, allow_file):
            options.pack_start(check, False, False, 0)
        kind.connect("changed", lambda *_: lock_chat.set_active(kind.get_active_id() != "assignment"))
        content.pack_start(self._form_row("exam_rules", options), False, False, 0)

        content.pack_start(label(self.t("questions"), "section-label"), False, False, 6)
        content.pack_start(label(self.t("questions_hint"), "muted", wrap=True), False, False, 0)
        question_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.pack_start(question_list, False, False, 0)
        editors: list[dict[str, Any]] = []

        def renumber():
            for index, editor in enumerate(editors, start=1):
                editor["number"].set_text(f"{index}. {self.t('question_' + editor['type'])}")

        def add_question(question_type: str):
            box = card(spacing=6, css="card question-editor")
            head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            number = label("", "question-number")
            head.pack_start(number, True, True, 0)
            points = Gtk.SpinButton.new_with_range(0, 100, 1)
            points.set_value(1 if question_type == "choice" else 10)
            head.pack_end(points, False, False, 0)
            head.pack_end(label(self.t("points"), "muted"), False, False, 0)
            editor: dict[str, Any] = {"type": question_type, "number": number, "points": points, "box": box}
            remove = button("✕", None, "small-button", self.t("delete"))

            def remove_question(*_args):
                editors.remove(editor)
                question_list.remove(box)
                renumber()

            remove.connect("clicked", remove_question)
            head.pack_end(remove, False, False, 0)
            box.pack_start(head, False, False, 0)
            text = text_view("", 50)
            editor["text"] = text
            box.pack_start(framed(text), False, False, 0)
            if question_type == "choice":
                grid = Gtk.Grid(column_spacing=8, row_spacing=4)
                option_entries = []
                correct = Gtk.ComboBoxText()
                for index, letter in enumerate(OPTION_LETTERS[:4]):
                    entry = Gtk.Entry()
                    entry.set_placeholder_text(f"{self.t('option')} {letter}")
                    entry.set_hexpand(True)
                    grid.attach(label(letter, "option-letter"), 0, index, 1, 1)
                    grid.attach(entry, 1, index, 1, 1)
                    option_entries.append(entry)
                    correct.append(str(index), letter)
                correct.set_active(0)
                box.pack_start(grid, False, False, 0)
                correct_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                correct_row.pack_start(label(self.t("correct_answer"), "field-label"), False, False, 0)
                correct_row.pack_start(correct, False, False, 0)
                box.pack_start(correct_row, False, False, 0)
                editor["options"] = option_entries
                editor["correct"] = correct
            editors.append(editor)
            question_list.pack_start(box, False, False, 0)
            box.show_all()
            renumber()

        add_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        add_row.pack_start(button("＋ " + self.t("add_choice_question"), lambda *_: add_question("choice")), False, False, 0)
        add_row.pack_start(button("＋ " + self.t("add_essay_question"), lambda *_: add_question("essay")), False, False, 0)
        content.pack_start(add_row, False, False, 0)
        error_label = label("", "error-text", wrap=True)
        content.pack_start(error_label, False, False, 0)

        dialog.show_all()
        mode_changed()
        while True:
            response = dialog.run()
            if response != Gtk.ResponseType.OK:
                dialog.destroy()
                return
            questions = []
            answer_key: dict[str, int] = {}
            problem = ""
            for index, editor in enumerate(editors, start=1):
                qid = f"q{index}"
                question_text = text_of(editor["text"]).strip()
                if not question_text:
                    problem = self.t("question_text_missing").format(number=index)
                    break
                question = {"qid": qid, "type": editor["type"], "text": question_text, "points": editor["points"].get_value()}
                if editor["type"] == "choice":
                    filled = [(position, entry.get_text().strip()) for position, entry in enumerate(editor["options"]) if entry.get_text().strip()]
                    if len(filled) < 2:
                        problem = self.t("question_options_missing").format(number=index)
                        break
                    correct_position = int(editor["correct"].get_active_id() or 0)
                    if correct_position not in [position for position, _ in filled]:
                        problem = self.t("question_correct_missing").format(number=index)
                        break
                    question["options"] = [value for _, value in filled]
                    answer_key[qid] = [position for position, _ in filled].index(correct_position)
                questions.append(question)
            title_value = title.get_text().strip()
            target = {
                "mode": mode.get_active_id() or "class",
                "school_class": class_combo.get_child().get_text().strip(),
                "student_ids": [user_id for check, user_id in student_checks if check.get_active()],
            }
            if not problem and not title_value:
                problem = self.t("exam_title_missing")
            if not problem and not questions and not file_state["path"] and not text_of(instructions).strip():
                problem = self.t("exam_content_missing")
            if not problem and target["mode"] == "class" and not target["school_class"]:
                problem = self.t("class_error")
            if not problem and target["mode"] == "students" and not target["student_ids"]:
                problem = self.t("choose_students")
            if problem:
                error_label.set_text("⚠ " + problem)
                continue
            try:
                exam = self.school.create_exam(
                    kind.get_active_id() or "exam", title_value, subject.get_text().strip(), text_of(instructions),
                    target, duration.get_value_as_int(), questions, answer_key,
                    lock_chat=lock_chat.get_active(), allow_late=allow_late.get_active(),
                    allow_file=allow_file.get_active(), question_file=file_state["path"],
                )
            except (OSError, ValueError) as error:
                error_label.set_text("⚠ " + (self.t("document_limit") if str(error) == "document_limit" else str(error)))
                continue
            break
        dialog.destroy()
        self.selected_exam_id = exam["exam_id"]
        self._switch_page("exams")
        self._render_exams()
        sent = len(exam.get("delivered_to", [])) or len(self.school.exam_targets(exam))
        self._show_toast(self.t("exam_published").format(count=sent))

    def _grade_submission_dialog(self, exam_id: str, student_id: str) -> None:
        exam = self.school.exams.get(exam_id)
        row = self.school.submissions.get(exam_id, {}).get(student_id)
        if not exam or not row:
            return
        dialog = Gtk.Dialog(title=f"{self.t('review_and_grade')} • {row.get('student_name', '')}", transient_for=self, modal=True)
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, "📨 " + self.t("send_result"), Gtk.ResponseType.OK)
        dialog.set_default_size(680, 640)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        margins(content, 16)
        scroller = scrolled(content)
        scroller.set_vexpand(True)
        dialog.get_content_area().pack_start(scroller, True, True, 0)
        summary = card(css="card exam-header")
        summary.pack_start(label(row.get("student_name", ""), "exam-title"), False, False, 0)
        summary.pack_start(label(f"{self.t('class')} {row.get('school_class', '')} • {row.get('room', '')} • {format_clock(row.get('submitted_at'))}", "muted"), False, False, 0)
        if row.get("late"):
            summary.pack_start(badge(self.t("late"), "warning"), False, False, 0)
        auto = row.get("auto", {})
        if auto.get("total"):
            summary.pack_start(label(f"{self.t('auto_score')}: {auto.get('correct')}/{auto.get('total')} ({auto.get('percent')}%) • {auto.get('points'):g}/{auto.get('max_points'):g} {self.t('points')}", "list-title"), False, False, 0)
        content.pack_start(summary, False, False, 0)
        key = exam.get("answer_key", {})
        answers = row.get("answers", {})
        for number, question in enumerate(exam.get("questions", []), start=1):
            box = card(spacing=4, css="card question-card")
            box.pack_start(label(f"{number}. {question['text']}", "question-text", wrap=True), False, False, 0)
            given = answers.get(question["qid"])
            if question["type"] == "choice":
                options = question.get("options", [])
                expected = key.get(question["qid"])
                given_text = f"{OPTION_LETTERS[int(given)]}. {options[int(given)]}" if given is not None and 0 <= int(given) < len(options) else self.t("no_answer")
                correct = given is not None and expected is not None and int(given) == int(expected)
                box.pack_start(label(("✅ " if correct else "❌ ") + given_text, "answer-text", wrap=True), False, False, 0)
                if not correct and expected is not None and 0 <= int(expected) < len(options):
                    box.pack_start(label(f"{self.t('correct_answer')}: {OPTION_LETTERS[int(expected)]}. {options[int(expected)]}", "muted", wrap=True), False, False, 0)
            else:
                box.pack_start(label(str(given) if given else self.t("no_answer"), "answer-text essay-answer", wrap=True), False, False, 0)
            content.pack_start(box, False, False, 0)
        if row.get("file"):
            file_path = Path(row["file"]["path"])
            file_box = card(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, css="card file-card")
            file_box.pack_start(label(f"📎 {row['file'].get('name', '')}", "list-title"), True, True, 0)
            file_box.pack_end(button(self.t("save_as"), lambda *_: self._save_copy(file_path), "small-button"), False, False, 0)
            file_box.pack_end(button(self.t("open"), lambda *_: self._open_path(file_path), "small-button primary-small"), False, False, 0)
            content.pack_start(file_box, False, False, 0)
        score = Gtk.Entry(text=str(row.get("score") or (auto.get("percent") if auto.get("total") and not auto.get("essays") and auto.get("percent") is not None else "")))
        score.set_placeholder_text("0 - 100")
        feedback = text_view(row.get("feedback", ""), 80)
        content.pack_start(self._form_row("final_score", score), False, False, 0)
        content.pack_start(self._form_row("teacher_feedback", framed(feedback)), False, False, 0)
        dialog.show_all()
        response = dialog.run()
        score_value = score.get_text().strip()
        feedback_value = text_of(feedback).strip()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        if not score_value:
            self._error(self.t("send_result"), self.t("score_missing"))
            return
        self.school.return_result(exam_id, student_id, score_value, feedback_value)
        online = any(peer.user_id == student_id for peer in self.peers)
        self._show_toast(self.t("result_sent") if online else self.t("result_saved_offline"))
        self._render_exams()
        self._update_nav_badges()

    # Attendance page -----------------------------------------------------
    def _build_attendance_page(self) -> Gtk.Widget:
        teacher = self.profile.role == "teacher"
        page, _header, actions = self._page("attendance_title", "attendance_subtitle_teacher" if teacher else "attendance_subtitle_student")
        if teacher:
            actions.pack_start(button("＋ " + self.t("start_attendance"), lambda *_: self._start_attendance_dialog(), "primary-button"), False, False, 0)
        self.attendance_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        margins(self.attendance_box, 18)
        page.pack_start(scrolled(self.attendance_box), True, True, 0)
        self._render_attendance()
        return page

    def _render_attendance(self) -> None:
        if not hasattr(self, "attendance_box") or not self.school:
            return
        clear_box(self.attendance_box)
        sessions = sorted(self.school.attendance.values(), key=lambda item: float(item.get("opened_at", item.get("received_at", 0))), reverse=True)
        if not sessions:
            empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            empty.set_margin_top(50)
            empty.pack_start(label("✅", "empty-icon", 0.5), False, False, 0)
            empty.pack_start(label(self.t("no_attendance_teacher" if self.profile.role == "teacher" else "no_attendance_student"), "empty-message", 0.5, wrap=True), False, False, 0)
            self.attendance_box.pack_start(empty, False, False, 0)
        for session in sessions[:40]:
            if session.get("role") == "owner":
                self.attendance_box.pack_start(self._teacher_attendance_card(session), False, False, 0)
            else:
                self.attendance_box.pack_start(self._student_attendance_card(session), False, False, 0)
        self.attendance_box.show_all()

    def _teacher_attendance_card(self, session: dict[str, Any]) -> Gtk.Widget:
        box = card(spacing=6)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.pack_start(label(session.get("title", ""), "list-title"), False, False, 0)
        open_now = self.school.attendance_open(session)
        head.pack_start(badge(self.t("state_open" if open_now else "state_closed"), "success" if open_now else "muted"), False, False, 0)
        present = session.get("present", {})
        class_students = [
            peer for peer in self.school.online_students()
            if not session.get("school_class") or self.school.matches_target({"mode": "class", "school_class": session["school_class"]}, peer.user_id, peer.profile)
        ]
        head.pack_end(button("📊 " + self.t("export_csv"), lambda *_: self._export_attendance(session["session_id"]), "small-button"), False, False, 0)
        if open_now:
            head.pack_end(button("⏹ " + self.t("close_attendance"), lambda *_: (self.school.close_attendance(session["session_id"]), self._render_attendance()), "small-button"), False, False, 0)
        box.pack_start(head, False, False, 0)
        box.pack_start(label(
            f"{self.t('class')} {session.get('school_class') or self.t('target_all')} • {format_clock(session.get('opened_at'))} • "
            f"{len(present)} {self.t('present')} • {len(class_students)} {self.t('online_now')}", "muted", wrap=True,
        ), False, False, 0)
        if present:
            names = ", ".join(
                row.get("name", "") + (" ⏰" if row.get("late") else "")
                for row in sorted(present.values(), key=lambda item: item.get("name", "").casefold())
            )
            box.pack_start(label("✅ " + names, "card-body", wrap=True), False, False, 0)
        missing = [peer.profile.get("full_name", "") for peer in class_students if peer.user_id not in present]
        if missing and open_now:
            box.pack_start(label("⏳ " + self.t("waiting_for") + ": " + ", ".join(missing), "muted", wrap=True), False, False, 0)
        return box

    def _student_attendance_card(self, session: dict[str, Any]) -> Gtk.Widget:
        box = card(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info.pack_start(label(session.get("title", ""), "list-title"), False, False, 0)
        info.pack_start(label(f"{session.get('teacher_name', '')} • {format_clock(session.get('received_at'))}", "muted"), False, False, 0)
        box.pack_start(info, True, True, 0)
        if session.get("answered_at"):
            box.pack_end(badge("✓ " + (self.t("attendance_recorded") if session.get("acked") else self.t("attendance_sending")), "success"), False, False, 0)
        elif self.school.attendance_open(session):
            box.pack_end(button("✋ " + self.t("i_am_present"), lambda *_: self._mark_present(session["session_id"]), "primary-button"), False, False, 0)
        else:
            box.pack_end(badge(self.t("state_closed"), "muted"), False, False, 0)
        return box

    def _mark_present(self, session_id: str) -> None:
        if self.school.mark_present(session_id):
            self._show_toast(self.t("attendance_sending"))
        self._render_attendance()
        self._update_nav_badges()

    def _start_attendance_dialog(self) -> None:
        dialog = Gtk.Dialog(title=self.t("start_attendance"), transient_for=self, modal=True)
        dialog.add_buttons(self.t("cancel"), Gtk.ResponseType.CANCEL, self.t("start"), Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        margins(box, 16)
        title = Gtk.Entry(text=f"{self.t('attendance')} {datetime.now():%d/%m/%Y}")
        class_combo = Gtk.ComboBoxText.new_with_entry()
        for item in self.school.known_classes():
            class_combo.append_text(item)
        class_combo.get_child().set_text(self.profile.school_class)
        minutes = Gtk.SpinButton.new_with_range(1, 240, 1)
        minutes.set_value(10)
        box.add(self._form_row("attendance_name", title))
        box.add(self._form_row("class", class_combo))
        box.add(label(self.t("attendance_class_hint"), "muted", wrap=True))
        box.add(self._form_row("open_minutes", minutes))
        dialog.show_all()
        response = dialog.run()
        values = (title.get_text().strip(), class_combo.get_child().get_text().strip(), minutes.get_value_as_int())
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        session = self.school.open_attendance(*values)
        self._render_attendance()
        self._show_toast(self.t("attendance_started").format(count=len(session.get("delivered_to", [])) or len(self.school.online_students())))

    def _export_attendance(self, session_id: str) -> None:
        session = self.school.attendance.get(session_id, {})
        destination = self._choose_save_path(f"{session.get('title', 'attendance')}.csv".replace("/", "-"), self.t("export_csv"))
        if destination:
            try:
                self.school.export_attendance_csv(session_id, destination)
                self._show_toast(self.t("saved") + ": " + destination.name)
            except OSError as error:
                self._error(self.t("export_csv"), str(error))

    # Rules page ----------------------------------------------------------
    def _build_rules_page(self) -> Gtk.Widget:
        page, _header, _actions = self._page("rules_title", "rules_subtitle")
        self.rules_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        margins(self.rules_box, 18)
        page.pack_start(scrolled(self.rules_box), True, True, 0)
        self._render_rules()
        return page

    def _render_rules(self) -> None:
        if not hasattr(self, "rules_box") or not self.school:
            return
        clear_box(self.rules_box)
        custom = self.school.rules
        if custom.get("text"):
            school_card = card(css="card rules-card")
            school_card.pack_start(label("🏫 " + self.t("school_rules"), "card-title"), False, False, 0)
            school_card.pack_start(label(f"{custom.get('teacher_name', '')} • {format_clock(custom.get('updated_at'))}", "muted"), False, False, 0)
            school_card.pack_start(label(custom["text"], "rules-text", wrap=True), False, False, 4)
            self.rules_box.pack_start(school_card, False, False, 0)
        default_card = card(css="card")
        default_card.pack_start(label("📜 " + self.t("rules_title"), "card-title"), False, False, 0)
        default_card.pack_start(label(self.t("default_rules"), "rules-text", wrap=True), False, False, 4)
        self.rules_box.pack_start(default_card, False, False, 0)
        policy = card(css="card info-card")
        policy.pack_start(label("🛡 " + self.t("enforced_rules"), "card-title"), False, False, 0)
        policy.pack_start(label(self.t("enforced_rules_body"), "card-body", wrap=True), False, False, 0)
        self.rules_box.pack_start(policy, False, False, 0)
        if self.profile.role == "teacher":
            editor = card()
            editor.pack_start(label("✏ " + self.t("edit_school_rules"), "card-title"), False, False, 0)
            editor.pack_start(label(self.t("edit_school_rules_hint"), "muted", wrap=True), False, False, 0)
            view = text_view(custom.get("text", ""), 160)
            editor.pack_start(framed(view), False, False, 0)
            publish = button("📤 " + self.t("publish_rules"), lambda *_: self._publish_rules(view), "primary-button")
            publish.set_halign(Gtk.Align.END)
            editor.pack_start(publish, False, False, 0)
            self.rules_box.pack_start(editor, False, False, 0)
        self.rules_box.show_all()

    def _publish_rules(self, view: Gtk.TextView) -> None:
        value = text_of(view).strip()
        if not value:
            self._error(self.t("publish_rules"), self.t("rules_empty"))
            return
        self.school.publish_rules(value)
        self._render_rules()
        self._show_toast(self.t("rules_published"))

    # Network page --------------------------------------------------------
    def _build_network_page(self) -> Gtk.Widget:
        page, _header, actions = self._page("network_title", "network_subtitle")
        actions.pack_start(button("↻ " + self.t("refresh_online"), self._refresh_online, "primary-button"), False, False, 0)
        actions.pack_start(button("🔗 " + self.t("connect_ip"), self._connect_ip_dialog), False, False, 0)
        actions.pack_start(button("🎥 " + self.t("media_devices"), self._show_devices_dialog), False, False, 0)
        self.network_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        margins(self.network_box, 18)
        page.pack_start(scrolled(self.network_box), True, True, 0)
        self._render_network()
        return page

    def _render_network(self) -> None:
        if not hasattr(self, "network_box") or not self.profile:
            return
        clear_box(self.network_box)
        info = self.network.diagnostics() if self.network else {"interfaces": [], "direct": 0, "relayed": 0, "tcp_port": "-", "listening_discovery": False, "last_sweep": 0}
        tiles = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        for value, key in (
            (info["direct"], "stat_direct"), (info["relayed"], "stat_relayed"),
            (len(info["interfaces"]), "stat_interfaces"), (info["tcp_port"], "stat_port"),
        ):
            tile = card(spacing=2, css="card stat-tile")
            tile.pack_start(label(str(value), "stat-value", 0.5), False, False, 0)
            tile.pack_start(label(self.t(key), "stat-label", 0.5, wrap=True), False, False, 0)
            tiles.pack_start(tile, True, True, 0)
        self.network_box.pack_start(tiles, False, False, 0)

        interfaces = card()
        interfaces.pack_start(label(self.t("my_connections"), "card-title"), False, False, 0)
        if not info["interfaces"]:
            interfaces.pack_start(label("⚠ " + self.t("no_network"), "error-text", wrap=True), False, False, 0)
        for item in info["interfaces"]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            kind = item.get("kind", "other")
            icon = {"wifi": "📶", "ethernet": "🔌"}.get(kind, "🌐")
            row.pack_start(label(icon, "list-title"), False, False, 0)
            parts = " • ".join(part for part in (self.t("iface_" + kind), item.get("interface", ""), item.get("network", "")) if part)
            row.pack_start(label(f"{item['address']}  ({parts})", "card-body"), True, True, 0)
            copy = button(self.t("copy"), lambda _b, value=item["address"]: self._copy_text(value), "small-button")
            row.pack_end(copy, False, False, 0)
            interfaces.pack_start(row, False, False, 0)
        discovery = self.t("discovery_on") if info.get("listening_discovery") else self.t("discovery_off")
        last = format_clock(info.get("last_sweep")) if info.get("last_sweep") else "-"
        interfaces.pack_start(label(f"{discovery} • {self.t('last_scan')}: {last}", "muted", wrap=True), False, False, 0)
        self.network_box.pack_start(interfaces, False, False, 0)

        peers_card = card()
        peers_card.pack_start(label(self.t("connected_users"), "card-title"), False, False, 0)
        if not self.peers:
            peers_card.pack_start(label(self.t("nobody_online_hint"), "muted", wrap=True), False, False, 0)
        names = {peer.user_id: peer.profile.get("full_name", "") for peer in self.peers}
        for peer in self.peers:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            role = peer.profile.get("role", "student")
            row.pack_start(badge(self.t(role), "teacher" if role == "teacher" else "student"), False, False, 0)
            row.pack_start(label(peer.profile.get("full_name", ""), "list-title"), False, False, 0)
            how = f"{self.t('connection_direct')} • {peer.ip}" if peer.direct else f"{self.t('connection_relay')}: {names.get(peer.via, peer.via[:15])}"
            row.pack_end(label(how, "muted"), False, False, 0)
            peers_card.pack_start(row, False, False, 0)
        self.network_box.pack_start(peers_card, False, False, 0)

        remembered = self.storage.known_peer_ips()[:12]
        if remembered:
            known = card()
            known.pack_start(label(self.t("remembered_addresses"), "card-title"), False, False, 0)
            flow = Gtk.FlowBox()
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_max_children_per_line(6)
            for ip in remembered:
                chip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                add_class(chip, "chip")
                chip.pack_start(label(ip, "card-body"), False, False, 0)
                chip.pack_start(button("✕", lambda _b, value=ip: self._forget_ip(value), "chip-close", self.t("forget")), False, False, 0)
                flow.add(chip)
            known.pack_start(flow, False, False, 0)
            self.network_box.pack_start(known, False, False, 0)

        help_card = card(css="card info-card")
        help_card.pack_start(label("🛠 " + self.t("wifi_help_title"), "card-title"), False, False, 0)
        help_card.pack_start(label(self.t("wifi_help_body"), "card-body", wrap=True), False, False, 0)
        self.network_box.pack_start(help_card, False, False, 0)
        self.network_box.show_all()

    def _forget_ip(self, ip: str) -> None:
        self.storage.forget_peer_ip(ip)
        if self.network:
            self.network.seed_ips.discard(ip)
        self._render_network()

    def _copy_text(self, value: str) -> None:
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(value, -1)
        self._show_toast(self.t("copied") + ": " + value)

    # Settings page -------------------------------------------------------
    def _build_settings_page(self) -> Gtk.Widget:
        page, _header, _actions = self._page("settings_title", "settings_subtitle")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        margins(box, 18)
        settings = self.storage.settings

        general = card()
        general.pack_start(label(self.t("general"), "card-title"), False, False, 0)
        language = Gtk.ComboBoxText()
        for code, name in LANGUAGES.items():
            language.append(code, name)
        language.set_active_id(self.language)
        language.connect("changed", self._settings_language_changed)
        general.pack_start(self._setting_row("language", "language_hint", language), False, False, 0)
        large = Gtk.Switch()
        large.set_active(bool(settings.get("large_text")))
        large.connect("notify::active", self._settings_large_text)
        general.pack_start(self._setting_row("large_text", "large_text_hint", large), False, False, 0)
        appearance = Gtk.ComboBoxText()
        for value in ("system", "light", "dark"):
            appearance.append(value, self.t("appearance_" + value))
        appearance.set_active_id(settings.get("appearance", "system"))
        appearance.connect("changed", self._settings_appearance)
        general.pack_start(self._setting_row("appearance", "appearance_hint", appearance), False, False, 0)
        box.pack_start(general, False, False, 0)

        notifications = card()
        notifications.pack_start(label(self.t("notifications"), "card-title"), False, False, 0)
        for key, hint in (("desktop_notifications", "desktop_notifications_hint"), ("notification_sound", "notification_sound_hint")):
            switch = Gtk.Switch()
            switch.set_active(bool(settings.get(key, True)))
            switch.connect("notify::active", lambda widget, _param, name=key: self.storage.save_settings(**{name: widget.get_active()}))
            notifications.pack_start(self._setting_row(key, hint, switch), False, False, 0)
        box.pack_start(notifications, False, False, 0)

        moderation = card()
        moderation.pack_start(label(self.t("chat_rules"), "card-title"), False, False, 0)
        word_filter = Gtk.Switch()
        word_filter.set_active(bool(settings.get("word_filter", True)))

        def filter_changed(widget, _param):
            self.storage.save_settings(word_filter=widget.get_active())
            self._render_messages()

        word_filter.connect("notify::active", filter_changed)
        moderation.pack_start(self._setting_row("word_filter", "word_filter_hint", word_filter), False, False, 0)
        words = Gtk.Entry(text=", ".join(settings.get("filter_words", [])))
        words.set_placeholder_text(self.t("filter_words_hint"))
        save_words = button(self.t("save"), lambda *_: (self.storage.save_settings(filter_words=parse_word_list(words.get_text())), self._render_messages(), self._show_toast(self.t("saved"))), "small-button")
        words_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        words_row.pack_start(words, True, True, 0)
        words_row.pack_start(save_words, False, False, 0)
        moderation.pack_start(self._form_row("filter_words", words_row), False, False, 0)
        moderation.pack_start(label(self.t("default_filter_note").format(count=len(DEFAULT_BLOCKED_WORDS)), "muted", wrap=True), False, False, 0)
        box.pack_start(moderation, False, False, 0)

        data = card()
        data.pack_start(label(self.t("data_privacy"), "card-title"), False, False, 0)
        data.pack_start(label(self.t("session_privacy"), "card-body", wrap=True), False, False, 0)
        data.pack_start(label(self.t("records_note"), "card-body", wrap=True), False, False, 0)
        folder_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        path_label = label(str(self.school.base_dir if self.school else self.storage.records_dir), "muted")
        path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        path_label.set_selectable(True)
        folder_row.pack_start(path_label, True, True, 0)
        folder_row.pack_end(button("📂 " + self.t("open_folder"), lambda *_: self._open_path(self.school.base_dir if self.school else self.storage.records_dir), "small-button"), False, False, 0)
        data.pack_start(folder_row, False, False, 0)
        box.pack_start(data, False, False, 0)

        account = card()
        account.pack_start(label(self.t("account"), "card-title"), False, False, 0)
        account_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        account_row.pack_start(button("✏ " + self.t("edit_profile"), lambda *_: self._edit_profile()), False, False, 0)
        account_row.pack_start(button("ℹ " + self.t("about"), lambda *_: self.show_about()), False, False, 0)
        account_row.pack_end(button("⎋ " + self.t("logout"), lambda *_: self._confirm_logout(), "danger-button"), False, False, 0)
        account.pack_start(account_row, False, False, 0)
        box.pack_start(account, False, False, 0)
        page.pack_start(scrolled(box), True, True, 0)
        return page

    def _setting_row(self, title_key: str, hint_key: str, control: Gtk.Widget) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        add_class(row, "setting-row")
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        texts.pack_start(label(self.t(title_key), "setting-title"), False, False, 0)
        texts.pack_start(label(self.t(hint_key), "muted", wrap=True), False, False, 0)
        row.pack_start(texts, True, True, 0)
        control.set_valign(Gtk.Align.CENTER)
        row.pack_end(control, False, False, 0)
        return row

    def _settings_language_changed(self, combo: Gtk.ComboBoxText) -> None:
        code = combo.get_active_id()
        if not code or code == self.language:
            return
        self.profile.language = code
        self.language = code
        self.storage.save_profile(self.profile)
        self.current_page = "settings"
        GLib.idle_add(lambda: (self.show_chat(restart_network=False), False)[1])

    def _settings_appearance(self, combo: Gtk.ComboBoxText) -> None:
        self.storage.save_settings(appearance=combo.get_active_id() or "system")
        self._load_css()

    def _settings_large_text(self, switch: Gtk.Switch, _param) -> None:
        self.storage.save_settings(large_text=switch.get_active())
        self._load_css()

    # Toasts --------------------------------------------------------------
    def _show_toast(self, text: str) -> None:
        toast = getattr(self, "toast_revealer", None)
        if toast is None:
            return
        self.toast_label.set_text(text)
        toast.set_reveal_child(True)
        if getattr(self, "_toast_timer", 0):
            GLib.source_remove(self._toast_timer)

        def hide() -> bool:
            toast.set_reveal_child(False)
            self._toast_timer = 0
            return False

        self._toast_timer = GLib.timeout_add_seconds(4, hide)

