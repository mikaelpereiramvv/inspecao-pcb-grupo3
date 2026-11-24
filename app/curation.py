"""Retorno à Origem & Curadoria (Bloco 5 da Figura 1).

Risco "Contaminação do retreinamento" (Seção 12): nenhuma correção do inspetor
entra na base de treino sem aprovação do Técnico de Qualidade. Só inspeções
com TODAS as correções curadas (e ao menos uma aprovada) são exportadas, no
formato YOLO, para retreinar o detector (laço de realimentação da Figura 1).
O mesmo diretório pode ser importado no Label Studio/CVAT para revisão visual.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import CLASSES
from .storage import Storage


class ErroCuradoria(ValueError):
    pass


def listar(con: sqlite3.Connection, status: str = "pendente", limite: int = 200) -> list[dict]:
    rows = con.execute(
        """SELECT c.id, c.inspecao_id, c.criado_em, c.tipo_correcao, c.classe, c.classe_original,
                  c.x1, c.y1, c.x2, c.y2, c.status, c.obs_curadoria, i.lote, i.modelo_placa, i.turno, i.posto
           FROM correcoes c JOIN inspecoes i ON i.id = c.inspecao_id
           WHERE c.status = ? ORDER BY c.criado_em LIMIT ?""",
        (status, limite),
    ).fetchall()
    return [dict(r) for r in rows]


def curar(con: sqlite3.Connection, id_correcao: int, aprovar: bool, obs: str | None = None) -> None:
    with con:
        cur = con.execute(
            "UPDATE correcoes SET status = ?, curado_em = ?, obs_curadoria = ? WHERE id = ? AND status = 'pendente'",
            ("aprovada" if aprovar else "rejeitada", datetime.now(timezone.utc).isoformat(),
             (obs or "").strip()[:500] or None, id_correcao),
        )
    if cur.rowcount == 0:
        raise ErroCuradoria("Correção inexistente ou já curada.")


def _mesma_caixa(a: dict, b: dict, tol: float = 0.5) -> bool:
    return all(abs(float(a[k]) - float(b[k])) <= tol for k in ("x1", "y1", "x2", "y2"))


def rotulos_curados(con: sqlite3.Connection, id_insp: str) -> list[dict]:
    """Detecções do sistema + apenas as correções APROVADAS pelo técnico."""
    rod = con.execute("SELECT COALESCE(MAX(rodada),0) FROM deteccoes WHERE inspecao_id=?", (id_insp,)).fetchone()[0]
    caixas = [dict(r) for r in con.execute(
        "SELECT tipo, x1, y1, x2, y2 FROM deteccoes WHERE inspecao_id=? AND rodada=? AND origem='yolo'",
        (id_insp, rod))]
    aprovadas = [dict(r) for r in con.execute(
        "SELECT * FROM correcoes WHERE inspecao_id=? AND status='aprovada'", (id_insp,))]
    for c in aprovadas:
        if c["tipo_correcao"] == "falso_positivo":
            caixas = [b for b in caixas if not _mesma_caixa(b, c)]
        elif c["tipo_correcao"] == "classe_errada":
            for b in caixas:
                if _mesma_caixa(b, c):
                    b["tipo"] = c["classe"]
        elif c["tipo_correcao"] == "defeito_nao_apontado":
            caixas.append({"tipo": c["classe"], "x1": c["x1"], "y1": c["y1"], "x2": c["x2"], "y2": c["y2"]})
    return caixas


def exportar_yolo(con: sqlite3.Connection, storage: Storage, pasta: Path, tamanho: int = 600) -> dict:
    pasta = Path(pasta)
    (pasta / "images").mkdir(parents=True, exist_ok=True)
    (pasta / "labels").mkdir(parents=True, exist_ok=True)
    ids = [r[0] for r in con.execute(
        """SELECT inspecao_id FROM correcoes GROUP BY inspecao_id
           HAVING SUM(status='pendente') = 0 AND SUM(status='aprovada') > 0 AND SUM(exportado=0) > 0""")]
    n_caixas, ignoradas = 0, 0
    for id_insp in ids:
        linhas = []
        for b in rotulos_curados(con, id_insp):
            if b["tipo"] not in CLASSES:
                ignoradas += 1  # "outro"/"anomalia": sem classe no YOLO → fica para nova classe futura
                continue
            cx = (b["x1"] + b["x2"]) / 2 / tamanho
            cy = (b["y1"] + b["y2"]) / 2 / tamanho
            w = (b["x2"] - b["x1"]) / tamanho
            h = (b["y2"] - b["y1"]) / tamanho
            linhas.append(f"{CLASSES.index(b['tipo'])} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
        (pasta / "images" / f"{id_insp}.png").write_bytes(storage.ler(id_insp, "original"))
        (pasta / "labels" / f"{id_insp}.txt").write_text("\n".join(linhas) + ("\n" if linhas else ""))
        n_caixas += len(linhas)
        with con:
            con.execute("UPDATE correcoes SET exportado = 1 WHERE inspecao_id = ?", (id_insp,))
    (pasta / "classes.txt").write_text("\n".join(CLASSES) + "\n")
    return {"imagens": len(ids), "caixas": n_caixas, "caixas_sem_classe_yolo": ignoradas, "pasta": str(pasta)}
