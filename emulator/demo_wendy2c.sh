#!/bin/sh
# wendy2c emulator end-to-end demo.
#
# Builds the wendy2c boot ROM (upload_and_run_eeprom_wendy2c.s) and a
# small "Hi! I'm Wendy 2." payload (hello_ram_4000_wendy2c.s) using
# vasm, frames the payload with the same length+payload+BSD-checksum
# layout as tools/upload/transfer.py (at 115200 baud), then launches the emulator with
# the boot ROM in the EEPROM and the framed bytes preloaded into the
# serial-USB chip's queue.
#
# The CPU runs the real wendy2c boot code, which negotiates the
# serial protocol with our SERIAL_USB chip, copies the payload into
# RAM at $4000, jumps to it, and then prints to the LCD.
#
# Usage:
#   demo_wendy2c.sh [--live | --web [--web-port N]] [--audio] [--wav PATH]
#
#   --live          Launch the emulator's live ANSI render of the LCD,
#                   LED, button, and VIA pin state. Runs uncapped;
#                   q/ESC/Ctrl-C in the live panel quits. Without this
#                   flag the emulator runs briefly under a cycle cap
#                   and prints the final LCD frame.
#   --web           Launch the embedded HTTP+WebSocket server with a
#                   browser UI on http://127.0.0.1:8080/ (override port
#                   with --web-port). Streams state snapshots and PB7
#                   audio over the WS; click the button or press SPACE
#                   in the browser to drive the control button. Runs
#                   uncapped; Ctrl-C in the terminal stops it.
#                   Mutually exclusive with --live.
#   --web-port N    TCP port for --web (default 8080; 0 picks ephemeral).
#   --web-bind ADDR IPv4 bind address for --web (default 127.0.0.1).
#                   Use 0.0.0.0 to expose to the LAN -- a warning is
#                   printed since anyone on the network can press the
#                   control button and stream the audio.
#   --audio         Play the PB7 piezo line through the host audio
#                   device. On Linux/WSL needs PulseAudio/PipeWire/ALSA;
#                   macOS uses CoreAudio; Windows uses WASAPI. On a host
#                   with no audio backend, miniaudio falls back to its
#                   Null backend (a no-op, with a warning printed).
#                   Pairs naturally with --live but works without it too.
#                   Redundant under --web (the browser plays its own
#                   stream).
#   --wav PATH      Record the piezo line to a WAV file (PCM mono int16
#                   @ 22050 Hz; high-passed to mimic a small piezo).
#                   Works with any of the above.
#
# Env overrides:
#   DEMO_PAYLOAD     path to a wendy2c .s file (default hello_ram_4000)
#   DEMO_CYCLE_CAP   non-live/-web: emulator --cycle-cap (default 3000000)
#                    live/web:      no cap by default; this overrides if set
#
# Requires:
#   - vasm6502_oldstyle on PATH
#   - python3 on PATH
#   - the emulator built (make, from the repository root)
#   - run from the repo root

set -e

LIVE=0
WEB=0
WEB_PORT=8080
WEB_BIND=""
AUDIO=0
WAV=""
LCD_PANEL=""
while [ $# -gt 0 ]; do
    case $1 in
        --live)  LIVE=1; shift ;;
        --web)   WEB=1; shift ;;
        --web-port)
            if [ $# -lt 2 ]; then
                echo "error: --web-port requires a value" >&2; exit 1
            fi
            WEB_PORT=$2; WEB=1; shift 2 ;;
        --web-bind)
            if [ $# -lt 2 ]; then
                echo "error: --web-bind requires a value" >&2; exit 1
            fi
            WEB_BIND=$2; WEB=1; shift 2 ;;
        --audio) AUDIO=1; shift ;;
        --wav)
            if [ $# -lt 2 ]; then
                echo "error: --wav requires a path" >&2; exit 1
            fi
            WAV=$2; shift 2 ;;
        --lcd-panel)
            if [ $# -lt 2 ]; then
                echo "error: --lcd-panel requires a value" >&2; exit 1
            fi
            LCD_PANEL=$2; shift 2 ;;
        -h|--help)
            awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"
            exit 0 ;;
        *)
            echo "error: unknown option '$1' (try --help)" >&2; exit 1 ;;
    esac
done

if [ "$LIVE" -eq 1 ] && [ "$WEB" -eq 1 ]; then
    echo "error: --live and --web are mutually exclusive" >&2; exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${OUT_DIR:-/tmp/wendy2c-demo}"
mkdir -p "$OUT_DIR"

# Default payload is the existing "Hi! I'm Wendy 2." program; override
# via DEMO_PAYLOAD env to point at any other wendy2c .s file that
# assembles to load at $4000.
FW="$REPO_ROOT/firmware"
PAYLOAD_SRC="${DEMO_PAYLOAD:-$FW/programs/wendy2/hello_ram_4000_wendy2c.s}"
# A bare file name is looked up in firmware/programs/wendy2/.
if [ ! -f "$PAYLOAD_SRC" ] && [ -f "$FW/programs/wendy2/$PAYLOAD_SRC" ]; then
    PAYLOAD_SRC="$FW/programs/wendy2/$PAYLOAD_SRC"
fi

VASM=vasm6502_oldstyle
command -v "$VASM" >/dev/null 2>&1 || {
    echo "error: $VASM not on PATH; install from http://sun.hasenbraten.de/vasm/" >&2
    exit 1
}

# Run vasm and fail fast on error. The previous version piped vasm output
# to `tail -5`, which masked vasm's exit status (only `tail`'s status was
# visible to `set -e`), so an option vasm did not recognise -- e.g. older
# vasm releases lacking -ignore-mult-inc -- silently produced no output
# and the emulator then failed with "could not load ROM image".
run_vasm() {
    out=$1
    src=$2
    log="$OUT_DIR/$(basename "$src").vasm.log"
    if ! "$FW/vasm" -wdc02 -wfail -Fbin -dotdir -ignore-mult-inc -esc \
            -o "$out" "$src" >"$log" 2>&1; then
        echo "error: vasm failed assembling $src (full log: $log):" >&2
        cat "$log" >&2
        exit 1
    fi
    tail -5 "$log"
}

cd "$REPO_ROOT"

echo ">> assembling boot ROM (upload_and_run_eeprom_wendy2c.s)"
run_vasm "$OUT_DIR/wendy2c_boot.bin" "$FW/boards/wendy2/upload_and_run_eeprom_wendy2c.s"

echo ">> assembling payload ($PAYLOAD_SRC)"
run_vasm "$OUT_DIR/payload.bin" "$PAYLOAD_SRC"

echo ">> framing payload"
python3 "$REPO_ROOT/emulator/wendy2_upload.py" \
    "$OUT_DIR/payload.bin" -o "$OUT_DIR/payload.framed"

cd "$REPO_ROOT"

# Build common emulator args. POSIX sh doesn't have arrays, but `set --`
# rebuilds the positional parameters and "$@" preserves arg boundaries
# (so a WAV path with spaces survives).
set -- "$OUT_DIR/wendy2c_boot.bin" \
       --machine wendy2c \
       --serial-input "$OUT_DIR/payload.framed"
[ "$AUDIO" -eq 1 ] && set -- "$@" --audio
[ -n "$WAV" ] && set -- "$@" --wav "$WAV"
[ -n "$LCD_PANEL" ] && set -- "$@" --lcd-panel "$LCD_PANEL"

if [ "$WEB" -eq 1 ]; then
    if [ "$WEB_PORT" = "0" ]; then
        echo ">> launching web UI on an ephemeral port"
        echo "   (look for the 'wendy2c-web: listening on ...' line below for the URL;"
        echo "    Ctrl-C here stops the server)"
    else
        echo ">> launching web UI at http://127.0.0.1:${WEB_PORT}/"
        echo "   (open the URL in a browser; Ctrl-C here stops the server)"
    fi
    # Same uncapped-by-default semantics as --live; DEMO_CYCLE_CAP can
    # force a fixed-length recording.
    set -- "$@" --web --web-port "$WEB_PORT"
    [ -n "$WEB_BIND" ] && set -- "$@" --web-bind "$WEB_BIND"
    if [ -n "${DEMO_CYCLE_CAP:-}" ]; then
        set -- "$@" --cycle-cap "$DEMO_CYCLE_CAP"
    fi
    exec ./emulator/emulator.out "$@"
fi

if [ "$LIVE" -eq 1 ]; then
    echo ">> launching live render (q / ESC / Ctrl-C to quit)"
    # In live mode the emulator defaults to no cycle cap, just like the
    # nmos-default --console / --terminal modes. DEMO_CYCLE_CAP can
    # override if you want a recording of fixed length.
    set -- "$@" --live
    if [ -n "${DEMO_CYCLE_CAP:-}" ]; then
        set -- "$@" --cycle-cap "$DEMO_CYCLE_CAP"
    fi
    exec ./emulator/emulator.out "$@"
fi

echo ">> running emulator"
echo "   (the boot ROM displays its 'Ready' screen briefly, then upload"
echo "    starts; on completion the payload writes to the LCD which we"
echo "    print on exit. Ctrl-C to stop early.)"
echo
# Cap is in oscillator ticks (~2 per CPU cycle). ~1.5M is the minimum for
# the payload's LCD frame to appear after the upload; 3M leaves headroom
# while still exiting in well under a second. Override via DEMO_CYCLE_CAP.
exec ./emulator/emulator.out "$@" --cycle-cap "${DEMO_CYCLE_CAP:-3000000}" --exit-report
