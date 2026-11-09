"""Discover the 01V96 'Remote meter' address map.

Sends the Remote Meter request (PDF 2.8.3.24):
    F0 43 3n 3E 0D 21 UL LU LL CH CL F7
and prints the meter values (14-bit, H/L pairs) the console streams back
(F0 43 1n 3E 0D 21 UL LU LL <H L>... F7). The request lasts 10 s, so it is repeated.

Usage (on the Pi, in the venv):
    python tools/meter_probe.py [port-substring] [start-address] [count] [device-number]
    python tools/meter_probe.py 01V96 0 128 0

Console: MIDI setup -> Parameter Change RX ON, Rx channel = device-number + 1.
Then feed a signal into ONE input at a time and watch which index lights up.
Try different start addresses (0, 128, 256, ...) if nothing moves.
"""
import sys
import time
import mido

want = (sys.argv[1] if len(sys.argv) > 1 else "01V96").lower()
start = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0
count = int(sys.argv[3], 0) if len(sys.argv) > 3 else 128
dev = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0
watch = int(sys.argv[5], 0) if len(sys.argv) > 5 else None   # print only this address' peak/second


def pick(names):
    m = [n for n in names if want in n.lower()]
    if not m:
        sys.exit(f"No port matching '{want}'. Found: {names}")
    return m[0]


def request():
    ul, lu, ll = (start >> 14) & 0x7F, (start >> 7) & 0x7F, start & 0x7F
    return mido.Message("sysex", data=[0x43, 0x30 | dev, 0x3E, 0x0D, 0x21,
                                       ul, lu, ll, (count >> 7) & 0x7F, count & 0x7F])


with mido.open_input(pick(mido.get_input_names())) as inp, \
        mido.open_output(pick(mido.get_output_names())) as out:
    print(f"start=0x{start:X} count={count} device={dev}. Ctrl+C to stop.")
    next_req, last_print, peak = 0, 0, {}
    seen = {"all": 0, "raw": 0}
    hist = []
    last_status = time.time()
    while True:
        now = time.time()
        if now >= next_req:
            out.send(request())
            next_req = now + 8
        for msg in inp.iter_pending():
            seen["all"] += 1
            if msg.type != "active_sensing" and seen["raw"] < 15:
                seen["raw"] += 1
                print("RX raw:", msg.hex())
            d = msg.data if msg.type == "sysex" else ()
            if len(d) > 8 and d[0] == 0x43 and d[1] & 0xF0 == 0x10 and d[2:5] == (0x3E, 0x0D, 0x21):
                base = (d[5] << 14) | (d[6] << 7) | d[7]
                vals = d[8:]
                if seen.setdefault("meter_raw", 0) < 4:
                    seen["meter_raw"] += 1
                    print(f"METER MSG addr=0x{base:X} bytes={len(vals)}:", " ".join(f"{b:02X}" for b in d))
                for i in range(0, len(vals) - 1, 2):
                    v = (vals[i] << 7) | vals[i + 1]
                    idx = base + i // 2
                    peak[idx] = max(peak.get(idx, 0), v)
        if now - last_status > 3 and not peak:
            last_status = now
            print(f"...no meter data yet (any MIDI received so far: {seen['all']}). "
                  "Check Parameter Change RX/port/channel on the console.")
        if now - last_print > 1.0 and peak:
            last_print = now
            if watch is not None:
                hist.append(peak.get(watch, 0))
                hist[:] = hist[-5:]
                print(f"addr {watch}: peak raw = {hist[-1]:5d}   "
                      f"avg(last {len(hist)}s) = {sum(hist)//len(hist):5d}   max = {max(hist):5d}")
                peak = {}
                continue
            live = {k: v for k, v in sorted(peak.items()) if v > 0}
            print(f"{len(peak)} meters seen; non-zero peaks (addr:value): {live}")
            peak = {}
        time.sleep(0.005)
