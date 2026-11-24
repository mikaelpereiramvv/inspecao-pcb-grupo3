"""Metadados produtivos (Bloco 1 da Figura 1).

Em fábrica: leitura de QR/código de barras da placa ou integração com ERP/MES.
No protótipo: gerados de forma SIMULADA (Seção 5) e marcados como tal no banco.
"""
from __future__ import annotations

import random
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

TURNOS = ("A", "B", "C")
ETAPAS_ORIGEM = ("Corrosão/gravação", "Furação", "Laminação", "Aplicação de máscara de solda")

_CAMPO = re.compile(r"^[\w .:/-]{1,40}$", re.UNICODE)


@dataclass
class Metadados:
    lote: str
    modelo_placa: str
    turno: str
    posto: str
    etapa_origem: str | None = None
    data_hora_producao: str | None = None
    simulado: bool = False

    def validar(self) -> "Metadados":
        for nome in ("lote", "modelo_placa", "turno", "posto"):
            valor = (getattr(self, nome) or "").strip()
            if not valor:
                raise ValueError(f"Metadado obrigatório ausente: {nome}")
            if not _CAMPO.match(valor):
                raise ValueError(f"Metadado inválido em '{nome}'")
            setattr(self, nome, valor)
        if self.etapa_origem is not None:
            self.etapa_origem = self.etapa_origem.strip() or None
        return self

    def to_dict(self) -> dict:
        return asdict(self)


def ler_codigo_qr(texto: str) -> Metadados:
    """Interpreta o conteúdo de um QR no formato 'LOTE;MODELO;TURNO;POSTO[;ETAPA]'."""
    partes = [p.strip() for p in texto.split(";")]
    if len(partes) < 4:
        raise ValueError("QR inválido: esperado LOTE;MODELO;TURNO;POSTO[;ETAPA]")
    return Metadados(partes[0], partes[1], partes[2], partes[3], partes[4] if len(partes) > 4 else None).validar()


def simular(modelo_placa: str = "HRIPCB", rng: random.Random | None = None) -> Metadados:
    rng = rng or random.Random()
    agora = datetime.now(timezone.utc)
    return Metadados(
        lote=f"L{agora:%y%m}-{rng.randint(1, 40):03d}",
        modelo_placa=modelo_placa,
        turno=rng.choice(TURNOS),
        posto=f"P{rng.randint(1, 3):02d}",
        etapa_origem=rng.choice(ETAPAS_ORIGEM),
        data_hora_producao=agora.isoformat(timespec="seconds"),
        simulado=True,
    )
