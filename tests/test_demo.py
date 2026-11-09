"""Demo mode (MIDI_PORT=mock DEMO=1): a fully populated, deterministic, made-up mix."""
import importlib
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def demo_server(tmp_path, monkeypatch):
    monkeypatch.setenv("NAMES_FILE", str(tmp_path / "names.json"))
    monkeypatch.setenv("DEMO", "1")
    import server.app as app_module
    app_module = importlib.reload(app_module)
    with TestClient(app_module.app) as client:
        yield app_module, client, tmp_path


def test_demo_is_off_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("NAMES_FILE", str(tmp_path / "names.json"))
    monkeypatch.delenv("DEMO", raising=False)
    import server.app as app_module
    app_module = importlib.reload(app_module)
    assert app_module.DEMO is False and app_module.state["fader"][1] is None


def test_everything_is_filled_in(demo_server):
    app, client, _ = demo_server
    with client.websocket_connect("/ws") as ws:
        init = ws.receive_json()
    fader, mute = init["state"]["fader"], init["state"]["mute"]
    keys = [str(c) for c in range(0, 25)] + [str(c) for c in (*range(101, 109), *range(201, 209))]
    assert all(fader[k] is not None and mute[k] is not None for k in keys)
    assert init["names"]["1"] == "Kick" and init["names"]["0"] == "Main" and init["names"]["101"] == "Mon Drums"
    eq = init["eq"]["1"]
    assert all(eq[b][p] is not None for b in ("low", "lomid", "himid", "high") for p in ("gain", "freq", "q"))
    assert eq["flags"] == {"eq": True, "hpf": True, "lpf": False}
    assert init["eq"]["18"]["flags"]["hpf"] is False                      # the click track has no high-pass filter
    assert init["dyn"]["1"]["on"] == 1 and init["dyn"]["3"]["on"] == 0
    assert all(init["sends"][str(a)]["1"]["level"] is not None for a in range(1, 9))


def test_values_are_in_range_and_deterministic(demo_server):
    app, client, _ = demo_server
    first = json.dumps([app.state, app.eq_state, app.dyn_state, app.send_state, app.names], sort_keys=True, default=str)
    from server import protocol as P
    for ch, dyn in app.dyn_state.items():
        for param, (lo, hi) in P.DYN_RANGE.items():
            assert lo <= dyn[param] <= hi, (ch, param, dyn[param])
    for ch, eq in app.eq_state.items():
        assert all(0 <= eq[b]["gain"] <= P.EQ_GAIN_MAX and 0 <= eq[b]["freq"] <= 127 and 0 <= eq[b]["q"] <= 127
                   for b in P.BANDS)
    assert all(0 <= v <= P.FADER_MAX for v in app.state["fader"].values())
    again = importlib.reload(app)
    assert json.dumps([again.state, again.eq_state, again.dyn_state, again.send_state, again.names],
                      sort_keys=True, default=str) == first


def test_demo_names_are_never_saved(demo_server):
    app, client, tmp_path = demo_server
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "name", "ch": 2, "name": "Snare top"})
        import time
        end = time.time() + 2
        while app.names.get(2) != "Snare top" and time.time() < end:
            time.sleep(0.01)
    assert app.names[2] == "Snare top"                                    # the change is live in the demo
    assert not (tmp_path / "names.json").exists()                          # but never written to disk
