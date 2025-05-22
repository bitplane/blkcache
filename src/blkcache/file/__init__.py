"""
File abstraction package with automatic type detection.

Provides File, Device, and Removable classes with a detect() factory
function that automatically chooses the appropriate class for a given path.
"""

from pathlib import Path
from typing import Type

from .base import File
from .device import Device
from .removable import Removable


def detect(path: Path | str) -> Type[File]:
    """
    Return the most specific file class that can handle this path.

    Checks classes in order of specificity: Removable -> Device -> File
    Returns the first class whose check() method returns True.
    """
    path = Path(path)

    # Check in order of specificity (most specific first)
    candidates = [Removable, Device, File]

    for cls in candidates:
        if cls.check(path):
            return cls

    # This should never happen since File.check() is very permissive
    raise ValueError(f"No file class can handle {path}")


__all__ = ["File", "Device", "Removable", "detect"]
