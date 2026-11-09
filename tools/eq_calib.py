"""Map the EQ element (ee=32) of the SysEx read-back onto our CC-side EQ parameters.

For each band and parameter (gain/freq/q) this sets known raw values through the
trusted CC path (server/protocol.py eq_param), reads all 16 parameters of element
32 back by SysEx after every step, and reports which 'pp' moved plus the
CC-value -> SysEx-value table (signed 28-bit data, see param_diff.py).

    python tools/eq_calib.py [--ch 1] [--ee 32]

WARNING: this overwrites the EQ gain/freq/Q of that channel (all four bands) and
leaves the last values set. Use a spare channel or recall a scene afterwards.
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
ap.add_argument("--ee", type=int, default=32, help="EQ element")
ap.add_argument("--settle", type=float, default=0.15)
a = ap.parse_args()

POINTS = {
    "gain": [0, 2048, 4096, 6144, 8192, 10240, 12288, 14336, 16383],   # 14-bit
    "freq": [0, 16, 32, 48, 64, 80, 96, 112, 127],                      # 7-bit
    "q":    [0, 16, 32, 48, 64, 80, 96, 112, 127],
}


def pick(names):
    m = [n for n in names if a.port.lower() in n.lower()]
    if not m:
        sys.exit(f"No port matching '{a.port}'. Found: {names}")
    return m[0]


def signed(data):
    v = 0
    for b in data:
        v = (v << 7) | b
    bits = 7 * len(data)
    return v - (1 << bits) if v >= 1 << (bits - 1) else v


def read_all(inp, out):
    """-> {pp: value} for pp 0..15 of the EQ element"""
    for _ in inp.iter_pending():
        pass
    for pp in range(16):
        out.send(mido.Message("sysex", data=[0x43, 0x30 | a.device, 0x3E, 0x7F, 0x01, a.ee, pp, a.ch - 1]))
        time.sleep(0.006)
    res, end = {}, time.time() + 0.3
    while time.time() < end:
        for m in inp.iter_pending():
            d = m.data if m.type == "sysex" else ()
            if len(d) >= 12 and d[0] == 0x43 and d[1] & 0xF0 == 0x10 and tuple(d[2:5]) == (0x3E, 0x7F, 0x01) \
                    and d[5] == a.ee and d[7] == a.ch - 1:
                res[d[6]] = signed(d[8:])
        time.sleep(0.005)
    return res


with mido.open_input(pick(mido.get_input_names())) as inp, \
        mido.open_output(pick(mido.get_output_names())) as out:
    base = read_all(inp, out)
    print(f"CH{a.ch} element {a.ee}: {len(base)}/16 parameters answered at start: {base}")
    for band in protocol.BANDS:
        for param, points in POINTS.items():
            rows = []
            for v in points:
                for m in protocol.eq_param(a.ch, band, param, v):
                    out.send(m)
                time.sleep(a.settle)
                rows.append((v, read_all(inp, out)))
            moved = [pp for pp in range(16) if len({r.get(pp) for _, r in rows}) > 1]
            print(f"\n== {band} {param}: pp that moved = {moved}")
            for pp in moved:
                print(f"   pp={pp}: " + "  ".join(f"{v}->{r.get(pp)}" for v, r in rows))
