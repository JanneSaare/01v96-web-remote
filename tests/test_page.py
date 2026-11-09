"""The web page is one HTML file with an inline script and no build step, so check the script at least parses."""
import pathlib
import re
import shutil
import subprocess

import pytest

PAGE = pathlib.Path(__file__).resolve().parent.parent / "server" / "static" / "index.html"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_page_script_is_valid_javascript(tmp_path):
    html = PAGE.read_text(encoding="utf-8")
    script = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    js = tmp_path / "page.js"
    js.write_text(script, encoding="utf-8")
    result = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_page_has_the_main_views():
    html = PAGE.read_text(encoding="utf-8")
    for text in ("AUX OUT", "BUS OUT", "COMP ON", "eqgraph", "dyngraph"):
        assert text in html
