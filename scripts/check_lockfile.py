"""Checks that a fresh install of requirements.txt matches the lockfile.

Usage (CI, .github/workflows/ci.yml):
    pip install -r requirements.txt -c requirements.lock.txt   # in a fresh venv
    pip freeze > /tmp/fresh.lock
    python scripts/check_lockfile.py requirements.lock.txt /tmp/fresh.lock

Every package in the fresh install must be pinned in the lockfile at the
same version. A package the lockfile does not pin means requirements.txt
gained a dependency the lockfile was not regenerated for. Extra pins in the
lockfile (not needed by requirements.txt) are allowed. Exit code 1 on a
mismatch, with one line per package.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def _canonical(name: str) -> str:
    # PEP 503: "Google_ADK" and "google-adk" are the same package.
    return re.sub(r"[-_.]+", "-", name).lower()


def read_pins(text: str) -> dict[str, str]:
    """{package: version} from `pip freeze` style lines ("name==1.2.3")."""
    pins: dict[str, str] = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name, sep, version = line.partition("==")
        if sep:
            pins[_canonical(name.split("[", 1)[0].strip())] = version.split(";", 1)[0].strip()
    return pins


def mismatches(locked: dict[str, str], installed: dict[str, str]) -> list[str]:
    problems = []
    for name, version in sorted(installed.items()):
        if name not in locked:
            problems.append(f"{name}=={version} is installed but not pinned in the lockfile")
        elif locked[name] != version:
            problems.append(f"{name}: lockfile pins {locked[name]}, the install got {version}")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    locked = read_pins(Path(argv[1]).read_text(encoding="utf-8"))
    installed = read_pins(Path(argv[2]).read_text(encoding="utf-8"))
    problems = mismatches(locked, installed)
    for problem in problems:
        print(f"::error::{problem}")
    if problems:
        print("requirements.lock.txt is stale. Regenerate it (docs/06-configuration-reference.md) and commit it.")
        return 1
    print(f"lockfile OK: all {len(installed)} installed packages are pinned at the same version")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
