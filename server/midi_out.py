import os
import mido


def _match(names, want):
    m = [n for n in names if want.lower() in n.lower()]
    if not m:
        raise RuntimeError(f"No MIDI port matching '{want}'. Found: {names}. "
                           "Set MIDI_PORT=<substring> or MIDI_PORT=mock.")
    return m[0]


class MidiOut:
    """Opens the console's USB MIDI port. MIDI_PORT=mock logs instead of sending."""

    def __init__(self):
        self.want = os.environ.get("MIDI_PORT", "01V96")
        self.mock = self.want.lower() == "mock"
        self.port = None
        self.inport = None
        if not self.mock:
            name = _match(mido.get_output_names(), self.want)
            self.port = mido.open_output(name)
            print("MIDI out:", name)
        else:
            print("MIDI out: MOCK (no hardware)")

    def open_input(self, callback):
        """Listen to the console (used for meters). No-op in mock mode."""
        if self.mock:
            return
        name = _match(mido.get_input_names(), self.want)
        self.inport = mido.open_input(name, callback=callback)
        print("MIDI in:", name)

    def send(self, msgs):
        for msg in msgs:
            if self.port:
                self.port.send(msg)
            else:
                print("MOCK send:", msg.hex())
