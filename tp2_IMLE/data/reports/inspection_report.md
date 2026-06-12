# Inspection Report — today
Gerado em: 2026-06-12T19:23:26Z

## 1. Sumário executivo
Foram inspecionadas 3 zonas em 5 imagem(ns). Foram detetados 11 problema(s), dos quais 5 críticos, e 1 zona(s) em warning. Prioridade imediata: rever Z_S2, Z_S3.

## 2. Problemas por zona
### Z_S1
Fill rate médio: 92.5%
- misaligned | severidade low | prateleira intermédia superior, centro-direita | Um saco de café Starbucks está ligeiramente desalinhado e recuado. | histórico: INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z; INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z
- misaligned | severidade low | prateleira intermédia, lado direito | Um saco de café Gevalia está ligeiramente inclinado. | histórico: INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z; INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z
- misaligned | severidade low | prateleira inferior, centro | Algumas garrafas de xarope Torani estão ligeiramente desalinhadas. | histórico: INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z; INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z
- misaligned | severidade low | prateleira inferior, lado direito | Um creme Baileys está ligeiramente inclinado. | histórico: INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z; INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z
- misaligned | severidade low | prateleira inferior, lado direito | Vários cremes de café estão ligeiramente desalinhados. | histórico: INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z; INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z
### Z_S2
Fill rate médio: 75.0%
- empty_shelf | severidade medium | prateleira intermédia 3, lado esquerdo | Área vazia significativa onde deveriam estar produtos Wartner, indicando rutura de stock. | histórico: INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z; INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z
- empty_shelf | severidade high | prateleira inferior, lado esquerdo | Grande área vazia onde deveriam estar sprays ou desodorizantes para os pés, indicando rutura de stock severa. | histórico: INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z; INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z
- empty_shelf | severidade high | prateleira inferior, centro | Grande área vazia no centro da prateleira inferior, onde deveriam estar palmilhas Balea, indicando rutura de stock severa. | histórico: INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z; INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z
- empty_shelf | severidade high | prateleira inferior, secção dos produtos Rockstar, lado direito | Grande espaço vazio na prateleira inferior onde deveriam estar mais produtos Rockstar, indicando rutura de stock para essa secção. | histórico: INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z; INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z
### Z_S3
Fill rate médio: 78.0%
- empty_shelf | severidade high | prateleira intermédia, lado direito | Área vazia significativa onde deveriam estar sabonetes em barra, indicando rutura de stock ou falta de reposição. | histórico: INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z; INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z
- empty_shelf | severidade high | prateleira inferior, lado direito | Área vazia significativa onde deveriam estar sabonetes em barra, indicando rutura de stock ou falta de reposição. | histórico: INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z; INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z

## 3. Regras disparadas
Nenhuma regra foi disparada nesta sessão.

## 4. Contexto histórico relevante
- INS_20260612_191910_Z_S2 | 2026-06-12T19:19:10Z | Z_S2: Inspeção INS_20260612_191910_Z_S2 em 2026-06-12T19:19:10Z na zona Z_S2: issue empty_shelf com severidade high em prateleira inferior, secção dos produtos Rockstar, lado direito. Descrição: Grande espaço vazio na prateleira inferior onde deveriam estar mais produtos Rockstar, indicando rutura de stock para essa secção.. Fill rate da prateleira 0.8. Estado geral critical.
- INS_20260612_191910_Z_S2 | 2026-06-12T19:19:10Z | Z_S2: Inspeção da zona Z_S2 em 2026-06-12T19:19:10Z. A taxa de ocupação da prateleira é de aproximadamente 80%. Foi detetado um problema crítico de rutura de stock (empty_shelf) na prateleira inferior, na secção dos produtos Rockstar, com cerca de 35% da área afetada. Os produtos visíveis incluem bebidas energéticas (Monster, Red Bull, Rockstar) e águas com gás (Clear, La Croix, Propel). Zona Z_S2. Data 2026-06-12T19:19:10Z. Estado critical. Fill rate 0.8. Produtos visíveis: Monster Energy, Red Bull, Rockstar Energy, Clear Sparkling Water, La Croix Sparkling Water, Propel Water. Issues: empty_shelf severidade high em prateleira inferior, secção dos produtos Rockstar, lado direito: Grande espaço vazio na prateleira inferior onde deveriam estar mais produtos Rockstar, indicando rutura de stock para essa secção..

## 5. Recomendações
1. Repor produto na Z_S2 em prateleira inferior, lado esquerdo e validar stock de retaguarda.
2. Repor produto na Z_S2 em prateleira inferior, centro e validar stock de retaguarda.
3. Repor produto na Z_S3 em prateleira intermédia, lado direito e validar stock de retaguarda.
4. Repor produto na Z_S3 em prateleira inferior, lado direito e validar stock de retaguarda.
5. Repor produto na Z_S2 em prateleira inferior, secção dos produtos Rockstar, lado direito e validar stock de retaguarda.

## 6. Integração com trajectória
Integração não ativa: não existe data/trajectory/traffic.csv.
