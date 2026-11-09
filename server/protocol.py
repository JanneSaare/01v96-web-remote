"""01V96 V2 control via MIDI Control Change, using the console's *default*
"Initial Parameter to Control Change Table" (MIDIControl_01v96v2 PDF, p.290).

Per the table (MIDI channel 1 = "CHANNEL1" page, MIDI channel 2 = "CHANNEL2"):
  MIDI ch 1: CC 1..24  = fader MSB ("FADER H") of INPUT 1..24
             CC 33..56 = fader LSB ("FADER L") of INPUT 1..24
             CC 64..87 = channel ON of INPUT 1..24
  MIDI ch 2: same CC layout for INPUT 25..32 (idx 1..8), then ST-IN1..4 (idx 9..12)

Console setup required (MIDI/Setup screen): Control Change = TABLE mode,
Control Change RX = ON, Rx channel/omni so that MIDI ch 1 and 2 are accepted,
and the control-change table left at its initial values.

Verified on a real 01V96 V2: 14-bit fader scaling (10-bit UI value << 4, 0 dB = 860) and ON = 127 / OFF = 0.
See docs/PROTOCOL.md for everything that is known about the console, and how sure each part is.
"""
import mido

FADER_MAX = 1023  # UI range; scaled to 14 bits on the wire

INPUTS_ON_FIRST_PAGE = 24
MASTER = 0   # pseudo channel number for the Stereo master
# Master Stereo (from the same table): fader MSB = CC 30 / LSB = CC 62 on MIDI ch 1,
# ON button = CC 30 on MIDI ch 2.
MASTER_FADER_H, MASTER_FADER_L, MASTER_ON = 30, 62, 30


def _locate(ch: int) -> tuple[int, int]:
    """input channel (1..32) -> (midi_channel 0-based, index 1..24 within that page)"""
    if not 1 <= ch <= 32:
        raise ValueError("channel must be 1..32")
    if ch <= INPUTS_ON_FIRST_PAGE:
        return 0, ch
    return 1, ch - INPUTS_ON_FIRST_PAGE


# ---- AUX / BUS master faders (found with tools/cc_sniff.py) ----
# All on MIDI page 2 (mido channel 1), same CC scheme as the inputs: fader MSB = CC idx, LSB = CC idx+32.
#   BUS n: idx 12+n (13..20), ON = CC 75+n (76..83)       AUX n: idx 20+n (21..28), ON = CC 110+n (111..118)
# Seen on the console: AUX1/2 and BUS1/2 faders, AUX1 ON, BUS1 ON. The rest follows the pattern (unconfirmed).
# We address them with pseudo channel numbers in the same fader/mute messages: AUX n = 100+n, BUS n = 200+n.
AUX_BASE, BUS_BASE = 100, 200
OUT_CHANNELS = [AUX_BASE + n for n in range(1, 9)] + [BUS_BASE + n for n in range(1, 9)]


def _out_loc(ch: int) -> tuple[int, int]:
    """AUX/BUS pseudo channel -> (page-2 CC index for the fader, CC number of its ON button)"""
    if AUX_BASE < ch <= AUX_BASE + 8:
        n = ch - AUX_BASE
        return 20 + n, 110 + n
    if BUS_BASE < ch <= BUS_BASE + 8:
        n = ch - BUS_BASE
        return 12 + n, 75 + n
    raise ValueError("not an AUX/BUS master channel")


def _out_ch(midi_ch: int, idx: int):
    """page-2 CC index -> AUX/BUS pseudo channel (or None)"""
    if midi_ch != 1:
        return None
    if 13 <= idx <= 20:
        return BUS_BASE + idx - 12
    if 21 <= idx <= 28:
        return AUX_BASE + idx - 20
    return None


def fader(ch: int, value: int) -> list[mido.Message]:
    """ch 1..32 (or an AUX/BUS pseudo channel), value 0..FADER_MAX. Sends MSB (CC idx) then LSB (CC idx+32)."""
    value = max(0, min(FADER_MAX, int(value)))
    v14 = value << 4          # 10-bit -> 14-bit (assumption: console uses top 10 bits)
    if ch in OUT_CHANNELS:
        idx, _ = _out_loc(ch)
        return [mido.Message("control_change", channel=1, control=idx, value=v14 >> 7),
                mido.Message("control_change", channel=1, control=idx + 32, value=v14 & 0x7F)]
    if ch == MASTER:
        return [
            mido.Message("control_change", channel=0, control=MASTER_FADER_H, value=v14 >> 7),
            mido.Message("control_change", channel=0, control=MASTER_FADER_L, value=v14 & 0x7F),
        ]
    midi_ch, idx = _locate(ch)
    return [
        mido.Message("control_change", channel=midi_ch, control=idx, value=v14 >> 7),
        mido.Message("control_change", channel=midi_ch, control=idx + 32, value=v14 & 0x7F),
    ]


def mute(ch: int, on: bool) -> list[mido.Message]:
    """'on' is the channel ON button; muted = ON off."""
    if ch in OUT_CHANNELS:
        _, on_cc = _out_loc(ch)
        return [mido.Message("control_change", channel=1, control=on_cc, value=127 if on else 0)]
    if ch == MASTER:
        return [mido.Message("control_change", channel=1, control=MASTER_ON,
                             value=127 if on else 0)]
    midi_ch, idx = _locate(ch)
    return [mido.Message("control_change", channel=midi_ch, control=63 + idx,
                         value=127 if on else 0)]


# ---- EQ (input channels 1..32) -------------------------------------------
# From the default control-change table (MIDI "CHANNELn" page n = mido channel n-1):
#   gain MSB/LSB: page 3+2*band (ch 1-24) or 4+2*band (ch 25-32), CC idx / idx+32
#   freq (7-bit): same page, CC 63+idx
#   Q    (7-bit): same page, CC 88+idx (idx<=7) else 94+idx   (CC 96-101 unused)
#   flags: page 11/12: HPF ON = CC 63+idx, LPF ON = Q-style CC; page 13/14: EQ ON = Q-style CC
# band: 0 low, 1 lo-mid, 2 hi-mid, 3 high.   The raw scales (gain 0..16383, freq/Q 0..127) are converted to
# dB / Hz / Q in the web page; see the SysEx section below and docs/PROTOCOL.md for the measured relations.
BANDS = ("low", "lomid", "himid", "high")
EQ_FLAGS = ("eq", "hpf", "lpf")
EQ_GAIN_MAX = 16383   # 14-bit raw
EQ_7BIT_MAX = 127


def _page(ch: int, base_page: int) -> tuple[int, int]:
    """-> (mido channel 0-based, idx 1..24 within the page) for input ch 1..32"""
    if not 1 <= ch <= 32:
        raise ValueError("channel must be 1..32")
    if ch <= INPUTS_ON_FIRST_PAGE:
        return base_page - 1, ch
    return base_page, ch - INPUTS_ON_FIRST_PAGE   # next page, idx 1..8


def _q_cc(idx: int) -> int:
    return 88 + idx if idx <= 7 else 94 + idx


def eq_param(ch: int, band: str, param: str, value: int) -> list[mido.Message]:
    """param: 'gain' (0..16383), 'freq' (0..127) or 'q' (0..127)."""
    b = BANDS.index(band)
    mc, idx = _page(ch, 3 + 2 * b)
    if param == "gain":
        v = max(0, min(EQ_GAIN_MAX, int(value)))
        return [mido.Message("control_change", channel=mc, control=idx, value=v >> 7),
                mido.Message("control_change", channel=mc, control=idx + 32, value=v & 0x7F)]
    v = max(0, min(EQ_7BIT_MAX, int(value)))
    if param == "freq":
        return [mido.Message("control_change", channel=mc, control=63 + idx, value=v)]
    if param == "q":
        return [mido.Message("control_change", channel=mc, control=_q_cc(idx), value=v)]
    raise ValueError(param)


def eq_flag(ch: int, flag: str, on: bool) -> list[mido.Message]:
    page = {"eq": 13, "hpf": 11, "lpf": 11}[flag]
    mc, idx = _page(ch, page)
    cc = 63 + idx if flag == "hpf" else _q_cc(idx)
    return [mido.Message("control_change", channel=mc, control=cc, value=127 if on else 0)]


def _build_eq_map():
    m = {}
    for ch in range(1, 33):
        for b, band in enumerate(BANDS):
            mc, idx = _page(ch, 3 + 2 * b)
            m[(mc, idx)] = ("gain_h", ch, band)
            m[(mc, idx + 32)] = ("gain_l", ch, band)
            m[(mc, 63 + idx)] = ("freq", ch, band)
            m[(mc, _q_cc(idx))] = ("q", ch, band)
        for flag in EQ_FLAGS:
            mc, idx = _page(ch, 13 if flag == "eq" else 11)
            m[(mc, 63 + idx if flag == "hpf" else _q_cc(idx))] = ("flag", ch, flag)
    return m


_EQ_MAP = _build_eq_map()


# ---- Reading state back (SysEx Parameter Request, edit buffer) -------------
# Request: F0 43 3n 3E 7F 01 ee pp cc F7   Reply: F0 43 1n 3E 7F 01 ee pp cc <4 data bytes> F7
# (data = 7 bits per byte, big endian; cc = input channel - 1). Addresses found with
# tools/param_probe.py + param_diff.py: element 28 = channel fader, 26 = channel ON.
SYSEX_EE_FADER, SYSEX_EE_ON = 28, 26
# The SysEx fader value is a coarse 0..255 scale; measured against the CC scale
# (0..1023, 860 = 0 dB) with tools/param_calib.py: (sysex value, CC raw).
_FADER_CAL = [(0, 0), (1, 0), (6, 50), (8, 100), (17, 200), (38, 300), (81, 430),
              (134, 600), (189, 760), (216, 860), (237, 950), (255, 1023)]


def sysex_fader_to_raw(v: int) -> int:
    """SysEx fader value -> UI scale 0..FADER_MAX (piecewise linear over the calibration)."""
    if v >= _FADER_CAL[-1][0]:
        return FADER_MAX
    for (x0, y0), (x1, y1) in zip(_FADER_CAL, _FADER_CAL[1:]):
        if x0 <= v <= x1:
            return round(y0 + (y1 - y0) * (v - x0) / (x1 - x0)) if x1 > x0 else y1
    return 0


# EQ: element 32, one 'pp' per band/param (measured with tools/eq_calib.py, CH1 and CH2).
# Values are signed 28-bit. gain = 0.1 dB, +-180; freq = 5..124 (1/12-octave steps);
# q = 0..44 (low/high) or 0..40 (mids), nonlinear. We convert them to the CC scale
# the UI works in (gain 0..16383, freq/q 0..127).
SYSEX_EE_EQ = 32
EQ_PP = {"low": {"q": 1, "freq": 2, "gain": 3}, "lomid": {"q": 5, "freq": 6, "gain": 7},
         "himid": {"q": 8, "freq": 9, "gain": 10}, "high": {"q": 11, "freq": 12, "gain": 13}}
_EQ_PP_REV = {pp: (band, param) for band, d in EQ_PP.items() for param, pp in d.items()}
# On/off switches on the same element (0/1), found by diffing on vs off on the console:
# pp 4 = HPF ON, pp 14 = LPF ON, pp 15 = EQ ON.
EQ_FLAG_PP = {4: "hpf", 14: "lpf", 15: "eq"}
# (CC raw, SysEx value) measured by sweeping Q through the CC path
_Q_CAL = {"edge": [(0, 0), (20, 0), (32, 6), (48, 14), (64, 22), (80, 30), (96, 38), (108, 44), (127, 44)],
          "mid": [(0, 0), (16, 4), (32, 10), (48, 15), (64, 20), (80, 26), (96, 31), (112, 36), (127, 40)]}


def _q_to_raw(band: str, v: int) -> int:
    pts = _Q_CAL["mid" if band in ("lomid", "himid") else "edge"]
    top = max(y for _, y in pts)
    if v <= pts[0][1]:
        return pts[0][0]
    if v >= top:
        return next(x for x, y in pts if y == top)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if y1 > y0 and y0 <= v <= y1:
            return round(x0 + (x1 - x0) * (v - y0) / (y1 - y0))
    return 0


def _eq_to_raw(band: str, param: str, v: int) -> int:
    if param == "gain":
        return max(0, min(EQ_GAIN_MAX, 8192 + 45 * v))
    if param == "freq":
        return max(0, min(EQ_7BIT_MAX, v - 1))
    return _q_to_raw(band, v)


# ---- Compressor (element 31), found with param_watch.py and calibrated with dyn_calib.py ----
# Raw values are the console's own (signed 28-bit SysEx). Display scales:
#   threshold -540..0 = -54.0..0 dB (0.1 dB) | ratio 0..15 = table | attack 0..120 = ms
#   release 0..159 = table (5 ms .. 42.4 s) | gain 0..180 = 0..+18.0 dB (0.1 dB) | knee 0..5 = hard,1..5
#   on: pp 1, 1 = compressor ON, 0 = OFF (found with param_watch.py). pp 0 (reads 1) is probably the
#   dynamics type and is not used yet.
# Not yet known: the gain-reduction meter.
SYSEX_EE_COMP = 31
DYN_PP = {"on": 1, "attack": 4, "release": 5, "ratio": 6, "gain": 7, "knee": 8, "threshold": 9}
DYN_RANGE = {"on": (0, 1), "attack": (0, 120), "release": (0, 159), "ratio": (0, 15), "gain": (0, 180),
             "knee": (0, 5), "threshold": (-540, 0)}
_DYN_REV = {pp: name for name, pp in DYN_PP.items()}


def _enc28(v: int) -> list[int]:
    v &= (1 << 28) - 1
    return [(v >> 21) & 0x7F, (v >> 14) & 0x7F, (v >> 7) & 0x7F, v & 0x7F]


def dyn_param(ch: int, param: str, value: int, device: int = 0) -> list[mido.Message]:
    """SysEx Parameter Change (write) of one compressor value on input channel ch (1..32)."""
    if not 1 <= ch <= 32:
        raise ValueError("channel must be 1..32")
    lo, hi = DYN_RANGE[param]                      # KeyError for unknown params
    v = max(lo, min(hi, int(value)))
    return [mido.Message("sysex", data=[0x43, 0x10 | device, 0x3E, 0x7F, 0x01, SYSEX_EE_COMP,
                                        DYN_PP[param], ch - 1] + _enc28(v))]


# ---- AUX sends (element 35), found with param_watch.py on CH1 (AUX1-3 seen, AUX4-8 extrapolated) ----
# Per aux n (1..8): PRE/POST at pp 3n-2 (0 = POST, 1 = PRE), send level at pp 3n-1. The level is on the
# same coarse 0..255 scale as the fader (216 = 0 dB), so we reuse the fader table to talk to the UI in
# 0..1023. The third value of each triple (pp 0, 3, 6, ...) reads 1 and is not used (this console has no
# per-channel send ON). AUX4-8 (pp 10..24) have NOT been confirmed on hardware.
SYSEX_EE_SEND = 35
SEND_RANGE = {"level": (0, FADER_MAX), "pre": (0, 1)}
_SEND_REV = {}
for _n in range(1, 9):
    _SEND_REV[3 * _n - 2] = (_n, "pre")
    _SEND_REV[3 * _n - 1] = (_n, "level")


def _send_pp(aux: int, kind: str) -> int:
    if not 1 <= aux <= 8:
        raise ValueError("aux must be 1..8")
    return 3 * aux - 2 if kind == "pre" else 3 * aux - 1


def raw_to_sysex_fader(raw: int) -> int:
    """UI scale 0..FADER_MAX -> console 0..255 fader/send scale (inverse of sysex_fader_to_raw).
    0 maps to 1, which is what the console itself reports for -inf."""
    raw = max(0, min(FADER_MAX, int(raw)))
    pts = _FADER_CAL[1:]                        # starts at (1, 0)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if y0 <= raw <= y1:
            return round(x0 + (x1 - x0) * (raw - y0) / (y1 - y0)) if y1 > y0 else x1
    return pts[-1][0]


def send_param(ch: int, aux: int, kind: str, value: int, device: int = 0) -> list[mido.Message]:
    """SysEx write of one aux-send value: kind 'level' (UI scale 0..1023) or 'pre' (0/1)."""
    if not 1 <= ch <= 32:
        raise ValueError("channel must be 1..32")
    lo, hi = SEND_RANGE[kind]                   # KeyError for an unknown kind
    v = max(lo, min(hi, int(value)))
    if kind == "level":
        v = raw_to_sysex_fader(v)
    return [mido.Message("sysex", data=[0x43, 0x10 | device, 0x3E, 0x7F, 0x01, SYSEX_EE_SEND,
                                        _send_pp(aux, kind), ch - 1] + _enc28(v))]


def request_sends(ch: int, aux: int, device: int = 0) -> list[mido.Message]:
    """Parameter Requests for one channel's send to one aux (PRE/POST and level)."""
    if not 1 <= ch <= 32:
        raise ValueError("channel must be 1..32")
    return [mido.Message("sysex", data=[0x43, 0x30 | device, 0x3E, 0x7F, 0x01, SYSEX_EE_SEND,
                                        _send_pp(aux, kind), ch - 1]) for kind in ("pre", "level")]


def request_state(ch: int, device: int = 0) -> list[mido.Message]:
    """Parameter Requests for one input channel (ch 1..32): fader, ON button, 4-band EQ, compressor."""
    if not 1 <= ch <= 32:
        raise ValueError("channel must be 1..32")
    addrs = [(SYSEX_EE_FADER, 0), (SYSEX_EE_ON, 0)] + \
            [(SYSEX_EE_EQ, pp) for pp in sorted(list(_EQ_PP_REV) + list(EQ_FLAG_PP))] + \
            [(SYSEX_EE_COMP, pp) for pp in sorted(_DYN_REV)]
    return [mido.Message("sysex", data=[0x43, 0x30 | device, 0x3E, 0x7F, 0x01, ee, pp, ch - 1])
            for ee, pp in addrs]


class Decoder:
    """Console -> us: turn incoming Control Change into ('fader', ch, value) /
    ('mute', ch, muted) events, using the same table as the encoders above.
    Requires Control Change TX = ON on the console.
    Fader MSB and LSB arrive as two CCs; we emit on each, using the last
    value seen of the other half (the server drops unchanged values)."""

    def __init__(self):
        self._h: dict[tuple[int, int], int] = {}
        self._l: dict[tuple[int, int], int] = {}
        self._eh: dict[tuple[int, str], int] = {}
        self._el: dict[tuple[int, str], int] = {}

    def _feed_eq(self, msg) -> list[tuple]:
        info = _EQ_MAP.get((msg.channel, msg.control))
        if not info:
            return []
        kind, ch, what = info
        v = msg.value
        if kind == "flag":
            return [("eqflag", ch, (what, v > 0))]
        if kind in ("gain_h", "gain_l"):
            (self._eh if kind == "gain_h" else self._el)[(ch, what)] = v
            v14 = (self._eh.get((ch, what), 0) << 7) | self._el.get((ch, what), 0)
            return [("eq", ch, (what, "gain", v14))]
        return [("eq", ch, (what, kind, v))]

    @staticmethod
    def _input(midi_ch: int, idx: int):
        ch = idx if midi_ch == 0 else idx + INPUTS_ON_FIRST_PAGE if midi_ch == 1 else None
        return ch if ch is not None and 1 <= ch <= 32 and (midi_ch == 0 or idx <= 8) else None

    @staticmethod
    def _feed_sysex(msg) -> list[tuple]:
        """Replies to request_state(): same events as the CC path."""
        d = msg.data
        if len(d) < 9 or d[0] != 0x43 or d[1] & 0xF0 != 0x10 or tuple(d[2:5]) != (0x3E, 0x7F, 0x01):
            return []
        ee, pp, cc, data = d[5], d[6], d[7], d[8:]
        if not 0 <= cc < 32 or not data:
            return []
        v = 0
        for b in data:
            v = (v << 7) | b
        if ee == SYSEX_EE_SEND:
            if pp not in _SEND_REV:
                return []
            aux, kind = _SEND_REV[pp]
            return [("send", cc + 1, (aux, kind, sysex_fader_to_raw(v) if kind == "level" else int(v != 0)))]
        if ee == SYSEX_EE_COMP:
            if pp not in _DYN_REV:
                return []
            if v >= 1 << (7 * len(data) - 1):
                v -= 1 << (7 * len(data))
            return [("dyn", cc + 1, (_DYN_REV[pp], v))]
        if ee == SYSEX_EE_EQ:
            if pp in EQ_FLAG_PP:
                return [("eqflag", cc + 1, (EQ_FLAG_PP[pp], v != 0))]
            if pp not in _EQ_PP_REV:
                return []
            if v >= 1 << (7 * len(data) - 1):         # two's complement (negative gain)
                v -= 1 << (7 * len(data))
            band, param = _EQ_PP_REV[pp]
            return [("eq", cc + 1, (band, param, _eq_to_raw(band, param, v)))]
        if pp != 0:
            return []
        if ee == SYSEX_EE_FADER:
            return [("fader", cc + 1, sysex_fader_to_raw(v))]
        if ee == SYSEX_EE_ON:
            return [("mute", cc + 1, v == 0)]
        return []

    def feed(self, msg) -> list[tuple]:
        if msg.type == "sysex":
            return self._feed_sysex(msg)
        if msg.type != "control_change":
            return []
        if msg.channel > 1:
            return self._feed_eq(msg)
        mc, cc, v = msg.channel, msg.control, msg.value
        if mc == 0 and cc in (MASTER_FADER_H, MASTER_FADER_L):
            if cc == MASTER_FADER_H:
                self._h[(mc, 0)] = v
            else:
                self._l[(mc, 0)] = v
            v14 = (self._h.get((mc, 0), 0) << 7) | self._l.get((mc, 0), 0)
            return [("fader", MASTER, min(FADER_MAX, v14 >> 4))]
        if mc == 1 and cc == MASTER_ON:
            return [("mute", MASTER, v == 0)]
        top = 28 if mc == 1 else 24                  # page 2 also carries ST-IN, BUS1-8 and AUX1-8 (idx up to 28)
        if 1 <= cc <= top:
            self._h[(mc, cc)] = v
            idx = cc
        elif 33 <= cc <= top + 32:
            self._l[(mc, cc - 32)] = v
            idx = cc - 32
        elif 64 <= cc <= 87:
            ch = self._input(mc, cc - 63)
            if ch is None and mc == 1 and 76 <= cc <= 83:
                ch = BUS_BASE + cc - 75              # BUS1-8 ON
            return [("mute", ch, v == 0)] if ch else []
        elif mc == 1 and 111 <= cc <= 118:
            return [("mute", AUX_BASE + cc - 110, v == 0)]   # AUX1-8 ON
        else:
            return []
        ch = self._input(mc, idx) or _out_ch(mc, idx)
        if not ch:
            return []
        v14 = (self._h.get((mc, idx), 0) << 7) | self._l.get((mc, idx), 0)
        return [("fader", ch, min(FADER_MAX, v14 >> 4))]


if __name__ == "__main__":
    d = Decoder()
    # AUX/BUS masters: replay what the console sent (tools/cc_sniff.py), then round-trip our own messages
    for hexs, want in (("B1 15 29", ("fader", 101, 328)), ("B1 35 10", ("fader", 101, 329)),   # AUX1 fader: MSB, then LSB
                       ("B1 0D 2A", ("fader", 201, 336)), ("B1 2D 60", ("fader", 201, 342)),    # BUS1 fader
                       ("B1 4C 7F", ("mute", 201, False)), ("B1 4C 00", ("mute", 201, True)),   # BUS1 ON
                       ("B1 6F 7F", ("mute", 101, False)), ("B1 6F 00", ("mute", 101, True))):  # AUX1 ON
        got = d.feed(mido.Message.from_hex(hexs))
        print("out", hexs, "->", got)
        assert (got[0] if got else None) == want, (hexs, got, want)
    for ch in OUT_CHANNELS:
        for val in (0, 430, 860, 1023):
            dd = Decoder()
            ev = [e for m in fader(ch, val) for e in dd.feed(m)][-1]
            assert ev == ("fader", ch, val), (ch, val, ev)
        for on in (True, False):
            ev = Decoder().feed(mute(ch, on)[0])
            assert ev == [("mute", ch, not on)], (ch, on, ev)
    print("out channels: fader and ON round-trip for all", len(OUT_CHANNELS))
    assert (fader(103, 860)[0].control, fader(208, 0)[0].control, mute(208, True)[0].control, mute(108, True)[0].control) == (23, 20, 83, 118)   # AUX3 idx, BUS8 idx, BUS8 ON, AUX8 ON
    for m in fader(1, 860) + fader(25, 300) + mute(3, False) + fader(MASTER, 860) + mute(MASTER, False):
        print(m.hex(), "->", d.feed(m))
    for ch, v in ((1, 1023), (1, 0), (25, 512)):
        print("fader", ch, v, [m.hex() for m in fader(ch, v)])
    print("mute CH1 (ON off)", [m.hex() for m in mute(1, False)])
    print("unmute CH32", [m.hex() for m in mute(32, True)])
    for args in ((1, "low", "gain", 8192), (1, "high", "q", 64), (25, "lomid", "freq", 90), (24, "himid", "q", 100)):
        ms = eq_param(*args)
        print("eq", args, [m.hex() for m in ms], "->", [e for m in ms for e in d.feed(m)])
    # SysEx read-back: replies as seen on the real console (CH1 fader 216 = 0 dB, CH2 muted)
    print("request", [m.hex() for m in request_state(2)])
    for hexs in ("F0 43 10 3E 7F 01 1C 00 00 00 00 01 58 F7", "F0 43 10 3E 7F 01 1A 00 01 00 00 00 00 F7",
                 "F0 43 10 3E 7F 01 1C 00 00 00 00 01 5F F7", "F0 43 10 3E 7F 01 5C 00 00 00 00 06 39 F7"):
        print("reply ->", d.feed(mido.Message.from_hex(hexs)))
    assert [sysex_fader_to_raw(v) for v in (0, 216, 255, 300)] == [0, 860, 1023, 1023]
    # EQ replies from the real console: low gain -180 = 0x0FFFFFCC, low freq 71, lomid Q 40, high Q 44
    for hexs in ("F0 43 10 3E 7F 01 20 03 00 7F 7F 7E 4C F7", "F0 43 10 3E 7F 01 20 02 00 00 00 00 47 F7",
                 "F0 43 10 3E 7F 01 20 05 00 00 00 00 28 F7", "F0 43 10 3E 7F 01 20 0B 01 00 00 00 2C F7"):
        print("eq reply ->", d.feed(mido.Message.from_hex(hexs)))
    for band, d_ in (("low", 0), ("low", 44), ("lomid", 40), ("lomid", 20)):
        print("q", band, d_, "->", _q_to_raw(band, d_))
    # every measured point must round-trip: CC raw -> sysex -> back to a raw that gives the same sysex value
    assert len(request_state(1)) == 24
    # aux sends: write -> read back through the decoder, and check the level scale round-trips
    assert [raw_to_sysex_fader(r) for r in (0, 860, 1023)] == [1, 216, 255]
    for r in (0, 50, 430, 860, 1000, 1023):
        assert abs(sysex_fader_to_raw(raw_to_sysex_fader(r)) - r) <= 12, r
    for aux, kind, val in ((1, "level", 860), (2, "level", 0), (3, "pre", 1), (8, "level", 1023), (8, "pre", 0)):
        m = send_param(5, aux, kind, val)[0]
        print("send", aux, kind, val, "->", m.hex(), "->", d.feed(mido.Message("sysex", data=[0x43, 0x10] + list(m.data[2:]))))
    print("pp used:", [(a, k, _send_pp(a, k)) for a in (1, 2, 3, 8) for k in ("pre", "level")])
    # compressor: encode through dyn_param and decode the same bytes back
    for param, val in (("threshold", -281), ("ratio", 12), ("release", 159), ("gain", 999), ("attack", -5),
                       ("on", 1), ("on", 0), ("on", 5)):
        m = dyn_param(2, param, val)[0]
        reply = mido.Message("sysex", data=[0x43, 0x10] + list(m.data[2:]))
        print("dyn", param, val, "->", m.hex(), "->", d.feed(reply))
    for hexs in ("F0 43 10 3E 7F 01 20 04 00 00 00 00 01 F7", "F0 43 10 3E 7F 01 20 04 01 00 00 00 00 F7",
                 "F0 43 10 3E 7F 01 20 0E 00 00 00 00 01 F7", "F0 43 10 3E 7F 01 20 0F 01 00 00 00 00 F7"):
        print("flag reply ->", d.feed(mido.Message.from_hex(hexs)))
    for ch, fl in ((1, "eq"), (1, "hpf"), (32, "lpf")):
        ms = eq_flag(ch, fl, True)
        print("flag", ch, fl, [m.hex() for m in ms], "->", [e for m in ms for e in d.feed(m)])
