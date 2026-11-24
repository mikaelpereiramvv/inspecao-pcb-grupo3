"""Monta o dataset YOLO de treino/validação/teste SEM vazamento de dados (Seção 5).

O teste final usa placas INTEIRAS originais do HRIPCB; os recortes/aumentos usados no treino
não podem vir dessas mesmas placas. A chave de agrupamento é extraída do nome do arquivo:
  HRIPCB original: 01_missing_hole_01.jpg      → imagem "01_missing_hole_01", template "01"
  recortes ampliados costumam manter esse prefixo (ex.: 01_missing_hole_01_crop_3.jpg)

--nivel imagem   : nenhuma imagem de teste tem recorte no treino (padrão)
--nivel template : nenhum TEMPLATE de placa de teste aparece no treino (mais rigoroso: mede
                   generalização para placas nunca vistas)

Uso:
  python scripts/dividir_por_placa.py --treino datasets/ampliado_yolo --teste datasets/hripcb_yolo \
         --saida datasets/pcb --frac-teste 0.2
Gera datasets/pcb/{train,val,test}/{images,labels} (links simbólicos) e datasets/pcb/pcb.yaml
"""
from __future__ import annotations

import argparse
import random
import re
from collections import defaultdict
from pathlib import Path

from _comum import listar_imagens, rotulo_de, salvar_json

from app.config import CLASSES

PADRAO = re.compile(r"^(?P<template>\d+)_(?P<classe>[a-z_]+?)_(?P<idx>\d+)", re.IGNORECASE)


def chave(nome: str, nivel: str) -> str:
    m = PADRAO.match(nome)
    if not m:
        return nome  # sem padrão reconhecido: o próprio arquivo é o grupo
    return m.group("template") if nivel == "template" else f"{m.group('template')}_{m.group('classe').lower()}_{m.group('idx')}"


def ligar(img: Path, raiz_img: Path, raiz_lbl: Path, destino: Path) -> None:
    lbl = rotulo_de(img, raiz_img, raiz_lbl)
    for origem, sub, suf in ((img, "images", img.suffix), (lbl, "labels", ".txt")):
        alvo = destino / sub / (img.stem + suf)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        if alvo.exists() or alvo.is_symlink():
            alvo.unlink()
        if origem.exists():
            alvo.symlink_to(origem.resolve())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--treino", type=Path, required=True, help="pasta YOLO (images/ e labels/) com as 10.668 imagens ampliadas")
    ap.add_argument("--teste", type=Path, required=True, help="pasta YOLO com as placas inteiras originais do HRIPCB")
    ap.add_argument("--saida", type=Path, required=True)
    ap.add_argument("--frac-teste", type=float, default=0.2, help="fração dos grupos de placas reservada para teste")
    ap.add_argument("--frac-val", type=float, default=0.1, help="fração do treino usada para validação")
    ap.add_argument("--nivel", choices=("imagem", "template"), default="imagem")
    ap.add_argument("--semente", type=int, default=42)
    a = ap.parse_args()
    rng = random.Random(a.semente)

    originais = listar_imagens(a.teste / "images")
    grupos = sorted({chave(p.stem, a.nivel) for p in originais})
    rng.shuffle(grupos)
    n_teste = max(1, round(len(grupos) * a.frac_teste))
    grupos_teste = set(grupos[:n_teste])

    teste = [p for p in originais if chave(p.stem, a.nivel) in grupos_teste]
    ampliadas = listar_imagens(a.treino / "images")
    por_grupo = defaultdict(list)
    descartadas = 0
    for p in ampliadas:
        k = chave(p.stem, a.nivel)
        if k in grupos_teste:
            descartadas += 1  # recorte derivado de placa de teste → fora (evita vazamento)
            continue
        por_grupo[k].append(p)
    gkeys = sorted(por_grupo)
    rng.shuffle(gkeys)
    n_val = max(1, round(len(gkeys) * a.frac_val))
    val = [p for k in gkeys[:n_val] for p in por_grupo[k]]
    treino = [p for k in gkeys[n_val:] for p in por_grupo[k]]

    for nome, lista, ri, rl in (("train", treino, a.treino / "images", a.treino / "labels"),
                                ("val", val, a.treino / "images", a.treino / "labels"),
                                ("test", teste, a.teste / "images", a.teste / "labels")):
        for p in lista:
            ligar(p, ri, rl, a.saida / nome)

    yaml = a.saida / "pcb.yaml"
    yaml.write_text(
        f"path: {a.saida.resolve()}\ntrain: train/images\nval: val/images\ntest: test/images\n"
        f"names:\n" + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES)))
    resumo = {"nivel": a.nivel, "grupos_teste": len(grupos_teste), "placas_inteiras_teste": len(teste),
              "treino": len(treino), "validacao": len(val), "recortes_descartados_por_vazamento": descartadas,
              "placas_inteiras_disponiveis": len(originais)}
    salvar_json(resumo, a.saida / "divisao.json")
    print(resumo)
    if descartadas == 0 and ampliadas:
        print("ATENÇÃO: nenhum recorte foi associado às placas de teste. Confira se os nomes dos arquivos "
              "ampliados preservam o prefixo da placa original; caso contrário use --nivel template.")


if __name__ == "__main__":
    main()
