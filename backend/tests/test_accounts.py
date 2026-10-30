import pytest

from app import auth, db
from conftest import PASSWORD

USER_PASSWORD = "s3cret-enough"


def register(client, username="alice", password=USER_PASSWORD, code=PASSWORD):
    return client.post("/api/auth/register", json={"username": username, "password": password, "code": code})


def login(client, username="alice", password=USER_PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_register_stores_only_a_hash_and_signs_in(client):
    res = register(client)
    assert res.status_code == 201, res.text
    assert res.json() == {"enabled": True, "signed_in": True, "username": "alice"}
    assert client.get("/api/auth").json()["username"] == "alice"
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM users").fetchone()
    assert row["username"] == "alice"
    assert USER_PASSWORD not in row["password_hash"]
    assert row["password_hash"].startswith("pbkdf2_sha256:")
    assert auth.verify_password(USER_PASSWORD, row["password_hash"])


def test_register_needs_the_editor_password(client):
    assert register(client, code="wrong").status_code == 401
    assert client.get("/api/auth").json()["signed_in"] is False
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_register_disabled_without_editor_password(client, monkeypatch):
    monkeypatch.setattr(auth, "EDIT_PASSWORD_HASH", "")
    assert register(client).status_code == 403


@pytest.mark.parametrize(
    "username, password",
    [("ab", USER_PASSWORD), ("-alice", USER_PASSWORD), ("al ice", USER_PASSWORD), ("a" * 41, USER_PASSWORD), ("alice", "short")],
)
def test_register_validation(client, username, password):
    assert register(client, username, password).status_code == 400


def test_username_is_unique_ignoring_case(client):
    assert register(client).status_code == 201
    assert register(client, "ALICE").status_code == 409


def test_login_and_logout(client):
    register(client)
    client.post("/api/auth/logout")
    assert client.get("/api/auth").json()["signed_in"] is False
    res = login(client, "Alice")  # case-insensitive, canonical name returned
    assert res.status_code == 200, res.text
    assert res.json()["username"] == "alice"
    assert client.post("/api/proposals", json={"filename": "x.md", "content": "x"}).status_code == 201


@pytest.mark.parametrize("username, password", [("alice", "wrong-password"), ("bob", USER_PASSWORD)])
def test_wrong_login_is_401_with_same_message(client, username, password):
    register(client)
    client.post("/api/auth/logout")
    res = login(client, username, password)
    assert res.status_code == 401
    assert res.json()["detail"] == "Wrong username or password"


def test_lockout_after_failures(client):
    register(client)
    client.post("/api/auth/logout")
    for _ in range(auth.MAX_FAILURES):
        assert login(client, password="wrong-password").status_code == 401
    assert login(client).status_code == 429


def test_shared_password_still_works(editor):
    state = editor.get("/api/auth").json()
    assert state["signed_in"] is True and state["username"] is None


def test_deleted_user_loses_session(client):
    register(client)
    with db.connect() as conn:
        conn.execute("DELETE FROM users")
    assert client.get("/api/auth").json()["signed_in"] is False
    assert client.post("/api/proposals", json={"filename": "x.md", "content": "x"}).status_code == 401


def test_forged_username_in_cookie_is_rejected(client):
    register(client)
    register(client, "mallory")  # now signed in as mallory
    token = client.cookies.get(auth.COOKIE)
    expires, signature, _ = token.split(".", 2)
    client.cookies.set(auth.COOKIE, f"{expires}.{signature}.alice", path="/api")
    assert client.get("/api/auth").json()["signed_in"] is False
