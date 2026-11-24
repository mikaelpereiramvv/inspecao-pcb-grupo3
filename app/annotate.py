"""Imagem anotada para o inspetor (Seção 7a).

Acessibilidade (Seção 12, risco daltonismo/baixa visão): cada marcação usa
CONTORNO GEOMÉTRICO + RÓTULO TEXTUAL numerado, nunca apenas cor:
  - defeito conhecido com confiança >= limiar: retângulo com linha contínua grossa;
  - defeito com confiança < limiar: retângulo tracejado;
  - anomalia: retângulo com cantos em "L" e rótulo "ANOMALIA".
O texto é desenhado sobre fundo sólido para manter contraste.
"""
from __future__ import annotations

import cv2
import numpy as np

from .config import ROTULOS_PT
from .detector import Deteccao

PRETO = (0, 0, 0)
BRANCO = (255, 255, 255)
# Cores apenas como reforço; a informação está na forma e no texto.
COR_FORTE = (40, 40, 220)     # vermelho (BGR)
COR_FRACA = (0, 170, 255)     # laranja
COR_ANOM = (200, 60, 160)     # roxo


def _tracejado(img, p1, p2, cor, esp, traco=8):
    x1, y1 = p1
    x2, y2 = p2
    for (a, b) in [((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)), ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1))]:
        dist = int(np.hypot(b[0] - a[0], b[1] - a[1]))
        for s in range(0, dist, traco * 2):
            t0, t1 = s / max(dist, 1), min(s + traco, dist) / max(dist, 1)
            pa = (int(a[0] + (b[0] - a[0]) * t0), int(a[1] + (b[1] - a[1]) * t0))
            pb = (int(a[0] + (b[0] - a[0]) * t1), int(a[1] + (b[1] - a[1]) * t1))
            cv2.line(img, pa, pb, cor, esp, cv2.LINE_AA)


def _cantos(img, p1, p2, cor, esp):
    x1, y1 = p1
    x2, y2 = p2
    L = max(6, min(x2 - x1, y2 - y1) // 3)
    for (cx, cy, dx, dy) in [(x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)]:
        cv2.line(img, (cx, cy), (cx + dx * L, cy), cor, esp, cv2.LINE_AA)
        cv2.line(img, (cx, cy), (cx, cy + dy * L), cor, esp, cv2.LINE_AA)


def _rotulo(img, texto, x, y, cor):
    fonte = cv2.FONT_HERSHEY_SIMPLEX
    escala, esp = 0.45, 1
    (w, h), base = cv2.getTextSize(texto, fonte, escala, esp)
    y = max(y, h + 4)
    x = min(max(x, 0), img.shape[1] - w - 4)
    cv2.rectangle(img, (x, y - h - 4), (x + w + 4, y + base - 2), cor, -1)
    cv2.putText(img, texto, (x + 2, y - 2), fonte, escala, BRANCO, esp, cv2.LINE_AA)


def anotar(bgr: np.ndarray, deteccoes: list[Deteccao], regioes_anomalia: list[tuple[int, int, int, int]],
           limiar_revisar: float) -> np.ndarray:
    img = bgr.copy()
    n = 0
    for d in deteccoes:
        n += 1
        p1, p2 = (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2))
        forte = d.confianca >= limiar_revisar
        cor = COR_FORTE if forte else COR_FRACA
        # borda preta por baixo garante contraste em qualquer fundo
        if forte:
            cv2.rectangle(img, p1, p2, PRETO, 4, cv2.LINE_AA)
            cv2.rectangle(img, p1, p2, cor, 2, cv2.LINE_AA)
        else:
            _tracejado(img, p1, p2, PRETO, 4)
            _tracejado(img, p1, p2, cor, 2)
        nome = ROTULOS_PT.get(d.classe, d.classe)
        _rotulo(img, f"{n}. {nome} {d.confianca:.0%}", p1[0], p1[1] - 3, cor)
    for (x1, y1, x2, y2) in regioes_anomalia:
        n += 1
        _cantos(img, (x1, y1), (x2, y2), PRETO, 5)
        _cantos(img, (x1, y1), (x2, y2), COR_ANOM, 3)
        _rotulo(img, f"{n}. ANOMALIA", x1, y1 - 3, COR_ANOM)
    return img
