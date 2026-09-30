# Eduka-Konekta 0.0.6 Alpha

Eduka-Konekta is a lightweight GTK school messenger. It communicates directly between computers over IP without a central chat server and accepts peers whose profile uses the same school name.

## Patch 0.0.6

- Automatic discovery now uses every active IPv4 Ethernet, Wi-Fi, and other normal network interface.
- Discovery combines multicast, each interface broadcast address, global broadcast, the operating-system neighbor table, remembered peer addresses, and a bounded local-subnet TCP probe.
- The **Refresh Online** button immediately repeats all discovery methods.
- The online directory is separated into **Students Online** and **Teachers Online**.
- Text messages can be edited or deleted by their sender for 30 minutes after sending.
- Images, video, audio, and documents can be replaced or deleted by their sender during the same 30-minute window.
- Documents and arbitrary file formats can be sent up to 25 MiB, including Word, Excel, PowerPoint, PDF, and ODT files.
- Status creation is a single simple composer: optional text, optional emotion, or an image from a local folder/USB drive.
- Current statuses from teachers and students appear in a horizontally scrollable school feed above the conversation.
- **Connect IP** and **Camera & Microphone** were moved from the main toolbar into the **Connection** menu.
- An explicit **Logout** action was added. Closing the window retains the active profile for the next launch; Logout removes it and returns to login.
- Chat messages, received files, status, groups, and grades are still temporary and are erased when the application closes.
- The blue GTK interface retains restrained gradients, bevels, borders, and shadows for a light three-dimensional appearance.
- International English, Portuguese (Portugal), Portuguese (Brazil), Indonesian, and Tetum.

## Login and session privacy

The active profile is stored in the user's configuration directory so an accidental window close does not log out the previous student or teacher. Select **Logout** from the toolbar or **File → Logout** to remove the saved profile and return to login.

Messages, grades, status, groups, recordings, received attachments, and the in-memory history database remain session-only. They are erased when Eduka-Konekta closes normally. Original files selected from a drive or USB device are never deleted.

The persistent `EK-...` Ed25519 device key also remains in the configuration directory so the signed device ID stays stable. Abrupt power loss or an operating-system crash may leave an operating-system temporary directory until normal temporary-file cleanup runs.

## File and media limits

- Profile photo: maximum 2 MiB and optional.
- Chat/status image: maximum 10 MiB.
- Chat video: maximum 25 MiB and 30 seconds.
- Chat voice/audio: maximum 10 MiB and 60 seconds.
- Document or other file: maximum 25 MiB.
- Status types: text, emotion, or image only. Video and music status are not accepted.

`ffprobe` from FFmpeg checks audio and video duration. A received file is validated again before it is made available to open.

## Install on Debian 13 / Edukasaun OS

Use APT so required dependencies are downloaded and installed automatically:

```bash
sudo apt install ./eduka-konekta_0.0.6_all.deb
```

Dependencies include GTK 3, Python GObject, Python Cryptography, FFmpeg, iproute2, v4l-utils, and pulseaudio-utils. APT downloads these automatically. Do not use `dpkg -i` alone on a new system because `dpkg` does not download missing dependencies.

Launch the application from the Network or Education menu, or run:

```bash
eduka-konekta
```

## School network behavior

Eduka-Konekta listens on TCP port **45901** and discovers peers on UDP port **45900** using multicast group **239.192.45.90**. Version 0.0.6 sends discovery from each active interface and actively checks a bounded set of addresses from the local subnet, neighbor table, and previously discovered peers. This works with Ethernet or Wi-Fi; both devices do not need to use the same connection technology.

Two devices still need IP reachability. Guest Wi-Fi client isolation, host firewalls, or routers that block traffic between VLANs cannot be bypassed by a serverless application. For separate campus VLANs/subnets, the network administrator must permit TCP 45901 and relay or route UDP 45900 multicast/broadcast. Manual **Connect IP** remains under the **Connection** menu for reachable routed addresses.

Peers with a different normalized school name are rejected. There is no cloud account, offline-message server, internet directory, or central data store.

## Message controls

The sender can edit a text message, replace an attached file, or delete their sent message for 30 minutes. Each action is signed and propagated to the same public room, group, or direct recipient. Controls disappear when the time window expires. Because there is no central server, an offline recipient cannot receive an edit/delete action that occurred while disconnected.

## Identity and safety

Messages and presence data are signed with a persistent Ed25519 device identity. This detects changes in transit and proves continuity of the same device key. It does not legally prove a person's name, role, school membership, or age. Profile pictures are decorative and may be any image.

Version 0.0.6 does not provide end-to-end content encryption, so it must be used only on a trusted school network. A production release should add school-admin signed enrollment codes, account revocation, moderation, encrypted rooms, and audited grade controls.

## Camera, microphone, and file access

The **Connection → Camera & Microphone** panel shows detected V4L2 webcams and PulseAudio/PipeWire or ALSA microphone inputs. Composer buttons provide separate actions for local files and new webcam/microphone capture. Linux desktop permissions and device rules control access; Eduka-Konekta does not bypass denied permissions.

The GTK chooser exposes local folders and mounted drives. A USB device must first be mounted by the desktop or administrator.

## Build and test

```bash
./build-deb.sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Developer

Hugo Moniz do Rego  
STI – Digitalização & Mídia – MCAS & Grupo IDEA  
[edukasaunos.tl](https://edukasaunos.tl)
