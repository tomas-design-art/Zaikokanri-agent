"""依存の取り込み方のルール（受け入れ条件 F-01 / A-08）。

開発憲章 1章：公開7日未満の版は使わない。npm は ~/.npmrc の min-release-age=7 で、
Python は uv の exclude-newer で作ったハッシュ付きロックから入れることで機械的に守る。
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def test_F01_lockfiles_built_with_7_day_cutoff():
    for name in ("requirements.lock", "requirements-dev.lock"):
        text = (BACKEND / name).read_text(encoding="utf-8")
        header = "\n".join(text.splitlines()[:3])
        assert "--exclude-newer 7 days" in header, f"{name} は 7日ルールなしで作られている"
        assert "--generate-hashes" in header
        pins = re.findall(r"^([a-z0-9][a-z0-9._-]*)==", text, flags=re.MULTILINE)
        assert pins, name


def test_F01_every_direct_dependency_is_locked():
    deps = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    lock = (BACKEND / "requirements.lock").read_text(encoding="utf-8").lower()
    for dep in deps:
        name = re.split(r"[\[<>=!~ ]", dep, maxsplit=1)[0].lower()
        assert f"\n{name}==" in lock, f"{name} がロックに無い"


def test_F01_docker_installs_from_hashed_lock():
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    assert "--require-hashes" in dockerfile
    assert "requirements.lock" in dockerfile


def test_A08_unmaintained_libraries_removed():
    deps = " ".join(tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"])
    for banned in ("python-jose", "passlib"):
        assert banned not in deps
