"""Bloco 2 – Detector de Anomalias (não supervisionado).

Compara a placa inspecionada com placas conformes do mesmo modelo e sinaliza
desvios inéditos ou raros que não constam nas 6 classes do YOLO
(Seção 8, componente 3). Treinado APENAS com imagens normais, como em
Bergmann et al. (2019) e Zou et al. (2022); validado nas categorias PCB1–PCB4
do VisA (scripts/ajustar_anomalias.py e scripts/avaliar_robustez.py).

Método (baseline leve, roda em CPU, sem GPU):
  1. A imagem 600×600 é dividida em patches (janela 32 px, passo 16 px).
  2. Cada patch vira um vetor de características: média e desvio no espaço Lab,
     histograma de orientação de gradiente (8 bins) e densidade de bordas.
  3. "Memory bank" posicional: para cada célula guardam-se as características
     das placas conformes na mesma célula e nas 8 vizinhas (tolera pequeno
     desalinhamento).
  4. Score de cada célula = distância ao vizinho mais próximo no banco.
     Score da imagem = maior score de célula. Região = células acima do limiar.
  5. O limiar é calibrado nas próprias normais (quantil alto, validação cruzada
     simples), sem precisar de exemplos rotulados de cada falha.

A troca por um método profundo (ex.: PatchCore via anomalib) é possível sem
mudar o restante do sistema, pois a interface é `pontuar(bgr) -> ResultadoAnomalia`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

JANELA = 32
PASSO = 16
N_ORIENT = 8


@dataclass
class ResultadoAnomalia:
    score: float                 # score da imagem (maior célula), normalizado pelo limiar (>1 = anômalo)
    anomala: bool
    regioes: list[tuple[int, int, int, int]]  # caixas (x1, y1, x2, y2) em px da imagem 600×600
    mapa: np.ndarray             # mapa de scores por célula (normalizado pelo limiar)


def _grade(tamanho: int) -> list[int]:
    return list(range(0, tamanho - JANELA + 1, PASSO))


def extrair_caracteristicas(bgr: np.ndarray) -> np.ndarray:
    """Retorna tensor (linhas, colunas, d) com as características de cada patch."""
    h, w = bgr.shape[:2]
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32) / 255.0
    cinza = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    gx = cv2.Sobel(cinza, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(cinza, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx * gx + gy * gy)
    ang = (np.arctan2(gy, gx) + np.pi) / (2 * np.pi)  # [0,1]
    bins = np.minimum((ang * N_ORIENT).astype(np.int32), N_ORIENT - 1)
    bordas = (mag > 0.25).astype(np.float32)

    # Imagens integrais para médias rápidas por janela
    def integral(x: np.ndarray) -> np.ndarray:
        return cv2.integral(x.astype(np.float64))

    def soma_janela(ii: np.ndarray, y: int, x: int) -> float:
        return ii[y + JANELA, x + JANELA] - ii[y, x + JANELA] - ii[y + JANELA, x] + ii[y, x]

    canais = [lab[:, :, c] for c in range(3)]
    ii_m = [integral(c) for c in canais]
    ii_q = [integral(c * c) for c in canais]
    ii_o = [integral(mag * (bins == b)) for b in range(N_ORIENT)]
    ii_b = integral(bordas)
    area = float(JANELA * JANELA)

    ys, xs = _grade(h), _grade(w)
    d = 3 * 2 + N_ORIENT + 1
    out = np.zeros((len(ys), len(xs), d), dtype=np.float32)
    for i, y in enumerate(ys):
        for j, x in enumerate(xs):
            v = []
            for c in range(3):
                m = soma_janela(ii_m[c], y, x) / area
                q = soma_janela(ii_q[c], y, x) / area
                v += [m, np.sqrt(max(q - m * m, 0.0))]
            hist = np.array([soma_janela(ii_o[b], y, x) for b in range(N_ORIENT)], dtype=np.float64)
            tot = hist.sum()
            v += list(hist / tot if tot > 1e-6 else hist)
            v.append(soma_janela(ii_b, y, x) / area)
            out[i, j] = v
    return out


class DetectorAnomalias:
    def __init__(self, banco: np.ndarray, media: np.ndarray, desvio: np.ndarray, limiar: float, modelo_placa: str):
        self.banco = banco            # (N_imgs, linhas, colunas, d) já padronizado
        self.media = media
        self.desvio = desvio
        self.limiar = float(limiar)
        self.modelo_placa = modelo_placa

    # ------------------------------------------------------------------ treino
    @classmethod
    def ajustar(cls, imagens_normais: list[np.ndarray], modelo_placa: str, frac_calibracao: float = 0.2,
                quantil: float = 0.99, semente: int = 0) -> "DetectorAnomalias":
        if len(imagens_normais) < 5:
            raise ValueError("São necessárias ao menos 5 imagens conformes.")
        rng = np.random.default_rng(semente)
        idx = rng.permutation(len(imagens_normais))
        n_cal = max(1, int(len(idx) * frac_calibracao))
        cal_idx, mem_idx = idx[:n_cal], idx[n_cal:]

        feats_mem = np.stack([extrair_caracteristicas(imagens_normais[k]) for k in mem_idx])
        media = feats_mem.reshape(-1, feats_mem.shape[-1]).mean(0)
        desvio = feats_mem.reshape(-1, feats_mem.shape[-1]).std(0) + 1e-6
        banco = (feats_mem - media) / desvio

        modelo = cls(banco, media, desvio, limiar=1.0, modelo_placa=modelo_placa)
        # Calibração: limiar = quantil dos scores máximos das normais separadas
        maximos = [modelo._mapa_bruto(imagens_normais[k]).max() for k in cal_idx]
        modelo.limiar = float(np.quantile(maximos, quantil)) * 1.05 if maximos else 1.0
        return modelo

    # --------------------------------------------------------------- inferência
    def _mapa_bruto(self, bgr: np.ndarray) -> np.ndarray:
        f = (extrair_caracteristicas(bgr) - self.media) / self.desvio
        L, C, _ = f.shape
        mapa = np.zeros((L, C), dtype=np.float32)
        for i in range(L):
            i0, i1 = max(0, i - 1), min(L, i + 2)
            for j in range(C):
                j0, j1 = max(0, j - 1), min(C, j + 2)
                viz = self.banco[:, i0:i1, j0:j1, :].reshape(-1, f.shape[-1])
                dif = viz - f[i, j]
                mapa[i, j] = float(np.sqrt(np.min(np.einsum("nd,nd->n", dif, dif))))
        return mapa

    def pontuar(self, bgr: np.ndarray) -> ResultadoAnomalia:
        mapa = self._mapa_bruto(bgr) / self.limiar
        score = float(mapa.max())
        regioes = _regioes(mapa > 1.0)
        return ResultadoAnomalia(score=score, anomala=score > 1.0, regioes=regioes, mapa=mapa)

    # -------------------------------------------------------------- persistência
    def salvar(self, caminho: Path) -> None:
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(caminho, banco=self.banco.astype(np.float16), media=self.media,
                            desvio=self.desvio, limiar=self.limiar, modelo_placa=self.modelo_placa)

    @classmethod
    def carregar(cls, caminho: Path) -> "DetectorAnomalias":
        z = np.load(caminho, allow_pickle=False)
        return cls(z["banco"].astype(np.float32), z["media"], z["desvio"], float(z["limiar"]),
                   str(z["modelo_placa"]))


def _regioes(mascara: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Converte a máscara de células anômalas em caixas na imagem."""
    if not mascara.any():
        return []
    n, rot = cv2.connectedComponents(mascara.astype(np.uint8), connectivity=8)
    caixas = []
    for k in range(1, n):
        ii, jj = np.where(rot == k)
        y1, x1 = int(ii.min()) * PASSO, int(jj.min()) * PASSO
        y2, x2 = int(ii.max()) * PASSO + JANELA, int(jj.max()) * PASSO + JANELA
        caixas.append((x1, y1, x2, y2))
    return caixas


class RepositorioAnomalias:
    """Carrega o detector de anomalias do modelo de placa informado nos metadados."""

    def __init__(self, pasta: Path):
        self.pasta = Path(pasta)
        self._cache: dict[str, DetectorAnomalias] = {}

    def modelos_disponiveis(self) -> list[str]:
        if not self.pasta.exists():
            return []
        return sorted(p.stem for p in self.pasta.glob("*.npz"))

    def obter(self, modelo_placa: str) -> DetectorAnomalias | None:
        chave = modelo_placa.lower()
        if chave in self._cache:
            return self._cache[chave]
        caminho = self.pasta / f"{chave}.npz"
        if not caminho.exists():
            return None
        det = DetectorAnomalias.carregar(caminho)
        self._cache[chave] = det
        return det
