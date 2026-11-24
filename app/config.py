"""Configuração central do protótipo.

Todos os valores marcados como "PROPOSTA DO GRUPO" vêm do documento
"Projeto Final – Primeira Versão Integrada" (Grupo 3) e podem ser ajustados
por variáveis de ambiente, porque várias delas ainda são decisões abertas
(Seção 9.1 do documento).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _env_float(nome: str, padrao: float) -> float:
    return float(os.environ.get(nome, padrao))


def _env_int(nome: str, padrao: int) -> int:
    return int(os.environ.get(nome, padrao))


# Os 6 tipos de defeito do HRIPCB (Huang; Wei, 2019), usados por Mitoso e Melo (2025).
# Ordem = índice de classe no formato YOLO.
CLASSES: list[str] = [
    "missing_hole",
    "mouse_bite",
    "open_circuit",
    "short",
    "spur",
    "spurious_copper",
]

ROTULOS_PT: dict[str, str] = {
    "missing_hole": "Furo ausente",
    "mouse_bite": "Mordida de rato",
    "open_circuit": "Circuito aberto",
    "short": "Curto-circuito",
    "spur": "Rebarba",
    "spurious_copper": "Cobre espúrio",
    "anomalia": "Anomalia (desvio inédito)",
}

# Sugestões exibidas ao inspetor (Seção 7: Aprovar, Revisar ou Reprovar)
SUGESTOES = ("APROVAR", "REVISAR", "REPROVAR")

# Decisões humanas (Seção 8, componente 4: Aprovar / Rev. 1ª / Rev. 2ª / Reprovar)
DECISOES = ("APROVAR", "REVISAR_1", "REVISAR_2", "REPROVAR")

PERFIS = ("inspetor", "supervisor", "tecnico")


@dataclass
class Config:
    # --- Captura / pré-processamento (Seção 8, componente 1) ---
    tamanho_imagem: int = field(default_factory=lambda: _env_int("PCB_TAMANHO", 600))

    # --- Detector (Seção 8, componente 2) ---
    # Decisão aberta 9.1: YOLOv10 Small otimizado ou variante padrão (YOLOv8n/v11s).
    # Qualquer peso compatível com a biblioteca Ultralytics funciona aqui.
    pesos_yolo: Path = field(
        default_factory=lambda: Path(os.environ.get("PCB_PESOS_YOLO", RAIZ / "modelos" / "yolo_pcb.pt"))
    )
    # Placas maiores que 1,5× o tamanho padrão são analisadas em blocos 600×600 na resolução original
    inferencia_blocos: bool = field(default_factory=lambda: os.environ.get("PCB_BLOCOS", "1") != "0")
    conf_minima_deteccao: float = field(default_factory=lambda: _env_float("PCB_CONF_MIN", 0.25))

    # Decisão aberta 9.1: limiar abaixo do qual o sistema sugere "Revisar" (ex.: < 70%).
    limiar_revisar: float = field(default_factory=lambda: _env_float("PCB_LIMIAR_REVISAR", 0.70))

    # --- Detector de anomalias (Seção 8, componente 3) ---
    # Um arquivo <modelo_da_placa>.npz por modelo de placa (ex.: pcb1.npz ... pcb4.npz do VisA)
    pasta_anomalia: Path = field(
        default_factory=lambda: Path(os.environ.get("PCB_PASTA_ANOMALIA", RAIZ / "modelos" / "anomalia"))
    )

    # Risco "uso fora do contexto" (Seção 12): modelos de placa validados.
    # Vazio = qualquer modelo com detector treinado. Ex.: PCB_MODELOS_VALIDADOS="HRIPCB,pcb1,pcb2"
    modelos_placa_validados: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            m.strip() for m in os.environ.get("PCB_MODELOS_VALIDADOS", "").split(",") if m.strip()
        )
    )

    # --- "Revisar 1ª vez" (Seção 12, risco novo da Arq. v1) ---
    reprocessamento_max: int = 1           # no máximo 1 tentativa
    reprocessamento_timeout_s: float = 3.0  # < 3 s
    # Decisão aberta 9.1: "contraste", "limiar" ou "ambos".
    reprocessamento_modo: str = field(default_factory=lambda: os.environ.get("PCB_REPROC_MODO", "ambos"))
    reprocessamento_reducao_limiar: float = 0.10

    # --- Latência (Critério 3) ---
    latencia_alvo_s: float = 5.0
    janela_linha_s: float = 30.0

    # --- Armazenamento (Seção 8, componente 5) ---
    banco: Path = field(default_factory=lambda: Path(os.environ.get("PCB_BANCO", RAIZ / "data" / "inspecoes.db")))
    pasta_imagens: Path = field(default_factory=lambda: Path(os.environ.get("PCB_IMAGENS", RAIZ / "data" / "imagens")))

    # --- LGPD (Seção 5) ---
    dias_anonimizacao: int = field(default_factory=lambda: _env_int("PCB_DIAS_ANONIMIZACAO", 90))
    segredo_pseudonimo: str = field(
        default_factory=lambda: os.environ.get("PCB_SEGREDO", "troque-este-segredo-em-producao")
    )

    # --- Painel / alertas de reincidência (Seção 7c) ---
    alerta_min_ocorrencias: int = field(default_factory=lambda: _env_int("PCB_ALERTA_MIN", 3))
    alerta_taxa_minima: float = field(default_factory=lambda: _env_float("PCB_ALERTA_TAXA", 0.20))

    # --- Acesso por perfil ---
    chave_sessao: str = field(default_factory=lambda: os.environ.get("PCB_CHAVE_SESSAO", "dev-chave-sessao"))
    pin_supervisor: str = field(default_factory=lambda: os.environ.get("PCB_PIN_SUPERVISOR", "1234"))
    pin_tecnico: str = field(default_factory=lambda: os.environ.get("PCB_PIN_TECNICO", "4321"))

    # Pasta onde a curadoria exporta o novo dataset para retreinamento
    pasta_curadoria: Path = field(
        default_factory=lambda: Path(os.environ.get("PCB_CURADORIA", RAIZ / "data" / "curadoria_yolo"))
    )

    # Teste controlado com voluntários (Seção 10, aspectos 4 e 5)
    pasta_teste: Path = field(
        default_factory=lambda: Path(os.environ.get("PCB_TESTE", RAIZ / "data" / "teste_humano"))
    )


def carregar() -> Config:
    return Config()
