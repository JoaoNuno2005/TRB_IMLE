import json
from pathlib import Path

OUTPUT_PATH = Path("data/evaluation_rag.json")

CORPUS_DIRS = [
    Path("data/inspections"),
    Path("data/evaluation_strategy_outputs")
]

queries = [
    {
        "query": "Que inspeções tiveram problemas de prateleira vazia?",
        "expected_terms": ["empty_shelf", "vazia", "stock", "reabastecimento"],
        "target_issue_type": "empty_shelf",
        "target_fill_below": None
    },
    {
        "query": "Que inspeções tiveram fill rate inferior a 80%?",
        "expected_terms": ["fill rate", "80", "inferior", "baixo"],
        "target_issue_type": None,
        "target_fill_below": 0.80
    },
    {
        "query": "Que inspeções tiveram produtos desalinhados ou planograma incorreto?",
        "expected_terms": ["misaligned", "wrong_product", "desalinh", "planograma"],
        "target_issue_type": None,
        "target_fill_below": None
    }
]

def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def collect_records():
    records = []
    seen = set()

    for root in CORPUS_DIRS:
        if not root.exists():
            continue

        for path in root.rglob("*.json"):
            data = load_json(path)
            if not isinstance(data, dict):
                continue

            if "inspection_id" not in data:
                continue

            key = (data.get("inspection_id"), data.get("image_path"))
            if key in seen:
                continue
            seen.add(key)

            text_parts = [
                str(data.get("inspection_id", "")),
                str(data.get("image_path", "")),
                str(data.get("zone_id", "")),
                str(data.get("overall_status", "")),
                str(data.get("summary", "")),
                str(data.get("model_reasoning", "")),
                " ".join(str(p) for p in data.get("products_detected", []) or [])
            ]

            for issue in data.get("issues", []) or []:
                text_parts.extend([
                    str(issue.get("type", "")),
                    str(issue.get("severity", "")),
                    str(issue.get("location", "")),
                    str(issue.get("description", ""))
                ])

            data["_search_text"] = " ".join(text_parts).lower()
            records.append(data)

    return records

def score_record(record, query):
    text = record["_search_text"]
    score = 0

    for term in query["expected_terms"]:
        if term.lower() in text:
            score += 2

    target_issue = query.get("target_issue_type")
    if target_issue:
        for issue in record.get("issues", []) or []:
            if issue.get("type") == target_issue:
                score += 5

    target_fill = query.get("target_fill_below")
    if target_fill is not None:
        try:
            if float(record.get("shelf_fill_rate", 1.0)) <= target_fill:
                score += 5
        except Exception:
            pass

    return score

def relevant(record, query):
    target_issue = query.get("target_issue_type")
    if target_issue:
        return any(issue.get("type") == target_issue for issue in record.get("issues", []) or [])

    target_fill = query.get("target_fill_below")
    if target_fill is not None:
        try:
            return float(record.get("shelf_fill_rate", 1.0)) <= target_fill
        except Exception:
            return False

    terms = query["expected_terms"]
    text = record["_search_text"]
    return any(term.lower() in text for term in terms)

records = collect_records()

details = []
recall_hits = 0
faithfulness_hits = 0
relevance_hits = 0

for query in queries:
    ranked = sorted(
        records,
        key=lambda r: score_record(r, query),
        reverse=True
    )

    top3 = [r for r in ranked[:3] if score_record(r, query) > 0]

    recall_ok = any(relevant(r, query) for r in top3)
    relevance_ok = len(top3) > 0
    faithfulness_ok = all(r.get("inspection_id") and r.get("image_path") for r in top3)

    if recall_ok:
        recall_hits += 1
    if relevance_ok:
        relevance_hits += 1
    if faithfulness_ok:
        faithfulness_hits += 1

    details.append({
        "query": query["query"],
        "top3": [
            {
                "inspection_id": r.get("inspection_id"),
                "image_path": r.get("image_path"),
                "zone_id": r.get("zone_id"),
                "overall_status": r.get("overall_status"),
                "shelf_fill_rate": r.get("shelf_fill_rate"),
                "issue_types": [i.get("type") for i in r.get("issues", []) or []],
                "score": score_record(r, query)
            }
            for r in top3
        ],
        "recall_at_3_ok": recall_ok,
        "faithfulness_ok": faithfulness_ok,
        "answer_relevance_ok": relevance_ok
    })

total = len(queries)

report = {
    "num_records_indexed": len(records),
    "num_queries": total,
    "metrics": {
        "recall_at_3": round((recall_hits / total) * 100, 2),
        "faithfulness": round((faithfulness_hits / total) * 100, 2),
        "answer_relevance": round((relevance_hits / total) * 100, 2)
    },
    "details": details,
    "notes": [
        "Avaliação local rápida da memória histórica com base nos JSON de inspeções guardados.",
        "A métrica Recall@3 verifica se pelo menos um dos três registos mais relevantes contém o padrão esperado.",
        "Faithfulness verifica se as respostas recuperadas têm referência explícita a inspection_id e image_path.",
        "Esta avaliação não depende da API Gemini."
    ]
}

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
print("Registos indexados:", len(records))
print("Guardado em:", OUTPUT_PATH)
