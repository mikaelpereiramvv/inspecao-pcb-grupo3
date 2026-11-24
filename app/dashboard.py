"""Painel de Indicadores (Bloco 5 da Figura 1) – Supervisor e Técnico de Qualidade.

Somente TOTAIS AGREGADOS por tipo, lote, turno, posto e etapa de origem.
Por desenho (LGPD e risco de vigilância punitiva, Seção 12), não existe
nenhuma consulta agrupada por inspetor.
"""
from __future__ import annotations

import sqlite3
from collections import Counter

from .config import ROTULOS_PT


def _filtro(lote: str | None, turno: str | None, desde: str | None, ate: str | None, alias: str = "i"):
    cond, args = [f"{alias}.decisao IS NOT NULL"], []
    if lote:
        cond.append(f"{alias}.lote = ?"); args.append(lote)
    if turno:
        cond.append(f"{alias}.turno = ?"); args.append(turno)
    if desde:
        cond.append(f"{alias}.criado_em >= ?"); args.append(desde)
    if ate:
        cond.append(f"{alias}.criado_em <= ?"); args.append(ate)
    return " AND ".join(cond), args


def resumo(con: sqlite3.Connection, lote=None, turno=None, desde=None, ate=None) -> dict:
    where, args = _filtro(lote, turno, desde, ate)
    q = lambda sql, extra=(): con.execute(sql, (*args, *extra)).fetchall()  # noqa: E731

    tot = q(f"""SELECT COUNT(*) n,
                  SUM(decisao='APROVAR') aprovadas, SUM(decisao='REPROVAR') reprovadas,
                  SUM(decisao='REVISAR_2') revisar2, SUM(reprocessamentos>0) revisar1,
                  SUM(modo='contingencia') contingencia,
                  SUM(CASE WHEN sugestao IN ('APROVAR','REPROVAR') THEN 1 ELSE 0 END) sugestoes_diretas,
                  SUM(CASE WHEN sugestao=decisao THEN 1 ELSE 0 END) concordantes,
                  AVG(CASE WHEN modo='assistido' THEN latencia_ms END) latencia_media_ms
                FROM inspecoes i WHERE {where}""")[0]
    n = tot["n"] or 0

    por_tipo = q(f"""SELECT d.tipo, COUNT(*) n, COUNT(DISTINCT d.inspecao_id) placas
                     FROM defeitos d JOIN inspecoes i ON i.id = d.inspecao_id
                     WHERE {where} GROUP BY d.tipo ORDER BY n DESC""")

    def agrupado(campo: str):
        rows = q(f"""SELECT i.{campo} chave, COUNT(*) n,
                       SUM(i.decisao='REPROVAR') reprovadas,
                       SUM(EXISTS(SELECT 1 FROM defeitos d WHERE d.inspecao_id=i.id)) com_defeito
                     FROM inspecoes i WHERE {where} GROUP BY i.{campo} ORDER BY i.{campo}""")
        return [{"chave": r["chave"] or "—", "inspecoes": r["n"], "reprovadas": r["reprovadas"] or 0,
                 "com_defeito": r["com_defeito"] or 0,
                 "taxa_defeito": round((r["com_defeito"] or 0) / r["n"], 3) if r["n"] else 0.0} for r in rows]

    corr = q(f"""SELECT c.tipo_correcao, COUNT(*) n FROM correcoes c JOIN inspecoes i ON i.id=c.inspecao_id
                 WHERE {where} GROUP BY c.tipo_correcao""")
    n_alertas = q(f"""SELECT COUNT(*) FROM deteccoes d JOIN inspecoes i ON i.id=d.inspecao_id
                      WHERE {where} AND d.rodada = (SELECT MAX(rodada) FROM deteccoes x WHERE x.inspecao_id=i.id)""")[0][0]
    corr_d = {r["tipo_correcao"]: r["n"] for r in corr}

    return {
        "total_inspecoes": n,
        "aprovadas": tot["aprovadas"] or 0,
        "reprovadas": tot["reprovadas"] or 0,
        "revisar_2": tot["revisar2"] or 0,
        "passaram_por_revisar_1": tot["revisar1"] or 0,
        "em_contingencia": tot["contingencia"] or 0,
        "taxa_reprovacao": round((tot["reprovadas"] or 0) / n, 3) if n else 0.0,
        # entre as sugestões diretas (Aprovar/Reprovar), fração em que o inspetor decidiu igual
        "concordancia_sugestao_decisao": round((tot["concordantes"] or 0) / tot["sugestoes_diretas"], 3)
        if tot["sugestoes_diretas"] else None,
        "latencia_media_s": round(tot["latencia_media_ms"] / 1000, 2) if tot["latencia_media_ms"] else None,
        "por_tipo": [{"tipo": r["tipo"], "rotulo": ROTULOS_PT.get(r["tipo"], r["tipo"]), "ocorrencias": r["n"],
                      "placas": r["placas"]} for r in por_tipo],
        "por_lote": agrupado("lote"),
        "por_turno": agrupado("turno"),
        "por_posto": agrupado("posto"),
        "por_etapa_origem": agrupado("etapa_origem"),
        # Monitoramento de falso positivo (Seção 12): fração dos alertas do sistema descartados pelo inspetor
        "alertas_sistema": n_alertas,
        "correcoes": corr_d,
        "taxa_alertas_descartados": round(corr_d.get("falso_positivo", 0) / n_alertas, 3) if n_alertas else None,
    }


def alertas_reincidencia(con: sqlite3.Connection, min_ocorrencias: int, taxa_minima: float,
                         desde: str | None = None) -> list[dict]:
    """Defeito do mesmo tipo reincidente em um lote → alerta para a etapa produtiva de origem."""
    cond, args = ["i.decisao IS NOT NULL"], []
    if desde:
        cond.append("i.criado_em >= ?"); args.append(desde)
    where = " AND ".join(cond)
    totais = {r["lote"]: r["n"] for r in con.execute(
        f"SELECT lote, COUNT(*) n FROM inspecoes i WHERE {where} GROUP BY lote", args)}
    rows = con.execute(
        f"""SELECT i.lote, d.tipo, COUNT(DISTINCT i.id) placas, GROUP_CONCAT(i.etapa_origem, '|') etapas,
                   GROUP_CONCAT(DISTINCT i.turno) turnos, MIN(i.criado_em) primeiro, MAX(i.criado_em) ultimo
            FROM defeitos d JOIN inspecoes i ON i.id = d.inspecao_id
            WHERE {where} GROUP BY i.lote, d.tipo""", args).fetchall()
    alertas = []
    for r in rows:
        total = totais.get(r["lote"], 0)
        taxa = r["placas"] / total if total else 0.0
        if r["placas"] >= min_ocorrencias and taxa >= taxa_minima:
            etapas = Counter(e for e in (r["etapas"] or "").split("|") if e)
            alertas.append({
                "lote": r["lote"],
                "tipo": r["tipo"],
                "rotulo": ROTULOS_PT.get(r["tipo"], r["tipo"]),
                "placas_afetadas": r["placas"],
                "placas_inspecionadas": total,
                "taxa": round(taxa, 3),
                "etapa_origem": etapas.most_common(1)[0][0] if etapas else None,
                "turnos": r["turnos"],
                "periodo": [r["primeiro"], r["ultimo"]],
                "mensagem": (f"Lote {r['lote']}: '{ROTULOS_PT.get(r['tipo'], r['tipo'])}' em {r['placas']} de "
                             f"{total} placas ({taxa:.0%}). Verificar etapa de origem"
                             + (f" '{etapas.most_common(1)[0][0]}'." if etapas else ".")),
            })
    alertas.sort(key=lambda a: (-a["taxa"], -a["placas_afetadas"]))
    return alertas
