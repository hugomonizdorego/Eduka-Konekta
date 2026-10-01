#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
VERSION=$(sed -n 's/^Version: //p' "$ROOT/packaging/control")
STAGE="$ROOT/build/eduka-konekta_${VERSION}_all"
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
    "$STAGE/usr/lib/firewalld/services" \
    "$STAGE/etc/ufw/applications.d" \
    "$OUTPUT"

cp "$ROOT/packaging/control" "$STAGE/DEBIAN/control"
cp "$ROOT/packaging/postinst" "$STAGE/DEBIAN/postinst"
cp "$ROOT/packaging/postrm" "$STAGE/DEBIAN/postrm"
chmod 0755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"
echo "/etc/ufw/applications.d/eduka-konekta" > "$STAGE/DEBIAN/conffiles"

cp "$ROOT/packaging/launcher" "$STAGE/usr/bin/eduka-konekta"
chmod 0755 "$STAGE/usr/bin/eduka-konekta"
cp -R "$ROOT/src/eduka_konekta" "$STAGE/usr/lib/python3/dist-packages/"
find "$STAGE/usr/lib/python3/dist-packages/eduka_konekta" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$STAGE/usr/lib/python3/dist-packages/eduka_konekta" -type d -exec chmod 0755 {} +
find "$STAGE/usr/lib/python3/dist-packages/eduka_konekta" -type f -exec chmod 0644 {} +

cp "$ROOT"/assets/*.svg "$ROOT"/assets/*.css "$STAGE/usr/share/eduka-konekta/assets/"
cp "$ROOT/assets/eduka-konekta.svg" "$STAGE/usr/share/icons/hicolor/scalable/apps/tl.edukasaun.EdukaKonekta.svg"
for size in 16 24 32 48 64 128 256 512; do
    mkdir -p "$STAGE/usr/share/icons/hicolor/${size}x${size}/apps"
    cp "$ROOT/assets/icons/eduka-konekta-$size.png" "$STAGE/usr/share/icons/hicolor/${size}x${size}/apps/tl.edukasaun.EdukaKonekta.png"
done
mkdir -p "$STAGE/usr/share/pixmaps"
cp "$ROOT/assets/icons/eduka-konekta-128.png" "$STAGE/usr/share/pixmaps/tl.edukasaun.EdukaKonekta.png"
cp "$ROOT/packaging/eduka-konekta.desktop" "$STAGE/usr/share/applications/eduka-konekta.desktop"
cp "$ROOT/packaging/tl.edukasaun.EdukaKonekta.metainfo.xml" "$STAGE/usr/share/metainfo/tl.edukasaun.EdukaKonekta.metainfo.xml"
cp "$ROOT/packaging/firewall/eduka-konekta.xml" "$STAGE/usr/lib/firewalld/services/eduka-konekta.xml"
cp "$ROOT/packaging/firewall/eduka-konekta.ufw" "$STAGE/etc/ufw/applications.d/eduka-konekta"
cp "$ROOT/README.md" "$STAGE/usr/share/doc/eduka-konekta/README.md"
cp "$ROOT/CHANGELOG.md" "$STAGE/usr/share/doc/eduka-konekta/changelog"
cp "$ROOT/LICENSE" "$STAGE/usr/share/doc/eduka-konekta/copyright"

chmod -R go-w "$STAGE"
find "$STAGE" -type f -exec chmod u+rw,go+r {} +
INSTALLED_SIZE=$(du -sk --exclude=DEBIAN "$STAGE" | cut -f1)
sed -i "/^Installed-Size:/d" "$STAGE/DEBIAN/control"
echo "Installed-Size: $INSTALLED_SIZE" >> "$STAGE/DEBIAN/control"
(cd "$STAGE" && find . -type f ! -path "./DEBIAN/*" -printf '%P\0' | sort -z | xargs -0 md5sum > DEBIAN/md5sums)
dpkg-deb --root-owner-group --build "$STAGE" "$OUTPUT/eduka-konekta_${VERSION}_all.deb"
