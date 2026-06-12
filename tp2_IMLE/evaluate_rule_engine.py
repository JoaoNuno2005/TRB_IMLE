import json
from pathlib import Path

RULES_DIR = Path("data/rules")
OUTPUT_PATH = Path("data/evaluation_rule_engine.json")

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def collect_rules():
    rules = []

    if not RULES_DIR.exists():
        return rules

    for path in RULES_DIR.rglob("*.json"):
        try:
            data = load_json(path)
        except Exception:
            continue

        if isinstance(data, dict) and data.get("rule_id"):
            rules.append(data)

        elif isinstance(data, dict):
            for key in ["rules", "items", "data"]:
                values = data.get(key)
                if isinstance(values, list):
                    for item in values:
                        if isinstance(item, dict) and item.get("rule_id"):
                            rules.append(item)

        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("rule_id"):
                    rules.append(item)

    unique = {}
    for rule in rules:
        unique[rule["rule_id"]] = rule

    return list(unique.values())

def can_parse_rule(rule):
    required = ["rule_id", "natural_language", "conditions", "action", "validation"]
    return all(k in rule for k in required)

def is_ambiguous(rule):
    validation = rule.get("validation") or {}
    ambiguities = validation.get("ambiguities") or []
    return len(ambiguities) > 0 or validation.get("is_valid") is False

def should_trigger(rule, inspection):
    validation = rule.get("validation") or {}
    if validation.get("is_valid") is False:
        return False

    conditions = rule.get("conditions") or {}
    threshold = conditions.get("fill_rate_threshold")
    zone_filter = conditions.get("zone_filter") or []
    issue_types = conditions.get("issue_types") or []

    if zone_filter and inspection.get("zone_id") not in zone_filter:
        return False

    if threshold is not None:
        try:
            if float(inspection.get("shelf_fill_rate")) <= float(threshold):
                return True
        except Exception:
            pass

    if issue_types:
        issues = inspection.get("issues") or []
        for issue in issues:
            if issue.get("type") in issue_types:
                return True

    return False

def main():
    rules = collect_rules()

    synthetic_inspections = [
        {
            "inspection_id": "SYN_001",
            "zone_id": "Z_S2",
            "shelf_fill_rate": 0.75,
            "issues": [
                {
                    "type": "empty_shelf",
                    "severity": "high",
                    "location": "prateleira inferior"
                }
            ]
        },
        {
            "inspection_id": "SYN_002",
            "zone_id": "Z_S1",
            "shelf_fill_rate": 0.92,
            "issues": []
        }
    ]

    expected = {
        "RULE_001": {
            "ambiguous": True,
            "valid": False
        },
        "RULE_002": {
            "ambiguous": True,
            "valid": False
        },
        "RULE_003": {
            "ambiguous": False,
            "valid": True,
            "should_trigger_on_SYN_001": True,
            "should_trigger_on_SYN_002": False
        }
    }

    parsed = 0
    ambiguity_correct = 0
    correctness_tests = 0
    correctness_ok = 0

    details = []

    for rule in rules:
        rule_id = rule.get("rule_id")
        parsed_ok = can_parse_rule(rule)
        if parsed_ok:
            parsed += 1

        ambiguous_pred = is_ambiguous(rule)
        expected_info = expected.get(rule_id, {})

        ambiguous_expected = expected_info.get("ambiguous")
        if ambiguous_expected is not None and ambiguous_pred == ambiguous_expected:
            ambiguity_correct += 1

        rule_detail = {
            "rule_id": rule_id,
            "natural_language": rule.get("natural_language"),
            "parsed_ok": parsed_ok,
            "validation_is_valid": (rule.get("validation") or {}).get("is_valid"),
            "ambiguities": (rule.get("validation") or {}).get("ambiguities", []),
            "synthetic_tests": []
        }

        for inspection in synthetic_inspections:
            key = f"should_trigger_on_{inspection['inspection_id']}"
            if key not in expected_info:
                continue

            correctness_tests += 1
            predicted = should_trigger(rule, inspection)
            expected_trigger = expected_info[key]

            if predicted == expected_trigger:
                correctness_ok += 1

            rule_detail["synthetic_tests"].append({
                "inspection_id": inspection["inspection_id"],
                "predicted_trigger": predicted,
                "expected_trigger": expected_trigger,
                "correct": predicted == expected_trigger
            })

        details.append(rule_detail)

    total_rules = len(rules)

    report = {
        "num_rules": total_rules,
        "metrics": {
            "rule_parse_rate": round((parsed / total_rules) * 100, 2) if total_rules else 0,
            "rule_correctness": round((correctness_ok / correctness_tests) * 100, 2) if correctness_tests else 0,
            "ambiguity_detection": round((ambiguity_correct / len(expected)) * 100, 2) if expected else 0
        },
        "details": details,
        "notes": [
            "RULE_001 e RULE_002 foram mantidas como exemplos de regras ambíguas/incompletas detetadas pelo sistema.",
            "RULE_003 é a regra válida usada para testar execução operacional sobre inspeções sintéticas.",
            "A avaliação é local e não depende da API Gemini."
        ]
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("Guardado em:", OUTPUT_PATH)

if __name__ == "__main__":
    main()
