"""Shared helpers for the Portalcrane backend."""

from pathlib import Path


def resolve_safe_path(relative: str, base_dir: Path) -> Path | None:
    """Resolve ``relative`` under ``base_dir`` guarding against traversal.

    Returns the resolved absolute path when it exists as a regular file and
    stays inside ``base_dir``. Returns ``None`` for empty inputs, paths that
    escape the base directory, or non-files, so callers can fall back to the
    SPA index.
    """
    if not relative:
        return None

    base = base_dir.resolve()
    candidate = (base / relative).resolve()

    # Reject anything that escapes the base directory (path traversal).
    if base != candidate and base not in candidate.parents:
        return None

    if candidate.is_file():
        return candidate
    return None
