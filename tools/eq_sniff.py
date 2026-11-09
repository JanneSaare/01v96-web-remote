"""Print what the console sends when you turn EQ knobs, decoded with the server's
own tables. Use it to calibrate raw values against what the console displays.

Usage (on the Pi, web server stopped):
    ./venv/bin/python tools/eq_sniff.py [port-substring]
Console: Control Change TX = ON (same as for fader feedback), then turn the EQ
knobs on a channel and note the console's display next to each printed line.
Raw units: gain 0..16383 (14-bit), freq 0..127, q 0..127.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mido
from server import protocol

want = (sys.argv[1] if len(sys.argv) > 1 else "01V96").lower()
names = [n for n in mido.get_input_names() if want in n.lower()]
if not names:
    sys.exit(f"No MIDI input matching '{want}'. Found: {mido.get_input_names()}")
dec = protocol.Decoder()
print("Listening on", names[0], "- Ctrl+C to stop")
last = None
with mido.open_input(names[0]) as port:
    for msg in port:
        for ev in dec.feed(msg):
            kind, ch, val = ev
            if kind == "eq":
                band, param, v = val
                extra = ""
                if param == "gain":
                    extra = f"  ({v - 8192:+d} from mid 8192)"
                line = f"CH{ch} {band:5s} {param:4s} raw={v}{extra}"
            elif kind == "eqflag":
                line = f"CH{ch} {val[0].upper()} {'ON' if val[1] else 'OFF'}"
            else:
                line = f"{kind} CH{ch} {val}"
            if line != last:
                print(line)
                last = line
