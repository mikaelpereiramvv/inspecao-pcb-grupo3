"""Orquestração do fluxo da Arquitetura v1:
Entrada → Pré-processamento → YOLO + Anomalias → Interface/Decisão Humana →
Banco + Storage → Painel e Curadoria.

Princípios garantidos aqui:
  * Nenhuma decisão é automatizada sem validação do inspetor (nota da Figura 1).
  * Contingência manual se o detector estiver indisponível (Seção 12).
  * "Revisar – 1ª vez": no máximo 1 reprocessamento, em < 3 s (Seção 12).
  * Imagem gravada com ID único antes do commit no banco (Seção 12).
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from datetime import datetime, timezone

import cv2
import numpy as np

from . import lgpd, preprocess
from .annotate import anotar
from .anomaly import RepositorioAnomalias, ResultadoAnomalia
from .config import CLASSES, Config
from .db import conectar
from .detector import Deteccao, DetectorDefeitos, DetectorIndisponivel, DetectorYOLO, detectar_em_blocos
from .metadata import Metadados
from .storage import Storage
from .suggestion import Sugestao, sugerir

DECISOES_FINAIS = ("APROVAR", "REVISAR_2", "REPROVAR")


class ErroFluxo(ValueError):
    """Operação inválida no fluxo de inspeção (mensagem exibível ao usuário)."""


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sobreposicao(a: tuple, b: tuple) -> float:
    """Fração da área de `a` coberta por `b`."""
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area = max(1e-6, (a[2] - a[0]) * (a[3] - a[1]))
    return inter / area


@dataclass
class ResultadoInspecao:
    id: str
    modo: str                                   # assistido | contingencia
    sugestao: str | None
    motivo: str
    deteccoes: list[Deteccao]
    regioes_anomalia: list[tuple[int, int, int, int]]
    anomalia_score: float | None
    latencia_ms: float
    reprocessamentos: int
    fora_contexto: bool
    avisos: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "modo": self.modo,
            "sugestao": self.sugestao,
            "motivo": self.motivo,
            "deteccoes": [d.to_dict() for d in self.deteccoes],
            "regioes_anomalia": [list(r) for r in self.regioes_anomalia],
            "anomalia_score": None if self.anomalia_score is None else round(self.anomalia_score, 3),
            "latencia_ms": round(self.latencia_ms, 1),
            "reprocessamentos": self.reprocessamentos,
            "fora_contexto": self.fora_contexto,
            "avisos": self.avisos,
        }


class ServicoInspecao:
    def __init__(self, cfg: Config, detector: DetectorDefeitos | None = None,
                 anomalias: RepositorioAnomalias | None = None, con=None, storage: Storage | None = None):
        self.cfg = cfg
        self.detector = detector if detector is not None else DetectorYOLO(cfg.pesos_yolo, cfg.tamanho_imagem)
        self.anomalias = anomalias if anomalias is not None else RepositorioAnomalias(cfg.pasta_anomalia)
        self.con = con if con is not None else conectar(cfg.banco)
        self.storage = storage if storage is not None else Storage(cfg.pasta_imagens)
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=2)

    # ---------------------------------------------------------------- estado
    def status(self) -> dict:
        disp = self.detector.disponivel
        return {
            "detector_disponivel": disp,
            "motivo_indisponivel": None if disp else getattr(self.detector, "motivo_indisponivel", None),
            "modelos_anomalia": self.anomalias.modelos_disponiveis(),
            "limiar_revisar": self.cfg.limiar_revisar,
            "reprocessamento_modo": self.cfg.reprocessamento_modo,
            "classes": CLASSES,
        }

    # ------------------------------------------------------------ análise
    def _analisar(self, original: np.ndarray, modelo_placa: str, limiar: float, conf_minima: float,
                  contraste: bool = False):
        """Retorna (detecções no referencial 600×600, anomalia, sugestão, imagem de exibição)."""
        prep = preprocess.preparar(original, self.cfg.tamanho_imagem)
        exib = prep.bgr
        h, w = original.shape[:2]
        if self.cfg.inferencia_blocos and max(h, w) > 1.5 * self.cfg.tamanho_imagem:
            entrada = preprocess.ajustar_contraste(original) if contraste else original
            brutas = detectar_em_blocos(self.detector, entrada, conf_minima, self.cfg.tamanho_imagem)
            deteccoes = [Deteccao(d.classe, d.confianca, d.x1 / prep.escala_x, d.y1 / prep.escala_y,
                                  d.x2 / prep.escala_x, d.y2 / prep.escala_y) for d in brutas]
        else:
            entrada = preprocess.ajustar_contraste(exib) if contraste else exib
            deteccoes = self.detector.detectar(entrada, conf_minima)
        anomalia: ResultadoAnomalia | None = None
        det_anom = self.anomalias.obter(modelo_placa)
        if det_anom is not None:
            anomalia = det_anom.pontuar(exib)
            # Regiões já explicadas por um defeito conhecido não são repetidas como anomalia
            caixas = [(d.x1, d.y1, d.x2, d.y2) for d in deteccoes]
            anomalia.regioes = [r for r in anomalia.regioes
                                if not any(_sobreposicao(r, c) > 0.3 or _sobreposicao(c, r) > 0.5 for c in caixas)]
            anomalia.anomala = bool(anomalia.regioes)
        sug = sugerir(deteccoes, anomalia, limiar)
        return deteccoes, anomalia, sug, exib

    def inspecionar(self, conteudo: bytes, meta: Metadados, codigo_inspetor: str) -> ResultadoInspecao:
        meta.validar()
        pseudo = lgpd.pseudonimizar(codigo_inspetor, self.cfg.segredo_pseudonimo)
        img = preprocess.decodificar(conteudo)
        exib = preprocess.preparar(img, self.cfg.tamanho_imagem).bgr  # valida integridade antes de tudo

        avisos: list[str] = []
        fora_contexto = bool(self.cfg.modelos_placa_validados) and \
            meta.modelo_placa.lower() not in {m.lower() for m in self.cfg.modelos_placa_validados}
        if fora_contexto:
            avisos.append(
                f"Modelo de placa '{meta.modelo_placa}' não foi validado para este assistente. "
                "As marcações podem não ser confiáveis: faça a inspeção manual completa."
            )

        t0 = time.perf_counter()
        modo = "assistido"
        deteccoes: list[Deteccao] = []
        anomalia = None
        try:
            deteccoes, anomalia, sug, exib = self._analisar(img, meta.modelo_placa, self.cfg.limiar_revisar,
                                                            self.cfg.conf_minima_deteccao)
        except DetectorIndisponivel as e:
            modo = "contingencia"
            sug = Sugestao(None, "Assistente indisponível – siga o procedimento de inspeção visual manual.")
            avisos.append(str(e))
        latencia_ms = (time.perf_counter() - t0) * 1000
        if modo == "assistido" and latencia_ms > self.cfg.latencia_alvo_s * 1000:
            avisos.append(f"Processamento levou {latencia_ms/1000:.1f}s (meta < {self.cfg.latencia_alvo_s:.0f}s).")
        if modo == "assistido" and anomalia is None:
            avisos.append("Sem detector de anomalias para este modelo de placa: apenas os 6 defeitos conhecidos são verificados.")

        regioes = anomalia.regioes if anomalia else []
        anotada = anotar(exib, deteccoes, regioes, self.cfg.limiar_revisar)

        id_insp = self.storage.novo_id()
        with self._lock, self.storage.transacao(id_insp):
            # 1º disco (com fsync), 2º banco – ver storage.py
            self.storage.gravar(id_insp, "original", preprocess.codificar_png(img))
            self.storage.gravar(id_insp, "exibicao", preprocess.codificar_png(exib))
            self.storage.gravar(id_insp, "anotada", preprocess.codificar_png(anotada))
            with self.con:
                self.con.execute(
                    """INSERT INTO inspecoes (id, criado_em, lote, modelo_placa, turno, posto, etapa_origem,
                       data_hora_producao, metadados_simulados, inspetor_pseudonimo, modo, fora_contexto,
                       sugestao, motivo_sugestao, limiar_usado, anomalia_score, latencia_ms)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (id_insp, _agora(), meta.lote, meta.modelo_placa, meta.turno, meta.posto, meta.etapa_origem,
                     meta.data_hora_producao, int(meta.simulado), pseudo, modo, int(fora_contexto),
                     sug.codigo, sug.motivo, self.cfg.limiar_revisar,
                     None if anomalia is None else anomalia.score, latencia_ms),
                )
                self._gravar_deteccoes(id_insp, 0, deteccoes, regioes)
                self._evento(id_insp, "inspecao_criada", {"modo": modo, "avisos": avisos})

        return ResultadoInspecao(id_insp, modo, sug.codigo, sug.motivo, deteccoes, regioes,
                                 None if anomalia is None else anomalia.score, latencia_ms, 0, fora_contexto, avisos)

    # -------------------------------------------------- Revisar – 1ª vez
    def reprocessar(self, id_insp: str) -> ResultadoInspecao:
        """Reanálise rápida (máx. 1x, < 3 s) com ajuste de contraste e/ou limiar (Decisão aberta 9.1)."""
        linha = self._obter(id_insp)
        if linha["decisao"] is not None:
            raise ErroFluxo("Esta inspeção já tem decisão final.")
        if linha["modo"] != "assistido":
            raise ErroFluxo("Reprocessamento indisponível em modo de contingência.")
        if linha["reprocessamentos"] >= self.cfg.reprocessamento_max:
            raise ErroFluxo("Limite de 1 reprocessamento atingido. Decida: Aprovar, Revisar 2ª vez ou Reprovar.")

        modo = self.cfg.reprocessamento_modo
        original = cv2.imdecode(np.frombuffer(self.storage.ler(id_insp, "original"), np.uint8), cv2.IMREAD_COLOR)
        contraste = modo in ("contraste", "ambos")
        limiar = self.cfg.limiar_revisar
        conf_min = self.cfg.conf_minima_deteccao
        if modo in ("limiar", "ambos"):
            conf_min = max(0.05, conf_min - self.cfg.reprocessamento_reducao_limiar)

        t0 = time.perf_counter()
        fut = self._executor.submit(self._analisar, original, linha["modelo_placa"], limiar, conf_min, contraste)
        try:
            deteccoes, anomalia, sug, exib = fut.result(timeout=self.cfg.reprocessamento_timeout_s)
        except FuturesTimeout:
            with self._lock, self.con:
                self.con.execute("UPDATE inspecoes SET reprocessamentos = reprocessamentos + 1 WHERE id = ?", (id_insp,))
                self._evento(id_insp, "reprocessamento_timeout", {"limite_s": self.cfg.reprocessamento_timeout_s})
            raise ErroFluxo("Reanálise excedeu 3 s. Encaminhe para 'Revisar – 2ª vez' se a dúvida persistir.")
        except DetectorIndisponivel as e:
            raise ErroFluxo(f"Assistente indisponível: {e}")
        latencia_ms = (time.perf_counter() - t0) * 1000

        regioes = anomalia.regioes if anomalia else []
        anotada = anotar(exib, deteccoes, regioes, limiar)  # marcações sobre a imagem sem ajuste
        with self._lock:
            self.storage.gravar(id_insp, "anotada", preprocess.codificar_png(anotada))
            with self.con:
                self.con.execute(
                    "UPDATE inspecoes SET reprocessamentos = reprocessamentos + 1, sugestao = ?, motivo_sugestao = ?, "
                    "anomalia_score = ? WHERE id = ?",
                    (sug.codigo, sug.motivo, None if anomalia is None else anomalia.score, id_insp),
                )
                self._gravar_deteccoes(id_insp, 1, deteccoes, regioes)
                self._evento(id_insp, "revisar_1_reprocessado", {"modo": modo, "latencia_ms": round(latencia_ms, 1)})
        return ResultadoInspecao(id_insp, "assistido", sug.codigo, sug.motivo, deteccoes, regioes,
                                 None if anomalia is None else anomalia.score, latencia_ms,
                                 linha["reprocessamentos"] + 1, bool(linha["fora_contexto"]), [])

    # --------------------------------------------------------- decisão humana
    def decidir(self, id_insp: str, decisao: str, codigo_inspetor: str, descartadas: list[int] | None = None,
                reclassificadas: dict[int, str] | None = None, adicionadas: list[dict] | None = None,
                observacao: str | None = None) -> dict:
        """Registra a decisão FINAL do inspetor e as correções feitas sobre a sugestão.

        descartadas     : índices das detecções do sistema marcadas como "não é defeito" (falso positivo)
        reclassificadas : {índice: nova_classe} (classe errada)
        adicionadas     : caixas desenhadas pelo inspetor para defeitos não apontados
        """
        decisao = (decisao or "").upper()
        if decisao == "REVISAR_1":
            raise ErroFluxo("'Revisar – 1ª vez' solicita reprocessamento; use o botão de reanálise.")
        if decisao not in DECISOES_FINAIS:
            raise ErroFluxo(f"Decisão inválida: {decisao}")
        pseudo = lgpd.pseudonimizar(codigo_inspetor, self.cfg.segredo_pseudonimo)
        descartadas = set(descartadas or [])
        reclassificadas = {int(k): v for k, v in (reclassificadas or {}).items()}
        adicionadas = adicionadas or []
        if observacao is not None:
            observacao = observacao.strip()[:500] or None

        linha = self._obter(id_insp)
        if linha["decisao"] is not None:
            raise ErroFluxo("Esta inspeção já foi decidida; o registro é imutável.")

        sistema = self.deteccoes_vigentes(id_insp)
        for i in list(descartadas) + list(reclassificadas):
            if not 0 <= i < len(sistema):
                raise ErroFluxo(f"Índice de detecção inválido: {i}")
        tipos_validos = set(CLASSES) | {"anomalia", "outro"}
        for i, c in reclassificadas.items():
            if c not in tipos_validos:
                raise ErroFluxo(f"Classe inválida: {c}")

        finais: list[dict] = []
        correcoes: list[tuple] = []
        agora = _agora()
        for i, d in enumerate(sistema):
            if i in descartadas:
                correcoes.append(("falso_positivo", d["tipo"], d["tipo"], d))
                continue
            tipo = d["tipo"]
            if i in reclassificadas and reclassificadas[i] != tipo:
                correcoes.append(("classe_errada", reclassificadas[i], tipo, d))
                tipo = reclassificadas[i]
            finais.append({**d, "tipo": tipo})
        for a in adicionadas:
            c = a.get("classe", "outro")
            if c not in tipos_validos:
                raise ErroFluxo(f"Classe inválida: {c}")
            caixa = {k: float(a[k]) for k in ("x1", "y1", "x2", "y2")}
            if caixa["x2"] <= caixa["x1"] or caixa["y2"] <= caixa["y1"]:
                raise ErroFluxo("Caixa desenhada inválida.")
            d = {"tipo": c, "origem": "inspetor", "confianca": None, **caixa}
            finais.append(d)
            correcoes.append(("defeito_nao_apontado", c, None, d))

        if decisao == "APROVAR" and finais:
            # Não bloqueia (a decisão é humana), mas fica registrado para auditoria.
            observacao = ((observacao + " | ") if observacao else "") + \
                f"Aprovada com {len(finais)} marcação(ões) mantida(s) pelo inspetor."

        with self._lock, self.con:
            self.con.execute(
                "UPDATE inspecoes SET decisao = ?, decidido_em = ?, observacao = ? WHERE id = ? AND decisao IS NULL",
                (decisao, agora, observacao, id_insp),
            )
            for d in finais:
                self.con.execute(
                    "INSERT INTO defeitos (inspecao_id, tipo, x1, y1, x2, y2, origem, confianca) VALUES (?,?,?,?,?,?,?,?)",
                    (id_insp, d["tipo"], d["x1"], d["y1"], d["x2"], d["y2"], d["origem"], d.get("confianca")),
                )
            for tipo_corr, classe, original, d in correcoes:
                self.con.execute(
                    """INSERT INTO correcoes (inspecao_id, criado_em, inspetor_pseudonimo, tipo_correcao, classe,
                       classe_original, x1, y1, x2, y2) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (id_insp, agora, pseudo, tipo_corr, classe, original, d["x1"], d["y1"], d["x2"], d["y2"]),
                )
            self._evento(id_insp, "decisao_final", {"decisao": decisao, "sugestao": linha["sugestao"],
                                                    "n_correcoes": len(correcoes)})
        return {"id": id_insp, "decisao": decisao, "defeitos_registrados": len(finais), "correcoes": len(correcoes)}

    # ----------------------------------------------------------- utilitários
    def deteccoes_vigentes(self, id_insp: str) -> list[dict]:
        """Detecções da última rodada (0 = original, 1 = após 'Revisar 1ª')."""
        rod = self.con.execute("SELECT COALESCE(MAX(rodada), 0) FROM deteccoes WHERE inspecao_id = ?",
                               (id_insp,)).fetchone()[0]
        rows = self.con.execute(
            "SELECT origem, tipo, confianca, x1, y1, x2, y2 FROM deteccoes WHERE inspecao_id = ? AND rodada = ? ORDER BY id",
            (id_insp, rod),
        ).fetchall()
        return [dict(r) for r in rows]

    def _obter(self, id_insp: str):
        linha = self.con.execute("SELECT * FROM inspecoes WHERE id = ?", (id_insp,)).fetchone()
        if linha is None:
            raise ErroFluxo("Inspeção não encontrada.")
        return linha

    def obter(self, id_insp: str) -> dict:
        d = dict(self._obter(id_insp))
        d.pop("inspetor_pseudonimo", None)  # nunca exposto pela API
        d["deteccoes"] = self.deteccoes_vigentes(id_insp)
        return d

    def _gravar_deteccoes(self, id_insp: str, rodada: int, deteccoes: list[Deteccao], regioes) -> None:
        for d in deteccoes:
            self.con.execute(
                "INSERT INTO deteccoes (inspecao_id, rodada, origem, tipo, confianca, x1, y1, x2, y2) VALUES (?,?,?,?,?,?,?,?,?)",
                (id_insp, rodada, "yolo", d.classe, d.confianca, d.x1, d.y1, d.x2, d.y2),
            )
        for (x1, y1, x2, y2) in regioes:
            self.con.execute(
                "INSERT INTO deteccoes (inspecao_id, rodada, origem, tipo, confianca, x1, y1, x2, y2) VALUES (?,?,?,?,?,?,?,?,?)",
                (id_insp, rodada, "anomalia", "anomalia", None, x1, y1, x2, y2),
            )

    def _evento(self, id_insp: str | None, evento: str, detalhes: dict) -> None:
        self.con.execute("INSERT INTO eventos (inspecao_id, em, evento, detalhes) VALUES (?,?,?,?)",
                         (id_insp, _agora(), evento, json.dumps(detalhes, ensure_ascii=False)))
