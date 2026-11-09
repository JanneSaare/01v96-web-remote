"""Live monitor: poll a range of SysEx parameters and print every change as it happens.

Turn ONE control at a time on the console and note the console's display next to
the printed raw value. That gives the raw <-> display calibration for each parameter.

    python tools/param_watch.py --ee 31 --ch 1 [--pp 0-15]
    python tools/param_watch.py --ee 33-48 --pp 0-5 --ch 1     # a range of elements at once

Prints the start values, then one line per change:   12.3s  pp=9: -84 -> -239
(with an element range the lines read:               12.3s  ee=35 pp=2: 77 -> 207)
Type a note + Enter at any time to put a marker line in the output (e.g. "thr -20dB").
Stop the server first (it owns the MIDI port). Ctrl+C to stop.
"""
import argparse
import select
import sys
import threading
import time
import mido

ap = argparse.ArgumentParser()
ap.add_argument("--port", default="01V96")
ap.add_argument("--device", type=int, default=0)
ap.add_argument("--ee", default="31", help="element or range, e.g. 31 or 33-48")
ap.add_argument("--ch", type=int, default=1)
ap.add_argument("--pp", default="0-15", help="parameter range, e.g. 0-15")
a = ap.parse_args()


def rng(s):
    lo, _, hi = s.partition("-")
    return range(int(lo), int(hi or lo) + 1)


PPS, EES = rng(a.pp), rng(a.ee)
MULTI = len(EES) > 1


def pick(names):
    m = [n for n in names if a.port.lower() in n.lower()]
    if not m:
        sys.exit(f"No port matching '{a.port}'. Found: {names}")
    return m[0]


def dec(data):
    v = 0
    for b in data:
        v = (v << 7) | b
    return v - (1 << (7 * len(data))) if v >= 1 << (7 * len(data) - 1) else v


notes = []
threading.Thread(target=lambda: [notes.append(l.strip()) for l in sys.stdin], daemon=True).start()

t0 = time.time()
with mido.open_input(pick(mido.get_input_names())) as inp, \
        mido.open_output(pick(mido.get_output_names())) as out:
    last = {}
    print(f"watching ee={a.ee} pp={a.pp} CH{a.ch}; Ctrl+C to stop")
    while True:
        for _ in inp.iter_pending():
            pass
        for ee in EES:
            for pp in PPS:
                out.send(mido.Message("sysex", data=[0x43, 0x30 | a.device, 0x3E, 0x7F, 0x01, ee, pp, a.ch - 1]))
                time.sleep(0.006)
        end, got = time.time() + 0.12, {}
        while time.time() < end:
            for m in inp.iter_pending():
                d = m.data if m.type == "sysex" else ()
                if len(d) >= 12 and d[0] == 0x43 and d[1] & 0xF0 == 0x10 and tuple(d[2:5]) == (0x3E, 0x7F, 0x01) \
                        and d[5] in EES and d[7] == a.ch - 1:
                    got[(d[5], d[6])] = dec(d[8:])
            time.sleep(0.003)
        t = f"{time.time() - t0:7.1f}s"
        if not last:
            print(f"{t}  start: " + (str({f'{e}.{p}': v for (e, p), v in sorted(got.items())}) if MULTI
                                      else str({p: v for (e, p), v in sorted(got.items())})))
        else:
            for key in sorted(got):
                if last.get(key) != got[key]:
                    ee, pp = key
                    print(f"{t}  " + (f"ee={ee} " if MULTI else "") + f"pp={pp}: {last.get(key)} -> {got[key]}")
        last.update(got)
        while notes:
            print(f"{t}  ---- {notes.pop(0)}")
