# Helping to test on your console

This project was built against **one** 01V96 V2, and some of it is only *assumed* from a pattern
(the ◐ rows in [PROTOCOL.md](PROTOCOL.md)). If you own a console, a short test session tells us what really
works. You don't need to do everything; each item you check is useful.

> **Safety.** The page **changes things on your console** (faders, mutes, EQ, compressor, sends). Test with
> nothing live: speakers off or a quiet room, and ideally on a scratch scene. Write down the values you change
> so you can put them back (or recall a scene afterwards).

## Before you start

1. Set up the console as described in the [README](../README.md#console-setup-midi--setup-screen), and note your
   **console model and firmware version** (UTILITY screen).
2. Start the server with your console connected, open the page in a browser, and check that the green dot in
   the header is lit. Use a force-reload (Ctrl+Shift+R) after every update.
3. If nothing reacts: check that the MIDI port is found (`python -c "import mido; print(mido.get_output_names())"`),
   that **Parameter Change** and **Control Change** TX/RX are on, and that the Rx channel matches. The tools in
   [TOOLS.md](TOOLS.md) (especially `cc_sniff.py`) show what the console actually sends.

## The checklist

Tick what you try, and report it with the **Console report** issue form.

### Basics (expected to work)
- [ ] **Startup read-back.** Move some faders and mutes on the console *before* starting the server. After the
      page opens, do the faders show the console's positions (not empty/dimmed)?
- [ ] **Faders and mutes** on CH1 and CH24: page to console, and console to page.
- [ ] **Stereo master** fader and mute.

### Assumed (these are the ones that matter most)
- [ ] **AUX OUT view:** move the master faders and ON buttons of **AUX 3 to AUX 8**, on the console and in the page.
      (Only AUX 1 and 2 were confirmed.)
- [ ] **BUS OUT view:** the same for **BUS 3 to BUS 8**. (Only BUS 1 and 2 were confirmed.)
- [ ] **AUX sends 4-8:** open the AUX 5 tab (for example), move a channel's send on the console, then in the page. Also
      the PRE/POST button. (Only AUX 1-3 were confirmed.)
- [ ] **Inputs 25-32:** start the server with `CHANNELS=32` and check faders and mutes on channels 25-32.
- [ ] **EQ ON switch** (the EQ button on the EQ page).

### Calibration (numbers needed)
- [ ] **Gain-reduction bars:** put a steady tone through a compressor that is reducing. Compare the page's
      "Gain reduction" readout (dB) with the console's own display. Please report **both numbers**; the scale is assumed.
- [ ] **Level meters:** compare the stereo master, an AUX and a BUS meter with the console's meters (roughly, with a
      steady tone). Do the bars sit at about the same level?
- [ ] **HIGH band types:** set the HIGH band to shelf and to LPF on the console. Does the page show the same type?
      (This is assumed to mirror the LOW band.)
- [ ] **Release and ratio labels:** pick two or three values on the compressor and compare the labels with the
      console's display (the release table is interpolated between measured points).

### If you can use the tools
- [ ] Find where **channel names** live. They could not be found over MIDI on the author's console. If you find
      them, that is a big one (see [TOOLS.md](TOOLS.md), `find_text.py`).
- [ ] Find a **SysEx address for the master faders**. A lead: element 79 announced a value while the stereo master
      fader moved.

## Reporting

Open a **Console report** (the form lists these items as checkboxes), or a **Found a new parameter** issue if you
worked out an address. Include your console model and firmware. If something misbehaves, the output of
`python tools/cc_sniff.py` while you move the control makes it much easier to fix. Thank you!
