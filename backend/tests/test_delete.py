from app import config, db

TEXT = "# Plan\n\nIntro.\n"


def write(name, text=TEXT):
    file = config.PROPOSALS_DIR / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text)
    return file


def upload(client, filename="plan.md", folder="", content=TEXT):
    res = client.post("/api/proposals", json={"filename": filename, "folder": folder, "content": content})
    assert res.status_code == 201, res.text
    return res.json()


def comment(client, proposal, body="hi"):
    res = client.post("/api/comments", json={"proposal": proposal, "author": "bob", "body": body})
    assert res.status_code == 201, res.text


def test_upload_records_owner(alice, bob):
    assert upload(alice)["owner"] == "alice"
    assert bob.get("/api/proposals/plan.md").json()["owner"] == "alice"
    assert bob.get("/api/proposals").json()[0]["owner"] == "alice"


def test_signed_out_is_401(alice, client):
    upload(alice)
    alice.post("/api/auth/logout")
    assert client.delete("/api/proposals/plan.md").status_code == 401
    assert (config.PROPOSALS_DIR / "plan.md").exists()


def test_only_the_uploader_can_delete(alice, bob):
    upload(alice)
    res = bob.delete("/api/proposals/plan.md")
    assert res.status_code == 403
    assert "alice" in res.json()["detail"]
    assert (config.PROPOSALS_DIR / "plan.md").exists()
    assert alice.delete("/api/proposals/plan.md").status_code == 200


def test_shared_password_cannot_delete(alice, bob):
    upload(alice)
    bob.post("/api/auth/login", json={"password": "correct horse"}).raise_for_status()
    assert bob.delete("/api/proposals/plan.md").status_code == 403


def test_files_copied_on_the_server_cannot_be_deleted(alice):
    write("plan.md")
    res = alice.delete("/api/proposals/plan.md")
    assert res.status_code == 403
    assert "server" in res.json()["detail"]
    assert (config.PROPOSALS_DIR / "plan.md").exists()


def test_delete_moves_file_comments_and_owner_to_trash(alice):
    upload(alice, folder="team")
    alice.get("/api/proposals/team/plan.md")  # takes a snapshot
    comment(alice, "team/plan.md")
    res = alice.delete("/api/proposals/team/plan.md")
    assert res.status_code == 200, res.text
    trashed = res.json()["trashed_as"]
    assert trashed.startswith(".trash/") and trashed.endswith("/team/plan.md")
    assert (config.PROPOSALS_DIR / trashed).read_text() == TEXT
    assert not (config.PROPOSALS_DIR / "team").exists()  # emptied folder removed
    assert alice.get("/api/proposals").json() == []
    assert alice.get("/api/proposals/team/plan.md").status_code == 404
    assert alice.get(f"/api/proposals/{trashed}").status_code == 404  # hidden
    with db.connect() as conn:
        for table in ("comments", "snapshots", "owners"):
            assert conn.execute(f"SELECT proposal FROM {table}").fetchone()[0] == trashed, table


def test_reupload_after_delete_starts_clean(alice, bob):
    upload(alice)
    comment(alice, "plan.md")
    alice.delete("/api/proposals/plan.md").raise_for_status()
    assert upload(bob)["owner"] == "bob"
    assert bob.get("/api/comments", params={"proposal": "plan.md"}).json() == []


def test_folder_with_other_files_is_kept(alice):
    upload(alice, folder="team")
    write("team/other.md")
    alice.delete("/api/proposals/team/plan.md").raise_for_status()
    assert [p["path"] for p in alice.get("/api/proposals").json()] == ["team/other.md"]


def test_html_can_be_deleted(alice):
    upload(alice, "page.html", content="<title>x</title>")
    assert alice.delete("/api/proposals/page.html").status_code == 200


def test_missing_hidden_and_escaping_paths_are_404(alice):
    write("notes.txt", "x")
    for path in ["nope.md", "notes.txt", "../x.md", ".trash/x.md"]:
        assert alice.delete(f"/api/proposals/{path}").status_code == 404, path


def test_read_only_folder_is_403(alice):
    upload(alice, folder="ro")
    folder = config.PROPOSALS_DIR / "ro"
    folder.chmod(0o555)
    try:
        assert alice.delete("/api/proposals/ro/plan.md").status_code == 403
        assert (folder / "plan.md").exists()
    finally:
        folder.chmod(0o755)
