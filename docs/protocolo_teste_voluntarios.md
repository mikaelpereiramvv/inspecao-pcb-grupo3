# Protocolo do teste controlado com voluntários (Seção 10, aspectos 4 e 5)

**Objetivo:** verificar se o assistente reduz os defeitos que passam despercebidos (Critério 4) sem gerar confiança cega (Critério 5).

## Preparação
1. Treine o modelo e gere a sessão com placas de **teste** (nunca vistas no treino):
   `python scripts/teste_humano/gerar_sessao.py --imagens datasets/pcb/test/images --rotulos datasets/pcb/test/labels --sessao S1`
2. A sessão sorteia 20 placas. Em cada metade, 1 placa recebe uma **sugestão errada proposital** (use `--erros-por-metade 2` para 2):
   * **omissão**: o assistente "esquece" um defeito real;
   * **falso alarme**: o assistente aponta uma área sem defeito.
3. O aplicador entra como Técnico ou Supervisor e abre `http://<servidor>:8000/teste/S1`.

## Aplicação (por participante, cerca de 12 minutos)
1. O participante recebe um **código** (V01, V02, …), sem nome. Códigos ímpares vão para o grupo A e pares para o grupo B.
   * Grupo A: placas 1–10 **sem** assistente, 11–20 **com** assistente.
   * Grupo B: placas 1–10 **com** assistente, 11–20 **sem**.
2. Leia a instrução da tela: *"clique sobre cada defeito que você encontrar; as sugestões podem estar erradas"*. Não revele quantos erros existem.
3. Cada placa tem no máximo **30 s**; ao esgotar, a tela avança sozinha.
4. No final, o participante responde ao questionário: facilidade de uso de 1 a 5 e se percebeu sugestão errada.

## Análise
`python scripts/teste_humano/analisar_resultados.py --sessao S1`

* **Escape** = defeitos do gabarito sem nenhum clique dentro da caixa (tolerância de 8 px), comparado como **taxa** em cada condição.
* **Percebeu o erro proposital**: na omissão, clicou no defeito esquecido; no falso alarme, **não** clicou na caixa falsa.
* **C4**: taxa de escape com assistente < sem assistente. Também é reportado o teste do sinal por participante.
* **C5**: mais da metade percebeu ao menos um erro **e** usabilidade média ≥ 3,0.

## Cuidados éticos e LGPD
* Participação voluntária; nenhum nome, foto ou biometria é coletado. Os resultados ficam em `data/teste_humano/<sessão>/resultados/<código>.json`.
* Resultados individuais não são divulgados; o relatório usa totais.
* **Limitação (Seção 14):** colegas de turma, e não inspetores profissionais, em janela curta. É evidência indicativa, não comprovação estatística.
