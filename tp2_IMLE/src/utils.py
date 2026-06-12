from __future__ import annotations

from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from pathlib import Path
import hashlib
import json
import re
import uuid

SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3}
STATUS_ORDER = {"ok": 1, "warning": 2, "critical": 3}
VALID_ISSUE_TYPES = {"empty_shelf", "wrong_product", "damaged", "misaligned", "label_missing", "other"}
VALID_SEVERITIES = {"low", "medium", "high"}
VALID_STATUSES = {"ok", "warning", "critical"}
VALID_ALERT_LEVELS = {"info", "warning", "critical"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_utc_iso() -> str:
    return now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str | None) -> datetime:
    if not value:
        return now_utc()
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return now_utc()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def make_id(prefix: str) -> str:
    stamp = now_utc().strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:6].upper()
    return f"{prefix}_{stamp}_{suffix}"


def file_md5(path: str | Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path: str | Path, default: str = "") -> str:
    p = Path(path)
    if not p.exists():
        return default
    return p.read_text(encoding="utf-8")


def read_json(path: str | Path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: str | Path, data) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: str | Path, data) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def extract_json(text: str):
    if not text:
        raise ValueError("Resposta vazia do modelo")
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    candidates = []
    stack = []
    start = None
    for i, ch in enumerate(stripped):
        if ch in "[{":
            if not stack:
                start = i
            stack.append(ch)
        elif ch in "]}":
            if stack:
                stack.pop()
                if not stack and start is not None:
                    candidates.append(stripped[start:i + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError("Não foi possível extrair JSON válido da resposta do modelo")


def clamp_float(value, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


def normalize_choice(value, valid, default):
    if isinstance(value, str) and value.strip().lower() in valid:
        return value.strip().lower()
    return default


def ensure_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def severity_at_least(actual: str, threshold: str | None) -> bool:
    if not threshold:
        return True
    return SEVERITY_ORDER.get(actual, 0) >= SEVERITY_ORDER.get(threshold, 0)


def detect_location_bucket(text: str | None) -> str:
    t = (text or "").lower()
    if any(x in t for x in ["inferior", "baixo", "bottom", "base", "lower"]):
        return "bottom"
    if any(x in t for x in ["superior", "cima", "top", "upper"]):
        return "top"
    if any(x in t for x in ["meio", "médio", "media", "central", "middle", "center", "centro"]):
        return "middle"
    return "any"


def period_start(period: str | None) -> datetime | None:
    if not period:
        return None
    p = period.lower().strip()
    now = now_utc()
    if p in {"today", "hoje"}:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if p in {"this week", "esta semana"}:
        start = now - timedelta(days=now.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    if p in {"this month", "este mês", "este mes"}:
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    match = re.search(r"(last|últimos|ultimos|últimas|ultimas)\s+(\d+)\s+(day|days|dias|semana|semanas|week|weeks)", p)
    if match:
        n = int(match.group(2))
        unit = match.group(3)
        if unit in {"semana", "semanas", "week", "weeks"}:
            n *= 7
        return now - timedelta(days=n)
    match = re.search(r"(\d+)\s+(day|days|dias)", p)
    if match:
        return now - timedelta(days=int(match.group(1)))
    return None


def list_image_files(path: str | Path):
    p = Path(path)
    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    if not p.exists():
        return []
    return sorted([x for x in p.rglob("*") if x.suffix.lower() in exts])


def zone_from_filename(path: str | Path, default: str = "Z_UNKNOWN") -> str:
    name = Path(path).stem.upper()
    match = re.search(r"Z_[A-Z]+\d+", name)
    if match:
        return match.group(0)
    match = re.search(r"Z\d+", name)
    if match:
        return "Z_" + match.group(0)[1:]
    return default


def compact_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
