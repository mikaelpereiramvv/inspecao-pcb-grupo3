"""Utilidades compartilhadas pelos scripts (permite rodar `python scripts/x.py` da raiz)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

EXT_IMG = {".jpg", ".jpeg", ".png", ".bmp"}


def listar_imagens(pasta: Path) -> list[Path]:
    return sorted(p for p in Path(pasta).rglob("*") if p.suffix.lower() in EXT_IMG)


def rotulo_de(imagem: Path, pasta_imagens: Path, pasta_rotulos: Path) -> Path:
    return (Path(pasta_rotulos) / imagem.relative_to(pasta_imagens)).with_suffix(".txt")


def salvar_json(obj, caminho: Path) -> None:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print(f"Resultado salvo em {caminho}")


def fmt(v) -> str:
    return "—" if v is None or v != v else f"{v * 100:.1f}%"


def aplicar_ruido(bgr, tipo: str, intensidade: float = 0.02, semente: int = 0):
    """Protocolo de robustez de Dias et al. (2025), parâmetro 0,02.

    gaussiano   : ruído aditivo N(0, σ²) com variância = intensidade, na escala [0, 1]
                  (mesma convenção de skimage.util.random_noise(mode='gaussian', var=...))
    sal_pimenta : fração `intensidade` dos pixels vira preto ou branco (amount=...)
    """
    import numpy as np

    rng = np.random.default_rng(semente)
    x = bgr.astype(np.float32) / 255.0
    if tipo == "gaussiano":
        x = x + rng.normal(0.0, intensidade ** 0.5, x.shape).astype(np.float32)
    elif tipo == "sal_pimenta":
        m = rng.random(x.shape[:2])
        x[m < intensidade / 2] = 0.0
        x[(m >= intensidade / 2) & (m < intensidade)] = 1.0
    elif tipo != "nenhum":
        raise ValueError(tipo)
    return (np.clip(x, 0, 1) * 255).round().astype(np.uint8)
