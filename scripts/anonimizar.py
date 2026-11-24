"""Rotina LGPD: apaga o pseudônimo do inspetor de registros com mais de 90 dias (art. 16).

Agende diariamente, ex. (cron):  0 2 * * *  cd /caminho/projeto && python scripts/anonimizar.py
"""
from __future__ import annotations

import argparse
from pathlib import Path

import _comum  # noqa: F401

from app.config import carregar
from app.db import conectar
from app.lgpd import anonimizar_vencidos


def main():
    cfg = carregar()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--banco", type=Path, default=cfg.banco)
    ap.add_argument("--dias", type=int, default=cfg.dias_anonimizacao)
    a = ap.parse_args()
    n = anonimizar_vencidos(conectar(a.banco), a.dias)
    print(f"{n} inspeção(ões) anonimizada(s) (corte: {a.dias} dias).")


if __name__ == "__main__":
    main()
