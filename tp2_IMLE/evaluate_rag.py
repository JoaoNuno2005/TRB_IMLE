import json
import subprocess
from pathlib import Path

OUTPUT_PATH = Path("data/evaluation_rag.json")

queries = [
    {
        "query": "Que inspeções tiveram problemas de prateleira vazia?",
        "expected_keywords": ["empty_shelf", "vazia", "stock", "reabastecimento"],
        "expected_issue_type": "empty_shelf"
    },
    {
        "query": "Que inspeções tiveram fill rate inferior a 80%?",
        "expected_keywords": ["fill rate", "80", "inferior", "baixo"],
        "expected_issue_type": None
    },
    {
        "query": "Que inspeções tiveram produtos desalinhados ou planograma incorreto?",
        "expected_keywords": ["misaligned", "wrong_product", "desalinh", "planograma"],
        "expected_issue_type": None
    }
]

def run_history(query):
    try:
        result = subprocess.run(
            ["python", "src/interface.py", "history", query],
            capture_output=True,
            text=True,
            timeout=90
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()
        }
    except Exception as e:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(e)
        }

def keyword_score(text, keywords):
    lower = text.lower()
    hits = [k for k in keywords if k.lower() in lower]
    return hits

def faithfulness_score(text):
    lower = text.lower()
    bad_signals = [
        "não tenho acesso",
        "não consigo",
        "invent",
        "sem base",
        "não foi possível"
    ]
    if not text.strip():
        return 0
    if any(signal in lower for signal in bad_signals):
        return 0
    return 1

def answer_relevance_score(text, keywords):
    if not text.strip():
        return 0
    hits = keyword_score(text, keywords)
    return 1 if hits else 0

details = []
recall_hits = 0
faithfulness_hits = 0
relevance_hits = 0

for item in queries:
    response = run_history(item["query"])
    text = response["stdout"]

    hits = keyword_score(text, item["expected_keywords"])
    recall_ok = len(hits) > 0
    faith_ok = faithfulness_score(text) == 1
    relevance_ok = answer_relevance_score(text, item["expected_keywords"]) == 1

    if recall_ok:
        recall_hits += 1
    if faith_ok:
        faithfulness_hits += 1
    if relevance_ok:
        relevance_hits += 1

    details.append({
        "query": item["query"],
        "expected_keywords": item["expected_keywords"],
        "keyword_hits": hits,
        "returncode": response["returncode"],
        "stdout_preview": text[:1200],
        "stderr_preview": response["stderr"][:500],
        "recall_at_3_ok": recall_ok,
        "faithfulness_ok": faith_ok,
        "answer_relevance_ok": relevance_ok
    })

total = len(queries)

report = {
    "num_queries": total,
    "metrics": {
        "recall_at_3": round((recall_hits / total) * 100, 2),
        "faithfulness": round((faithfulness_hits / total) * 100, 2),
        "answer_relevance": round((relevance_hits / total) * 100, 2)
    },
    "details": details,
    "notes": [
        "A avaliação executa o comando history da interface e verifica se a resposta recupera contexto semanticamente relevante.",
        "Recall@3 é aproximado por presença de termos esperados nas respostas recuperadas.",
        "Faithfulness penaliza respostas vazias ou respostas que indiquem falta de base factual.",
        "Answer Relevance mede se a resposta contém sinais compatíveis com a pergunta."
    ]
}

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
print("Guardado em:", OUTPUT_PATH)
