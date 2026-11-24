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
