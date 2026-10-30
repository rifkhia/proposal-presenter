import pytest

from app import config, db
from app.anchoring import version_of

PAGE = "<!doctype html><html><head><title>\n  Q4 &amp; beyond </title></head><body><script>x()</script></body></html>"
RENDER_HEADERS = {
    "content-security-policy": "sandbox allow-scripts allow-popups allow-forms; frame-ancestors 'self'",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "cache-control": "no-cache",
}


def write(name, text):
    file = config.PROPOSALS_DIR / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text)
    return file


def snapshot_count():
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]


def test_list_kinds_and_titles(client):
    write("plan.md", "# Plan\n\nIntro.\n")
    write("page.html", PAGE)
    write("old-page.htm", "<p>no title</p>")
    write("notes.txt", "not listed")
    write("x.artifact.json", "{}")
    items = {p["path"]: p for p in client.get("/api/proposals").json()}
    assert set(items) == {"plan.md", "page.html", "old-page.htm"}
    assert items["plan.md"]["kind"] == "markdown"
    assert items["page.html"]["kind"] == "html"
    assert items["page.html"]["title"] == "Q4 & beyond"
    assert items["page.html"]["excerpt"] == ""
    assert items["old-page.htm"]["kind"] == "html"
    assert items["old-page.htm"]["title"] == "Old page"


@pytest.mark.parametrize(
    "text, title",
    [
        ("<titlebar>Bar</titlebar><p>x</p>", "Page"),  # not a <title>
        ("<titlebar>Bar</titlebar><title lang='en'>Real</title>", "Real"),
        ("<TITLE>Upper</TITLE >", "Upper"),
    ],
)
def test_html_title_needs_a_title_tag(client, text, title):
    write("page.html", text)
    assert client.get("/api/proposals").json()[0]["title"] == title


def test_get_html_has_no_content_and_no_snapshot(client):
    write("page.html", PAGE)
    body = client.get("/api/proposals/page.html").json()
    assert body["kind"] == "html"
    assert body["title"] == "Q4 & beyond"
    assert body["version"] == version_of(PAGE)
    assert "content" not in body
    assert snapshot_count() == 0


def test_get_markdown_still_has_content(client):
    write("plan.md", "# Plan\n")
    body = client.get("/api/proposals/plan.md").json()
    assert body["kind"] == "markdown"
    assert body["content"] == "# Plan\n"
    assert snapshot_count() == 1


def test_render_html_is_sandboxed(client):
    file = write("page.html", PAGE)
    res = client.get("/api/render/page.html")
    assert res.status_code == 200
    assert res.headers["content-type"] == "text/html; charset=utf-8"
    for name, value in RENDER_HEADERS.items():
        assert res.headers[name] == value
    assert res.content == file.read_bytes()


@pytest.mark.parametrize("path", ["plan.md", "missing.html", "%2E%2E/outside.html"])
def test_render_only_html_inside_the_folder(client, path):
    write("plan.md", "# Plan\n")
    (config.PROPOSALS_DIR.parent / "outside.html").write_text(PAGE)
    assert client.get(f"/api/render/{path}").status_code == 404


@pytest.mark.parametrize("name", ["page.html", "img/logo.svg"])
def test_assets_are_sandboxed(client, name):
    write(name, "<svg xmlns='http://www.w3.org/2000/svg'><script>x()</script></svg>")
    res = client.get(f"/api/assets/{name}")
    assert res.status_code == 200
    assert res.headers["content-security-policy"] == "sandbox"
    assert res.headers["x-content-type-options"] == "nosniff"


def test_pdf_assets_are_not_sandboxed(client):
    write("doc.pdf", "%PDF-1.4")
    res = client.get("/api/assets/doc.pdf")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" not in res.headers


def test_general_comment_on_html(client):
    write("page.html", PAGE)
    res = client.post("/api/comments", json={"proposal": "page.html", "author": "Ann", "body": "Nice"})
    assert res.status_code == 201
    assert [t["body"] for t in client.get("/api/comments", params={"proposal": "page.html"}).json()] == ["Nice"]
    assert snapshot_count() == 0


@pytest.mark.parametrize("anchor", [{"line_start": 1}, {"quote": "Q4"}])
def test_inline_comment_on_html_is_400(client, anchor):
    write("page.html", PAGE)
    res = client.post("/api/comments", json={"proposal": "page.html", "author": "Ann", "body": "Hm", **anchor})
    assert res.status_code == 400
    assert res.json()["detail"] == "Inline comments are only supported on Markdown proposals"


def test_inline_comment_on_markdown_still_works(client):
    write("plan.md", "# Plan\n\nIntro.\n")
    res = client.post(
        "/api/comments",
        json={"proposal": "plan.md", "author": "Ann", "body": "Hm", "quote": "Intro.", "line_start": 3},
    )
    assert res.status_code == 201


def test_upload_html(editor):
    res = editor.post("/api/proposals", json={"filename": "page.html", "content": PAGE})
    assert res.status_code == 201
    assert res.json()["kind"] == "html"
    assert "content" not in res.json()
    assert (config.PROPOSALS_DIR / "page.html").read_text() == PAGE


def test_upload_txt_is_400(editor):
    res = editor.post("/api/proposals", json={"filename": "x.txt", "content": "x"})
    assert res.status_code == 400
    assert res.json()["detail"] == "Only .md, .html and .htm files can be uploaded"


def test_put_html_replaces_without_snapshot(editor):
    write("page.html", PAGE)
    new = PAGE.replace("x()", "y()")
    res = editor.put("/api/proposals/page.html", json={"content": new, "base_version": version_of(PAGE)})
    assert res.status_code == 200
    assert res.json()["proposal"]["version"] == version_of(new)
    assert (config.PROPOSALS_DIR / "page.html").read_text() == new
    assert snapshot_count() == 0

    stale = editor.put("/api/proposals/page.html", json={"content": PAGE, "base_version": version_of(PAGE)})
    assert stale.status_code == 409
