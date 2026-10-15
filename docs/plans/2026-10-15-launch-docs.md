# Launch docs — Implementation Plan

> **For agentic workers:** run with `/orchestrate` on this file (Dryas). Each `## Task N:` section is self-contained: its Goal/Scope/Done/Failing-test lines are the `.orchestrate/PLAN.md` contract; Interfaces and Steps follow. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Rewrite the repo's public face (README, docs landing, pitch docs, images) so Dryas markets itself as the product it is, with every claim true today.

**Architecture:** Docs-only change. Images are HTML sources in `docs/assets/src/` sharing one brand stylesheet, rendered to PNG by headless Google Chrome through `docs/assets/src/render.py`. Content moved out of the README lands in `docs/` first (Task 3), then the README is rewritten (Task 4). Python `unittest` tests in `install/tests/` pin each deliverable; existing doc tests that pinned old README text are updated in the task that moves the text.

**Tech Stack:** Markdown, HTML/CSS, headless Google Chrome (`/Applications/Google Chrome.app`, already installed), macOS `sips`, Python 3.9+ stdlib tests run with `python3 -m pytest`.

**Spec:** `docs/specs/2026-10-15-launch-docs-design.md`

## Global Constraints

- Docs only: no change to code, flags, hooks, `claude/CLAUDE.md.template`, Codex copies, the spec (`spec/dryas-spec-v1.md`), `NOTICE.md` or `GLOSSARY.md`. Tests in `install/tests/`, image sources in `docs/assets/src/` and the rendered images in `docs/assets/` are the only non-Markdown files written.
- Headline, verbatim: `Rules your AI agents can't ignore.` Hook line, verbatim: `Stop asking your agent to behave. Make it.` Problem headline, verbatim: `Brilliant agents. No discipline.`
- Banned words in `README.md`, `docs/README.md` and `docs/why-dryas.md` (case-insensitive): revolutionary, AI-powered, seamless, seamlessly, supercharge, unleash, game-changing, cutting-edge, blazing, effortless.
- No model names (Haiku, Sonnet, Opus, Fable) in prose of `README.md`, `docs/*.md` or `examples/*.md` outside backticks (`install/tests/test_tier_docs.py` enforces this). Use tiers: fast, standard, strong, frontier.
- British spelling (organisation, behaviour, licence as a noun).
- No private project, client or venture names anywhere (the pre-commit deny-term scan). Proof numbers are totals only.
- Proof numbers (window 2026-10-07 to 2026-10-15, studio logs): 1,154 tasks merged, 1,689 executor dispatches, 160 out-of-scope edits blocked. Test count wording: "over 2,000 tests" (2,042 collected on 2026-10-15).
- Palette: Paper `#EFEEE8`, District Green `#1B342C`, Shade `#10201B`, Driving Mist `#4A5D53`, Moss Pale `#C9CFC4`, Slate Grey `#7C8A83`, Earth Brown `#5C4A3F`. Earth Brown only for human-gate and denial markers. Slate Grey only for lines and dividers, never text.
- Brand rules: one stroke weight 3.4 units, round joins, no gradients, glow, bevel, shadow or blur. Product lockup: mark plus `DRYAS`, no subline.
- Fonts: Archivo 500 (wordmark and titles, caps; tracking 0.22em wordmark, 0.06em headings), JetBrains Mono 400/500 (labels, terminal), loaded from Google Fonts.
- Images: 2x device scale; each file at most 307200 bytes; light and dark PNG per image except `flowobserve.jpg` (dark only, JPEG to meet the size budget) and `social-preview.png` (one variant).
- Every file under 500 lines.

## Review Focus

- A visitor on GitHub's dark theme: every `<picture>` must serve a dark variant that exists, otherwise a light image glares or vanishes (Task 4 test `test_pictures_have_both_themes`).
- A reader with images off or a screen reader: every `<img>` has non-empty alt text and the README reads fully without images (Task 4 test `test_images_have_alt`).
- A broken path after files move: every relative link and image path in `README.md` and `docs/README.md` resolves (Task 3 `test_docs_index_links_resolve`, Task 4 `test_readme_paths_resolve`).
- A README claim drifting from the code: every command the README lists exists as a command or skill file (Task 4 test `test_listed_commands_exist`).
- A Windows visitor copying the install block: the PowerShell installer line is present next to the shell one (Task 4 test `test_install_block`).

---

## Task 1: Brand stylesheet, renderer and the hero, loop, ladder and social images

Goal: Create the shared brand stylesheet, the Chrome render script and the four brand images (hero, loop, ladder, social preview) in light and dark.
Scope:
- docs/assets/src/_brand.css
- docs/assets/src/render.py
- docs/assets/src/hero.html
- docs/assets/src/loop.html
- docs/assets/src/ladder.html
- docs/assets/src/social-preview.html
- docs/assets/hero-*.png
- docs/assets/loop-*.png
- docs/assets/ladder-*.png
- docs/assets/social-preview.png
- install/tests/test_launch_assets.py
Done:
- `python3 -m pytest -q install/tests/test_launch_assets.py` passes
- `python3 -m pytest -q claude/jev/tests install/tests` passes
Failing test first: install/tests/test_launch_assets.py :: LaunchAssetsTest.test_pngs_exist_at_2x

**Interfaces:**
- Consumes: nothing.
- Produces: `docs/assets/src/_brand.css` (CSS variables `--ground`, `--ink`, `--ink-2`, `--rule`, `--accent-ground`, `--accent-ink`, `--stroke`; dark values under `:root[data-theme="dark"]`); `python3 docs/assets/src/render.py <name> <width> <height> [themed|single]` writing `docs/assets/<name>-light.png` and `docs/assets/<name>-dark.png` (or `docs/assets/<name>.png` when themes is `single`); the PNG files listed in Scope.

- [ ] **Step 1: Write the failing test.** Create `install/tests/test_launch_assets.py`:

```python
import re
import struct
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ASSETS = REPO / "docs" / "assets"
SRC = ASSETS / "src"
MAX_BYTES = 307200
# name: (css width, css height, themed)
IMAGES = {"hero": (1600, 640, True), "loop": (1600, 420, True), "ladder": (1400, 520, True),
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
        for s in ("DRYAS", "Rules your AI agents can't ignore.", "Stop asking your agent to behave. Make it."):
            self.assertIn(s, t)
        self.assertNotIn("STUDIO", t)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q install/tests/test_launch_assets.py`. Expected: FAIL (`docs/assets/hero-light.png` missing, `_brand.css` missing).

- [ ] **Step 3: Write the brand stylesheet.** Create `docs/assets/src/_brand.css`:

```css
@import url("https://fonts.googleapis.com/css2?family=Archivo:wght@500&family=JetBrains+Mono:wght@400;500&display=block");

:root {
  --ground: #EFEEE8;
  --ink: #1B342C;
  --ink-2: #4A5D53;
  --rule: #7C8A83;
  --accent-ground: #5C4A3F;
  --accent-ink: #EFEEE8;
  --stroke: 3.4px;
}

:root[data-theme="dark"] {
  --ground: #10201B;
  --ink: #EFEEE8;
  --ink-2: #C9CFC4;
  --rule: #7C8A83;
  --accent-ground: #5C4A3F;
  --accent-ink: #EFEEE8;
}

* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: 100%; height: 100%; background: var(--ground); color: var(--ink); overflow: hidden; }
body { font-family: "JetBrains Mono", ui-monospace, monospace; -webkit-font-smoothing: antialiased; }
.display { font-family: Archivo, Helvetica, Arial, sans-serif; font-weight: 500; }
.wordmark { font-family: Archivo, Helvetica, Arial, sans-serif; font-weight: 500; letter-spacing: 0.22em; text-transform: uppercase; }
.heading { font-family: Archivo, Helvetica, Arial, sans-serif; font-weight: 500; letter-spacing: 0.06em; text-transform: uppercase; }
.mono { font-family: "JetBrains Mono", ui-monospace, monospace; }
.muted { color: var(--ink-2); }
.gate { background: var(--accent-ground); color: var(--accent-ink); font-family: "JetBrains Mono", monospace; font-weight: 500; letter-spacing: 0.08em; padding: 4px 10px; border-radius: 3px; }
svg .mark { fill: none; stroke: var(--ink); stroke-width: 3.4; stroke-linejoin: round; stroke-linecap: round; }
svg .line { fill: none; stroke: var(--rule); stroke-width: 3.4; stroke-linejoin: round; stroke-linecap: round; }
svg .ink { fill: none; stroke: var(--ink); stroke-width: 3.4; stroke-linejoin: round; stroke-linecap: round; }
svg .accent { fill: none; stroke: var(--accent-ground); stroke-width: 3.4; stroke-linejoin: round; stroke-linecap: round; }
```

Every image HTML starts with this head and theme switch (the query `?theme=dark` selects dark):

```html
<!doctype html>
<html><head><meta charset="utf-8"><link rel="stylesheet" href="_brand.css">
<script>if (new URLSearchParams(location.search).get("theme") === "dark") document.documentElement.dataset.theme = "dark";</script>
```

The Dryas mark (from `projects/dryas/brand-assets/dryas-symbol.svg`) is drawn inline with the `mark` class:

```html
<svg viewBox="0 0 120 120" width="72" height="72" aria-hidden="true"><g class="mark"><path d="M60 26 92 84H28Z"/><path d="M60 48 76 82H44Z"/><path d="M60 84V108"/></g></svg>
```

- [ ] **Step 4: Write the renderer.** Create `docs/assets/src/render.py` (Python, so it runs the same from any shell; headless Chrome gives exactly 2W x 2H at `--force-device-scale-factor=2`, checked 2026-10-15):

```python
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
```

- [ ] **Step 5: Write `docs/assets/src/hero.html` (1600x640).** Body is a 1600x640 box, padding 88px. Top left: the mark (72px) and `DRYAS` in `.wordmark` at 40px, side by side with a 24px gap. Vertically centred on the left, max width 1180px: `<h1 class="display">Rules your AI agents can't ignore.</h1>` at 92px, line-height 1.02, colour `--ink`; below it, 28px gap, `<p class="mono muted">Stop asking your agent to behave. Make it.</p>` at 30px. Bottom edge, 56px from the bottom: the seven stages as a row of `.mono` labels at 18px, letter-spacing 0.12em, uppercase, colour `--ink-2`, separated by a 3.4px `--rule` line segment 40px long: BRAINSTORM, PLAN, JUDGE, BUILD, ESCALATE, REVIEW, SHIP. BRAINSTORM and SHIP carry the `.gate` class instead of the muted colour.

- [ ] **Step 6: Write `docs/assets/src/loop.html` (1600x420).** An inline SVG `viewBox="0 0 1600 420"`. Seven nodes at x = 140, 360, 580, 800, 1020, 1240, 1460, y = 200: each a circle r=14 with class `ink` (Brainstorm and Ship circles class `accent`). One horizontal `line` path joins them (x 154 to 1446). Under each node at y=260, a `.heading` label at 20px: BRAINSTORM, PLAN, JUDGE, BUILD, ESCALATE, REVIEW, SHIP. Above Brainstorm and Ship at y=120, a `.gate` label `YOU APPROVE` (HTML positioned over the SVG). A return arc, class `ink`, from Escalate (1020,186) up and back to Build (800,186): `M1020 186 C1000 110 820 110 800 186`, with a `.mono muted` 16px label `climb a tier, retry` centred above it at y=100. Title top left at (64,64): `.heading` 18px muted `THE DRYAS LOOP`.

- [ ] **Step 7: Write `docs/assets/src/ladder.html` (1400x520).** An inline SVG `viewBox="0 0 1400 520"`. Four rising steps drawn as one `ink` path, each step 260 wide and 80 high, starting at (140,440): `M140 440 H400 V360 H660 V280 H920 V200 H1180`. Step labels in `.heading` 22px, left-aligned 20px inside each tread, 24px above it: FAST, STANDARD, STRONG, FRONTIER. Under each label in `.mono muted` 15px: `fast`, `standard`, `strong`, `frontier` tier examples `e.g. Haiku`, `e.g. Sonnet`, `e.g. Opus`, `e.g. Fable` (this text is inside the PNG only; it is not README prose). At each riser (x = 400, 660, 920) a small `accent` cross (two 14px strokes) marks the failure, with a `.mono muted` 14px label `failed → logged reason → next tier` once, under the first riser. By the top step at (1200,170), `.mono` 18px: `Stops at the first success.` Title top left at (64,64): `.heading` 18px muted `THE MODEL LADDER`.

- [ ] **Step 8: Write `docs/assets/src/social-preview.html` (1280x640).** Fixed dark ground: set `document.documentElement.dataset.theme = "dark"` unconditionally in its script so it renders reversed (Paper mark on Shade). Content inside a centred 1040x480 safe area: mark (88px) and `DRYAS` wordmark at 48px top left; `Rules your AI agents can't ignore.` in `.display` at 76px; `Stop asking your agent to behave. Make it.` in `.mono muted` at 26px; bottom line `.mono muted` 20px: `Claude Code · Codex · MIT`.

- [ ] **Step 9: Render.** Run:

```
python3 docs/assets/src/render.py hero 1600 640
python3 docs/assets/src/render.py loop 1600 420
python3 docs/assets/src/render.py ladder 1400 520
python3 docs/assets/src/render.py social-preview 1280 640 single
ls -l docs/assets/*.png
```

Expected: seven PNG files. Open each with the Read tool and check: fonts are Archivo and JetBrains Mono (not a serif fallback), nothing is clipped, the dark variants have the Shade ground. If a font fell back, re-run the render (the font fetch needs the network); if a file is over 307200 bytes, reduce flat areas of detail (no change of size).

- [ ] **Step 10: Run the tests.** Run: `python3 -m pytest -q install/tests/test_launch_assets.py && python3 -m pytest -q claude/jev/tests install/tests`. Expected: PASS.

- [ ] **Step 11: Commit** (explicit paths, `docs(assets): brand images for the launch README`) when the dispatch prompt allows it; otherwise report and the orchestrator commits.

## Task 2: Scope-lock card with real hook output, and the FlowObserve image

Goal: Render the scope-lock terminal card using the literal reason returned by `claude/jev/scope_lock.py`, and add the FlowObserve screenshot within the size budget.
Scope:
- docs/assets/src/scope-lock.html
- docs/assets/scope-lock-*.png
- docs/assets/flowobserve.jpg
- install/tests/test_launch_proof_assets.py
Done:
- `python3 -m pytest -q install/tests/test_launch_proof_assets.py` passes
- `python3 -m pytest -q claude/jev/tests install/tests` passes
Failing test first: install/tests/test_launch_proof_assets.py :: ProofAssetsTest.test_card_shows_real_deny_line

**Interfaces:**
- Consumes: `docs/assets/src/_brand.css` and `docs/assets/src/render.py` from Task 1; `scope_lock.check(root, path)` in `claude/jev/scope_lock.py`.
- Produces: `docs/assets/scope-lock-light.png`, `docs/assets/scope-lock-dark.png` (2800x1120), `docs/assets/flowobserve.jpg`.

- [ ] **Step 1: Write the failing test.** Create `install/tests/test_launch_proof_assets.py`:

```python
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "claude" / "jev"))
import scope_lock  # noqa: E402

ASSETS = REPO / "docs" / "assets"
MAX_BYTES = 307200


def real_deny_line():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".orchestrate").mkdir()
        (root / ".orchestrate" / "active.json").write_text(json.dumps({"active": [2]}), encoding="utf-8")
        (root / ".orchestrate" / "PLAN.md").write_text(
            "## Task 2: Rate-limit the login endpoint\n\nGoal: x\nScope:\n- src/auth/**\nDone:\n- y\n", encoding="utf-8")
        return scope_lock.check(str(root), str(root / "src" / "billing" / "invoice.ts"))


class ProofAssetsTest(unittest.TestCase):
    def test_card_shows_real_deny_line(self):
        line = real_deny_line()
        self.assertEqual(line, "scope lock: src/billing/invoice.ts is outside the scope of active task(s) 2")
        self.assertIn(line, (ASSETS / "src" / "scope-lock.html").read_text(encoding="utf-8"))

    def test_card_pngs(self):
        for t in ("light", "dark"):
            p = ASSETS / ("scope-lock-%s.png" % t)
            b = p.read_bytes()
            self.assertEqual(b[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", b[16:24]), (2800, 1120))
            self.assertLessEqual(len(b), MAX_BYTES, p)

    def test_flowobserve_jpeg(self):
        p = ASSETS / "flowobserve.jpg"
        b = p.read_bytes()
        self.assertEqual(b[:3], b"\xff\xd8\xff")
        self.assertLessEqual(len(b), MAX_BYTES)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q install/tests/test_launch_proof_assets.py`. Expected: FAIL on the missing `scope-lock.html` (the deny-line equality passes; if it does not, stop and report the actual line: the card must use whatever the hook really returns, and the spec's quoted line is then out of date).

- [ ] **Step 3: Write `docs/assets/src/scope-lock.html` (1400x560).** Same head and theme switch as Task 1 (`_brand.css`, `?theme=dark`). A terminal card filling the frame with 56px padding, a 3.4px `--rule` border, radius 10px; top bar `.mono muted` 16px: `executor · task 2 · scope src/auth/**`. Body `.mono` 22px, line-height 1.7, these lines in order:
  1. muted: `● Edit src/auth/rate_limit.ts`
  2. ink: `  ✓ in scope`
  3. muted: `● Edit src/billing/invoice.ts`
  4. a `.gate` span `DENIED` followed by the exact text `scope lock: src/billing/invoice.ts is outside the scope of active task(s) 2`
  5. muted: `● Edit src/auth/rate_limit.test.ts`
  6. ink: `  ✓ in scope`
  The deny text must be byte-identical to the test's `real_deny_line()`; the test checks it. No other copy in the image.

- [ ] **Step 4: Render and convert.** Set `FLOWOBSERVE_REPO` to the FlowObserve checkout (on the studio Mac it is the `flowobserve` folder next to the main `dryas-workflow` checkout under `projects/`). Run:

```
python3 docs/assets/src/render.py scope-lock 1400 560
sips -s format jpeg -s formatOptions 80 "$FLOWOBSERVE_REPO/docs/screenshot.png" --out docs/assets/flowobserve.jpg
ls -l docs/assets/scope-lock-*.png docs/assets/flowobserve.jpg
```

Expected: three files. If `flowobserve.jpg` is over 307200 bytes, re-run `sips` with `formatOptions 70`. Open the PNGs and the JPEG with the Read tool and check legibility in both themes.

- [ ] **Step 5: Run the tests.** Run: `python3 -m pytest -q install/tests/test_launch_proof_assets.py && python3 -m pytest -q claude/jev/tests install/tests`. Expected: PASS.

- [ ] **Step 6: Commit** (explicit paths, `docs(assets): scope-lock card from real hook output, FlowObserve image`) when the dispatch prompt allows it; otherwise report and the orchestrator commits.

## Task 3: Reference docs receive what leaves the README, the docs landing page and the deprecation banners

Goal: Move the README's reference material into `docs/` (install, adoption guide, a new judge scorecard page), add `docs/README.md`, and mark Ruflo and Superpowers deprecated in `docs/workflow.md` and `docs/install.md`.
Scope:
- docs/README.md
- docs/judge-scorecard.md
- docs/install.md
- docs/workflow.md
- docs/adoption-guide.md
- install/tests/test_launch_docs.py
- install/tests/test_owned_core_docs.py
- install/tests/test_public_docs.py
Done:
- `python3 -m pytest -q install/tests/test_launch_docs.py install/tests/test_owned_core_docs.py install/tests/test_public_docs.py` passes
- `python3 -m pytest -q claude/jev/tests install/tests` passes
Failing test first: install/tests/test_launch_docs.py :: LaunchDocsTest.test_scorecard_page_matches_generated

**Interfaces:**
- Consumes: the current `README.md` text (source of the moved sections), `reference/judge-corpus/SCORECARD.md`.
- Produces: `docs/judge-scorecard.md` with the `<!-- scorecard:start -->`/`<!-- scorecard:end -->` block; `docs/README.md`; `## Use it for yourself` in `docs/adoption-guide.md`; `## Reference stack` and `### Manual plugin route` in `docs/install.md`; the deprecation banner text below. Task 4 links to all of these.

- [ ] **Step 1: Write the failing tests.** Create `install/tests/test_launch_docs.py`:

```python
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BANNER = "Deprecated: removed in 2.2. Dryas memory and the Dryas skills replace them."


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def section(text, heading):
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


class LaunchDocsTest(unittest.TestCase):
    def test_scorecard_page_matches_generated(self):
        page = read("docs/judge-scorecard.md")
        block = page.split("<!-- scorecard:start -->")[1].split("<!-- scorecard:end -->")[0]
        card = read("reference/judge-corpus/SCORECARD.md")
        self.assertEqual(block.strip(), card[card.index("| Measure"):].strip())
        for s in ("gated in CI", "tools/judge_score.py", "reference/judge-corpus/"):
            self.assertIn(s, page)

    def test_docs_index_links_resolve(self):
        t = read("docs/README.md")
        targets = re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", t)
        self.assertGreaterEqual(len(targets), 20)
        for target in targets:
            if "://" not in target:
                self.assertTrue((REPO / "docs" / target).exists(), target)
        for door in ("## Use it", "## Understand it", "## Run it in a team", "## History"):
            self.assertIn(door, t)

    def test_deprecation_banners(self):
        w = read("docs/workflow.md")
        self.assertIn(BANNER, section(w, "## 7. "))
        self.assertIn(BANNER, section(w, "## 8. "))
        i = read("docs/install.md")
        self.assertGreaterEqual(i.count(BANNER), 1)
        self.assertIn("dryas memory import-ruflo", i)

    def test_moved_reference_material(self):
        i = read("docs/install.md")
        for s in ("## Reference stack", "### Manual plugin route", "/plugin marketplace add promprit/dryas-workflow",
                  "--no-design", "--no-pstack-picks", "--keep-extras"):
            self.assertIn(s, i, s)


if __name__ == "__main__":
    unittest.main()
```

In `install/tests/test_owned_core_docs.py`, change `test_readme_scorecard_matches` to read the new page (rename it `test_scorecard_page_matches`, replace `(ROOT / "README.md")` with `(ROOT / "docs/judge-scorecard.md")`). In `install/tests/test_public_docs.py`, change `test_readme_use_it_yourself` to read `docs/adoption-guide.md` instead of `README.md` (rename it `test_adoption_guide_use_it_yourself`; keep its four required strings and the `## Use it for yourself` heading check).

- [ ] **Step 2: Run them to see them fail.** Run: `python3 -m pytest -q install/tests/test_launch_docs.py install/tests/test_owned_core_docs.py install/tests/test_public_docs.py`. Expected: FAIL (`docs/judge-scorecard.md` and `docs/README.md` missing, no banner, no `## Use it for yourself` in the adoption guide).

- [ ] **Step 3: Write `docs/judge-scorecard.md`.**

```markdown
# Local judge scorecard

The local judge decides gate questions with deterministic rules: no key, no network. These are the numbers a keyless install gets, measured on a public corpus and gated in CI: a change that makes them worse fails the build.

## How it is measured

The corpus lives in `reference/judge-corpus/` and is original to this repo. Each command has a class: dangerous (must not be allowed), safe (must be allowed without a question) and tricky (quoting, wrappers and heredocs that hide a dangerous command or only look like one; each row names the verdict it should get). `python3 tools/judge_score.py` scores the judge against it; `--write` regenerates `reference/judge-corpus/SCORECARD.md`, and CI checks this page against that file. Latency (p95) is measured but not gated, because it depends on the machine.

## Today's numbers

<!-- scorecard:start -->
| Measure | Value |
|---|---|
| Commands in corpus | 79 |
| Edits in corpus | 21 |
| Missed dangerous commands | 14 |
| Deny downgraded to ask | 4 |
| Needless asks on safe commands | 0 |
| Always-judged files not judged | 1 |
<!-- scorecard:end -->

## Known gaps

The scorecard counts what the rules miss, in the open. Missed dangerous commands are commands the corpus marks dangerous that the local judge allows; each is a candidate rule, and `/tune` proposes corpus additions from real disagreements. For the strongest judgement, set `OPENROUTER_API_KEY` and use the Jev judge (`--judge jev`); the local judge stays the keyless default.
```

The table is today's `reference/judge-corpus/SCORECARD.md` from `| Measure` on; if that file changed since this plan was written, copy its current table instead (the test compares them after stripping).

- [ ] **Step 4: Move the README reference material into `docs/install.md`.** Add a `## Reference stack` section after `## Components` holding the README's "Reference stack" table and the FlowObserve paragraph below it, verbatim. Add `### Manual plugin route` at the end of `## Claude Code: plugin plus setup` holding the README's "Manual route, inside Claude Code" block and the paragraph after it, verbatim. Add the README's optional-flags block (`--judge`, `--with-ruflo`, `--with-superpowers`, `--no-design`) and the `--uninstall`/`--purge`/`--keep-extras` paragraph to `## Flags` and `### Uninstall and purge` where they are not already said; do not duplicate a sentence that is already there. Then put this banner as the first line under each heading or table row block that is about the Ruflo or Superpowers extras (at least the flag rows for `--with-ruflo` and `--with-superpowers`, and any `###` section about them):

```markdown
> Deprecated: removed in 2.2. Dryas memory and the Dryas skills replace them. Bring 1.x Ruflo memory across with `dryas memory import-ruflo`.
```

Keep the existing text below each banner unchanged: the flags work until 2.2, and `install/tests/test_owned_core_docs.py` requires `--with-ruflo`, `--with-superpowers` and `dryas memory import-ruflo` to stay in this file.

- [ ] **Step 5: Banners in `docs/workflow.md`.** Insert the same banner as the first paragraph under `## 7. Dryas memory, and the optional extra Ruflo` and under `## 8. Optional extra: Superpowers`. Change nothing else in the file.

- [ ] **Step 6: Move "Use it for yourself" into `docs/adoption-guide.md`.** Insert a `## Use it for yourself` section after `## 2. Fork it and make it yours`, holding the README's three numbered steps and the `~/.dryas/docs/dryas-local.md` sentence, verbatim. If section 2 already says the same thing, keep section 2 and make the new section the short version with a pointer to it; the four strings `Fork`, `claude/CLAUDE.md.template`, `docs/workflow.md`, `install/install.sh` must appear in it.

- [ ] **Step 7: Write `docs/README.md`.**

```markdown
# Dryas docs

Rules your AI agents can't ignore, in detail. Start with the door that fits.

## Use it

- [Install](install.md): Claude Code, Codex, Windows, WSL, every flag, upgrade and uninstall
- [Cloud sessions](cloud-sessions.md): run Dryas in claude.ai/code on any repo
- [Harnesses](harnesses.md): what each harness gets, and several accounts side by side
- [Workflow reference](workflow.md): the rules, hooks, commands and model policy in full
- [Release check](release-check.md): confirm a new machine is set up right
- [Judge scorecard](judge-scorecard.md): what the keyless judge catches, gated in CI

## Understand it

- [Why Dryas](why-dryas.md): the problems it solves, and what it is not
- [Architecture](architecture.md): five layers, one loop
- [Memory](memory-model.md) · [Governance](governance.md) · [Execution](execution-model.md) · [Escalation](escalation-model.md) · [Review](review-model.md): one doc per layer
- [Glossary](../GLOSSARY.md): every term in one place

## Run it in a team

- [Operating model](operating-model.md): the whole model on one page
- [Roles](roles.md): who holds each human decision, with a RACI
- [Metrics](metrics.md): KPIs per layer with healthy ranges
- [Adoption guide](adoption-guide.md): use it, fork it, maturity levels L0 to L4
- [Specification v1 (draft)](../spec/dryas-spec-v1.md): the rules any harness can implement
- [Reference map](../reference/README.md): how this repo implements each rule
- [Examples](../examples/README.md): a feature walked through the loop
- [Roadmap](roadmap.md): what ships next

## History

How each change was decided: [plans](plans/), [specs](specs/), [earlier specs and plans](superpowers/) and the [changelog](../CHANGELOG.md). Kept as a record, not as current docs.
```

- [ ] **Step 8: Run the tests.** Run: `python3 -m pytest -q install/tests/test_launch_docs.py install/tests/test_owned_core_docs.py install/tests/test_public_docs.py && python3 -m pytest -q claude/jev/tests install/tests`. Expected: PASS. (The README still holds its old copies until Task 4; that is fine.)

- [ ] **Step 9: Commit** (explicit paths, `docs: reference material out of the README, docs landing page, deprecation banners`) when the dispatch prompt allows it; otherwise report and the orchestrator commits.

## Task 4: README rewrite

Goal: Replace `README.md` with the launch README (spec section 3), about 150 lines, using the Task 1–3 images and pages.
Scope:
- README.md
- install/tests/test_launch_readme.py
- install/tests/test_owned_core_docs.py
Done:
- `python3 -m pytest -q install/tests/test_launch_readme.py install/tests/test_owned_core_docs.py` passes
- `python3 -m pytest -q claude/jev/tests install/tests` passes
Failing test first: install/tests/test_launch_readme.py :: LaunchReadmeTest.test_hero_and_order

**Interfaces:**
- Consumes: `docs/assets/{hero,loop,ladder,scope-lock}-{light,dark}.png`, `docs/assets/flowobserve.jpg` (Tasks 1–2); `docs/judge-scorecard.md`, `docs/README.md`, `docs/install.md#reference-stack`, `docs/adoption-guide.md` (Task 3).
- Produces: the new `README.md`.

- [ ] **Step 1: Write the failing test.** Create `install/tests/test_launch_readme.py`:

```python
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BANNED = ("revolutionary", "ai-powered", "seamless", "supercharge", "unleash", "game-changing",
          "cutting-edge", "blazing", "effortless")
ORDER = ["Rules your AI agents can't ignore.", "Stop asking your agent to behave. Make it.",
         "## Brilliant agents. No discipline.", "## Asked vs enforced", "## The loop", "## Install in 60 seconds",
         "## What you get", "## Proof: we ship with it", "## For teams", "## Works with", "## Credits"]


def readme():
    return (REPO / "README.md").read_text(encoding="utf-8")


class LaunchReadmeTest(unittest.TestCase):
    def test_hero_and_order(self):
        t = readme()
        pos = [t.find(s) for s in ORDER]
        self.assertNotIn(-1, pos, [s for s, p in zip(ORDER, pos) if p < 0])
        self.assertEqual(pos, sorted(pos))
        self.assertLessEqual(len(t.splitlines()), 170)

    def test_no_banned_words(self):
        low = readme().lower()
        for w in BANNED:
            self.assertNotIn(w, low, w)

    def test_readme_paths_resolve(self):
        t = readme()
        paths = re.findall(r'(?:src|srcset)="([^"]+)"', t) + re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", t)
        for p in paths:
            if "://" not in p:
                self.assertTrue((REPO / p).exists(), p)

    def test_pictures_have_both_themes(self):
        t = readme()
        pictures = re.findall(r"<picture>(.*?)</picture>", t, re.S)
        self.assertGreaterEqual(len(pictures), 4)
        for pic in pictures:
            self.assertIn('media="(prefers-color-scheme: dark)"', pic)
            dark = re.search(r'srcset="([^"]+-dark\.png)"', pic).group(1)
            light = re.search(r'<img src="([^"]+-light\.png)"', pic).group(1)
            self.assertTrue((REPO / dark).is_file() and (REPO / light).is_file(), pic)

    def test_images_have_alt(self):
        for img in re.findall(r"<img [^>]*>", readme()):
            alt = re.search(r'alt="([^"]*)"', img)
            self.assertTrue(alt and len(alt.group(1)) >= 12, img)

    def test_listed_commands_exist(self):
        t = readme().split("## What you get", 1)[1].split("\n## ", 1)[0]
        cmds = set(re.findall(r"`/([a-z-]+)`", t))
        self.assertGreaterEqual(len(cmds), 7)
        for c in cmds:
            self.assertTrue((REPO / "claude/commands" / (c + ".md")).is_file()
                            or (REPO / "claude/skills" / c / "SKILL.md").is_file(), c)

    def test_install_block(self):
        t = readme().split("## Install in 60 seconds", 1)[1].split("\n## ", 1)[0]
        for s in ("git clone https://github.com/promprit/dryas-workflow", "install/install.sh", "install\\install.ps1",
                  "/orchestrate", "docs/install.md"):
            self.assertIn(s, t, s)

    def test_extras_only_in_credits(self):
        t = readme()
        body = t.split("## Credits", 1)[0]
        for s in ("Ruflo", "Superpowers", "--with-ruflo", "--with-superpowers", "rough edges"):
            self.assertNotIn(s, body, s)
        self.assertNotIn("<!-- scorecard:start -->", t)

    def test_proof_numbers(self):
        t = readme().split("## Proof: we ship with it", 1)[1].split("\n## ", 1)[0]
        for s in ("1,154", "1,689", "160", "Not a benchmark", "docs/assets/flowobserve.jpg", "docs/judge-scorecard.md"):
            self.assertIn(s, t, s)


if __name__ == "__main__":
    unittest.main()
```

In `install/tests/test_owned_core_docs.py`, replace `test_readme_positioning` with:

```python
    def test_readme_positioning(self):
        r = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Rules your AI agents can't ignore.", r)
        self.assertIn("target operating model", r)
        self.assertNotIn("built on Superpowers, Ruflo", r)
        self.assertIn("docs/install.md", r)
        i = (ROOT / "docs/install.md").read_text(encoding="utf-8")
        for flag in ("--with-ruflo", "--with-superpowers", "--judge"):
            self.assertIn(flag, i)
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q install/tests/test_launch_readme.py install/tests/test_owned_core_docs.py`. Expected: FAIL (headline and sections missing).

- [ ] **Step 3: Write `README.md`.** Replace the whole file with this text (keep it byte-exact except where a later test run shows a path is wrong):

````markdown
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/hero-dark.png"><img src="docs/assets/hero-light.png" alt="Dryas: rules your AI agents can't ignore." width="100%"></picture>

# Rules your AI agents can't ignore.

**Stop asking your agent to behave. Make it.**

Dryas turns Claude Code and Codex into a disciplined delivery team. It agrees the design before it writes code. It edits only the files its task names. It proves the tests pass. It pays for the big model only when the small one fails. Every rule is enforced by a hook, not hoped for in a prompt.

`v2` · MIT · Claude Code · Codex · Cloud sessions · macOS, Linux, Windows

## Brilliant agents. No discipline.

- They build before anyone agreed what.
- They tidy files nobody asked about, and parallel agents overwrite each other.
- They report tests they never ran.
- They spend big-model money on small-model questions.

## Asked vs enforced

| Your agent today | With Dryas |
| --- | --- |
| Told to plan first. Starts coding anyway. | **Design gate.** Nothing is built until you approve the design. |
| Told to stay in scope. Doesn't. | **Scope lock.** A hook denies edits outside the task's files.¹ |
| Says the tests pass. | **Proof, not claims.** Executors report what they ran; review and verification gate the merge. |
| Runs everything on the default model. | **Model ladder.** Cheapest first, a stronger model only after a failure, every step logged with its reason. |
| Installs, deletes and pushes on its own. | **Judge and human gates.** Risky commands are judged; installs, deletes, pushes, overwrites and settings changes always need you. |

¹ The lock covers the file-edit tools. A write from a shell command is asked about, not blocked.

<picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/scope-lock-dark.png"><img src="docs/assets/scope-lock-light.png" alt="A terminal: the scope lock denies an edit to src/billing/invoice.ts because it is outside task 2's scope." width="100%"></picture>

*The agent wasn't asked to stay in scope. It couldn't leave.*

<picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/ladder-dark.png"><img src="docs/assets/ladder-light.png" alt="The model ladder: fast, standard, strong, frontier. A task climbs only after a failure, and every climb is logged." width="100%"></picture>

The full comparison with installing skills side by side: [Why Dryas](docs/why-dryas.md).

## The loop

<picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/loop-dark.png"><img src="docs/assets/loop-light.png" alt="The Dryas loop: Brainstorm, Plan, Judge, Build, Escalate, Review, Ship. You approve the design and the ship." width="100%"></picture>

- **Brainstorm.** The design is settled with you before any code is written. You approve it.
- **Plan.** The design becomes small tasks, each with a file scope and a done check.
- **Judge.** A small judge answers narrow questions (is this command risky? which tier?) so the big model is called less.
- **Build.** Executors on the `fast` tier do each task in its own git worktree, test first.
- **Escalate.** A failed task climbs to `standard`, then `strong`. `frontier` only after `strong` fails. Each climb is logged with a reason.
- **Review.** Fresh reviewers check the diff, and the tests are run, before anything merges.
- **Ship.** You approve the merge.

## Install in 60 seconds

```
git clone https://github.com/promprit/dryas-workflow
cd dryas-workflow
install/install.sh          # macOS, Linux, WSL
install\install.ps1         # Windows (PowerShell)
```

Then, in Claude Code:

```
/orchestrate add rate limiting to the login endpoint
```

No API key. No Node. Python 3.9+ and git.

Codex: `install/install.sh --harness codex`. Cloud sessions on claude.ai/code: [docs/cloud-sessions.md](docs/cloud-sessions.md). Every flag, several accounts, upgrade and uninstall: [docs/install.md](docs/install.md).

## What you get

| Command | What it does |
| --- | --- |
| `/orchestrate` | Runs the loop on a task: brainstorm, plan, build, review |
| `/wreview` | Three fresh reviewers check the branch: spec, quality, over-engineering |
| `/interrogate` | Two-model adversarial review for contested changes |
| `/commit` | A judged commit; it never pushes |
| `/handoff` | Saves a scored summary so you can clear the context and carry on |
| `/tune` | Weekly: reads the logs and proposes guardrail changes |
| `/retro` | Proposes lessons from a finished task; never applies them |

Underneath: a local judge that needs no key, Dryas memory that remembers what was tried, and eight process skills (brainstorm, plan, tdd, debug, verify, review-request, review-receive, worktree). Terms: [glossary](GLOSSARY.md).

## Proof: we ship with it

Dryas Studio delivers every project with Dryas, Dryas 2.0 included. Our own logs, 7 to 15 October 2026:

**1,154 tasks merged · 1,689 executor dispatches · 160 out-of-scope edits blocked**

Not a benchmark. Just the work.

[<img src="docs/assets/flowobserve.jpg" alt="FlowObserve: four live sessions, each at its stage in the loop; one needs you." width="100%">](https://dryasstudio.com/demos/flowobserve/)

*[FlowObserve](https://github.com/promprit/flowobserve) live demo (sample data): every session's stage, and the one that needs you.*

Over 2,000 tests, with CI on macOS, Linux and Windows. The keyless judge is measured on a public corpus and gated in CI: [judge scorecard](docs/judge-scorecard.md). Built and run by [Dryas Studio](https://dryasstudio.com).

## For teams

Dryas is also a target operating model for AI software delivery: roles, a RACI, metrics with healthy ranges, maturity levels L0 to L4, and a draft specification any harness can implement. Formally, the Dryas Workflow Framework.

[Operating model](docs/operating-model.md) · [Architecture](docs/architecture.md) · [Roles](docs/roles.md) · [Metrics](docs/metrics.md) · [Adoption guide](docs/adoption-guide.md) · [Specification](spec/dryas-spec-v1.md) · [Reference map](reference/README.md) · [Examples](examples/README.md) · [All docs](docs/README.md)

## Works with

| Harness | Status |
| --- | --- |
| Claude Code | Shipping: plugin `dryas@dryas-workflow` |
| Codex | Shipping: plugin `dryas@dryas-workflow` |
| Claude Code cloud sessions | Shipping: `dryas cloud init` commits the core into your repo |
| OpenCode | Next, in 2.2 |
| Pi, Roo, Cursor | Later |

macOS, Linux, WSL and Windows. Details: [harnesses](docs/harnesses.md).

## Credits

- [Superpowers](https://github.com/obra/superpowers) by obra: the Dryas process skills are derived from it
- [Ruflo](https://github.com/ruvnet/ruflo) by ruvnet: 1.x Ruflo memory imports with `dryas memory import-ruflo`
- [Impeccable](https://github.com/pbakaus/impeccable) by pbakaus and [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) by nextlevelbuilder: the design skills
- [TypeSafe skills (Jev)](https://github.com/typesafe-ai/skills) by TypeSafe: the optional Jev judge
- [pstack](https://github.com/cursor/plugins/tree/main/pstack) by Lauren Tan, Claude Code port [pstack-claude](https://github.com/michael-denyer/pstack-claude) by Michael Denyer, and deslop from Cursor's cursor-team-kit (all MIT); skip them with `--no-pstack-picks`

Third-party code is fetched from upstream by the installer, except the adapted pstack files in `claude/pstack/` and the process skills derived from Superpowers (see [NOTICE.md](NOTICE.md)).

![ci](https://github.com/promprit/dryas-workflow/actions/workflows/ci.yml/badge.svg)

## License

MIT. See [LICENSE](LICENSE).
````

- [ ] **Step 4: Run the tests.** Run: `python3 -m pytest -q install/tests/test_launch_readme.py install/tests/test_owned_core_docs.py && python3 -m pytest -q claude/jev/tests install/tests`. Expected: PASS. `install/tests/test_tier_docs.py`, `test_framework_docs.py` and `test_pstack_docs.py` read the README too; if one fails, fix the README wording (never the test) and re-run.

- [ ] **Step 5: Commit** (explicit paths, `docs(readme): launch README`) when the dispatch prompt allows it; otherwise report and the orchestrator commits.

## Task 5: The pitch docs, roadmap, harnesses, contributing and changelog

Goal: Tighten `docs/why-dryas.md` as the long-form pitch, add the 2.2 entries to the roadmap and harnesses, drop "rough edges" wording, and add the CHANGELOG `Unreleased` entry.
Scope:
- docs/why-dryas.md
- docs/roadmap.md
- docs/harnesses.md
- CONTRIBUTING.md
- CHANGELOG.md
- install/tests/test_launch_pitch_docs.py
Done:
- `python3 -m pytest -q install/tests/test_launch_pitch_docs.py` passes
- `python3 -m pytest -q claude/jev/tests install/tests` passes
- `python3 tools/release_check.py --help` still runs and `python3 -m pytest -q install/tests/test_release_2_0.py install/tests/test_release_version.py` passes (the `Unreleased` heading must not be read as a version)
Failing test first: install/tests/test_launch_pitch_docs.py :: PitchDocsTest.test_why_dryas_opens_with_problem

**Interfaces:**
- Consumes: nothing from earlier tasks (can run in parallel with Task 3).
- Produces: the edited files in Scope.

- [ ] **Step 1: Write the failing test.** Create `install/tests/test_launch_pitch_docs.py`:

```python
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BANNED = ("revolutionary", "ai-powered", "seamless", "supercharge", "unleash", "game-changing",
          "cutting-edge", "blazing", "effortless")


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


class PitchDocsTest(unittest.TestCase):
    def test_why_dryas_opens_with_problem(self):
        t = read("docs/why-dryas.md")
        head = t.split("\n## ", 2)
        self.assertIn("Brilliant agents. No discipline.", head[0] + head[1][:400])
        self.assertNotIn("hardened on install", t)
        self.assertNotIn("Ruflo", t)
        self.assertNotIn("Superpowers", t)
        self.assertIn("OpenCode", t.split("## What Dryas is not", 1)[1])
        for w in BANNED:
            self.assertNotIn(w, t.lower(), w)

    def test_roadmap_and_harnesses(self):
        r = read("docs/roadmap.md")
        self.assertIn("2.2", r)
        self.assertIn("owned core", r)
        h = read("docs/harnesses.md")
        self.assertIn("| OpenCode | Next (2.2) |", h)

    def test_contributing(self):
        self.assertNotIn("rough edges", read("CONTRIBUTING.md"))

    def test_changelog_unreleased(self):
        c = read("CHANGELOG.md")
        u = c.index("## Unreleased")
        self.assertLess(u, c.index("## 2.0.1"))
        self.assertIn("### Docs", c[u:c.index("## 2.0.1")])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail.** Run: `python3 -m pytest -q install/tests/test_launch_pitch_docs.py`. Expected: FAIL.

- [ ] **Step 3: Edit `docs/why-dryas.md`.**
  - Replace the two opening paragraphs (under `# Why Dryas exists`, before `## The problems it solves`) with:

```markdown
**Brilliant agents. No discipline.** They build before anyone agreed what. They tidy files nobody asked about. They report tests they never ran. They spend big-model money on small-model questions.

Dryas fixes that with rules your agents can't ignore. It is a target operating model for AI software delivery (process, decision rights, roles, controls, cost rules and metrics) and a reference implementation that enforces it with hooks on Claude Code and Codex. The tools are replaceable. The model is the asset.
```

  - In `## Why not just install the skills?`: replace the paragraph's last sentence ("Dryas owns the core of those jobs and makes them one system; Superpowers, Ruflo and the Jev model stay available as optional extras.") with "Dryas owns the core of those jobs and makes them one system."; in the "One owner per job" row, delete the sentence starting "When an extra such as Superpowers is added"; delete the whole row starting `| **Each tool's defaults ship as they are.**`.
  - In `## What Dryas is not`, first bullet: replace "Pi, OpenCode, Roo and Cursor are planned." with "OpenCode is next, in 2.2; Pi, Roo and Cursor are planned."
  - Check the whole file for any remaining "Ruflo" or "Superpowers" and reword those sentences without them.

- [ ] **Step 4: Edit `docs/roadmap.md`.** Rename `## Later: an OpenCode edition (parked 2026-10-15)` to `## Next: 2.2, the OpenCode edition` and add, as the first paragraph under it: "2.2 ships the OpenCode edition and removes the optional Ruflo and Superpowers extras: Dryas memory and the Dryas skills replace them, and `dryas memory import-ruflo` stays for 1.x memory." Leave the rest of that section unchanged.

- [ ] **Step 5: Edit `docs/harnesses.md`.** In the table at the top, replace the row `| Pi, OpenCode, Roo, Cursor | Later |` with two rows: `| OpenCode | Next (2.2) |` and `| Pi, Roo, Cursor | Later |`. In `## Later`, replace "Pi, OpenCode, Roo and Cursor are planned, not started." with "OpenCode is in progress for 2.2. Pi, Roo and Cursor are planned, not started."

- [ ] **Step 6: Edit `CONTRIBUTING.md`.** Remove any "rough edges" wording if present (the README carried it; `CONTRIBUTING.md` may not). Change nothing else.

- [ ] **Step 7: Edit `CHANGELOG.md`.** Insert above `## 2.0.1 - 2026-10-15`:

```markdown
## Unreleased

### Docs
- The README is rewritten for launch: what Dryas does in one line, the problem, asked vs enforced, the loop, a 60-second install, the commands, proof from our own logs, and the operating model for teams. Brand images in `docs/assets/` (light and dark), with their sources in `docs/assets/src/`.
- New `docs/README.md` (docs landing page) and `docs/judge-scorecard.md` (the scorecard moved out of the README).
- Ruflo and Superpowers are marked deprecated in `docs/install.md` and `docs/workflow.md`; they are removed in 2.2 with the OpenCode edition.

```

- [ ] **Step 8: Run the tests.** Run: `python3 -m pytest -q install/tests/test_launch_pitch_docs.py install/tests/test_release_2_0.py install/tests/test_release_version.py && python3 -m pytest -q claude/jev/tests install/tests`. Expected: PASS.

- [ ] **Step 9: Commit** (explicit paths, `docs: tighter why-dryas, 2.2 in roadmap and harnesses, changelog`) when the dispatch prompt allows it; otherwise report and the orchestrator commits.

## Task 6: Launch verification and design critique

Goal: Prove the launch is done (spec section 8) and run the design critique on the rendered images and the README as GitHub shows it.
Scope:
- none (review)
Done:
- `python3 -m pytest -q claude/jev/tests install/tests` passes, and `python3 -m pytest --collect-only -q claude/jev/tests install/tests claude/ruflo/tests | tail -1` reports at least 2,000 tests
- `python3 tools/inventory.py --check` reports 0 problems
- The proof numbers recount to 1,154 / 1,689 / 160 with the spec section 4 method (or the README is updated to the recount)
- Light and dark screenshots of the README on the pushed `docs/launch` branch show every image, legible
- `impeccable` and `ui-ux-pro-max` critiques have no unresolved material finding
Failing test first: none (review)

**Interfaces:**
- Consumes: everything from Tasks 1–5.
- Produces: a verification report; fix tasks for any finding.

- [ ] **Step 1: Suite and inventory.** Run: `python3 -m pytest -q claude/jev/tests install/tests && python3 tools/inventory.py --check`. Expected: all pass, `0 problems`.
- [ ] **Step 2: Recount the proof numbers.** Run:

```sh
python3 - <<'EOF'
import json, os
L = os.path.expanduser("~/.dryas/jev/logs")
def rows(f): return [json.loads(l) for l in open(os.path.join(L, f)) if l.strip()]
inw = lambda x: "2026-10-07" <= (x.get("ts") or "")[:10] <= "2026-10-15"
print(sum(int(x.get("tasks_merged") or 0) for x in rows("merge.jsonl") if inw(x)),
      sum(1 for x in rows("dispatch.jsonl") if inw(x) and x.get("phase") != "return"),
      sum(1 for x in rows("scope.jsonl") if inw(x) and x.get("decision") == "deny"))
EOF
```

Expected: `1154 1689 160`.
- [ ] **Step 3: Push and look.** `git push -u origin docs/launch` (standing rule allows feature branches). With the Playwright browser, open `https://github.com/promprit/dryas-workflow/tree/docs/launch`, screenshot the README with `browser_emulate_media` colour scheme `light` and then `dark`, and check each image loads and switches theme.
- [ ] **Step 4: Design critique.** Run `impeccable` (critique) and `ui-ux-pro-max` on the PNGs in `docs/assets/` and the two README screenshots. Material findings become fix tasks scoped to `docs/assets/src/*` and the re-rendered PNGs (Task 1 or 2 tests must still pass).
- [ ] **Step 5: Report** the evidence for each Done line.

## After merge (orchestrator, with Promprit)

Not executor tasks. The GitHub wording was approved with the spec (2026-10-15); still confirm before running, because it is outward-facing.

1. Ask before opening the PR `docs/launch → main`; it merges after CI passes on macOS, Ubuntu and Windows.
2. After the merge:

```sh
gh repo edit promprit/dryas-workflow \
  --description "Rules your AI agents can't ignore. Design-first, scope-locked, test-proven delivery for Claude Code and Codex, enforced by hooks." \
  --homepage "https://dryasstudio.com" \
  --remove-topic target-operating-model --remove-topic llm-governance --remove-topic developer-workflow \
  --add-topic claude-code-plugin --add-topic coding-agents --add-topic ai-coding --add-topic guardrails \
  --add-topic claude-code-hooks --add-topic tdd --add-topic model-routing --add-topic git-worktrees
```

3. Give Promprit the social preview steps: repo Settings → General → Social preview → Edit → upload `docs/assets/social-preview.png`.
