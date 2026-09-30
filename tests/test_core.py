import base64
import json
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

from eduka_konekta.devices import DeviceManager, detect_video_devices
from eduka_konekta.i18n import CATALOGS, EN, LANGUAGES, tr
from eduka_konekta.models import (
    Identity,
    Profile,
    rooms_for,
    validate_attachment,
    validate_ip,
    validate_profile,
    validate_message_action_payload,
    validate_status_payload,
    verify_signature,
)
from eduka_konekta.network import P2PNetwork, decode_packet, encode_frame, local_ipv4_info
from eduka_konekta.storage import Storage


def profile(name="Maria da Silva", role="student"):
    return Profile(
        name, "Escola Central Dili", role, 16, "10A", "Room 2", "tet",
        subject="Mathematics" if role == "teacher" else "",
        photo_b64=base64.b64encode(b"test-profile-photo").decode("ascii"),
        photo_mime="image/jpeg",
    )


class ProfileTests(unittest.TestCase):
    def test_requires_full_name(self):
        item = profile("Fantasma")
        self.assertIn("name_error", validate_profile(item))
        self.assertEqual([], validate_profile(profile()))

    def test_room_policy(self):
        student_rooms = rooms_for(profile())
        teacher_rooms = rooms_for(profile(role="teacher"))
        self.assertEqual(4, len(student_rooms))
        self.assertEqual(5, len(teacher_rooms))
        self.assertTrue(teacher_rooms[-1][0].startswith("teachers:"))

    def test_ip_validation(self):
        self.assertEqual("192.168.1.10", validate_ip(" 192.168.1.10 "))
        with self.assertRaises(ValueError):
            validate_ip("school.example")

    def test_teacher_requires_subject_and_photo_can_be_skipped(self):
        missing_subject = profile(role="teacher")
        missing_subject.subject = ""
        self.assertIn("subject_error", validate_profile(missing_subject))
        missing_photo = profile()
        missing_photo.photo_b64 = ""
        self.assertNotIn("photo_required", validate_profile(missing_photo))
        self.assertEqual([], validate_profile(missing_photo))


class IdentityTests(unittest.TestCase):
    def test_identity_persists_and_signatures_detect_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "identity.json"
            first = Identity.load_or_create(path)
            second = Identity.load_or_create(path)
            self.assertEqual(first.user_id, second.user_id)
            payload = {"type": "chat", "text": "Bondia"}
            signature = first.sign(payload)
            self.assertTrue(verify_signature(payload, signature, first.public_key, first.user_id))
            self.assertFalse(verify_signature({**payload, "text": "changed"}, signature, first.public_key, first.user_id))

    def test_frame_round_trip(self):
        packet = {"payload": {"hello": "mundu"}, "signature": "x", "public_key": "y", "user_id": "z"}
        frame = encode_frame(packet)
        self.assertEqual(packet, decode_packet(frame[4:]))


class StorageTests(unittest.TestCase):
    def test_history_is_deduplicated(self):
        with tempfile.TemporaryDirectory() as folder:
            storage = Storage(Path(folder))
            message = {
                "msg_id": "m1", "room_id": "all-schools", "timestamp": 1,
                "sender_id": "EK-123", "profile": profile().public(), "kind": "text", "text": "Oi",
            }
            self.assertTrue(storage.add_message(message))
            self.assertFalse(storage.add_message(message))
            self.assertEqual("Oi", storage.messages("all-schools")[0]["text"])
            session_dir = storage.session_dir
            storage.close()
            self.assertFalse(session_dir.exists(), "ephemeral session directory was not erased")

    def test_profile_persists_until_explicit_logout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = Storage(root)
            first.save_profile(profile())
            self.assertIsNotNone(first.load_profile())
            identity_path = first.identity_path
            Identity.load_or_create(identity_path)
            first.close()
            self.assertTrue(identity_path.exists())
            second = Storage(root)
            self.assertEqual("Maria da Silva", second.load_profile().full_name)
            second.logout()
            second.close()
            third = Storage(root)
            self.assertIsNone(third.load_profile())
            third.close()

    def test_image_size_and_type(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / "small.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n")
            allowed, error, mime = validate_attachment(image, "image")
            self.assertTrue(allowed)
            self.assertIsNone(error)
            self.assertEqual("image/png", mime)

    def test_document_transfer_and_thirty_minute_message_controls(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            document = root / "lesson.odt"
            document.write_bytes(b"school document")
            allowed, error, _mime = validate_attachment(document, "document")
            self.assertTrue(allowed)
            self.assertIsNone(error)

            storage = Storage(root / "profile")
            now = time.time()
            message = {
                "msg_id": "editable", "room_id": "all-schools", "timestamp": now,
                "sender_id": "EK-OWNER", "profile": profile().public(), "kind": "text", "text": "Before",
            }
            storage.add_message(message)
            self.assertTrue(storage.edit_message("editable", "EK-OWNER", "After", now + 60))
            self.assertEqual("After", storage.message("editable")["text"])
            self.assertFalse(storage.edit_message("editable", "EK-OWNER", "Late", now + 1801))
            self.assertTrue(storage.delete_message("editable", "EK-OWNER", now + 120))
            self.assertIsNone(storage.message("editable"))
            storage.close()


class StatusAndDeviceTests(unittest.TestCase):
    def test_only_text_emotion_image_and_clear_status_are_supported(self):
        self.assertTrue(validate_status_payload({"status_kind": "text", "text": "Studying"}))
        self.assertTrue(validate_status_payload({"status_kind": "emotion", "emotion": "😊", "text": "Ready"}))
        self.assertTrue(validate_status_payload({
            "status_kind": "image", "text": "", "file_name": "class.png",
            "mime": "image/png", "file_data": base64.b64encode(b"image").decode("ascii"),
        }))
        self.assertTrue(validate_status_payload({"status_kind": "none", "text": ""}))
        self.assertFalse(validate_status_payload({"status_kind": "music", "file_name": "song.ogg"}))
        self.assertFalse(validate_status_payload({"status_kind": "video", "file_name": "clip.mp4"}))

    def test_message_action_payload_validation(self):
        base = {"event_id": "event-1", "msg_id": "message-1", "room_id": "all-schools"}
        self.assertTrue(validate_message_action_payload({**base, "action": "edit", "text": "Updated"}))
        self.assertTrue(validate_message_action_payload({**base, "action": "delete"}))
        self.assertTrue(validate_message_action_payload({
            **base, "action": "replace", "kind": "document", "file_name": "report.pdf",
            "mime": "application/pdf", "file_data": base64.b64encode(b"pdf").decode("ascii"),
        }))
        self.assertFalse(validate_message_action_payload({**base, "action": "edit", "text": ""}))

    def test_webcam_detection_and_unique_ephemeral_capture_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "video0").touch()
            (root / "video2").touch()
            devices = detect_video_devices(root)
            self.assertEqual(["video0", "video2"], [Path(item.source).name for item in devices])
            manager = DeviceManager(root / "captures")
            first = manager.capture_path("voice", ".ogg")
            first.touch()
            self.assertEqual("voice-1.ogg", manager.capture_path("voice", ".ogg").name)

    def test_all_media_choosers_use_standard_gtk_dialog(self):
        source = (Path(__file__).parents[1] / "src/eduka_konekta/ui.py").read_text(encoding="utf-8")
        self.assertNotIn("Gtk.FileChooserNative", source)
        self.assertIn("Gtk.FileChooserDialog", source)
        self.assertIn("_choose_status_image", source)
        self.assertIn("_record_media", source)
        self.assertIn("students_online", source)
        self.assertIn("teachers_online", source)
        self.assertIn("_refresh_online", source)
        self.assertIn("_confirm_logout", source)


class TranslationTests(unittest.TestCase):
    def test_all_declared_languages_have_core_strings(self):
        for language in LANGUAGES:
            self.assertIn(language, CATALOGS)
            for key in ("sign_in", "all_schools", "send", "about", "network_warning", "logout", "students_online", "upload_document"):
                self.assertNotEqual(key, tr(language, key))


class NetworkTests(unittest.TestCase):
    def test_two_peers_exchange_signed_group_message(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            identity_a = Identity.load_or_create(root / "a.json")
            identity_b = Identity.load_or_create(root / "b.json")
            received = []
            received_event = threading.Event()
            peers_a = threading.Event()
            peers_b = threading.Event()

            def receive(message):
                received.append(message)
                received_event.set()

            network_a = P2PNetwork(identity_a, profile("Ana Pereira"), receive, lambda peers: peers_a.set() if peers else None, tcp_port=0, enable_discovery=False)
            network_b = P2PNetwork(identity_b, profile("João Soares", "teacher"), receive, lambda peers: peers_b.set() if peers else None, tcp_port=0, enable_discovery=False)
            try:
                network_a.start()
                network_b.start()
                network_b.connect_ip("127.0.0.1", network_a.tcp_port)
                self.assertTrue(peers_a.wait(3), "peer A did not see B")
                self.assertTrue(peers_b.wait(3), "peer B did not see A")
                message_id = uuid.uuid4().hex
                network_b.send_chat({
                    "msg_id": message_id, "room_id": "all-schools", "timestamp": time.time(),
                    "profile": profile("João Soares", "teacher").public(), "kind": "text", "text": "Bom dia",
                })
                self.assertTrue(received_event.wait(3), "signed message was not delivered")
                self.assertEqual(message_id, received[-1]["msg_id"])
                self.assertTrue(received[-1]["verified"])
                self.assertEqual(identity_b.user_id, received[-1]["sender_id"])
            finally:
                network_a.stop()
                network_b.stop()

    def test_message_relays_across_three_peer_mesh(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            identities = [Identity.load_or_create(root / f"{name}.json") for name in "abc"]
            arrivals = [threading.Event(), threading.Event(), threading.Event()]
            received = [[], [], []]
            profiles = [profile("Abel Pereira"), profile("Berta Soares"), profile("Carlos da Costa")]
            networks = []
            for index in range(3):
                networks.append(P2PNetwork(
                    identities[index], profiles[index],
                    lambda message, i=index: (received[i].append(message), arrivals[i].set()),
                    lambda _peers: None, tcp_port=0, enable_discovery=False,
                ))
            try:
                for network in networks:
                    network.start()
                networks[1].connect_ip("127.0.0.1", networks[0].tcp_port)
                deadline = time.time() + 3
                while time.time() < deadline and not networks[0].peers():
                    time.sleep(0.02)
                networks[2].connect_ip("127.0.0.1", networks[1].tcp_port)
                deadline = time.time() + 3
                while time.time() < deadline and len(networks[1].peers()) < 2:
                    time.sleep(0.02)
                message_id = uuid.uuid4().hex
                networks[0].send_chat({
                    "msg_id": message_id, "room_id": "all-schools", "timestamp": time.time(),
                    "profile": profiles[0].public(), "kind": "text", "text": "Mesh test",
                })
                self.assertTrue(arrivals[2].wait(3), "third peer did not receive relayed message")
                self.assertEqual(message_id, received[2][-1]["msg_id"])
                self.assertEqual(identities[0].user_id, received[2][-1]["sender_id"])
            finally:
                for network in networks:
                    network.stop()

    def test_direct_message_reaches_only_selected_user(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            identities = [Identity.load_or_create(root / f"direct-{i}.json") for i in range(3)]
            arrivals = [[], [], []]
            networks = [
                P2PNetwork(
                    identities[i], profile(["Ana Pereira", "Beto Soares", "Carla Costa"][i]),
                    lambda message, index=i: arrivals[index].append(message), lambda _peers: None,
                    tcp_port=0, enable_discovery=False,
                ) for i in range(3)
            ]
            try:
                for network in networks:
                    network.start()
                networks[0].connect_ip("127.0.0.1", networks[1].tcp_port)
                networks[2].connect_ip("127.0.0.1", networks[0].tcp_port)
                deadline = time.time() + 3
                while time.time() < deadline and len(networks[0].peers()) < 2:
                    time.sleep(0.02)
                message_id = uuid.uuid4().hex
                networks[0].send_chat({
                    "msg_id": message_id, "room_id": "direct:test", "timestamp": time.time(),
                    "profile": profile("Ana Pereira").public(include_photo=False), "kind": "text", "text": "Private grade",
                }, [identities[1].user_id])
                deadline = time.time() + 2
                while time.time() < deadline and not arrivals[1]:
                    time.sleep(0.02)
                self.assertEqual(message_id, arrivals[1][-1]["msg_id"])
                self.assertEqual([], arrivals[2], "non-target peer received direct message")
            finally:
                for network in networks:
                    network.stop()

    def test_status_is_signed_and_delivered(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            identity_a = Identity.load_or_create(root / "status-a.json")
            identity_b = Identity.load_or_create(root / "status-b.json")
            received = []
            event = threading.Event()
            network_a = P2PNetwork(identity_a, profile("Status Sender"), lambda _m: None, lambda _p: None, tcp_port=0, enable_discovery=False)
            network_b = P2PNetwork(
                identity_b, profile("Status Receiver"), lambda _m: None, lambda _p: None,
                lambda status: (received.append(status), event.set()), tcp_port=0, enable_discovery=False,
            )
            try:
                network_a.start(); network_b.start()
                network_b.connect_ip("127.0.0.1", network_a.tcp_port)
                deadline = time.time() + 3
                while time.time() < deadline and not network_a.peers():
                    time.sleep(0.02)
                network_a.send_status({
                    "status_id": uuid.uuid4().hex, "status_kind": "emotion", "emotion": "😊", "text": "Learning",
                    "timestamp": time.time(), "profile": profile("Status Sender").public(include_photo=False),
                })
                self.assertTrue(event.wait(3))
                self.assertEqual(identity_a.user_id, received[-1]["sender_id"])
                self.assertTrue(received[-1]["verified"])
            finally:
                network_a.stop(); network_b.stop()

    def test_signed_message_edit_action_is_delivered(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            identity_a = Identity.load_or_create(root / "action-a.json")
            identity_b = Identity.load_or_create(root / "action-b.json")
            actions = []
            event = threading.Event()
            network_a = P2PNetwork(identity_a, profile("Action Sender"), lambda _m: None, lambda _p: None, tcp_port=0, enable_discovery=False)
            network_b = P2PNetwork(
                identity_b, profile("Action Receiver"), lambda _m: None, lambda _p: None,
                on_message_action=lambda action: (actions.append(action), event.set()),
                tcp_port=0, enable_discovery=False,
            )
            try:
                network_a.start(); network_b.start()
                network_b.connect_ip("127.0.0.1", network_a.tcp_port)
                deadline = time.time() + 3
                while time.time() < deadline and not network_a.peers():
                    time.sleep(0.02)
                network_a.send_message_action({
                    "event_id": uuid.uuid4().hex, "action": "edit", "msg_id": "original-message",
                    "room_id": "all-schools", "text": "Corrected text", "timestamp": time.time(),
                    "profile": profile("Action Sender").public(include_photo=False),
                })
                self.assertTrue(event.wait(3))
                self.assertEqual("Corrected text", actions[-1]["text"])
                self.assertEqual(identity_a.user_id, actions[-1]["sender_id"])
            finally:
                network_a.stop(); network_b.stop()

    def test_refresh_candidates_include_wifi_subnet_and_known_peers(self):
        with tempfile.TemporaryDirectory() as folder:
            identity = Identity.load_or_create(Path(folder) / "refresh.json")
            network = P2PNetwork(
                identity, profile("Refresh User"), lambda _m: None, lambda _p: None,
                seed_ips=["10.20.30.77"], tcp_port=0, enable_discovery=False,
            )
            network.local_ips = [{
                "address": "192.168.50.2", "broadcast": "192.168.50.3",
                "network": "192.168.50.0/30", "prefix": "30", "interface": "wlan0",
            }]
            candidates = network._candidate_ips()
            self.assertIn("10.20.30.77", candidates)
            self.assertIn("192.168.50.1", candidates)
            self.assertNotIn("192.168.50.2", candidates)

    def test_teacher_group_definition_reaches_selected_member(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            teacher_id = Identity.load_or_create(root / "teacher.json")
            student_id = Identity.load_or_create(root / "student.json")
            groups = []
            event = threading.Event()
            teacher = P2PNetwork(teacher_id, profile("Teacher Pereira", "teacher"), lambda _m: None, lambda _p: None, tcp_port=0, enable_discovery=False)
            student = P2PNetwork(
                student_id, profile("Student Soares"), lambda _m: None, lambda _p: None,
                on_group=lambda group: (groups.append(group), event.set()), tcp_port=0, enable_discovery=False,
            )
            try:
                teacher.start(); student.start(); student.connect_ip("127.0.0.1", teacher.tcp_port)
                deadline = time.time() + 3
                while time.time() < deadline and not teacher.peers():
                    time.sleep(0.02)
                definition = {
                    "group_id": "group:test", "name": "Mathematics 10A", "owner_id": teacher_id.user_id,
                    "timestamp": time.time(),
                }
                teacher.send_group_definition(definition, [teacher_id.user_id, student_id.user_id])
                self.assertTrue(event.wait(3))
                self.assertEqual("Mathematics 10A", groups[-1]["name"])
                self.assertIn(student_id.user_id, groups[-1]["members"])
            finally:
                teacher.stop(); student.stop()

    def test_different_school_profile_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            identity_a = Identity.load_or_create(root / "same-a.json")
            identity_b = Identity.load_or_create(root / "other-b.json")
            other = profile("Other School User")
            other.school = "Another School"
            network_a = P2PNetwork(identity_a, profile("Same School User"), lambda _m: None, lambda _p: None, tcp_port=0, enable_discovery=False)
            network_b = P2PNetwork(identity_b, other, lambda _m: None, lambda _p: None, tcp_port=0, enable_discovery=False)
            try:
                network_a.start(); network_b.start(); network_b.connect_ip("127.0.0.1", network_a.tcp_port)
                time.sleep(0.4)
                self.assertEqual([], network_a.peers())
                self.assertEqual([], network_b.peers())
            finally:
                network_a.stop(); network_b.stop()


if __name__ == "__main__":
    unittest.main()
