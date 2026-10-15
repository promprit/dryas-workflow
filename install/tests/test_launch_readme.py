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
        self.assertGreaterEqual(t.count("```"), 6)  # macOS/Linux, Windows and first-command blocks are separate

    def test_extras_only_in_credits(self):
        t = readme()
        body = t.split("## Credits", 1)[0]
        for s in ("Ruflo", "Superpowers", "--with-ruflo", "--with-superpowers", "rough edges"):
            self.assertNotIn(s, body, s)
        self.assertNotIn("<!-- scorecard:start -->", t)

    def test_proof_numbers(self):
        t = readme().split("## Proof: we ship with it", 1)[1].split("\n## ", 1)[0]
        for s in ("1,036", "1,556", "150", "7 to 14 October 2026", "Not a benchmark", "docs/assets/flowobserve.jpg", "docs/judge-scorecard.md"):
            self.assertIn(s, t, s)


if __name__ == "__main__":
    unittest.main()
