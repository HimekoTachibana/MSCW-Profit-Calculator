#!/usr/bin/env python3
"""Print the CHANGELOG.md section for a version (used for GitHub release notes).

Usage:
    python scripts/release_notes.py 1.0.0      # also accepts v1.0.0
    python scripts/release_notes.py --check v1.0.0
        Exit non-zero unless the tag matches __version__ in profit_calculator.py
        AND CHANGELOG.md has a non-empty section for it.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def app_version():
    with open(os.path.join(ROOT, "profit_calculator.py"), encoding="utf-8") as f:
        m = re.search(r'^__version__\s*=\s*"([^"]+)"', f.read(), re.M)
    return m.group(1) if m else None


def changelog_section(version):
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"^## \[" + re.escape(version) + r"\][^\n]*\n(.*?)(?=^## \[|^\[[^\]]+\]: |\Z)",
                  text, re.M | re.S)
    return m.group(1).strip() if m else ""


def main(argv):
    check = "--check" in argv
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    version = args[0].lstrip("v")
    notes = changelog_section(version)
    if check:
        problems = []
        if app_version() != version:
            problems.append(f"tag is {version} but profit_calculator.py has __version__ = {app_version()}")
        if not notes:
            problems.append(f"CHANGELOG.md has no entry for [{version}]")
        for p in problems:
            print("ERROR:", p, file=sys.stderr)
        return 1 if problems else 0
    if not notes:
        print(f"No CHANGELOG.md entry for {version}", file=sys.stderr)
        return 1
    print(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
