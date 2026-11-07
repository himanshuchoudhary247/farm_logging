"""scripts/check_lockfile.py: the CI check that a fresh install of
requirements.txt (with the lockfile as constraints) matches the lockfile."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "check_lockfile", Path(__file__).resolve().parent.parent / "scripts" / "check_lockfile.py")
check_lockfile = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_lockfile)

LOCK = "boto3==1.43.125\nGoogle_ADK==2.13.0\nmcp==2.3.0\npytest==9.2.0\n"


def _run(tmp_path, lock, fresh):
    (tmp_path / "lock.txt").write_text(lock, encoding="utf-8")
    (tmp_path / "fresh.txt").write_text(fresh, encoding="utf-8")
    return check_lockfile.main(["check_lockfile.py", str(tmp_path / "lock.txt"), str(tmp_path / "fresh.txt")])


def test_a_matching_install_passes_and_extra_pins_are_allowed(tmp_path):
    assert _run(tmp_path, LOCK, "boto3==1.43.125\ngoogle-adk==2.13.0\nmcp==2.3.0\n") == 0


def test_a_package_the_lockfile_does_not_pin_fails(tmp_path, capsys):
    assert _run(tmp_path, LOCK, "boto3==1.43.125\nnewlib==1.0\n") == 1
    assert "newlib==1.0 is installed but not pinned" in capsys.readouterr().out


def test_a_different_version_fails(tmp_path, capsys):
    assert _run(tmp_path, LOCK, "boto3==1.44.0\n") == 1
    assert "boto3: lockfile pins 1.43.125, the install got 1.44.0" in capsys.readouterr().out


def test_names_are_compared_the_pip_way():
    assert check_lockfile.read_pins("Google_ADK==2.13.0\nzope.interface==7.0  # note\n-e .\n\n") == {
        "google-adk": "2.13.0", "zope-interface": "7.0"}


def test_the_real_lockfile_pins_every_requirement():
    """Every package named in requirements.txt is pinned in requirements.lock.txt."""
    root = Path(__file__).resolve().parent.parent
    lock = root / "requirements.lock.txt"
    if not lock.exists():
        return
    locked = check_lockfile.read_pins(lock.read_text(encoding="utf-8"))
    for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name = check_lockfile._canonical(line.split("[", 1)[0].split(">", 1)[0].split("=", 1)[0].split("<", 1)[0].strip())
        assert name in locked, f"{name} is in requirements.txt but not pinned in requirements.lock.txt"
