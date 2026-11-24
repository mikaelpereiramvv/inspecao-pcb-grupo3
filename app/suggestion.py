"""Regra de sugestão exibida ao inspetor (Seção 7a: Aprovar, Revisar ou Reprovar).

O sistema NUNCA aprova sozinho (Seção 12, risco "falso negativo"): a saída
desta regra é apenas uma SUGESTÃO; a decisão registrada é sempre a do inspetor.

Regra (o limiar é decisão aberta 9.1, padrão 70%):
  - REPROVAR: há pelo menos um defeito conhecido com confiança >= limiar.
  - REVISAR : há defeito com confiança < limiar, OU o detector de anomalias
              sinalizou desvio inédito (anomalia não tem classe → precisa de olho humano).
  - APROVAR : nenhum defeito e nenhuma anomalia.
"""
from __future__ import annotations

from dataclasses import dataclass

from .anomaly import ResultadoAnomalia
from .detector import Deteccao


@dataclass
class Sugestao:
    codigo: str          # APROVAR | REVISAR | REPROVAR
    motivo: str          # texto acessível explicando o porquê


def sugerir(deteccoes: list[Deteccao], anomalia: ResultadoAnomalia | None, limiar_revisar: float) -> Sugestao:
    fortes = [d for d in deteccoes if d.confianca >= limiar_revisar]
    fracas = [d for d in deteccoes if d.confianca < limiar_revisar]
    if fortes:
        return Sugestao(
            "REPROVAR",
            f"{len(fortes)} defeito(s) com confiança ≥ {limiar_revisar:.0%}. Confira os contornos antes de decidir.",
        )
    motivos = []
    if fracas:
        motivos.append(f"{len(fracas)} possível(is) defeito(s) com confiança < {limiar_revisar:.0%}")
    if anomalia is not None and anomalia.anomala:
        motivos.append(f"{len(anomalia.regioes)} região(ões) fora do padrão das placas conformes")
    if motivos:
        return Sugestao("REVISAR", "; ".join(motivos) + ". Olhe as áreas indicadas.")
    return Sugestao(
        "APROVAR",
        "Nenhum defeito conhecido nem anomalia apontados. A decisão final é sua: faça a verificação visual.",
    )
