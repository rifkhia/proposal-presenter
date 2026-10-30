import os
import stat

import pytest

from app import auth, config, proposals
from app.anchoring import version_of

TEXT = "# Plan\n\nIntro.\n\nDetails.\n"


def upload(client, filename="plan.md", folder="", content=TEXT):
    return client.post("/api/proposals", json={"filename": filename, "folder": folder, "content": content})


def assert_nothing_written():
    assert list(config.PROPOSALS_DIR.rglob("*")) == []
    assert not (config.PROPOSALS_DIR.parent / "x.md").exists()


def test_signed_out_is_401(client):
    assert upload(client).status_code == 401
    assert_nothing_written()


def test_editing_disabled_is_403(client, monkeypatch):
    monkeypatch.setattr(auth, "EDIT_PASSWORD_HASH", "")
    assert upload(client).status_code == 403
    assert_nothing_written()


@pytest.mark.parametrize(
    "filename, folder",
    [
        ("../x.md", ""),
        (".hidden.md", ""),
        ("x.md", "a/../.."),
        ("x.txt", ""),
        ("x.md", "/etc"),
        ("", ""),
        ("x.md", "a//b"),
        ("a/b.md", ""),
        (" x.md", ""),
        ("x.md", ".git"),
        ("a" * 118 + ".md", ""),  # 121 chars
        ("x.md", "/".join(["a" * 100] * 5)),  # over 500 in total
    ],
)
def test_invalid_names_are_400(editor, filename, folder):
    res = upload(editor, filename, folder)
    assert res.status_code == 400, res.text
    assert_nothing_written()


def test_symlinked_folder_outside_is_400(editor, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (config.PROPOSALS_DIR / "link").symlink_to(outside)
    res = upload(editor, "x.md", "link")
    assert res.status_code == 400
    assert res.json()["detail"] == "Folder must be inside the proposals folder"
    assert list(outside.iterdir()) == []


def test_folder_that_is_a_file_is_400(editor):
    (config.PROPOSALS_DIR / "team").write_text("not a folder")
    res = upload(editor, "x.md", "team/q4")
    assert res.status_code == 400
    assert res.json()["detail"] == "Can't create folder 'team/q4'"


def test_create_at_root(editor):
    res = upload(editor)
    assert res.status_code == 201
    body = res.json()
    assert body["path"] == "plan.md"
    assert body["title"] == "Plan"
    assert body["version"] == version_of(TEXT)
    file = config.PROPOSALS_DIR / "plan.md"
    assert file.read_text() == TEXT
    assert stat.S_IMODE(file.stat().st_mode) == 0o644
    assert [p["path"] for p in editor.get("/api/proposals").json()] == ["plan.md"]


def test_create_in_new_subfolder(editor):
    res = upload(editor, "plan.md", "team/q4")
    assert res.status_code == 201
    assert res.json()["path"] == "team/q4/plan.md"
    assert (config.PROPOSALS_DIR / "team" / "q4" / "plan.md").is_file()
    [item] = editor.get("/api/proposals").json()
    assert item["folder"] == "team/q4"


def test_crlf_is_stored_as_lf(editor):
    assert upload(editor, content="# Plan\r\n\r\nIntro.\r\n").status_code == 201
    assert (config.PROPOSALS_DIR / "plan.md").read_bytes() == b"# Plan\n\nIntro.\n"


def test_existing_name_is_409_with_version(editor):
    file = config.PROPOSALS_DIR / "plan.md"
    file.write_text(TEXT)
    res = upload(editor, content="# Other\n")
    assert res.status_code == 409
    assert res.json() == {
        "detail": "A proposal with this name already exists",
        "path": "plan.md",
        "version": version_of(TEXT),
    }
    assert file.read_text() == TEXT


def test_create_never_overwrites():
    file = config.PROPOSALS_DIR / "plan.md"
    file.write_text(TEXT)
    with pytest.raises(FileExistsError):
        proposals.write_proposal(file, "x", create=True)
    assert file.read_text() == TEXT
    assert list(config.PROPOSALS_DIR.glob(".*.tmp")) == []


def test_replace_flow_moves_comments(editor):
    created = upload(editor).json()
    comment = {
        "proposal": "plan.md",
        "author": "Ann",
        "body": "Why?",
        "quote": "Intro.",
        "line_start": 3,
        "version": created["version"],
    }
    assert editor.post("/api/comments", json=comment).status_code == 201

    conflict = upload(editor, content="# Plan v2\n")
    assert conflict.status_code == 409
    existing = conflict.json()

    new_text = "Added 1\nAdded 2\n" + TEXT
    res = editor.put(
        f"/api/proposals/{existing['path']}", json={"content": new_text, "base_version": existing["version"]}
    )
    assert res.status_code == 200
    [thread] = editor.get("/api/comments", params={"proposal": "plan.md"}).json()
    assert thread["line_start"] == 5

    stale = editor.put(
        f"/api/proposals/{existing['path']}", json={"content": "# Again\n", "base_version": existing["version"]}
    )
    assert stale.status_code == 409


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
def test_folder_not_writable_is_403(editor):
    config.PROPOSALS_DIR.chmod(0o555)
    try:
        res = upload(editor)
    finally:
        config.PROPOSALS_DIR.chmod(0o755)
    assert res.status_code == 403
    assert res.json()["detail"] == "The proposals folder isn't writable by the app (see README: Editing)"
    assert_nothing_written()
