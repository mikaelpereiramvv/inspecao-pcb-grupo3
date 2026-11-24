"""Seção 10, aspecto 2 – Robustez sob ruído (protocolo de Dias et al., 2025).

Roda a avaliação de detecção nas placas de teste: limpa, com ruído gaussiano e com ruído sal e pimenta
(intensidade 0,02), e compara o recall. A parte de anomalias (VisA PCB1–PCB4) está em avaliar_anomalias.py.

Uso:
  python scripts/avaliar_robustez.py --imagens datasets/pcb/test/images --rotulos datasets/pcb/test/labels
"""
from __future__ import annotations

import argparse
from pathlib import Path

from _comum import RAIZ, fmt, salvar_json
from avaliar_deteccao import rodar

from app.config import carregar


def main():
    cfg = carregar()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--imagens", required=True, type=Path)
    ap.add_argument("--rotulos", required=True, type=Path)
    ap.add_argument("--pesos", type=Path, default=cfg.pesos_yolo)
    ap.add_argument("--intensidade", type=float, default=0.02)
    ap.add_argument("--limite", type=int, default=None)
    ap.add_argument("--saida", type=Path, default=RAIZ / "resultados" / "robustez.json")
    a = ap.parse_args()

    resultados = {}
    for ruido in ("nenhum", "gaussiano", "sal_pimenta"):
        r = rodar(a.imagens, a.rotulos, a.pesos, cfg.conf_minima_deteccao, ruido, a.intensidade, a.limite)
        resultados[ruido] = {"recall": r["geral"]["recall"], "precisao": r["geral"]["precisao"],
                             "map50": r["geral"]["map50"]}
    base = resultados["nenhum"]["recall"] or 0
    print(f"\n{'Condição':<14}{'Recall':>9}{'Precisão':>10}{'mAP50':>8}{'Queda recall':>14}")
    for k, v in resultados.items():
        queda = None if v["recall"] is None or not base else (base - v["recall"])
        v["queda_recall_pp"] = queda
        print(f"{k:<14}{fmt(v['recall']):>9}{fmt(v['precisao']):>10}{fmt(v['map50']):>8}{fmt(queda):>14}")
    salvar_json({"intensidade": a.intensidade, "resultados": resultados}, a.saida)


if __name__ == "__main__":
    main()
