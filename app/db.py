"""Banco relacional (Bloco 4 da Figura 1). SQLite no protótipo; PostgreSQL em fábrica.

Registro estruturado e rastreável de cada inspeção: lote, modelo, turno, posto,
etapa de origem, tipo e posição de cada defeito e decisão humana (Seção 7b).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS inspecoes (
    id                    TEXT PRIMARY KEY,       -- mesmo ID da imagem no storage
    criado_em             TEXT NOT NULL,          -- ISO-8601 UTC
    -- metadados produtivos (Seção 5)
    lote                  TEXT NOT NULL,
    modelo_placa          TEXT NOT NULL,
    turno                 TEXT NOT NULL,
    posto                 TEXT NOT NULL,
    etapa_origem          TEXT,
    data_hora_producao    TEXT,
    metadados_simulados   INTEGER NOT NULL DEFAULT 0,
    -- LGPD: pseudônimo, apagado após 90 dias
    inspetor_pseudonimo   TEXT,
    anonimizado_em        TEXT,
    -- saída do sistema
    modo                  TEXT NOT NULL CHECK (modo IN ('assistido','contingencia')),
    fora_contexto         INTEGER NOT NULL DEFAULT 0,
    sugestao              TEXT CHECK (sugestao IN ('APROVAR','REVISAR','REPROVAR')),
    motivo_sugestao       TEXT,
    limiar_usado          REAL,
    anomalia_score        REAL,
    latencia_ms           REAL,
    reprocessamentos      INTEGER NOT NULL DEFAULT 0,
    -- decisão humana (sempre do inspetor)
    decisao               TEXT CHECK (decisao IN ('APROVAR','REVISAR_1','REVISAR_2','REPROVAR')),
    decidido_em           TEXT,
    observacao            TEXT
);

CREATE TABLE IF NOT EXISTS deteccoes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    inspecao_id   TEXT NOT NULL REFERENCES inspecoes(id) ON DELETE CASCADE,
    rodada        INTEGER NOT NULL DEFAULT 0,  -- 0 = original, 1 = reprocessamento "Revisar 1ª"
    origem        TEXT NOT NULL CHECK (origem IN ('yolo','anomalia')),
    tipo          TEXT NOT NULL,
    confianca     REAL,
    x1 REAL NOT NULL, y1 REAL NOT NULL, x2 REAL NOT NULL, y2 REAL NOT NULL
);

-- Defeitos finais após a decisão humana (o que vai para o painel)
CREATE TABLE IF NOT EXISTS defeitos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    inspecao_id   TEXT NOT NULL REFERENCES inspecoes(id) ON DELETE CASCADE,
    tipo          TEXT NOT NULL,
    x1 REAL NOT NULL, y1 REAL NOT NULL, x2 REAL NOT NULL, y2 REAL NOT NULL,
    origem        TEXT NOT NULL CHECK (origem IN ('yolo','anomalia','inspetor')),
    confianca     REAL
);

-- Correções do inspetor → fila de curadoria do Técnico de Qualidade
CREATE TABLE IF NOT EXISTS correcoes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    inspecao_id         TEXT NOT NULL REFERENCES inspecoes(id) ON DELETE CASCADE,
    criado_em           TEXT NOT NULL,
    inspetor_pseudonimo TEXT,
    tipo_correcao       TEXT NOT NULL CHECK (tipo_correcao IN ('falso_positivo','defeito_nao_apontado','classe_errada')),
    classe              TEXT,
    classe_original     TEXT,
    x1 REAL, y1 REAL, x2 REAL, y2 REAL,
    status              TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente','aprovada','rejeitada')),
    curado_em           TEXT,
    obs_curadoria       TEXT,
    exportado           INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS eventos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    inspecao_id  TEXT REFERENCES inspecoes(id) ON DELETE CASCADE,
    em           TEXT NOT NULL,
    evento       TEXT NOT NULL,
    detalhes     TEXT
);

CREATE INDEX IF NOT EXISTS ix_insp_lote  ON inspecoes(lote);
CREATE INDEX IF NOT EXISTS ix_insp_turno ON inspecoes(turno);
CREATE INDEX IF NOT EXISTS ix_insp_data  ON inspecoes(criado_em);
CREATE INDEX IF NOT EXISTS ix_def_insp   ON defeitos(inspecao_id);
CREATE INDEX IF NOT EXISTS ix_corr_status ON correcoes(status);
"""


def conectar(caminho: Path | str) -> sqlite3.Connection:
    if str(caminho) != ":memory:":
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    # Transações explícitas com "with con:" (commit/rollback automáticos).
    con = sqlite3.connect(str(caminho), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    if str(caminho) != ":memory:":
        con.execute("PRAGMA journal_mode = WAL")
    con.executescript(ESQUEMA)
    return con
