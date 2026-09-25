"""Keeps inline comments pointing at the right lines when a proposal changes.

The server stores a snapshot of the last version of each proposal it has seen.
Whenever the file on disk differs from it (edited in the app, or replaced by hand
over scp), the two versions are line-diffed and every thread's line range is moved
along with its text:

- lines that didn't change      -> shifted by however much was added/removed above
- lines that were rewritten     -> the rewritten lines ("touched")
- lines that were deleted       -> the line after the deletion ("touched")

Whether a touched thread is outdated is decided by the frontend, which checks
whether its quoted text is still in the document.
"""

import difflib
import hashlib


def version_of(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _line_map(old_lines: list[str], new_lines: list[str]) -> list[tuple[int, bool]]:
    """For each old line index: (new line index, whether the line was changed)."""
    mapping: list[tuple[int, bool]] = [(0, True)] * len(old_lines)
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        for i in range(i1, i2):
            if tag == "equal":
                mapping[i] = (j1 + i - i1, False)
            elif tag == "replace":
                mapping[i] = (min(j1 + i - i1, j2 - 1), True)
            elif tag == "delete":
                mapping[i] = (j1, True)
    return mapping


def remap(conn, proposal: str, old_text: str, new_text: str) -> dict:
    """Move every thread's lines from old_text to new_text. Returns counts for the UI."""
    old_lines, new_lines = old_text.split("\n"), new_text.split("\n")
    mapping = _line_map(old_lines, new_lines)
    last = max(len(new_lines), 1)
    moved = touched = 0
    rows = conn.execute(
        """SELECT id, line_start, line_end FROM comments
           WHERE proposal = ? AND parent_id IS NULL AND line_start IS NOT NULL""",
        (proposal,),
    ).fetchall()
    for row in rows:
        start = row["line_start"]
        if start > len(old_lines):
            continue  # already past the end of the file; nothing to follow
        end = min(row["line_end"] or start, len(old_lines))
        span = mapping[start - 1 : end]
        new_start = min(span[0][0] + 1, last)
        new_end = min(max(span[-1][0] + 1, new_start), last)
        if any(changed for _, changed in span):
            touched += 1
        if (new_start, new_end) != (start, row["line_end"]):
            moved += 1
            conn.execute(
                "UPDATE comments SET line_start = ?, line_end = ? WHERE id = ?",
                (new_start, new_end, row["id"]),
            )
    return {"moved": moved, "touched": touched}


def catch_up(conn, proposal: str, text: str) -> dict | None:
    """Remap threads if the proposal changed since its snapshot, then store the new
    snapshot. The caller must hold the write lock (BEGIN IMMEDIATE)."""
    version = version_of(text)
    row = conn.execute(
        "SELECT version, content FROM snapshots WHERE proposal = ?", (proposal,)
    ).fetchone()
    if row and row["version"] == version:
        return None
    # No snapshot yet: existing comments were made against this text (or there are none).
    result = remap(conn, proposal, row["content"], text) if row else None
    conn.execute(
        """INSERT INTO snapshots (proposal, version, content) VALUES (?, ?, ?)
           ON CONFLICT (proposal) DO UPDATE SET version = excluded.version, content = excluded.content""",
        (proposal, version, text),
    )
    return result


def sync(conn, proposal: str, text: str) -> None:
    """catch_up() for read paths: cheap when nothing changed, and safe under
    concurrent requests (the re-check under the lock makes it remap only once)."""
    row = conn.execute("SELECT version FROM snapshots WHERE proposal = ?", (proposal,)).fetchone()
    if row and row["version"] == version_of(text):
        return
    conn.execute("BEGIN IMMEDIATE")
    catch_up(conn, proposal, text)
    conn.commit()
