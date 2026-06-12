import json
from pathlib import Path
from collections import defaultdict

GROUND_TRUTH_PATH = Path("data/ground_truth.json")
OUTPUTS_DIR = Path("data/evaluation_strategy_outputs")
REPORT_PATH = Path("data/evaluation_prompting_report.json")

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def normalize_path(path):
    return str(path).replace("\\", "/")

def expected_main_type(expected_types):
    if not expected_types:
        return None
    return expected_types[0]

def has_expected_issue(predicted_issues, expected_types):
    if not expected_types:
        return len(predicted_issues) == 0
    predicted_types = {issue.get("type") for issue in predicted_issues}
    return any(t in predicted_types for t in expected_types)

def severity_match(predicted_issues, expected_types):
    if not expected_types:
        return True
    relevant = [i for i in predicted_issues if i.get("type") in expected_types]
    if not relevant:
        return False
    return any(i.get("severity") in ["low", "medium", "high"] for i in relevant)

def hallucination_flag(record):
    text = " ".join([
        str(record.get("model_reasoning", "")),
        str(record.get("summary", "")),
        " ".join(str(i.get("description", "")) for i in record.get("issues", []) or [])
    ]).lower()

    suspicious = [
        "mock",
        "não especificados",
        "não consigo ver",
        "não é possível analisar",
        "imagem indisponível"
    ]

    return any(s in text for s in suspicious)

def evaluate_strategy(strategy, ground_truth_records):
    files = sorted((OUTPUTS_DIR / strategy).glob("*.json"))

    by_image = {}
    for path in files:
        data = load_json(path)
        image_path = normalize_path(data.get("image_path", ""))
        by_image[image_path] = data

    total = len(ground_truth_records)
    found_outputs = 0
    correct_issue_detection = 0
    false_positive_cases = 0
    severity_correct = 0
    json_parse_ok = 0
    hallucinations = 0
    status_correct = 0

    details = []

    for gt in ground_truth_records:
        image_path = normalize_path(gt["image_path"])
        expected_types = gt.get("expected_issue_types", [])
        expected_status = gt.get("expected_status")

        pred = by_image.get(image_path)

        if pred is None:
            details.append({
                "image_path": image_path,
                "found_output": False,
                "expected_issue_types": expected_types,
                "predicted_issue_types": [],
                "issue_detection_correct": False
            })
            continue

        found_outputs += 1
        json_parse_ok += 1

        issues = pred.get("issues", []) or []
        predicted_types = [i.get("type") for i in issues if i.get("type")]

        issue_ok = has_expected_issue(issues, expected_types)
        if issue_ok:
            correct_issue_detection += 1

        if not expected_types and predicted_types:
            false_positive_cases += 1
        elif expected_types:
            unexpected = [t for t in predicted_types if t not in expected_types]
            if unexpected:
                false_positive_cases += 1

        sev_ok = severity_match(issues, expected_types)
        if sev_ok:
            severity_correct += 1

        if pred.get("overall_status") == expected_status:
            status_correct += 1

        hallucinated = hallucination_flag(pred)
        if hallucinated:
            hallucinations += 1

        details.append({
            "image_path": image_path,
            "found_output": True,
            "expected_status": expected_status,
            "predicted_status": pred.get("overall_status"),
            "expected_issue_types": expected_types,
            "predicted_issue_types": predicted_types,
            "issue_detection_correct": issue_ok,
            "severity_valid": sev_ok,
            "hallucination_flag": hallucinated
        })

    def pct(x, denom=total):
        return round((x / denom) * 100, 2) if denom else 0.0

    return {
        "strategy": strategy,
        "total_ground_truth_images": total,
        "outputs_found": found_outputs,
        "json_parse_rate": pct(json_parse_ok),
        "issue_detection_rate": pct(correct_issue_detection),
        "false_positive_rate": pct(false_positive_cases),
        "severity_accuracy": pct(severity_correct),
        "status_accuracy": pct(status_correct),
        "hallucination_rate": pct(hallucinations),
        "details": details
    }

def main():
    gt = load_json(GROUND_TRUTH_PATH)
    records = gt["records"]

    strategies = ["zero_shot", "cot_visual", "few_shot"]

    report = {
        "dataset": {
            "ground_truth_path": str(GROUND_TRUTH_PATH),
            "num_images": len(records)
        },
        "strategies": {},
        "summary_table": []
    }

    for strategy in strategies:
        result = evaluate_strategy(strategy, records)
        report["strategies"][strategy] = result
        report["summary_table"].append({
            "strategy": strategy,
            "outputs_found": result["outputs_found"],
            "json_parse_rate": result["json_parse_rate"],
            "issue_detection_rate": result["issue_detection_rate"],
            "false_positive_rate": result["false_positive_rate"],
            "severity_accuracy": result["severity_accuracy"],
            "status_accuracy": result["status_accuracy"],
            "hallucination_rate": result["hallucination_rate"]
        })

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report["summary_table"], ensure_ascii=False, indent=2))
    print("Guardado em:", REPORT_PATH)

if __name__ == "__main__":
    main()
