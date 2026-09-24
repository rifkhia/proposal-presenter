# proposal-presenter

A small web app for sharing proposals written in Markdown. It lists every `.md` file in a folder; click one to read it rendered and leave comments. Select any text in a proposal to comment on that specific passage.

- **Frontend:** Vue 3 + Vite, served by nginx
- **Backend:** Python (FastAPI), comments stored in SQLite
- **Deploy:** Docker Compose (two containers)

```
browser ──► frontend (nginx :80) ──/api──► backend (FastAPI :8000)
                                             ├── /proposals  ← host folder, read-only
                                             └── /data       ← comments.db (named volume)
```

## Run on the VM

Requirements: Docker with the Compose plugin (`docker compose version`).

```bash
# 1. Copy this repo to the VM, then inside it:
cp .env.example .env          # optional: change APP_PORT / PROPOSALS_PATH

# 2. Build and start
docker compose up -d --build

# 3. Open http://<vm-ip>:8080
```

## Adding proposals

Put `.md` files into the `proposals/` folder next to `docker-compose.yml`, or into whatever folder `PROPOSALS_PATH` in `.env` points to:

```bash
scp my-proposal.md user@vm:/path/to/proposal-presenter/proposals/
```

No restart is needed. Files are read from disk on every request, so just refresh the page.

- **Title:** the first `# Heading` in the file, or the file name if there is none.
- **Subfolders** are supported and shown as a tag on the card (for example `proposals/payments/refunds.md`).
- **Images and links:** relative paths work. For example, `![diagram](img/flow.png)` next to the `.md` file is served, and a link to `other.md` opens that proposal in the app.
- Hidden files and folders (starting with `.`) are ignored.
- `proposals/example-proposal.md` is a sample. Delete it once you've added your own.

> Comments are tied to a proposal's file path. Renaming or moving a file starts it with no comments. Moving it back brings them back.

## Configuration (`.env`)

| Variable         | Default       | Meaning                                                  |
|------------------|---------------|----------------------------------------------------------|
| `APP_PORT`       | `8080`        | Host port the app is published on                        |
| `PROPOSALS_PATH` | `./proposals` | Host folder with the Markdown files (mounted read-only)  |

After changing `.env`, run `docker compose up -d`.

## Operations

```bash
docker compose ps                 # status
docker compose logs -f backend    # logs
docker compose up -d --build      # redeploy after code changes
docker compose down               # stop (comments are kept)
```

**Back up comments:**

```bash
docker compose cp backend:/data/comments.db ./comments-backup.db
```

**Restore:**

```bash
docker compose cp ./comments-backup.db backend:/data/comments.db && docker compose restart backend
```

`docker compose down -v` deletes the comments volume. Don't use `-v` unless you mean it.

## Security note

The app has no login. Anyone who can reach the port can read proposals, post comments, and delete comments. Keep it on an internal network or VPN, or put it behind a reverse proxy with authentication.

## Troubleshooting

- **Proposals don't show up:** the container runs as a non-root user (uid 10001) and needs read access. Run `chmod -R a+rX proposals/`.
- **SELinux hosts (RHEL, CentOS, Fedora)** may block the bind mount. Change the volume line in `docker-compose.yml` to `${PROPOSALS_PATH:-./proposals}:/proposals:ro,z`.
- **Port already in use:** set another `APP_PORT` in `.env`.

## Local development

```bash
# Backend (http://localhost:8000)
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
PROPOSALS_DIR=../proposals DATA_DIR=../data uvicorn app.main:app --reload

# Frontend (http://localhost:5173, proxies /api to :8000)
cd frontend
npm install
npm run dev
```

### API

| Method   | Path                          | Description                                               |
|----------|-------------------------------|-----------------------------------------------------------|
| `GET`    | `/api/proposals`              | List proposals (title, folder, excerpt, modified, comment count) |
| `GET`    | `/api/proposals/{path}`       | Raw Markdown and metadata for one proposal                |
| `GET`    | `/api/assets/{path}`          | Files referenced from proposals (images and similar)      |
| `GET`    | `/api/comments?proposal=...`  | Comments for a proposal                                   |
| `POST`   | `/api/comments`               | `{proposal, author, body, quote?}`                        |
| `DELETE` | `/api/comments/{id}`          | Delete a comment                                          |
| `GET`    | `/api/health`                 | Health check                                              |
