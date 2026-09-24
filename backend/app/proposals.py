"""Reads proposals straight from PROPOSALS_DIR on every request, so files
dropped into the folder show up without restarting anything."""

import re
from datetime import datetime, timezone
from pathlib import Path

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
        text = path.read_text(encoding="utf-8", errors="replace")
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


def read_proposal(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = path.relative_to(PROPOSALS_DIR)
    title, _ = _title_and_excerpt(text, _fallback_title(path))
    return {
        "path": rel.as_posix(),
        "title": title,
        "modified": _iso_mtime(path),
        "content": text,
    }
