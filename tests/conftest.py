import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Config  # noqa: E402
from app.detector import Deteccao, DetectorIndisponivel  # noqa: E402


def placa_sintetica(semente: int = 0, defeito: bool = False, tamanho: int = 600) -> np.ndarray:
    """Placa verde com trilhas e furos regulares; o 'defeito' é uma mancha de cobre espúrio."""
    rng = np.random.default_rng(semente)
    img = np.full((tamanho, tamanho, 3), (40, 110, 30), np.uint8)
    for y in range(60, tamanho, 80):
        cv2.line(img, (30, y), (tamanho - 30, y), (60, 170, 200), 6)
    for x in range(60, tamanho, 80):
        for y in range(60, tamanho, 80):
            cv2.circle(img, (x, y), 9, (200, 200, 200), -1)
            cv2.circle(img, (x, y), 4, (20, 20, 20), -1)
    img = np.clip(img.astype(np.int16) + rng.integers(-3, 4, img.shape), 0, 255).astype(np.uint8)
    if defeito:
        cv2.ellipse(img, (330, 300), (25, 14), 30, 0, 360, (60, 170, 200), -1)
    return img


def png(img: np.ndarray) -> bytes:
    return cv2.imencode(".png", img)[1].tobytes()


class DetectorFalso:
    def __init__(self, deteccoes=None, disponivel=True):
        self._det = deteccoes if deteccoes is not None else []
        self._disp = disponivel
        self.chamadas = []

    @property
    def disponivel(self):
        return self._disp

    motivo_indisponivel = "modelo de teste indisponível"

    def detectar(self, bgr, conf_minima):
        self.chamadas.append(conf_minima)
        if not self._disp:
            raise DetectorIndisponivel(self.motivo_indisponivel)
        return [d for d in self._det if d.confianca >= conf_minima]


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.banco = tmp_path / "t.db"
    c.pasta_imagens = tmp_path / "img"
    c.pasta_anomalia = tmp_path / "anom"
    c.pasta_curadoria = tmp_path / "cur"
    c.segredo_pseudonimo = "segredo-teste"
    c.modelos_placa_validados = ()
    return c


@pytest.fixture
def det_padrao():
    return DetectorFalso([
        Deteccao("short", 0.91, 100, 100, 140, 130),
        Deteccao("spur", 0.45, 300, 300, 330, 320),
    ])
