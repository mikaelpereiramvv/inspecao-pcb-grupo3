"""Teste controlado com voluntários (Seção 10, aspectos 4 e 5; Critérios 4 e 5).

O participante (identificado só por código, ex.: V01) clica onde vê defeitos em cada placa,
com limite de 30 s. Na condição COM assistente, as sugestões aparecem como caixas.
O gabarito nunca é enviado ao navegador.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

_ID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


class ErroTeste(ValueError):
    pass


def _validar(nome: str, valor: str) -> str:
    if not _ID.match(valor or ""):
        raise ErroTeste(f"{nome} inválido (use letras, números, '-' ou '_').")
    return valor


def carregar_sessao(pasta: Path, sessao: str) -> dict:
    arq = Path(pasta) / _validar("Sessão", sessao) / "sessao.json"
    if not arq.exists():
        raise ErroTeste("Sessão não encontrada. Gere-a com scripts/teste_humano/gerar_sessao.py")
    return json.loads(arq.read_text(encoding="utf-8"))


def grupo_do_participante(participante: str) -> str:
    """Alterna A/B pelo número do código (V01→A, V02→B…), garantindo contrabalanceamento."""
    nums = re.findall(r"\d+", participante)
    return "A" if not nums or int(nums[-1]) % 2 == 1 else "B"


def plano_publico(plano: dict, participante: str) -> dict:
    _validar("Participante", participante)
    grupo = grupo_do_participante(participante)
    por_id = {p["id"]: p for p in plano["placas"]}
    itens = []
    for id_placa, com in plano["grupos"][grupo]:
        p = por_id[id_placa]
        itens.append({"id": id_placa, "arquivo": p["arquivo"], "largura": p["largura"], "altura": p["altura"],
                      "com_assistente": com, "sugestoes": p["sugestoes"] if com else []})
    return {"sessao": plano["sessao"], "participante": participante, "grupo": grupo,
            "limite_s": plano["limite_s"], "limiar_revisar": plano.get("limiar_revisar", 0.7), "placas": itens}


def caminho_imagem(pasta: Path, sessao: str, arquivo: str) -> Path:
    _validar("Sessão", sessao)
    if not re.match(r"^\d{2}\.png$", arquivo):
        raise ErroTeste("Arquivo inválido.")
    return Path(pasta) / sessao / "img" / arquivo


def salvar_resultado(pasta: Path, sessao: str, dados: dict) -> Path:
    plano = carregar_sessao(pasta, sessao)
    participante = _validar("Participante", str(dados.get("participante", "")))
    nota = dados.get("usabilidade")
    if not isinstance(nota, int) or not 1 <= nota <= 5:
        raise ErroTeste("Nota de usabilidade deve ser de 1 a 5.")
    ids = {p["id"] for p in plano["placas"]}
    respostas = dados.get("respostas") or []
    for r in respostas:
        if r.get("id") not in ids or not isinstance(r.get("cliques"), list):
            raise ErroTeste("Resposta malformada.")
    destino = Path(pasta) / sessao / "resultados" / f"{participante}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    registro = {
        "participante": participante, "grupo": grupo_do_participante(participante),
        "concluido_em": datetime.now(timezone.utc).isoformat(),
        "usabilidade": nota, "notou_sugestao_errada": dados.get("notou_sugestao_errada"),
        "comentario": (dados.get("comentario") or "")[:1000],
        "respostas": [{"id": r["id"], "tempo_s": float(r.get("tempo_s", 0)),
                       "esgotou": bool(r.get("esgotou")),
                       "cliques": [[float(x), float(y)] for x, y in r["cliques"]][:50]} for r in respostas],
    }
    destino.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino
