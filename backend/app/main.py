from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from . import db, proposals


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="proposal-presenter", lifespan=lifespan)


class CommentIn(BaseModel):
    proposal: str = Field(min_length=1, max_length=500)
    author: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=5000)
    # Inline anchor: the selected text and the source lines it came from.
    quote: str | None = Field(default=None, max_length=2000)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    # Set to reply to a thread instead of starting one.
    parent_id: int | None = None

    @field_validator("author", "body")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("quote")
    @classmethod
    def empty_quote_is_none(cls, v: str | None) -> str | None:
        return v.strip() or None if v else None

    @model_validator(mode="after")
    def check_lines(self):
        if self.line_start is None:
            if self.line_end is not None:
                raise ValueError("line_end requires line_start")
        elif self.line_end is None:
            self.line_end = self.line_start
        elif self.line_end < self.line_start:
            raise ValueError("line_end must be >= line_start")
        return self


class ResolveIn(BaseModel):
    resolved: bool
    by: str | None = Field(default=None, max_length=100)


def _comment(row) -> dict:
    c = dict(row)
    c["resolved"] = bool(c["resolved"])
    return c


def _get(conn, comment_id: int):
    return conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/proposals")
def list_proposals():
    items = proposals.list_proposals()
    with db.connect() as conn:
        counts = {
            row["proposal"]: row
            for row in conn.execute(
                """SELECT proposal,
                          COUNT(*) AS total,
                          SUM(parent_id IS NULL AND resolved = 0) AS open_threads
                   FROM comments GROUP BY proposal"""
            )
        }
    for item in items:
        row = counts.get(item["path"])
        item["comment_count"] = row["total"] if row else 0
        item["open_threads"] = row["open_threads"] if row else 0
    return items


@app.get("/api/proposals/{path:path}")
def get_proposal(path: str):
    file = proposals.resolve_markdown(path)
    if file is None:
        raise HTTPException(404, "Proposal not found")
    return proposals.read_proposal(file)


@app.get("/api/assets/{path:path}")
def get_asset(path: str):
    """Serves images and other files referenced from proposals by relative path."""
    file = proposals.resolve(path)
    if file is None:
        raise HTTPException(404, "File not found")
    return FileResponse(file)


@app.get("/api/comments")
def list_comments(proposal: str = Query(min_length=1)):
    """Threads for a proposal, oldest first, each with its replies nested."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM comments WHERE proposal = ? ORDER BY created_at, id",
            (proposal,),
        ).fetchall()
    threads = {}
    for row in rows:
        if row["parent_id"] is None:
            threads[row["id"]] = {**_comment(row), "replies": []}
    for row in rows:
        if row["parent_id"] in threads:
            threads[row["parent_id"]]["replies"].append(_comment(row))
    return list(threads.values())


@app.post("/api/comments", status_code=201)
def create_comment(comment: CommentIn):
    if proposals.resolve_markdown(comment.proposal) is None:
        raise HTTPException(404, "Proposal not found")
    with db.connect() as conn:
        if comment.parent_id is not None:
            parent = _get(conn, comment.parent_id)
            if parent is None or parent["proposal"] != comment.proposal:
                raise HTTPException(404, "Thread not found")
            if parent["parent_id"] is not None:
                raise HTTPException(400, "Replies can't be replied to; reply to the thread")
            # The anchor belongs to the thread, not to individual replies.
            comment.quote = comment.line_start = comment.line_end = None
        cur = conn.execute(
            """INSERT INTO comments (proposal, author, body, quote, line_start, line_end, parent_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                comment.proposal,
                comment.author,
                comment.body,
                comment.quote,
                comment.line_start,
                comment.line_end,
                comment.parent_id,
            ),
        )
        created = _comment(_get(conn, cur.lastrowid))
    if created["parent_id"] is None:
        created["replies"] = []
    return created


@app.patch("/api/comments/{comment_id}")
def resolve_comment(comment_id: int, change: ResolveIn):
    """Resolve or reopen a thread."""
    with db.connect() as conn:
        row = _get(conn, comment_id)
        if row is None:
            raise HTTPException(404, "Comment not found")
        if row["parent_id"] is not None:
            raise HTTPException(400, "Only threads can be resolved, not replies")
        if change.resolved:
            by = change.by.strip() if change.by else None
            conn.execute(
                f"UPDATE comments SET resolved = 1, resolved_by = ?, resolved_at = {db.NOW} WHERE id = ?",
                (by or None, comment_id),
            )
        else:
            conn.execute(
                "UPDATE comments SET resolved = 0, resolved_by = NULL, resolved_at = NULL WHERE id = ?",
                (comment_id,),
            )
        return _comment(_get(conn, comment_id))


@app.delete("/api/comments/{comment_id}", status_code=204)
def delete_comment(comment_id: int):
    """Deletes a reply, or a whole thread including its replies."""
    with db.connect() as conn:
        cur = conn.execute(
            "DELETE FROM comments WHERE id = ? OR parent_id = ?", (comment_id, comment_id)
        )
    if cur.rowcount == 0:
        raise HTTPException(404, "Comment not found")
