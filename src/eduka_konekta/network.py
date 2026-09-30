"""Signed peer-to-peer TCP mesh with multicast LAN discovery."""

from __future__ import annotations

import json
import ipaddress
import logging
import socket
import struct
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from . import DISCOVERY_PORT, MULTICAST_GROUP, PROTOCOL_VERSION, TCP_PORT
from .models import (
    Identity,
    Profile,
    slug,
    validate_message_action_payload,
    validate_profile,
    validate_status_payload,
    verify_signature,
)

LOG = logging.getLogger(__name__)
MAX_FRAME = 36 * 1024 * 1024


def local_ipv4_info() -> list[dict[str, str]]:
    """Return active IPv4 addresses and broadcast targets without a server."""
    found: dict[str, dict[str, str]] = {}
    try:
        result = subprocess.run(
            ["ip", "-j", "-4", "addr", "show", "up"], capture_output=True,
            text=True, timeout=3, check=True,
        )
        for interface in json.loads(result.stdout):
            interface_name = str(interface.get("ifname", ""))
            if interface_name.startswith(("docker", "veth", "virbr", "podman", "br-")):
                continue
            for info in interface.get("addr_info", []):
                address = str(info.get("local", ""))
                if not address or address.startswith("127."):
                    continue
                prefix = int(info.get("prefixlen", 24))
                broadcast = info.get("broadcast")
                if not broadcast:
                    broadcast = str(ipaddress.ip_interface(f"{address}/{prefix}").network.broadcast_address)
                network = ipaddress.ip_interface(f"{address}/{prefix}").network
                found[address] = {
                    "address": address,
                    "broadcast": str(broadcast),
                    "network": str(network),
                    "prefix": str(prefix),
                    "interface": interface_name,
                }
    except (OSError, ValueError, TypeError, subprocess.SubprocessError, json.JSONDecodeError):
        pass
    if not found:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(("192.0.2.1", 9))
                address = probe.getsockname()[0]
            if not address.startswith("127."):
                interface = ipaddress.ip_interface(f"{address}/24")
                found[address] = {
                    "address": address,
                    "broadcast": str(interface.network.broadcast_address),
                    "network": str(interface.network),
                    "prefix": "24",
                    "interface": "",
                }
        except OSError:
            pass
    return list(found.values())


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        part = sock.recv(size - len(chunks))
        if not part:
            raise ConnectionError("peer closed connection")
        chunks.extend(part)
    return bytes(chunks)


def encode_frame(packet: dict[str, Any]) -> bytes:
    body = json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_FRAME:
        raise ValueError("frame too large")
    return struct.pack("!I", len(body)) + body


def decode_packet(raw: bytes) -> dict[str, Any]:
    packet = json.loads(raw.decode("utf-8"))
    if not isinstance(packet, dict) or not isinstance(packet.get("payload"), dict):
        raise ValueError("invalid packet")
    return packet


@dataclass
class PeerInfo:
    user_id: str
    profile: dict[str, Any]
    ip: str
    public_key: str


class PeerConnection:
    def __init__(self, network: "P2PNetwork", sock: socket.socket, address: tuple[str, int], outgoing: bool):
        self.network = network
        self.sock = sock
        self.address = address
        self.outgoing = outgoing
        self.user_id: str | None = None
        self._send_lock = threading.Lock()
        self._closed = False

    def start(self) -> None:
        self.sock.settimeout(None)
        threading.Thread(target=self._reader, name=f"eduka-peer-{self.address[0]}", daemon=True).start()
        self.send(self.network.make_packet(self.network.hello_payload()))

    def send(self, packet: dict[str, Any]) -> None:
        if self._closed:
            return
        frame = encode_frame(packet)
        with self._send_lock:
            self.sock.sendall(frame)

    def _reader(self) -> None:
        try:
            while not self.network.stopped.is_set():
                size = struct.unpack("!I", _recv_exact(self.sock, 4))[0]
                if size <= 0 or size > MAX_FRAME:
                    raise ValueError("invalid frame size")
                packet = decode_packet(_recv_exact(self.sock, size))
                self.network.handle_packet(self, packet)
        except (OSError, ConnectionError, ValueError, json.JSONDecodeError) as error:
            LOG.debug("Peer %s disconnected: %s", self.address, error)
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.sock.close()
        except OSError:
            pass
        self.network.peer_closed(self)


class P2PNetwork:
    def __init__(
        self,
        identity: Identity,
        profile: Profile,
        on_message: Callable[[dict[str, Any]], None],
        on_peers: Callable[[list[PeerInfo]], None],
        on_status: Callable[[dict[str, Any]], None] | None = None,
        on_group: Callable[[dict[str, Any]], None] | None = None,
        on_message_action: Callable[[dict[str, Any]], None] | None = None,
        seed_ips: list[str] | None = None,
        tcp_port: int = TCP_PORT,
        discovery_port: int = DISCOVERY_PORT,
        enable_discovery: bool = True,
    ):
        self.identity = identity
        self.profile = profile
        self.on_message = on_message
        self.on_peers = on_peers
        self.on_status = on_status or (lambda _status: None)
        self.on_group = on_group or (lambda _group: None)
        self.on_message_action = on_message_action or (lambda _action: None)
        self.seed_ips = set(seed_ips or [])
        self.tcp_port = tcp_port
        self.discovery_port = discovery_port
        self.enable_discovery = enable_discovery
        self.stopped = threading.Event()
        self._lock = threading.RLock()
        self._connections: set[PeerConnection] = set()
        self._peers: dict[str, tuple[PeerInfo, PeerConnection]] = {}
        self._connecting_ips: set[str] = set()
        self._seen: dict[str, float] = {}
        self._server: socket.socket | None = None
        self._discovery: socket.socket | None = None
        self.local_ips = local_ipv4_info()

    def start(self) -> None:
        self._start_server()
        if self.enable_discovery:
            self._start_discovery()

    def _start_server(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("", self.tcp_port))
        self.tcp_port = server.getsockname()[1]
        server.listen(32)
        server.settimeout(1.0)
        self._server = server

        def accept_loop():
            while not self.stopped.is_set():
                try:
                    sock, address = server.accept()
                    self._register_connection(sock, address, outgoing=False)
                except socket.timeout:
                    continue
                except OSError:
                    break

        threading.Thread(target=accept_loop, name="eduka-tcp-listener", daemon=True).start()

    def _start_discovery(self) -> None:
        receiver = None
        try:
            receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            receiver.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            receiver.bind(("", self.discovery_port))
            joined = False
            for interface in self.local_ips:
                try:
                    membership = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton(interface["address"])
                    receiver.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
                    joined = True
                except OSError:
                    continue
            if not joined:
                receiver.setsockopt(
                    socket.IPPROTO_IP,
                    socket.IP_ADD_MEMBERSHIP,
                    socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton("0.0.0.0"),
                )
            receiver.settimeout(1.0)
            self._discovery = receiver
        except OSError as error:
            LOG.warning("LAN discovery unavailable: %s", error)

        def receive_loop():
            if receiver is None:
                return
            while not self.stopped.is_set():
                try:
                    raw, address = receiver.recvfrom(65507)
                    packet = decode_packet(raw)
                    payload = packet["payload"]
                    if payload.get("type") != "discover" or payload.get("protocol") != PROTOCOL_VERSION:
                        continue
                    if not self._verified(packet) or packet.get("user_id") == self.identity.user_id:
                        continue
                    remote_profile = payload.get("profile", {})
                    if slug(str(remote_profile.get("school", ""))) != slug(self.profile.school):
                        continue
                    user_id = packet["user_id"]
                    with self._lock:
                        known = user_id in self._peers
                    if not known:
                        self.connect_ip(address[0], int(payload.get("tcp_port", TCP_PORT)))
                except socket.timeout:
                    continue
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    continue

        def announce_loop():
            iteration = 0
            while not self.stopped.is_set():
                self._announce_once()
                if iteration % 8 == 0:
                    self._probe_candidates()
                iteration += 1
                self.stopped.wait(4.0)

        if receiver is not None:
            threading.Thread(target=receive_loop, name="eduka-discovery-listener", daemon=True).start()
        threading.Thread(target=announce_loop, name="eduka-discovery-announcer", daemon=True).start()

    def _announce_once(self) -> None:
        try:
            payload = self.hello_payload("discover")
            raw = json.dumps(self.make_packet(payload), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (OSError, ValueError):
            return
        interfaces = self.local_ips or [{"address": "0.0.0.0", "broadcast": "255.255.255.255"}]
        sent_global = False
        for interface in interfaces:
            sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            try:
                sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sender.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 8)
                sender.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 0)
                if interface["address"] != "0.0.0.0":
                    sender.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(interface["address"]))
                sender.sendto(raw, (MULTICAST_GROUP, self.discovery_port))
                sender.sendto(raw, (interface["broadcast"], self.discovery_port))
                if not sent_global:
                    sender.sendto(raw, ("255.255.255.255", self.discovery_port))
                    sent_global = True
            except OSError:
                pass
            finally:
                sender.close()

    def _candidate_ips(self) -> list[str]:
        own = {item["address"] for item in self.local_ips}
        candidates: list[str] = []

        def add(value: str) -> None:
            if value not in candidates:
                candidates.append(value)

        for value in sorted(self.seed_ips):
            add(value)
        try:
            result = subprocess.run(
                ["ip", "-4", "neigh", "show"], capture_output=True, text=True,
                timeout=3, check=True,
            )
            for line in result.stdout.splitlines():
                value = line.split(maxsplit=1)[0]
                ipaddress.ip_address(value)
                add(value)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        for interface in self.local_ips:
            try:
                network = ipaddress.ip_network(interface.get("network", ""), strict=False)
                if network.num_addresses > 512:
                    network = ipaddress.ip_network(f"{interface['address']}/24", strict=False)
                for host in network.hosts():
                    add(str(host))
            except ValueError:
                continue
        valid = []
        for value in candidates:
            try:
                parsed = ipaddress.ip_address(value)
            except ValueError:
                continue
            if parsed.version == 4 and not parsed.is_loopback and value not in own:
                valid.append(value)
        return valid[:512]

    def _probe_candidates(self) -> None:
        candidates = self._candidate_ips()
        if not candidates or self.stopped.is_set():
            return

        def probe(ip: str) -> None:
            with self._lock:
                if ip in self._connecting_ips or any(peer.ip == ip for peer, _ in self._peers.values()):
                    return
                self._connecting_ips.add(ip)
            try:
                sock = socket.create_connection((ip, TCP_PORT), timeout=0.22)
                self._register_connection(sock, (ip, TCP_PORT), outgoing=True)
            except OSError:
                pass
            finally:
                with self._lock:
                    self._connecting_ips.discard(ip)

        with ThreadPoolExecutor(max_workers=48, thread_name_prefix="eduka-probe") as executor:
            list(executor.map(probe, candidates))

    def refresh_discovery(self) -> None:
        """Immediately retry every local discovery path and known peer address."""
        self.local_ips = local_ipv4_info()
        if self._discovery:
            for interface in self.local_ips:
                try:
                    membership = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton(interface["address"])
                    self._discovery.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
                except OSError:
                    continue

        def refresh_worker():
            self._announce_once()
            self._probe_candidates()

        threading.Thread(target=refresh_worker, name="eduka-refresh", daemon=True).start()

    def hello_payload(self, message_type: str = "hello") -> dict[str, Any]:
        return {
            "type": message_type,
            "protocol": PROTOCOL_VERSION,
            "tcp_port": self.tcp_port,
            "profile": self.profile.public(include_photo=message_type != "discover"),
            "local_ips": [item["address"] for item in self.local_ips],
            "timestamp": time.time(),
        }

    def make_packet(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "payload": payload,
            "signature": self.identity.sign(payload),
            "public_key": self.identity.public_key,
            "user_id": self.identity.user_id,
        }

    def _verified(self, packet: dict[str, Any]) -> bool:
        return verify_signature(
            packet.get("payload", {}), packet.get("signature", ""),
            packet.get("public_key", ""), packet.get("user_id", ""),
        )

    def connect_ip(self, ip: str, port: int | None = None) -> None:
        port = port or TCP_PORT
        with self._lock:
            if ip in self._connecting_ips or any(peer.ip == ip for peer, _ in self._peers.values()):
                return
            self._connecting_ips.add(ip)

        def connector():
            try:
                sock = socket.create_connection((ip, port), timeout=4.0)
                self._register_connection(sock, (ip, port), outgoing=True)
            except OSError as error:
                LOG.debug("Could not connect to %s:%s: %s", ip, port, error)
            finally:
                with self._lock:
                    self._connecting_ips.discard(ip)

        threading.Thread(target=connector, name=f"eduka-connect-{ip}", daemon=True).start()

    def _register_connection(self, sock: socket.socket, address: tuple[str, int], outgoing: bool) -> None:
        connection = PeerConnection(self, sock, address, outgoing)
        with self._lock:
            self._connections.add(connection)
        connection.start()

    def handle_packet(self, connection: PeerConnection, packet: dict[str, Any]) -> None:
        if not self._verified(packet):
            raise ValueError("invalid identity signature")
        user_id = packet["user_id"]
        if user_id == self.identity.user_id:
            return
        payload = packet["payload"]
        message_type = payload.get("type")
        if message_type == "hello":
            profile = payload.get("profile")
            if not isinstance(profile, dict) or not profile.get("full_name"):
                raise ValueError("invalid peer profile")
            try:
                parsed_profile = Profile.from_dict(profile)
                if validate_profile(parsed_profile) or slug(parsed_profile.school) != slug(self.profile.school):
                    raise ValueError("peer profile did not pass school profile rules")
            except (TypeError, ValueError):
                raise ValueError("invalid peer profile") from None
            peer = PeerInfo(user_id, profile, connection.address[0], packet["public_key"])
            connection.user_id = user_id
            close_connection = None
            with self._lock:
                old = self._peers.get(user_id)
                # Both peers may connect simultaneously. The lexicographically
                # smaller device ID keeps its outgoing socket, so both ends
                # deterministically keep the same TCP connection.
                prefer_outgoing = self.identity.user_id < user_id
                if old and old[1] is not connection:
                    old_is_preferred = old[1].outgoing == prefer_outgoing
                    new_is_preferred = connection.outgoing == prefer_outgoing
                    if old_is_preferred or not new_is_preferred:
                        close_connection = connection
                    else:
                        self._peers[user_id] = (peer, connection)
                        close_connection = old[1]
                else:
                    self._peers[user_id] = (peer, connection)
            if close_connection:
                close_connection.close()
            self._emit_peers()
            return
        if payload.get("protocol") != PROTOCOL_VERSION:
            return
        if message_type == "status":
            if not self._profile_matches(user_id, payload):
                return
            if not validate_status_payload(payload):
                return
            status_id = str(payload.get("status_id", ""))
            if not self._mark_seen(status_id):
                return
            status = dict(payload)
            status.update({"sender_id": user_id, "verified": True})
            self.on_status(status)
            self._broadcast_packet(packet, except_connection=connection)
            return
        if message_type == "group_create":
            with self._lock:
                owner = self._peers.get(user_id)
            if not owner or owner[0].profile.get("role") != "teacher":
                return
            members = payload.get("members", [])
            if not isinstance(members, list) or self.identity.user_id not in members:
                return
            group = dict(payload)
            group.update({"sender_id": user_id, "verified": True})
            self.on_group(group)
            return
        if message_type == "message_action":
            if not self._profile_matches(user_id, payload) or not validate_message_action_payload(payload):
                return
            if not self._mark_seen(str(payload.get("event_id", ""))):
                return
            targets = payload.get("targets", [])
            targeted = isinstance(targets, list) and bool(targets)
            if targeted and self.identity.user_id not in targets:
                return
            action = dict(payload)
            action.update({"sender_id": user_id, "verified": True})
            self.on_message_action(action)
            if not targeted:
                self._broadcast_packet(packet, except_connection=connection)
            return
        if message_type != "chat":
            return
        if not self._profile_matches(user_id, payload):
            return
        message_id = str(payload.get("msg_id", ""))
        if not self._mark_seen(message_id):
            return
        targets = payload.get("targets", [])
        targeted = isinstance(targets, list) and bool(targets)
        if targeted and self.identity.user_id not in targets:
            return
        message = dict(payload)
        message["sender_id"] = user_id
        message["verified"] = True
        self.on_message(message)
        if not targeted:
            self._broadcast_packet(packet, except_connection=connection)

    def _profile_matches(self, user_id: str, payload: dict[str, Any]) -> bool:
        declared = payload.get("profile")
        if not isinstance(declared, dict):
            return False
        with self._lock:
            peer = self._peers.get(user_id)
        if not peer:
            try:
                parsed = Profile.from_dict(declared)
                return not validate_profile(parsed, require_photo=False) and slug(parsed.school) == slug(self.profile.school)
            except (TypeError, ValueError):
                return False
        known = peer[0].profile
        keys = ("full_name", "school", "role", "age", "school_class", "room", "subject")
        return all(declared.get(key, "") == known.get(key, "") for key in keys)

    def _mark_seen(self, event_id: str) -> bool:
        if not event_id or len(event_id) > 80:
            return False
        now = time.monotonic()
        with self._lock:
            if event_id in self._seen:
                return False
            self._seen[event_id] = now
            if len(self._seen) > 5000:
                cutoff = now - 86400
                self._seen = {key: stamp for key, stamp in self._seen.items() if stamp > cutoff}
        return True

    def send_chat(self, payload: dict[str, Any], target_ids: list[str] | None = None) -> None:
        payload = dict(payload)
        payload.update({"type": "chat", "protocol": PROTOCOL_VERSION})
        if target_ids:
            payload["targets"] = sorted(set(target_ids))
        with self._lock:
            self._seen[payload["msg_id"]] = time.monotonic()
        packet = self.make_packet(payload)
        if target_ids:
            threading.Thread(
                target=self._send_packet_to_users, args=(packet, target_ids),
                name=f"eduka-direct-{payload['msg_id'][:8]}", daemon=True,
            ).start()
            return
        threading.Thread(
            target=self._broadcast_packet, args=(packet,),
            name=f"eduka-send-{payload['msg_id'][:8]}", daemon=True,
        ).start()

    def send_status(self, payload: dict[str, Any]) -> None:
        payload = dict(payload)
        payload.update({"type": "status", "protocol": PROTOCOL_VERSION})
        self._mark_seen(payload["status_id"])
        packet = self.make_packet(payload)
        threading.Thread(target=self._broadcast_packet, args=(packet,), name="eduka-status", daemon=True).start()

    def send_message_action(self, payload: dict[str, Any], target_ids: list[str] | None = None) -> None:
        payload = dict(payload)
        payload.update({"type": "message_action", "protocol": PROTOCOL_VERSION})
        if target_ids:
            payload["targets"] = sorted(set(target_ids))
        self._mark_seen(payload["event_id"])
        packet = self.make_packet(payload)
        if target_ids:
            threading.Thread(
                target=self._send_packet_to_users, args=(packet, target_ids),
                name=f"eduka-action-{payload['event_id'][:8]}", daemon=True,
            ).start()
        else:
            threading.Thread(
                target=self._broadcast_packet, args=(packet,),
                name=f"eduka-action-{payload['event_id'][:8]}", daemon=True,
            ).start()

    def send_group_definition(self, payload: dict[str, Any], member_ids: list[str]) -> None:
        payload = dict(payload)
        payload.update({"type": "group_create", "protocol": PROTOCOL_VERSION, "members": sorted(set(member_ids))})
        packet = self.make_packet(payload)
        threading.Thread(
            target=self._send_packet_to_users, args=(packet, member_ids),
            name="eduka-group-create", daemon=True,
        ).start()

    def _send_packet_to_users(self, packet: dict[str, Any], user_ids: list[str]) -> None:
        with self._lock:
            connections = [self._peers[user_id][1] for user_id in set(user_ids) if user_id in self._peers]
        for connection in connections:
            try:
                connection.send(packet)
            except (OSError, ValueError):
                connection.close()

    def _broadcast_packet(self, packet: dict[str, Any], except_connection: PeerConnection | None = None) -> None:
        with self._lock:
            connections = list(self._connections)
        for connection in connections:
            if connection is except_connection:
                continue
            try:
                connection.send(packet)
            except (OSError, ValueError):
                connection.close()

    def update_profile(self, profile: Profile) -> None:
        self.profile = profile
        self._broadcast_packet(self.make_packet(self.hello_payload()))

    def peer_closed(self, connection: PeerConnection) -> None:
        changed = False
        with self._lock:
            self._connections.discard(connection)
            if connection.user_id and self._peers.get(connection.user_id, (None, None))[1] is connection:
                self._peers.pop(connection.user_id, None)
                changed = True
        if changed:
            self._emit_peers()

    def _emit_peers(self) -> None:
        with self._lock:
            peers = sorted((value[0] for value in self._peers.values()), key=lambda item: item.profile.get("full_name", "").casefold())
        self.on_peers(peers)

    def peers(self) -> list[PeerInfo]:
        with self._lock:
            return [value[0] for value in self._peers.values()]

    def stop(self) -> None:
        self.stopped.set()
        for sock in (self._server, self._discovery):
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass
        with self._lock:
            connections = list(self._connections)
        for connection in connections:
            connection.close()
