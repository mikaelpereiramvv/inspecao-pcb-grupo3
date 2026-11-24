# Decisões abertas (Seção 9.1) e pendências encontradas na implementação

## Decisões abertas: como ficaram configuráveis

| Decisão (9.1) | Como o protótipo trata | Onde ajustar |
|---|---|---|
| Variante exata do YOLO | Aceita qualquer peso Ultralytics (YOLOv10s, YOLOv8n, YOLO11s…) | `scripts/treinar_yolo.py --modelo`, `PCB_PESOS_YOLO` |
| Anomalias na mesma tela ou em aba separada | **Na mesma tela**, quando existe `modelos/anomalia/<modelo_da_placa>.npz`; regiões já explicadas pelo YOLO não se repetem | `PCB_PASTA_ANOMALIA` |
| Regra do "Revisar – 1ª vez" em imagem estática | Contraste (CLAHE), redução do limiar (−0,10) ou os dois (padrão) | `PCB_REPROC_MODO=contraste\|limiar\|ambos` |
| Limiar de confiança | 70% (exemplo do documento): abaixo disso a sugestão é "Revisar" | `PCB_LIMIAR_REVISAR` |

**Sugestão para a versão final:** escolher os valores com base em `avaliar_deteccao.py`, variando `--conf-operacao`, e na taxa de "alertas descartados" do painel.

## Pendências identificadas ao implementar

1. **Vazamento de dados entre as 10.668 imagens de treino e as 1.386 placas de teste.** O conjunto ampliado deriva do próprio HRIPCB. Se todas as 1.386 placas forem teste, os recortes de treino vêm das mesmas placas. `dividir_por_placa.py` reserva uma fração das placas para teste e **remove do treino** os recortes derivados delas. Com `--nivel template`, nenhum template de placa de teste aparece no treino. → Ajustar o texto das Seções 5 e 10 para o número real de placas de teste (`datasets/pcb/divisao.json`).
2. **"mAP@50-90"** → implementado como **mAP@50:95** (padrão COCO/Ultralytics). Corrigir o termo no documento.
3. **Resolução.** As placas inteiras do HRIPCB têm cerca de 3000×1600 px e defeitos de poucos pixels. Reduzir para 600×600 apaga os defeitos, então a detecção roda em **blocos 600×600 na resolução original** (`detectar_em_blocos`). O banco guarda as coordenadas no referencial de exibição 600×600 e o storage guarda também a imagem original.
4. **Ghost Convolution.** A Ultralytics traz o YOLOv10s padrão. Reproduzir Mitoso e Melo (2025) exige o YAML de arquitetura dos autores.
5. **Ruído "densidade 0,02".** No gaussiano foi usada variância 0,02 (escala 0–1); no sal e pimenta, 2% dos pixels. Conferir a convenção exata em Dias et al. (2025).
6. **Detector de anomalias.** É um baseline leve, sem GPU: k-NN de patches com características de cor e gradiente, posicional. Se o AUROC no VisA ficar baixo, trocar por PatchCore (anomalib) mantendo a interface `pontuar()`.
7. **Acesso por perfil** usa PIN simples no protótipo. Em fábrica, integrar ao login corporativo.
8. **"Revisar – 2ª vez" (análise externa)** fica registrada como decisão final do posto. O fluxo da análise externa não foi modelado (fora do recorte).
