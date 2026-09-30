"""Local webcam and microphone discovery plus bounded FFmpeg capture."""

from __future__ import annotations

import shutil
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MediaDevice:
    kind: str
    name: str
    source: str
    backend: str


def _command_output(command: list[str], timeout: float = 3.0) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def detect_video_devices(device_root: Path = Path("/dev")) -> list[MediaDevice]:
    """Find Linux V4L2 capture nodes without requiring a desktop portal."""
    devices = []
    for path in sorted(device_root.glob("video*")):
        if not path.exists():
            continue
        name = f"Webcam {path.name}"
        properties = _command_output(
            ["udevadm", "info", "--query=property", f"--name={path}"], timeout=2.0
        )
        for line in properties.splitlines():
            if line.startswith("ID_V4L_PRODUCT="):
                name = line.partition("=")[2].replace("_", " ").strip() or name
                break
        devices.append(MediaDevice("video", name, str(path), "v4l2"))
    return devices


def detect_audio_devices() -> list[MediaDevice]:
    """Find PulseAudio/PipeWire microphone sources, with an ALSA fallback."""
    devices = []
    if shutil.which("pactl"):
        output = _command_output(["pactl", "list", "short", "sources"])
        for line in output.splitlines():
            columns = line.split("\t")
            if len(columns) < 2:
                columns = line.split()
            if len(columns) < 2:
                continue
            source = columns[1]
            if source.endswith(".monitor"):
                continue
            devices.append(MediaDevice("audio", source, source, "pulse"))
    if not devices and Path("/proc/asound").exists():
        devices.append(MediaDevice("audio", "Default ALSA microphone", "default", "alsa"))
    return devices


class DeviceManager:
    """Build and run conservative FFmpeg commands for chat media capture."""

    def __init__(self, capture_dir: Path):
        self.capture_dir = capture_dir
        self.capture_dir.mkdir(parents=True, exist_ok=True)

    @property
    def ffmpeg_available(self) -> bool:
        return shutil.which("ffmpeg") is not None

    def video_devices(self) -> list[MediaDevice]:
        return detect_video_devices()

    def audio_devices(self) -> list[MediaDevice]:
        return detect_audio_devices()

    def capture_path(self, stem: str, suffix: str) -> Path:
        candidate = self.capture_dir / f"{stem}{suffix}"
        counter = 1
        while candidate.exists():
            candidate = self.capture_dir / f"{stem}-{counter}{suffix}"
            counter += 1
        return candidate

    def capture_photo(self, device: MediaDevice, output: Path) -> tuple[bool, str]:
        if not self.ffmpeg_available:
            return False, "ffmpeg is not installed"
        command = [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "v4l2", "-i", device.source,
            "-frames:v", "1", "-q:v", "2", str(output),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=12)
        except (OSError, subprocess.SubprocessError) as error:
            return False, str(error)
        return result.returncode == 0 and output.is_file(), result.stderr.strip()

    def start_recording(
        self,
        kind: str,
        output: Path,
        duration: int,
        camera: MediaDevice | None = None,
        microphone: MediaDevice | None = None,
    ) -> subprocess.Popen:
        if not self.ffmpeg_available:
            raise RuntimeError("ffmpeg is not installed")
        duration = max(1, min(duration, 30 if kind == "video" else 60))
        command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
        if kind == "video":
            if camera is None:
                raise ValueError("a webcam is required")
            command += ["-thread_queue_size", "512", "-f", "v4l2", "-i", camera.source]
            if microphone:
                command += [
                    "-thread_queue_size", "512", "-f", microphone.backend,
                    "-i", microphone.source,
                ]
            command += ["-t", str(duration), "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
            if microphone:
                command += ["-c:a", "aac", "-b:a", "96k"]
            command += ["-movflags", "+faststart", str(output)]
        elif kind == "audio":
            if microphone is None:
                raise ValueError("a microphone is required")
            command += [
                "-thread_queue_size", "512", "-f", microphone.backend,
                "-i", microphone.source, "-t", str(duration),
                "-c:a", "libopus", "-b:a", "96k", str(output),
            ]
        else:
            raise ValueError("recording kind must be audio or video")
        return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

    @staticmethod
    def stop_recording(process: subprocess.Popen) -> str:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        stderr = ""
        if process.stderr:
            try:
                stderr = process.stderr.read().strip()
            except OSError:
                pass
        return stderr
