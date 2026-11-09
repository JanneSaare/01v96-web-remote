# Contributing

Thanks for your interest! This project is small and was built around a single console, so the most valuable
contributions are **reports from other consoles and firmware versions**, and **new parameters** found with the tools.

## Reporting what works (or doesn't) on your console

Please open an issue and choose the **Console report** form (the checklist in [docs/TESTING.md](docs/TESTING.md)
lists what is worth trying). It asks for:

- your console model and firmware version (01V96 V2? version number from the console's UTILITY screen),
- what you tried, and what happened,
- if something is wrong, the output of `tools/cc_sniff.py` while you move the control on the console.

The tables in [docs/PROTOCOL.md](docs/PROTOCOL.md) mark rows as ✔ (seen on hardware) or ◐ (extrapolated). Confirming
or correcting a ◐ row (for example AUX 4-8 sends, or the AUX/BUS master numbers) is a great first contribution.

## Finding new parameters

Follow the method in [docs/TOOLS.md](docs/TOOLS.md): listen with `cc_sniff.py`, otherwise scan and diff. If you find
an address, please share the raw output (the lines that changed) together with what you changed on the console.

## Code changes

```bash
pip install -r requirements-dev.txt
pytest
```

The tests run without a console (the server's `MIDI_PORT=mock` mode). To try the page by hand without a console,
start it with `MIDI_PORT=mock DEMO=1` (a made-up mix); `tools/make_screenshots.py` regenerates the README pictures. Run them before sending a pull request,
and add a test for new protocol code: the tests in `tests/test_protocol.py` use messages that a real console sent,
so a new parameter is easy to add the same way.

A few guidelines:

- Keep the **protocol knowledge in `server/protocol.py` and `server/meters.py`**, with a comment saying how it was
  found and how sure it is. Do not copy text from Yamaha's manuals into the repository.
- **Do not commit Yamaha's PDF manuals** (they are copyrighted); link to them instead.
- The web page is a single file, `server/static/index.html`, with no build step. Keep it that way.
- Say in the pull request how you tested the change (mock mode only, or on a real console).

## Behaviour

Please follow the [code of conduct](CODE_OF_CONDUCT.md). Security problems are reported privately, see [SECURITY.md](SECURITY.md).

## Licence

By contributing you agree that your contribution is licensed under the [MIT licence](LICENSE) like the rest.
