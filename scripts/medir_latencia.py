"""Seção 10, aspecto 3 – Velocidade de processamento (Critério 3: média < 5 s por placa).

Mede a latência PONTA A PONTA do serviço (decodificação, pré-processamento, YOLO, anomalias,
anotação e gravação em banco/disco) no computador de teste do grupo, frente à janela de ~30 s.
Usa um banco temporário: não polui o banco do posto.

Uso:
  python scripts/medir_latencia.py --imagens datasets/pcb/test/images --n 50 --modelo-placa HRIPCB
"""
from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

import numpy as np
from _comum import RAIZ, listar_imagens, salvar_json

from app.config import carregar
from app.metadata import simular
from app.service import ServicoInspecao


def main():
    cfg = carregar()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--imagens", required=True, type=Path)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--modelo-placa", default="HRIPCB")
    ap.add_argument("--saida", type=Path, default=RAIZ / "resultados" / "latencia.json")
    a = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        cfg.banco = Path(tmp) / "lat.db"
        cfg.pasta_imagens = Path(tmp) / "img"
        srv = ServicoInspecao(cfg)
        if not srv.detector.disponivel:
            raise SystemExit(f"Detector indisponível: {srv.detector.motivo_indisponivel}")
        lista = listar_imagens(a.imagens)[: a.n + 1]
        srv.inspecionar(lista[0].read_bytes(), simular(a.modelo_placa), "BENCH")  # aquecimento
        tempos = []
        for p in lista[1:]:
            t0 = time.perf_counter()
            srv.inspecionar(p.read_bytes(), simular(a.modelo_placa), "BENCH")
            tempos.append(time.perf_counter() - t0)
    t = np.array(tempos)
    res = {"n": len(t), "media_s": float(t.mean()), "mediana_s": float(np.median(t)), "p95_s": float(np.percentile(t, 95)),
           "max_s": float(t.max()), "janela_linha_s": cfg.janela_linha_s,
           "C3_latencia_<_5s": bool(t.mean() < cfg.latencia_alvo_s)}
    print(f"Latência ponta a ponta: média {res['media_s']:.2f}s · p95 {res['p95_s']:.2f}s · máx {res['max_s']:.2f}s "
          f"→ Critério 3 {'ATENDIDO' if res['C3_latencia_<_5s'] else 'NÃO atendido'}")
    salvar_json(res, a.saida)


if __name__ == "__main__":
    main()
