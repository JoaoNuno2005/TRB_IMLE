from __future__ import annotations

from pathlib import Path as _PathForSys
import sys as _SysForPath

_ProjectRootForSys = _PathForSys(__file__).resolve().parents[1]
if str(_ProjectRootForSys) not in _SysForPath.path:
    _SysForPath.path.insert(0, str(_ProjectRootForSys))

from collections import defaultdict
from pathlib import Path
from typing import Any

from src import config
from src.rag_memory import RAGMemory
from src.utils import parse_timestamp, period_start, read_json, now_utc_iso


class ReportGenerator:
    def __init__(
        self,
        memory: RAGMemory | None = None,
        inspections_dir: Path | None = None,
        reports_dir: Path | None = None,
    ):
        self.memory = memory or RAGMemory()
        self.inspections_dir = inspections_dir or config.INSPECTIONS_DIR
        self.reports_dir = reports_dir or config.DATA_DIR / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def generate_session_report(
        self,
        inspections: list[dict],
        rule_results: list[dict] | dict | None = None,
        output_path: str | Path | None = None,
        title: str = "Inspection Report",
    ) -> str:
        if isinstance(rule_results, dict):
            rule_results = [rule_results]
        rule_results = rule_results or []
        markdown = self._compose_report(inspections, rule_results, title=title)
        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(markdown, encoding="utf-8")
        return markdown

    def generate_period_report(
        self,
        zone_id: str | None = None,
        period: str | None = None,
        output_path: str | Path | None = None,
    ) -> str:
        inspections = self.load_inspections(zone_id=zone_id, period=period)
        title = "Inspection Report"
        if zone_id:
            title += f" — {zone_id}"
        if period:
            title += f" — {period}"
        return self.generate_session_report(
            inspections,
            [],
            output_path=output_path,
            title=title,
        )

    def load_inspections(
        self,
        zone_id: str | None = None,
        period: str | None = None,
    ) -> list[dict]:
        start = period_start(period)
        records = []

        for path in sorted(self.inspections_dir.rglob("INS_*.json")):
            data = read_json(path)
            if not isinstance(data, dict):
                continue

            if zone_id and data.get("zone_id") != zone_id:
                continue

            timestamp = data.get("timestamp")
            if start and timestamp:
                try:
                    if parse_timestamp(timestamp) < start:
                        continue
                except Exception:
                    continue

            records.append(data)

        records.sort(key=lambda item: item.get("timestamp") or "")
        return records

    def _compose_report(
        self,
        inspections: list[dict],
        rule_results: list[dict],
        title: str,
    ) -> str:
        now = now_utc_iso()
        executive = self._executive_summary(inspections)
        by_zone = self._problems_by_zone(inspections)
        rules = self._rules_section(rule_results, inspections)
        historical = self._historical_context(inspections)
        recommendations = self._recommendations(inspections, rule_results)
        trajectory = self._trajectory_section(inspections)

        parts = [
            f"# {title}",
            f"Gerado em: {now}",
            "",
            "## 1. Sumário executivo",
            executive,
            "",
            "## 2. Problemas por zona",
            by_zone,
            "",
            "## 3. Regras disparadas",
            rules,
            "",
            "## 4. Contexto histórico relevante",
            historical,
            "",
            "## 5. Recomendações",
            recommendations,
            "",
            "## 6. Integração com trajectória",
            trajectory,
            "",
        ]

        return "\n".join(parts)

    def _executive_summary(self, inspections: list[dict]) -> str:
        if not inspections:
            return "Não existem inspeções no período selecionado."

        zones = sorted({i.get("zone_id") for i in inspections if i.get("zone_id")})
        issues = [
            issue
            for inspection in inspections
            for issue in inspection.get("issues", []) or []
            if isinstance(issue, dict)
        ]

        critical_issues = sum(
            1
            for issue in issues
            if self._severity_rank(issue.get("severity")) >= self._severity_rank("high")
        )
        warning_issues = sum(
            1
            for issue in issues
            if self._severity_rank(issue.get("severity")) == self._severity_rank("medium")
        )
        critical_zones = sorted(
            {
                inspection.get("zone_id")
                for inspection in inspections
                if inspection.get("overall_status") == "critical"
            }
        )
        warning_zones = sorted(
            {
                inspection.get("zone_id")
                for inspection in inspections
                if inspection.get("overall_status") == "warning"
            }
        )

        avg_fill = self._average_fill_rate(inspections)

        message = (
            f"Foram inspecionadas {len(zones)} zonas em {len(inspections)} imagem(ns). "
            f"O sistema detetou {len(issues)} problema(s): {critical_issues} crítico(s) "
            f"e {warning_issues} warning(s). "
            f"O fill rate médio observado foi {avg_fill:.1f}%."
        )

        if critical_zones:
            message += f" Prioridade imediata: intervenção nas zonas {', '.join(critical_zones)}."
        elif warning_zones:
            message += f" Recomendação principal: acompanhar as zonas {', '.join(warning_zones)}."
        else:
            message += " Estado geral operacionalmente estável, sem zonas críticas."

        return self._limit_words(message, 150)

    def _problems_by_zone(self, inspections: list[dict]) -> str:
        if not inspections:
            return "Sem inspeções para apresentar."

        grouped = defaultdict(list)
        for inspection in inspections:
            grouped[inspection.get("zone_id") or "Z_UNKNOWN"].append(inspection)

        lines = []

        for zone, records in sorted(grouped.items()):
            zone_issues = [
                issue
                for record in records
                for issue in record.get("issues", []) or []
                if isinstance(issue, dict)
            ]
            avg_fill = self._average_fill_rate(records)

            status_counts = defaultdict(int)
            for record in records:
                status_counts[record.get("overall_status") or "unknown"] += 1

            lines.append(f"### {zone}")
            lines.append(f"- Inspeções analisadas: {len(records)}")
            lines.append(f"- Fill rate médio: {avg_fill:.1f}%")
            lines.append(
                "- Estados observados: "
                + ", ".join(f"{status}: {count}" for status, count in sorted(status_counts.items()))
            )

            if not zone_issues:
                lines.append("- Sem problemas detetados nesta zona.")
                continue

            for issue in zone_issues:
                issue_type = issue.get("type") or "other"
                severity = issue.get("severity") or "unknown"
                location = issue.get("location") or "localização não especificada"
                description = issue.get("description") or "sem descrição"
                confidence = self._format_confidence(issue.get("confidence"))
                affected = self._format_pct(issue.get("affected_area_pct"))

                query = f"{zone} {issue_type} {location} {severity} {description}"
                historical = self._safe_memory_query(query, top_k=2)
                refs = self._refs(historical)

                lines.append(
                    f"- {issue_type} | severidade: {severity} | localização: {location} | "
                    f"área afetada: {affected} | confiança: {confidence} | {description} | "
                    f"histórico: {refs}"
                )

        return "\n".join(lines)

    def _rules_section(
        self,
        rule_results: list[dict],
        inspections: list[dict] | None = None,
    ) -> str:
        triggered = self._extract_triggered_items(rule_results)

        if not triggered and inspections:
            triggered = self._load_triggered_rule_logs(inspections)

        if not triggered and inspections:
            triggered = self._recompute_rule_triggers(inspections)

        if not triggered:
            return "Nenhuma regra foi disparada nesta sessão."

        unique = {}
        for item in triggered:
            if not isinstance(item, dict):
                continue

            key = (
                item.get("rule_id"),
                item.get("inspection_id"),
                item.get("zone_id"),
                item.get("reason"),
                item.get("notification"),
            )
            unique[key] = item

        lines = []

        for item in unique.values():
            rule_id = item.get("rule_id") or "RULE_UNKNOWN"
            inspection_id = item.get("inspection_id") or "INS_UNKNOWN"
            zone_id = item.get("zone_id") or "zona desconhecida"
            reason = item.get("reason") or item.get("message") or "condição operacional satisfeita"
            notification = item.get("notification") or item.get("notification_message") or "sem notificação"
            alert_level = item.get("alert_level") or item.get("level") or "warning"

            lines.append(f"- {rule_id} disparou na inspeção {inspection_id}, zona {zone_id}.")
            lines.append(f"  - Nível de alerta: {alert_level}.")
            lines.append(f"  - Condição ativada: {reason}.")
            lines.append(f"  - Ação gerada: {notification}")

        return "\n".join(lines)

    def _extract_triggered_items(self, obj: Any) -> list[dict]:
        triggered = []

        if isinstance(obj, list):
            for item in obj:
                triggered.extend(self._extract_triggered_items(item))
            return triggered

        if not isinstance(obj, dict):
            return triggered

        for key in ("triggered", "triggered_rules", "fired_rules", "alerts", "notifications"):
            value = obj.get(key)
            if isinstance(value, list):
                for item in value:
                    triggered.extend(self._extract_triggered_items(item))
            elif isinstance(value, dict):
                triggered.extend(self._extract_triggered_items(value))

        if obj.get("triggered") is True:
            triggered.append(obj)
        elif obj.get("rule_id") and any(k in obj for k in ("reason", "notification", "notification_message", "inspection_id")):
            triggered.append(obj)

        return triggered

    def _load_triggered_rule_logs(self, inspections: list[dict]) -> list[dict]:
        inspection_ids = {
            inspection.get("inspection_id")
            for inspection in inspections
            if inspection.get("inspection_id")
        }

        if not inspection_ids:
            return []

        triggered = []
        search_dirs = [
            getattr(config, "RULES_DIR", config.DATA_DIR / "rules"),
            self.inspections_dir,
            self.reports_dir,
        ]

        for base_dir in search_dirs:
            base = Path(base_dir)
            if not base.exists():
                continue

            for path in base.rglob("*.json"):
                data = read_json(path)
                for item in self._extract_triggered_items(data):
                    if item.get("inspection_id") in inspection_ids:
                        triggered.append(item)

        return triggered

    def _load_rules_from_disk(self) -> list[dict]:
        rules_dir = Path(getattr(config, "RULES_DIR", config.DATA_DIR / "rules"))
        rules = []

        if not rules_dir.exists():
            return []

        for path in rules_dir.rglob("*.json"):
            data = read_json(path)

            if isinstance(data, dict) and data.get("rule_id"):
                rules.append(data)
                continue

            if isinstance(data, dict):
                for key in ("rules", "items", "data"):
                    values = data.get(key)
                    if isinstance(values, list):
                        for item in values:
                            if isinstance(item, dict) and item.get("rule_id"):
                                rules.append(item)
                continue

            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("rule_id"):
                        rules.append(item)

        unique = {}
        for rule in rules:
            unique[rule.get("rule_id")] = rule

        return list(unique.values())

    def _recompute_rule_triggers(self, inspections: list[dict]) -> list[dict]:
        rules = self._load_rules_from_disk()
        triggered = []

        for rule in rules:
            validation = rule.get("validation") or {}
            if validation.get("is_valid") is False:
                continue

            for inspection in inspections:
                result = self._evaluate_rule_against_inspection(rule, inspection)
                if result:
                    triggered.append(result)

        return triggered

    def _evaluate_rule_against_inspection(
        self,
        rule: dict,
        inspection: dict,
    ) -> dict | None:
        conditions = rule.get("conditions") or {}
        inspection_id = inspection.get("inspection_id")
        zone_id = inspection.get("zone_id")

        zone_filter = conditions.get("zone_filter") or []
        if isinstance(zone_filter, str):
            zone_filter = [zone_filter]

        if zone_filter and zone_id not in zone_filter and "any" not in zone_filter:
            return None

        if not self._time_matches(inspection.get("timestamp"), conditions.get("time_filter")):
            return None

        reasons = []

        threshold = conditions.get("fill_rate_threshold")
        if threshold is not None:
            fill_rate = self._normalise_rate(inspection.get("shelf_fill_rate"))
            threshold_value = self._normalise_rate(threshold)
            if fill_rate is None or threshold_value is None or fill_rate > threshold_value:
                return None
            reasons.append(
                f"fill rate {fill_rate * 100:.1f}% abaixo ou igual ao limiar {threshold_value * 100:.1f}%"
            )

        issue_types = conditions.get("issue_types") or []
        if isinstance(issue_types, str):
            issue_types = [issue_types]

        severity_threshold = conditions.get("severity_threshold")
        location_filter = conditions.get("location_filter") or "any"

        issue_reason = self._matching_issue_reason(
            inspection.get("issues", []) or [],
            issue_types=issue_types,
            severity_threshold=severity_threshold,
            location_filter=location_filter,
        )

        has_issue_conditions = bool(issue_types or severity_threshold or location_filter not in (None, "", "any"))
        if has_issue_conditions:
            if issue_reason is None:
                return None
            reasons.append(issue_reason)

        if not reasons:
            return None

        rule_id = rule.get("rule_id") or "RULE_UNKNOWN"
        alert_level = (rule.get("action") or {}).get("alert_level") or "warning"
        reason = "; ".join(reasons)

        template = (rule.get("action") or {}).get(
            "notification_message",
            "Regra {rule_id} disparada na zona {zone_id}: {reason}",
        )

        fill_rate = self._normalise_rate(inspection.get("shelf_fill_rate"))
        fill_rate_pct = None if fill_rate is None else f"{fill_rate * 100:.1f}%"

        try:
            notification = template.format(
                rule_id=rule_id,
                zone_id=zone_id,
                inspection_id=inspection_id,
                reason=reason,
                alert_level=alert_level,
                fill_rate=fill_rate,
                fill_rate_pct=fill_rate_pct,
            )
        except Exception:
            notification = f"Regra {rule_id} disparada na zona {zone_id}: {reason}"

        return {
            "rule_id": rule_id,
            "inspection_id": inspection_id,
            "zone_id": zone_id,
            "triggered": True,
            "alert_level": alert_level,
            "reason": reason,
            "notification": notification,
        }

    def _matching_issue_reason(
        self,
        issues: list[dict],
        issue_types: list[str],
        severity_threshold: str | None,
        location_filter: str | None,
    ) -> str | None:
        for issue in issues:
            if not isinstance(issue, dict):
                continue

            issue_type = issue.get("type")
            severity = issue.get("severity")
            location = issue.get("location") or ""

            if issue_types and issue_type not in issue_types:
                continue

            if severity_threshold and self._severity_rank(severity) < self._severity_rank(severity_threshold):
                continue

            if location_filter not in (None, "", "any") and not self._location_matches(location, location_filter):
                continue

            return (
                f"issue {issue_type or 'desconhecido'} com severidade {severity or 'unknown'} "
                f"em {location or 'localização não especificada'}"
            )

        return None

    def _historical_context(self, inspections: list[dict]) -> str:
        if not inspections:
            return "Sem contexto histórico relevante."

        queries = []
        for inspection in inspections[:8]:
            issues = inspection.get("issues", []) or []
            issue_types = " ".join(
                issue.get("type", "")
                for issue in issues
                if isinstance(issue, dict)
            )
            queries.append(
                f"histórico zona {inspection.get('zone_id')} estado {inspection.get('overall_status')} "
                f"fill rate {inspection.get('shelf_fill_rate')} {issue_types}"
            )

        retrieved = []
        seen = set()

        for query in queries:
            for item in self._safe_memory_query(query, top_k=3):
                meta = item.get("metadata", {}) or {}
                key = item.get("chunk_id") or meta.get("inspection_id") or item.get("document")
                if key and key not in seen:
                    seen.add(key)
                    retrieved.append(item)

        if retrieved:
            lines = []
            for item in retrieved[:6]:
                meta = item.get("metadata", {}) or {}
                inspection_id = meta.get("inspection_id") or "INS_UNKNOWN"
                timestamp = meta.get("timestamp") or "data desconhecida"
                zone_id = meta.get("zone_id") or "zona desconhecida"
                document = item.get("document") or item.get("text") or "sem descrição histórica"
                lines.append(f"- {inspection_id} | {timestamp} | {zone_id}: {document}")
            return "\n".join(lines)

        fallback = self._historical_fallback_from_disk(inspections)
        if fallback:
            return fallback

        return "Não foram recuperados padrões históricos relevantes na memória vetorial."

    def _historical_fallback_from_disk(self, inspections: list[dict]) -> str:
        current_ids = {
            inspection.get("inspection_id")
            for inspection in inspections
            if inspection.get("inspection_id")
        }
        current_zones = {
            inspection.get("zone_id")
            for inspection in inspections
            if inspection.get("zone_id")
        }

        if not current_zones:
            return ""

        candidates = []
        for path in sorted(self.inspections_dir.rglob("INS_*.json")):
            data = read_json(path)
            if not isinstance(data, dict):
                continue

            if data.get("inspection_id") in current_ids:
                continue

            if data.get("zone_id") not in current_zones:
                continue

            candidates.append(data)

        candidates.sort(key=lambda item: item.get("timestamp") or "", reverse=True)

        lines = []
        for item in candidates[:6]:
            issues = item.get("issues", []) or []
            issue_types = [
                issue.get("type")
                for issue in issues
                if isinstance(issue, dict) and issue.get("type")
            ]
            issue_text = ", ".join(issue_types) if issue_types else "sem issues registados"
            fill_rate = self._format_pct(item.get("shelf_fill_rate"))
            lines.append(
                f"- {item.get('inspection_id')} | {item.get('timestamp')} | {item.get('zone_id')}: "
                f"estado {item.get('overall_status')}, fill rate {fill_rate}, issues: {issue_text}"
            )

        return "\n".join(lines)

    def _recommendations(
        self,
        inspections: list[dict],
        rule_results: list[dict],
    ) -> str:
        issues = []
        for inspection in inspections:
            for issue in inspection.get("issues", []) or []:
                if isinstance(issue, dict):
                    enriched = dict(issue)
                    enriched["zone_id"] = inspection.get("zone_id")
                    enriched["inspection_id"] = inspection.get("inspection_id")
                    issues.append(enriched)

        if not issues:
            return "1. Manter monitorização normal e repetir inspeção visual no próximo ciclo operacional."

        priority = sorted(
            issues,
            key=lambda item: (
                -self._severity_rank(item.get("severity")),
                item.get("zone_id") or "",
                item.get("type") or "",
            ),
        )

        recommendations = []

        for issue in priority:
            issue_type = issue.get("type")
            zone = issue.get("zone_id") or "zona não identificada"
            location = issue.get("location") or "localização não especificada"

            if issue_type == "empty_shelf":
                rec = f"Repor produto na {zone}, em {location}, e validar stock de retaguarda antes do próximo ciclo de afluência."
            elif issue_type == "wrong_product":
                rec = f"Corrigir o planograma na {zone}, em {location}, e confirmar etiqueta, preço e categoria do produto exposto."
            elif issue_type == "damaged":
                rec = f"Remover produto danificado ou tombado na {zone}, em {location}, e substituir por unidade vendável."
            elif issue_type == "misaligned":
                rec = f"Realinhar produtos na {zone}, em {location}, garantindo facing uniforme e visibilidade frontal."
            elif issue_type == "label_missing":
                rec = f"Repor etiqueta em falta na {zone}, em {location}, e validar correspondência entre preço físico e sistema."
            elif issue_type in ("dirty", "dirty_misaligned"):
                rec = f"Limpar e reorganizar a prateleira na {zone}, em {location}, removendo embalagens soltas ou desalinhadas."
            else:
                rec = f"Verificar manualmente o problema assinalado na {zone}, em {location}, e registar a decisão operacional."

            if rec not in recommendations:
                recommendations.append(rec)

            if len(recommendations) == 5:
                break

        return "\n".join(
            f"{idx + 1}. {rec}"
            for idx, rec in enumerate(recommendations)
        )

    def _trajectory_section(self, inspections: list[dict]) -> str:
        trajectory_dir = Path(getattr(config, "TRAJECTORY_DIR", config.DATA_DIR / "trajectory"))
        csv_path = trajectory_dir / "traffic.csv"

        if not csv_path.exists():
            return "Integração não ativa: não existe data/trajectory/traffic.csv."

        try:
            import pandas as pd

            df = pd.read_csv(csv_path)
        except Exception:
            return "Integração não ativa: não foi possível ler data/trajectory/traffic.csv."

        required = {"timestamp", "zone_id"}
        if not required.issubset(df.columns):
            return "Integração não ativa: o ficheiro de trajectória deve conter timestamp e zone_id."

        lines = []

        for inspection in inspections:
            zone = inspection.get("zone_id")
            if not zone:
                continue

            zone_df = df[df["zone_id"] == zone]
            if zone_df.empty:
                continue

            fill_rate = self._format_pct(inspection.get("shelf_fill_rate"))

            if "traffic_index" in zone_df.columns:
                avg = round(float(zone_df["traffic_index"].mean()), 3)
                lines.append(
                    f"- {zone}: índice médio de afluência {avg}; fill rate observado {fill_rate}. "
                    "Quando a afluência é elevada e o fill rate é baixo, a causa provável pode ser procura superior à reposição."
                )
            elif "visitors" in zone_df.columns:
                avg = round(float(zone_df["visitors"].mean()), 1)
                lines.append(
                    f"- {zone}: média de {avg} visitantes nos dados de trajectória; fill rate observado {fill_rate}."
                )
            elif "dwell_time" in zone_df.columns:
                avg = round(float(zone_df["dwell_time"].mean()), 1)
                lines.append(
                    f"- {zone}: dwell time médio {avg}; fill rate observado {fill_rate}."
                )

        return "\n".join(lines) if lines else "Sem correspondências úteis entre inspeções e dados de trajectória."

    def _refs(self, retrieved: list[dict]) -> str:
        refs = []

        for item in retrieved:
            meta = item.get("metadata", {}) or {}
            inspection_id = meta.get("inspection_id")
            timestamp = meta.get("timestamp")

            if inspection_id:
                if timestamp:
                    refs.append(f"{inspection_id} em {timestamp}")
                else:
                    refs.append(str(inspection_id))

        return "; ".join(refs) if refs else "sem registos semelhantes"

    def _safe_memory_query(self, query: str, top_k: int = 3) -> list[dict]:
        try:
            result = self.memory.query(query, top_k=top_k)
            return result if isinstance(result, list) else []
        except Exception:
            return []

    def _time_matches(self, timestamp: str | None, time_filter: dict | None) -> bool:
        if not time_filter:
            return True

        if not timestamp:
            return False

        try:
            hour = parse_timestamp(timestamp).hour
        except Exception:
            return False

        start = time_filter.get("hours_start")
        end = time_filter.get("hours_end")

        if start is None and end is None:
            return True

        if start is None:
            return hour <= int(end)

        if end is None:
            return hour >= int(start)

        start = int(start)
        end = int(end)

        if start <= end:
            return start <= hour <= end

        return hour >= start or hour <= end

    def _location_matches(self, location: str, location_filter: str) -> bool:
        location = location.lower()
        location_filter = str(location_filter).lower()

        aliases = {
            "bottom": ["bottom", "inferior", "baixo", "base"],
            "middle": ["middle", "meio", "central", "centro"],
            "top": ["top", "superior", "cima", "alto"],
            "left": ["left", "esquerda"],
            "right": ["right", "direita"],
        }

        terms = aliases.get(location_filter, [location_filter])
        return any(term in location for term in terms)

    def _average_fill_rate(self, inspections: list[dict]) -> float:
        values = []

        for inspection in inspections:
            value = self._normalise_rate(inspection.get("shelf_fill_rate"))
            if value is not None:
                values.append(value)

        if not values:
            return 0.0

        return sum(values) / len(values) * 100

    def _normalise_rate(self, value: Any) -> float | None:
        if value is None:
            return None

        try:
            numeric = float(value)
        except Exception:
            return None

        if numeric < 0:
            return 0.0

        if numeric > 1:
            return min(numeric / 100, 1.0)

        return numeric

    def _format_pct(self, value: Any) -> str:
        normalised = self._normalise_rate(value)
        if normalised is None:
            return "n/d"
        return f"{normalised * 100:.1f}%"

    def _format_confidence(self, value: Any) -> str:
        if value is None:
            return "n/d"

        try:
            numeric = float(value)
        except Exception:
            return "n/d"

        if numeric <= 1:
            return f"{numeric * 100:.1f}%"

        return f"{numeric:.1f}%"

    def _severity_rank(self, severity: Any) -> int:
        severity = str(severity or "").lower()
        return {
            "none": 0,
            "ok": 0,
            "low": 1,
            "medium": 2,
            "warning": 2,
            "high": 3,
            "critical": 3,
        }.get(severity, 0)

    def _limit_words(self, text: str, max_words: int) -> str:
        words = text.split()
        if len(words) <= max_words:
            return text
        return " ".join(words[:max_words]).rstrip(".,;:") + "."


def main():
    import argparse

    parser = argparse.ArgumentParser(prog="report_generator.py")
    parser.add_argument("--zone")
    parser.add_argument("--period")
    parser.add_argument("--output")
    args = parser.parse_args()

    generator = ReportGenerator()
    report = generator.generate_period_report(
        zone_id=args.zone,
        period=args.period,
        output_path=args.output,
    )
    print(report)


if __name__ == "__main__":
    main()
