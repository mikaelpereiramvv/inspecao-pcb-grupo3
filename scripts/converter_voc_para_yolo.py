"""Converte anotações Pascal VOC (HRIPCB / conjunto ampliado de Mitoso e Melo, 2025) para o formato YOLO.

Seção 5: "caixas delimitadoras já presentes nos conjuntos públicos (convertidas de Pascal VOC para formato YOLO)".

Uso:
  python scripts/converter_voc_para_yolo.py --imagens PCB_DATASET/images --anotacoes PCB_DATASET/Annotations \
         --saida datasets/hripcb_yolo/todas
Cria <saida>/images/... e <saida>/labels/... preservando a estrutura de subpastas.
"""
from __future__ import annotations

import argparse
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from _comum import listar_imagens

from app.config import CLASSES

SINONIMOS = {"missing_hole": "missing_hole", "mouse_bite": "mouse_bite", "open_circuit": "open_circuit",
             "short": "short", "spur": "spur", "spurious_copper": "spurious_copper"}


def normalizar(nome: str) -> str:
    n = nome.strip().lower().replace(" ", "_").replace("-", "_")
    if n not in SINONIMOS:
        raise ValueError(f"Classe desconhecida no XML: {nome!r}")
    return SINONIMOS[n]


def converter_xml(xml: Path) -> tuple[list[str], int, int]:
    raiz = ET.parse(xml).getroot()
    w = int(float(raiz.findtext("size/width")))
    h = int(float(raiz.findtext("size/height")))
    linhas = []
    for obj in raiz.iter("object"):
        c = normalizar(obj.findtext("name"))
        bb = obj.find("bndbox")
        x1, y1, x2, y2 = (float(bb.findtext(k)) for k in ("xmin", "ymin", "xmax", "ymax"))
        x1, x2 = max(0, min(x1, x2)), min(w, max(x1, x2))
        y1, y2 = max(0, min(y1, y2)), min(h, max(y1, y2))
        if x2 - x1 < 1 or y2 - y1 < 1:
            continue
        linhas.append(f"{CLASSES.index(c)} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} "
                      f"{(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}")
    return linhas, w, h


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--imagens", required=True, type=Path)
    ap.add_argument("--anotacoes", required=True, type=Path)
    ap.add_argument("--saida", required=True, type=Path)
    ap.add_argument("--mover", action="store_true", help="cria links simbólicos em vez de copiar as imagens")
    a = ap.parse_args()

    xmls = {x.stem: x for x in a.anotacoes.rglob("*.xml")}
    sem_xml, n_caixas, n = 0, 0, 0
    for img in listar_imagens(a.imagens):
        xml = xmls.get(img.stem)
        if xml is None:
            sem_xml += 1
            continue
        linhas, _, _ = converter_xml(xml)
        rel = img.relative_to(a.imagens)
        destino_img = a.saida / "images" / rel
        destino_lbl = (a.saida / "labels" / rel).with_suffix(".txt")
        destino_img.parent.mkdir(parents=True, exist_ok=True)
        destino_lbl.parent.mkdir(parents=True, exist_ok=True)
        if a.mover:
            if not destino_img.exists():
                destino_img.symlink_to(img.resolve())
        else:
            shutil.copy2(img, destino_img)
        destino_lbl.write_text("\n".join(linhas) + ("\n" if linhas else ""))
        n += 1
        n_caixas += len(linhas)
    print(f"{n} imagens convertidas, {n_caixas} caixas. Imagens sem XML ignoradas: {sem_xml}")


if __name__ == "__main__":
    main()
