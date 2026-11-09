"""The web server end to end in mock mode: websocket messages in, state and MIDI out, console events back."""
import importlib
import json
import time

import mido
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("NAMES_FILE", str(tmp_path / "names.json"))
    import server.app as app_module
    app_module = importlib.reload(app_module)          # fresh state and a fresh names file for every test
    with TestClient(app_module.app) as client:
        yield app_module, client


def wait_for(condition, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.01)
    return False


def next_of_type(ws, kind, limit=200):
    for _ in range(limit):
        msg = ws.receive_json()
        if msg["type"] == kind:
            return msg
    raise AssertionError(f"no {kind!r} message arrived")


def test_init_message(server):
    app, client = server
    with client.websocket_connect("/ws") as ws:
        init = ws.receive_json()
    assert init["type"] == "init" and init["channels"] == 24
    assert set(init) >= {"state", "eq", "dyn", "sends", "names", "meter_cal", "gr_steps_per_db"}
    assert "101" in init["state"]["fader"] and "208" in init["state"]["mute"]       # AUX / BUS masters
    assert sorted(init["sends"], key=int) == [str(n) for n in range(1, 9)]


def test_fader_and_mute_from_the_page(server):
    app, client = server
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "fader", "ch": 3, "value": 860})
        ws.send_json({"type": "mute", "ch": 3, "muted": True})
        ws.send_json({"type": "fader", "ch": 103, "value": 500})       # AUX 3 master
        ws.send_json({"type": "mute", "ch": 208, "muted": True})       # BUS 8 master
        ws.send_json({"type": "fader", "ch": 150, "value": 5})          # not a channel: ignored
        ws.send_json({"type": "mute", "ch": 109, "muted": True})        # AUX 9 does not exist: ignored
        assert wait_for(lambda: app.state["mute"][208] is True)
    assert app.state["fader"][3] == 860 and app.state["mute"][3] is True
    assert app.state["fader"][103] == 500
    assert 150 not in app.state["fader"] and 109 not in app.state["mute"]


def test_console_events_reach_the_browser(server):
    app, client = server
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        for hexs in ("B1 15 29", "B1 35 10"):                           # AUX 1 master fader moved on the console
            app.on_midi(mido.Message.from_hex(hexs))
        msg = next_of_type(ws, "fader")
        assert msg["ch"] == 101
        app.on_midi(mido.Message.from_hex("B1 4C 00"))                  # BUS 1 ON switched off
        msg = next_of_type(ws, "mute")
        assert msg["ch"] == 201 and msg["muted"] is True


def test_compressor_and_sends_from_the_page(server):
    app, client = server
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "dyn", "ch": 1, "param": "threshold", "value": -250})
        ws.send_json({"type": "dyn", "ch": 1, "param": "ratio", "value": 99})           # clamps to 15
        ws.send_json({"type": "dyn", "ch": 1, "param": "bogus", "value": 5})            # ignored
        ws.send_json({"type": "send", "ch": 1, "aux": 2, "kind": "level", "value": 860})
        ws.send_json({"type": "send", "ch": 1, "aux": 2, "kind": "pre", "value": 1})
        ws.send_json({"type": "send", "ch": 1, "aux": 9, "kind": "level", "value": 5})  # no AUX 9: ignored
        assert wait_for(lambda: app.send_state[2][1]["pre"] == 1)
    assert app.dyn_state[1]["threshold"] == -250 and app.dyn_state[1]["ratio"] == 15
    assert app.send_state[2][1]["level"] == 860


def test_names_are_saved_shared_and_survive_a_restart(server, tmp_path):
    app, client = server
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "name", "ch": 1, "name": "  Vocal  "})
        ws.send_json({"type": "name", "ch": 0, "name": "Main"})
        ws.send_json({"type": "name", "ch": 103, "name": "Mon 3"})
        ws.send_json({"type": "name", "ch": 2, "name": "x" * 60})        # cut to 24 characters
        ws.send_json({"type": "name", "ch": 999, "name": "nope"})        # not a channel: ignored
        ws.send_json({"type": "name", "ch": "abc", "name": "nope"})      # garbage must not kill the connection
        ws.send_json({"type": "name", "ch": 3, "name": "Keys"})
        assert wait_for(lambda: app.names.get(3) == "Keys")
        ws.send_json({"type": "name", "ch": 3, "name": "   "})           # empty = back to the default
        assert wait_for(lambda: 3 not in app.names)
    saved = json.loads((tmp_path / "names.json").read_text(encoding="utf-8"))
    assert saved == {"0": "Main", "1": "Vocal", "2": "x" * 24, "103": "Mon 3"}
    with client.websocket_connect("/ws") as second_device:
        assert second_device.receive_json()["names"]["1"] == "Vocal"
    assert importlib.reload(app).names[1] == "Vocal"                      # after a server restart


def test_meters_message_has_all_blocks(server):
    app, client = server
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        msg = next_of_type(ws, "meters")
    assert len(msg["v"]) == 24 and len(msg["gr"]) == 24
    assert len(msg["aux"]) == 8 and len(msg["bus"]) == 8 and len(msg["st"]) == 2


def test_meter_diagnostics_endpoint(server):
    app, client = server
    data = client.get("/api/meters").json()
    assert data["mock"] is True and len(data["inputs"]) == 24 and data["gr_steps_per_db"] == 41


def test_page_is_served(server):
    app, client = server
    html = client.get("/").text
    assert "01V96 Remote" in html and "BUS OUT" in html
