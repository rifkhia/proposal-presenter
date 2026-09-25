"""Reads proposals straight from PROPOSALS_DIR on every request, so files
dropped into the folder show up without restarting anything."""

import contextlib
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .anchoring import version_of
from .config import PROPOSALS_DIR

_H1 = re.compile(r"^#\s+(.+?)\s*#*\s*$")


def resolve(rel_path: str) -> Path | None:
    """Map a client-supplied relative path to a real file inside PROPOSALS_DIR,
    or None if it escapes the folder, is hidden, or doesn't exist."""
    candidate = (PROPOSALS_DIR / rel_path).resolve()
    if not candidate.is_relative_to(PROPOSALS_DIR) or not candidate.is_file():
        return None
    if any(part.startswith(".") for part in candidate.relative_to(PROPOSALS_DIR).parts):
        return None
    return candidate


def resolve_markdown(rel_path: str) -> Path | None:
    path = resolve(rel_path)
    return path if path and path.suffix.lower() == ".md" else None


def _title_and_excerpt(text: str, fallback: str) -> tuple[str, str]:
    title = None
    excerpt_lines: list[str] = []
    in_code = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if title is None and (m := _H1.match(stripped)):
            title = m.group(1)
            continue
        if not stripped:
            if excerpt_lines:
                break
            continue
        if stripped.startswith(("#", "|", ">", "-", "*", "!", "<")) and not excerpt_lines:
            continue
        excerpt_lines.append(stripped)
    excerpt = " ".join(excerpt_lines)
    if len(excerpt) > 220:
        excerpt = excerpt[:217].rstrip() + "..."
    return title or fallback, excerpt


def _fallback_title(path: Path) -> str:
    return re.sub(r"[-_]+", " ", path.stem).strip().capitalize() or path.name


def _iso_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def list_proposals() -> list[dict]:
    if not PROPOSALS_DIR.is_dir():
        return []
    items = []
    for path in PROPOSALS_DIR.rglob("*"):
        if path.suffix.lower() != ".md" or not path.is_file():
            continue
        rel = path.relative_to(PROPOSALS_DIR)
        if any(part.startswith(".") for part in rel.parts):
            continue
        text = read_text(path)
        title, excerpt = _title_and_excerpt(text, _fallback_title(path))
        items.append(
            {
                "path": rel.as_posix(),
                "folder": rel.parent.as_posix() if rel.parent != Path(".") else "",
                "title": title,
                "excerpt": excerpt,
                "modified": _iso_mtime(path),
            }
        )
    items.sort(key=lambda p: p["modified"], reverse=True)
    return items


def read_text(path: Path) -> str:
    # Universal newlines: CRLF files read as LF, so line numbers and versions match
    # what the browser sees.
    return path.read_text(encoding="utf-8", errors="replace")


def is_writable(path: Path) -> bool:
    # Saving replaces the file via a temp file in the same folder, so the folder
    # (not the file) is what needs to be writable.
    return os.access(path.parent, os.W_OK)


def read_proposal(path: Path, text: str | None = None) -> dict:
    text = read_text(path) if text is None else text
    rel = path.relative_to(PROPOSALS_DIR)
    title, _ = _title_and_excerpt(text, _fallback_title(path))
    return {
        "path": rel.as_posix(),
        "title": title,
        "modified": _iso_mtime(path),
        "version": version_of(text),
        "writable": is_writable(path),
        "content": text,
    }


def write_proposal(path: Path, text: str) -> None:
    """Atomically replace the file, keeping its permissions and line endings."""
    newline = "\r\n" if b"\r\n" in path.read_bytes() else "\n"
    mode = path.stat().st_mode & 0o777
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
