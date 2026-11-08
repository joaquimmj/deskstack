"""The plugin's files: manifests, skills, agents, vendored scripts (platform rules in docs/PLATFORM_NOTES_REVIEW_LAYER.md)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from demo_models import build_demo  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "deskstack"
SKILLS = sorted(p.parent for p in (PLUGIN / "skills").glob("*/SKILL.md"))


def frontmatter(path: Path) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", path.read_text(), re.S)
    assert m, f"{path} has no frontmatter"
    return dict(re.findall(r"^([A-Za-z-]+):\s*(.*)$", m.group(1), re.M))


def test_marketplace_points_at_the_plugin():
    mk = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    pl = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    assert mk["name"] and mk["owner"]["name"]
    entry = next(p for p in mk["plugins"] if p["name"] == pl["name"])
    assert (ROOT / entry["source"]).resolve() == PLUGIN
    assert ".." not in entry["source"]


def test_names_follow_the_rules():
    pl = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    for name in [pl["name"]] + [s.name for s in SKILLS]:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name), name
        assert "claude" not in name and "anthropic" not in name and "gstack" not in name, name


def test_no_top_level_bin_and_readme_license():
    assert not (PLUGIN / "bin").exists()  # claude.ai and Cowork refuse a plugin with a top-level bin/
    assert len((PLUGIN / "README.md").read_text().split()) >= 40
    assert (PLUGIN / "LICENSE").exists()


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_skill_frontmatter(skill):
    fm = frontmatter(skill / "SKILL.md")
    assert fm["name"] == skill.name
    assert 0 < len(fm["description"]) <= 200, len(fm["description"])  # claude.ai upload limit


def test_agents_are_read_only_reviewers():
    for name in ("associate", "vp-review", "md-redteam"):
        fm = frontmatter(PLUGIN / "agents" / f"{name}.md")
        assert fm["name"] == name and fm["description"]
        assert {"Write", "Edit"} <= {t.strip() for t in fm["disallowedTools"].split(",")}


def test_skills_that_run_scripts_say_so_and_ship_them():
    for skill in SKILLS:
        text = (skill / "SKILL.md").read_text()
        if "scripts/deskstack.py" in text:
            assert (skill / "scripts" / "deskstack.py").exists(), skill.name


def test_vendored_copies_are_current():
    r = subprocess.run([sys.executable, str(ROOT / "plugins" / "sync_vendor.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("skill", ["analyst", "associate", "vp-review", "md-redteam", "compliance", "sign-off"])
def test_launcher_runs_without_any_installed_package(tmp_path, skill):
    """-I -S: no user site, no site-packages. Only the vendored copy can provide openpyxl."""
    model = build_demo("hardcode-in-formula", tmp_path)
    launcher = PLUGIN / "skills" / skill / "scripts" / "deskstack.py"
    r = subprocess.run([sys.executable, "-I", "-S", str(launcher), "check", str(model)], capture_output=True, text=True, cwd=tmp_path)
    assert "DS001" in r.stdout, r.stdout + r.stderr
    r = subprocess.run([sys.executable, "-I", "-S", str(launcher), "extract", str(model)], capture_output=True, text=True, cwd=tmp_path)
    assert json.loads(r.stdout)["counts"]["filed"] == 14, r.stderr
