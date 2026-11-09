"""Take the README screenshots from the demo mix (no console needed).

Starts the server in demo mode (MIDI_PORT=mock DEMO=1), opens the page in a real browser, clicks through the main
views and saves PNG files to docs/images/. Run it again whenever the page changes.

    pip install playwright            # only this tool needs it; the browser itself is not downloaded
    python tools/make_screenshots.py [--browser msedge|chrome] [--out docs/images]

It uses the Edge or Chrome that is already installed on your computer.
"""
import argparse
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--browser", default="msedge", help="installed browser to use: msedge or chrome")
ap.add_argument("--out", default=str(ROOT / "docs" / "images"))
ap.add_argument("--width", type=int, default=1280)
ap.add_argument("--height", type=int, default=760)
a = ap.parse_args()
out = pathlib.Path(a.out)
out.mkdir(parents=True, exist_ok=True)

with socket.socket() as s:                       # a free port
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
url = f"http://127.0.0.1:{port}"
env = dict(os.environ, MIDI_PORT="mock", DEMO="1")
server = subprocess.Popen([sys.executable, "-m", "uvicorn", "server.app:app", "--port", str(port)], cwd=ROOT, env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(100):                         # wait until the server answers
        try:
            urllib.request.urlopen(url, timeout=0.5)
            break
        except OSError:
            time.sleep(0.1)
    else:
        sys.exit("the server did not start")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=a.browser, headless=True)
        page = browser.new_page(viewport={"width": a.width, "height": a.height})
        page.goto(url)
        page.wait_for_selector("#dot.ok")
        page.wait_for_selector(".strip")

        def shot(name, pause=1.2):
            page.wait_for_timeout(int(pause * 1000))           # let the meters move and the canvas draw
            page.screenshot(path=str(out / f"{name}.png"))
            print("saved", out / f"{name}.png")

        mode = lambda label: page.get_by_role("button", name=label, exact=True).click()
        shot("mix")
        page.set_viewport_size({"width": 1280, "height": 640})          # GitHub's social preview size (upload it in
        shot("social-preview", pause=0.5)                                # the repository settings, not used by the README)
        page.set_viewport_size({"width": a.width, "height": a.height})
        mode("AUX 1"); shot("aux-sends")
        mode("BUS OUT"); shot("bus-masters")
        mode("MIX")
        page.locator("#tabs button").nth(1).click()            # channels 9-16
        page.locator("button.eqbtn", has_text="EQ").nth(5).click()   # strip 14 (Lead)
        page.wait_for_selector("#eq:not([hidden])")
        shot("eq")
        page.click("#eqclose")
        page.locator("button.eqbtn", has_text="DYN").nth(5).click()
        page.wait_for_selector("#dyn:not([hidden])")
        shot("compressor", pause=2.0)
        browser.close()
finally:
    server.terminate()
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()
