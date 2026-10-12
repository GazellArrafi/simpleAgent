"""Konfigurasi terpusat: path, setting dari .env, dan ambang batas aturan (lihat rules.md)."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
OUTBOX_FILE = DATA_DIR / "outbox.json"

MODEL_NAME = os.getenv("MODEL_NAME", "openrouter:openai/gpt-4o-mini").strip()
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1500"))  # batas jawaban per panggilan (hemat kredit)
SIM_DATE = os.getenv("SIM_DATE", "").strip() or None

# --- Sumber data (markdown/database.md) ---
DATA_BACKEND = os.getenv("DATA_BACKEND", "json").strip().lower()  # json | postgres
DATABASE_ADMIN_URL = os.getenv("DATABASE_ADMIN_URL", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DATABASE_READONLY_URL = os.getenv("DATABASE_READONLY_URL", "").strip()

TELEGRAM_BOT_TOKEN =os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_DEMO_CHAT_ID = os.getenv("TELEGRAM_DEMO_CHAT_ID", "").strip()

# --- Asumsi produk kartu kredit ---
CC_INTEREST_MONTHLY = 0.0175
CC_MIN_PAYMENT_PCT = 0.05
CC_MIN_PAYMENT_FLOOR = 50_000
CC_LATE_FEE_PCT = 0.01
CC_LATE_FEE_CAP = 100_000
CC_DUE_DAYS = 20

# --- Ambang batas aturan (rules.md bagian A & B) ---
RULES = {
    # A1 billing
    "due_soon_days": 3,
    "due_critical_days": 1,
    "due_upcoming_days": 7,
    "min_payment_streak": 3,
    # A2 limit
    "util_critical": 0.95,
    "util_high": 0.80,
    # A3 spending
    "spike_pct": 0.40,
    "spike_warning_pct": 0.80,
    "spike_min_delta": 1_000_000,
    "spend_income_ratio": 0.70,
    "unusual_multiplier": 5,
    "unusual_min_amount": 5_000_000,
    # A4 loan
    "loan_due_days": 5,
    # B supervisor
    "max_messages_per_run": 3,
    # C komunikasi
    "quiet_hours": (21, 8),
    "max_body_chars": 700,
}

ANALYSIS_WINDOW_DAYS = 120  # transaksi yang diambil Data Agent untuk analisa
