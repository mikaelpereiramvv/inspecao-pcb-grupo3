"""Ajusta o detector de anomalias com placas CONFORMES (Seção 8, componente 3).

Protótipo: imagens normais de treino das categorias PCB1–PCB4 do VisA.
Fábrica: amostras de placas aprovadas e validadas pelo Técnico de Qualidade (risco de contaminação, Seção 5).

Uso:
  python scripts/ajustar_anomalias.py --visa datasets/VisA --categorias pcb1 pcb2 pcb3 pcb4
  python scripts/ajustar_anomalias.py --pasta-normais fotos_aprovadas/ --modelo-placa MINHA_PLACA
Gera modelos/anomalia/<modelo>.npz (o nome deve coincidir com o "modelo da placa" informado na inspeção).
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import cv2
from _comum import listar_imagens
from _visa import particao

from app.anomaly import DetectorAnomalias
from app.config import carregar
from app.preprocess import preparar


def carregar_imgs(caminhos, tamanho):
    out = []
    for p in caminhos:
        img = cv2.imread(str(p))
        if img is not None:
            out.append(preparar(img, tamanho).bgr)
    return out


def main():
    cfg = carregar()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--visa", type=Path)
    ap.add_argument("--categorias", nargs="+", default=["pcb1", "pcb2", "pcb3", "pcb4"])
    ap.add_argument("--pasta-normais", type=Path)
    ap.add_argument("--modelo-placa")
    ap.add_argument("--max-normais", type=int, default=200, help="limita a memória/tempo de inferência")
    ap.add_argument("--saida", type=Path, default=cfg.pasta_anomalia)
    a = ap.parse_args()

    trabalhos = []
    if a.visa:
        for c in a.categorias:
            normais = [p for p, r, _ in particao(a.visa, c)["train"] if r == 0]
            trabalhos.append((c, normais))
    elif a.pasta_normais and a.modelo_placa:
        trabalhos.append((a.modelo_placa, listar_imagens(a.pasta_normais)))
    else:
        ap.error("informe --visa ou (--pasta-normais e --modelo-placa)")

    for nome, caminhos in trabalhos:
        random.Random(0).shuffle(caminhos)
        imgs = carregar_imgs(caminhos[: a.max_normais], cfg.tamanho_imagem)
        print(f"[{nome}] ajustando com {len(imgs)} placas conformes…")
        det = DetectorAnomalias.ajustar(imgs, nome)
        destino = a.saida / f"{nome.lower()}.npz"
        det.salvar(destino)
        print(f"[{nome}] limiar calibrado={det.limiar:.3f} → {destino}")


if __name__ == "__main__":
    main()
