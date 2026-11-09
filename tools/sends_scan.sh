#!/bin/bash
# Guided scan to find the SysEx addresses of the AUX sends (level, ON, PRE/POST) for CH1, AUX1 and AUX2.
#
#   bash tools/sends_scan.sh
#
# Run on the Pi with the web server STOPPED (it owns the MIDI port), from ~/yamaha-remote, venv active.
# It scans element 1-127, params 0-15 of CH1 six times (about a minute each) and asks you to change ONE
# thing on the console between scans. At the end it prints the differences between consecutive scans
# and saves them to sends/report.txt - paste that file's content.
set -e
cd "$(dirname "$0")/.."
# use the project virtualenv if there is one (mido is installed there), else whatever python is active
PY=python
for v in venv .venv; do [ -x "$v/bin/python" ] && PY="$v/bin/python" && break; done
echo "using: $PY"
mkdir -p sends
rm -f sends/*.jsonl sends/report.txt     # param_probe appends to its output file, so start clean

scan() { $PY tools/param_probe.py --model 7F --tt 01 --ee 1-127 --pp 0-15 --cc 0 --wait 0.015 --out "sends/$1.jsonl" | tail -1; }
ask() { echo; echo ">>> $1"; read -r -p "    Press Enter when done (the scan starts right after)... " _; }

echo "On the console: select CH1 and open its AUX SEND page. Note the display values as you go."
ask "BASELINE: CH1 -> AUX1 send: level -20 dB, ON, POST.  CH1 -> AUX2 send: level -20 dB, ON, POST.  Touch nothing else from now on."
scan s0
ask "Change ONLY CH1's AUX1 send LEVEL to 0 dB."
scan s1
ask "Change ONLY CH1's AUX1 send to OFF (send off)."
scan s2
ask "Change ONLY CH1's AUX1 send to PRE (it was POST)."
scan s3
ask "Change ONLY CH1's AUX2 send LEVEL to -5 dB."
scan s4
ask "Change ONLY CH1's AUX2 send to OFF."
scan s5

{
  echo "== AUX1 level (-20 -> 0 dB) =====";   $PY tools/param_diff.py sends/s0.jsonl sends/s1.jsonl
  echo "== AUX1 send ON -> OFF ==========";   $PY tools/param_diff.py sends/s1.jsonl sends/s2.jsonl
  echo "== AUX1 POST -> PRE =============";   $PY tools/param_diff.py sends/s2.jsonl sends/s3.jsonl
  echo "== AUX2 level (-20 -> -5 dB) ====";   $PY tools/param_diff.py sends/s3.jsonl sends/s4.jsonl
  echo "== AUX2 send ON -> OFF ==========";   $PY tools/param_diff.py sends/s4.jsonl sends/s5.jsonl
} | tee sends/report.txt
echo
echo "Saved sends/report.txt - paste it (lines ending in 'None' are just dropped replies, ignore them)."
