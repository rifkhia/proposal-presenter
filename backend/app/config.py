import os
from pathlib import Path

PROPOSALS_DIR = Path(os.environ.get("PROPOSALS_DIR", "./proposals")).resolve()
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data")).resolve()

# Hash of the shared editor password (see `python -m app.hashpw`). Unset = editing disabled.
EDIT_PASSWORD_HASH = os.environ.get("EDIT_PASSWORD_HASH", "").strip()
