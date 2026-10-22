"""Separate local run output from deliberately published evidence."""
import os
from pathlib import Path


def evidence_dir():
    return Path(os.getenv("SERVICESETU_ARTIFACT_DIR", "artifacts/local"))


def evidence_path(name):
    path = evidence_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def evidence_input(name):
    local = evidence_dir() / name
    return local if local.exists() else Path("artifacts") / name


def publishing_evidence():
    return evidence_dir().resolve() == Path("artifacts").resolve()
