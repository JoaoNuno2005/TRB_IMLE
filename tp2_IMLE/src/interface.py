from __future__ import annotations

from pathlib import Path as _PathForSys
import sys as _SysForPath
_ProjectRootForSys = _PathForSys(__file__).resolve().parents[1]
if str(_ProjectRootForSys) not in _SysForPath.path:
    _SysForPath.path.insert(0, str(_ProjectRootForSys))


from pathlib import Path
import argparse
import json
import sys

from src.rag_memory import RAGMemory
from src.report_generator import ReportGenerator
from src.rule_engine import RuleEngine
from src.shelf_inspector import ShelfInspector, STRATEGY_PROMPTS


class RetailVisionCLI:
    def __init__(self):
        self.inspector = ShelfInspector()
        self.rules = RuleEngine(llm=self.inspector.llm)
        self.memory = RAGMemory(llm=self.inspector.llm)
        self.reporter = ReportGenerator(memory=self.memory)

    def inspect(self, args) -> None:
        if args.image:
            inspections = [self.inspector.inspect_image(args.image, args.zone, strategy=args.strategy, force=args.force)]
        elif args.images_dir:
            inspections = self.inspector.inspect_directory(args.images_dir, zone_id=args.zone, strategy=args.strategy, force=args.force)
        else:
            raise ValueError("Indica --image ou --images-dir.")
        all_rule_results = []
        for inspection in inspections:
            self.memory.index_inspection(inspection, chunk_mode=args.chunk_mode)
            rule_result = self.rules.execute_rules(inspection)
            all_rule_results.append(rule_result)
        payload = {"inspections": inspections, "rule_results": all_rule_results}
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    def add_rule(self, args) -> None:
        text = " ".join(args.text).strip()
        rule = self.rules.add_rule(text)
        if not rule["validation"]["is_valid"]:
            if sys.stdin.isatty() and not args.no_clarify:
                print("A regra é ambígua e ainda não foi guardada.")
                for ambiguity in rule["validation"]["ambiguities"]:
                    answer = input(f"{ambiguity} ")
                    text += f" Clarificação: {answer}."
                rule = self.rules.add_rule(text)
            else:
                print(json.dumps({"saved": False, "rule": rule, "message": "Regra ambígua. Resolve as ambiguidades antes de guardar."}, ensure_ascii=False, indent=2))
                return
        print(json.dumps({"saved": True, "rule": rule}, ensure_ascii=False, indent=2))

    def list_rules(self, args) -> None:
        print(json.dumps(self.rules.list_rules(), ensure_ascii=False, indent=2))

    def delete_rule(self, args) -> None:
        deleted = self.rules.delete_rule(args.rule_id)
        print(json.dumps({"deleted": deleted, "rule_id": args.rule_id}, ensure_ascii=False, indent=2))

    def test_rule(self, args) -> None:
        rule = self.rules.get_rule(args.rule_id)
        if not rule:
            raise ValueError(f"Regra inexistente: {args.rule_id}")
        inspection = self.inspector.inspect_image(args.image, args.zone, strategy=args.strategy, force=args.force, persist=False)
        result = self.rules.execute_rules(inspection, rules=[rule])
        print(json.dumps({"inspection": inspection, "result": result}, ensure_ascii=False, indent=2))

    def history(self, args) -> None:
        query = " ".join(args.query).strip()
        result = self.memory.answer(query, top_k=args.top_k)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    def compare(self, args) -> None:
        result = self.memory.compare_zones(args.zone_a, args.zone_b, period=args.period)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    def report(self, args) -> None:
        output = args.output
        if not output:
            safe = "report"
            if args.zone:
                safe += f"_{args.zone}"
            safe += ".md"
            output = Path("data") / "reports" / safe
        if args.session == "today":
            period = "today"
        else:
            period = args.period
        report = self.reporter.generate_period_report(zone_id=args.zone, period=period, output_path=output)
        print(report)
        print(json.dumps({"saved_to": str(output)}, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="interface.py")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("zone")
    inspect.add_argument("--image")
    inspect.add_argument("--images-dir")
    inspect.add_argument("--strategy", default="cot_visual", choices=sorted(STRATEGY_PROMPTS))
    inspect.add_argument("--chunk-mode", default="hybrid", choices=["record", "issue", "hybrid"])
    inspect.add_argument("--force", action="store_true")
    inspect.set_defaults(handler="inspect")

    add = sub.add_parser("add")
    add_sub = add.add_subparsers(dest="kind", required=True)
    add_rule = add_sub.add_parser("rule")
    add_rule.add_argument("text", nargs="+")
    add_rule.add_argument("--no-clarify", action="store_true")
    add_rule.set_defaults(handler="add_rule")

    list_cmd = sub.add_parser("list")
    list_sub = list_cmd.add_subparsers(dest="kind", required=True)
    list_rules = list_sub.add_parser("rules")
    list_rules.set_defaults(handler="list_rules")

    delete = sub.add_parser("delete")
    delete_sub = delete.add_subparsers(dest="kind", required=True)
    delete_rule = delete_sub.add_parser("rule")
    delete_rule.add_argument("rule_id")
    delete_rule.set_defaults(handler="delete_rule")

    test = sub.add_parser("test")
    test_sub = test.add_subparsers(dest="kind", required=True)
    test_rule = test_sub.add_parser("rule")
    test_rule.add_argument("rule_id")
    test_rule.add_argument("--image", required=True)
    test_rule.add_argument("--zone", default="Z_UNKNOWN")
    test_rule.add_argument("--strategy", default="cot_visual", choices=sorted(STRATEGY_PROMPTS))
    test_rule.add_argument("--force", action="store_true")
    test_rule.set_defaults(handler="test_rule")

    history = sub.add_parser("history")
    history.add_argument("query", nargs="+")
    history.add_argument("--top-k", type=int, default=3)
    history.set_defaults(handler="history")

    compare = sub.add_parser("compare")
    compare.add_argument("zone_a")
    compare.add_argument("zone_b")
    compare.add_argument("--period", default="last 7 days")
    compare.set_defaults(handler="compare")

    report = sub.add_parser("report")
    report.add_argument("--session")
    report.add_argument("--zone")
    report.add_argument("--period")
    report.add_argument("--output")
    report.set_defaults(handler="report")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    cli = RetailVisionCLI()
    try:
        getattr(cli, args.handler)(args)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
