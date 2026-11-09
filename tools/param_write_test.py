"""Test whether the console accepts a SysEx Parameter Change (write) and echoes it back.

Frame (same as the reply we already read): F0 43 1n 3E 7F 01 ee pp cc <4 data bytes> F7
(data = signed 28-bit, 7 bits per byte, big endian; cc = channel - 1; n = device number = console Rx CH - 1).

It reads the current value, writes a new one, reads it back, then restores the original.
Default target: LOW EQ frequency (ee=32 pp=2) on the given channel - harmless, but use a spare channel.

    python tools/param_write_test.py --ch 1 [--ee 32 --pp 2 --value 60]

Console: Parameter Change RX ON, Rx CH = device + 1. Stop the server first (it owns the MIDI port).
Watch the console's display too: the value should change on screen.
"""
import argparse
import sys
import time
import mido

ap = argparse.ArgumentParser()
ap.add_argument("--port", default="01V96")
ap.add_argument("--device", type=int, default=0)
ap.add_argument("--ch", type=int, default=1)
ap.add_argument("--ee", type=int, default=32)
ap.add_argument("--pp", type=int, default=2)
ap.add_argument("--value", type=int, default=60, help="new value (raw SysEx units)")
ap.add_argument("--hold", type=float, default=2.0, help="seconds to leave the new value (look at the console)")
a = ap.parse_args()


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


def read(inp, out):
    for _ in inp.iter_pending():
        pass
    out.send(mido.Message("sysex", data=[0x43, 0x30 | a.device, 0x3E, 0x7F, 0x01, a.ee, a.pp, a.ch - 1]))
    end = time.time() + 0.5
    while time.time() < end:
        for m in inp.iter_pending():
            d = m.data if m.type == "sysex" else ()
            if len(d) >= 12 and d[0] == 0x43 and d[1] & 0xF0 == 0x10 and tuple(d[2:5]) == (0x3E, 0x7F, 0x01) \
                    and d[5] == a.ee and d[6] == a.pp and d[7] == a.ch - 1:
                return dec(d[8:])
        time.sleep(0.005)
    return None


def write(out, v):
    out.send(mido.Message("sysex", data=[0x43, 0x10 | a.device, 0x3E, 0x7F, 0x01, a.ee, a.pp, a.ch - 1] + enc(v)))


with mido.open_input(pick(mido.get_input_names())) as inp, \
        mido.open_output(pick(mido.get_output_names())) as out:
    orig = read(inp, out)
    print(f"CH{a.ch} ee={a.ee} pp={a.pp}: current value {orig}")
    if orig is None:
        sys.exit("No reply to the read request - cannot test safely.")
    write(out, a.value)
    time.sleep(0.3)
    now = read(inp, out)
    print(f"wrote {a.value} -> read back {now}  => {'WRITE WORKS' if now == a.value else 'write NOT accepted (or clipped)'}")
    time.sleep(a.hold)
    write(out, orig)
    time.sleep(0.3)
    print(f"restored to {orig} -> read back {read(inp, out)}")
