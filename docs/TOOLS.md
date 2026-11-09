# Tools for exploring the console

Everything in [`tools/`](../tools/) talks **directly to the console's MIDI port**, so:

- **Stop the web server first.** It holds the port, and only one program can use it.
- Run them on the computer that is connected to the console, in the same Python environment as the server
  (`mido` and `python-rtmidi` installed).
- Some tools **write** to the console (they say so at the top of their help text). Use a spare channel, and
  don't run them while the console is feeding a live sound system.
- The scan scripts (`*_scan.sh`) pick the project's virtual environment (`venv/` or `.venv/`) automatically.

Each tool explains itself in the comment at the top of its file (usage, what it changes on the console).

## The usual method for finding a parameter

1. **Listen.** Run `cc_sniff.py` and move the control on the console. If the console sends it as a CC or a SysEx,
   the address is right there.
2. **Scan and diff.** If it sends nothing: run `param_probe.py` (it asks the console for a whole range of
   addresses), change **one** thing on the console, run it again, and compare the two files with
   `param_diff.py`. Only the address that moved will show up.
3. **Watch.** Once you know the element, `param_watch.py` shows every change live while you turn one knob at a time.
4. **Calibrate.** Write known values and compare with the console's display (`dyn_calib.py`, `eq_calib.py`,
   `param_calib.py`), or set known values through the CC path and see what the console reports.

## Reference

| Tool | What it is for |
|---|---|
| `cc_sniff.py` | Prints every raw MIDI message the console sends (CC and SysEx, meters hidden). Type a note + Enter to leave a marker. The quickest way to learn an address. |
| `sniff.py` | The first, simpler sniffer. |
| `eq_sniff.py` | Prints EQ changes decoded with the server's own tables, to calibrate raw values against the display. |
| `param_probe.py` | Asks the console for a range of `(element, parameter, channel)` addresses and logs every reply to a `.jsonl` file. |
| `param_diff.py` | Compares two probe files and lists which parameters changed (values shown decoded, signed). Add an element number to dump all of its parameters. |
| `param_watch.py` | Polls a range of parameters several times a second and prints each change as it happens. Accepts a range of elements. |
| `find_text.py` | Searches a probe file for text (names are stored one ASCII character per parameter). |
| `param_write_test.py` | Checks that the console accepts a SysEx **write** and reads it back (restores the original value afterwards). |
| `param_calib.py` | Moves one input fader through known positions via CC and prints the SysEx value reported for each. Moves a fader. |
| `eq_calib.py` | Sets known EQ values via CC for every band/parameter and reports which SysEx parameter moved, with the value table. Overwrites that channel's EQ. |
| `eq_type_probe.py` | Sweeps one EQ band's Q slowly so you can note where the console switches between bell, shelf and HPF/LPF. |
| `dyn_calib.py` | Interactive: writes compressor values and asks what the console's display shows. Restores the originals. |
| `meter_probe.py` | Streams a range of meters and prints the non-zero ones; first tool used to find the input meters. |
| `meter_scan.py` | Scans many meter address blocks (including whole address groups) for ones that answer. |
| `meter_blocks.py` | Live view of several meter blocks with a "baseline" key, to see which meter reacts to one change. |
| `make_screenshots.py` | Starts the server in demo mode and takes the README screenshots with your installed Edge or Chrome (`pip install playwright`). Not a console tool. |
| `sends_scan.sh` | Guided session that finds the AUX send addresses for CH1, AUX1 and AUX2. |
| `masters_scan.sh` | Guided session that scans fader/ON elements for the AUX, BUS and stereo masters. |

## Example: find where a new parameter lives

```bash
python tools/param_probe.py --model 7F --tt 01 --ee 1-127 --pp 0-15 --cc 0 --out before.jsonl
# ... change ONE thing on the console, for example the pan of channel 1 ...
python tools/param_probe.py --model 7F --tt 01 --ee 1-127 --pp 0-15 --cc 0 --out after.jsonl
python tools/param_diff.py before.jsonl after.jsonl
```

`param_probe.py` **appends** to its output file, so use a new file name for every run (the guided scripts
delete their own output first).

If you find something new, please share it: open an issue with the output (see [CONTRIBUTING.md](../CONTRIBUTING.md)).
