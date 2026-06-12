from __future__ import annotations

from pathlib import Path as _PathForSys
import sys as _SysForPath
_ProjectRootForSys = _PathForSys(__file__).resolve().parents[1]
if str(_ProjectRootForSys) not in _SysForPath.path:
    _SysForPath.path.insert(0, str(_ProjectRootForSys))


from pathlib import Path
import json
import re

from src import config
from src.llm_client import GeminiClient, LLMUnavailableError
from src.schemas import normalize_rule
from src.utils import append_jsonl, detect_location_bucket, make_id, now_utc_iso, parse_timestamp, read_json, read_text, severity_at_least, write_json


class RuleEngine:
    def __init__(self, rules_path: Path | None = None, logs_path: Path | None = None, llm: GeminiClient | None = None):
        self.rules_path = rules_path or config.RULES_DIR / "rules.json"
        self.logs_path = logs_path or config.RULES_DIR / "rule_execution_logs.jsonl"
        self.llm = llm or GeminiClient()
        if not self.rules_path.exists():
            write_json(self.rules_path, [])

    def list_rules(self) -> list[dict]:
        rules = read_json(self.rules_path, [])
        return rules if isinstance(rules, list) else []

    def save_rules(self, rules: list[dict]) -> None:
        write_json(self.rules_path, rules)

    def parse_rule(self, natural_language: str) -> dict:
        template = read_text(config.PROMPTS_DIR / "rule_parser.txt")
        prompt = template.replace("{rule_text}", natural_language.strip())
        try:
            raw = self.llm.generate_text(prompt, expect_json=True)
        except LLMUnavailableError:
            raw = self._local_parse_rule(natural_language)
        rule = normalize_rule(raw, natural_language=natural_language, rule_id=self._next_rule_id())
        if raw.get("rule_id") in {"RULE_MOCK", "RULE_001", None}:
            rule["rule_id"] = self._next_rule_id()
        return rule

    def add_rule(self, natural_language: str, save_invalid: bool = False) -> dict:
        rule = self.parse_rule(natural_language)
        if not rule["validation"]["is_valid"] and not save_invalid:
            return rule
        rules = self.list_rules()
        rules.append(rule)
        self.save_rules(rules)
        return rule

    def delete_rule(self, rule_id: str) -> bool:
        rules = self.list_rules()
        kept = [r for r in rules if r.get("rule_id") != rule_id]
        self.save_rules(kept)
        return len(kept) != len(rules)

    def get_rule(self, rule_id: str) -> dict | None:
        for rule in self.list_rules():
            if rule.get("rule_id") == rule_id:
                return rule
        return None

    def execute_rules(self, inspection: dict, rules: list[dict] | None = None) -> dict:
        rules_to_check = rules if rules is not None else self.list_rules()
        checked = []
        triggered = []
        for rule in rules_to_check:
            result = self._evaluate_rule(rule, inspection)
            checked.append(result)
            if result["triggered"]:
                triggered.append(result)
            append_jsonl(self.logs_path, result)
        return {"inspection_id": inspection.get("inspection_id"), "checked": checked, "triggered": triggered}

    def _evaluate_rule(self, rule: dict, inspection: dict) -> dict:
        conditions = rule.get("conditions", {}) or {}
        reasons = []
        failures = []
        zone_filter = conditions.get("zone_filter") or []
        zone_id = inspection.get("zone_id")
        if zone_filter and zone_id not in zone_filter:
            failures.append(f"zona {zone_id} fora do filtro {zone_filter}")
        time_filter = conditions.get("time_filter") or {}
        if not self._time_matches(inspection.get("timestamp"), time_filter):
            failures.append("hora fora do filtro temporal")
        fill_threshold = conditions.get("fill_rate_threshold")
        if fill_threshold is not None:
            fill = float(inspection.get("shelf_fill_rate", 1.0))
            if fill <= float(fill_threshold):
                reasons.append(f"fill rate {round(fill * 100, 1)}% abaixo ou igual ao limiar {round(float(fill_threshold) * 100, 1)}%")
            else:
                failures.append(f"fill rate {round(fill * 100, 1)}% acima do limiar {round(float(fill_threshold) * 100, 1)}%")
        issue_types = conditions.get("issue_types") or []
        severity_threshold = conditions.get("severity_threshold")
        location_filter = conditions.get("location_filter") or "any"
        matched_issues = []
        if issue_types or severity_threshold or location_filter != "any":
            for issue in inspection.get("issues", []) or []:
                issue_match = True
                if issue_types and issue.get("type") not in issue_types:
                    issue_match = False
                if severity_threshold and not severity_at_least(issue.get("severity"), severity_threshold):
                    issue_match = False
                if location_filter != "any" and detect_location_bucket(issue.get("location")) != location_filter:
                    issue_match = False
                if issue_match:
                    matched_issues.append(issue)
            if matched_issues:
                reasons.append(f"{len(matched_issues)} issue(s) compatíveis com tipo/severidade/localização")
            else:
                failures.append("nenhum issue correspondeu aos filtros de tipo, severidade e localização")
        operational_conditions = [fill_threshold is not None, bool(issue_types), bool(severity_threshold), location_filter != "any"]
        if not any(operational_conditions):
            failures.append("regra sem condições operacionais executáveis")
        triggered = len(failures) == 0 and len(reasons) > 0
        reason_text = "; ".join(reasons) if reasons else "; ".join(failures)
        notification = None
        if triggered:
            notification = self._render_notification(rule, inspection, reason_text)
        return {
            "execution_id": make_id("EXEC"),
            "timestamp": now_utc_iso(),
            "rule_id": rule.get("rule_id"),
            "inspection_id": inspection.get("inspection_id"),
            "zone_id": zone_id,
            "triggered": triggered,
            "reason": reason_text,
            "notification": notification,
            "matched_issues": matched_issues,
        }

    def _time_matches(self, timestamp: str | None, time_filter: dict) -> bool:
        start = time_filter.get("hours_start")
        end = time_filter.get("hours_end")
        if start is None and end is None:
            return True
        hour = parse_timestamp(timestamp).hour
        if start is not None and end is not None:
            if int(start) <= int(end):
                return int(start) <= hour < int(end)
            return hour >= int(start) or hour < int(end)
        if start is not None:
            return hour >= int(start)
        return hour < int(end)

    def _render_notification(self, rule: dict, inspection: dict, reason: str) -> str:
        template = rule.get("action", {}).get("notification_message") or "Regra {rule_id} disparada na zona {zone_id}: {reason}"
        values = {
            "rule_id": rule.get("rule_id"),
            "zone_id": inspection.get("zone_id"),
            "inspection_id": inspection.get("inspection_id"),
            "reason": reason,
            "alert_level": rule.get("action", {}).get("alert_level"),
            "fill_rate": inspection.get("shelf_fill_rate"),
            "status": inspection.get("overall_status"),
        }
        try:
            return template.format(**values)
        except Exception:
            return f"Regra {rule.get('rule_id')} disparada na zona {inspection.get('zone_id')}: {reason}"

    def _next_rule_id(self) -> str:
        highest = 0
        for rule in self.list_rules():
            match = re.search(r"RULE_(\d+)$", str(rule.get("rule_id", "")))
            if match:
                highest = max(highest, int(match.group(1)))
        return f"RULE_{highest + 1:03d}"

    def _local_parse_rule(self, natural_language: str) -> dict:
        text = natural_language.strip()
        lower = text.lower()
        issue_types = []
        assumptions = ["Conversão local usada porque a API LLM não estava disponível."]
        ambiguities = []
        fill_threshold = None
        if any(x in lower for x in ["vazia", "vazio", "stock", "sem produto"]):
            issue_types.append("empty_shelf")
            empty_pct = re.search(r"(?:mais de|acima de|superior a)\s*(\d+(?:[,.]\d+)?)\s*%\s*(?:vazia|vazio)", lower)
            if empty_pct:
                fill_threshold = 1.0 - float(empty_pct.group(1).replace(",", ".")) / 100.0
            else:
                ambiguities.append("Não é claro se 'vazia' significa 0% de produto ou abaixo de uma percentagem concreta.")
        fill_pct = re.search(r"fill\s*rate.*?(?:abaixo de|inferior a|<)\s*(\d+(?:[,.]\d+)?)\s*%", lower)
        if fill_pct:
            fill_threshold = float(fill_pct.group(1).replace(",", ".")) / 100.0
        if any(x in lower for x in ["produto errado", "posição errada", "planograma", "fora de posição"]):
            issue_types.append("wrong_product")
        if any(x in lower for x in ["tombado", "danificado", "embalagem danificada"]):
            issue_types.append("damaged")
        if any(x in lower for x in ["desalinhado", "desordenado", "suja", "sujo"]):
            issue_types.append("misaligned")
        if any(x in lower for x in ["etiqueta ausente", "sem etiqueta"]):
            issue_types.append("label_missing")
        zones = sorted(set(re.findall(r"Z_[A-Z]+\d+", text.upper())))
        location = "any"
        if any(x in lower for x in ["inferior", "baixo"]):
            location = "bottom"
        elif any(x in lower for x in ["superior", "cima"]):
            location = "top"
        elif any(x in lower for x in ["intermédia", "intermedia", "central", "meio"]):
            location = "middle"
        time_filter = {"hours_start": None, "hours_end": None}
        hours = re.search(r"entre\s+as?\s*(\d{1,2})h?\s+e\s+as?\s*(\d{1,2})h?", lower)
        if hours:
            time_filter = {"hours_start": int(hours.group(1)), "hours_end": int(hours.group(2))}
        alert = "warning"
        if any(x in lower for x in ["crítico", "critico", "imediatamente", "urgente"]):
            alert = "critical"
        if any(x in lower for x in ["não é urgente", "nao e urgente", "informativo", "info"]):
            alert = "info"
        severity_threshold = None
        if any(x in lower for x in ["severidade alta", "sempre severidade alta"]):
            severity_threshold = "high"
        elif "severidade média" in lower or "severidade media" in lower:
            severity_threshold = "medium"
        elif "severidade baixa" in lower:
            severity_threshold = "low"
        if not zones:
            assumptions.append("Regra aplicada a todas as zonas por ausência de filtro explícito de zona.")
        if not issue_types and fill_threshold is None and severity_threshold is None:
            ambiguities.append("Não foi detetada uma condição operacional executável.")
        return {
            "rule_id": self._next_rule_id(),
            "created_at": now_utc_iso(),
            "natural_language": text,
            "description": f"Regra convertida para monitorização automática: {text}",
            "conditions": {
                "zone_filter": zones,
                "time_filter": time_filter,
                "issue_types": sorted(set(issue_types)),
                "severity_threshold": severity_threshold,
                "fill_rate_threshold": fill_threshold,
                "location_filter": location,
            },
            "action": {
                "alert_level": alert,
                "notification_message": "Regra {rule_id} disparada na zona {zone_id}: {reason}",
            },
            "validation": {
                "is_valid": len(ambiguities) == 0,
                "ambiguities": ambiguities,
                "assumptions": assumptions,
            },
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(prog="rule_engine.py")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("text")
    sub.add_parser("list")
    delete = sub.add_parser("delete")
    delete.add_argument("rule_id")
    args = parser.parse_args()
    engine = RuleEngine()
    if args.command == "add":
        print(json.dumps(engine.add_rule(args.text), ensure_ascii=False, indent=2))
    elif args.command == "list":
        print(json.dumps(engine.list_rules(), ensure_ascii=False, indent=2))
    elif args.command == "delete":
        print(json.dumps({"deleted": engine.delete_rule(args.rule_id)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
