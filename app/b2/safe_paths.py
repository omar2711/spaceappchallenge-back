"""Portable relative paths for server-owned scientific roots, including Windows."""

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated

from pydantic import AfterValidator


def relative_path(value: str) -> str:
    """Reject traversal, drive/UNC paths, ADS and Windows normalization aliases."""
    parts = value.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10)}
    if (not value or "\\" in value or ":" in value or any(ord(c) < 32 for c in value)
            or any(c in value for c in '<>"|?*')
            or PurePosixPath(value).is_absolute() or PureWindowsPath(value).drive
            or any(p in ("", ".", "..") or p.endswith((".", " ")) or p.split(".")[0].upper() in reserved for p in parts)):
        raise ValueError("Expected a portable relative POSIX path without traversal")
    return value


RelativePath = Annotated[str, AfterValidator(relative_path)]


def inside(root: Path, value: str) -> Path:
    """Resolve an existing file and reject links, even links inside the root."""
    relative_path(value)
    base = root.resolve(strict=True)
    path = base
    for part in value.split("/"):
        path = path / part
        if path.is_symlink():
            raise ValueError("Symbolic links are not accepted")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(base) or not resolved.is_file():
        raise ValueError("Expected a file inside the configured root")
    return resolved
