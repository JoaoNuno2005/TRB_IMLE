from pathlib import Path
import os
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
IMAGES_DIR = DATA_DIR / "images"
INSPECTIONS_DIR = DATA_DIR / "inspections"
RULES_DIR = DATA_DIR / "rules"
TRAJECTORY_DIR = DATA_DIR / "trajectory"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
CACHE_DIR = PROJECT_ROOT / "cache"
VECTORSTORE_DIR = PROJECT_ROOT / "vectorstore"
EVALUATION_DIR = PROJECT_ROOT / "evaluation"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0") or 0)
TP2_MOCK_LLM = os.getenv("TP2_MOCK_LLM", "0").strip().lower() in {"1", "true", "yes", "sim"}

RATE_LIMIT_REQUESTS = int(os.getenv("TP2_RATE_LIMIT_REQUESTS", "15") or 15)
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("TP2_RATE_LIMIT_WINDOW_SECONDS", "60") or 60)
DEFAULT_TOP_K = int(os.getenv("TP2_DEFAULT_TOP_K", "3") or 3)

for path in [DATA_DIR, IMAGES_DIR, INSPECTIONS_DIR, RULES_DIR, TRAJECTORY_DIR, PROMPTS_DIR, CACHE_DIR, VECTORSTORE_DIR, EVALUATION_DIR]:
    path.mkdir(parents=True, exist_ok=True)
