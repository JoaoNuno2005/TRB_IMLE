from __future__ import annotations

from pathlib import Path
import json
import random
import re
import time

from PIL import Image

from src import config
from src.utils import extract_json, now_utc_iso, read_json, write_json


class LLMUnavailableError(RuntimeError):
    pass


class RateLimiter:
    def __init__(self, state_path: Path, max_requests: int, window_seconds: int):
        self.state_path = state_path
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def wait(self) -> None:
        now = time.time()
        state = read_json(self.state_path, {"timestamps": []}) or {"timestamps": []}
        timestamps = [float(x) for x in state.get("timestamps", []) if now - float(x) < self.window_seconds]
        if len(timestamps) >= self.max_requests:
            wait_seconds = self.window_seconds - (now - min(timestamps)) + 0.25
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            now = time.time()
            timestamps = [float(x) for x in timestamps if now - float(x) < self.window_seconds]
        timestamps.append(now)
        write_json(self.state_path, {"timestamps": timestamps})


class GeminiClient:
    def __init__(self, api_key: str | None = None, model_name: str | None = None, temperature: float | None = None):
        self.api_key = api_key if api_key is not None else config.GEMINI_API_KEY
        self.model_name = model_name or config.GEMINI_MODEL
        self.temperature = config.GEMINI_TEMPERATURE if temperature is None else temperature
        self.mock = config.TP2_MOCK_LLM
        self.rate_limiter = RateLimiter(config.CACHE_DIR / "rate_limit_state.json", config.RATE_LIMIT_REQUESTS, config.RATE_LIMIT_WINDOW_SECONDS)
        self._model = None
        self._genai = None
        if self.api_key and not self.mock:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._genai = genai
                self._model = genai.GenerativeModel(self.model_name)
            except Exception as exc:
                raise LLMUnavailableError(f"Não foi possível inicializar o Gemini: {exc}") from exc

    def available(self) -> bool:
        return bool(self._model) or self.mock

    def generate_text(self, prompt: str, expect_json: bool = False):
        if self.mock:
            return self._mock_text(prompt, expect_json)
        if not self._model:
            raise LLMUnavailableError("GEMINI_API_KEY não configurada ou modelo indisponível.")
        return self._call_with_backoff([prompt], expect_json=expect_json)

    def generate_with_image(self, prompt: str, image_path: str | Path, expect_json: bool = False):
        if self.mock:
            return self._mock_image(prompt, image_path, expect_json)
        if not self._model:
            raise LLMUnavailableError("GEMINI_API_KEY não configurada ou modelo indisponível.")
        image = Image.open(image_path)
        return self._call_with_backoff([prompt, image], expect_json=expect_json)

    def _call_with_backoff(self, parts, expect_json: bool = False):
        last_error = None
        for attempt in range(6):
            self.rate_limiter.wait()
            try:
                response = self._model.generate_content(
                    parts,
                    generation_config={"temperature": self.temperature, "response_mime_type": "application/json" if expect_json else "text/plain"},
                )
                text = getattr(response, "text", "") or ""
                if expect_json:
                    return extract_json(text)
                return text.strip()
            except Exception as exc:
                last_error = exc
                message = str(exc).lower()
                if "429" in message or "quota" in message or "rate" in message:
                    time.sleep(min(60, 2 ** attempt + random.random()))
                    continue
                if attempt < 2:
                    time.sleep(1 + attempt)
                    continue
                break
        raise LLMUnavailableError(f"Falha na chamada ao modelo ou quota indisponível: {last_error}") from last_error

    def _mock_text(self, prompt: str, expect_json: bool = False):
        if "schema de configuração" in prompt.lower() or "rule_id" in prompt.lower() and "natural_language" in prompt.lower():
            return self._mock_rule(prompt) if expect_json else json.dumps(self._mock_rule(prompt), ensure_ascii=False)
        if "juiz" in prompt.lower() or "judge" in prompt.lower() or "pontuação" in prompt.lower():
            data = {"score": 3, "justification": "Avaliação mock neutra sem chamada externa ao modelo.", "supported_claims": [], "unsupported_claims": []}
            return data if expect_json else json.dumps(data, ensure_ascii=False)
        data = {"answer": "Resposta mock gerada sem API. Configure GEMINI_API_KEY para síntese real.", "references": []}
        return data if expect_json else data["answer"]

    def _mock_image(self, prompt: str, image_path: str | Path, expect_json: bool = False):
        path = Path(image_path)
        name = path.stem.lower()
        issues = []
        fill = 0.92
        status = "ok"
        if any(x in name for x in ["empty", "vazia", "vazio", "stockout"]):
            fill = 0.45
            status = "critical"
            issues.append({"issue_id": "ISS_001", "type": "empty_shelf", "location": "prateleira central", "severity": "high", "description": "Zona da prateleira aparenta estar com falta significativa de produto.", "confidence": 0.62, "affected_area_pct": 0.35})
        if any(x in name for x in ["dirty", "suja", "mess", "desordenada"]):
            fill = min(fill, 0.72)
            status = "warning" if status == "ok" else status
            issues.append({"issue_id": f"ISS_{len(issues)+1:03d}", "type": "misaligned", "location": "lado direito", "severity": "medium", "description": "Produtos aparentam estar desalinhados ou desordenados.", "confidence": 0.58, "affected_area_pct": 0.22})
        if any(x in name for x in ["wrong", "plano", "planograma"]):
            fill = min(fill, 0.8)
            status = "warning" if status == "ok" else status
            issues.append({"issue_id": f"ISS_{len(issues)+1:03d}", "type": "wrong_product", "location": "secção intermédia", "severity": "medium", "description": "Possível produto fora da posição prevista no planograma.", "confidence": 0.55, "affected_area_pct": 0.18})
        result = {
            "inspection_id": f"INS_MOCK_{int(time.time())}",
            "timestamp": now_utc_iso(),
            "image_path": str(image_path),
            "zone_id": self._extract_zone(prompt) or "Z_UNKNOWN",
            "overall_status": status,
            "issues": issues,
            "shelf_fill_rate": fill,
            "products_detected": ["produtos de retalho não especificados"],
            "model_reasoning": "Observação visual mock: foram avaliadas zonas superior, central e inferior; a classificação segue indícios no nome do ficheiro porque TP2_MOCK_LLM está ativo.",
            "summary": f"Inspeção mock da imagem {path.name} com estado {status}, fill rate {round(fill * 100, 1)}% e {len(issues)} issues.",
        }
        return result if expect_json else json.dumps(result, ensure_ascii=False)

    def _extract_zone(self, text: str) -> str | None:
        match = re.search(r"Z_[A-Z]+\d+", text.upper())
        return match.group(0) if match else None

    def _mock_rule(self, prompt: str):
        match = re.search(r"REGRA_ORIGINAL:\s*(.+)", prompt, re.DOTALL)
        text = match.group(1).strip().split("\n")[0] if match else prompt[-300:]
        lower = text.lower()
        issue_types = []
        threshold = None
        location = "any"
        alert = "warning"
        ambiguities = []
        if "vazia" in lower or "vazio" in lower:
            issue_types.append("empty_shelf")
            pct = re.search(r"(\d+(?:[,.]\d+)?)\s*%\s*(?:vazia|vazio|empty)", lower)
            if pct:
                threshold = 1 - float(pct.group(1).replace(",", ".")) / 100
            else:
                ambiguities.append("Não é claro se prateleira vazia significa 0% de produto ou abaixo de uma percentagem.")
        if "fill rate" in lower or "taxa" in lower:
            pct = re.search(r"(?:abaixo de|inferior a|below)\s*(\d+(?:[,.]\d+)?)\s*%", lower)
            if pct:
                threshold = float(pct.group(1).replace(",", ".")) / 100
        if "tombado" in lower or "danificado" in lower:
            issue_types.append("damaged")
        if "inferior" in lower or "baixo" in lower:
            location = "bottom"
        if "superior" in lower or "cima" in lower:
            location = "top"
        if "crítico" in lower or "critico" in lower or "imediatamente" in lower or "urgente" in lower:
            alert = "critical"
        elif "não é urgente" in lower or "nao e urgente" in lower:
            alert = "info"
        zones = re.findall(r"Z_[A-Z]+\d+", text.upper())
        if not zones:
            zones = []
        time_filter = {"hours_start": None, "hours_end": None}
        hours = re.search(r"entre\s+as?\s*(\d{1,2})h?\s+e\s+as?\s*(\d{1,2})h?", lower)
        if hours:
            time_filter = {"hours_start": int(hours.group(1)), "hours_end": int(hours.group(2))}
        if not issue_types and threshold is None:
            ambiguities.append("Não foi identificado um tipo de problema nem um limiar operacional executável.")
        return {
            "rule_id": "RULE_MOCK",
            "created_at": now_utc_iso(),
            "natural_language": text,
            "description": f"Regra operacional derivada de: {text}",
            "conditions": {
                "zone_filter": zones,
                "time_filter": time_filter,
                "issue_types": sorted(set(issue_types)),
                "severity_threshold": "high" if "severidade alta" in lower else None,
                "fill_rate_threshold": threshold,
                "location_filter": location,
            },
            "action": {"alert_level": alert, "notification_message": "Regra {rule_id} disparada na zona {zone_id}: {reason}"},
            "validation": {"is_valid": len(ambiguities) == 0, "ambiguities": ambiguities, "assumptions": ["Conversão local mock usada por falta de API Gemini."]},
        }
