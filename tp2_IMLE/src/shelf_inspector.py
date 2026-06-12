from __future__ import annotations

from pathlib import Path as _PathForSys
import sys as _SysForPath
_ProjectRootForSys = _PathForSys(__file__).resolve().parents[1]
if str(_ProjectRootForSys) not in _SysForPath.path:
    _SysForPath.path.insert(0, str(_ProjectRootForSys))


from pathlib import Path
import json

from src import config
from src.llm_client import GeminiClient, LLMUnavailableError
from src.schemas import normalize_inspection
from src.utils import file_md5, list_image_files, now_utc_iso, read_json, read_text, write_json, zone_from_filename


STRATEGY_PROMPTS = {
    "zero_shot": "visual_zero_shot.txt",
    "cot_visual": "visual_cot.txt",
    "few_shot": "visual_few_shot.txt",
}


class ShelfInspector:
    def __init__(self, llm: GeminiClient | None = None, cache_dir: Path | None = None, inspections_dir: Path | None = None):
        self.llm = llm or GeminiClient()
        self.cache_dir = cache_dir or config.CACHE_DIR
        self.inspections_dir = inspections_dir or config.INSPECTIONS_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.inspections_dir.mkdir(parents=True, exist_ok=True)

    def inspect_image(self, image_path: str | Path, zone_id: str = "Z_UNKNOWN", strategy: str = "cot_visual", force: bool = False, persist: bool = True) -> dict:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Imagem não encontrada: {path}")
        if strategy not in STRATEGY_PROMPTS:
            raise ValueError(f"Estratégia inválida. Usa uma destas: {', '.join(STRATEGY_PROMPTS)}")
        image_hash = file_md5(path)
        cache_path = self._cache_path(image_hash, zone_id, strategy)
        if cache_path.exists() and not force:
            cached = read_json(cache_path)
            if isinstance(cached, dict):
                return cached
        prompt = self._build_prompt(path, zone_id, strategy, image_hash)
        try:
            raw = self.llm.generate_with_image(prompt, path, expect_json=True)
        except LLMUnavailableError as exc:
            if cache_path.exists():
                cached = read_json(cache_path)
                if isinstance(cached, dict):
                    return cached
            raise LLMUnavailableError(f"Não foi possível processar imagem nova. Cache inexistente e chamada à API indisponível: {exc}") from exc
        inspection = normalize_inspection(raw, path, zone_id)
        inspection["timestamp"] = inspection.get("timestamp") or now_utc_iso()
        write_json(cache_path, inspection)
        if persist:
            write_json(self.inspections_dir / f"{inspection['inspection_id']}.json", inspection)
        return inspection

    def inspect_directory(self, images_dir: str | Path, zone_id: str = "Z_UNKNOWN", strategy: str = "cot_visual", force: bool = False, persist: bool = True) -> list[dict]:
        files = list_image_files(images_dir)
        if not files:
            raise FileNotFoundError(f"Não foram encontradas imagens em: {images_dir}")
        results = []
        for image in files:
            current_zone = zone_from_filename(image, default=zone_id) if zone_id.lower() == "all" else zone_id
            results.append(self.inspect_image(image, current_zone, strategy=strategy, force=force, persist=persist))
        return results

    def load_inspections(self, zone_id: str | None = None) -> list[dict]:
        records = []
        for path in sorted(self.inspections_dir.glob("*.json")):
            data = read_json(path)
            if isinstance(data, dict) and (zone_id is None or data.get("zone_id") == zone_id):
                records.append(data)
        return records

    def _cache_path(self, image_hash: str, zone_id: str, strategy: str) -> Path:
        safe_zone = zone_id.replace("/", "_").replace(" ", "_")
        return self.cache_dir / f"inspection_{image_hash}_{safe_zone}_{strategy}_{config.GEMINI_MODEL.replace('/', '_')}.json"

    def _build_prompt(self, image_path: Path, zone_id: str, strategy: str, image_hash: str) -> str:
        template_path = config.PROMPTS_DIR / STRATEGY_PROMPTS[strategy]
        template = read_text(template_path)
        context = {
            "timestamp": now_utc_iso(),
            "image_path": str(image_path),
            "zone_id": zone_id,
            "image_md5": image_hash,
            "strategy": strategy,
        }
        return template + "\n\nDADOS_DA_INSPEÇÃO:\n" + json.dumps(context, ensure_ascii=False, indent=2)


def main():
    import argparse
    parser = argparse.ArgumentParser(prog="shelf_inspector.py")
    parser.add_argument("zone_id")
    parser.add_argument("--image")
    parser.add_argument("--images-dir")
    parser.add_argument("--strategy", default="cot_visual", choices=sorted(STRATEGY_PROMPTS))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    inspector = ShelfInspector()
    if args.image:
        print(json.dumps(inspector.inspect_image(args.image, args.zone_id, args.strategy, args.force), ensure_ascii=False, indent=2))
    elif args.images_dir:
        print(json.dumps(inspector.inspect_directory(args.images_dir, args.zone_id, args.strategy, args.force), ensure_ascii=False, indent=2))
    else:
        raise SystemExit("Indica --image ou --images-dir")


if __name__ == "__main__":
    main()
