# proposal-presenter

A small web app for sharing proposals written in Markdown. It lists every `.md` file in a folder; click one to read it rendered and leave comments. Select any text in a proposal to comment on that specific passage.

- **Frontend:** Vue 3 + Vite, served by nginx
- **Backend:** Python (FastAPI), comments stored in SQLite
- **Deploy:** Docker Compose (two containers). Images are published to GHCR by GitHub Actions, and Watchtower on the VM pulls them.

```
browser ──► frontend (nginx :80) ──/api──► backend (FastAPI :8000)
                                             ├── /proposals  ← host folder, read-only
                                             └── /data       ← comments.db (named volume)
```

## Deployment

The VM (`vmw4-raprustandi`) is behind the corporate VPN, so **GitHub can't reach in**. Deployment is **pull-based**, the same as `simple-placement-providers`:

```
push to main → Actions builds both images → GHCR (:latest, :<sha>)
             → Watchtower on the VM polls every 120s → recreates the containers
```

| Service    | Image                                          | Container                       | Host port |
|------------|------------------------------------------------|---------------------------------|-----------|
| `backend`  | `ghcr.io/rifkhia/proposal-presenter-backend`   | `proposal-presenter-backend-1`  | none      |
| `frontend` | `ghcr.io/rifkhia/proposal-presenter-frontend`  | `proposal-presenter-frontend-1` | 8080      |

- `docker-compose.deploy.yml` pulls the published images. The VM uses it.
- `docker-compose.yml` builds from source. Use it for local runs.
- Both files set `name: proposal-presenter`, so they drive the same containers and the same comments volume.

### Watchtower: one per host

The Watchtower in `simple-placement-providers` runs label-enabled across the whole host. It updates any container labelled `com.centurylinklabs.watchtower.enable=true`, in any project. Both services here carry that label, so **that Watchtower deploys this app too**.

Don't start a second Watchtower on the same host. When a Watchtower starts, it stops the other instances it finds. Also, an unscoped Watchtower acts on every labelled container, so two of them would race to recreate the same containers.

`docker-compose.deploy.yml` still has its own `watchtower` service, behind a compose profile. It's only for a host with no Watchtower:

```bash
docker-compose -f docker-compose.deploy.yml --profile watchtower up -d
```

If the `simple-placement-providers` stack is ever removed, start this one so updates keep arriving.

### One-time VM setup

Both GHCR packages must be **public** so the VM and Watchtower can pull without credentials. Set this once in GitHub: open *Packages* → select the package → *Package settings* → *Change visibility* → *Public*. Repeat for both packages. The images contain no secrets; proposals and comments live only on the VM.

```bash
# podman.socket is what Watchtower talks to. podman-restart brings
# restart: always containers back after a reboot.
systemctl enable --now podman-restart.service podman.socket

mkdir -p /opt/proposal-presenter/proposals
cd /opt/proposal-presenter      # copy docker-compose.deploy.yml (and optionally .env) here
docker-compose -f docker-compose.deploy.yml up -d

# Open http://<vm-host>:8080
```

> Keep the deployment in `/opt`, not `/tmp`. `systemd-tmpfiles` clears `/tmp`, and it would take `proposals/` with it.

### Updating a deployment

Push to `main`. That's the whole process. To watch it land:

```bash
podman logs -f simple-placement-providers-watchtower-1
podman inspect proposal-presenter-backend-1 \
  --format '{{.ImageName}} {{index .Config.Labels "org.opencontainers.image.revision"}}'
```

To pull immediately instead of waiting out the poll interval:

```bash
cd /opt/proposal-presenter && docker-compose -f docker-compose.deploy.yml up -d
```

To roll back, point the images at the immutable tag the workflow also pushes (`ghcr.io/rifkhia/proposal-presenter-<service>:<sha>`), or revert the commit.

### Run anywhere else (build from source)

This needs Docker with the Compose plugin.

```bash
cp .env.example .env          # optional: change APP_PORT / PROPOSALS_PATH
docker compose up -d --build  # then open http://<host>:8080
```

## Adding proposals

Put `.md` files into the `proposals/` folder next to the compose file (`/opt/proposal-presenter/proposals/` on the VM), or into whatever folder `PROPOSALS_PATH` in `.env` points to:

```bash
scp my-proposal.md root@vmw4-raprustandi.cdt.spb.openwaygroup.com:/opt/proposal-presenter/proposals/
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

After changing `.env`, run `docker-compose -f docker-compose.deploy.yml up -d` on the VM.

## Operations

On the VM, run these in `/opt/proposal-presenter` (`DC="docker-compose -f docker-compose.deploy.yml"`). Locally, use `docker compose` instead.

```bash
$DC ps                 # status
$DC logs -f backend    # logs
$DC down               # stop (comments are kept)
```

**Back up comments:**

```bash
$DC cp backend:/data/comments.db ./comments-backup.db
```

**Restore:**

```bash
$DC cp ./comments-backup.db backend:/data/comments.db && $DC restart backend
```

`down -v` deletes the comments volume. Don't use `-v` unless you mean it.

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
