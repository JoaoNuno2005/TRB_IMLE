from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

from src import config
from src.rag_memory import RAGMemory
from src.rule_engine import RuleEngine
from src.shelf_inspector import ShelfInspector, STRATEGY_PROMPTS
from src.utils import detect_location_bucket, list_image_files, read_json, read_text, text_similarity, write_json, zone_from_filename


class LLMJudge:
    def __init__(self, llm):
        self.llm = llm

    def evaluate(self, output, criterion: str, context="") -> dict:
        template = read_text(config.PROMPTS_DIR / "judge.txt")
        prompt = template.replace("{criterion}", criterion).replace("{context}", json.dumps(context, ensure_ascii=False)).replace("{output}", json.dumps(output, ensure_ascii=False))
        try:
            result = self.llm.generate_text(prompt, expect_json=True)
            return self._normalize(result)
        except Exception as exc:
            return {"score": None, "justification": f"LLM-as-judge indisponível: {exc}", "supported_claims": [], "unsupported_claims": []}

    def _normalize(self, raw) -> dict:
        data = raw if isinstance(raw, dict) else {}
        score = data.get("score")
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = None
        if score is not None:
            score = max(1, min(5, score))
        return {
            "score": score,
            "justification": str(data.get("justification") or "Sem justificação."),
            "supported_claims": data.get("supported_claims") if isinstance(data.get("supported_claims"), list) else [],
            "unsupported_claims": data.get("unsupported_claims") if isinstance(data.get("unsupported_claims"), list) else [],
        }


class Evaluator:
    def __init__(self, images_dir: Path, output: Path, ground_truth_path: Path | None, strategy: str, force: bool, compare_prompts: bool, prompt_limit: int):
        self.images_dir = images_dir
        self.output = output
        self.ground_truth_path = ground_truth_path
        self.strategy = strategy
        self.force = force
        self.compare_prompts = compare_prompts
        self.prompt_limit = prompt_limit
        self.inspector = ShelfInspector()
        self.rules = RuleEngine(llm=self.inspector.llm)
        self.memory = RAGMemory(llm=self.inspector.llm)
        self.judge = LLMJudge(self.inspector.llm)
        self.ground_truth = self._load_ground_truth()

    def run(self) -> dict:
        images = list_image_files(self.images_dir)
        inspections = []
        errors = []
        for image in images:
            gt = self._gt_for_image(image)
            zone = gt.get("zone_id") or zone_from_filename(image)
            try:
                inspection = self.inspector.inspect_image(image, zone_id=zone, strategy=self.strategy, force=self.force)
                inspections.append({"image": str(image), "inspection": inspection, "ground_truth": gt})
                self.memory.index_inspection(inspection, chunk_mode="hybrid")
            except Exception as exc:
                errors.append({"image": str(image), "error": str(exc)})
        visual = self._visual_metrics(inspections, errors)
        rag = self._rag_metrics([row["inspection"] for row in inspections])
        rules = self._rule_metrics()
        judge = self._judge_metrics(rag)
        prompt_comparison = self._prompt_comparison(images) if self.compare_prompts else None
        report = {
            "images_dir": str(self.images_dir),
            "strategy": self.strategy,
            "total_images": len(images),
            "processed_images": len(inspections),
            "errors": errors,
            "visual_analysis": visual,
            "rag": rag,
            "rule_engine": rules,
            "llm_as_judge": judge,
            "prompt_comparison": prompt_comparison,
        }
        write_json(self.output, report)
        return report

    def _load_ground_truth(self) -> dict:
        path = self.ground_truth_path
        if path and path.exists():
            data = read_json(path, {})
            return data if isinstance(data, dict) else {}
        default = self.images_dir / "ground_truth.json"
        if default.exists():
            data = read_json(default, {})
            return data if isinstance(data, dict) else {}
        return {}

    def _gt_for_image(self, image: Path) -> dict:
        items = self.ground_truth.get("images", []) if isinstance(self.ground_truth.get("images"), list) else []
        for item in items:
            candidate = str(item.get("image_path") or item.get("file") or item.get("filename") or "")
            if candidate == str(image) or Path(candidate).name == image.name:
                return item
        return {"image_path": str(image), "zone_id": zone_from_filename(image), "issues": []}

    def _visual_metrics(self, rows: list[dict], errors: list[dict]) -> dict:
        total_images = len(rows) + len(errors)
        valid_json = len(rows)
        total_gt = 0
        total_pred = 0
        matched = 0
        severity_correct = 0
        false_positives = 0
        details = []
        for row in rows:
            gt_issues = row.get("ground_truth", {}).get("issues", []) or []
            pred_issues = row.get("inspection", {}).get("issues", []) or []
            total_gt += len(gt_issues)
            total_pred += len(pred_issues)
            used = set()
            image_matches = []
            for gt in gt_issues:
                best_idx = None
                best_score = -1
                for idx, pred in enumerate(pred_issues):
                    if idx in used:
                        continue
                    score = self._issue_match_score(gt, pred)
                    if score > best_score:
                        best_score = score
                        best_idx = idx
                if best_idx is not None and best_score >= 0.55:
                    used.add(best_idx)
                    matched += 1
                    pred = pred_issues[best_idx]
                    sev_ok = pred.get("severity") == gt.get("severity") if gt.get("severity") else True
                    severity_correct += 1 if sev_ok else 0
                    image_matches.append({"gt": gt, "pred": pred, "score": best_score, "severity_correct": sev_ok})
            fp = len(pred_issues) - len(used)
            false_positives += max(0, fp)
            details.append({"image": row.get("image"), "matches": image_matches, "false_positives": fp})
        return {
            "issue_detection_rate": matched / total_gt if total_gt else None,
            "false_positive_rate": false_positives / total_pred if total_pred else 0.0,
            "severity_accuracy": severity_correct / matched if matched else None,
            "json_parse_rate": valid_json / total_images if total_images else None,
            "hallucination_rate": false_positives / total_pred if total_pred else 0.0,
            "counts": {"ground_truth_issues": total_gt, "predicted_issues": total_pred, "matched_issues": matched, "false_positives": false_positives},
            "details": details,
        }

    def _issue_match_score(self, gt: dict, pred: dict) -> float:
        type_score = 0.7 if gt.get("type") == pred.get("type") else 0.0
        gt_bucket = detect_location_bucket(gt.get("location"))
        pred_bucket = detect_location_bucket(pred.get("location"))
        bucket_score = 0.2 if gt_bucket == "any" or pred_bucket == "any" or gt_bucket == pred_bucket else 0.0
        text_score = 0.1 * text_similarity(gt.get("location", ""), pred.get("location", ""))
        if not gt.get("location"):
            bucket_score = 0.2
            text_score = 0.1
        return type_score + bucket_score + text_score

    def _rag_metrics(self, inspections: list[dict]) -> dict:
        queries = self.ground_truth.get("rag_queries", []) if isinstance(self.ground_truth.get("rag_queries"), list) else []
        recall = self.memory.recall_at_k(queries, k=3)
        chunking = self.memory.compare_chunking_strategies(queries, inspections, k=3)
        answers = []
        for item in queries:
            result = self.memory.answer(item.get("query", ""), top_k=3)
            answers.append(result)
        return {"recall_at_3": recall, "chunking_comparison": chunking, "answers": answers}

    def _rule_metrics(self) -> dict:
        tests = self.ground_truth.get("rule_tests", []) if isinstance(self.ground_truth.get("rule_tests"), list) else []
        if not tests:
            tests = self._default_rule_tests()
        parsed = 0
        correctness_total = 0
        correctness_ok = 0
        ambiguity_total = 0
        ambiguity_ok = 0
        details = []
        for test in tests:
            try:
                rule = self.rules.parse_rule(test.get("text", ""))
                parsed += 1
                parse_error = None
            except Exception as exc:
                rule = None
                parse_error = str(exc)
            if rule is not None and "should_be_ambiguous" in test:
                ambiguity_total += 1
                detected = not rule.get("validation", {}).get("is_valid", True)
                if detected == bool(test.get("should_be_ambiguous")):
                    ambiguity_ok += 1
            triggered = None
            if rule is not None and test.get("synthetic_inspection") is not None and "should_trigger" in test:
                correctness_total += 1
                if rule.get("validation", {}).get("is_valid", True):
                    result = self.rules.execute_rules(test.get("synthetic_inspection"), rules=[rule])
                    triggered = bool(result.get("triggered"))
                else:
                    triggered = False
                if triggered == bool(test.get("should_trigger")):
                    correctness_ok += 1
            details.append({"text": test.get("text"), "rule": rule, "parse_error": parse_error, "triggered": triggered})
        return {
            "rule_parse_rate": parsed / len(tests) if tests else None,
            "rule_correctness": correctness_ok / correctness_total if correctness_total else None,
            "ambiguity_detection": ambiguity_ok / ambiguity_total if ambiguity_total else None,
            "details": details,
        }

    def _default_rule_tests(self) -> list[dict]:
        inspection_empty = {
            "inspection_id": "INS_SYNTH_001",
            "timestamp": "2025-03-17T11:00:00Z",
            "image_path": "synthetic.jpg",
            "zone_id": "Z_S1",
            "overall_status": "critical",
            "issues": [{"issue_id": "ISS_001", "type": "empty_shelf", "location": "prateleira inferior", "severity": "high", "description": "Prateleira inferior com área vazia relevante.", "confidence": 0.9, "affected_area_pct": 0.45}],
            "shelf_fill_rate": 0.55,
            "products_detected": [],
            "model_reasoning": "sintético",
        }
        return [
            {"text": "Quero ser alertado quando a prateleira inferior de qualquer zona estiver mais de 30% vazia.", "synthetic_inspection": inspection_empty, "should_trigger": True, "should_be_ambiguous": False},
            {"text": "Avisa-me quando a prateleira estiver vazia.", "synthetic_inspection": inspection_empty, "should_trigger": False, "should_be_ambiguous": True},
            {"text": "Se um produto estiver tombado, considera sempre severidade alta.", "synthetic_inspection": inspection_empty, "should_trigger": False, "should_be_ambiguous": False},
        ]

    def _judge_metrics(self, rag: dict) -> dict:
        judged_answers = []
        for answer in rag.get("answers", []):
            context = answer.get("retrieved", [])
            relevance = self.judge.evaluate(answer.get("answer"), "Answer Relevance: a resposta responde diretamente à query do utilizador?", context={"query": answer.get("query"), "retrieved": context})
            faithfulness = self.judge.evaluate(answer.get("answer"), "Faithfulness: todas as afirmações factuais estão suportadas pelos chunks recuperados?", context=context)
            judged_answers.append({"query": answer.get("query"), "answer_relevance": relevance, "faithfulness": faithfulness})
        return {"rag_answer_judgements": judged_answers}

    def _prompt_comparison(self, images: list[Path]) -> dict:
        selected = images[: self.prompt_limit]
        output = {}
        for strategy in STRATEGY_PROMPTS:
            rows = []
            errors = []
            for image in selected:
                gt = self._gt_for_image(image)
                zone = gt.get("zone_id") or zone_from_filename(image)
                try:
                    inspection = self.inspector.inspect_image(image, zone_id=zone, strategy=strategy, force=self.force)
                    rows.append({"image": str(image), "inspection": inspection, "ground_truth": gt})
                except Exception as exc:
                    errors.append({"image": str(image), "error": str(exc)})
            output[strategy] = self._visual_metrics(rows, errors)
        return output


def main():
    parser = argparse.ArgumentParser(prog="evaluate.py")
    parser.add_argument("--images-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ground-truth")
    parser.add_argument("--strategy", default="cot_visual", choices=sorted(STRATEGY_PROMPTS))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--compare-prompts", action="store_true")
    parser.add_argument("--prompt-limit", type=int, default=15)
    args = parser.parse_args()
    evaluator = Evaluator(Path(args.images_dir), Path(args.output), Path(args.ground_truth) if args.ground_truth else None, args.strategy, args.force, args.compare_prompts, args.prompt_limit)
    report = evaluator.run()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
