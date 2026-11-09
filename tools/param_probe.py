"""Discover which SysEx Parameter Request addresses the 01V96 answers.

The manual (App. C, 2.8.3.1.3 / 2.8.3.3) gives only the frame, not the addresses:

    Universal/edit buffer:  F0 43 3n 3E 7F 01 ee pp cc F7
    Basic format:           F0 43 3n 3E 0D tt ee pp cc F7
        tt = data type, ee = element no., pp = parameter no., cc = channel no.

The console answers a valid request with a Parameter Change (F0 43 1n 3E ... F7)
holding the current value. This tool sweeps ranges of ee/pp/cc and prints every
reply, so we can find the element/parameter that holds e.g. fader level or ON.

Usage (on the Pi, in the venv, stop the server first - it owns the MIDI port):
    python tools/param_probe.py --model 7F --tt 01 --ee 1-16 --pp 0-8 --cc 0-1
    python tools/param_probe.py --model 0D --tt 01 --ee 1-16 --pp 0-8 --cc 0-1

Then set CH1's fader to a known position on the console and sweep again: the
reply whose data bytes change is the fader. Replies are also appended to
param_probe.jsonl for diffing between runs.

Console: Parameter Change RX + TX ON, Rx CH = device number + 1 (default 1).
Requests are throttled (--wait seconds each); keep ranges small at first.
"""
import argparse
import json
import sys
import time
import mido


def rng(s: str) -> range:
    a, _, b = s.partition("-")
    return range(int(a, 0), int(b or a, 0) + 1)


ap = argparse.ArgumentParser()
ap.add_argument("--port", default="01V96")
ap.add_argument("--device", type=int, default=0, help="device number 0-15")
ap.add_argument("--model", default="7F", help="model byte: 7F (universal/edit buffer) or 0D")
ap.add_argument("--tt", default="01", help="data type byte (hex); with model 7F it is the 'address' byte, 01 = edit buffer")
ap.add_argument("--ee", type=rng, default=rng("1-8"), help="element range, e.g. 1-16; numbers above 127 are sent in the "
                "two-byte form (the manual: 'if ee is 0, ee is expanded to two bytes')")
ap.add_argument("--ext-order", choices=("hl", "lh"), default="hl",
                help="byte order of the two-byte element number after the 0: high-low (default) or low-high")
ap.add_argument("--pp", type=rng, default=rng("0-8"), help="parameter range")
ap.add_argument("--cc", type=rng, default=rng("0-1"), help="channel range (0 = CH1)")
ap.add_argument("--wait", type=float, default=0.03, help="seconds to wait for a reply per request")
ap.add_argument("--out", default="param_probe.jsonl")
a = ap.parse_args()

model, tt = int(a.model, 16), int(a.tt, 16)


def pick(names):
    m = [n for n in names if a.port.lower() in n.lower()]
    if not m:
        sys.exit(f"No port matching '{a.port}'. Found: {names}")
    return m[0]


def is_reply(msg) -> bool:
    d = msg.data if msg.type == "sysex" else ()
    # ignore the remote-meter stream (addr 0x21) which may still be running
    return len(d) > 5 and d[0] == 0x43 and d[1] & 0xF0 == 0x10 and d[2] == 0x3E and not (d[3] == 0x0D and d[4] == 0x21)


total = len(a.ee) * len(a.pp) * len(a.cc)
print(f"model={model:02X} tt={tt:02X} -> {total} requests, ~{total * a.wait:.0f}s")
hits = 0
with mido.open_input(pick(mido.get_input_names())) as inp, \
        mido.open_output(pick(mido.get_output_names())) as out, \
        open(a.out, "a") as log:
    for _ in inp.iter_pending():     # drop anything queued
        pass
    for ee in a.ee:
        for pp in a.pp:
            for cc in a.cc:
                el = [ee] if ee < 128 else ([0, ee >> 7, ee & 0x7F] if a.ext_order == "hl" else [0, ee & 0x7F, ee >> 7])
                out.send(mido.Message("sysex", data=[0x43, 0x30 | a.device, 0x3E, model, tt] + el + [pp, cc]))
                t_end = time.time() + a.wait
                while time.time() < t_end:
                    for msg in inp.iter_pending():
                        if is_reply(msg):
                            hits += 1
                            h = " ".join(f"{b:02X}" for b in msg.data)
                            print(f"ee={ee:3d} pp={pp:3d} cc={cc:3d} -> {h}")
                            log.write(json.dumps({"model": model, "tt": tt, "ee": ee, "pp": pp, "cc": cc,
                                                  "reply": list(msg.data), "t": time.time()}) + "\n")
                    time.sleep(0.002)
print(f"done: {hits} replies of {total} requests")
if not hits:
    print("No replies. Check Parameter Change RX/TX, Rx CH = device+1, try --model 0D / other --tt values.")
