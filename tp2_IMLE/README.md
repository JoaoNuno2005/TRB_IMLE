# TP2 — Retail Vision Intelligence System

Sistema de inspeção visual de prateleiras com Gemini Flash, regras em linguagem natural, memória RAG, relatórios Markdown e harness de avaliação.

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Preencher `GEMINI_API_KEY` no ficheiro `.env`.

## Estrutura

```text
tp2/
├── README.md
├── requirements.txt
├── .env.example
├── data/
│   ├── images/
│   ├── inspections/
│   ├── rules/
│   └── trajectory/
├── src/
│   ├── shelf_inspector.py
│   ├── rule_engine.py
│   ├── rag_memory.py
│   ├── report_generator.py
│   └── interface.py
├── prompts/
├── vectorstore/
├── cache/
└── evaluate.py
```

## Comandos principais

```bash
python src/interface.py inspect Z_S3 --image data/images/shelf_photo.jpg
python src/interface.py inspect all --images-dir data/images/
python src/interface.py add rule "Avisa-me quando a prateleira inferior estiver mais de 40% vazia"
python src/interface.py list rules
python src/interface.py delete rule RULE_003
python src/interface.py test rule RULE_001 --image data/images/shelf_photo.jpg
python src/interface.py history "quais as zonas com mais problemas esta semana?"
python src/interface.py compare Z_S1 Z_S3 --period "last 7 days"
python src/interface.py report --session today
python src/interface.py report --zone Z_S3 --period "last 14 days"
```

## Avaliação

```bash
python evaluate.py --images-dir test_images/ --output evaluation_report.json
```

Com ground truth próprio:

```bash
python evaluate.py --images-dir test_images/ --ground-truth test_images/ground_truth.json --output evaluation_report.json --compare-prompts
```

Formato recomendado para `ground_truth.json`:

```json
{
  "images": [
    {
      "image_path": "example.jpg",
      "zone_id": "Z_S1",
      "issues": [
        {
          "type": "empty_shelf",
          "severity": "high",
          "location": "prateleira inferior"
        }
      ]
    }
  ],
  "rag_queries": [
    {
      "query": "Quando foi a última vez que a zona Z_S1 teve problemas de prateleira vazia?",
      "relevant_inspection_ids": ["INS_20250317_143022_001"]
    }
  ],
  "rule_tests": [
    {
      "text": "Quero ser alertado quando a prateleira inferior estiver mais de 30% vazia.",
      "synthetic_inspection": {},
      "should_trigger": true,
      "should_be_ambiguous": false
    }
  ]
}
```

## Modo sem API para testes locais

```bash
TP2_MOCK_LLM=1 python src/interface.py inspect Z_S1 --image data/images/example_empty.jpg
```

Este modo serve apenas para testar a execução do pipeline sem consumir quota.


## Interface Streamlit

Depois de instalar as dependências, correr:

```bash
streamlit run app.py
```

A aplicação inclui dashboard, inspeção por upload, inspeção de pasta, gestão de regras, teste de regras, consultas RAG, comparação de zonas, relatórios Markdown e execução do harness de avaliação.

## Organização recomendada das imagens

```text
data/images/
├── normal/
├── empty_shelf/
├── wrong_product/
├── dirty_misaligned/
├── ambiguous/
└── uploads/
```

Preencher `data/images/dataset_manifest_template.csv` com origem, licença e categoria de cada imagem. Copiar `data/images/ground_truth_template.json` para `data/images/ground_truth.json` e ajustar pelo menos 15 imagens para a comparação das três estratégias de prompting.
