from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
KB_DIR = DATA_DIR / "knowledge_base"
ORDERS_PATH = DATA_DIR / "orders.json"
TICKETS_PATH = DATA_DIR / "tickets.json"
