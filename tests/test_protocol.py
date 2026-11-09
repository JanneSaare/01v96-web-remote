"""Protocol encoding/decoding. Where possible the messages are ones a real 01V96 V2 sent."""
import mido
import pytest

from server import protocol as P


def cc(status: int, control: int, value: int) -> mido.Message:
    return mido.Message.from_bytes([status, control, value])


def sysex(hex_string: str) -> mido.Message:
    return mido.Message.from_hex(hex_string)


def feed_all(messages):
    decoder = P.Decoder()
    return [event for m in messages for event in decoder.feed(m)]


# ---- Control Change ---------------------------------------------------------------------------

@pytest.mark.parametrize("ch", [1, 12, 24, 25, 32])
@pytest.mark.parametrize("value", [0, 430, 860, 1023])
def test_input_fader_roundtrip(ch, value):
    assert feed_all(P.fader(ch, value))[-1] == ("fader", ch, value)


def test_input_fader_cc_numbers():
    msb, lsb = P.fader(1, 860)                      # 860 << 4 = 13760 = 107 * 128 + 64
    assert (msb.channel, msb.control, msb.value) == (0, 1, 107)
    assert (lsb.channel, lsb.control, lsb.value) == (0, 33, 64)


def test_fader_values_are_clamped():
    assert feed_all(P.fader(1, 5000))[-1] == ("fader", 1, P.FADER_MAX)
    assert feed_all(P.fader(1, -5))[-1] == ("fader", 1, 0)


def test_mute_is_inverted_on_button():
    (m,) = P.mute(3, on=False)
    assert (m.channel, m.control, m.value) == (0, 66, 0)
    assert feed_all([m]) == [("mute", 3, True)]
    assert feed_all(P.mute(3, on=True)) == [("mute", 3, False)]


def test_stereo_master():
    msb, lsb = P.fader(P.MASTER, 860)
    assert (msb.channel, msb.control, lsb.control) == (0, 30, 62)
    (m,) = P.mute(P.MASTER, on=False)
    assert (m.channel, m.control) == (1, 30)
    assert feed_all([m]) == [("mute", P.MASTER, True)]


def test_aux_bus_masters_as_seen_on_the_console():
    # Captured with tools/cc_sniff.py: AUX1 fader MSB then LSB, BUS1 ON off/on, AUX1 ON off
    assert feed_all([cc(0xB1, 0x15, 0x29), cc(0xB1, 0x35, 0x10)])[-1] == ("fader", 101, 329)
    assert feed_all([cc(0xB1, 0x0D, 0x2A), cc(0xB1, 0x2D, 0x60)])[-1] == ("fader", 201, 342)
    assert feed_all([cc(0xB1, 0x4C, 0x00)]) == [("mute", 201, True)]
    assert feed_all([cc(0xB1, 0x4C, 0x7F)]) == [("mute", 201, False)]
    assert feed_all([cc(0xB1, 0x6F, 0x00)]) == [("mute", 101, True)]


@pytest.mark.parametrize("ch", P.OUT_CHANNELS)
def test_aux_bus_masters_roundtrip(ch):
    for value in (0, 430, 860, 1023):
        assert feed_all(P.fader(ch, value))[-1] == ("fader", ch, value)
    for on in (True, False):
        assert feed_all(P.mute(ch, on)) == [("mute", ch, not on)]


def test_aux_bus_cc_pattern():
    assert P.fader(103, 0)[0].control == 23          # AUX 3: MSB CC 20 + 3
    assert P.fader(208, 0)[0].control == 20          # BUS 8: MSB CC 12 + 8
    assert P.mute(208, True)[0].control == 83        # BUS 8 ON: CC 75 + 8
    assert P.mute(108, True)[0].control == 118       # AUX 8 ON: CC 110 + 8


def test_hpf_lpf_flags_as_seen_on_the_console():
    assert feed_all([cc(0xBA, 0x40, 0x7F)]) == [("eqflag", 1, ("hpf", True))]
    assert feed_all([cc(0xBA, 0x59, 0x00)]) == [("eqflag", 1, ("lpf", False))]


def test_eq_cc_roundtrip():
    for band in P.BANDS:
        assert feed_all(P.eq_param(5, band, "gain", 9000))[-1] == ("eq", 5, (band, "gain", 9000))
        assert feed_all(P.eq_param(5, band, "freq", 64)) == [("eq", 5, (band, "freq", 64))]
        assert feed_all(P.eq_param(5, band, "q", 100)) == [("eq", 5, (band, "q", 100))]
    assert feed_all(P.eq_flag(2, "eq", True)) == [("eqflag", 2, ("eq", True))]


def test_unrelated_midi_is_ignored():
    assert feed_all([mido.Message("note_on", note=60, velocity=64)]) == []
    assert feed_all([cc(0xB0, 100, 5)]) == []


# ---- SysEx replies ----------------------------------------------------------------------------

def test_fader_scale_anchors_and_roundtrip():
    assert [P.raw_to_sysex_fader(r) for r in (0, 860, 1023)] == [1, 216, 255]
    assert [P.sysex_fader_to_raw(v) for v in (0, 216, 255, 300)] == [0, 860, 1023, 1023]
    for raw in (0, 50, 430, 860, 1000, 1023):
        assert abs(P.sysex_fader_to_raw(P.raw_to_sysex_fader(raw)) - raw) <= 12


def test_decode_fader_and_on_replies():
    assert feed_all([sysex("F0 43 10 3E 7F 01 1C 00 00 00 00 01 58 F7")]) == [("fader", 1, 860)]
    assert feed_all([sysex("F0 43 10 3E 7F 01 1A 00 01 00 00 00 00 F7")]) == [("mute", 2, True)]


def test_decode_eq_replies():
    # low gain -180 (= -18.0 dB) as 28-bit two's complement: 7F 7F 7E 4C
    assert feed_all([sysex("F0 43 10 3E 7F 01 20 03 00 7F 7F 7E 4C F7")]) == [("eq", 1, ("low", "gain", 92))]
    assert feed_all([sysex("F0 43 10 3E 7F 01 20 02 00 00 00 00 47 F7")]) == [("eq", 1, ("low", "freq", 70))]
    # switches: HPF (pp 4), LPF (pp 14), EQ (pp 15)
    assert feed_all([sysex("F0 43 10 3E 7F 01 20 04 00 00 00 00 01 F7")]) == [("eqflag", 1, ("hpf", True))]
    assert feed_all([sysex("F0 43 10 3E 7F 01 20 0E 00 00 00 00 01 F7")]) == [("eqflag", 1, ("lpf", True))]
    assert feed_all([sysex("F0 43 10 3E 7F 01 20 0F 01 00 00 00 00 F7")]) == [("eqflag", 2, ("eq", False))]


def test_q_value_selects_filter_type_zone():
    # low band: step 0 -> raw 0, step 41 -> shelf zone (raw 102), step 44 -> HPF zone (raw 108)
    assert [P._q_to_raw("low", v) for v in (0, 40, 41, 44)] == [0, 100, 102, 108]
    assert P._q_to_raw("lomid", 40) == 127 and P._q_to_raw("lomid", 20) == 64


def test_decode_compressor_reply_with_negative_threshold():
    assert feed_all([sysex("F0 43 10 3E 7F 01 1F 09 00 7F 7F 7D 67 F7")]) == [("dyn", 1, ("threshold", -281))]


def test_dynamics_writes_are_clamped_and_decode_back():
    for param, value, expected in (("gain", 999, 180), ("attack", -5, 0), ("on", 5, 1), ("threshold", -281, -281),
                                   ("ratio", 12, 12), ("release", 159, 159)):
        (m,) = P.dyn_param(2, param, value)
        reply = mido.Message("sysex", data=[0x43, 0x10] + list(m.data[2:]))     # a write looks like a reply
        assert feed_all([reply]) == [("dyn", 2, (param, expected))]


def test_send_writes_roundtrip():
    for aux, kind, value in ((1, "level", 860), (2, "level", 0), (3, "pre", 1), (8, "level", 1023), (8, "pre", 0)):
        (m,) = P.send_param(5, aux, kind, value)
        reply = mido.Message("sysex", data=[0x43, 0x10] + list(m.data[2:]))
        assert feed_all([reply]) == [("send", 5, (aux, kind, value))]
    with pytest.raises(ValueError):
        P.send_param(5, 9, "level", 1)                 # there is no AUX 9


def test_send_addresses():
    # Seen on the console for CH1: AUX1 level pp 2, PRE/POST pp 1; AUX2 level pp 5; AUX3 level pp 8, PRE/POST pp 7
    pairs = ((1, "level"), (1, "pre"), (2, "level"), (3, "level"), (3, "pre"))
    assert [P.send_param(1, a, k, 0)[0].data[6] for a, k in pairs] == [2, 1, 5, 8, 7]


def test_request_state_covers_everything():
    msgs = P.request_state(1)
    assert len(msgs) == 24
    assert msgs[0].hex() == "F0 43 30 3E 7F 01 1C 00 00 F7"          # fader of CH1
    assert msgs[1].hex() == "F0 43 30 3E 7F 01 1A 00 00 F7"          # ON of CH1
    with pytest.raises(ValueError):
        P.request_state(33)


def test_meter_stream_is_not_mistaken_for_parameters():
    assert feed_all([sysex("F0 43 10 3E 0D 21 00 00 00 0F 7F F7")]) == []
