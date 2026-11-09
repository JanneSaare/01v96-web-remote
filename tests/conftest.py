"""Test setup: run everything in the server's mock mode (no MIDI hardware needed)."""
import os
import pathlib
import sys

os.environ["MIDI_PORT"] = "mock"          # must be set before server.app is imported
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
