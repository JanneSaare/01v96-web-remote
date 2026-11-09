"""Demo mix for mock mode (MIDI_PORT=mock DEMO=1): a plausible, fully populated console, no hardware needed.

Used to try the page, to take screenshots (tools/make_screenshots.py) and for tests. The values are made up and
deterministic (the same every run). Nothing here is ever sent to a console.
"""
import math
import random

from . import protocol

CHANNEL_NAMES = ["Kick", "Snare", "Hat", "Tom 1", "Tom 2", "Floor", "OH L", "OH R", "Bass", "Gtr L", "Gtr R",
                 "Keys L", "Keys R", "Lead", "Vox 2", "Vox 3", "Vox 4", "Click", "Track L", "Track R", "Talk",
                 "Sax", "Perc", "Spare"]
AUX_NAMES = ["Mon Drums", "Mon Bass", "Mon Vox", "Mon Gtr", "Mon Keys", "IEM Lead", "Reverb", "Delay"]
BUS_NAMES = ["Drums", "Guitars", "Keys", "Vocals"]
COMPRESSED = {1, 2, 9, 14, 15, 16, 17}              # channels with the compressor on
NO_HPF = {18, 19, 20, 24}                            # click and playback tracks get no high-pass filter
PRE_AUXES = {1, 2, 3, 4, 5, 6}                       # monitor auxes are pre-fader; the two effect auxes are post


def _step_from_hz(hz: float) -> int:
    """console frequency step (5..124, 1/12 octave from 21.2 Hz to 20 kHz)"""
    return max(5, min(124, round(5 + 119 * math.log(hz / 21.2) / math.log(20000 / 21.2))))


def fill(state, eq_state, dyn_state, send_state, names) -> None:
    rnd = random.Random(2026)
    for ch in eq_state:
        names[ch] = CHANNEL_NAMES[ch - 1] if ch <= len(CHANNEL_NAMES) else f"CH {ch}"
        state["fader"][ch] = rnd.randint(540, 880)
        state["mute"][ch] = ch in (21, 24)
    state["fader"][0], state["mute"][0] = 860, False       # stereo master at 0 dB
    names[0] = "Main"
    for n in range(1, 9):
        names[protocol.AUX_BASE + n] = AUX_NAMES[n - 1]
        state["fader"][protocol.AUX_BASE + n] = rnd.randint(700, 880)
        state["mute"][protocol.AUX_BASE + n] = False
    for n in range(1, 9):
        if n <= len(BUS_NAMES):
            names[protocol.BUS_BASE + n] = BUS_NAMES[n - 1]
        state["fader"][protocol.BUS_BASE + n] = rnd.randint(700, 880)
        state["mute"][protocol.BUS_BASE + n] = False

    for ch, eq in eq_state.items():
        # (gain in 0.1 dB, frequency in Hz, Q step) per band; everything is given in the console's own units
        low = (rnd.randint(-30, 40), rnd.choice((80, 100, 120, 160)), 44 if ch not in NO_HPF else 41)
        lomid = (rnd.randint(-60, 30), rnd.choice((250, 315, 400, 500)), rnd.choice((12, 16, 20, 24)))
        himid = (rnd.randint(-30, 50), rnd.choice((1600, 2500, 3150, 4000)), rnd.choice((14, 18, 22)))
        high = (rnd.randint(0, 70), rnd.choice((8000, 10000, 12500)), 41 if ch % 3 == 0 else 20)
        for band, (gain, hz, q) in zip(protocol.BANDS, (low, lomid, himid, high)):
            eq[band]["gain"] = protocol._eq_to_raw(band, "gain", gain)
            eq[band]["freq"] = protocol._eq_to_raw(band, "freq", _step_from_hz(hz))
            eq[band]["q"] = protocol._eq_to_raw(band, "q", q)
        eq["flags"].update({"eq": True, "hpf": ch not in NO_HPF, "lpf": False})

    for ch, dyn in dyn_state.items():
        on = ch in COMPRESSED
        dyn.update({"on": int(on), "threshold": -rnd.randint(150, 320) if on else -200,
                    "ratio": rnd.choice((7, 9, 9, 10)) if on else 9, "attack": rnd.choice((5, 10, 20, 30)),
                    "release": rnd.randint(55, 85), "gain": rnd.randint(10, 60) if on else 0,
                    "knee": rnd.choice((1, 2, 3))})

    for aux, per_channel in send_state.items():
        for ch, send in per_channel.items():
            wanted = rnd.random() < (0.75 if aux <= 6 else 0.5)
            send["level"] = rnd.randint(380, 800) if wanted else 0
            send["pre"] = int(aux in PRE_AUXES)
