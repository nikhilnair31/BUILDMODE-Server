
# core/utils/data.py

from pathlib import Path

def _safe_unlink(p: str) -> bool:
    """Delete a file if it exists. Returns True if removed."""
    if not p:
        return False
    try:
        path = Path(p)
        # Optional: only allow absolute paths within your storage root
        # STORAGE_ROOT = Path("/var/forgor/uploads").resolve()
        # if not path.is_absolute() or STORAGE_ROOT not in path.resolve().parents | {STORAGE_ROOT}:
        #     return False
        if path.exists():
            path.unlink()
            return True
    except Exception:
        # swallow per-file errors; we'll still remove DB rows
        pass
    return False