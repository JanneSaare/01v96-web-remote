"""Find where the LOW/HIGH band changes type (HPF / shelf / bell, LPF / shelf / bell).

Sweeps one band's Q through the CC path in small steps, slowly, and after each step
prints the SysEx value the console reports for that Q (and any OTHER parameter of
the EQ element that changed, which would reveal a separate type parameter).
Watch the console's EQ display for that channel while it runs and note the raw
values at which the band type/curve changes.

    python tools/eq_type_probe.py --band low  --ch 1 [--start 0 --stop 127 --step 2 --delay 0.5]
    python tools/eq_type_probe.py --band high --ch 1

WARNING: overwrites that band's Q on the channel. Use a spare channel. Stop the
server first (it owns the MIDI port).
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
ap.add_argument("--ch", type=int, default=1)
ap.add_argument("--band", choices=protocol.BANDS, default="low")
ap.add_argument("--start", type=int, default=0)
ap.add_argument("--stop", type=int, default=127)
ap.add_argument("--step", type=int, default=2)
ap.add_argument("--delay", type=float, default=0.5, help="seconds per step (time to look at the display)")
a = ap.parse_args()
Q_PP = protocol.EQ_PP[a.band]["q"]


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
    for _ in inp.iter_pending():
        pass
    for pp in range(16):
        out.send(mido.Message("sysex", data=[0x43, 0x30 | a.device, 0x3E, 0x7F, 0x01,
                                             protocol.SYSEX_EE_EQ, pp, a.ch - 1]))
        time.sleep(0.006)
    res, end = {}, time.time() + 0.25
    while time.time() < end:
        for m in inp.iter_pending():
            d = m.data if m.type == "sysex" else ()
            if len(d) >= 12 and d[0] == 0x43 and d[1] & 0xF0 == 0x10 and tuple(d[2:5]) == (0x3E, 0x7F, 0x01) \
                    and d[5] == protocol.SYSEX_EE_EQ and d[7] == a.ch - 1:
                res[d[6]] = signed(d[8:])
        time.sleep(0.005)
    return res


with mido.open_input(pick(mido.get_input_names())) as inp, \
        mido.open_output(pick(mido.get_output_names())) as out:
    base = read_all(inp, out)
    print(f"{a.band} band, CH{a.ch}: Q is pp={Q_PP}. Start state: {base}")
    print(" raw_cc  sysex_Q  other-pp-changes-vs-start")
    for raw in range(a.start, a.stop + 1, a.step):
        for m in protocol.eq_param(a.ch, a.band, "q", raw):
            out.send(m)
        time.sleep(max(0.0, a.delay - 0.3))
        r = read_all(inp, out)
        other = {pp: v for pp, v in r.items() if pp != Q_PP and v != base.get(pp)}
        print(f"{raw:6d}  {r.get(Q_PP)!s:>7}  {other or ''}")
