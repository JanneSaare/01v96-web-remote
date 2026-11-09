## What does this change?

<!-- A sentence or two. Link the issue it fixes, if there is one. -->

## How was it tested?

- [ ] `pytest` passes (no console needed)
- [ ] Tried in mock mode (`MIDI_PORT=mock`)
- [ ] Tried on a real console: *which model and firmware?*

## Checklist

- [ ] New protocol knowledge is in `server/protocol.py` or `server/meters.py` with a comment on how it was found and how sure it is, and [docs/PROTOCOL.md](../blob/main/docs/PROTOCOL.md) is updated (✔ seen on hardware / ◐ assumed)
- [ ] A test covers new protocol code, ideally with a message a real console sent
- [ ] No Yamaha manuals or text copied from them (they are copyrighted)
- [ ] No personal data (names, e-mail addresses, network details) in the files or the logs I pasted
