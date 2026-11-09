"""Scan a range of 'Remote meter' addresses to find where the console puts the
master/bus/aux meters (the inputs are at 0..39).

For each block we send the request F0 43 3n 3E 0D 21 UL LU LL CH CL F7 and listen
~0.8 s. Output: only blocks that answered with a non-zero value, as address:value.

Usage (on the Pi):  python tools/meter_scan.py [port] [first] [last] [block] [device]
    python tools/meter_scan.py 01V96 0 0x400 16 0
Or scan the upper address bytes (output meters probably live there):
    python tools/meter_scan.py 01V96 groups [UL_MAX=4] [LU_MAX=8] [device]
    -> requests 48 meters at (UL<<14 | LU<<7) for every UL/LU combination.
Before running: send a steady tone through CH1, with CH1 ON, routed to the Stereo
bus and the Stereo master fader up. Keep it constant for the whole scan (~1-2 min).
"""
import sys
import time
import mido

want = (sys.argv[1] if len(sys.argv) > 1 else "01V96").lower()
groups = len(sys.argv) > 2 and sys.argv[2] == "groups"
if groups:
    ul_max = int(sys.argv[3], 0) if len(sys.argv) > 3 else 4
    lu_max = int(sys.argv[4], 0) if len(sys.argv) > 4 else 8
    dev = int(sys.argv[5], 0) if len(sys.argv) > 5 else 0
    block = 48
    starts = [(ul << 14) | (lu << 7) for ul in range(ul_max) for lu in range(lu_max)]
    first, last = starts[0], starts[-1]
else:
    first = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0
    last = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x400
    block = int(sys.argv[4], 0) if len(sys.argv) > 4 else 16
    dev = int(sys.argv[5], 0) if len(sys.argv) > 5 else 0
    starts = list(range(first, last, block))


def pick(names):
    m = [n for n in names if want in n.lower()]
    if not m:
        sys.exit(f"No port matching '{want}'. Found: {names}")
    return m[0]


def request(start, count):
    return mido.Message("sysex", data=[
        0x43, 0x30 | dev, 0x3E, 0x0D, 0x21,
        (start >> 14) & 0x7F, (start >> 7) & 0x7F, start & 0x7F,
        (count >> 7) & 0x7F, count & 0x7F])


def stop():
    # address UL = 0x7F stops all meter transmission (PDF 2.8.3.24)
    return mido.Message("sysex", data=[0x43, 0x30 | dev, 0x3E, 0x0D, 0x21, 0x7F, 0, 0, 0, 0])


with mido.open_input(pick(mido.get_input_names())) as inp, \
        mido.open_output(pick(mido.get_output_names())) as out:
    out.send(stop())
    time.sleep(0.3)
    list(inp.iter_pending())
    print(f"Scanning {len(starts)} blocks of {block} meters, 0x{first:X}..0x{last:X}. Tone on CH1 -> Stereo.")
    for start in starts:
        out.send(request(start, block))
        t_end = time.time() + 0.8
        got = {}
        while time.time() < t_end:
            for msg in inp.iter_pending():
                d = msg.data if msg.type == "sysex" else ()
                if len(d) > 8 and d[0] == 0x43 and d[1] & 0xF0 == 0x10 and tuple(d[2:5]) == (0x3E, 0x0D, 0x21):
                    base = (d[5] << 14) | (d[6] << 7) | d[7]
                    vals = d[8:]
                    for i in range(0, len(vals) - 1, 2):
                        v = (vals[i] << 7) | vals[i + 1]
                        got[base + i // 2] = max(got.get(base + i // 2, 0), v)
            time.sleep(0.005)
        out.send(stop())
        time.sleep(0.05)
        hot = {hex(k): v for k, v in sorted(got.items()) if v > 0}
        if got:
            print(f"0x{start:05X}: {len(got)} meters answered; non-zero: {hot if hot else 'none'}")
        elif not groups:
            print(f"0x{start:05X}: no answer")
    print("done")
