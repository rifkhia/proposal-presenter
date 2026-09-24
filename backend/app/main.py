from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

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
    quote: str | None = Field(default=None, max_length=2000)

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


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/proposals")
def list_proposals():
    items = proposals.list_proposals()
    with db.connect() as conn:
        counts = dict(
            conn.execute("SELECT proposal, COUNT(*) FROM comments GROUP BY proposal").fetchall()
        )
    for item in items:
        item["comment_count"] = counts.get(item["path"], 0)
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
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM comments WHERE proposal = ? ORDER BY created_at, id",
            (proposal,),
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/comments", status_code=201)
def create_comment(comment: CommentIn):
    if proposals.resolve_markdown(comment.proposal) is None:
        raise HTTPException(404, "Proposal not found")
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO comments (proposal, author, body, quote) VALUES (?, ?, ?, ?)",
            (comment.proposal, comment.author, comment.body, comment.quote),
        )
        row = conn.execute("SELECT * FROM comments WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


@app.delete("/api/comments/{comment_id}", status_code=204)
def delete_comment(comment_id: int):
    with db.connect() as conn:
        cur = conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "Comment not found")
