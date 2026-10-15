import re
import struct
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ASSETS = REPO / "docs" / "assets"
SRC = ASSETS / "src"
MAX_BYTES = 307200
# name: (css width, css height, themed)
IMAGES = {"hero": (1600, 400, True), "loop": (1600, 420, True), "ladder": (1400, 440, True),
          "social-preview": (1280, 640, False)}


def png_size(p):
    b = p.read_bytes()[:24]
    assert b[:8] == b"\x89PNG\r\n\x1a\n", p
    return struct.unpack(">II", b[16:24])


def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def theme_vars(css, selector):
    block = css.split(selector, 1)[1].split("}", 1)[0]
    return dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{6})", block))


class LaunchAssetsTest(unittest.TestCase):
    def files(self, name, themed):
        return [ASSETS / ("%s-%s.png" % (name, t)) for t in ("light", "dark")] if themed else [ASSETS / ("%s.png" % name)]

    def test_pngs_exist_at_2x(self):
        for name, (w, h, themed) in IMAGES.items():
            for p in self.files(name, themed):
                self.assertTrue(p.is_file(), p)
                self.assertEqual(png_size(p), (2 * w, 2 * h), p)
                self.assertLessEqual(p.stat().st_size, MAX_BYTES, p)

    def test_sources_use_brand_variables_only(self):
        for name in IMAGES:
            t = (SRC / ("%s.html" % name)).read_text(encoding="utf-8")
            self.assertIn("_brand.css", t, name)
            self.assertIsNone(re.search(r"#[0-9A-Fa-f]{3,6}\b", t), name + ": raw colour, use a --variable")
            for bad in ("gradient", "box-shadow", "text-shadow", "blur(", "drop-shadow"):
                self.assertNotIn(bad, t, name)

    def test_palette_contrast_meets_aa(self):
        css = (SRC / "_brand.css").read_text(encoding="utf-8")
        for selector in (":root {", ':root[data-theme="dark"] {'):
            v = theme_vars(css, selector)
            for fg, bg in (("--ink", "--ground"), ("--ink-2", "--ground"), ("--accent-ink", "--accent-ground")):
                self.assertGreaterEqual(contrast(v[fg], v[bg]), 4.5, "%s %s on %s" % (selector, fg, bg))

    def test_hero_copy(self):
        t = (SRC / "hero.html").read_text(encoding="utf-8")
        self.assertIn("DRYAS", t)
        self.assertIn("scope lock: src/billing/invoice.ts is outside the scope of active task(s) 2", t)
        self.assertNotIn("Rules your AI agents can't ignore.", t)  # the README H1 carries the headline
        self.assertNotIn("STUDIO", t)

    def test_label_sizes_readable(self):
        import re as _re
        for name, floor in (("loop", 26), ("ladder", 24)):
            t = (SRC / ("%s.html" % name)).read_text(encoding="utf-8")
            sizes = [float(s) for s in _re.findall(r"font-size:\s*([0-9.]+)px", t)]
            self.assertTrue(sizes, name)
            self.assertGreaterEqual(min(sizes), floor, name)


if __name__ == "__main__":
    unittest.main()
