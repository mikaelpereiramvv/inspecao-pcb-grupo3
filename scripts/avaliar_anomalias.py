"""Seção 10, aspecto 2 – Taxa de detecção de anomalias nas categorias PCB1–PCB4 do VisA.

Para cada categoria: AUROC (nível de imagem), taxa de detecção das placas anômalas no limiar
calibrado, taxa de falso alarme nas placas normais de teste e acerto de região (a região apontada
toca a máscara do defeito). Também pode repetir com ruído (--ruido).

Uso:
  python scripts/avaliar_anomalias.py --visa datasets/VisA --categorias pcb1 pcb2 pcb3 pcb4
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from _comum import RAIZ, aplicar_ruido, fmt, salvar_json
from _visa import auroc, particao

from app.anomaly import DetectorAnomalias
from app.config import carregar
from app.preprocess import preparar


def main():
    cfg = carregar()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--visa", type=Path, required=True)
    ap.add_argument("--categorias", nargs="+", default=["pcb1", "pcb2", "pcb3", "pcb4"])
    ap.add_argument("--ruido", choices=("nenhum", "gaussiano", "sal_pimenta"), default="nenhum")
    ap.add_argument("--intensidade", type=float, default=0.02)
    ap.add_argument("--limite", type=int, default=None, help="máx. de imagens de teste por categoria")
    ap.add_argument("--saida", type=Path, default=RAIZ / "resultados" / "anomalias.json")
    a = ap.parse_args()

    res = {}
    for c in a.categorias:
        det = DetectorAnomalias.carregar(cfg.pasta_anomalia / f"{c.lower()}.npz")
        teste = particao(a.visa, c)["test"][: a.limite] if a.limite else particao(a.visa, c)["test"]
        scores, rotulos, acerto_regiao, n_anom_det = [], [], 0, 0
        for k, (p, r, mascara) in enumerate(teste):
            img = cv2.imread(str(p))
            if img is None:
                continue
            if a.ruido != "nenhum":
                img = aplicar_ruido(img, a.ruido, a.intensidade, semente=k)
            out = det.pontuar(preparar(img, cfg.tamanho_imagem).bgr)
            scores.append(out.score)
            rotulos.append(r)
            if r == 1 and out.anomala:
                n_anom_det += 1
                if mascara is not None and Path(mascara).exists():
                    m = cv2.imread(str(mascara), cv2.IMREAD_GRAYSCALE)
                    m = cv2.resize(m, (cfg.tamanho_imagem, cfg.tamanho_imagem), interpolation=cv2.INTER_NEAREST) > 0
                    if any(m[y1:y2, x1:x2].any() for x1, y1, x2, y2 in out.regioes):
                        acerto_regiao += 1
        s, rr = np.array(scores), np.array(rotulos)
        n_anom, n_norm = int((rr == 1).sum()), int((rr == 0).sum())
        res[c] = {
            "imagens_teste": len(scores), "anomalas": n_anom, "normais": n_norm,
            "auroc": auroc(scores, rotulos),
            "taxa_deteccao": float(((s > 1) & (rr == 1)).sum() / n_anom) if n_anom else None,
            "taxa_falso_alarme": float(((s > 1) & (rr == 0)).sum() / n_norm) if n_norm else None,
            "acerto_regiao_entre_detectadas": acerto_regiao / n_anom_det if n_anom_det else None,
        }
        v = res[c]
        print(f"[{c}] AUROC={fmt(v['auroc'])} detecção={fmt(v['taxa_deteccao'])} "
              f"falso alarme={fmt(v['taxa_falso_alarme'])} região correta={fmt(v['acerto_regiao_entre_detectadas'])}")
    salvar_json({"ruido": a.ruido, "intensidade": a.intensidade, "categorias": res}, a.saida)


if __name__ == "__main__":
    main()
