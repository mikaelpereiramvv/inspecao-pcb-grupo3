"""Seção 10, aspecto 6 – Rastreabilidade do registro.

Auditoria direta nas tabelas do banco: porcentagem de inspeções DECIDIDAS salvas com lote, tipo,
posição e decisão. Regras:
  - toda inspeção decidida precisa de lote, turno, posto e decisão;
  - inspeção REPROVADA precisa de ao menos um defeito com tipo e posição (caixa válida);
  - todo defeito registrado precisa de tipo e posição válidos.

Uso:  python scripts/auditar_rastreabilidade.py [--banco data/inspecoes.db]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from _comum import RAIZ, salvar_json

from app.config import carregar
from app.db import conectar


def auditar(con) -> dict:
    total = con.execute("SELECT COUNT(*) FROM inspecoes WHERE decisao IS NOT NULL").fetchone()[0]
    falhas = {
        "sem_metadados": con.execute(
            """SELECT COUNT(*) FROM inspecoes WHERE decisao IS NOT NULL AND
               (TRIM(COALESCE(lote,''))='' OR TRIM(COALESCE(turno,''))='' OR TRIM(COALESCE(posto,''))='')""").fetchone()[0],
        "reprovada_sem_defeito_localizado": con.execute(
            """SELECT COUNT(*) FROM inspecoes i WHERE decisao='REPROVAR' AND NOT EXISTS
               (SELECT 1 FROM defeitos d WHERE d.inspecao_id=i.id AND TRIM(d.tipo)<>'' AND d.x2>d.x1 AND d.y2>d.y1)""").fetchone()[0],
        "defeito_sem_tipo_ou_posicao": con.execute(
            """SELECT COUNT(DISTINCT inspecao_id) FROM defeitos WHERE TRIM(COALESCE(tipo,''))='' OR
               x1 IS NULL OR y1 IS NULL OR x2<=x1 OR y2<=y1""").fetchone()[0],
    }
    incompletas = con.execute(
        """SELECT COUNT(*) FROM inspecoes i WHERE decisao IS NOT NULL AND (
             TRIM(COALESCE(lote,''))='' OR TRIM(COALESCE(turno,''))='' OR TRIM(COALESCE(posto,''))=''
             OR (decisao='REPROVAR' AND NOT EXISTS (SELECT 1 FROM defeitos d WHERE d.inspecao_id=i.id
                 AND TRIM(d.tipo)<>'' AND d.x2>d.x1 AND d.y2>d.y1))
             OR EXISTS (SELECT 1 FROM defeitos d WHERE d.inspecao_id=i.id AND (TRIM(COALESCE(d.tipo,''))=''
                 OR d.x2<=d.x1 OR d.y2<=d.y1)))""").fetchone()[0]
    pendentes = con.execute("SELECT COUNT(*) FROM inspecoes WHERE decisao IS NULL").fetchone()[0]
    return {"inspecoes_decididas": total, "completas": total - incompletas,
            "percentual_rastreavel": (total - incompletas) / total if total else None,
            "falhas": falhas, "inspecoes_sem_decisao": pendentes}


def main():
    cfg = carregar()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--banco", type=Path, default=cfg.banco)
    ap.add_argument("--saida", type=Path, default=RAIZ / "resultados" / "rastreabilidade.json")
    a = ap.parse_args()
    r = auditar(conectar(a.banco))
    pct = "—" if r["percentual_rastreavel"] is None else f"{r['percentual_rastreavel']:.1%}"
    print(f"{r['completas']}/{r['inspecoes_decididas']} inspeções com lote, tipo, posição e decisão ({pct}).")
    print("Falhas:", r["falhas"], "| sem decisão:", r["inspecoes_sem_decisao"])
    salvar_json(r, a.saida)


if __name__ == "__main__":
    main()
