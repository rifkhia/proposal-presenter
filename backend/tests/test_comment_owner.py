import pytest

from app import config

PROPOSAL = "plan.md"


@pytest.fixture(autouse=True)
def proposal():
    (config.PROPOSALS_DIR / PROPOSAL).write_text("# Plan\n\nIntro.\n")


def post(client, body="hi", parent_id=None):
    res = client.post("/api/comments", json={"proposal": PROPOSAL, "author": "Any Name", "body": body, "parent_id": parent_id})
    assert res.status_code == 201, res.text
    return res.json()


def test_comment_records_the_account(alice, client):
    assert post(alice)["owner"] == "alice"
    alice.post("/api/auth/logout")
    assert post(client)["owner"] is None  # anonymous
    alice.post("/api/auth/login", json={"password": "correct horse"}).raise_for_status()
    assert post(alice)["owner"] is None  # shared password: no one in particular


def test_owner_can_delete_reply_and_thread(alice):
    thread = post(alice)
    reply = post(alice, parent_id=thread["id"])
    assert alice.delete(f"/api/comments/{reply['id']}").status_code == 204
    assert alice.delete(f"/api/comments/{thread['id']}").status_code == 204
    assert alice.get("/api/comments", params={"proposal": PROPOSAL}).json() == []


def test_others_cannot_delete(alice, bob):
    thread = post(alice)
    assert bob.delete(f"/api/comments/{thread['id']}").status_code == 403
    assert len(alice.get("/api/comments", params={"proposal": PROPOSAL}).json()) == 1


def test_signed_out_and_shared_password_cannot_delete(alice, client):
    thread = post(alice)
    alice.post("/api/auth/logout")
    assert client.delete(f"/api/comments/{thread['id']}").status_code == 401
    client.post("/api/auth/login", json={"password": "correct horse"}).raise_for_status()
    assert client.delete(f"/api/comments/{thread['id']}").status_code == 401


def test_anonymous_comment_cannot_be_deleted(alice, bob):
    bob.post("/api/auth/logout")
    thread = post(bob)
    assert alice.delete(f"/api/comments/{thread['id']}").status_code == 403


def test_thread_with_others_replies_cannot_be_deleted(alice, bob):
    thread = post(alice)
    reply = post(bob, parent_id=thread["id"])
    assert alice.delete(f"/api/comments/{thread['id']}").status_code == 409
    assert bob.delete(f"/api/comments/{reply['id']}").status_code == 204  # bob removes his own
    assert alice.delete(f"/api/comments/{thread['id']}").status_code == 204
