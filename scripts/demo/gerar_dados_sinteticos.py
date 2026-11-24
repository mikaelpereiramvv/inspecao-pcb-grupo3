"""Gera um mini-dataset SINTÉTICO no mesmo formato do HRIPCB (imagens + XML Pascal VOC).

SERVE APENAS PARA ENSAIAR O PIPELINE (conversão → divisão → treino → avaliação → teste com
voluntários) sem baixar os conjuntos reais. Métricas obtidas com ele NÃO valem como resultado
do projeto: a avaliação oficial usa HRIPCB e VisA (Seção 5).

Uso:  python scripts/demo/gerar_dados_sinteticos.py --saida datasets/sintetico
Gera: <saida>/inteiras/{images,Annotations}  (placas inteiras, nomes 01_short_01.jpg)
      <saida>/recortes/{images,Annotations}  (recortes 600×600, nomes 01_short_01_crop0.jpg)
      <saida>/normais/                       (placas sem defeito, p/ detector de anomalias)
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import cv2
import numpy as np

CLASSES_HRIPCB = ["Missing_hole", "Mouse_bite", "Open_circuit", "Short", "Spur", "Spurious_copper"]


def placa_base(rng, w, h, template):
    r = random.Random(template)
    img = np.full((h, w, 3), (35 + r.randint(0, 15), 105 + r.randint(0, 20), 30), np.uint8)
    trilhas, furos = [], []
    for y in range(50 + r.randint(0, 20), h - 40, 70 + r.randint(0, 20)):
        x0, x1 = r.randint(20, 120), w - r.randint(20, 120)
        cv2.line(img, (x0, y), (x1, y), (70, 175, 205), 8)
        trilhas.append((x0, y, x1))
    for x in range(70, w - 40, 90):
        for y in range(85, h - 40, 140):
            cv2.circle(img, (x, y), 11, (205, 205, 205), -1)
            cv2.circle(img, (x, y), 5, (25, 25, 25), -1)
            furos.append((x, y))
    ruido = np.random.default_rng(rng.randint(0, 10**6)).integers(-4, 5, img.shape)
    return np.clip(img.astype(np.int16) + ruido, 0, 255).astype(np.uint8), trilhas, furos


def inserir_defeito(img, classe, trilhas, furos, rng):
    cobre, verde = (70, 175, 205), tuple(int(v) for v in img[5, 5])
    if classe == "Missing_hole":
        x, y = rng.choice(furos)
        cv2.circle(img, (x, y), 5, (205, 205, 205), -1)
        return x - 13, y - 13, x + 13, y + 13
    x0, y, x1 = rng.choice(trilhas)
    x = rng.randint(x0 + 40, x1 - 40)
    if classe == "Open_circuit":
        cv2.rectangle(img, (x, y - 5), (x + 7, y + 5), verde, -1)
        return x - 6, y - 10, x + 13, y + 10
    if classe == "Mouse_bite":
        for k in range(3):
            cv2.circle(img, (x + 5 * k, y - 4), 2, verde, -1)
        return x - 6, y - 10, x + 18, y + 6
    if classe == "Spur":
        cv2.line(img, (x, y), (x + 6, y - 14), cobre, 3)
        return x - 5, y - 19, x + 11, y + 4
    if classe == "Spurious_copper":
        cv2.circle(img, (x, y - 24), 6, cobre, -1)
        return x - 9, y - 33, x + 9, y - 15
    if classe == "Short":
        cv2.line(img, (x, y), (x, y + 30), cobre, 4)
        return x - 7, y - 4, x + 7, y + 34
    raise ValueError(classe)


def xml_voc(nome, w, h, objs):
    s = f"<annotation><filename>{nome}</filename><size><width>{w}</width><height>{h}</height><depth>3</depth></size>"
    for c, (x1, y1, x2, y2) in objs:
        s += (f"<object><name>{c}</name><bndbox><xmin>{int(x1)}</xmin><ymin>{int(y1)}</ymin>"
              f"<xmax>{int(x2)}</xmax><ymax>{int(y2)}</ymax></bndbox></object>")
    return s + "</annotation>"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--saida", type=Path, required=True)
    ap.add_argument("--templates", type=int, default=4)
    ap.add_argument("--por-classe", type=int, default=4, help="placas por (template, classe)")
    ap.add_argument("--normais", type=int, default=30)
    ap.add_argument("--semente", type=int, default=0)
    a = ap.parse_args()
    rng = random.Random(a.semente)
    W, H = 1200, 900
    for sub in ("inteiras/images", "inteiras/Annotations", "recortes/images", "recortes/Annotations", "normais"):
        (a.saida / sub).mkdir(parents=True, exist_ok=True)
    n_int = n_rec = 0
    for t in range(1, a.templates + 1):
        for c in CLASSES_HRIPCB:
            for i in range(1, a.por_classe + 1):
                img, trilhas, furos = placa_base(rng, W, H, t)
                objs = [(c, inserir_defeito(img, c, trilhas, furos, rng)) for _ in range(rng.randint(2, 4))]
                nome = f"{t:02d}_{c.lower()}_{i:02d}"
                cv2.imwrite(str(a.saida / "inteiras/images" / f"{nome}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                (a.saida / "inteiras/Annotations" / f"{nome}.xml").write_text(xml_voc(nome, W, H, objs))
                n_int += 1
                for k, (_, (x1, y1, x2, y2)) in enumerate(objs):   # recorte 600×600 em torno de cada defeito
                    cx = int(min(max((x1 + x2) / 2 + rng.randint(-150, 150), 300), W - 300))
                    cy = int(min(max((y1 + y2) / 2 + rng.randint(-150, 150), 300), H - 300))
                    ox, oy = cx - 300, cy - 300
                    rec = img[oy:oy + 600, ox:ox + 600]
                    dentro = [(cc, (bx1 - ox, by1 - oy, bx2 - ox, by2 - oy)) for cc, (bx1, by1, bx2, by2) in objs
                              if bx1 >= ox and by1 >= oy and bx2 <= ox + 600 and by2 <= oy + 600]
                    nr = f"{nome}_crop{k}"
                    cv2.imwrite(str(a.saida / "recortes/images" / f"{nr}.jpg"), rec, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    (a.saida / "recortes/Annotations" / f"{nr}.xml").write_text(xml_voc(nr, 600, 600, dentro))
                    n_rec += 1
    for k in range(a.normais):
        img, _, _ = placa_base(rng, W, H, 1)
        cv2.imwrite(str(a.saida / "normais" / f"normal_{k:03d}.png"), img)
    print(f"{n_int} placas inteiras, {n_rec} recortes e {a.normais} placas normais em {a.saida} (DADOS SINTÉTICOS)")


if __name__ == "__main__":
    main()
