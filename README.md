# proposal-presenter

A small web app for sharing proposals written in Markdown. It lists every `.md` file in a folder. Click one to read it and discuss it in comment threads, the way you'd review a pull request on GitHub or Bitbucket.

- **Inline comments:** select text, or hover a block and click **+**, to comment on that passage. Each inline thread shows the source line it refers to (for example `Line 12` or `Lines 17–21`). Click it to jump to the passage, which is then highlighted.
- **Rendered / Source toggle:** Source shows the raw Markdown with line numbers. Click a line number to comment on that line, or shift-click a second one to comment on a range.
- **Replies and resolving:** reply to any thread, and resolve it when it's settled. Resolved threads move to the *Resolved* tab and can be reopened.
- **Shareable links:** *Copy link* on a thread gives a URL (`?thread=12`) that opens the proposal with that thread selected.
- **Editing in the browser:** editors sign in with a shared password and edit the Markdown directly (see [Editing](#editing)). The editor highlights lines that have comments. As you type, the comment markers move with the text, and hovering a marker shows the comment.
- **Comments follow edits:** when a proposal changes, whether edited in the app or replaced on disk, each comment's line numbers move with its text. A thread whose quoted text is gone is marked *Outdated*.

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
| `frontend` | `ghcr.io/rifkhia/proposal-presenter-frontend`  | `proposal-presenter-frontend-1` | 127.0.0.1:8080 (served on 443 by the host nginx, see [HTTPS](#https)) |

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

# Then set up HTTPS (next section) and open https://<vm-host>/
```

> Keep the deployment in `/opt`, not `/tmp`. `systemd-tmpfiles` clears `/tmp`, and it would take `proposals/` with it.

### HTTPS

The app is live at **https://vmw4-raprustandi.cdt.spb.openwaygroup.com/**.

How it's wired:
- The **host's nginx** handles HTTPS on port 443, using `nginx-vm.conf`, installed as `/etc/nginx/conf.d/proposal-presenter.conf`.
- It forwards to the app on `127.0.0.1:8080`.
- The app container is published on loopback only (`APP_PORT=127.0.0.1:8080` in `.env`), so there is no plain-HTTP way in, and the editor password always travels encrypted.
- Port 80 on this host belongs to simple-placement-providers and isn't touched.

**Certificate: a private CA that only covers this hostname.** Company laptops don't necessarily trust the OpenWay Group CA (this Mac has none of its certificates), and the VM isn't reachable for Let's Encrypt. So the server certificate is signed by a small private CA, `proposal-presenter local CA (vmw4-raprustandi)`, which you install once per device. The CA carries a critical *name constraint* limiting it to `vmw4-raprustandi.cdt.spb.openwaygroup.com`, so trusting it can't be abused to impersonate any other site: a certificate it signs for another name fails with "permitted subtree violation".

A self-signed certificate with a "click to proceed" warning is **not** an option on this host. Chrome already has an HSTS record for this hostname, most likely from the Vault UI that ran here on `:8200`, and HSTS forbids clicking through certificate errors.

**Install the CA once per device** (the file is [`certs/proposal-presenter-ca.crt`](certs/proposal-presenter-ca.crt)). Then fully quit and reopen the browser.

- **macOS:**
  ```bash
  sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain certs/proposal-presenter-ca.crt
  ```
- **Windows:** double-click the file, choose *Install Certificate*, then *Current User*, then *Place all certificates in: Trusted Root Certification Authorities*.
- **Linux (Chrome):**
  ```bash
  certutil -d sql:$HOME/.pki/nssdb -A -t "C,," -n proposal-presenter-ca -i certs/proposal-presenter-ca.crt
  ```

SHA-256 fingerprint to check against: `5E:86:74:F6:5F:17:6A:3A:9D:78:94:88:15:D7:7E:61:A0:DE:45:21:75:82:79:DC:6A:74:8D:92:DA:FF:32:71`.

| File on the VM (`/etc/pki/nginx/`) | What |
|---|---|
| `private/vmw4-raprustandi.key` | Server key (root only) |
| `vmw4-raprustandi.crt` | Server certificate nginx serves, signed by the local CA, valid until Oct 2027 |
| `vmw4-raprustandi.csr` | Certificate request for the same key, in case IT issues an OpenWay certificate later |
| `local-ca.crt`, `private/local-ca.key` | The local CA, valid until Sep 2031. Keep the key root-only; it's what signs renewals |
| `local-ca.cnf`, `leaf.ext` | The settings the CA and the server certificate were made with |

**Renewing the server certificate** before it expires. Devices keep trusting the CA, so nobody reinstalls anything:

```bash
cd /etc/pki/nginx
openssl x509 -req -sha256 -days 397 -in vmw4-raprustandi.csr -CA local-ca.crt -CAkey private/local-ca.key \
  -CAserial local-ca.srl -extfile leaf.ext -out vmw4-raprustandi.crt
nginx -t && systemctl reload nginx
```

**Switching to an OpenWay certificate instead** (only worth it once every device trusts the OpenWay Group Root CA): send `vmw4-raprustandi.csr` to IT, put the returned certificate followed by its intermediates into `vmw4-raprustandi.crt`, and reload nginx.

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

> Comments are tied to a proposal's file path. Replacing a file under the **same name** keeps its comments, and their line numbers follow the text (see [How comments follow edits](#how-comments-follow-edits)). A **new name**, for example `plan-v2.md`, starts with no comments. The old ones stay with `plan.md` and come back if that file returns.

## Configuration (`.env`)

| Variable         | Default       | Meaning                                                  |
|------------------|---------------|----------------------------------------------------------|
| `APP_PORT`       | `8080`        | Host port the app is published on. `127.0.0.1:8080` on the VM, so only the HTTPS proxy can reach it |
| `PROPOSALS_PATH` | `./proposals` | Host folder with the Markdown files                      |
| `EDIT_PASSWORD_HASH` | *(empty)* | Hash of the editor password. Empty means editing is off (see [Editing](#editing)) |

After changing `.env`, run `docker-compose -f docker-compose.deploy.yml up -d` on the VM. Watchtower only swaps images; it never picks up `.env` or compose-file changes.

## Editing

Editing is **off** until you set a password. There is one shared editor password, and the server only ever stores a hash of it.

**1. Generate the hash.** You type the password twice; only the hash is printed.

```bash
cd /opt/proposal-presenter
docker-compose -f docker-compose.deploy.yml run --rm --no-deps backend python -m app.hashpw
```

**2. Put the hash in `.env`** next to the compose file. Paste it as-is, without quotes:

```
EDIT_PASSWORD_HASH=pbkdf2_sha256:600000:<salt>:<hash>
```

**3. Let the app write to the proposals folder.** The backend runs as uid 10001, and saving replaces the file through a temp file in the same folder:

```bash
chown -R 10001:10001 /opt/proposal-presenter/proposals
```

Files you later copy in as root stay editable. Saving only needs the *folder* to be writable, not the file. A subfolder you create yourself needs the same `chown`. Until then, the Edit button is greyed out on proposals in that folder.

**4. Apply:** run `docker-compose -f docker-compose.deploy.yml up -d`.

To change the password, repeat steps 1, 2 and 4. Changing it signs everyone out.

### How editing works

- Click **Edit** on a proposal and enter the password. You stay signed in for 12 hours (HttpOnly cookie).
- After 5 wrong passwords, sign-in from that address is blocked for 5 minutes.
- Lines with open comments are highlighted, with a bubble in the margin:
  - Hover a bubble to read the comment; click it to open the thread in the panel.
  - While you type, the bubbles move with the text, and the panel's chips show the live position, for example `Line 9 (was 7)`.
  - An orange bubble means you changed a commented line.
- **Ctrl/⌘ + S** saves.
- If someone else saved, or the file changed on disk, since you started editing, you're asked whether to overwrite their version or discard yours.

### How comments follow edits

The server keeps a copy of the last version of each proposal it served. When the file on disk differs from that copy, whether saved in the app or replaced over `scp`, it compares the two versions line by line and moves each thread:

| Commented lines... | Thread moves to... |
|---|---|
| unchanged, but lines were added or removed above | the same text at its new line numbers |
| rewritten | the rewritten lines |
| deleted | the line after the deletion |

A thread whose quoted text no longer appears anywhere is labelled *Outdated* and keeps its quote for context. After a save, the app tells you how many threads moved and how many are on lines you changed.

The line comparison needs the server to have seen the previous version. If a file is replaced twice before anyone opens it, the comparison runs from the last version it saw, which is still correct. The only case it can't follow is a file that already differed from its comments before this feature was deployed. Those threads still find their passage by quoted text in the Rendered view.

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

Reading and commenting are open: anyone who can reach the port can read proposals, post, resolve and delete comments. Only **editing proposals** needs the editor password. Keep the app on an internal network or VPN.

Sign-in details:
- The password is checked against a PBKDF2-SHA256 hash (600,000 iterations).
- Sessions are HMAC-signed, HttpOnly, `SameSite=Strict` cookies. The signing key lives in the data volume and is mixed with the password hash, so changing the password invalidates every session.
- The app is only reachable over HTTPS (see [HTTPS](#https)), and the session cookie is marked `Secure`.
- The certificate comes from a private CA that is name-constrained to this one hostname (see [HTTPS](#https)). Installing that CA on a device lets it verify this server, and nothing else.
- The sign-in lockout counts failures per client address. The app's nginx takes that address from the `X-Real-IP` header only when the request comes from loopback or a container bridge network (a proxy on the same host), so clients can't fake it.

## Troubleshooting

- **Proposals don't show up:** the container runs as a non-root user (uid 10001) and needs read access. Run `chmod -R a+rX proposals/`.
- **SELinux hosts (RHEL, CentOS, Fedora)** may block the bind mount. Add `:z` to the volume line in the compose file: `${PROPOSALS_PATH:-./proposals}:/proposals:z`.
- **Port already in use:** set another `APP_PORT` in `.env`.
- **Edit button missing:** `EDIT_PASSWORD_HASH` isn't set, or wasn't applied with `up -d`. `docker-compose -f docker-compose.deploy.yml logs backend` shows the reason on startup; a malformed hash is logged as an error.
- **Edit button greyed out:** the proposal's folder isn't writable by uid 10001. See step 3 under [Editing](#editing).

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
| `GET`    | `/api/proposals`              | List proposals (title, folder, excerpt, modified, comment count, open threads) |
| `GET`    | `/api/proposals/{path}`       | Raw Markdown and metadata (`version`, `writable`) for one proposal |
| `PUT`    | `/api/proposals/{path}`       | Save (editor only): `{content, base_version, force?}`. Returns 409 if the file changed since `base_version` |
| `GET`    | `/api/assets/{path}`          | Files referenced from proposals (images and similar)      |
| `GET`    | `/api/comments?proposal=...`  | Threads for a proposal, each with its `replies`           |
| `POST`   | `/api/comments`               | Start a thread `{proposal, author, body, quote?, line_start?, line_end?, version?}`, or reply with `{proposal, author, body, parent_id}`. An inline thread made against an old `version` gets 409 |
| `PATCH`  | `/api/comments/{id}`          | Resolve or reopen a thread: `{resolved, by?}`             |
| `DELETE` | `/api/comments/{id}`          | Delete a reply, or a thread together with its replies     |
| `GET`    | `/api/auth`                   | `{enabled, signed_in}`                                    |
| `POST`   | `/api/auth/login`             | `{password}`; sets the session cookie                     |
| `POST`   | `/api/auth/logout`            | Clears the session cookie                                 |
| `GET`    | `/api/health`                 | Health check                                              |
