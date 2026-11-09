"""Interactive calibration of the compressor's raw SysEx values against the console display.

For each parameter it writes a raw value (SysEx Parameter Change, proven to work), and you
type what the console's DYNAMICS screen shows for that channel (e.g. "4:1", "-20.0", "120 ms").
Just press Enter to skip a point. Original values are restored at the end. Results are
printed as a table and saved to dyn_calib.json.

    python tools/dyn_calib.py --ch 1 [--ee 31] [--only ratio,release]

Prepare: the console must show the COMPRESSOR page of that channel (comp type selected).
Use a spare channel. Stop the server first (it owns the MIDI port).
"""
import argparse
import json
import sys
import time
import mido

ap = argparse.ArgumentParser()
ap.add_argument("--port", default="01V96")
ap.add_argument("--device", type=int, default=0)
ap.add_argument("--ch", type=int, default=1)
ap.add_argument("--ee", type=int, default=31)
ap.add_argument("--only", default="", help="comma list of parameter names to calibrate")
a = ap.parse_args()

# name, pp, raw values to visit
STEPS = [
    ("ratio", 6, list(range(16))),
    ("knee", 8, list(range(6))),
    ("attack", 4, [0, 1, 5, 10, 30, 60, 90, 120]),
    ("release", 5, [0, 10, 20, 40, 60, 80, 100, 120, 140, 159]),
    ("threshold", 9, [-540, -400, -270, -100, 0]),
    ("gain", 7, [0, 45, 90, 135, 180]),
]
only = {s for s in a.only.split(",") if s}


def pick(names):
    m = [n for n in names if a.port.lower() in n.lower()]
    if not m:
        sys.exit(f"No port matching '{a.port}'. Found: {names}")
    return m[0]


def enc(v):
    v &= (1 << 28) - 1
    return [(v >> 21) & 0x7F, (v >> 14) & 0x7F, (v >> 7) & 0x7F, v & 0x7F]


def dec(data):
    v = 0
    for b in data:
        v = (v << 7) | b
    return v - (1 << (7 * len(data))) if v >= 1 << (7 * len(data) - 1) else v


def read(inp, out, pp):
    for _ in inp.iter_pending():
        pass
    out.send(mido.Message("sysex", data=[0x43, 0x30 | a.device, 0x3E, 0x7F, 0x01, a.ee, pp, a.ch - 1]))
    end = time.time() + 0.5
    while time.time() < end:
        for m in inp.iter_pending():
            d = m.data if m.type == "sysex" else ()
            if len(d) >= 12 and d[0] == 0x43 and d[1] & 0xF0 == 0x10 and tuple(d[2:5]) == (0x3E, 0x7F, 0x01) \
                    and d[5] == a.ee and d[6] == pp and d[7] == a.ch - 1:
                return dec(d[8:])
        time.sleep(0.005)
    return None


def write(out, pp, v):
    out.send(mido.Message("sysex", data=[0x43, 0x10 | a.device, 0x3E, 0x7F, 0x01, a.ee, pp, a.ch - 1] + enc(v)))


results = {}
with mido.open_input(pick(mido.get_input_names())) as inp, \
        mido.open_output(pick(mido.get_output_names())) as out:
    orig = {pp: read(inp, out, pp) for _, pp, _ in STEPS}
    print("original values:", orig)
    try:
        for name, pp, values in STEPS:
            if only and name not in only:
                continue
            print(f"\n=== {name} (pp={pp}) ===")
            results[name] = []
            for v in values:
                write(out, pp, v)
                time.sleep(0.25)
                back = read(inp, out, pp)
                shown = input(f"  raw {v:5d} (console reports {back}) -> display shows: ").strip()
                if shown:
                    results[name].append((v, shown))
    except (KeyboardInterrupt, EOFError):
        print("\ninterrupted")
    finally:
        for _, pp, _ in STEPS:
            if orig.get(pp) is not None:
                write(out, pp, orig[pp])
                time.sleep(0.05)
        print("\noriginal values restored:", {pp: read(inp, out, pp) for _, pp, _ in STEPS})

print("\n==== RESULT ====")
for name, rows in results.items():
    print(f"{name}: " + ", ".join(f"{v}={s}" for v, s in rows))
with open("dyn_calib.json", "w") as f:
    json.dump(results, f, indent=1)
print("saved dyn_calib.json")
