import json
from pathlib import Path

OUTPUT_PATH = Path("data/evaluation_llm_judge.json")

REPORTS_DIR = Path("data/reports")
RAG_PATH = Path("data/evaluation_rag.json")
RULE_PATH = Path("data/evaluation_rule_engine.json")
PROMPT_PATH = Path("data/evaluation_prompting_report_common10.json")

def read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""

def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def latest_report():
    if not REPORTS_DIR.exists():
        return None
    files = sorted(REPORTS_DIR.rglob("*.md"))
    return files[-1] if files else None

def score_report(text):
    required_sections = [
        "sumário executivo",
        "problemas por zona",
        "regras disparadas",
        "contexto histórico",
        "recomendações",
        "integração"
    ]

    lower = text.lower()
    present = [s for s in required_sections if s in lower]

    section_score = len(present) / len(required_sections)
    has_recommendations = lower.count("recomend") >= 1
    has_rules = "rule_" in lower or "regra" in lower
    has_history = "histórico" in lower or "contexto" in lower
    has_zones = "zona" in lower or "z_" in lower

    factual_signals = sum([has_recommendations, has_rules, has_history, has_zones]) / 4

    score = round(((section_score * 0.6) + (factual_signals * 0.4)) * 10, 2)

    return {
        "score_0_10": score,
        "sections_found": present,
        "required_sections": required_sections,
        "has_recommendations": has_recommendations,
        "has_rules": has_rules,
        "has_history": has_history,
        "has_zones": has_zones
    }

def score_rag(data):
    metrics = data.get("metrics", {})
    recall = metrics.get("recall_at_3", 0)
    faithfulness = metrics.get("faithfulness", 0)
    relevance = metrics.get("answer_relevance", 0)

    score = round(((recall + faithfulness + relevance) / 300) * 10, 2)

    return {
        "score_0_10": score,
        "recall_at_3": recall,
        "faithfulness": faithfulness,
        "answer_relevance": relevance
    }

def score_rule_engine(data):
    metrics = data.get("metrics", {})
    parse_rate = metrics.get("rule_parse_rate", 0)
    correctness = metrics.get("rule_correctness", 0)
    ambiguity = metrics.get("ambiguity_detection", 0)

    score = round(((parse_rate + correctness + ambiguity) / 300) * 10, 2)

    return {
        "score_0_10": score,
        "rule_parse_rate": parse_rate,
        "rule_correctness": correctness,
        "ambiguity_detection": ambiguity
    }

def score_prompting(data):
    rows = data.get("summary_table", [])
    if not rows:
        return {
            "score_0_10": 0,
            "best_strategy": None,
            "reason": "Sem tabela de avaliação."
        }

    scored = []

    for row in rows:
        issue_detection = row.get("issue_detection_rate", 0)
        severity = row.get("severity_accuracy", 0)
        status = row.get("status_accuracy", 0)
        hallucination = row.get("hallucination_rate", 0)
        false_positive = row.get("false_positive_rate", 0)

        score = (
            issue_detection * 0.35 +
            severity * 0.25 +
            status * 0.15 +
            (100 - hallucination) * 0.15 +
            (100 - false_positive) * 0.10
        )

        scored.append({
            "strategy": row.get("strategy"),
            "score_0_10": round(score / 10, 2),
            "raw": row
        })

    best = sorted(scored, key=lambda x: x["score_0_10"], reverse=True)[0]

    return {
        "score_0_10": best["score_0_10"],
        "best_strategy": best["strategy"],
        "all_strategy_scores": scored
    }

report_path = latest_report()
report_text = read_text(report_path) if report_path else ""

rag_data = load_json(RAG_PATH)
rule_data = load_json(RULE_PATH)
prompt_data = load_json(PROMPT_PATH)

report_score = score_report(report_text)
rag_score = score_rag(rag_data)
rule_score = score_rule_engine(rule_data)
prompt_score = score_prompting(prompt_data)

overall = round((
    report_score["score_0_10"] * 0.30 +
    rag_score["score_0_10"] * 0.25 +
    rule_score["score_0_10"] * 0.25 +
    prompt_score["score_0_10"] * 0.20
), 2)

result = {
    "judge_mode": "local_fallback",
    "note": "Avaliação automática local usada como fallback por indisponibilidade da API Gemini. O script mantém a estrutura de LLM-as-Judge para efeitos de validação da pipeline.",
    "latest_report": str(report_path) if report_path else None,
    "scores": {
        "report_quality": report_score,
        "rag_quality": rag_score,
        "rule_engine_quality": rule_score,
        "prompting_quality": prompt_score,
        "overall_score_0_10": overall
    }
}

OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

print(json.dumps(result, ensure_ascii=False, indent=2))
print("Guardado em:", OUTPUT_PATH)
