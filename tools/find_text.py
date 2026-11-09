"""Find where the console keeps text (channel names etc.) in a param_probe.py scan.

Text is stored one character per parameter number (pp), e.g. a 4-letter name in pp 0..3 of some element.
This lists, for every element, runs of consecutive parameters that read as printable ASCII, and marks the
ones that contain the text you are looking for.

    python tools/find_text.py scan.jsonl [ABCD]

Typical use: name CH1 "ABCD" on the console, then
    python tools/param_probe.py --model 7F --tt 01 --ee 1-127 --pp 0-31 --cc 0 --out names.jsonl
    python tools/find_text.py names.jsonl ABCD
(Re-scan with --cc 1 after naming CH2 "WXYZ" to see how the channel number selects the name.)
"""
import json
import sys

if len(sys.argv) < 2:
    sys.exit(__doc__)
want = sys.argv[2] if len(sys.argv) > 2 else None

vals = {}
with open(sys.argv[1]) as f:
    for line in f:
        r = json.loads(line)
        v = 0
        for b in (r["reply"][10:] if r["reply"][5] == 0 else r["reply"][8:]):
            v = (v << 7) | b
        vals[(r["ee"], r["pp"], r["cc"])] = v

for cc in sorted({k[2] for k in vals}):
    elements = sorted({k[0] for k in vals if k[2] == cc})
    for ee in elements:
        pps = sorted(k[1] for k in vals if k[0] == ee and k[2] == cc)
        run, runs = [], []
        for pp in pps:
            v = vals[(ee, pp, cc)]
            if 32 <= v <= 126 and (not run or pp == run[-1][0] + 1):
                run.append((pp, v))
            else:
                if len(run) >= 3:
                    runs.append(run)
                run = [(pp, v)] if 32 <= v <= 126 else []
        if len(run) >= 3:
            runs.append(run)
        for run in runs:
            text = "".join(chr(v) for _, v in run)
            hit = "   <== FOUND" if want and want in text else ""
            print(f"cc={cc} ee={ee:3d} (0x{ee:02X}) pp {run[0][0]}..{run[-1][0]}: {text!r}{hit}")
