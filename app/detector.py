"""Bloco 2 – Detector de Defeitos Conhecidos (YOLO).

Localiza (bounding boxes) e classifica os 6 tipos de defeito do HRIPCB e
calcula o nível de confiança. Entrada: imagem pré-processada. Saída: caixas,
classe e confiança (Seção 8, componente 2).

A variante exata do YOLO é decisão aberta (Seção 9.1): qualquer peso treinado
com a biblioteca Ultralytics (YOLOv10s, YOLOv8n, YOLO11s...) é aceito. O
script `scripts/treinar_yolo.py` gera esse peso.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from .config import CLASSES


class DetectorIndisponivel(RuntimeError):
    """Modelo ausente ou falhou. A interface entra em contingência manual (Seção 12)."""


@dataclass
class Deteccao:
    classe: str
    confianca: float
    x1: float
    y1: float
    x2: float
    y2: float
    origem: str = "yolo"  # "yolo", "anomalia" ou "inspetor" (correção humana)

    @property
    def centro(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["confianca"] = round(float(self.confianca), 4)
        for k in ("x1", "y1", "x2", "y2"):
            d[k] = round(float(d[k]), 1)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Deteccao":
        return cls(
            classe=str(d["classe"]),
            confianca=float(d.get("confianca", 1.0)),
            x1=float(d["x1"]),
            y1=float(d["y1"]),
            x2=float(d["x2"]),
            y2=float(d["y2"]),
            origem=str(d.get("origem", "yolo")),
        )


class DetectorDefeitos(Protocol):
    def detectar(self, bgr: np.ndarray, conf_minima: float) -> list[Deteccao]: ...

    @property
    def disponivel(self) -> bool: ...


class DetectorYOLO:
    """Adaptador para modelos Ultralytics. Carregamento preguiçoso e thread-safe."""

    def __init__(self, pesos: Path, tamanho: int = 600, dispositivo: str | None = None):
        self.pesos = Path(pesos)
        self.tamanho = tamanho
        self.dispositivo = dispositivo
        self._modelo = None
        self._erro: str | None = None
        self._lock = threading.Lock()

    def _carregar(self):
        if self._modelo is not None:
            return self._modelo
        with self._lock:
            if self._modelo is not None:
                return self._modelo
            if not self.pesos.exists():
                self._erro = f"Pesos do modelo não encontrados em {self.pesos}"
                raise DetectorIndisponivel(self._erro)
            try:
                from ultralytics import YOLO  # import tardio: dependência pesada
            except ImportError as e:  # pragma: no cover - depende do ambiente
                self._erro = "Biblioteca 'ultralytics' não instalada (veja requirements-ml.txt)"
                raise DetectorIndisponivel(self._erro) from e
            self._modelo = YOLO(str(self.pesos))
            return self._modelo

    @property
    def disponivel(self) -> bool:
        try:
            self._carregar()
            return True
        except DetectorIndisponivel:
            return False

    @property
    def motivo_indisponivel(self) -> str | None:
        return self._erro

    def detectar(self, bgr: np.ndarray, conf_minima: float) -> list[Deteccao]:
        modelo = self._carregar()
        try:
            resultados = modelo.predict(
                bgr, imgsz=self.tamanho, conf=conf_minima, verbose=False, device=self.dispositivo
            )
        except Exception as e:  # pragma: no cover
            raise DetectorIndisponivel(f"Falha na inferência: {e}") from e
        saida: list[Deteccao] = []
        nomes = getattr(modelo, "names", None) or dict(enumerate(CLASSES))
        for r in resultados:
            if r.boxes is None:
                continue
            xyxy = r.boxes.xyxy.cpu().numpy()
            confs = r.boxes.conf.cpu().numpy()
            clss = r.boxes.cls.cpu().numpy().astype(int)
            for (x1, y1, x2, y2), c, k in zip(xyxy, confs, clss):
                nome = str(nomes.get(int(k), k)) if isinstance(nomes, dict) else str(nomes[int(k)])
                saida.append(Deteccao(nome, float(c), float(x1), float(y1), float(x2), float(y2)))
        saida.sort(key=lambda d: d.confianca, reverse=True)
        return saida


# ---------------------------------------------------------------------------
# Inferência em blocos (placas inteiras de alta resolução)
# ---------------------------------------------------------------------------
# As placas inteiras do HRIPCB têm ~3000×1600 px e defeitos de poucos pixels.
# Reduzir a placa inteira para 600×600 apagaria esses defeitos, então a placa
# é percorrida em blocos de 600×600 na resolução original (mesmo tamanho dos
# recortes de treino de Mitoso e Melo, 2025) e as caixas são unidas por NMS.

def _iou(a: Deteccao, b: Deteccao) -> float:
    x1, y1 = max(a.x1, b.x1), max(a.y1, b.y1)
    x2, y2 = min(a.x2, b.x2), min(a.y2, b.y2)
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    ua = (a.x2 - a.x1) * (a.y2 - a.y1) + (b.x2 - b.x1) * (b.y2 - b.y1) - inter
    return inter / ua if ua > 0 else 0.0


def nms(deteccoes: list[Deteccao], iou_max: float = 0.5) -> list[Deteccao]:
    mantidas: list[Deteccao] = []
    for d in sorted(deteccoes, key=lambda d: d.confianca, reverse=True):
        if all(d.classe != m.classe or _iou(d, m) < iou_max for m in mantidas):
            mantidas.append(d)
    return mantidas


def posicoes_blocos(total: int, bloco: int, passo: int) -> list[int]:
    if total <= bloco:
        return [0]
    pos = list(range(0, total - bloco + 1, passo))
    if pos[-1] != total - bloco:
        pos.append(total - bloco)
    return pos


def detectar_em_blocos(detector: DetectorDefeitos, bgr: np.ndarray, conf_minima: float, bloco: int = 600,
                       sobreposicao: float = 0.2) -> list[Deteccao]:
    """Detecta na resolução original, em blocos com sobreposição. Coordenadas na imagem original."""
    h, w = bgr.shape[:2]
    if h <= bloco and w <= bloco:
        return detector.detectar(bgr, conf_minima)
    passo = max(1, int(bloco * (1 - sobreposicao)))
    todas: list[Deteccao] = []
    for y in posicoes_blocos(h, bloco, passo):
        for x in posicoes_blocos(w, bloco, passo):
            recorte = bgr[y:y + bloco, x:x + bloco]
            for d in detector.detectar(np.ascontiguousarray(recorte), conf_minima):
                todas.append(Deteccao(d.classe, d.confianca, d.x1 + x, d.y1 + y, d.x2 + x, d.y2 + y, d.origem))
    return nms(todas)
