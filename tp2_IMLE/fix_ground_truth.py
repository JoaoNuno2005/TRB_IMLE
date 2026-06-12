import json
from pathlib import Path

gt_path = Path("data/ground_truth.json")
backup_path = Path("data/ground_truth_backup.json")

with gt_path.open("r", encoding="utf-8") as f:
    data = json.load(f)

backup_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

if isinstance(data, dict):
    items = data.get("images", data)
else:
    items = data

cleaned = []
missing = []

if isinstance(items, list):
    for item in items:
        image_path = item.get("image") or item.get("image_path")
        if image_path and Path(image_path).exists():
            cleaned.append(item)
        else:
            missing.append(image_path)
    output = {"images": cleaned}
elif isinstance(items, dict):
    output_items = {}
    for image_path, value in items.items():
        if Path(image_path).exists():
            output_items[image_path] = value
        else:
            missing.append(image_path)
    output = output_items
else:
    raise ValueError("Formato de ground_truth.json não reconhecido.")

gt_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"Ground truth original guardado em: {backup_path}")
print(f"Entradas válidas mantidas: {len(cleaned) if isinstance(items, list) else len(output)}")
print(f"Entradas removidas por imagem inexistente: {len(missing)}")

if missing:
    print("Primeiras imagens em falta:")
    for p in missing[:20]:
        print("-", p)