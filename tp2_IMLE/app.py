from __future__ import annotations

from pathlib import Path
import json
import os
import sys
import time

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
if (PROJECT_ROOT / "src").exists():
    ROOT = PROJECT_ROOT
else:
    ROOT = Path.cwd()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config
from src.rag_memory import RAGMemory
from src.report_generator import ReportGenerator
from src.rule_engine import RuleEngine
from src.shelf_inspector import ShelfInspector, STRATEGY_PROMPTS
from src.utils import list_image_files, read_json, zone_from_filename
from evaluate import Evaluator

APP_TITLE = "Retail Vision Intelligence System"
UPLOAD_DIR = config.IMAGES_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

STATUS_LABELS = {
    "ok": "Operação normal",
    "warning": "Atenção necessária",
    "critical": "Intervenção urgente",
}

STATUS_EMOJI = {
    "ok": "🟢",
    "warning": "🟠",
    "critical": "🔴",
}

STRATEGY_LABELS = {
    "zero_shot": "Zero-shot direto",
    "cot_visual": "Chain-of-thought visual",
    "few_shot": "Few-shot textual",
}


def configure_page() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="🛒", layout="wide", initial_sidebar_state="expanded")
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.4rem; padding-bottom: 2rem;}
        .main-hero {
            padding: 1.25rem 1.45rem;
            border-radius: 1.25rem;
            background: linear-gradient(135deg, #111827 0%, #1f2937 48%, #0f766e 100%);
            color: white;
            margin-bottom: 1.2rem;
            box-shadow: 0 14px 35px rgba(15, 23, 42, 0.18);
        }
        .main-hero h1 {font-size: 2.1rem; margin: 0 0 0.2rem 0;}
        .main-hero p {margin: 0; opacity: 0.9; font-size: 1rem;}
        .metric-card {
            padding: 1rem;
            border-radius: 1rem;
            background: #ffffff;
            border: 1px solid #e5e7eb;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
        }
        .issue-card {
            padding: 0.85rem 1rem;
            border-radius: 0.9rem;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            margin-bottom: 0.55rem;
        }
        .trigger-card {
            padding: 0.85rem 1rem;
            border-radius: 0.9rem;
            background: #fff7ed;
            border: 1px solid #fed7aa;
            margin-bottom: 0.55rem;
        }
        .ok-card {
            padding: 0.85rem 1rem;
            border-radius: 0.9rem;
            background: #ecfdf5;
            border: 1px solid #bbf7d0;
            margin-bottom: 0.55rem;
        }
        .small-muted {color: #64748b; font-size: 0.85rem;}
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 1rem;
            padding: 0.8rem 1rem;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.05);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource(show_spinner=False)
def get_services(mock_mode: bool, model_name: str, temperature: float):
    config.TP2_MOCK_LLM = mock_mode
    config.GEMINI_MODEL = model_name
    config.GEMINI_TEMPERATURE = temperature
    inspector = ShelfInspector()
    rules = RuleEngine(llm=inspector.llm)
    memory = RAGMemory(llm=inspector.llm)
    reporter = ReportGenerator(memory=memory)
    return inspector, rules, memory, reporter


def safe_rerun() -> None:
    try:
        st.rerun()
    except Exception:
        st.experimental_rerun()


def save_uploaded_image(uploaded_file) -> Path:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    safe_name = Path(uploaded_file.name).name.replace(" ", "_")
    path = UPLOAD_DIR / f"{timestamp}_{safe_name}"
    path.write_bytes(uploaded_file.getbuffer())
    return path


def load_all_inspections() -> list[dict]:
    inspections = []
    for path in sorted(config.INSPECTIONS_DIR.glob("INS_*.json"), reverse=True):
        data = read_json(path)
        if isinstance(data, dict):
            inspections.append(data)
    return inspections


def issue_count(inspections: list[dict]) -> int:
    return sum(len(item.get("issues", []) or []) for item in inspections)


def render_hero() -> None:
    st.markdown(
        """
        <div class="main-hero">
            <h1>🛒 Retail Vision Intelligence System</h1>
            <p>Painel do gestor de loja para inspeção visual de prateleiras, regras operacionais, memória histórica e relatórios.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> tuple[ShelfInspector, RuleEngine, RAGMemory, ReportGenerator]:
    with st.sidebar:
        st.markdown("### ⚙️ Configuração")
        default_mock = os.getenv("TP2_MOCK_LLM", "0").strip().lower() in {"1", "true", "yes", "sim"} or config.TP2_MOCK_LLM
        mock_mode = st.toggle("Modo mock sem gastar API", value=default_mock)
        model_name = st.text_input("Modelo Gemini", value=config.GEMINI_MODEL or "gemini-1.5-flash")
        temperature = st.slider("Temperatura", min_value=0.0, max_value=1.0, value=float(config.GEMINI_TEMPERATURE), step=0.05)
        st.markdown("---")
        api_ready = bool(config.GEMINI_API_KEY)
        if mock_mode:
            st.success("Mock ativo")
        elif api_ready:
            st.success("API Gemini configurada")
        else:
            st.warning("Sem GEMINI_API_KEY. Usa mock ou configura o .env.")
        st.caption(f"Imagens: `{config.IMAGES_DIR}`")
        st.caption(f"Inspeções: `{config.INSPECTIONS_DIR}`")
        st.caption(f"Regras: `{config.RULES_DIR}`")
        st.caption(f"Vectorstore: `{config.VECTORSTORE_DIR}`")
        if st.button("Recarregar serviços"):
            get_services.clear()
            safe_rerun()
    return get_services(mock_mode, model_name, temperature)


def render_dashboard(rules: RuleEngine) -> None:
    inspections = load_all_inspections()
    total = len(inspections)
    warnings = sum(1 for item in inspections if item.get("overall_status") == "warning")
    critical = sum(1 for item in inspections if item.get("overall_status") == "critical")
    issues = issue_count(inspections)
    total_rules = len(rules.list_rules())
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Inspeções", total)
    c2.metric("Issues", issues)
    c3.metric("Warnings", warnings)
    c4.metric("Críticas", critical)
    c5.metric("Regras", total_rules)
    if inspections:
        latest = inspections[0]
        st.markdown("### Última inspeção")
        render_inspection_summary(latest)
    else:
        st.info("Ainda não existem inspeções guardadas. Vai ao separador Inspeção e analisa uma imagem.")


def render_inspection_summary(inspection: dict) -> None:
    status = inspection.get("overall_status", "ok")
    fill_rate = float(inspection.get("shelf_fill_rate") or 0)
    products = inspection.get("products_detected", []) or []
    issues = inspection.get("issues", []) or []
    left, right = st.columns([1, 2])
    with left:
        st.metric("Estado", f"{STATUS_EMOJI.get(status, '⚪')} {STATUS_LABELS.get(status, status)}")
        st.metric("Fill rate", f"{fill_rate * 100:.1f}%")
        st.metric("Issues", len(issues))
    with right:
        st.markdown(f"**Inspection ID:** `{inspection.get('inspection_id')}`")
        st.markdown(f"**Zona:** `{inspection.get('zone_id')}`")
        st.markdown(f"**Data:** `{inspection.get('timestamp')}`")
        if products:
            st.markdown("**Produtos visíveis:** " + ", ".join(str(x) for x in products))
        reasoning = inspection.get("model_reasoning")
        if reasoning:
            with st.expander("Raciocínio do modelo"):
                st.write(reasoning)
    if issues:
        st.markdown("#### Problemas detetados")
        for issue in issues:
            severity = issue.get("severity", "unknown")
            st.markdown(
                f"""
                <div class="issue-card">
                    <b>{issue.get('type', 'issue')}</b> · severidade <b>{severity}</b> · confiança <b>{float(issue.get('confidence') or 0):.2f}</b><br>
                    <span class="small-muted">{issue.get('location', 'localização não especificada')}</span><br>
                    {issue.get('description', '')}
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.markdown("<div class='ok-card'>Sem problemas detetados nesta inspeção.</div>", unsafe_allow_html=True)


def render_rule_results(rule_result: dict) -> None:
    checked = rule_result.get("checked", []) or []
    triggered = rule_result.get("triggered", []) or []
    st.markdown(f"#### Regras verificadas: {len(checked)} · Regras disparadas: {len(triggered)}")
    if triggered:
        for item in triggered:
            st.markdown(
                f"""
                <div class="trigger-card">
                    <b>{item.get('rule_id')}</b> disparou em <b>{item.get('zone_id')}</b><br>
                    <span class="small-muted">{item.get('reason')}</span><br>
                    {item.get('notification') or ''}
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("Nenhuma regra foi disparada.")
    with st.expander("Ver log completo da execução das regras"):
        st.json(rule_result)


def inspection_page(inspector: ShelfInspector, rules: RuleEngine, memory: RAGMemory) -> None:
    st.markdown("## 📷 Inspecionar prateleira")
    tab_single, tab_batch = st.tabs(["Uma imagem", "Pasta de imagens"])
    with tab_single:
        c1, c2 = st.columns([1, 1])
        with c1:
            zone_id = st.text_input("Zona", value="Z_S1", key="single_zone")
            strategy = st.selectbox("Estratégia de prompting", options=list(STRATEGY_PROMPTS.keys()), format_func=lambda x: STRATEGY_LABELS.get(x, x), index=list(STRATEGY_PROMPTS.keys()).index("cot_visual"))
            chunk_mode = st.selectbox("Chunking RAG", options=["hybrid", "record", "issue"], index=0)
            force = st.checkbox("Forçar nova chamada, ignorando cache", value=False)
            uploaded = st.file_uploader("Carregar fotografia da prateleira", type=["jpg", "jpeg", "png", "webp", "bmp"])
        with c2:
            if uploaded is not None:
                st.image(uploaded, caption=uploaded.name, use_container_width=True)
            else:
                st.info("Carrega uma imagem para simular a operação do gestor de loja.")
        if st.button("Executar inspeção", type="primary", disabled=uploaded is None):
            try:
                image_path = save_uploaded_image(uploaded)
                with st.spinner("A analisar imagem, aplicar regras e indexar memória histórica..."):
                    inspection = inspector.inspect_image(image_path, zone_id=zone_id.strip() or "Z_UNKNOWN", strategy=strategy, force=force, persist=True)
                    memory.index_inspection(inspection, chunk_mode=chunk_mode)
                    rule_result = rules.execute_rules(inspection)
                st.success("Inspeção concluída.")
                render_inspection_summary(inspection)
                render_rule_results(rule_result)
                with st.expander("JSON da inspeção"):
                    st.json(inspection)
            except Exception as exc:
                st.error(f"Não foi possível executar a inspeção: {exc}")
    with tab_batch:
        images_dir = st.text_input("Pasta de imagens", value=str(config.IMAGES_DIR))
        zone_mode = st.selectbox("Zona", options=["all", "Z_S1", "Z_S2", "Z_S3", "Z_S4", "Z_UNKNOWN"], index=0, help="Usa all para tentar inferir a zona pelo nome do ficheiro.")
        strategy_batch = st.selectbox("Estratégia", options=list(STRATEGY_PROMPTS.keys()), format_func=lambda x: STRATEGY_LABELS.get(x, x), index=list(STRATEGY_PROMPTS.keys()).index("cot_visual"), key="batch_strategy")
        chunk_batch = st.selectbox("Chunking", options=["hybrid", "record", "issue"], index=0, key="batch_chunk")
        files = []
        try:
            files = list_image_files(images_dir)
        except Exception:
            files = []
        st.caption(f"Imagens encontradas: {len(files)}")
        limit = st.number_input("Limite de imagens nesta execução", min_value=1, max_value=max(1, len(files) or 1), value=min(10, max(1, len(files) or 1)), step=1)
        if st.button("Inspecionar pasta", type="primary", disabled=not files):
            results = []
            rule_results = []
            progress = st.progress(0)
            try:
                selected_files = files[: int(limit)]
                for idx, image in enumerate(selected_files):
                    zone = zone_mode
                    if zone_mode == "all":
                        zone = zone_from_filename(image, default="Z_UNKNOWN")
                    inspection = inspector.inspect_image(image, zone_id=zone, strategy=strategy_batch, force=False, persist=True)
                    memory.index_inspection(inspection, chunk_mode=chunk_batch)
                    rule_result = rules.execute_rules(inspection)
                    results.append(inspection)
                    rule_results.append(rule_result)
                    progress.progress((idx + 1) / len(selected_files))
                st.success(f"Foram analisadas {len(results)} imagens.")
                st.dataframe(
                    [
                        {
                            "inspection_id": r.get("inspection_id"),
                            "zona": r.get("zone_id"),
                            "estado": r.get("overall_status"),
                            "fill_rate": r.get("shelf_fill_rate"),
                            "issues": len(r.get("issues", []) or []),
                        }
                        for r in results
                    ],
                    use_container_width=True,
                )
                with st.expander("JSON da sessão"):
                    st.json({"inspections": results, "rule_results": rule_results})
            except Exception as exc:
                st.error(f"Erro na inspeção em lote: {exc}")


def rules_page(rules: RuleEngine) -> None:
    st.markdown("## 🧠 Regras operacionais")
    tab_add, tab_list, tab_test = st.tabs(["Adicionar regra", "Regras guardadas", "Testar regra"])
    with tab_add:
        text = st.text_area("Escreve a regra em português", value="Avisa-me quando a prateleira inferior estiver mais de 40% vazia", height=120)
        save_invalid = st.checkbox("Guardar mesmo que a regra tenha ambiguidades", value=False)
        if st.button("Converter e guardar regra", type="primary", disabled=not text.strip()):
            try:
                with st.spinner("A converter linguagem natural para JSON executável..."):
                    rule = rules.add_rule(text.strip(), save_invalid=save_invalid)
                is_valid = rule.get("validation", {}).get("is_valid")
                if is_valid or save_invalid:
                    st.success(f"Regra {rule.get('rule_id')} guardada.")
                else:
                    st.warning("A regra é ambígua e não foi guardada.")
                    ambiguities = rule.get("validation", {}).get("ambiguities", []) or []
                    for ambiguity in ambiguities:
                        st.write(f"- {ambiguity}")
                st.json(rule)
            except Exception as exc:
                st.error(f"Não foi possível guardar a regra: {exc}")
    with tab_list:
        saved = rules.list_rules()
        if not saved:
            st.info("Ainda não existem regras guardadas.")
        for rule in saved:
            with st.expander(f"{rule.get('rule_id')} · {rule.get('description')}"):
                st.markdown(f"**Regra original:** {rule.get('natural_language')}")
                action = rule.get("action", {}) or {}
                st.markdown(f"**Alerta:** `{action.get('alert_level')}`")
                st.json(rule)
                if st.button(f"Apagar {rule.get('rule_id')}", key=f"delete_{rule.get('rule_id')}"):
                    rules.delete_rule(rule.get("rule_id"))
                    st.success("Regra apagada.")
                    safe_rerun()



    with tab_test:
        saved = rules.list_rules()
        if not saved:
            st.info("Cria primeiro uma regra para a poderes testar.")
        else:
            rule_options = [rule.get("rule_id") for rule in saved]
            selected_rule = st.selectbox("Regra a testar", options=rule_options)
            c1, c2 = st.columns(2)
            with c1:
                zone_id = st.text_input("Zona da imagem de teste", value="Z_S1", key="test_rule_zone")
                strategy = st.selectbox("Estratégia de análise", options=list(STRATEGY_PROMPTS.keys()), format_func=lambda x: STRATEGY_LABELS.get(x, x), key="test_rule_strategy")
            with c2:
                uploaded = st.file_uploader("Imagem para testar a regra", type=["jpg", "jpeg", "png", "webp", "bmp"], key="test_rule_upload")
                if uploaded is not None:
                    st.image(uploaded, caption=uploaded.name, use_container_width=True)
            if st.button("Testar regra nesta imagem", type="primary", disabled=uploaded is None):
                try:
                    image_path = save_uploaded_image(uploaded)
                    rule = rules.get_rule(selected_rule)
                    with st.spinner("A analisar imagem e testar apenas a regra selecionada..."):
                        inspection = ShelfInspector(llm=rules.llm).inspect_image(image_path, zone_id=zone_id.strip() or "Z_UNKNOWN", strategy=strategy, persist=False)
                        result = rules.execute_rules(inspection, rules=[rule])
                    render_inspection_summary(inspection)
                    render_rule_results(result)
                except Exception as exc:
                    st.error(f"Não foi possível testar a regra: {exc}")


def history_page(memory: RAGMemory) -> None:
    st.markdown("## 🗂️ Histórico e memória RAG")
    tab_query, tab_compare = st.tabs(["Perguntar ao histórico", "Comparar zonas"])
    with tab_query:
        query = st.text_area("Pergunta em linguagem natural", value="Quando foi a última vez que a zona Z_S1 teve problemas de prateleira vazia?", height=100)
        top_k = st.slider("Top-k documentos recuperados", min_value=1, max_value=10, value=3)
        if st.button("Consultar memória", type="primary", disabled=not query.strip()):
            try:
                with st.spinner("A recuperar inspeções relevantes e sintetizar resposta..."):
                    result = memory.answer(query.strip(), top_k=top_k)
                st.markdown("### Resposta")
                st.write(result.get("answer"))
                st.markdown("### Inspeções recuperadas")
                retrieved = result.get("retrieved", []) or []
                if retrieved:
                    for item in retrieved:
                        meta = item.get("metadata", {}) or {}
                        with st.expander(f"{meta.get('inspection_id', item.get('chunk_id'))} · {meta.get('zone_id', '')} · {meta.get('timestamp', '')}"):
                            st.write(item.get("document"))
                            st.json(meta)
                else:
                    st.info("A memória ainda não recuperou documentos. Faz primeiro algumas inspeções.")
            except Exception as exc:
                st.error(f"Erro na consulta histórica: {exc}")
    with tab_compare:
        c1, c2, c3 = st.columns(3)
        zone_a = c1.text_input("Zona A", value="Z_S1")
        zone_b = c2.text_input("Zona B", value="Z_S3")
        period = c3.text_input("Período", value="last 7 days")
        if st.button("Comparar zonas", type="primary"):
            try:
                result = memory.compare_zones(zone_a.strip(), zone_b.strip(), period=period.strip())
                st.json(result)
            except Exception as exc:
                st.error(f"Erro na comparação: {exc}")


def reports_page(reporter: ReportGenerator) -> None:
    st.markdown("## 📄 Relatórios Markdown")
    c1, c2 = st.columns(2)
    zone = c1.text_input("Zona opcional", value="")
    period = c2.text_input("Período", value="today")
    output_name = st.text_input("Nome do ficheiro", value="inspection_report.md")
    if st.button("Gerar relatório", type="primary"):
        try:
            output_path = config.DATA_DIR / "reports" / output_name
            with st.spinner("A gerar relatório com contexto histórico..."):
                markdown = reporter.generate_period_report(zone_id=zone.strip() or None, period=period.strip() or None, output_path=output_path)
            st.success(f"Relatório guardado em {output_path}")
            st.download_button("Descarregar relatório", data=markdown, file_name=output_name, mime="text/markdown")
            st.markdown(markdown)
        except Exception as exc:
            st.error(f"Erro ao gerar relatório: {exc}")



def evaluation_page() -> None:
    st.markdown("## 📊 Avaliação do sistema")
    st.write("Executa o harness de avaliação diretamente a partir da interface, usando o mesmo código de `evaluate.py`.")
    c1, c2 = st.columns(2)
    images_dir = c1.text_input("Pasta de imagens de teste", value="data/images")
    ground_truth = c2.text_input("Ground truth JSON opcional", value="data/images/ground_truth.json")
    c3, c4, c5 = st.columns(3)
    strategy = c3.selectbox("Estratégia principal", options=list(STRATEGY_PROMPTS.keys()), format_func=lambda x: STRATEGY_LABELS.get(x, x), key="eval_strategy")
    compare_prompts = c4.checkbox("Comparar 3 estratégias", value=True)
    force = c5.checkbox("Ignorar cache", value=False, key="eval_force")
    prompt_limit = st.number_input("Limite para comparação de prompts", min_value=1, max_value=100, value=15, step=1)
    output_path = st.text_input("Ficheiro de saída", value="evaluation/evaluation_report.json")
    if st.button("Executar avaliação", type="primary"):
        try:
            gt_path = Path(ground_truth) if ground_truth.strip() else None
            if gt_path is not None and not gt_path.exists():
                gt_path = None
            evaluator = Evaluator(Path(images_dir), Path(output_path), gt_path, strategy, force, compare_prompts, int(prompt_limit))
            with st.spinner("A executar avaliação. Pode demorar se não estiver em modo mock ou se não houver cache..."):
                report = evaluator.run()
            st.success(f"Relatório de avaliação guardado em {output_path}")
            st.download_button("Descarregar JSON de avaliação", data=json.dumps(report, ensure_ascii=False, indent=2), file_name=Path(output_path).name, mime="application/json")
            st.json(report)
        except Exception as exc:
            st.error(f"Erro na avaliação: {exc}")


def records_page() -> None:
    st.markdown("## 📚 Registos técnicos")
    inspections = load_all_inspections()
    if inspections:
        st.dataframe(
            [
                {
                    "inspection_id": i.get("inspection_id"),
                    "timestamp": i.get("timestamp"),
                    "zone_id": i.get("zone_id"),
                    "status": i.get("overall_status"),
                    "fill_rate": i.get("shelf_fill_rate"),
                    "issues": len(i.get("issues", []) or []),
                    "image_path": i.get("image_path"),
                }
                for i in inspections
            ],
            use_container_width=True,
        )
        selected = st.selectbox("Abrir inspeção", options=[i.get("inspection_id") for i in inspections])
        item = next((i for i in inspections if i.get("inspection_id") == selected), None)
        if item:
            st.json(item)
    else:
        st.info("Sem inspection records guardados.")


def main() -> None:
    configure_page()
    render_hero()
    inspector, rules, memory, reporter = render_sidebar()
    page = st.tabs(["Dashboard", "Inspeção", "Regras", "Histórico", "Relatórios", "Avaliação", "Registos"])
    with page[0]:
        render_dashboard(rules)
    with page[1]:
        inspection_page(inspector, rules, memory)
    with page[2]:
        rules_page(rules)
    with page[3]:
        history_page(memory)
    with page[4]:
        reports_page(reporter)
    with page[5]:
        evaluation_page()
    with page[6]:
        records_page()


if __name__ == "__main__":
    main()
