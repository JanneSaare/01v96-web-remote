"""Compare two param_probe.py result files and show which parameters changed.

    python tools/param_diff.py a.jsonl b.jsonl

Reply layout (verified on the console): 43 1n 3E 7F 01 ee pp cc <4 data bytes>,
the data being 7 bits per byte, big endian, two's complement (EQ gain is negative
for cuts, in 0.1 dB). If a file holds several runs, the last reply per (ee, pp, cc) wins.
"""
import json
import sys


def load(path):
    out = {}
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            data = r["reply"][10:] if r["reply"][5] == 0 else r["reply"][8:]   # two-byte element number: data starts 2 later
            v = 0
            for b in data:
                v = (v << 7) | b
            bits = 7 * len(data)
            if v >= 1 << (bits - 1):      # two's complement (e.g. negative EQ gain)
                v -= 1 << bits
            out[(r["ee"], r["pp"], r["cc"])] = v
    return out


if len(sys.argv) not in (3, 4):
    sys.exit(__doc__ + "\n    python tools/param_diff.py a.jsonl b.jsonl [ELEMENT]   # dump one element in both files")
a, b = load(sys.argv[1]), load(sys.argv[2])
if len(sys.argv) == 4:
    el = int(sys.argv[3], 0)
    for k in sorted(set(a) | set(b)):
        if k[0] == el:
            print(f"ee={k[0]:3d} pp={k[1]:3d} cc={k[2]}  a={a.get(k)}  b={b.get(k)}")
    sys.exit()
changed = [(k, a.get(k), b.get(k)) for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
for (ee, pp, cc), x, y in changed:
    print(f"ee={ee:3d} (0x{ee:02X}) pp={pp:3d} cc={cc}  {x} -> {y}")
print(f"{len(changed)} changed of {len(set(a) | set(b))} parameters")
