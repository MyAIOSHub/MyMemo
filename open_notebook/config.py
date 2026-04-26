import os

# ROOT DATA FOLDER
DATA_FOLDER = "./data"

# LANGGRAPH CHECKPOINT FILE
sqlite_folder = f"{DATA_FOLDER}/sqlite-db"
os.makedirs(sqlite_folder, exist_ok=True)
LANGGRAPH_CHECKPOINT_FILE = f"{sqlite_folder}/checkpoints.sqlite"

# UPLOADS FOLDER
UPLOADS_FOLDER = f"{DATA_FOLDER}/uploads"
os.makedirs(UPLOADS_FOLDER, exist_ok=True)

# TIKTOKEN CACHE FOLDER
# Reads TIKTOKEN_CACHE_DIR from the environment so Docker can redirect the cache
# to a path outside /data/ (which is typically volume-mounted and would hide the
# pre-baked encoding baked into the image at build time).
TIKTOKEN_CACHE_DIR = os.environ.get("TIKTOKEN_CACHE_DIR", "").strip() or f"{DATA_FOLDER}/tiktoken-cache"
os.makedirs(TIKTOKEN_CACHE_DIR, exist_ok=True)

# MEMORY HUB
MEMORY_HUB_URL = os.environ.get("MEMORY_HUB_URL", "http://localhost:1995")
MEMORY_HUB_USER_ID = os.environ.get("MEMORY_HUB_USER_ID", "mymemo_user")

# Origins to drop from browse/search/materialize results.
# Default blocks the high-volume noisy sources; set MEMORY_BLOCKED_ORIGINS=""
# to disable, or override with a comma-separated list.
_blocked_raw = os.environ.get("MEMORY_BLOCKED_ORIGINS", "browser,claude_code")
MEMORY_BLOCKED_ORIGINS = frozenset(
    s.strip() for s in _blocked_raw.split(",") if s.strip()
)
