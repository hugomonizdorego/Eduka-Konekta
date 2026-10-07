import base64
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
from eduka_konekta.moderation import RateLimiter, filter_text, parse_word_list
from eduka_konekta.network import P2PNetwork, decode_packet, encode_frame, subnet_hosts
from eduka_konekta.school import SchoolManager, grade_answers, validate_school_payload
from eduka_konekta.storage import Storage


def wait_until(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


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
        package = Path(__file__).parents[1] / "src/eduka_konekta"
        source = (package / "ui.py").read_text(encoding="utf-8") + (package / "ui_school.py").read_text(encoding="utf-8")
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

    def test_every_interface_key_is_translated_in_every_language(self):
        import re
        package = Path(__file__).parents[1] / "src/eduka_konekta"
        source = "".join((package / name).read_text(encoding="utf-8") for name in ("ui.py", "ui_school.py"))
        keys = set(re.findall(r'self\.t\("([a-z0-9_]+)"\)', source))
        keys |= set(re.findall(r"self\.t\('([a-z0-9_]+)'\)", source))
        self.assertGreater(len(keys), 150)
        for language, catalog in CATALOGS.items():
            missing = sorted(key for key in keys if key not in catalog)
            self.assertEqual([], missing, f"{language} is missing translations")
            self.assertEqual(set(EN), set(catalog), f"{language} catalog keys differ from English")

    def test_placeholders_match_between_languages(self):
        import re
        for key, english in EN.items():
            expected = set(re.findall(r"{(\w+)}", english))
            for language, catalog in CATALOGS.items():
                self.assertEqual(expected, set(re.findall(r"{(\w+)}", catalog[key])), f"{language}:{key}")


class AssetTests(unittest.TestCase):
    def test_logo_and_theme_files_are_valid(self):
        import xml.etree.ElementTree as ET
        assets = Path(__file__).parents[1] / "assets"
        for name in ("eduka-konekta.svg", "eduka-konekta-logo.svg", "eduka-konekta-logo-light.svg"):
            root = ET.parse(assets / name).getroot()
            self.assertTrue(root.tag.endswith("svg"), name)
            self.assertNotIn("Chatalk", (assets / name).read_text(encoding="utf-8"))
        for mode in ("system", "light", "dark"):
            palette = (assets / f"palette-{mode}.css").read_text(encoding="utf-8")
            for colour in ("ek_bg", "ek_surface", "ek_fg", "ek_muted", "ek_border", "ek_accent", "ek_accent_text", "ek_rail"):
                self.assertIn(f"@define-color {colour} ", palette, f"{mode} lacks {colour}")
        for size in (16, 32, 48, 128, 256):
            self.assertTrue((assets / "icons" / f"eduka-konekta-{size}.png").is_file())


class ModerationTests(unittest.TestCase):
    def test_word_filter_masks_whole_words_only(self):
        self.assertEqual("dasar b******", filter_text("dasar bangsat"))
        self.assertEqual("jangan B****** ya", filter_text("jangan BANGSAT ya"))
        self.assertEqual("pelajaran klasik", filter_text("pelajaran klasik"))
        self.assertEqual("ini s***** kelas", filter_text("ini sampah kelas", ["sampah"]))
        self.assertEqual(["kasar", "jelek"], parse_word_list("Kasar, jelek; kasar"))

    def test_rate_limiter_blocks_spam(self):
        now = [0.0]
        limiter = RateLimiter(limit=3, window=10, clock=lambda: now[0])
        self.assertTrue(all(limiter.allow() for _ in range(3)))
        self.assertFalse(limiter.allow())
        now[0] = 11
        self.assertTrue(limiter.allow())


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

    def test_wifi_client_isolation_is_bridged_by_a_relay_peer(self):
        """A and B cannot reach each other (AP isolation) but both reach H (wired)."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ids = [Identity.load_or_create(root / f"relay-{name}.json") for name in "ahb"]
            names = ["Ana Pereira", "Hugo Moniz", "Beto Soares"]
            inbox = [[], [], []]
            networks = []
            for index in range(3):
                network = P2PNetwork(
                    ids[index], profile(names[index], "teacher" if index == 1 else "student"),
                    lambda message, i=index: inbox[i].append(message), lambda _peers: None,
                    tcp_port=0, enable_discovery=False,
                )
                network.local_ips = []  # no gossiped addresses: A and B stay isolated
                networks.append(network)
            a, hub, b = networks
            try:
                for network in networks:
                    network.start()
                a.connect_ip("127.0.0.1", hub.tcp_port)
                b.connect_ip("127.0.0.1", hub.tcp_port)
                self.assertTrue(wait_until(lambda: any(peer.user_id == ids[2].user_id for peer in a.peers())), "A never learned about B through the relay")
                self.assertTrue(wait_until(lambda: any(peer.user_id == ids[0].user_id for peer in b.peers())), "B never learned about A through the relay")
                seen_b = next(peer for peer in a.peers() if peer.user_id == ids[2].user_id)
                self.assertFalse(seen_b.direct)
                self.assertEqual(ids[1].user_id, seen_b.via)

                private_id = uuid.uuid4().hex
                room = "direct:" + ":".join(sorted((ids[0].user_id, ids[2].user_id)))
                a.send_chat({
                    "msg_id": private_id, "room_id": room, "timestamp": time.time(),
                    "profile": profile(names[0]).public(include_photo=False), "kind": "text", "text": "Via relay",
                }, [ids[2].user_id])
                self.assertTrue(wait_until(lambda: any(m["msg_id"] == private_id for m in inbox[2])), "private message did not cross the relay")
                self.assertEqual([], [m for m in inbox[1] if m["msg_id"] == private_id], "relay must not deliver a message addressed to someone else")

                public_id = uuid.uuid4().hex
                b.send_chat({
                    "msg_id": public_id, "room_id": "all-schools", "timestamp": time.time(),
                    "profile": profile(names[2]).public(include_photo=False), "kind": "text", "text": "Hello everyone",
                })
                self.assertTrue(wait_until(lambda: any(m["msg_id"] == public_id for m in inbox[0])), "room message did not cross the relay")
                self.assertTrue(wait_until(lambda: any(m["msg_id"] == public_id for m in inbox[1])))
                time.sleep(0.3)
                self.assertEqual(1, len([m for m in inbox[0] if m["msg_id"] == public_id]), "duplicate delivery")

                b.stop()
                self.assertTrue(wait_until(lambda: all(peer.user_id != ids[2].user_id for peer in a.peers()), 6), "relayed peer did not expire after leaving")
            finally:
                for network in networks:
                    network.stop()

    def test_full_mesh_does_not_duplicate_room_messages(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ids = [Identity.load_or_create(root / f"mesh-{i}.json") for i in range(3)]
            names = ["Ana Pereira", "Beto Soares", "Carla Costa"]
            inbox = [[], [], []]
            networks = [
                P2PNetwork(ids[i], profile(names[i]), lambda m, i=i: inbox[i].append(m), lambda _p: None, tcp_port=0, enable_discovery=False)
                for i in range(3)
            ]
            try:
                for network in networks:
                    network.local_ips = []
                    network.start()
                networks[0].connect_ip("127.0.0.1", networks[1].tcp_port)
                networks[0].connect_ip("127.0.0.1", networks[2].tcp_port)
                networks[1].connect_ip("127.0.0.1", networks[2].tcp_port)
                self.assertTrue(wait_until(lambda: all(len([p for p in n.peers() if p.direct]) == 2 for n in networks)))
                time.sleep(1.5)  # let presence (direct-peer lists) propagate
                message_id = uuid.uuid4().hex
                networks[0].send_chat({
                    "msg_id": message_id, "room_id": "all-schools", "timestamp": time.time(),
                    "profile": profile(names[0]).public(include_photo=False), "kind": "text", "text": "Once",
                })
                self.assertTrue(wait_until(lambda: inbox[1] and inbox[2]))
                time.sleep(0.3)
                self.assertEqual(1, len(inbox[1]))
                self.assertEqual(1, len(inbox[2]))
            finally:
                for network in networks:
                    network.stop()

    def test_subnet_scan_covers_large_wifi_networks(self):
        hosts = subnet_hosts("10.5.6.20", "10.5.4.0/22", 1024)
        self.assertIn("10.5.6.1", hosts)
        self.assertIn("10.5.4.9", hosts)
        self.assertIn("10.5.7.200", hosts)
        self.assertNotIn("10.5.6.20", hosts)
        self.assertEqual("10.5.6.1", hosts[0], "own /24 must be scanned first")
        big = subnet_hosts("172.16.9.9", "172.16.0.0/16", 600)
        self.assertEqual(600, len(big))
        self.assertTrue(all(ipaddress_in(host, "172.16.0.0/16") for host in big))


def ipaddress_in(host, network):
    import ipaddress
    return ipaddress.ip_address(host) in ipaddress.ip_network(network)


class SchoolTests(unittest.TestCase):
    def test_grading_and_payload_validation(self):
        questions = [
            {"qid": "q1", "type": "choice", "options": ["a", "b"], "points": 2},
            {"qid": "q2", "type": "choice", "options": ["a", "b"], "points": 1},
            {"qid": "q3", "type": "essay"},
        ]
        result = grade_answers(questions, {"q1": 1, "q2": 0}, {"q1": 1, "q2": 1, "q3": "text"})
        self.assertEqual((1, 2, 2.0, 3.0, 1), (result["correct"], result["total"], result["points"], result["max_points"], result["essays"]))
        self.assertFalse(validate_school_payload({"kind": "exam_submit", "exam_id": "x", "submission_id": "s", "answers": "bad"}))
        self.assertFalse(validate_school_payload({"kind": "unknown"}))
        self.assertTrue(validate_school_payload({"kind": "room_lock", "room_id": "school:x", "locked": True}))

    def test_exam_attendance_and_rules_flow_over_the_network(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            teacher_id = Identity.load_or_create(root / "exam-teacher.json")
            student_id = Identity.load_or_create(root / "exam-student.json")
            teacher_profile = profile("Rita Belo", "teacher")
            student_profile = profile("Maria da Silva")
            holders = {}

            def make(identity, prof, key):
                network = P2PNetwork(
                    identity, prof, lambda _m: None,
                    lambda peers, k=key: holders[k].set_peers(peers),
                    tcp_port=0, enable_discovery=False,
                    on_school=lambda event, k=key: holders[k].handle(event),
                )
                network.local_ips = []
                holders[key] = SchoolManager(root / key, identity.user_id, lambda p=prof: p, network.send_school)
                return network

            teacher_net = make(teacher_id, teacher_profile, "teacher")
            student_net = make(student_id, student_profile, "student")
            teacher, student = holders["teacher"], holders["student"]
            questions_file = root / "soal.pdf"
            questions_file.write_bytes(b"%PDF-1.4 soal ujian")
            answer_file = root / "jawaban.odt"
            answer_file.write_bytes(b"jawaban siswa")
            try:
                teacher_net.start(); student_net.start()
                # The exam is created while the student is offline (store-and-forward).
                exam = teacher.create_exam(
                    "exam", "Ulangan Matematika", "Matematika", "Kerjakan sendiri.",
                    {"mode": "class", "school_class": "10a"}, 30,
                    [
                        {"qid": "q1", "type": "choice", "text": "2+2?", "options": ["3", "4", "5"]},
                        {"qid": "q2", "type": "essay", "text": "Jelaskan.", "points": 5},
                    ],
                    {"q1": 1}, lock_chat=True, question_file=questions_file,
                )
                exam_id = exam["exam_id"]
                student_net.connect_ip("127.0.0.1", teacher_net.tcp_port)
                self.assertTrue(wait_until(lambda: exam_id in student.exams), "offline student did not receive the exam")
                received = student.exams[exam_id]
                self.assertNotIn("answer_key", received, "answer key leaked to the student")
                self.assertEqual("student", received["role"])
                self.assertIsNotNone(student.chat_locked(), "exam mode did not lock student chat")
                self.assertTrue(wait_until(lambda: student_id.user_id in teacher.exams[exam_id]["delivered_to"]))

                self.assertTrue(student.request_exam_file(exam_id))
                self.assertTrue(wait_until(lambda: Path(student.exams[exam_id]["file"].get("path", "/nonexistent")).exists()))
                self.assertEqual(b"%PDF-1.4 soal ujian", Path(student.exams[exam_id]["file"]["path"]).read_bytes())

                student.submit_exam(exam_id, {"q1": 1, "q2": "Karena dua tambah dua."}, answer_file)
                self.assertTrue(wait_until(lambda: student_id.user_id in teacher.submissions.get(exam_id, {})))
                row = teacher.submissions[exam_id][student_id.user_id]
                self.assertEqual((1, 1), (row["auto"]["correct"], row["auto"]["total"]))
                self.assertFalse(row["late"])
                self.assertEqual(b"jawaban siswa", Path(row["file"]["path"]).read_bytes())
                self.assertTrue(wait_until(lambda: student.exams[exam_id]["submission"]["acked"]), "submission receipt not delivered")

                teacher.return_result(exam_id, student_id.user_id, "95", "Bagus sekali")
                self.assertTrue(wait_until(lambda: student.exams[exam_id].get("result", {}).get("score") == "95"))
                csv_path = teacher.export_results_csv(exam_id, root / "hasil.csv")
                self.assertIn("Maria da Silva", csv_path.read_text(encoding="utf-8-sig"))
                self.assertEqual(1, teacher.copy_answer_files(exam_id, root / "answers"))

                teacher.close_exam(exam_id)
                self.assertTrue(wait_until(lambda: student.exams[exam_id].get("closed")))
                self.assertIsNone(student.chat_locked())
                with self.assertRaises(PermissionError):
                    student.submit_exam(exam_id, {"q1": 0})

                session = teacher.open_attendance("Absensi pagi", "10A", 5)
                self.assertTrue(wait_until(lambda: session["session_id"] in student.attendance))
                self.assertTrue(student.mark_present(session["session_id"]))
                self.assertTrue(wait_until(lambda: student_id.user_id in teacher.attendance[session["session_id"]]["present"]))
                self.assertTrue(wait_until(lambda: student.attendance[session["session_id"]].get("acked")))

                teacher.close_attendance(session["session_id"])
                self.assertTrue(wait_until(lambda: student.attendance[session["session_id"]].get("closed")), "closing attendance did not reach the student")
                self.assertFalse(student.mark_present(session["session_id"]))

                teacher.publish_rules("Dilarang menyontek.")
                self.assertTrue(wait_until(lambda: student.rules.get("text") == "Dilarang menyontek."))
                teacher.set_room_lock("school:escola-central-dili", True)
                self.assertTrue(wait_until(lambda: student.room_locked("school:escola-central-dili")))

                # Records survive a restart of the application.
                reloaded = SchoolManager(root / "teacher", teacher_id.user_id, lambda: teacher_profile, lambda *_: None)
                self.assertEqual("95", reloaded.submissions[exam_id][student_id.user_id]["score"])
            finally:
                teacher_net.stop(); student_net.stop()

    def test_malformed_events_are_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = SchoolManager(Path(folder), "EK-ME", lambda: profile("Maria da Silva"), lambda *_: None)
            teacher = profile("Rita Belo", "teacher").public(include_photo=False)
            self.assertIsNone(manager.handle({
                "kind": "exam_publish", "sender_id": "EK-T", "profile": teacher,
                "exam": {"exam_id": "e1", "kind": "exam", "title": "Broken", "teacher_id": "EK-T",
                         "questions": [], "remaining_seconds": "not-a-number"},
            }))

    def test_students_cannot_publish_exams_or_rules(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = SchoolManager(Path(folder), "EK-ME", lambda: profile("Maria da Silva"), lambda *_: None)
            fake_teacher = profile("Beto Soares").public(include_photo=False)  # role student
            self.assertIsNone(manager.handle({
                "kind": "exam_publish", "sender_id": "EK-X", "profile": fake_teacher,
                "exam": {"exam_id": "e1", "kind": "exam", "title": "Fake", "teacher_id": "EK-X", "questions": []},
            }))
            self.assertIsNone(manager.handle({"kind": "rules", "rules_id": "r", "text": "x", "sender_id": "EK-X", "profile": fake_teacher}))
            self.assertEqual({}, manager.exams)
            with self.assertRaises(PermissionError):
                manager.create_exam("exam", "t", "s", "", {"mode": "all"}, 0, [], {})


if __name__ == "__main__":
    unittest.main()
