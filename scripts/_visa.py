"""Leitura do dataset VisA (Zou et al., 2022), categorias PCB1–PCB4."""
from __future__ import annotations

import csv
import random
from pathlib import Path


def particao(visa: Path, categoria: str, semente: int = 0) -> dict[str, list[tuple[Path, int, Path | None]]]:
    """Retorna {'train': [(img, rotulo, mascara)], 'test': [...]}; rótulo 1 = anomalia.

    Usa VisA/split_csv/1cls.csv (divisão oficial) quando existir; senão 80% das normais para treino.
    """
    visa = Path(visa)
    csv_oficial = visa / "split_csv" / "1cls.csv"
    out = {"train": [], "test": []}
    if csv_oficial.exists():
        with open(csv_oficial, newline="") as f:
            for r in csv.DictReader(f):
                if r["object"].lower() != categoria.lower():
                    continue
                mascara = visa / r["mask"] if r.get("mask") else None
                out[r["split"]].append((visa / r["image"], int(r["label"] == "anomaly"), mascara))
        return out
    base = visa / categoria / "Data"
    normais = sorted((base / "Images" / "Normal").glob("*"))
    anomalas = sorted((base / "Images" / "Anomaly").glob("*"))
    random.Random(semente).shuffle(normais)
    corte = int(len(normais) * 0.8)
    out["train"] = [(p, 0, None) for p in normais[:corte]]
    out["test"] = [(p, 0, None) for p in normais[corte:]]
    for p in anomalas:
        m = base / "Masks" / "Anomaly" / (p.stem + ".png")
        out["test"].append((p, 1, m if m.exists() else None))
    return out


def auroc(scores: list[float], rotulos: list[int]) -> float | None:
    pos = [s for s, r in zip(scores, rotulos) if r == 1]
    neg = [s for s, r in zip(scores, rotulos) if r == 0]
    if not pos or not neg:
        return None
    vence = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return vence / (len(pos) * len(neg))
