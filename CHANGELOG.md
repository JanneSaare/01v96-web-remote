# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [0.1.0] - first public version

### Added
- Browser remote for the Yamaha 01V96 V2 over USB MIDI, running on a Raspberry Pi (or any computer in mock mode).
- Faders and mutes for input channels 1-24, the stereo master, and the AUX 1-8 and BUS 1-8 masters, both directions.
- Startup read-back of the console's state over SysEx (faders, ON, EQ, compressor, AUX sends).
- EQ page with a response graph (bell, shelf, HPF and LPF), and a compressor page with a transfer curve.
- AUX send views and a `?aux=n` link that shows one monitor mix only.
- Level meters (inputs, AUX, BUS, stereo master) and compressor gain-reduction bars.
- Channel, master, AUX and BUS names, shared between all browsers and kept on the server.
- Protocol notes in `docs/PROTOCOL.md` and the tools used to find them in `tools/`.
- Automated tests (no console needed) and a CI workflow.

### Known limitations
- Developed against a single console; AUX 4-8 sends and some AUX/BUS master numbers are extrapolated.
- Channel names cannot be written to the console (no way found over MIDI).
