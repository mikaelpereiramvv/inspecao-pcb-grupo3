"""Governança de dados pessoais (LGPD – Lei nº 13.709/2018), Seção 5.

- A decisão do inspetor é dado pessoal (art. 5º, I): registra desempenho humano.
- Nenhum nome, foto ou biometria é coletado.
- O código do inspetor é PSEUDONIMIZADO (HMAC-SHA256 com segredo do servidor)
  antes de chegar ao banco; o código em claro nunca é gravado.
- Após 90 dias o pseudônimo é apagado (anonimização, art. 16), deixando apenas
  o registro técnico da inspeção.
- O painel mostra apenas totais agregados por lote/turno/tipo; não existe
  consulta por inspetor (veja app/dashboard.py).
"""
from __future__ import annotations

import hashlib
import hmac
import re
import sqlite3
from datetime import datetime, timedelta, timezone

PSEUDONIMO_ANONIMIZADO = None  # o campo vira NULL

_CODIGO_VALIDO = re.compile(r"^[A-Za-z0-9_-]{2,32}$")


def validar_codigo(codigo: str) -> str:
    codigo = (codigo or "").strip()
    if not _CODIGO_VALIDO.match(codigo):
        raise ValueError(
            "Use apenas o código funcional do posto/inspetor (2 a 32 letras, números, '-' ou '_'). "
            "Não informe nome, CPF ou outro dado pessoal."
        )
    return codigo


def pseudonimizar(codigo: str, segredo: str) -> str:
    codigo = validar_codigo(codigo)
    return hmac.new(segredo.encode(), codigo.encode(), hashlib.sha256).hexdigest()[:16]


def anonimizar_vencidos(con: sqlite3.Connection, dias: int, agora: datetime | None = None) -> int:
    """Apaga o pseudônimo de inspeções com mais de `dias` dias. Retorna quantas foram anonimizadas."""
    agora = agora or datetime.now(timezone.utc)
    corte = (agora - timedelta(days=dias)).isoformat()
    with con:
        cur = con.execute(
            "UPDATE inspecoes SET inspetor_pseudonimo = NULL, anonimizado_em = ? "
            "WHERE inspetor_pseudonimo IS NOT NULL AND criado_em < ?",
            (agora.isoformat(), corte),
        )
        con.execute(
            "UPDATE correcoes SET inspetor_pseudonimo = NULL "
            "WHERE inspetor_pseudonimo IS NOT NULL AND criado_em < ?",
            (corte,),
        )
    return cur.rowcount
