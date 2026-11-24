"""Seção 10, aspecto 1 – Desempenho técnico (Critérios 1 e 2 da Seção 11).

Executa o modelo sobre as placas inteiras de teste (não vistas no treino) e compara com o gabarito:
recall, precisão, mAP@50 e mAP@50:95 por classe. Placas grandes são analisadas em blocos 600×600.

Uso:
  python scripts/avaliar_deteccao.py --imagens datasets/pcb/test/images --rotulos datasets/pcb/test/labels
  (opcional) --ruido gaussiano|sal_pimenta --intensidade 0.02   → usado por avaliar_robustez.py
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
from _comum import RAIZ, aplicar_ruido, fmt, listar_imagens, rotulo_de, salvar_json

from app.config import CLASSES, ROTULOS_PT, carregar
from app.detector import DetectorYOLO, detectar_em_blocos
from app.metricas import Caixa, avaliar, criterios, ler_rotulos_yolo


def rodar(imagens: Path, rotulos: Path, pesos: Path, conf_operacao: float, ruido: str = "nenhum",
          intensidade: float = 0.02, limite: int | None = None, dispositivo: str | None = None) -> dict:
    det = DetectorYOLO(pesos, dispositivo=dispositivo)
    amostras, tempos = [], []
    lista = listar_imagens(imagens)[:limite] if limite else listar_imagens(imagens)
    if not lista:
        raise SystemExit(f"Nenhuma imagem em {imagens}")
    for k, p in enumerate(lista):
        img = cv2.imread(str(p))
        if img is None:
            continue
        if ruido != "nenhum":
            img = aplicar_ruido(img, ruido, intensidade, semente=k)
        h, w = img.shape[:2]
        gts = ler_rotulos_yolo(rotulo_de(p, imagens, rotulos), w, h, CLASSES)
        t0 = time.perf_counter()
        preds = detectar_em_blocos(det, img, conf_minima=0.001)  # curva completa para o mAP
        tempos.append(time.perf_counter() - t0)
        amostras.append((gts, [Caixa(d.classe, d.x1, d.y1, d.x2, d.y2, d.confianca) for d in preds]))
    res = avaliar(amostras, CLASSES, conf_operacao)
    res["imagens"] = len(amostras)
    res["ruido"] = {"tipo": ruido, "intensidade": intensidade}
    res["tempo_medio_inferencia_s"] = sum(tempos) / len(tempos)
    res["criterios"] = criterios(res)
    return res


def imprimir(res: dict) -> None:
    print(f"\nImagens: {res['imagens']} | ruído: {res['ruido']['tipo']} | conf. de operação: {res['conf_operacao']}")
    print(f"{'Classe':<22}{'GT':>6}{'Recall':>9}{'Precisão':>10}{'AP50':>8}{'AP50:95':>9}")
    for c, m in res["por_classe"].items():
        print(f"{ROTULOS_PT[c]:<22}{m['gabarito']:>6}{fmt(m['recall']):>9}{fmt(m['precisao']):>10}"
              f"{fmt(m['ap50']):>8}{fmt(m['ap50_95']):>9}")
    g = res["geral"]
    print(f"{'GERAL':<22}{g['gabarito']:>6}{fmt(g['recall']):>9}{fmt(g['precisao']):>10}"
          f"{fmt(g['map50']):>8}{fmt(g['map50_95']):>9}")
    for k, v in res["criterios"].items():
        print(f"  {k}: {'ATENDIDO' if v else 'NÃO atendido' if v is not None else 'sem dados'}")


def main():
    cfg = carregar()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--imagens", required=True, type=Path)
    ap.add_argument("--rotulos", required=True, type=Path)
    ap.add_argument("--pesos", type=Path, default=cfg.pesos_yolo)
    ap.add_argument("--conf-operacao", type=float, default=cfg.conf_minima_deteccao)
    ap.add_argument("--ruido", choices=("nenhum", "gaussiano", "sal_pimenta"), default="nenhum")
    ap.add_argument("--intensidade", type=float, default=0.02)
    ap.add_argument("--limite", type=int, default=None)
    ap.add_argument("--dispositivo", default=None)
    ap.add_argument("--saida", type=Path, default=RAIZ / "resultados" / "deteccao.json")
    a = ap.parse_args()
    res = rodar(a.imagens, a.rotulos, a.pesos, a.conf_operacao, a.ruido, a.intensidade, a.limite, a.dispositivo)
    imprimir(res)
    salvar_json(res, a.saida)


if __name__ == "__main__":
    main()
