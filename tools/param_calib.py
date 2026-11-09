"""Calibrate a SysEx parameter against the CC fader scale we already trust.

Moves ONE input fader through known positions via the working CC path
(server/protocol.py, 0..1023, 860 = 0 dB), and after each move asks the console
for the SysEx value of the given element and prints the pair.

    python tools/param_calib.py [--ch 1] [--ee 28] [--pp 0]

WARNING: this moves the fader of that channel and leaves it at the last
position (reset it by hand). Make sure nothing live depends on it.
Stop the server first (it owns the MIDI port).
"""
import argparse
import os
import sys
import time
import mido

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from server import protocol  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--port", default="01V96")
ap.add_argument("--device", type=int, default=0)
ap.add_argument("--ch", type=int, default=1, help="input channel 1..24")
ap.add_argument("--ee", type=int, default=28, help="element holding the fader (found with param_diff)")
ap.add_argument("--pp", type=int, default=0)
ap.add_argument("--settle", type=float, default=0.4, help="seconds to let the console move")
a = ap.parse_args()
POINTS = [0, 50, 100, 200, 300, 430, 600, 760, 860, 950, 1023]


def pick(names):
    m = [n for n in names if a.port.lower() in n.lower()]
    if not m:
        sys.exit(f"No port matching '{a.port}'. Found: {names}")
    return m[0]


def read(inp, out):
    for _ in inp.iter_pending():
        pass
    out.send(mido.Message("sysex", data=[0x43, 0x30 | a.device, 0x3E, 0x7F, 0x01, a.ee, a.pp, a.ch - 1]))
    end = time.time() + 0.5
    while time.time() < end:
        for m in inp.iter_pending():
            d = m.data if m.type == "sysex" else ()
            if len(d) >= 12 and d[0] == 0x43 and d[1] & 0xF0 == 0x10 and d[2:6] == (0x3E, 0x7F, 0x01, a.ee)[0:4] \
                    and d[5] == a.ee and d[6] == a.pp and d[7] == a.ch - 1:
                v = 0
                for b in d[8:]:
                    v = (v << 7) | b
                return v
        time.sleep(0.005)
    return None


with mido.open_input(pick(mido.get_input_names())) as inp, \
        mido.open_output(pick(mido.get_output_names())) as out:
    start = read(inp, out)
    print(f"CH{a.ch} ee={a.ee}: starting sysex value {start}")
    print(" cc_raw(0-1023)  sysex_value")
    for p in POINTS:
        for m in protocol.fader(a.ch, p):
            out.send(m)
        time.sleep(a.settle)
        print(f"{p:10d}  {read(inp, out)}")
    print("Note the console's fader stays at the last position (1023 = max). Reset it by hand.")
