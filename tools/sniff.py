"""Print every MIDI message the console sends, so we can learn the SysEx addresses.

Usage:  python tools/sniff.py            (lists ports, opens the first one matching '01V96')
        python tools/sniff.py <substring>
On the console enable: MIDI setup -> Parameter Change TX (and Control Change TX).
Then move CH1 fader (slowly: bottom, -10, 0, top), toggle CH1 ON, repeat on CH2,
and send me the output.
"""
import sys
import mido

names = mido.get_input_names()
print("Input ports:", names)
want = (sys.argv[1] if len(sys.argv) > 1 else "01V96").lower()
match = [n for n in names if want in n.lower()]
if not match:
    sys.exit(f"No input port matching '{want}'")
print("Listening on", match[0], "- Ctrl+C to stop")
with mido.open_input(match[0]) as port:
    for msg in port:
        print(msg.hex() if msg.type == "sysex" else msg)
