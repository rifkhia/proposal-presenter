import os
from pathlib import Path

PROPOSALS_DIR = Path(os.environ.get("PROPOSALS_DIR", "./proposals")).resolve()
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data")).resolve()
