"""Gera a sessão do teste controlado com voluntários (Seção 10, aspectos 4 e 5).

Protocolo (Seções 10 e 11):
  * cada participante avalia 20 placas: 10 SEM assistente e 10 COM assistente, até 30 s por placa;
  * contrabalanceamento: grupo A vê as placas 1–10 sem e 11–20 com assistente; grupo B, o inverso
    (assim a dificuldade das placas não favorece nenhuma condição);
  * 1 a 2 sugestões ERRADAS propositais na metade assistida (omissão de um defeito real ou
    falso alarme em área sem defeito) para medir viés de automação.

Uso:
  python scripts/teste_humano/gerar_sessao.py --imagens datasets/pcb/test/images \
         --rotulos datasets/pcb/test/labels --sessao S1
  (sem modelo treinado, para ensaio da dinâmica: --sugestoes-do-gabarito)
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _comum import listar_imagens, rotulo_de, salvar_json  # noqa: E402

from app.config import CLASSES, carregar  # noqa: E402
from app.detector import DetectorYOLO, detectar_em_blocos  # noqa: E402
from app.metricas import ler_rotulos_yolo  # noqa: E402


def caixa_livre(gabarito, w, h, rng, lado=40):
    for _ in range(200):
        x, y = rng.uniform(lado, w - 2 * lado), rng.uniform(lado, h - 2 * lado)
        c = {"x1": x, "y1": y, "x2": x + lado, "y2": y + lado}
        if all(c["x2"] + 30 < g["x1"] or c["x1"] - 30 > g["x2"] or c["y2"] + 30 < g["y1"] or c["y1"] - 30 > g["y2"]
               for g in gabarito):
            return c
    raise RuntimeError("Não achei área livre para o falso alarme.")


def main():
    cfg = carregar()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--imagens", required=True, type=Path)
    ap.add_argument("--rotulos", required=True, type=Path)
    ap.add_argument("--sessao", required=True)
    ap.add_argument("--n-placas", type=int, default=20)
    ap.add_argument("--erros-por-metade", type=int, choices=(1, 2), default=1)
    ap.add_argument("--exibicao", type=int, default=900, help="maior lado da imagem exibida (px)")
    ap.add_argument("--sugestoes-do-gabarito", action="store_true",
                    help="ensaio sem modelo: usa o gabarito como sugestão (NÃO usar no teste real)")
    ap.add_argument("--semente", type=int, default=7)
    ap.add_argument("--saida", type=Path, default=cfg.pasta_teste)
    a = ap.parse_args()
    if a.n_placas % 2:
        ap.error("--n-placas deve ser par")
    rng = random.Random(a.semente)

    candidatas = [p for p in listar_imagens(a.imagens) if rotulo_de(p, a.imagens, a.rotulos).exists()]
    if len(candidatas) < a.n_placas:
        raise SystemExit(f"Só há {len(candidatas)} imagens com gabarito.")
    escolhidas = rng.sample(candidatas, a.n_placas)
    det = None if a.sugestoes_do_gabarito else DetectorYOLO(cfg.pesos_yolo)

    pasta = a.saida / a.sessao
    (pasta / "img").mkdir(parents=True, exist_ok=True)
    placas = []
    for i, p in enumerate(escolhidas, 1):
        img = cv2.imread(str(p))
        h, w = img.shape[:2]
        gts = ler_rotulos_yolo(rotulo_de(p, a.imagens, a.rotulos), w, h, CLASSES)
        if det is not None:
            sug = [(d.classe, d.confianca, d.x1, d.y1, d.x2, d.y2)
                   for d in detectar_em_blocos(det, img, cfg.conf_minima_deteccao)]
        else:
            sug = [(g.classe, 0.9, g.x1, g.y1, g.x2, g.y2) for g in gts]
        s = a.exibicao / max(h, w)
        img_s = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
        arquivo = f"{i:02d}.png"
        cv2.imwrite(str(pasta / "img" / arquivo), img_s)
        esc = lambda x1, y1, x2, y2: {"x1": x1 * s, "y1": y1 * s, "x2": x2 * s, "y2": y2 * s}  # noqa: E731
        placas.append({
            "id": i, "arquivo": arquivo, "origem": p.name, "largura": img_s.shape[1], "altura": img_s.shape[0],
            "gabarito": [{"classe": g.classe, **esc(g.x1, g.y1, g.x2, g.y2)} for g in gts],
            "sugestoes": [{"classe": c, "confianca": round(cf, 3), **esc(*b)} for c, cf, *b in sug],
            "erro_proposital": None,
        })

    # Erros propositais: em cada metade (cada participante vê exatamente uma metade com assistente)
    tipos = ["omissao", "falso_alarme"]
    for m, metade in enumerate((placas[: a.n_placas // 2], placas[a.n_placas // 2:])):
        for k, pl in enumerate(rng.sample(metade, a.erros_por_metade)):
            tipo = tipos[(k + m) % 2]
            if tipo == "omissao" and pl["sugestoes"] and pl["gabarito"]:
                alvo = rng.choice(pl["sugestoes"])
                pl["sugestoes"].remove(alvo)
                # o defeito real omitido (o gabarito mais próximo da sugestão removida)
                g = min(pl["gabarito"], key=lambda g: abs(g["x1"] - alvo["x1"]) + abs(g["y1"] - alvo["y1"]))
                pl["erro_proposital"] = {"tipo": "omissao", "caixa": {k2: g[k2] for k2 in ("x1", "y1", "x2", "y2")}}
            else:
                c = caixa_livre(pl["gabarito"], pl["largura"], pl["altura"], rng)
                pl["sugestoes"].append({"classe": rng.choice(CLASSES), "confianca": 0.88, **c})
                pl["erro_proposital"] = {"tipo": "falso_alarme", "caixa": c}

    metade = a.n_placas // 2
    plano = {
        "sessao": a.sessao, "limite_s": cfg.janela_linha_s, "limiar_revisar": cfg.limiar_revisar,
        "sugestoes_fonte": "gabarito (ENSAIO)" if det is None else "modelo",
        "placas": placas,
        # grupo → lista de (id_placa, com_assistente)
        "grupos": {"A": [[pl["id"], i >= metade] for i, pl in enumerate(placas)],
                   "B": [[pl["id"], i < metade] for i, pl in enumerate(placas)]},
    }
    salvar_json(plano, pasta / "sessao.json")
    print(f"Sessão '{a.sessao}' pronta: abra /teste/{a.sessao} logado como Técnico ou Supervisor.")


if __name__ == "__main__":
    main()
