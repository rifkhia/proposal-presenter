import pytest
from fastapi.testclient import TestClient

from app import auth, config, main

ADMIN_PASSWORD = "admin-test-pw"
TEXT = "# Plan\n\nIntro.\n"


@pytest.fixture
def admin(client):
    auth.set_admin("boss", ADMIN_PASSWORD)
    client.post("/api/auth/login", json={"username": "boss", "password": ADMIN_PASSWORD}).raise_for_status()
    return client


def test_auth_status_says_admin(admin, bob):
    assert admin.get("/api/auth").json()["admin"] is True
    assert bob.get("/api/auth").json()["admin"] is False


def test_admin_deletes_any_proposal(admin, bob):
    bob.post("/api/proposals", json={"filename": "bob.md", "content": TEXT}).raise_for_status()
    (config.PROPOSALS_DIR / "server.md").write_text(TEXT)  # copied in, no owner
    assert admin.delete("/api/proposals/bob.md").status_code == 200
    assert admin.delete("/api/proposals/server.md").status_code == 200
    assert admin.get("/api/proposals").json() == []


def test_admin_deletes_any_comment(admin, bob, client):
    (config.PROPOSALS_DIR / "plan.md").write_text(TEXT)
    post = lambda c, **kw: c.post("/api/comments", json={"proposal": "plan.md", "author": "x", "body": "b", **kw}).json()
    thread = post(bob)
    post(bob, parent_id=thread["id"])
    with TestClient(main.app) as anon:
        anonymous = post(anon)
    assert admin.delete(f"/api/comments/{anonymous['id']}").status_code == 204
    assert admin.delete(f"/api/comments/{thread['id']}").status_code == 204  # replies go with it
    assert admin.get("/api/comments", params={"proposal": "plan.md"}).json() == []


def test_set_admin_promotes_existing_account_and_resets_password(alice):
    assert auth.set_admin("alice", "brand-new-pw") is True
    assert auth.is_admin("alice")
    alice.post("/api/auth/logout")
    assert alice.post("/api/auth/login", json={"username": "alice", "password": "s3cret-enough"}).status_code == 401
    assert alice.post("/api/auth/login", json={"username": "alice", "password": "brand-new-pw"}).status_code == 200


@pytest.mark.parametrize("username, password", [("a", ADMIN_PASSWORD), ("boss", "short")])
def test_set_admin_validates(client, username, password):
    with pytest.raises(ValueError):
        auth.set_admin(username, password)


def test_registered_users_are_not_admin(alice):
    assert not auth.is_admin("alice")
    assert not auth.is_admin(None) and not auth.is_admin("")
