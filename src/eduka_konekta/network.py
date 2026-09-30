"""Signed peer-to-peer TCP mesh with LAN discovery that also works over Wi-Fi.

Discovery combines several independent paths because school Wi-Fi access
points frequently drop multicast/broadcast frames or isolate wireless clients:

* multicast and per-interface broadcast announcements (fast on Ethernet);
* unicast UDP announcements to neighbour-table, remembered and gossiped peers;
* a non-blocking TCP sweep of the local subnet with a Wi-Fi friendly timeout;
* signed presence gossip, so a device that everyone can reach (for example a
  teacher computer on the wired LAN) relays peers that cannot reach each other.

Every connection carries a signed presence heartbeat. Dead Wi-Fi links are
detected and closed so the peer can be rediscovered after roaming or sleep.
"""

from __future__ import annotations

import errno
import ipaddress
import json
import logging
import os
import queue
import random
import selectors
import socket
import struct
import subprocess
import threading
import time
import uuid
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
MAX_QUEUED_BYTES = 160 * 1024 * 1024
SEND_CHUNK = 64 * 1024
SOCKET_TIMEOUT = 15.0
HEARTBEAT_INTERVAL = 10.0
CONNECTION_TIMEOUT = 45.0
HANDSHAKE_TIMEOUT = 20.0
ROUTE_TIMEOUT = 35.0
PROBE_TIMEOUT = 1.5
PROBE_BATCH = 96
AUTO_SCAN_HOSTS = 254
FULL_SCAN_HOSTS = 1024
IGNORED_INTERFACES = ("lo", "docker", "veth", "virbr", "podman", "br-", "lxc", "vboxnet", "vmnet", "cni", "flannel")
WIFI_PREFIXES = ("wl", "wlan", "wifi", "ath", "ra")
ETHERNET_PREFIXES = ("en", "eth", "em", "usb")


def interface_kind(name: str) -> str:
    """Classify a network interface as wifi, ethernet or other."""
    if name and os.path.isdir(f"/sys/class/net/{name}/wireless"):
        return "wifi"
    if name.startswith(WIFI_PREFIXES):
        return "wifi"
    if name.startswith(ETHERNET_PREFIXES):
        return "ethernet"
    return "other"


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
            if interface_name.startswith(IGNORED_INTERFACES):
                continue
            for info in interface.get("addr_info", []):
                address = str(info.get("local", ""))
                if not address or address.startswith("127."):
                    continue
                prefix = int(info.get("prefixlen", 24))
                network = ipaddress.ip_interface(f"{address}/{prefix}").network
                broadcast = info.get("broadcast") or str(network.broadcast_address)
                found[address] = {
                    "address": address,
                    "broadcast": str(broadcast),
                    "network": str(network),
                    "prefix": str(prefix),
                    "interface": interface_name,
                    "kind": interface_kind(interface_name),
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
                    "kind": "other",
                }
        except OSError:
            pass
    return list(found.values())


def neighbor_ips() -> list[str]:
    """Return addresses from the kernel neighbour (ARP) table that are alive."""
    values: list[str] = []
    try:
        result = subprocess.run(
            ["ip", "-4", "neigh", "show"], capture_output=True, text=True,
            timeout=3, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return values
    for line in result.stdout.splitlines():
        parts = line.split()
        if not parts or parts[-1] in {"FAILED", "INCOMPLETE"}:
            continue
        try:
            ipaddress.ip_address(parts[0])
        except ValueError:
            continue
        values.append(parts[0])
    return values


def subnet_hosts(address: str, network_text: str, limit: int) -> list[str]:
    """Hosts near ``address``: its own /24 first, then neighbouring /24 blocks."""
    try:
        own = ipaddress.ip_address(address)
        network = ipaddress.ip_network(network_text, strict=False)
    except ValueError:
        return []
    if network.num_addresses <= 2:
        return [str(host) for host in network.hosts() if host != own][:limit]
    if network.prefixlen >= 24:
        blocks = [network]
    else:
        base = ipaddress.ip_network(f"{address}/24", strict=False)
        blocks = [base]
        step = 1
        while len(blocks) * 254 < limit and step < 256:
            for direction in (1, -1):
                start = int(base.network_address) + direction * step * 256
                try:
                    candidate = ipaddress.ip_network(f"{ipaddress.ip_address(start)}/24")
                except ValueError:
                    continue
                if candidate.subnet_of(network):
                    blocks.append(candidate)
            step += 1
    hosts: list[str] = []
    for block in blocks:
        for host in block.hosts():
            if host == own or host == network.broadcast_address or host == network.network_address:
                continue
            hosts.append(str(host))
            if len(hosts) >= limit:
                return hosts
    return hosts


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


def _enable_keepalive(sock: socket.socket) -> None:
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        for option, value in (("TCP_KEEPIDLE", 20), ("TCP_KEEPINTVL", 5), ("TCP_KEEPCNT", 4)):
            if hasattr(socket, option):
                sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, option), value)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass


@dataclass
class PeerInfo:
    user_id: str
    profile: dict[str, Any]
    ip: str
    public_key: str
    port: int = TCP_PORT
    via: str = ""

    @property
    def direct(self) -> bool:
        return not self.via


class PeerConnection:
    """One TCP link with a dedicated reader and an asynchronous writer queue."""

    def __init__(self, network: "P2PNetwork", sock: socket.socket, address: tuple[str, int], outgoing: bool):
        self.network = network
        self.sock = sock
        self.address = address
        self.outgoing = outgoing
        self.user_id: str | None = None
        self.listen_port = address[1] if outgoing else TCP_PORT
        self.created = time.monotonic()
        self.last_rx = self.created
        self.heartbeat_seen = False
        self._queue: queue.Queue[bytes | None] = queue.Queue()
        self._queued_bytes = 0
        self._queue_lock = threading.Lock()
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def start(self) -> None:
        _enable_keepalive(self.sock)
        self.sock.settimeout(SOCKET_TIMEOUT)
        threading.Thread(target=self._writer, name=f"eduka-write-{self.address[0]}", daemon=True).start()
        threading.Thread(target=self._reader, name=f"eduka-read-{self.address[0]}", daemon=True).start()
        self.send(self.network.make_packet(self.network.hello_payload()))

    def send(self, packet: dict[str, Any]) -> None:
        if self._closed:
            return
        self.send_frame(encode_frame(packet))

    def send_frame(self, frame: bytes) -> None:
        if self._closed:
            return
        with self._queue_lock:
            if self._queued_bytes + len(frame) > MAX_QUEUED_BYTES:
                overflow = True
            else:
                overflow = False
                self._queued_bytes += len(frame)
        if overflow:
            LOG.warning("Send queue to %s overflowed; closing slow connection", self.address[0])
            self.close()
            return
        self._queue.put(frame)

    def _writer(self) -> None:
        try:
            while not self._closed and not self.network.stopped.is_set():
                try:
                    frame = self._queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                if frame is None:
                    break
                view = memoryview(frame)
                offset = 0
                while offset < len(view):
                    offset += self.sock.send(view[offset:offset + SEND_CHUNK])
                with self._queue_lock:
                    self._queued_bytes -= len(frame)
        except (OSError, ValueError) as error:
            LOG.debug("Writer to %s stopped: %s", self.address, error)
        finally:
            self.close()

    def _reader(self) -> None:
        buffer = bytearray()
        try:
            while not self.network.stopped.is_set() and not self._closed:
                try:
                    chunk = self.sock.recv(256 * 1024)
                except socket.timeout:
                    idle = time.monotonic() - self.last_rx
                    if self.heartbeat_seen and idle > CONNECTION_TIMEOUT:
                        raise ConnectionError("heartbeat timeout") from None
                    if self.user_id is None and idle > HANDSHAKE_TIMEOUT:
                        raise ConnectionError("handshake timeout") from None
                    continue
                if not chunk:
                    raise ConnectionError("peer closed connection")
                self.last_rx = time.monotonic()
                buffer.extend(chunk)
                while len(buffer) >= 4:
                    size = struct.unpack("!I", buffer[:4])[0]
                    if size <= 0 or size > MAX_FRAME:
                        raise ValueError("invalid frame size")
                    if len(buffer) < 4 + size:
                        break
                    raw = bytes(buffer[4:4 + size])
                    del buffer[:4 + size]
                    self.network.handle_packet(self, decode_packet(raw))
        except (OSError, ConnectionError, ValueError, json.JSONDecodeError) as error:
            LOG.debug("Peer %s disconnected: %s", self.address, error)
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
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
        on_school: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.identity = identity
        self.profile = profile
        self.on_message = on_message
        self.on_peers = on_peers
        self.on_status = on_status or (lambda _status: None)
        self.on_group = on_group or (lambda _group: None)
        self.on_message_action = on_message_action or (lambda _action: None)
        self.on_school = on_school or (lambda _event: None)
        self.seed_ips = set(seed_ips or [])
        self.tcp_port = tcp_port
        self.discovery_port = discovery_port
        self.enable_discovery = enable_discovery
        self.stopped = threading.Event()
        self._lock = threading.RLock()
        self._connections: set[PeerConnection] = set()
        self._peers: dict[str, tuple[PeerInfo, PeerConnection]] = {}
        self._routes: dict[str, tuple[PeerInfo, PeerConnection, float]] = {}
        self._neighbor_direct: dict[str, set[str]] = {}
        self._presence_packets: dict[str, dict[str, Any]] = {}
        self._connecting: set[tuple[str, int]] = set()
        self._last_attempt: dict[str, float] = {}
        self._last_reply: dict[str, float] = {}
        self._gossip_ips: dict[str, int] = {}
        self._seen: dict[str, float] = {}
        self._server: socket.socket | None = None
        self._discovery: socket.socket | None = None
        self._joined: set[str] = set()
        self._presence_dirty = threading.Event()
        self._sweep_now = threading.Event()
        self._full_sweep = True
        self.last_sweep: float = 0.0
        self.local_ips = local_ipv4_info()

    # Lifecycle -----------------------------------------------------------
    def start(self) -> None:
        self._start_server()
        threading.Thread(target=self._maintenance_loop, name="eduka-maintenance", daemon=True).start()
        if self.enable_discovery:
            self._start_discovery()

    def stop(self) -> None:
        self.stopped.set()
        self._sweep_now.set()
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

    def _start_server(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("", self.tcp_port))
        self.tcp_port = server.getsockname()[1]
        server.listen(64)
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
                    if self.stopped.is_set():
                        break
                    time.sleep(0.2)

        threading.Thread(target=accept_loop, name="eduka-tcp-listener", daemon=True).start()

    # Discovery -----------------------------------------------------------
    def _open_discovery_socket(self) -> None:
        if self._discovery is not None:
            return
        try:
            receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            receiver.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    receiver.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass
            receiver.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            receiver.bind(("", self.discovery_port))
            receiver.settimeout(1.0)
            self._discovery = receiver
            self._joined = set()
        except OSError as error:
            LOG.warning("LAN discovery listener unavailable: %s", error)
            self._discovery = None
        self._join_multicast()

    def _join_multicast(self) -> None:
        """Join the discovery group on every interface, including new Wi-Fi links."""
        receiver = self._discovery
        if receiver is None:
            return
        current = {item["address"] for item in self.local_ips}
        for address in sorted(current - self._joined):
            try:
                membership = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton(address)
                receiver.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
            except OSError as error:
                if error.errno != errno.EADDRINUSE:
                    LOG.debug("Multicast join on %s failed: %s", address, error)
                    continue
            self._joined.add(address)
        self._joined &= current

    def refresh_interfaces(self) -> bool:
        """Re-read interfaces. Returns True when addresses changed (Wi-Fi joined, DHCP renew)."""
        fresh = local_ipv4_info()
        changed = {item["address"] for item in fresh} != {item["address"] for item in self.local_ips}
        self.local_ips = fresh
        if changed:
            LOG.info("Network interfaces changed: %s", ", ".join(item["address"] for item in fresh) or "none")
            self._join_multicast()
            self._full_sweep = True
            self._sweep_now.set()
        return changed

    def _start_discovery(self) -> None:
        self._open_discovery_socket()

        def receive_loop():
            while not self.stopped.is_set():
                receiver = self._discovery
                if receiver is None:
                    self.stopped.wait(2.0)
                    continue
                try:
                    raw, address = receiver.recvfrom(65507)
                except socket.timeout:
                    continue
                except OSError:
                    if self.stopped.is_set():
                        break
                    self.stopped.wait(0.5)
                    continue
                try:
                    self._handle_discovery(decode_packet(raw), address[0])
                except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                    continue

        def announce_loop():
            iteration = 0
            while not self.stopped.is_set():
                if iteration % 3 == 0:
                    self.refresh_interfaces()
                    if self._discovery is None:
                        self._open_discovery_socket()
                self._announce_once()
                if iteration % 4 == 1:
                    self._unicast_announce(self._known_candidate_ips())
                iteration += 1
                self.stopped.wait(4.0)

        def sweep_loop():
            # Randomised start avoids every classroom computer sweeping at once.
            self._sweep_now.wait(random.uniform(1.0, 4.0))
            interval = 30.0
            while not self.stopped.is_set():
                self._sweep_now.clear()
                full = self._full_sweep
                self._full_sweep = False
                self._probe_candidates(full=full)
                if full:
                    interval = 30.0
                else:
                    interval = min(interval * 2, 240.0)
                self._sweep_now.wait(interval + random.uniform(0, 5))

        threading.Thread(target=receive_loop, name="eduka-discovery-listener", daemon=True).start()
        threading.Thread(target=announce_loop, name="eduka-discovery-announcer", daemon=True).start()
        threading.Thread(target=sweep_loop, name="eduka-discovery-sweep", daemon=True).start()

    def _handle_discovery(self, packet: dict[str, Any], source_ip: str) -> None:
        payload = packet["payload"]
        kind = payload.get("type")
        if kind not in {"discover", "discover_reply"} or payload.get("protocol") != PROTOCOL_VERSION:
            return
        if packet.get("user_id") == self.identity.user_id or not self._verified(packet):
            return
        remote_profile = payload.get("profile", {})
        if not isinstance(remote_profile, dict) or slug(str(remote_profile.get("school", ""))) != slug(self.profile.school):
            return
        user_id = packet["user_id"]
        port = int(payload.get("tcp_port", TCP_PORT) or TCP_PORT)
        if kind == "discover":
            # Answer directly so a peer whose broadcast reached us can also reach us
            # back even when the access point drops our own broadcasts.
            now = time.monotonic()
            if now - self._last_reply.get(source_ip, 0.0) > 5.0:
                self._last_reply[source_ip] = now
                self._send_udp(source_ip, self._discover_bytes("discover_reply"))
        with self._lock:
            known = user_id in self._peers
        if not known:
            self.connect_ip(source_ip, port, force=True)

    def _discover_bytes(self, kind: str = "discover") -> bytes:
        payload = self.hello_payload(kind)
        return json.dumps(self.make_packet(payload), ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def _send_udp(self, ip: str, raw: bytes) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sender:
            try:
                sender.sendto(raw, (ip, self.discovery_port))
            except OSError:
                pass

    def _announce_once(self) -> None:
        try:
            raw = self._discover_bytes()
        except (OSError, ValueError):
            return
        interfaces = self.local_ips or [{"address": "0.0.0.0", "broadcast": "255.255.255.255"}]
        for interface in interfaces:
            sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            try:
                sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sender.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
                sender.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 0)
                if interface["address"] != "0.0.0.0":
                    # Binding to the interface address makes the broadcast leave
                    # through that interface (Wi-Fi and Ethernet separately).
                    try:
                        sender.bind((interface["address"], 0))
                    except OSError:
                        pass
                    sender.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(interface["address"]))
                for target in (MULTICAST_GROUP, interface["broadcast"], "255.255.255.255"):
                    try:
                        sender.sendto(raw, (target, self.discovery_port))
                    except OSError:
                        continue
            finally:
                sender.close()

    def _unicast_announce(self, ips: list[str]) -> None:
        if not ips:
            return
        try:
            raw = self._discover_bytes()
        except (OSError, ValueError):
            return
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sender:
            for ip in ips:
                if self.stopped.is_set():
                    return
                try:
                    sender.sendto(raw, (ip, self.discovery_port))
                except OSError:
                    continue

    def _connected_addresses(self) -> set[str]:
        with self._lock:
            return {peer.ip for peer, _ in self._peers.values()}

    def _known_candidate_ips(self) -> list[str]:
        own = {item["address"] for item in self.local_ips}
        connected = self._connected_addresses()
        values: list[str] = []
        with self._lock:
            gossip = list(self._gossip_ips)
        for value in [*sorted(self.seed_ips), *gossip, *neighbor_ips()]:
            try:
                parsed = ipaddress.ip_address(value)
            except ValueError:
                continue
            if parsed.version != 4 or parsed.is_loopback or parsed.is_multicast:
                continue
            if value in own or value in connected or value in values:
                continue
            values.append(value)
        return values

    def _candidate_ips(self, full: bool = True) -> list[str]:
        limit = FULL_SCAN_HOSTS if full else AUTO_SCAN_HOSTS
        candidates = self._known_candidate_ips()
        own = {item["address"] for item in self.local_ips}
        connected = self._connected_addresses()
        seen = set(candidates)
        for interface in self.local_ips:
            for host in subnet_hosts(interface["address"], interface.get("network", ""), limit):
                if host in seen or host in own or host in connected:
                    continue
                seen.add(host)
                candidates.append(host)
        return candidates[: limit + 256]

    def _probe_candidates(self, full: bool = True) -> None:
        """Non-blocking TCP sweep with a timeout long enough for Wi-Fi and ARP."""
        candidates = self._candidate_ips(full)
        if not candidates or self.stopped.is_set():
            return
        self.last_sweep = time.time()
        self._unicast_announce(candidates)
        for start in range(0, len(candidates), PROBE_BATCH):
            if self.stopped.is_set():
                return
            self._probe_batch(candidates[start:start + PROBE_BATCH])

    def _probe_batch(self, batch: list[str]) -> None:
        selector = selectors.DefaultSelector()
        pending: dict[socket.socket, str] = {}
        try:
            for ip in batch:
                key = (ip, TCP_PORT)
                with self._lock:
                    if key in self._connecting or ip in {peer.ip for peer, _ in self._peers.values()}:
                        continue
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setblocking(False)
                error = sock.connect_ex((ip, TCP_PORT))
                if error not in (0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY):
                    sock.close()
                    continue
                pending[sock] = ip
                selector.register(sock, selectors.EVENT_WRITE)
            deadline = time.monotonic() + PROBE_TIMEOUT
            while pending and not self.stopped.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                for key, _events in selector.select(remaining):
                    sock = key.fileobj
                    ip = pending.pop(sock)
                    selector.unregister(sock)
                    if sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) != 0:
                        sock.close()
                        continue
                    with self._lock:
                        busy = (ip, TCP_PORT) in self._connecting or ip in {peer.ip for peer, _ in self._peers.values()}
                    if busy:
                        sock.close()
                        continue
                    sock.setblocking(True)
                    self._register_connection(sock, (ip, TCP_PORT), outgoing=True)
        finally:
            for sock in pending:
                try:
                    selector.unregister(sock)
                except (KeyError, ValueError):
                    pass
                sock.close()
            selector.close()

    def refresh_discovery(self) -> None:
        """Immediately retry every local discovery path and known peer address."""
        def refresh_worker():
            self.refresh_interfaces()
            if self.enable_discovery:
                self._open_discovery_socket()
                self._announce_once()
            for ip in list(self.seed_ips):
                self.connect_ip(ip, force=True)
            if self.enable_discovery:
                self._full_sweep = True
                self._sweep_now.set()

        threading.Thread(target=refresh_worker, name="eduka-refresh", daemon=True).start()

    # Packets -------------------------------------------------------------
    def hello_payload(self, message_type: str = "hello") -> dict[str, Any]:
        return {
            "type": message_type,
            "protocol": PROTOCOL_VERSION,
            "tcp_port": self.tcp_port,
            "profile": self.profile.public(include_photo=message_type == "hello"),
            "local_ips": [item["address"] for item in self.local_ips],
            "timestamp": time.time(),
        }

    def presence_payload(self) -> dict[str, Any]:
        with self._lock:
            direct = sorted(self._peers)[:512]
        return {
            "type": "presence",
            "protocol": PROTOCOL_VERSION,
            "presence_id": uuid.uuid4().hex,
            "tcp_port": self.tcp_port,
            "profile": self.profile.public(include_photo=False),
            "local_ips": [item["address"] for item in self.local_ips],
            "direct_ids": direct,
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

    # Connections ---------------------------------------------------------
    def connect_ip(self, ip: str, port: int | None = None, force: bool = False) -> None:
        port = port or TCP_PORT
        key = (ip, port)
        now = time.monotonic()
        with self._lock:
            if key in self._connecting:
                return
            if any(peer.ip == ip and peer.port == port for peer, _ in self._peers.values()):
                return
            if not force and now - self._last_attempt.get(f"{ip}:{port}", 0.0) < 10.0:
                return
            self._last_attempt[f"{ip}:{port}"] = now
            self._connecting.add(key)

        def connector():
            try:
                sock = socket.create_connection((ip, port), timeout=5.0)
                self._register_connection(sock, (ip, port), outgoing=True)
            except OSError as error:
                LOG.debug("Could not connect to %s:%s: %s", ip, port, error)
            finally:
                with self._lock:
                    self._connecting.discard(key)

        threading.Thread(target=connector, name=f"eduka-connect-{ip}", daemon=True).start()

    def _register_connection(self, sock: socket.socket, address: tuple[str, int], outgoing: bool) -> None:
        connection = PeerConnection(self, sock, address, outgoing)
        with self._lock:
            self._connections.add(connection)
        connection.start()

    def peer_closed(self, connection: PeerConnection) -> None:
        changed = False
        with self._lock:
            self._connections.discard(connection)
            if connection.user_id and self._peers.get(connection.user_id, (None, None))[1] is connection:
                self._peers.pop(connection.user_id, None)
                self._neighbor_direct.pop(connection.user_id, None)
                self._presence_packets.pop(connection.user_id, None)
                changed = True
            for user_id in [uid for uid, route in self._routes.items() if route[1] is connection]:
                self._routes.pop(user_id, None)
                changed = True
        if changed and not self.stopped.is_set():
            self._presence_dirty.set()
            self._emit_peers()

    def _maintenance_loop(self) -> None:
        last_presence = 0.0
        while not self.stopped.is_set():
            self._presence_dirty.wait(1.0)
            if self.stopped.is_set():
                break
            now = time.monotonic()
            if self._presence_dirty.is_set() or now - last_presence >= HEARTBEAT_INTERVAL:
                self._presence_dirty.clear()
                last_presence = now
                self._send_presence()
            expired = False
            with self._lock:
                for user_id, (_peer, connection, seen) in list(self._routes.items()):
                    if now - seen > ROUTE_TIMEOUT or connection.closed:
                        self._routes.pop(user_id, None)
                        expired = True
                stale = [
                    connection for connection in self._connections
                    if connection.user_id is None and now - connection.created > HANDSHAKE_TIMEOUT
                ]
            for connection in stale:
                connection.close()
            if expired:
                self._emit_peers()
            # A presence message arriving while this loop slept could mark it
            # dirty again; limit the rate to one presence per second.
            self.stopped.wait(0.5)

    def _send_presence(self) -> None:
        packet = self.make_packet(self.presence_payload())
        frame = encode_frame(packet)
        with self._lock:
            connections = [connection for _peer, connection in self._peers.values()]
        for connection in connections:
            connection.send_frame(frame)

    # Receiving -----------------------------------------------------------
    def handle_packet(self, connection: PeerConnection, packet: dict[str, Any]) -> None:
        if not self._verified(packet):
            raise ValueError("invalid identity signature")
        user_id = packet["user_id"]
        payload = packet["payload"]
        message_type = payload.get("type")
        if user_id == self.identity.user_id:
            if message_type == "hello":
                # We reached ourselves through another local address.
                connection.close()
            return
        if message_type == "hello":
            self._handle_hello(connection, packet)
            return
        if payload.get("protocol") != PROTOCOL_VERSION:
            return
        if message_type == "presence":
            self._handle_presence(connection, packet)
            return
        if message_type == "relay_presence":
            self._handle_relay_presence(connection, packet)
            return
        if message_type == "status":
            if not self._profile_matches(user_id, payload) or not validate_status_payload(payload):
                return
            if not self._mark_seen(str(payload.get("status_id", ""))):
                return
            status = dict(payload)
            status.update({"sender_id": user_id, "verified": True})
            self.on_status(status)
            self._relay_broadcast(packet, connection)
            return
        if message_type == "group_create":
            owner = self._known_profile(user_id)
            if not owner or owner.get("role") != "teacher":
                return
            members = payload.get("members", [])
            if not isinstance(members, list):
                return
            if not self._mark_seen("grp-" + str(payload.get("group_id", ""))[:70] + str(payload.get("timestamp", ""))[:6]):
                return
            self._forward_targeted(packet, members, connection)
            if self.identity.user_id not in members:
                return
            group = dict(payload)
            group.update({"sender_id": user_id, "verified": True})
            self.on_group(group)
            return
        if message_type == "message_action":
            if not self._profile_matches(user_id, payload) or not validate_message_action_payload(payload):
                return
            self._deliver(connection, packet, str(payload.get("event_id", "")), self.on_message_action)
            return
        if message_type == "school":
            if not self._profile_matches(user_id, payload):
                return
            self._deliver(connection, packet, str(payload.get("event_id", "")), self.on_school)
            return
        if message_type == "chat":
            if not self._profile_matches(user_id, payload):
                return
            self._deliver(connection, packet, str(payload.get("msg_id", "")), self.on_message)

    def _deliver(self, connection: PeerConnection, packet: dict[str, Any], event_id: str, callback) -> None:
        """Deduplicate, relay one hop when needed, and hand a packet to the UI."""
        if not self._mark_seen(event_id):
            return
        payload = packet["payload"]
        targets = payload.get("targets", [])
        targeted = isinstance(targets, list) and bool(targets)
        if targeted:
            self._forward_targeted(packet, targets, connection)
            if self.identity.user_id not in targets:
                return
        else:
            self._relay_broadcast(packet, connection)
        item = dict(payload)
        item["sender_id"] = packet["user_id"]
        item["verified"] = True
        callback(item)

    def _handle_hello(self, connection: PeerConnection, packet: dict[str, Any]) -> None:
        user_id = packet["user_id"]
        payload = packet["payload"]
        profile = payload.get("profile")
        if not isinstance(profile, dict) or not profile.get("full_name"):
            raise ValueError("invalid peer profile")
        try:
            parsed_profile = Profile.from_dict(profile)
            if validate_profile(parsed_profile) or slug(parsed_profile.school) != slug(self.profile.school):
                raise ValueError("peer profile did not pass school profile rules")
        except (TypeError, ValueError):
            raise ValueError("invalid peer profile") from None
        try:
            port = int(payload.get("tcp_port", TCP_PORT))
        except (TypeError, ValueError):
            port = TCP_PORT
        connection.listen_port = port
        peer = PeerInfo(user_id, profile, connection.address[0], packet["public_key"], port)
        connection.user_id = user_id
        close_connection = None
        with self._lock:
            old = self._peers.get(user_id)
            # Both peers may connect simultaneously. The lexicographically
            # smaller device ID keeps its outgoing socket, so both ends
            # deterministically keep the same TCP connection.
            prefer_outgoing = self.identity.user_id < user_id
            if old and old[1] is not connection and not old[1].closed:
                old_is_preferred = old[1].outgoing == prefer_outgoing
                new_is_preferred = connection.outgoing == prefer_outgoing
                if old_is_preferred or not new_is_preferred:
                    close_connection = connection
                else:
                    self._peers[user_id] = (peer, connection)
                    close_connection = old[1]
            else:
                self._peers[user_id] = (peer, connection)
            self._routes.pop(user_id, None)
        if close_connection:
            close_connection.close()
        self._presence_dirty.set()
        self._emit_peers()

    def _handle_presence(self, connection: PeerConnection, packet: dict[str, Any]) -> None:
        user_id = packet["user_id"]
        if connection.user_id != user_id:
            return
        payload = packet["payload"]
        if not self._profile_matches(user_id, payload):
            return
        direct_ids = payload.get("direct_ids", [])
        if not isinstance(direct_ids, list):
            return
        connection.heartbeat_seen = True
        advertised = {str(item) for item in direct_ids[:512]}
        with self._lock:
            self._neighbor_direct[user_id] = advertised
            self._presence_packets[user_id] = packet
            # A relay stopped advertising someone: that user left, forget them now.
            gone = [
                uid for uid, route in self._routes.items()
                if route[1] is connection and uid not in advertised
            ]
            for uid in gone:
                self._routes.pop(uid, None)
            our_direct = {uid: conn for uid, (_peer, conn) in self._peers.items()}
            missing_for_sender = [
                self._presence_packets[uid] for uid in our_direct
                if uid != user_id and uid not in advertised and uid in self._presence_packets
            ]
            push_targets = [
                conn for uid, conn in our_direct.items()
                if uid != user_id and uid in self._neighbor_direct and user_id not in self._neighbor_direct[uid]
            ]
        if gone:
            self._emit_peers()
        if missing_for_sender:
            connection.send(self._relay_bundle(missing_for_sender))
        if push_targets:
            bundle = encode_frame(self._relay_bundle([packet]))
            for target in push_targets:
                target.send_frame(bundle)

    def _relay_bundle(self, packets: list[dict[str, Any]]) -> dict[str, Any]:
        return self.make_packet({
            "type": "relay_presence", "protocol": PROTOCOL_VERSION,
            "bundle_id": uuid.uuid4().hex, "packets": packets[:256],
        })

    def _handle_relay_presence(self, connection: PeerConnection, packet: dict[str, Any]) -> None:
        if connection.user_id != packet["user_id"]:
            return
        inner_packets = packet["payload"].get("packets", [])
        if not isinstance(inner_packets, list):
            return
        changed = False
        now = time.monotonic()
        for inner in inner_packets[:256]:
            if not isinstance(inner, dict) or not isinstance(inner.get("payload"), dict):
                continue
            payload = inner["payload"]
            user_id = inner.get("user_id")
            if payload.get("type") != "presence" or user_id == self.identity.user_id:
                continue
            if not self._verified(inner):
                continue
            profile = payload.get("profile")
            try:
                parsed = Profile.from_dict(profile)
                if validate_profile(parsed) or slug(parsed.school) != slug(self.profile.school):
                    continue
            except (TypeError, ValueError, AttributeError):
                continue
            ips = [str(ip) for ip in payload.get("local_ips", []) if isinstance(ip, str)][:8]
            try:
                port = int(payload.get("tcp_port", TCP_PORT))
            except (TypeError, ValueError):
                port = TCP_PORT
            peer = PeerInfo(user_id, profile, ips[0] if ips else "", inner.get("public_key", ""), port, via=connection.user_id or "")
            with self._lock:
                if user_id in self._peers:
                    continue
                if user_id not in self._routes:
                    changed = True
                self._routes[user_id] = (peer, connection, now)
                for ip in ips:
                    self._gossip_ips[ip] = port
                while len(self._gossip_ips) > 1024:
                    self._gossip_ips.pop(next(iter(self._gossip_ips)))
            # Gossip also teaches us addresses we may reach directly.
            for ip in ips:
                self.connect_ip(ip, port)
        if changed:
            self._emit_peers()

    def _known_profile(self, user_id: str) -> dict[str, Any] | None:
        with self._lock:
            if user_id in self._peers:
                return self._peers[user_id][0].profile
            if user_id in self._routes:
                return self._routes[user_id][0].profile
        return None

    def _profile_matches(self, user_id: str, payload: dict[str, Any]) -> bool:
        declared = payload.get("profile")
        if not isinstance(declared, dict):
            return False
        known = self._known_profile(user_id)
        if not known:
            try:
                parsed = Profile.from_dict(declared)
                return not validate_profile(parsed, require_photo=False) and slug(parsed.school) == slug(self.profile.school)
            except (TypeError, ValueError):
                return False
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
                cutoff = now - 3600
                self._seen = {key: stamp for key, stamp in self._seen.items() if stamp > cutoff}
        return True

    # Relaying ------------------------------------------------------------
    def _forward_targeted(self, packet: dict[str, Any], targets: list[Any], incoming: PeerConnection | None) -> None:
        """Relay a targeted packet one hop to direct peers its sender cannot reach."""
        origin = packet["user_id"]
        if incoming is None or incoming.user_id != origin:
            return
        with self._lock:
            origin_direct = self._neighbor_direct.get(origin, set())
            connections = []
            for target in {str(item) for item in targets}:
                if target in {origin, self.identity.user_id} or target in origin_direct:
                    continue
                entry = self._peers.get(target)
                if entry and entry[1] is not incoming and entry[1] not in connections:
                    connections.append(entry[1])
        if connections:
            frame = encode_frame(packet)
            for connection in connections:
                connection.send_frame(frame)

    def _relay_broadcast(self, packet: dict[str, Any], incoming: PeerConnection | None) -> None:
        """Relay a room packet one hop to peers that are not directly linked to its sender."""
        origin = packet["user_id"]
        if incoming is None or incoming.user_id != origin:
            return
        with self._lock:
            origin_direct = self._neighbor_direct.get(origin)
            connections = [
                connection for uid, (_peer, connection) in self._peers.items()
                if connection is not incoming and uid != origin
                and (origin_direct is None or uid not in origin_direct)
            ]
        if connections:
            frame = encode_frame(packet)
            for connection in connections:
                connection.send_frame(frame)

    # Sending -------------------------------------------------------------
    def _send_async(self, packet: dict[str, Any], target_ids: list[str] | None, name: str) -> None:
        if target_ids:
            target = self._send_packet_to_users
            args: tuple = (packet, target_ids)
        else:
            target = self._broadcast_packet
            args = (packet,)
        threading.Thread(target=target, args=args, name=name, daemon=True).start()

    def send_chat(self, payload: dict[str, Any], target_ids: list[str] | None = None) -> None:
        payload = dict(payload)
        payload.update({"type": "chat", "protocol": PROTOCOL_VERSION})
        if target_ids:
            payload["targets"] = sorted(set(target_ids))
        self._mark_seen(payload["msg_id"])
        self._send_async(self.make_packet(payload), target_ids, f"eduka-send-{payload['msg_id'][:8]}")

    def send_status(self, payload: dict[str, Any]) -> None:
        payload = dict(payload)
        payload.update({"type": "status", "protocol": PROTOCOL_VERSION})
        self._mark_seen(payload["status_id"])
        self._send_async(self.make_packet(payload), None, "eduka-status")

    def send_message_action(self, payload: dict[str, Any], target_ids: list[str] | None = None) -> None:
        payload = dict(payload)
        payload.update({"type": "message_action", "protocol": PROTOCOL_VERSION})
        if target_ids:
            payload["targets"] = sorted(set(target_ids))
        self._mark_seen(payload["event_id"])
        self._send_async(self.make_packet(payload), target_ids, f"eduka-action-{payload['event_id'][:8]}")

    def send_school(self, payload: dict[str, Any], target_ids: list[str] | None = None) -> None:
        """Send a signed school event (exam, submission, attendance, rules)."""
        payload = dict(payload)
        payload.setdefault("event_id", uuid.uuid4().hex)
        payload.update({"type": "school", "protocol": PROTOCOL_VERSION})
        if target_ids:
            payload["targets"] = sorted(set(target_ids))
        self._mark_seen(payload["event_id"])
        self._send_async(self.make_packet(payload), target_ids, f"eduka-school-{payload['event_id'][:8]}")

    def send_group_definition(self, payload: dict[str, Any], member_ids: list[str]) -> None:
        payload = dict(payload)
        payload.update({"type": "group_create", "protocol": PROTOCOL_VERSION, "members": sorted(set(member_ids))})
        self._mark_seen("grp-" + str(payload.get("group_id", ""))[:70] + str(payload.get("timestamp", ""))[:6])
        self._send_async(self.make_packet(payload), member_ids, "eduka-group-create")

    def _send_packet_to_users(self, packet: dict[str, Any], user_ids: list[str]) -> None:
        """Send directly when possible, otherwise through the relay that announced the user."""
        with self._lock:
            connections: list[PeerConnection] = []
            for user_id in set(user_ids):
                if user_id in self._peers:
                    connection = self._peers[user_id][1]
                elif user_id in self._routes:
                    connection = self._routes[user_id][1]
                else:
                    continue
                if connection not in connections:
                    connections.append(connection)
        if not connections:
            return
        frame = encode_frame(packet)
        for connection in connections:
            connection.send_frame(frame)

    def _broadcast_packet(self, packet: dict[str, Any], except_connection: PeerConnection | None = None) -> None:
        with self._lock:
            connections = [connection for _peer, connection in self._peers.values() if connection is not except_connection]
        if not connections:
            return
        frame = encode_frame(packet)
        for connection in connections:
            connection.send_frame(frame)

    def update_profile(self, profile: Profile) -> None:
        self.profile = profile
        self._broadcast_packet(self.make_packet(self.hello_payload()))
        self._presence_dirty.set()

    # Directory -----------------------------------------------------------
    def _emit_peers(self) -> None:
        self.on_peers(self.peers())

    def peers(self) -> list[PeerInfo]:
        """Direct peers plus peers reachable through one relay, sorted by name."""
        with self._lock:
            items = [value[0] for value in self._peers.values()]
            items += [route[0] for uid, route in self._routes.items() if uid not in self._peers]
        return sorted(items, key=lambda item: str(item.profile.get("full_name", "")).casefold())

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            direct = len(self._peers)
            relayed = len([uid for uid in self._routes if uid not in self._peers])
            connections = len(self._connections)
        return {
            "interfaces": list(self.local_ips),
            "tcp_port": self.tcp_port,
            "discovery_port": self.discovery_port,
            "listening_discovery": self._discovery is not None,
            "direct": direct,
            "relayed": relayed,
            "connections": connections,
            "last_sweep": self.last_sweep,
        }
