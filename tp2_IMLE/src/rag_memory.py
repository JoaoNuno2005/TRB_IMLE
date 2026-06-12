from __future__ import annotations

from pathlib import Path as _PathForSys
import sys as _SysForPath
_ProjectRootForSys = _PathForSys(__file__).resolve().parents[1]
if str(_ProjectRootForSys) not in _SysForPath.path:
    _SysForPath.path.insert(0, str(_ProjectRootForSys))


from collections import Counter
from pathlib import Path
import hashlib
import json
import re

import numpy as np

from src import config
from src.llm_client import GeminiClient, LLMUnavailableError
from src.utils import period_start, read_json, read_text, write_json, parse_timestamp, now_utc_iso


class HashEmbeddingModel:
    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions

    def encode(self, texts, normalize_embeddings: bool = True):
        if isinstance(texts, str):
            texts = [texts]
        vectors = []
        for text in texts:
            vector = np.zeros(self.dimensions, dtype=float)
            tokens = re.findall(r"[\wáàâãéêíóôõúç]+", (text or "").lower())
            for token in tokens:
                h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
                vector[h % self.dimensions] += 1.0
            norm = np.linalg.norm(vector)
            if normalize_embeddings and norm > 0:
                vector = vector / norm
            vectors.append(vector.tolist())
        return vectors


class ChromaEmbeddingFunction:
    def __init__(self, model):
        self.model = model

    def __call__(self, input):
        return self.model.encode(input, normalize_embeddings=True)


class RAGMemory:
    def __init__(self, persist_dir: Path | None = None, records_path: Path | None = None, llm: GeminiClient | None = None, collection_name: str = "inspection_memory"):
        self.persist_dir = persist_dir or config.VECTORSTORE_DIR
        self.records_path = records_path or config.INSPECTIONS_DIR / "indexed_records.json"
        self.llm = llm or GeminiClient()
        self.collection_name = collection_name
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        if not self.records_path.exists():
            write_json(self.records_path, [])
        self.embedding_model = self._load_embedding_model()
        self.collection = self._load_chroma_collection()

    def _load_embedding_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            return SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        except Exception:
            return HashEmbeddingModel()

    def _load_chroma_collection(self):
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(self.persist_dir))
            return client.get_or_create_collection(name=self.collection_name, embedding_function=ChromaEmbeddingFunction(self.embedding_model))
        except Exception:
            return None

    def index_inspection(self, inspection: dict, chunk_mode: str = "hybrid") -> list[str]:
        chunks = self.build_chunks(inspection, chunk_mode=chunk_mode)
        if not chunks:
            return []
        records = self._load_records()
        existing_ids = {r.get("chunk_id") for r in records}
        fresh_records = [r for r in records if r.get("inspection_id") != inspection.get("inspection_id")]
        ids = []
        for chunk in chunks:
            ids.append(chunk["chunk_id"])
            fresh_records.append(chunk)
        write_json(self.records_path, fresh_records)
        if self.collection is not None:
            documents = [c["document"] for c in chunks]
            metadatas = [self._clean_metadata(c.get("metadata", {})) for c in chunks]
            try:
                self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            except Exception:
                try:
                    self.collection.add(ids=[i for i in ids if i not in existing_ids], documents=documents, metadatas=metadatas)
                except Exception:
                    self.collection = None
        return ids

    def build_chunks(self, inspection: dict, chunk_mode: str = "hybrid") -> list[dict]:
        mode = chunk_mode.lower().strip()
        if mode not in {"record", "issue", "hybrid"}:
            mode = "hybrid"
        base_meta = self._metadata_from_inspection(inspection)
        chunks = []
        if mode in {"record", "hybrid"}:
            document = self._record_document(inspection)
            chunks.append({
                "chunk_id": f"{inspection.get('inspection_id')}_record",
                "inspection_id": inspection.get("inspection_id"),
                "timestamp": inspection.get("timestamp"),
                "zone_id": inspection.get("zone_id"),
                "chunk_type": "record",
                "document": document,
                "metadata": {**base_meta, "chunk_type": "record", "issue_type": "", "severity": ""},
            })
        if mode in {"issue", "hybrid"}:
            for issue in inspection.get("issues", []) or []:
                document = self._issue_document(inspection, issue)
                chunks.append({
                    "chunk_id": f"{inspection.get('inspection_id')}_{issue.get('issue_id')}",
                    "inspection_id": inspection.get("inspection_id"),
                    "timestamp": inspection.get("timestamp"),
                    "zone_id": inspection.get("zone_id"),
                    "chunk_type": "issue",
                    "document": document,
                    "metadata": {**base_meta, "chunk_type": "issue", "issue_type": issue.get("type", ""), "severity": issue.get("severity", "")},
                })
        return chunks

    def query(self, query: str, top_k: int | None = None, where: dict | None = None) -> list[dict]:
        k = top_k or config.DEFAULT_TOP_K
        if self.collection is not None:
            try:
                kwargs = {"query_texts": [query], "n_results": k}
                if where:
                    kwargs["where"] = where
                result = self.collection.query(**kwargs)
                ids = result.get("ids", [[]])[0]
                docs = result.get("documents", [[]])[0]
                metas = result.get("metadatas", [[]])[0]
                distances = result.get("distances", [[]])[0] if result.get("distances") else [None] * len(ids)
                return [{"chunk_id": ids[i], "document": docs[i], "metadata": metas[i] or {}, "distance": distances[i]} for i in range(len(ids))]
            except Exception:
                self.collection = None
        return self._fallback_query(query, k, where)

    def answer(self, query: str, top_k: int | None = None) -> dict:
        retrieved = self.query(query, top_k=top_k or config.DEFAULT_TOP_K)
        context = self._format_context(retrieved)
        template = read_text(config.PROMPTS_DIR / "rag_answer.txt")
        prompt = template.replace("{query}", query).replace("{context}", context)
        try:
            answer = self.llm.generate_text(prompt, expect_json=False)
        except LLMUnavailableError:
            answer = self._local_answer(query, retrieved)
        return {"query": query, "answer": answer, "retrieved": retrieved}

    def compare_zones(self, zone_a: str, zone_b: str, period: str | None = None) -> dict:
        start = period_start(period)
        records = self._inspection_level_records()
        filtered = []
        for record in records:
            if record.get("zone_id") not in {zone_a, zone_b}:
                continue
            if start and parse_timestamp(record.get("timestamp")) < start:
                continue
            filtered.append(record)
        summary = {}
        for zone in [zone_a, zone_b]:
            zone_records = [r for r in filtered if r.get("zone_id") == zone]
            issue_counter = Counter()
            severities = Counter()
            fill_rates = []
            for record in zone_records:
                metadata = record.get("metadata", {}) or {}
                if record.get("chunk_type") == "issue" and metadata.get("issue_type"):
                    issue_counter[metadata.get("issue_type")] += 1
                    severities[metadata.get("severity")] += 1
                fill = metadata.get("shelf_fill_rate")
                if isinstance(fill, (int, float)):
                    fill_rates.append(float(fill))
            summary[zone] = {
                "chunks": len(zone_records),
                "issues_by_type": dict(issue_counter),
                "severities": dict(severities),
                "avg_fill_rate": round(sum(fill_rates) / len(fill_rates), 4) if fill_rates else None,
            }
        return {"period": period, "zone_a": zone_a, "zone_b": zone_b, "summary": summary}

    def recall_at_k(self, queries: list[dict], k: int = 3) -> dict:
        if not queries:
            return {"recall_at_k": None, "k": k, "details": []}
        hits = 0
        details = []
        for item in queries:
            q = item.get("query", "")
            expected = set(item.get("relevant_inspection_ids", []) or item.get("relevant_chunk_ids", []) or [])
            retrieved = self.query(q, top_k=k)
            retrieved_ids = {r.get("metadata", {}).get("inspection_id") or r.get("chunk_id") for r in retrieved}
            retrieved_chunk_ids = {r.get("chunk_id") for r in retrieved}
            hit = bool(expected & retrieved_ids) or bool(expected & retrieved_chunk_ids)
            hits += 1 if hit else 0
            details.append({"query": q, "expected": sorted(expected), "retrieved": sorted([x for x in retrieved_ids if x]), "hit": hit})
        return {"recall_at_k": hits / len(queries), "k": k, "details": details}


    def compare_chunking_strategies(self, queries: list[dict], inspections: list[dict], k: int = 3) -> dict:
        if not queries:
            return {}
        results = {}
        for mode in ["record", "issue", "hybrid"]:
            chunks = []
            for inspection in inspections:
                chunks.extend(self.build_chunks(inspection, chunk_mode=mode))
            results[mode] = self._recall_on_chunks(queries, chunks, k)
        return results

    def _recall_on_chunks(self, queries: list[dict], chunks: list[dict], k: int) -> dict:
        if not chunks:
            return {"recall_at_k": 0.0, "k": k, "details": []}
        texts = [c.get("document", "") for c in chunks]
        embeddings = np.array(self.embedding_model.encode(texts, normalize_embeddings=True), dtype=float)
        hits = 0
        details = []
        for item in queries:
            query = item.get("query", "")
            expected = set(item.get("relevant_inspection_ids", []) or item.get("relevant_chunk_ids", []) or [])
            q = np.array(self.embedding_model.encode([query], normalize_embeddings=True)[0], dtype=float)
            scores = embeddings @ q
            order = np.argsort(-scores)[:k]
            retrieved = [chunks[int(idx)] for idx in order]
            retrieved_inspections = {r.get("inspection_id") for r in retrieved}
            retrieved_chunks = {r.get("chunk_id") for r in retrieved}
            hit = bool(expected & retrieved_inspections) or bool(expected & retrieved_chunks)
            hits += 1 if hit else 0
            details.append({"query": query, "expected": sorted(expected), "retrieved_inspection_ids": sorted([x for x in retrieved_inspections if x]), "retrieved_chunk_ids": sorted([x for x in retrieved_chunks if x]), "hit": hit})
        return {"recall_at_k": hits / len(queries), "k": k, "details": details}

    def _fallback_query(self, query: str, k: int, where: dict | None = None) -> list[dict]:
        records = self._load_records()
        if where:
            records = [r for r in records if self._where_matches(r.get("metadata", {}), where)]
        if not records:
            return []
        texts = [r.get("document", "") for r in records]
        embeddings = np.array(self.embedding_model.encode(texts, normalize_embeddings=True), dtype=float)
        q = np.array(self.embedding_model.encode([query], normalize_embeddings=True)[0], dtype=float)
        scores = embeddings @ q
        order = np.argsort(-scores)[:k]
        output = []
        for idx in order:
            record = records[int(idx)]
            output.append({"chunk_id": record.get("chunk_id"), "document": record.get("document"), "metadata": record.get("metadata", {}), "distance": float(1 - scores[int(idx)])})
        return output

    def _where_matches(self, metadata: dict, where: dict) -> bool:
        for key, value in where.items():
            if metadata.get(key) != value:
                return False
        return True

    def _load_records(self) -> list[dict]:
        records = read_json(self.records_path, [])
        return records if isinstance(records, list) else []

    def _inspection_level_records(self) -> list[dict]:
        return self._load_records()

    def _metadata_from_inspection(self, inspection: dict) -> dict:
        ts = parse_timestamp(inspection.get("timestamp"))
        return {
            "inspection_id": str(inspection.get("inspection_id", "")),
            "timestamp": str(inspection.get("timestamp", "")),
            "date": ts.date().isoformat(),
            "weekday": ts.strftime("%A"),
            "hour": int(ts.hour),
            "zone_id": str(inspection.get("zone_id", "")),
            "overall_status": str(inspection.get("overall_status", "")),
            "shelf_fill_rate": float(inspection.get("shelf_fill_rate", 0.0)),
            "issue_count": int(len(inspection.get("issues", []) or [])),
            "image_path": str(inspection.get("image_path", "")),
        }

    def _record_document(self, inspection: dict) -> str:
        products = ", ".join(inspection.get("products_detected", []) or [])
        issues = inspection.get("issues", []) or []
        issue_text = "; ".join([f"{i.get('type')} severidade {i.get('severity')} em {i.get('location')}: {i.get('description')}" for i in issues]) or "sem issues"
        summary = inspection.get("summary", "")
        return f"{summary} Zona {inspection.get('zone_id')}. Data {inspection.get('timestamp')}. Estado {inspection.get('overall_status')}. Fill rate {inspection.get('shelf_fill_rate')}. Produtos visíveis: {products}. Issues: {issue_text}."

    def _issue_document(self, inspection: dict, issue: dict) -> str:
        return f"Inspeção {inspection.get('inspection_id')} em {inspection.get('timestamp')} na zona {inspection.get('zone_id')}: issue {issue.get('type')} com severidade {issue.get('severity')} em {issue.get('location')}. Descrição: {issue.get('description')}. Fill rate da prateleira {inspection.get('shelf_fill_rate')}. Estado geral {inspection.get('overall_status')}."

    def _clean_metadata(self, metadata: dict) -> dict:
        clean = {}
        for key, value in metadata.items():
            if value is None:
                clean[key] = ""
            elif isinstance(value, (str, int, float, bool)):
                clean[key] = value
            else:
                clean[key] = json.dumps(value, ensure_ascii=False)
        return clean

    def _format_context(self, retrieved: list[dict]) -> str:
        if not retrieved:
            return "Sem registos recuperados."
        lines = []
        for item in retrieved:
            meta = item.get("metadata", {}) or {}
            lines.append(f"inspection_id={meta.get('inspection_id')} data={meta.get('timestamp')} zona={meta.get('zone_id')} chunk={item.get('chunk_id')} texto={item.get('document')}")
        return "\n".join(lines)

    def _local_answer(self, query: str, retrieved: list[dict]) -> str:
        if not retrieved:
            return "Não há registos históricos suficientes para responder à consulta."
        refs = []
        for item in retrieved:
            meta = item.get("metadata", {}) or {}
            refs.append(f"{meta.get('inspection_id')} em {meta.get('timestamp')} na zona {meta.get('zone_id')}")
        return "Foram recuperados registos relevantes: " + "; ".join(refs) + ". A resposta é baseada apenas nesses registos, sem síntese LLM externa."


def main():
    import argparse
    parser = argparse.ArgumentParser(prog="rag_memory.py")
    sub = parser.add_subparsers(dest="command", required=True)
    index = sub.add_parser("index")
    index.add_argument("inspection_json")
    index.add_argument("--chunk-mode", default="hybrid", choices=["record", "issue", "hybrid"])
    query_cmd = sub.add_parser("query")
    query_cmd.add_argument("text")
    query_cmd.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    memory = RAGMemory()
    if args.command == "index":
        inspection = read_json(args.inspection_json)
        print(json.dumps({"indexed": memory.index_inspection(inspection, args.chunk_mode)}, ensure_ascii=False, indent=2))
    elif args.command == "query":
        print(json.dumps(memory.answer(args.text, args.top_k), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
