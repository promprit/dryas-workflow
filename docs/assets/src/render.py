#!/usr/bin/env python3
"""Render one image source to PNG at 2x with headless Chrome.
Usage: python3 docs/assets/src/render.py <name> <css-width> <css-height> [themed|single]
Set CHROME to use another Chrome or Chromium binary."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def shot(name, w, h, query, dest):
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                    "--window-size=%s,%s" % (w, h), "--virtual-time-budget=10000", "--screenshot=" + dest,
                    "file://" + os.path.join(HERE, name + ".html") + query],
                   check=True, capture_output=True, timeout=120)
    print(dest)


def main(argv):
    name, w, h = argv[1], argv[2], argv[3]
    mode = argv[4] if len(argv) > 4 else "themed"
    if mode == "single":
        shot(name, w, h, "", os.path.join(OUT, name + ".png"))
    else:
        for theme in ("light", "dark"):
            shot(name, w, h, "?theme=" + theme, os.path.join(OUT, "%s-%s.png" % (name, theme)))


if __name__ == "__main__":
    main(sys.argv)
