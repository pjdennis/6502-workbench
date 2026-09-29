#!/bin/bash
# usage: build.sh <src.p8> <out_image.bin>   (env: PROG8C jar, default /tmp/prog8c.jar)
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PROG8C="${PROG8C:-/tmp/prog8c.jar}"
SRC="$1"; OUT="$2"; TMP="$(mktemp -d)"
( cd "$HERE" && java -jar "$PROG8C" -target nmos.properties -out "$TMP" "$(realpath "$SRC")" )
base="$(basename "${SRC%.p8}")"
python3 "$HERE/mkimage.py" "$TMP/$base.bin" "$OUT"
rm -rf "$TMP"
echo "wrote $OUT"
