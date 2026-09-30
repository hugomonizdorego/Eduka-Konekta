Eduka-Konekta (0.1.0 Alpha) — 2026-09-30

- Fixed peers not being found over Wi-Fi while LAN cable worked: Wi-Fi friendly
  non-blocking subnet sweep (1.5 s timeout, up to 1024 hosts on large Wi-Fi
  networks), interfaces re-read every 12 s so late Wi-Fi connections and DHCP
  changes are announced, unicast UDP discovery with replies, and multicast
  re-joined on new interfaces.
- Added signed presence heartbeats, TCP keep-alive and dead-link detection so
  peers reconnect after Wi-Fi sleep or roaming.
- Added automatic one-hop relay through any mutually reachable peer, which
  bridges access-point client isolation; relayed users are marked in the list.
- Added per-connection writer queues and relay only to peers the sender cannot
  reach, removing duplicate floods on Wi-Fi.
- Added firewalld service and ufw profile; the installer opens TCP 45901 and
  UDP 45900 when a firewall is active.
- Added Exams & Assignments: question editor (multiple choice with automatic
  grading, essay), question files, class/all/selected targets, time limits,
  late marking, exam mode chat lock, answer files, store-and-forward delivery
  with receipts, review and grading dialog, results returned to students, CSV
  export and bulk answer-file export. Records persist on disk.
- Added one-click attendance with CSV export.
- Added school usage rules (accepted at sign-in), teacher-published school
  rules, teacher room locks, offensive-word filter and anti-spam rate limit.
- Redesigned the interface: navigation rail, top bar, room descriptions and
  unread counters, people search, initials avatars, toasts, network
  diagnostics page and settings page (language, large text, notifications,
  word filter).
- Rewrote the translation catalog so every string exists in Indonesian, Tetun,
  Portuguese (Portugal and Brazil) and English, with tests that enforce it.
- The logo no longer crashes the application when no SVG loader is installed;
  librsvg2-common is now a dependency.

Eduka-Konekta (0.0.6 Alpha) — 2026-09-04

- Expanded automatic discovery to all active Ethernet, Wi-Fi, and other IPv4
  interfaces using multicast, per-interface/global broadcast, the neighbor
  table, remembered peer IPs, and bounded local-subnet TCP probing.
- Added manual Refresh Online and split the directory into Students Online and
  Teachers Online.
- Added signed text edit and message deletion for the first 30 minutes.
- Added signed replacement/deletion for sent images, video, audio, and files
  during the same 30-minute window.
- Added arbitrary document/file transfer up to 25 MiB, including Word, Excel,
  PowerPoint, PDF, and ODT formats.
- Rebuilt status as a simple text/emotion/image composer with a school status
  feed for student and teacher updates.
- Moved manual Connect IP and device detection into the Connection menu.
- Added explicit Logout and persistent active-profile restore after an
  accidental close; chat/session data remains ephemeral.
- Added light 3D styling for the new status cards, online sections, refresh,
  and message action controls.

Eduka-Konekta (0.0.5 Alpha) — 2026-09-04

- Added a restrained three-dimensional GTK design using light gradients,
  borders, inset highlights, and soft shadows.
- Removed music and video status. Status now accepts only text, emotion, image,
  or the clear-status event, with validation at the network boundary.
- Added image status selection from local folders and mounted USB drives.
- Replaced every remaining native/portal media picker with the standard GTK
  file chooser for image, video, voice/audio, and status-image uploads.
- Added V4L2 webcam and PulseAudio/PipeWire or ALSA microphone detection.
- Added webcam photo capture, voice recording up to 60 seconds, and webcam
  video recording up to 30 seconds through FFmpeg.
- Added desktop and in-app notifications for incoming chat, new friend status,
  newly online friends, online teachers, broadcasts, and group invitations.
- Added exact validation of received media after decoding and before display.
- Added v4l-utils and pulseaudio-utils as APT-managed dependencies.

Eduka-Konekta (0.0.4 Alpha) — 2026-07-21

- Replaced Gtk.FileChooserNative with a standard GTK file chooser dialog for
  better compatibility on Debian, LXQt, X11, and systems without a portal.
- Added Skip Photo on the login page.
- Made profile pictures fully optional and added the default avatar fallback.
- Users can continue logging in even when a drive or USB picture cannot open.

Eduka-Konekta (0.0.3 Alpha) — 2026-07-21

- Removed the real-person photo requirement and ownership confirmation.
- Profile picture may now be any supported image selected from a local drive
  or a mounted USB device through the GTK file chooser.
- Retained image validation and the 2 MiB safety limit.

Eduka-Konekta (0.0.2 Alpha) — 2026-07-21

- Added required real-photo profile selection with user ownership confirmation.
- Added teacher subject/course field shown only for teacher accounts.
- Added automatic IPv4 detection plus multicast and interface-broadcast discovery.
- Restricted peer acceptance to profiles using the same school name.
- Added clickable online-user list and targeted direct school chat.
- Added ephemeral text, mood, one-minute music, and 30-second video status.
- Added teacher-created session groups with selected online students and teachers.
- Added teacher broadcasts and private exam-grade delivery to selected students.
- Moved profiles, history, received media, statuses, groups, and grades to an
  ephemeral session that is erased when the application closes.
- Added iproute2 as a managed Debian dependency.

Eduka-Konekta (0.0.1 Alpha) — 2026-07-21

- Initial GTK desktop interface and original Eduka-Konekta branding.
- Added multilingual profile login without passwords.
- Added persistent signed device identities.
- Added multicast LAN discovery and manual IP connections.
- Added group rooms without private messaging.
- Added text, links, emoji, images, 30-second video, and 60-second audio.
- Added local SQLite history, received-file storage, and About information.
