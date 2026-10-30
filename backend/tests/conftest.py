import os
import shutil
import tempfile
from pathlib import Path

import pytest

# config.py and db.DB_PATH read the environment at import, so set it before importing app.
ROOT = Path(tempfile.mkdtemp(prefix="pp-tests-"))
os.environ["PROPOSALS_DIR"] = str(ROOT / "proposals")
os.environ["DATA_DIR"] = str(ROOT / "data")
os.environ.pop("EDIT_PASSWORD_HASH", None)

from fastapi.testclient import TestClient  # noqa: E402

from app import auth, config, main  # noqa: E402

PASSWORD = "correct horse"
HASH = auth.hash_password(PASSWORD, iterations=1_000)  # fast


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    for d in (config.PROPOSALS_DIR, config.DATA_DIR):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    monkeypatch.setattr(auth, "EDIT_PASSWORD_HASH", HASH)  # auth reads its own module global
    monkeypatch.setattr(auth, "ITERATIONS", 1_000)  # account hashes, fast
    auth._failures.clear()


@pytest.fixture
def client():
    with TestClient(main.app) as c:  # runs lifespan -> db.init_db()
        yield c


@pytest.fixture
def editor(client):
    client.post("/api/auth/login", json={"password": PASSWORD}).raise_for_status()
    return client


@pytest.fixture(scope="session", autouse=True)
def _rm_root():
    yield
    shutil.rmtree(ROOT, ignore_errors=True)


USER_PASSWORD = "s3cret-enough"


def _register(client, username):
    body = {"username": username, "password": USER_PASSWORD, "code": PASSWORD}
    client.post("/api/auth/register", json=body).raise_for_status()
    return client


@pytest.fixture
def alice(client):
    return _register(client, "alice")


@pytest.fixture
def bob(client):  # a second browser
    with TestClient(main.app) as c:
        yield _register(c, "bob")
