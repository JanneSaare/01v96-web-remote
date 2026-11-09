"""Remote-meter request and parsing, with values from a real console."""
import mido

from server import meters as M


def reply(base: int, values) -> mido.Message:
    data = [0x43, 0x10, 0x3E, 0x0D, 0x21, (base >> 14) & 0x7F, (base >> 7) & 0x7F, base & 0x7F]
    for v in values:
        data += [(v >> 7) & 0x7F, v & 0x7F]
    return mido.Message("sysex", data=data)


def test_requests_cover_all_blocks():
    starts = []
    for m in M.requests():
        d = m.data
        assert d[:5] == (0x43, 0x30, 0x3E, 0x0D, 0x21)
        starts.append((d[5] << 14) | (d[6] << 7) | d[7])
    assert starts == [0x0000, 0x0180, 0x8000, 0x4000, 0x10000]


def test_parses_each_block_into_the_right_list():
    m = M.Meters()
    m.on_message(reply(0x0000, [3871, 444]))
    m.on_message(reply(0x0180, [3715, 4095]))
    m.on_message(reply(0x8000, [3350, 0, 0, 0, 3098, 3124, 0, 3436]))
    m.on_message(reply(0x4000, [2963, 0, 0, 0, 0, 0, 0, 3335]))
    m.on_message(reply(0x10000, [3414, 3414]))
    assert m.snapshot(2) == [3871, 444]
    assert m.gr_snapshot(2) == [3715, 4095]
    aux, bus = m.out_snapshot()
    assert aux[0] == 3350 and aux[7] == 3436 and bus[0] == 2963 and bus[7] == 3335
    assert m.st_snapshot() == [3414, 3414]


def test_other_copies_of_a_block_are_ignored():
    m = M.Meters()
    m.on_message(reply(0x10080, [111, 222]))       # the same stereo meter at another metering point
    m.on_message(reply(0x10100, [333, 444]))
    assert m.st_snapshot() == [0, 0]


def test_unrelated_messages_are_ignored():
    m = M.Meters()
    m.on_message(mido.Message("note_on", note=60))
    m.on_message(mido.Message("sysex", data=[0x43, 0x10, 0x3E, 0x7F, 0x01, 0x1C, 0x00, 0x00, 0, 0, 0, 5]))
    assert m.snapshot(1) == [0]


def test_gain_reduction_scale():
    assert M.GR_NONE == 4095
    assert M.GR_STEPS_PER_DB == 41


def test_mock_animation_stays_in_range():
    m = M.Meters()
    m.fake()
    assert all(0 <= v <= 4095 for v in m.snapshot(24) + m.aux + m.bus + m.st)
    assert all(v <= M.GR_NONE for v in m.gr)
