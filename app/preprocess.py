"""Bloco 2 – Pré-processamento (Figura 1 / Arquitetura v1).

- Redimensionamento para 600×600 px (padronização da Seção 8, componente 1)
- Normalização
- Verificação de integridade da imagem
- Ajuste de contraste usado no "Revisar – 1ª vez" (Decisão aberta 9.1)
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


class ImagemInvalida(ValueError):
    """A imagem recebida não pode ser usada na inspeção."""


@dataclass
class ImagemPreparada:
    bgr: np.ndarray            # imagem 600×600 em BGR (uint8) usada pelos modelos e pela anotação
    escala_x: float            # fator para voltar as coordenadas à imagem original
    escala_y: float
    largura_original: int
    altura_original: int


def decodificar(conteudo: bytes) -> np.ndarray:
    """Decodifica bytes (JPEG/PNG/BMP) em matriz BGR, validando a integridade."""
    if not conteudo:
        raise ImagemInvalida("Arquivo vazio.")
    arr = np.frombuffer(conteudo, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ImagemInvalida("Arquivo não é uma imagem válida ou está corrompido.")
    return img


def verificar_integridade(img: np.ndarray) -> None:
    if img.ndim != 3 or img.shape[2] != 3:
        raise ImagemInvalida("A imagem deve ter 3 canais de cor.")
    h, w = img.shape[:2]
    if h < 64 or w < 64:
        raise ImagemInvalida(f"Resolução muito baixa ({w}×{h}).")
    # Imagem praticamente uniforme (câmera tampada, quadro preto/branco)
    if float(img.std()) < 2.0:
        raise ImagemInvalida("Imagem sem conteúdo (uniforme). Verifique câmera e iluminação.")


def preparar(img: np.ndarray, tamanho: int = 600) -> ImagemPreparada:
    verificar_integridade(img)
    h, w = img.shape[:2]
    redim = cv2.resize(img, (tamanho, tamanho), interpolation=cv2.INTER_AREA)
    return ImagemPreparada(
        bgr=redim,
        escala_x=w / tamanho,
        escala_y=h / tamanho,
        largura_original=w,
        altura_original=h,
    )


def normalizar(img: np.ndarray) -> np.ndarray:
    """Retorna float32 em [0, 1] (usado pelo detector de anomalias)."""
    return img.astype(np.float32) / 255.0


def ajustar_contraste(img: np.ndarray) -> np.ndarray:
    """CLAHE no canal L (Lab). Usado no reprocessamento do 'Revisar – 1ª vez'."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    l2 = clahe.apply(l)
    return cv2.cvtColor(cv2.merge((l2, a, b)), cv2.COLOR_LAB2BGR)


def codificar_png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("Falha ao codificar imagem.")
    return buf.tobytes()
