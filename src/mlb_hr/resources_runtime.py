from __future__ import annotations

from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path
from typing import Iterator


def bundled_model_text() -> str:
    return files("mlb_hr.resources").joinpath("bundled_model", "model_manifest.json").read_text(encoding="utf-8")


@contextmanager
def packaged_migrations_dir() -> Iterator[Path]:
    resource = files("mlb_hr.resources").joinpath("migrations")
    with as_file(resource) as path:
        yield Path(path)
