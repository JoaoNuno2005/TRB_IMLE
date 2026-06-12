from __future__ import annotations

from pathlib import Path
from typing import Any

from src.utils import clamp_float, ensure_list, make_id, normalize_choice, now_utc_iso, VALID_ISSUE_TYPES, VALID_SEVERITIES, VALID_STATUSES, VALID_ALERT_LEVELS


def normalize_issue(raw: dict[str, Any], index: int = 1) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    return {
        "issue_id": str(data.get("issue_id") or f"ISS_{index:03d}"),
        "type": normalize_choice(data.get("type"), VALID_ISSUE_TYPES, "other"),
        "location": str(data.get("location") or "não especificado"),
        "severity": normalize_choice(data.get("severity"), VALID_SEVERITIES, "medium"),
        "description": str(data.get("description") or "Problema operacional identificado na prateleira."),
        "confidence": clamp_float(data.get("confidence", 0.0)),
        "affected_area_pct": clamp_float(data.get("affected_area_pct", 0.0)),
    }


def normalize_inspection(raw: dict[str, Any], image_path: str | Path, zone_id: str) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    issues = [normalize_issue(item, i + 1) for i, item in enumerate(ensure_list(data.get("issues")))]
    status = normalize_choice(data.get("overall_status"), VALID_STATUSES, "ok" if not issues else "warning")
    if any(issue["severity"] == "high" for issue in issues):
        status = "critical"
    products = [str(x) for x in ensure_list(data.get("products_detected")) if str(x).strip()]
    inspection = {
        "inspection_id": str(data.get("inspection_id") or make_id("INS")),
        "timestamp": str(data.get("timestamp") or now_utc_iso()),
        "image_path": str(data.get("image_path") or image_path),
        "zone_id": str(data.get("zone_id") or zone_id),
        "overall_status": status,
        "issues": issues,
        "shelf_fill_rate": clamp_float(data.get("shelf_fill_rate", 1.0 if not issues else 0.7)),
        "products_detected": products,
        "model_reasoning": str(data.get("model_reasoning") or data.get("visual_evidence") or "Evidência visual não detalhada pelo modelo."),
    }
    if data.get("summary"):
        inspection["summary"] = str(data.get("summary"))
    else:
        inspection["summary"] = build_local_summary(inspection)
    return inspection


def build_local_summary(inspection: dict[str, Any]) -> str:
    zone = inspection.get("zone_id", "zona não especificada")
    fill = round(float(inspection.get("shelf_fill_rate", 0)) * 100, 1)
    status = inspection.get("overall_status", "indefinido")
    issues = inspection.get("issues", []) or []
    if not issues:
        return f"Inspeção {inspection.get('inspection_id')} na {zone}: prateleira sem problemas visíveis, fill rate {fill}%, estado {status}."
    parts = []
    for issue in issues:
        parts.append(f"{issue.get('type')} com severidade {issue.get('severity')} em {issue.get('location')}: {issue.get('description')}")
    return f"Inspeção {inspection.get('inspection_id')} na {zone}: fill rate {fill}%, estado {status}. Issues detetados: " + "; ".join(parts)


def normalize_rule(raw: dict[str, Any], natural_language: str | None = None, rule_id: str | None = None) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    conditions = data.get("conditions") if isinstance(data.get("conditions"), dict) else {}
    action = data.get("action") if isinstance(data.get("action"), dict) else {}
    validation = data.get("validation") if isinstance(data.get("validation"), dict) else {}
    zone_filter = [str(x).upper() for x in ensure_list(conditions.get("zone_filter")) if str(x).strip()]
    issue_types = [normalize_choice(x, VALID_ISSUE_TYPES, "other") for x in ensure_list(conditions.get("issue_types")) if str(x).strip()]
    time_filter = conditions.get("time_filter") if isinstance(conditions.get("time_filter"), dict) else {}
    hours_start = time_filter.get("hours_start")
    hours_end = time_filter.get("hours_end")
    try:
        hours_start = None if hours_start is None else int(hours_start)
    except (TypeError, ValueError):
        hours_start = None
    try:
        hours_end = None if hours_end is None else int(hours_end)
    except (TypeError, ValueError):
        hours_end = None
    location_filter = str(conditions.get("location_filter") or "any").lower()
    if location_filter not in {"bottom", "middle", "top", "any"}:
        location_filter = "any"
    fill_rate_threshold = conditions.get("fill_rate_threshold")
    fill_rate_threshold = None if fill_rate_threshold is None else clamp_float(fill_rate_threshold)
    return {
        "rule_id": str(data.get("rule_id") or rule_id or make_id("RULE")),
        "created_at": str(data.get("created_at") or now_utc_iso()),
        "natural_language": str(data.get("natural_language") or natural_language or ""),
        "description": str(data.get("description") or natural_language or "Regra sem descrição."),
        "conditions": {
            "zone_filter": zone_filter,
            "time_filter": {"hours_start": hours_start, "hours_end": hours_end},
            "issue_types": sorted(set(issue_types)),
            "severity_threshold": normalize_choice(conditions.get("severity_threshold"), VALID_SEVERITIES, None) if conditions.get("severity_threshold") else None,
            "fill_rate_threshold": fill_rate_threshold,
            "location_filter": location_filter,
        },
        "action": {
            "alert_level": normalize_choice(action.get("alert_level"), VALID_ALERT_LEVELS, "warning"),
            "notification_message": str(action.get("notification_message") or "Regra {rule_id} disparada na zona {zone_id}: {reason}"),
        },
        "validation": {
            "is_valid": bool(validation.get("is_valid", True)),
            "ambiguities": [str(x) for x in ensure_list(validation.get("ambiguities")) if str(x).strip()],
            "assumptions": [str(x) for x in ensure_list(validation.get("assumptions")) if str(x).strip()],
        },
    }
