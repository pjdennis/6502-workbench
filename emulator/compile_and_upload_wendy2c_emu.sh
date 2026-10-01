#!/bin/sh
# Emulator-side equivalent of tools/upload/compile_and_upload_wendy.sh.
#
# Assembles the given .s source with vasm6502_oldstyle, frames the
# resulting binary (length + payload + BSD checksum), and streams it
# over the running emulator's --serial-link Unix socket. The on-target
# boot ROM verifies the checksum and jumps to $4000.
#
# Assumes the emulator is already running, e.g. via:
#   wendy2c_emu_serve.sh --live    # or --web
# in another terminal.
#
# Usage:
#   compile_and_upload_wendy2c_emu.sh source.s [--sock PATH]
#                                              [--baud N]
#                                              [--reset-ns N]
#                                              [--post-reset-ns N]
#                                              [--inter-byte-ns N]
#                                              [-v|--verbose]
#
#   --sock PATH         Emulator's --serial-link socket
#                       (default /tmp/wendy2c-link.sock, matching
#                       wendy2c_emu_serve.sh's default).
#   --baud N            Wire baud (default 230400 -- see
#                       wendy2c_emu_upload.py docstring for why this
#                       is 2x the real-hardware rate).
#   --reset-ns N        Reset hold (ns; default 1_000_000 = 1 ms).
#   --post-reset-ns N   Post-reset emulated-time pad in ns (default
#                       50_000_000 = 50 ms; gives the boot ROM time
#                       to reach its CB2-wait state).
#   --inter-byte-ns N   Optional gap between bytes (default 0).
#   -v, --verbose       Echo each stage.
#
# Requires:
#   - vasm6502_oldstyle on PATH
#   - python3 on PATH
#   - wendy2c_emu_serve.sh (or equivalent) already running

set -e

SRC=""
SOCK="/tmp/wendy2c-link.sock"
BAUD=""
RESET_NS=""
POST_RESET_NS=""
INTER_BYTE_NS=""
VERBOSE=0

while [ $# -gt 0 ]; do
    case $1 in
        --sock)
            if [ $# -lt 2 ]; then echo "error: --sock requires a path" >&2; exit 1; fi
            SOCK=$2; shift 2 ;;
        --baud)
            if [ $# -lt 2 ]; then echo "error: --baud requires a value" >&2; exit 1; fi
            BAUD=$2; shift 2 ;;
        --reset-ns)
            if [ $# -lt 2 ]; then echo "error: --reset-ns requires a value" >&2; exit 1; fi
            RESET_NS=$2; shift 2 ;;
        --post-reset-ns)
            if [ $# -lt 2 ]; then echo "error: --post-reset-ns requires a value" >&2; exit 1; fi
            POST_RESET_NS=$2; shift 2 ;;
        --inter-byte-ns)
            if [ $# -lt 2 ]; then echo "error: --inter-byte-ns requires a value" >&2; exit 1; fi
            INTER_BYTE_NS=$2; shift 2 ;;
        -v|--verbose) VERBOSE=1; shift ;;
        -h|--help)
            awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"
            exit 0 ;;
        --) shift; break ;;
        -*)
            echo "error: unknown option '$1' (try --help)" >&2; exit 1 ;;
        *)
            if [ -n "$SRC" ]; then
                echo "error: extra positional arg '$1'" >&2; exit 1
            fi
            SRC=$1; shift ;;
    esac
done

if [ -z "$SRC" ]; then
    echo "error: missing source file (try --help)" >&2
    exit 1
fi
if [ ! -f "$SRC" ]; then
    echo "error: source not found: $SRC" >&2
    exit 1
fi
if [ ! -S "$SOCK" ]; then
    echo "error: emulator socket not listening at $SOCK" >&2
    echo "       start it first with wendy2c_emu_serve.sh" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UPLOAD_PY="$SCRIPT_DIR/wendy2c_emu_upload.py"
if [ ! -f "$UPLOAD_PY" ]; then
    echo "error: $UPLOAD_PY not found" >&2
    exit 1
fi

VASM=vasm6502_oldstyle
command -v "$VASM" >/dev/null 2>&1 || {
    echo "error: $VASM not on PATH" >&2; exit 1
}

OUT_DIR="${OUT_DIR:-/tmp/wendy2c-emu-build}"
mkdir -p "$OUT_DIR"

base=$(basename "$SRC" .s)
bin="$OUT_DIR/${base}.bin"
log="$OUT_DIR/${base}.vasm.log"

[ "$VERBOSE" -eq 1 ] && echo ">> assembling $SRC -> $bin"
if ! "$SCRIPT_DIR/../firmware/vasm" -wdc02 -wfail -Fbin -dotdir -ignore-mult-inc -esc \
        -o "$bin" "$SRC" >"$log" 2>&1; then
    echo "error: vasm failed assembling $SRC (full log: $log):" >&2
    cat "$log" >&2
    exit 1
fi
[ "$VERBOSE" -eq 1 ] && tail -3 "$log"

set -- "$SOCK" "$bin"
[ -n "$BAUD" ]            && set -- "$@" --baud "$BAUD"
[ -n "$RESET_NS" ]        && set -- "$@" --reset-ns "$RESET_NS"
[ -n "$POST_RESET_NS" ]   && set -- "$@" --post-reset-ns "$POST_RESET_NS"
[ -n "$INTER_BYTE_NS" ]   && set -- "$@" --inter-byte-ns "$INTER_BYTE_NS"
[ "$VERBOSE" -eq 1 ]      && set -- "$@" -v

[ "$VERBOSE" -eq 1 ] && echo ">> uploading $bin to $SOCK"
exec python3 "$UPLOAD_PY" "$@"
