#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
STAGE="$ROOT/build/eduka-konekta_0.0.6_all"
OUTPUT=${1:-"$ROOT/../dist"}

rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" \
    "$STAGE/usr/bin" \
    "$STAGE/usr/lib/python3/dist-packages" \
    "$STAGE/usr/share/eduka-konekta/assets" \
    "$STAGE/usr/share/applications" \
    "$STAGE/usr/share/icons/hicolor/scalable/apps" \
    "$STAGE/usr/share/metainfo" \
    "$STAGE/usr/share/doc/eduka-konekta" \
    "$OUTPUT"

cp "$ROOT/packaging/control" "$STAGE/DEBIAN/control"
cp "$ROOT/packaging/postinst" "$STAGE/DEBIAN/postinst"
cp "$ROOT/packaging/postrm" "$STAGE/DEBIAN/postrm"
chmod 0755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

cp "$ROOT/packaging/launcher" "$STAGE/usr/bin/eduka-konekta"
chmod 0755 "$STAGE/usr/bin/eduka-konekta"
cp -R "$ROOT/src/eduka_konekta" "$STAGE/usr/lib/python3/dist-packages/"
find "$STAGE/usr/lib/python3/dist-packages/eduka_konekta" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$STAGE/usr/lib/python3/dist-packages/eduka_konekta" -type d -exec chmod 0755 {} +
find "$STAGE/usr/lib/python3/dist-packages/eduka_konekta" -type f -exec chmod 0644 {} +

cp "$ROOT/assets/eduka-konekta.svg" "$STAGE/usr/share/eduka-konekta/assets/eduka-konekta.svg"
cp "$ROOT/assets/style.css" "$STAGE/usr/share/eduka-konekta/assets/style.css"
cp "$ROOT/assets/eduka-konekta.svg" "$STAGE/usr/share/icons/hicolor/scalable/apps/tl.edukasaun.EdukaKonekta.svg"
cp "$ROOT/packaging/eduka-konekta.desktop" "$STAGE/usr/share/applications/eduka-konekta.desktop"
cp "$ROOT/packaging/tl.edukasaun.EdukaKonekta.metainfo.xml" "$STAGE/usr/share/metainfo/tl.edukasaun.EdukaKonekta.metainfo.xml"
cp "$ROOT/README.md" "$STAGE/usr/share/doc/eduka-konekta/README.md"
cp "$ROOT/CHANGELOG.md" "$STAGE/usr/share/doc/eduka-konekta/changelog"
cp "$ROOT/LICENSE" "$STAGE/usr/share/doc/eduka-konekta/copyright"

chmod -R go-w "$STAGE"
dpkg-deb --root-owner-group --build "$STAGE" "$OUTPUT/eduka-konekta_0.0.6_all.deb"
