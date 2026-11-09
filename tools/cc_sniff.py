"""Print every raw MIDI message the console sends (no decoding with our tables).

Use it to see which CC / SysEx the console really uses for a control, e.g. the
HPF ON button, then compare with what the web UI sends (protocol.py).

    python tools/cc_sniff.py [port-substring]

Console: Control Change TX = ON. Press the control on the console and read the line.
Shows MIDI channel (1-based, as the manual's CHANNELn pages), CC number and value.
Meter and active-sensing traffic is hidden.
Type a note and press Enter at any time to put a marker line in the output
(e.g. "AUX1 master fader"), then move that control.
"""
import sys
import threading
import time
import mido

want = (sys.argv[1] if len(sys.argv) > 1 else "01V96").lower()
names = [n for n in mido.get_input_names() if want in n.lower()]
if not names:
    sys.exit(f"No MIDI input matching '{want}'. Found: {mido.get_input_names()}")
print("Listening on", names[0], "- Ctrl+C to stop")
t0 = time.time()


def _markers():
    for line in sys.stdin:
        print(f"{time.time() - t0:7.2f}s  ---- {line.strip()}", flush=True)


threading.Thread(target=_markers, daemon=True).start()
with mido.open_input(names[0]) as port:
    for msg in port:
        if msg.type == "active_sensing":
            continue
        t = f"{time.time() - t0:7.2f}s"
        if msg.type == "control_change":
            print(f"{t}  CC   page(midi ch)={msg.channel + 1:2d}  cc={msg.control:3d}  value={msg.value:3d}   [{msg.hex()}]")
        elif msg.type == "sysex":
            d = msg.data
            if len(d) > 5 and d[3:5] == (0x0D, 0x21):      # remote meter stream
                continue
            print(f"{t}  SYSEX {' '.join(f'{b:02X}' for b in d)}")
        else:
            print(f"{t}  {msg.type}  {msg.hex()}")
