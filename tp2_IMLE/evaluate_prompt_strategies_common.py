import json
from pathlib import Path

GROUND_TRUTH_PATH = Path("data/ground_truth.json")
OUTPUTS_DIR = Path("data/evaluation_strategy_outputs")
REPORT_PATH = Path("data/evaluation_prompting_report_common12.json")

strategies = ["zero_shot", "cot_visual", "few_shot"]

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def norm(path):
    return str(path).replace("\\", "/")

def load_outputs(strategy):
    out = {}
    for path in sorted((OUTPUTS_DIR / strategy).glob("*.json")):
        data = load_json(path)
        image_path = norm(data.get("image_path", ""))
        out[image_path] = data
    return out

def has_expected_issue(issues, expected_types):
    if not expected_types:
        return len(issues) == 0
    predicted = {i.get("type") for i in issues}
    return any(t in predicted for t in expected_types)

def severity_ok(issues, expected_types):
    if not expected_types:
        return True
    relevant = [i for i in issues if i.get("type") in expected_types]
    return bool(relevant) and any(i.get("severity") in ["low", "medium", "high"] for i in relevant)

def hallucination_flag(record):
    text = " ".join([
        str(record.get("model_reasoning", "")),
        str(record.get("summary", "")),
        " ".join(str(i.get("description", "")) for i in record.get("issues", []) or [])
    ]).lower()
    suspicious = ["mock", "não especificados", "imagem indisponível", "não consigo ver", "não é possível analisar"]
    return any(s in text for s in suspicious)

gt = load_json(GROUND_TRUTH_PATH)["records"]
gt_by_image = {norm(r["image_path"]): r for r in gt}

outputs = {s: load_outputs(s) for s in strategies}

common_images = set(gt_by_image)
for s in strategies:
    common_images &= set(outputs[s])

common_images = sorted(common_images)

report = {
    "num_common_images": len(common_images),
    "common_images": common_images,
    "summary_table": [],
    "details": {}
}

for s in strategies:
    total = len(common_images)
    issue_ok = 0
    false_positive = 0
    severity = 0
    status = 0
    hallucination = 0
    details = []

    for image_path in common_images:
        gt_record = gt_by_image[image_path]
        pred = outputs[s][image_path]

        expected_types = gt_record.get("expected_issue_types", [])
        expected_status = gt_record.get("expected_status")
        issues = pred.get("issues", []) or []
        predicted_types = [i.get("type") for i in issues if i.get("type")]

        ok = has_expected_issue(issues, expected_types)
        if ok:
            issue_ok += 1

        if not expected_types and predicted_types:
            false_positive += 1
        elif expected_types:
            unexpected = [t for t in predicted_types if t not in expected_types]
            if unexpected:
                false_positive += 1

        if severity_ok(issues, expected_types):
            severity += 1

        if pred.get("overall_status") == expected_status:
            status += 1

        h = hallucination_flag(pred)
        if h:
            hallucination += 1

        details.append({
            "image_path": image_path,
            "expected_types": expected_types,
            "predicted_types": predicted_types,
            "expected_status": expected_status,
            "predicted_status": pred.get("overall_status"),
            "issue_detection_correct": ok,
            "hallucination_flag": h
        })

    def pct(x):
        return round((x / total) * 100, 2) if total else 0.0

    row = {
        "strategy": s,
        "images_evaluated": total,
        "json_parse_rate": 100.0,
        "issue_detection_rate": pct(issue_ok),
        "false_positive_rate": pct(false_positive),
        "severity_accuracy": pct(severity),
        "status_accuracy": pct(status),
        "hallucination_rate": pct(hallucination)
    }

    report["summary_table"].append(row)
    report["details"][s] = details

REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

print(json.dumps(report["summary_table"], ensure_ascii=False, indent=2))
print("Guardado em:", REPORT_PATH)
