import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from . import protocol, meters as meters_mod
from .midi_out import MidiOut

NUM_CHANNELS = int(os.environ.get("CHANNELS", 24))
METER_HZ = 15
STATIC = os.path.join(os.path.dirname(__file__), "static")

midi = MidiOut()
meters = meters_mod.Meters()
decoder = protocol.Decoder()
loop: asyncio.AbstractEventLoop | None = None
# None = not known yet (filled by sync_from_console at startup, then by console feedback)
# Keys 101-108 / 201-208 are the AUX / BUS master faders and ON buttons (pseudo channels, see protocol.OUT_CHANNELS).
_FADER_KEYS = list(range(0, NUM_CHANNELS + 1)) + protocol.OUT_CHANNELS
state = {"fader": {c: None for c in _FADER_KEYS},   # 0 = master
         "mute": {c: None for c in _FADER_KEYS}}
# EQ state per input channel; None = unknown until the console reports it or we set it.
eq_state = {c: {**{b: {"gain": None, "freq": None, "q": None} for b in protocol.BANDS},
                "flags": {f: None for f in protocol.EQ_FLAGS}}
            for c in range(1, NUM_CHANNELS + 1)}
# Compressor values per input channel (raw console units, see protocol.DYN_RANGE); None = unknown.
dyn_state = {c: {p: None for p in protocol.DYN_PP} for c in range(1, NUM_CHANNELS + 1)}
# Aux sends: send_state[aux][ch] = {"level": UI scale 0..1023, "pre": 0/1}; None = unknown.
# Read lazily, per aux, when a browser opens that aux tab (see sync_aux).
send_state = {a: {c: {"level": None, "pre": None} for c in range(1, NUM_CHANNELS + 1)} for a in range(1, 9)}
# Names typed in the web page, shared by every browser and kept across restarts (the console's own channel
# names are not reachable over MIDI as far as we found). Key: channel 1..N, 0 = ST OUT, 101-108 = AUX n master,
# 201-208 = BUS n master.
NAMES_FILE = os.environ.get("NAMES_FILE", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "names.json"))
MAX_NAME = 24
NAME_KEYS = set(range(0, NUM_CHANNELS + 1)) | set(protocol.OUT_CHANNELS)


def _load_names() -> dict[int, str]:
    try:
        with open(NAMES_FILE, encoding="utf-8") as f:
            return {int(k): str(v)[:MAX_NAME] for k, v in json.load(f).items() if int(k) in NAME_KEYS and str(v).strip()}
    except (OSError, ValueError, TypeError):
        return {}


def _save_names() -> None:
    tmp = NAMES_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in sorted(names.items())}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, NAMES_FILE)          # atomic: a power cut never leaves half a file
    except OSError as e:
        print("could not save names:", e)


names = _load_names()
clients: set[WebSocket] = set()


def on_midi(msg):
    """MIDI input thread: meters + console-originated fader/mute changes."""
    meters.on_message(msg)
    events = decoder.feed(msg)
    if events and loop:
        loop.call_soon_threadsafe(lambda: asyncio.create_task(apply_console_events(events)))


async def apply_console_events(events):
    for kind, ch, val in events:
        if kind in ("fader", "mute"):
            if ch not in state["fader"]:
                continue
        elif ch > NUM_CHANNELS:
            continue
        if kind == "send":
            aux, what, v = val
            if send_state[aux][ch][what] != v:
                send_state[aux][ch][what] = v
                await broadcast({"type": "send", "ch": ch, "aux": aux, "kind": what, "value": v})
            continue
        if kind == "dyn":
            param, v = val
            if dyn_state[ch][param] != v:
                dyn_state[ch][param] = v
                await broadcast({"type": "dyn", "ch": ch, "param": param, "value": v})
            continue
        if kind == "eq":
            band, param, v = val
            if eq_state[ch][band][param] != v:
                eq_state[ch][band][param] = v
                await broadcast({"type": "eq", "ch": ch, "band": band, "param": param, "value": v})
            continue
        if kind == "eqflag":
            flag, on = val
            if eq_state[ch]["flags"][flag] != on:
                eq_state[ch]["flags"][flag] = on
                await broadcast({"type": "eqflag", "ch": ch, "flag": flag, "on": on})
            continue
        key = "fader" if kind == "fader" else "mute"
        if state[key][ch] == val:
            continue
        state[key][ch] = val
        await broadcast({"type": kind, "ch": ch,
                         "value": state["fader"][ch], "muted": state["mute"][ch]})


async def broadcast(payload, skip=None):
    for c in list(clients):
        if c is skip:
            continue
        try:
            await c.send_json(payload)
        except Exception:
            clients.discard(c)


midi.open_input(on_midi)


async def meter_loop():
    last_req = 0.0
    while True:
        await asyncio.sleep(1 / METER_HZ)
        if not clients:
            continue
        now = time.time()
        if midi.mock:
            meters.fake()
        elif now - last_req > meters_mod.REREQUEST_S:
            midi.send(meters_mod.requests())
            last_req = now
        aux, bus = meters.out_snapshot()
        payload = {"type": "meters", "v": meters.snapshot(NUM_CHANNELS), "gr": meters.gr_snapshot(NUM_CHANNELS),
                   "aux": aux, "bus": bus, "st": meters.st_snapshot()}
        for c in list(clients):
            try:
                await c.send_json(payload)
            except Exception:
                clients.discard(c)


async def sync_from_console():
    """Ask the console for every channel's fader, ON state and 4-band EQ. Replies arrive
    on the MIDI input thread and go through on_midi -> apply_console_events (updates
    state and all browsers). Needs Parameter Change TX/RX ON on the console."""
    if midi.mock:
        return
    for ch in range(1, NUM_CHANNELS + 1):
        for req in protocol.request_state(ch):
            midi.send([req])
            await asyncio.sleep(0.006)     # don't flood the console's MIDI input (tools use the same pace)


async def sync_aux(aux: int):
    """Read every channel's send level and PRE/POST for one aux (about 0.3 s). Replies are handled
    like any console message, so the browsers update themselves."""
    if midi.mock:
        return
    for ch in range(1, NUM_CHANNELS + 1):
        for req in protocol.request_sends(ch, aux):
            midi.send([req])
            await asyncio.sleep(0.006)


@asynccontextmanager
async def lifespan(app):
    global loop
    loop = asyncio.get_running_loop()
    task = asyncio.create_task(meter_loop())
    sync = asyncio.create_task(sync_from_console())
    yield
    task.cancel()
    sync.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/meters")
def api_meters():
    """Diagnostics: the latest meter values the server holds (only refreshed while a browser page is open).
    gr = gain reduction raw, 4095 = none; reduction dB = (4095 - raw) / gr_steps_per_db."""
    return {"inputs": meters.snapshot(NUM_CHANNELS), "gr": meters.gr_snapshot(NUM_CHANNELS),
            "gr_steps_per_db": meters_mod.GR_STEPS_PER_DB, "mock": midi.mock}


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    clients.add(sock)
    await sock.send_json({"type": "init", "channels": NUM_CHANNELS,
                          "fader_max": protocol.FADER_MAX, "state": state, "eq": eq_state, "dyn": dyn_state,
                          "sends": send_state, "names": {str(k): v for k, v in names.items()},
                          "eq_max": {"gain": protocol.EQ_GAIN_MAX, "freq": protocol.EQ_7BIT_MAX,
                                     "q": protocol.EQ_7BIT_MAX},
                          "meter_cal": meters_mod.CALIBRATION, "gr_steps_per_db": meters_mod.GR_STEPS_PER_DB,
                          "meter_floor_db": meters_mod.FLOOR_DB})
    try:
        while True:
            m = await sock.receive_json()
            if m.get("type") == "sync":       # client asks to re-read the console
                asyncio.create_task(sync_from_console())
                continue
            if m.get("type") == "name":       # a name typed in a browser: keep it and tell every browser
                try:
                    nch = int(m.get("ch", -1))
                    nname = str(m.get("name", "")).strip()[:MAX_NAME]
                except (ValueError, TypeError):
                    continue
                if nch in NAME_KEYS:
                    if nname:
                        names[nch] = nname
                    else:
                        names.pop(nch, None)
                    _save_names()
                    await broadcast({"type": "name", "ch": nch, "name": nname})
                continue
            if m.get("type") == "sync_aux":   # client opened an aux tab: read that aux's sends
                aux = int(m.get("aux", 0))
                if 1 <= aux <= 8:
                    asyncio.create_task(sync_aux(aux))
                continue
            ch = int(m.get("ch", 0))
            if not (0 <= ch <= NUM_CHANNELS or (m.get("type") in ("fader", "mute") and ch in protocol.OUT_CHANNELS)):
                continue
            try:
                if m["type"] == "send":
                    if ch == 0:
                        continue
                    aux, kind = int(m["aux"]), m["kind"]
                    lo, hi = protocol.SEND_RANGE[kind]            # KeyError for unknown kinds -> ignored below
                    v = max(lo, min(hi, int(m["value"])))
                    midi.send(protocol.send_param(ch, aux, kind, v))      # ValueError for aux outside 1..8
                    send_state[aux][ch][kind] = v
                    await broadcast({"type": "send", "ch": ch, "aux": aux, "kind": kind, "value": v}, skip=sock)
                    continue
                if m["type"] == "dyn":
                    if ch == 0:
                        continue
                    param = m["param"]
                    lo, hi = protocol.DYN_RANGE[param]       # KeyError for unknown params -> ignored below
                    v = max(lo, min(hi, int(m["value"])))
                    midi.send(protocol.dyn_param(ch, param, v))
                    dyn_state[ch][param] = v
                    await broadcast({"type": "dyn", "ch": ch, "param": param, "value": v}, skip=sock)
                    continue
                if m["type"] in ("eq", "eqflag"):
                    if ch == 0:
                        continue
                    if m["type"] == "eq":
                        band, param = m["band"], m["param"]
                        v = int(m["value"])
                        msgs = protocol.eq_param(ch, band, param, v)   # validates band/param
                        mx = protocol.EQ_GAIN_MAX if param == "gain" else protocol.EQ_7BIT_MAX
                        v = max(0, min(mx, v))
                        midi.send(msgs)
                        eq_state[ch][band][param] = v
                        out = {"type": "eq", "ch": ch, "band": band, "param": param, "value": v}
                    else:
                        flag, on = m["flag"], bool(m["on"])
                        midi.send(protocol.eq_flag(ch, flag, on))
                        eq_state[ch]["flags"][flag] = on
                        out = {"type": "eqflag", "ch": ch, "flag": flag, "on": on}
                    await broadcast(out, skip=sock)
                    continue
                if m["type"] == "fader":
                    v = max(0, min(protocol.FADER_MAX, int(m["value"])))
                    midi.send(protocol.fader(ch, v))
                    state["fader"][ch] = v
                elif m["type"] == "mute":
                    muted = bool(m["muted"])
                    midi.send(protocol.mute(ch, on=not muted))
                    state["mute"][ch] = muted
                else:
                    continue
            except NotImplementedError as e:
                await sock.send_json({"type": "error", "message": str(e)})
                continue
            except (ValueError, KeyError, TypeError):
                continue    # malformed message from a client: ignore
            await broadcast({"type": m["type"], "ch": ch,   # keep other browsers in sync
                             "value": state["fader"][ch], "muted": state["mute"][ch]}, skip=sock)
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(sock)


app.mount("/static", StaticFiles(directory=STATIC), name="static")
