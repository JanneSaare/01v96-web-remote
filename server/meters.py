"""Remote-meter handling (PDF 2.8.3.23 / 2.8.3.24).

Request:  F0 43 3n 3E 0D 21 UL LU LL CH CL F7   -> console streams every 50 ms for 10 s
Reply:    F0 43 1n 3E 0D 21 UL LU LL <H L>... F7  (14-bit value per meter)

Observed on the real console: addresses 0..39 respond (40 meters), input k at address k-1.
See docs/PROTOCOL.md for the other blocks (gain reduction, AUX, BUS, stereo master).
"""
import math
import time
import mido

DEVICE = 0            # device number = console Rx channel - 1
START = 0
COUNT = 40
import os
# Meter display floor (dB). Override without editing code: METER_FLOOR_DB=-50
FLOOR_DB = float(os.environ.get("METER_FLOOR_DB", -60))

# Raw value -> dB, measured on the real console with a steady 1 kHz tone on CH1,
# read against the console's own meter. Raw is ~linear in dB (about 41 steps/dB,
# 4095 = 0 dB). The first point extends that line down to raw 0. Unconnected
# inputs (raw ~100-300) therefore land near -95 dB, below the display floor.
CALIBRATION = [
    (0, -100), (2145, -48), (2852, -30), (3394, -18), (3587, -12), (3848, -6), (4095, 0),
]
REREQUEST_S = 8       # console stops after 10 s

# Compressor gain-reduction meters: 40 values at 0x180 + (input channel - 1), found by comparing a
# full address scan (tools/meter_scan.py groups) with the compressor off and on. 4095 = no reduction,
# lower = more reduction. Assumed scale: the same ~41 steps/dB as the input meters (to be checked
# against the console's own reduction display).
GR_START = 0x180
GR_NONE = 4095
GR_STEPS_PER_DB = float(os.environ.get("GR_STEPS_PER_DB", 41))


# Output level meters: 8 values each, found with tools/meter_blocks.py by routing CH1 to AUX1 / BUS1 and
# watching which meter came alive. The blocks at +0x80 / +0x100 repeat the same values for outputs.
# AUX n = 0x8000 + n-1, BUS n = 0x4000 + n-1. Inferred from AUX1 and BUS1 only; AUX2-8 / BUS2-8 follow the order.
OUT_COUNT = 8
AUX_START = 0x8000
BUS_START = 0x4000
# Stereo master meter: L and R at 0x10000 / 0x10001 (found with tools/meter_scan.py groups 8 32 and a mono tone to
# ST OUT: both read the same). The copies at +0x80 / +0x100 are other metering points; we use the first block,
# like for the inputs.
ST_START = 0x10000
ST_COUNT = 2


def request(start: int = START, count: int = COUNT) -> mido.Message:
    return mido.Message("sysex", data=[
        0x43, 0x30 | DEVICE, 0x3E, 0x0D, 0x21,
        (start >> 14) & 0x7F, (start >> 7) & 0x7F, start & 0x7F,
        (count >> 7) & 0x7F, count & 0x7F])


def requests() -> list[mido.Message]:
    """Input level meters, gain-reduction meters, AUX, BUS and stereo master output meters."""
    return [request(START), request(GR_START), request(AUX_START, OUT_COUNT), request(BUS_START, OUT_COUNT),
            request(ST_START, ST_COUNT)]


class Meters:
    def __init__(self):
        self.values = [0] * COUNT
        self.gr = [GR_NONE] * COUNT
        self.aux = [0] * OUT_COUNT
        self.bus = [0] * OUT_COUNT
        self.st = [0] * ST_COUNT
        self._t = 0.0

    def on_message(self, msg):
        """Called from the MIDI input thread."""
        if msg.type != "sysex":
            return
        d = msg.data
        if len(d) > 8 and d[0] == 0x43 and d[1] & 0xF0 == 0x10 and tuple(d[2:5]) == (0x3E, 0x0D, 0x21):
            base = (d[5] << 14) | (d[6] << 7) | d[7]
            vals = d[8:]
            for i in range(0, len(vals) - 1, 2):
                addr = base + i // 2
                v = (vals[i] << 7) | vals[i + 1]
                if 0 <= addr - START < COUNT:
                    self.values[addr - START] = v
                elif 0 <= addr - GR_START < COUNT:
                    self.gr[addr - GR_START] = v
                elif 0 <= addr - AUX_START < OUT_COUNT:
                    self.aux[addr - AUX_START] = v
                elif 0 <= addr - BUS_START < OUT_COUNT:
                    self.bus[addr - BUS_START] = v
                elif 0 <= addr - ST_START < ST_COUNT:
                    self.st[addr - ST_START] = v

    def fake(self):
        """Mock-mode animation so the UI can be developed without hardware."""
        t = time.time()
        for i in range(COUNT):
            x = 0.5 + 0.5 * math.sin(t * (1.3 + i * 0.17) + i)
            self.values[i] = int(4095 * x * x)
            red = 12 * max(0.0, math.sin(t * 0.7 + i)) * x          # up to ~12 dB of fake reduction
            self.gr[i] = int(GR_NONE - red * GR_STEPS_PER_DB)
        for i in range(OUT_COUNT):
            self.aux[i] = int(4095 * (0.5 + 0.5 * math.sin(t * (0.9 + i * 0.21) + i)) ** 2)
            self.bus[i] = int(4095 * (0.5 + 0.5 * math.sin(t * (1.1 + i * 0.13) + 2 * i)) ** 2)
        for i in range(ST_COUNT):
            self.st[i] = int(4095 * (0.55 + 0.45 * math.sin(t * (1.0 + i * 0.3))) ** 2)

    def snapshot(self, n: int) -> list[int]:
        return self.values[:n]

    def gr_snapshot(self, n: int) -> list[int]:
        return self.gr[:n]

    def out_snapshot(self) -> tuple[list[int], list[int]]:
        return list(self.aux), list(self.bus)

    def st_snapshot(self) -> list[int]:
        return list(self.st)
