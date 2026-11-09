"""Live view of several 'Remote meter' blocks, to find which meter belongs to which output.

Streams the given blocks (default: the two 8-meter blocks found by tools/meter_scan.py, 0x4000 and
0x8000, plus the same blocks at the other metering points) and prints, once a second, every meter
that is non-zero or has changed. Press Enter to capture a BASELINE; from then on each line shows
the change in dB against it, so you can do ONE thing on the console and see which cell reacts.
Type a note and press Enter to put a marker line in the output (a bare Enter just re-captures
the baseline).

    python tools/meter_blocks.py [--blocks 0x4000:8,0x8000:8]

Prepare: a steady tone into CH1 (CH1 routed to ST), then e.g. raise CH1's send to AUX1, move the ST
OUT fader, assign CH1 to BUS1, ... one at a time. Stop the web server first (it owns the MIDI port).
Raw 4095 = 0 dB, about 41 steps per dB near the top (the dB shown is that approximation).
"""
import argparse
import sys
import threading
import time
import mido

ap = argparse.ArgumentParser()
ap.add_argument("--port", default="01V96")
ap.add_argument("--device", type=int, default=0)
ap.add_argument("--blocks", default="0x4000:8,0x4080:8,0x4100:8,0x8000:8,0x8080:8,0x8100:8",
                help="comma list of start[:count], e.g. 0x4000:8,0x8000:8")
a = ap.parse_args()
BLOCKS = []
for item in a.blocks.split(","):
    start, _, cnt = item.partition(":")
    BLOCKS.append((int(start, 0), int(cnt or 8, 0)))


def pick(names):
    m = [n for n in names if a.port.lower() in n.lower()]
    if not m:
        sys.exit(f"No port matching '{a.port}'. Found: {names}")
    return m[0]


def request(start, count):
    return mido.Message("sysex", data=[0x43, 0x30 | a.device, 0x3E, 0x0D, 0x21,
                                       (start >> 14) & 0x7F, (start >> 7) & 0x7F, start & 0x7F,
                                       (count >> 7) & 0x7F, count & 0x7F])


def db(raw):
    return (raw - 4095) / 41.0


values, baseline, notes = {}, None, []
threading.Thread(target=lambda: [notes.append(l.strip()) for l in sys.stdin], daemon=True).start()
t0, last_req, last_print = time.time(), 0.0, 0.0
with mido.open_input(pick(mido.get_input_names())) as inp, \
        mido.open_output(pick(mido.get_output_names())) as out:
    print("Blocks:", ", ".join(f"0x{s:X}x{c}" for s, c in BLOCKS), "- Enter = capture baseline, text+Enter = note")
    while True:
        now = time.time()
        if now - last_req > 8:                       # the console stops streaming after 10 s
            for s, c in BLOCKS:
                out.send(request(s, c))
                time.sleep(0.01)
            last_req = now
        for msg in inp.iter_pending():
            d = msg.data if msg.type == "sysex" else ()
            if len(d) > 8 and d[0] == 0x43 and d[1] & 0xF0 == 0x10 and tuple(d[2:5]) == (0x3E, 0x0D, 0x21):
                base = (d[5] << 14) | (d[6] << 7) | d[7]
                vals = d[8:]
                for i in range(0, len(vals) - 1, 2):
                    values[base + i // 2] = (vals[i] << 7) | vals[i + 1]
        while notes:
            n = notes.pop(0)
            if n:
                print(f"{now - t0:7.1f}s  ---- {n}")
            else:
                baseline = dict(values)
                print(f"{now - t0:7.1f}s  ---- baseline captured ({len(baseline)} meters)")
        if now - last_print >= 1.0 and values:
            last_print = now
            for s, c in BLOCKS:
                cells = []
                for i in range(c):
                    v = values.get(s + i)
                    if v is None:
                        continue
                    if baseline is not None:
                        dv = db(v) - db(baseline.get(s + i, v))
                        if abs(dv) >= 0.5:
                            cells.append(f"{i}:{v}({dv:+.1f}dB)")
                    elif v > 0:
                        cells.append(f"{i}:{v}")
                print(f"{now - t0:7.1f}s  0x{s:04X}  " + ("  ".join(cells) if cells else ("." if baseline is not None else "all zero")))
        time.sleep(0.005)
