from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from . import anchoring, auth, db, proposals
from .config import PROPOSALS_DIR


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    auth.check_config()
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
    # Version of the proposal the anchor's line numbers refer to.
    version: str | None = Field(default=None, max_length=64)

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


class LoginIn(BaseModel):
    password: str = Field(min_length=1, max_length=1000)


class ProposalEdit(BaseModel):
    content: str = Field(max_length=2_000_000)
    # Version the editor started from; saving is refused if the file has changed since.
    base_version: str = Field(min_length=1, max_length=64)
    force: bool = False

    @field_validator("content")
    @classmethod
    def normalize_newlines(cls, v: str) -> str:
        return v.replace("\r\n", "\n").replace("\r", "\n")


def _comment(row) -> dict:
    c = dict(row)
    c["resolved"] = bool(c["resolved"])
    return c


def _get(conn, comment_id: int):
    return conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()


def _rel(file) -> str:
    return file.relative_to(PROPOSALS_DIR).as_posix()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/auth")
def auth_status(request: Request):
    return {"enabled": auth.enabled(), "signed_in": auth.is_signed_in(request)}


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request, response: Response):
    auth.sign_in(request, response, body.password)
    return {"enabled": True, "signed_in": True}


@app.post("/api/auth/logout")
def logout(response: Response):
    auth.sign_out(response)
    return {"enabled": auth.enabled(), "signed_in": False}


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
    text = proposals.read_text(file)
    with db.connect() as conn:
        anchoring.sync(conn, _rel(file), text)
    return proposals.read_proposal(file, text)


@app.put("/api/proposals/{path:path}", dependencies=[Depends(auth.require_editor)])
def save_proposal(path: str, edit: ProposalEdit):
    file = proposals.resolve_markdown(path)
    if file is None:
        raise HTTPException(404, "Proposal not found")
    if not proposals.is_writable(file):
        raise HTTPException(403, "The proposals folder isn't writable by the app (see README: Editing)")
    rel = _rel(file)
    with db.connect() as conn:
        # Hold the write lock across check, write and remap so two saves can't interleave.
        conn.execute("BEGIN IMMEDIATE")
        current = proposals.read_text(file)
        anchoring.catch_up(conn, rel, current)
        if not edit.force and anchoring.version_of(current) != edit.base_version:
            raise HTTPException(409, "This proposal was changed by someone else since you started editing")
        result = {"moved": 0, "touched": 0}
        if edit.content != current:
            try:
                proposals.write_proposal(file, edit.content)
            except PermissionError:
                raise HTTPException(403, "The proposals folder isn't writable by the app (see README: Editing)")
            result = anchoring.catch_up(conn, rel, edit.content) or result
    return {"proposal": proposals.read_proposal(file, edit.content), "remap": result}


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
    file = proposals.resolve_markdown(proposal)
    with db.connect() as conn:
        if file is not None:
            anchoring.sync(conn, proposal, proposals.read_text(file))  # line numbers follow edits
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
    file = proposals.resolve_markdown(comment.proposal)
    if file is None:
        raise HTTPException(404, "Proposal not found")
    with db.connect() as conn:
        if comment.parent_id is None and comment.line_start is not None and comment.version:
            text = proposals.read_text(file)
            anchoring.sync(conn, comment.proposal, text)
            if anchoring.version_of(text) != comment.version:
                raise HTTPException(409, "This proposal was updated since you opened it. Reload to comment on the new version.")
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
