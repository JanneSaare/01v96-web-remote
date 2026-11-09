#!/bin/bash
# Guided scan to find the SysEx channel numbers of the AUX masters, BUS masters and the stereo master.
#
#   bash tools/masters_scan.sh
#
# Run on the Pi with the web server STOPPED (it owns the MIDI port), from ~/yamaha-remote, venv active.
# Scans elements 26-28 (channel ON = 26, fader = 28) for all 128 channel numbers (cc 0-127), a few
# seconds each, and asks you to change ONE thing on the console between scans. Prints the differences
# and saves them to masters/report.txt - paste that.
set -e
cd "$(dirname "$0")/.."
# use the project virtualenv if there is one (mido is installed there), else whatever python is active
PY=python
for v in venv .venv; do [ -x "$v/bin/python" ] && PY="$v/bin/python" && break; done
echo "using: $PY"
mkdir -p masters
rm -f masters/*.jsonl masters/report.txt        # param_probe appends to its output file, so start clean

scan() { $PY tools/param_probe.py --model 7F --tt 01 --ee 26-28 --pp 0 --cc 0-127 --wait 0.015 --out "masters/$1.jsonl" | tail -1; }
ask() { echo; echo ">>> $1"; read -r -p "    Press Enter when done (the scan starts right after)... " _; }

ask "BASELINE: AUX1 master 0 dB, AUX2 master -10 dB, BUS1 master 0 dB, BUS2 master -10 dB, ST OUT master 0 dB. All of them ON. Touch nothing else from now on."
scan m0
ask "Change ONLY the AUX1 master fader to -20 dB."
scan m1
ask "Change ONLY the AUX2 master fader to -30 dB."
scan m2
ask "Change ONLY the BUS1 master fader to -20 dB."
scan m3
ask "Change ONLY the BUS2 master fader to -30 dB."
scan m4
ask "Change ONLY the ST OUT (stereo) master fader to -5 dB."
scan m5
ask "Switch ONLY the AUX1 master OFF (its ON button)."
scan m6
ask "Switch ONLY the BUS1 master OFF (its ON button)."
scan m7
ask "Optional - switch the ST OUT master OFF (this mutes the main output; switch it back ON afterwards)."
scan m8

{
  echo "== AUX1 fader -> -20 dB ==";    $PY tools/param_diff.py masters/m0.jsonl masters/m1.jsonl
  echo "== AUX2 fader -> -30 dB ==";    $PY tools/param_diff.py masters/m1.jsonl masters/m2.jsonl
  echo "== BUS1 fader -> -20 dB ==";    $PY tools/param_diff.py masters/m2.jsonl masters/m3.jsonl
  echo "== BUS2 fader -> -30 dB ==";    $PY tools/param_diff.py masters/m3.jsonl masters/m4.jsonl
  echo "== ST OUT fader -> -5 dB ==";   $PY tools/param_diff.py masters/m4.jsonl masters/m5.jsonl
  echo "== AUX1 ON -> OFF ==========";  $PY tools/param_diff.py masters/m5.jsonl masters/m6.jsonl
  echo "== BUS1 ON -> OFF ==========";  $PY tools/param_diff.py masters/m6.jsonl masters/m7.jsonl
  echo "== ST OUT ON -> OFF ========";  $PY tools/param_diff.py masters/m7.jsonl masters/m8.jsonl
  echo "== which channel numbers answer at all (baseline, fader element 28) ==";
  $PY - <<'PY'
import json
seen = sorted({r["cc"] for r in map(json.loads, open("masters/m0.jsonl")) if r["ee"] == 28})
print("cc values that answer for the fader element:", seen)
PY
} | tee masters/report.txt
echo
echo "Saved masters/report.txt - paste it (lines ending in 'None' are just dropped replies, ignore them)."
echo "If you switched ST OUT off, switch it back ON now."
