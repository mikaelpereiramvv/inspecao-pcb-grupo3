# Rastreabilidade: documento integrado → código

Cada requisito do *Projeto Final – Primeira Versão Integrada (Grupo 3)* e onde ele foi implementado.

| Seção do documento | Requisito | Implementação |
|---|---|---|
| 2. Delimitação | Conjunto fechado de defeitos visuais em PCB e registro/retorno à origem | `app/config.py` (`CLASSES`, 6 tipos do HRIPCB); `app/dashboard.py` (alertas) |
| 2. Fora do escopo | Causa raiz, ensaios elétricos, normas e gestão da produção | não implementados de propósito |
| 4. Persona Daniel | Ferramenta rápida que aponta onde olhar, sem tirar a autonomia nem vigiar | `inspetor.html`: sugestão + decisão humana; painel sem visão individual |
| 4. Usuários secundários | Painel por lote, turno e tipo; curadoria | `/painel`, `/curadoria` |
| 5. Imagens | Treino com as 10.668 do HRIPCB ampliado; teste com placas inteiras separadas por placa; VisA PCB1–4 | `scripts/converter_voc_para_yolo.py`, `scripts/dividir_por_placa.py`, `scripts/_visa.py` |
| 5. Anotações | VOC → YOLO; em fábrica, CVAT/Label Studio | `converter_voc_para_yolo.py`; exportação YOLO da curadoria (importável nas duas ferramentas) |
| 5. Decisão do inspetor | Sem nome/foto/biometria; código pseudonimizado; anonimizado após 90 dias; painel agregado | `app/lgpd.py`, `scripts/anonimizar.py`, `app/dashboard.py` |
| 5. Metadados | Simulados no protótipo; QR/ERP em fábrica | `app/metadata.py` (`simular`, `ler_codigo_qr`); coluna `metadados_simulados` |
| 5. Referências conformes | Validadas pelo técnico; risco de contaminação | `scripts/ajustar_anomalias.py --pasta-normais` |
| 7.(a) | Imagem anotada com contornos, rótulos e sugestão | `app/annotate.py`, `app/suggestion.py` |
| 7.(b) | Registro rastreável: lote, turno, posto, tipo, posição e decisão | `app/db.py` (`inspecoes`, `defeitos`) |
| 7.(c) | Painel agregado com alertas de reincidência | `app/dashboard.py` |
| 8.1 | Imagem 600×600 + metadados | `app/preprocess.py`, `app/metadata.py` |
| 8.2 | YOLOv10 Small, 6 classes, < 5 s | `app/detector.py`, `scripts/treinar_yolo.py` |
| 8.3 | Anomalias não supervisionadas (VisA) | `app/anomaly.py`, `scripts/ajustar_anomalias.py`, `scripts/avaliar_anomalias.py` |
| 8.4 | Web leve (Python/FastAPI + HTML/JS); decisões Aprovar/Rev. 1ª/Rev. 2ª/Reprovar; zoom/contorno + texto | `app/main.py`, `app/templates`, `app/static` |
| 8.5 | SQLite (protótipo) / PostgreSQL (fábrica) + disco | `app/db.py`, `app/storage.py` |
| 8.6 | Dashboard + curadoria → novo dataset | `app/dashboard.py`, `app/curation.py` |
| 8. Descartes | Sem aprendizado federado, blockchain ou LLM | nenhuma dessas dependências |
| 9. Figura 1 | Fluxo Entrada → Processamento → Decisão → Armazenamento → Gestão, com laço | `app/service.py` |
| 9. Nota | Contingência manual; nenhuma decisão automatizada | `service.py` (modo `contingencia`, `decisao` só via `decidir()`) |
| 9.1 | Decisões abertas | variáveis em `app/config.py` (ver `decisoes_e_pendencias.md`) |
| 10.1 | Recall, precisão, mAP@50, mAP@50-95 por classe nas placas de teste | `app/metricas.py`, `scripts/avaliar_deteccao.py` |
| 10.2 | Ruído gaussiano / sal e pimenta (Dias et al.) e anomalias no VisA | `scripts/avaliar_robustez.py`, `scripts/avaliar_anomalias.py` |
| 10.3 | Latência ponta a ponta frente aos ~30 s | `scripts/medir_latencia.py` |
| 10.4 | 20 placas (10 sem / 10 com), 30 s por placa | `scripts/teste_humano/gerar_sessao.py`, `/teste/<sessão>` |
| 10.5 | 1–2 erros propositais + questionário de usabilidade de 1 a 5 | idem + `analisar_resultados.py` |
| 10.6 | Auditoria nas tabelas | `scripts/auditar_rastreabilidade.py` |
| 11 | Critérios C1–C5 | `app/metricas.criterios`, `medir_latencia.py`, `analisar_resultados.py` |
| 12 | 10 riscos e mitigações | tabela na seção 6 do README |
| 14 | Limitações | README e saída dos scripts (avisos de dados sintéticos e de amostra pequena) |
