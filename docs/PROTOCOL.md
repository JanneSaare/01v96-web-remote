# Protocol notes: talking to a Yamaha 01V96 V2

Yamaha documents the 01V96's MIDI implementation only partly: the *message formats* are in the owner's manual
(Appendix C: MIDI data format), but the manual says "consult your dealer" for the **parameter addresses**.
Everything below marked ✔ was found by experiment on one console with the scripts in [`tools/`](../tools/)
(see [TOOLS.md](TOOLS.md) for how). Please read the "confidence" column before relying on a row.

| Mark | Meaning |
|---|---|
| ✔ | Seen on a real 01V96 V2 (the console sent it, or accepted it and changed) |
| ◐ | Extrapolated from a pattern, or taken from the manual's table, but not seen on hardware |
| ? | Unknown |

## 1. Two ways in

The console can be driven in two independent ways over the same USB MIDI port:

1. **Control Change (CC)**, using the console's *initial control-change table* ("TABLE" mode).
   Each parameter has a fixed channel/CC number. Simple, but only parameters that are in the table exist, and
   it carries no way to *ask* for a value. The console also *sends* these CCs when you move a control.
2. **SysEx Parameter Change / Parameter Request.** Every parameter has an address
   `(element, parameter, channel)`. Values can be *read* (request) and *written*, and the console *announces*
   changes of parameters that are not in the CC table. This is what makes the startup read-back possible.

If a parameter is in the CC table, the console normally sends it as CC and not as SysEx. (The stereo master
fader was seen sending **both**; see the lead in the table in section 3.)

### Console settings

MIDI / SETUP screen: **Control Change** = TABLE, TX and RX on; **Parameter Change** TX and RX on;
Rx channel = device number + 1 (this project uses device 0, so channel 1); MIDI channels 1-14 accepted;
the control-change table left at its initial values.

## 2. Control Change

"Page n" is MIDI channel n (the manual's tables are called `CHANNEL1`, `CHANNEL2`, ...; in code with 0-based
channels it is channel n−1). Faders are 14-bit: MSB at CC *k*, LSB at CC *k*+32.

| Parameter | Page / CC | Confidence |
|---|---|---|
| Input 1-24 fader | page 1, MSB CC 1-24, LSB CC 33-56 | ✔ |
| Input 1-24 ON | page 1, CC 64-87 (127 = on, 0 = off) | ✔ |
| Input 25-32 fader / ON | page 2, same layout, index 1-8 | ◐ |
| Stereo master fader | page 1, MSB CC 30, LSB CC 62 | ✔ |
| Stereo master ON | page 2, CC 30 | ✔ |
| BUS *n* fader (n = 1-8) | page 2, MSB CC 12+*n*, LSB CC 44+*n* | ✔ BUS1-2, ◐ rest |
| BUS *n* ON | page 2, CC 75+*n* | ✔ BUS1, ◐ rest |
| AUX *n* fader (n = 1-8) | page 2, MSB CC 20+*n*, LSB CC 52+*n* | ✔ AUX1-2, ◐ rest |
| AUX *n* ON | page 2, CC 110+*n* (111-118) | ✔ AUX1, ◐ rest |
| EQ gain, frequency, Q | pages 3-10 (two pages per band), see below | ✔ |
| HPF ON, LPF ON | page 11, CC 63+*index* (HPF) and Q-style CC (LPF) | ✔ |
| EQ ON | page 13, Q-style CC | ◐ |

**Fader scale:** the page works with 0-1023 (10 bits) and sends `value << 4` as 14 bits. **0 dB = 860.**

**EQ CCs.** Band *b* (0 low, 1 low-mid, 2 high-mid, 3 high) uses page `3 + 2b` (input 1-24) and the next
page for inputs 25-32. On that page: gain = MSB CC *i* / LSB CC *i*+32, frequency = CC 63+*i*, Q = CC 88+*i*
(for *i* ≤ 7) or 94+*i*; *i* is the input's index on the page (1-24). Frequency and Q are 7-bit.

## 3. SysEx

### Frames

```
Request:  F0 43 3n 3E 7F 01  ee pp cc  F7
Reply:    F0 43 1n 3E 7F 01  ee pp cc  d3 d2 d1 d0  F7
Write:    F0 43 1n 3E 7F 01  ee pp cc  d3 d2 d1 d0  F7      (same as a reply)
```

`n` = device number (console Rx channel − 1). `ee` = element, `pp` = parameter, `cc` = channel (input *k* → *k*−1).
The data is **four 7-bit bytes, big-endian, two's complement** (28 bits): a gain of −18.0 dB (−180) is
`7F 7F 7E 4C`. The universal model byte `7F` with address `01` ("edit buffer") answers; the same request with
model byte `0D` does not. Replies to requests that the console cannot answer simply do not arrive.

Requests answered about 6 ms apart worked reliably; the page paces them like that.

### Parameters

| Element | Parameter (`pp`) | Meaning and scale | Confidence |
|---|---|---|---|
| 28 | 0 | Channel **fader** level, coarse 0-255 scale (table below) | ✔ |
| 26 | 0 | Channel **ON**: 1 = on, 0 = off | ✔ |
| 32 | 1, 2, 3 | EQ **low** band: Q, frequency, gain | ✔ |
| 32 | 5, 6, 7 | EQ **low-mid**: Q, frequency, gain | ✔ |
| 32 | 8, 9, 10 | EQ **high-mid**: Q, frequency, gain | ✔ |
| 32 | 11, 12, 13 | EQ **high**: Q, frequency, gain | ✔ |
| 32 | 4 / 14 / 15 | **HPF ON** / **LPF ON** / **EQ ON**: 1 or 0 | ✔ |
| 31 | 1 | **Compressor on**: 1 = on, 0 = off | ✔ |
| 31 | 4 | Attack, 0-120 = milliseconds | ✔ |
| 31 | 5 | Release, step 0-159 (table below) | ✔ |
| 31 | 6 | Ratio, step 0-15 (table below) | ✔ |
| 31 | 7 | Output gain, 0-180 = 0 to +18.0 dB (0.1 dB) | ✔ |
| 31 | 8 | Knee, 0 = hard, 1-5 | ✔ |
| 31 | 9 | Threshold, −540 to 0 = −54.0 to 0 dB (0.1 dB) | ✔ |
| 35 | 3n−2 | **AUX *n* send**: PRE/POST (0 = post, 1 = pre) | ✔ AUX1-3, ◐ rest |
| 35 | 3n−1 | **AUX *n* send**: level (0-255, same scale as the fader) | ✔ AUX1-3, ◐ rest |
| 1 | 0-15 | Scene title, one ASCII character per parameter | ✔ (read only) |
| 88 | 0-15 | Effect name, channel `cc` = effect number | ✔ (read only) |
| 79 | 0 | **Lead:** announced with `cc` = 1 while the stereo master fader moves; the value looks like the 0-255 fader scale. Might be a way to read the stereo master fader. | ? |

Element 35 also has `pp` 0, 3, 6, ... (one per aux) that always read 1. This console has no per-send ON
switch, so they were left alone. Element 31 `pp` 0 reads 1 and is probably the dynamics type; not used.

**Fader / send level scale** (console value → the 0-1023 scale of the CC path):
`0→0, 1→0, 6→50, 8→100, 17→200, 38→300, 81→430, 134→600, 189→760, 216→860 (0 dB), 237→950, 255→1023`
(linear in between). The console reports 1 for −∞.

**EQ values**
- Gain: units of 0.1 dB, ±180, i.e. ±18 dB. Relation to the CC value `c` (0-16383): `gain = (c − 8192) / 45`.
- Frequency: step `v` = CC value + 1, clipped to 5-124. 120 steps (1/12 octave) from 21.2 Hz to 20 kHz.
- Q: step `v` 0-40 is a bell with `Q = 10^(1 − v/20)` (v = 0 → 10, v = 40 → 0.10). On the **low and high**
  bands the same parameter also selects the filter type: **41 = shelf**, **42-44 = HPF (low) / LPF (high)** (44 was seen).
  The CC value maps to `v` at about 0.5 step per CC value on those bands (about 0.33 on the mid bands). The
  HIGH band's types are assumed to mirror the LOW band's.

**Compressor tables**
- Ratio steps 0-15: `1:1, 1.1:1, 1.4:1, 1.5:1, 1.7:1, 2:1, 2.5:1, 3:1, 3.5:1, 4:1, 5:1, 6:1, 8:1, 10:1, 20:1, ∞:1`
- Release steps, measured points (the rest is roughly logarithmic): `0→5 ms, 10→50 ms, 20→112 ms, 40→261 ms, 60→603 ms,
  80→1.37 s, 100→3.41 s, 120→6.19 s, 140→19.1 s, 159→42.4 s`

### Changes the console announces

When a parameter that is **not** in the CC table is changed on the console, it sends a SysEx Parameter Change
in the reply format above (for example compressor and send changes). That is how the page follows the console
live without polling.

### Things that did **not** work

- **Channel names:** not found over MIDI. They are not in elements 1-127 of the edit buffer (those hold scene
  and effect names), changing one on the console sends nothing, and elements above 127 gave no replies (only one byte order for the two-byte element number was tried).
  The setup memory (model `0D`, address `03`) holds patch and port names but no channel names.
- Master fader and master ON have no SysEx address that we know of; their startup state is only learned from
  CC when you touch them.
- Parameter requests with model byte `0D` and address `01` get no answer (use `7F`).

## 4. Meters

```
Request:  F0 43 3n 3E 0D 21  UL LU LL  CH CL  F7      (start address, count)
Reply:    F0 43 1n 3E 0D 21  UL LU LL  <H L> <H L> ...  F7     (14-bit value per meter)
```

The console then streams the values every 50 ms for **10 seconds**; re-request every 8 s. Several requests can be
active at the same time (this project runs five). The raw value 4095 is 0 dB.

| Block (start address) | Count | Meaning | Confidence |
|---|---|---|---|
| `0x0000` | 40 | Input level, input *k* at address *k*−1 | ✔ |
| `0x0080`, `0x0100`, `0x0200` | 40 | The same inputs at other metering points | ✔ (unused) |
| `0x0180` | 40 | **Compressor gain reduction**, input *k* at `0x180`+*k*−1; 4095 = none, lower = more reduction | ✔ address, scale ◐ |
| `0x8000` | 8 | **AUX 1-8** output level | ✔ AUX1, ◐ rest |
| `0x4000` | 8 | **BUS 1-8** output level | ✔ BUS1, ◐ rest |
| `0x10000` | 2 | **Stereo master** left, right | ✔ |
| `0x4180`, `0x8180`, `0x10180` | 8 / 8 / 2 | Gain reduction of buses / auxes / stereo | ? (read 4095, unused) |

For output blocks the `+0x80` and `+0x100` copies repeated the same values; the stereo block's `+0x100` copy read
lower (2667 against 3414), so it is another metering point.

**Level scale** (raw → dB, measured with a steady 1 kHz tone against the console's own meter; it is almost
linear in dB, about 41 steps per dB near the top):
`0→−100, 2145→−48, 2852→−30, 3394→−18, 3587→−12, 3848→−6, 4095→0`.
The gain-reduction scale is assumed to be the same 41 steps per dB: `reduction_dB = (4095 − raw) / 41`
(a 9 dB reading on the console's own display would confirm it; `GR_STEPS_PER_DB` adjusts it).

## 5. How this was found

By experiment, mostly in this order: change **one** thing on the console, scan or watch the SysEx replies, diff.
For parameters the console announces by itself, simply listening while moving a control shows the address.
Scales were then calibrated by writing known values and reading the console's display. The tools are described in
[TOOLS.md](TOOLS.md); with them, checking another console is a matter of minutes per parameter.
