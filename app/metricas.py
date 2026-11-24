"""Métricas da Estratégia de Avaliação (Seção 10, aspecto 1 e 2).

Sensibilidade (recall), precisão, mAP@50 e mAP@50:95 por classe.
Obs.: o documento escreve "mAP@50-90"; a métrica padrão da literatura (COCO e
Ultralytics, usada por Mitoso e Melo, 2025) é mAP@50:95, adotada aqui.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

LIMIARES_IOU = np.round(np.arange(0.5, 0.96, 0.05), 2)


@dataclass
class Caixa:
    classe: str
    x1: float
    y1: float
    x2: float
    y2: float
    confianca: float = 1.0


def iou(a: Caixa, b: Caixa) -> float:
    x1, y1 = max(a.x1, b.x1), max(a.y1, b.y1)
    x2, y2 = min(a.x2, b.x2), min(a.y2, b.y2)
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    ua = (a.x2 - a.x1) * (a.y2 - a.y1) + (b.x2 - b.x1) * (b.y2 - b.y1) - inter
    return inter / ua if ua > 0 else 0.0


def ler_rotulos_yolo(caminho, largura: int, altura: int, classes: list[str]) -> list[Caixa]:
    caixas = []
    try:
        texto = open(caminho, encoding="utf-8").read()
    except FileNotFoundError:
        return caixas
    for linha in texto.splitlines():
        p = linha.split()
        if len(p) < 5:
            continue
        k, cx, cy, w, h = int(p[0]), *map(float, p[1:5])
        caixas.append(Caixa(classes[k], (cx - w / 2) * largura, (cy - h / 2) * altura,
                            (cx + w / 2) * largura, (cy + h / 2) * altura))
    return caixas


def _casar(gts: list[Caixa], preds: list[Caixa], limiar_iou: float) -> tuple[list[bool], int]:
    """Casamento guloso por confiança (mesma classe). Retorna acerto de cada predição e nº de GTs."""
    usados = [False] * len(gts)
    acertos = []
    for p in sorted(preds, key=lambda c: c.confianca, reverse=True):
        melhor, idx = 0.0, -1
        for i, g in enumerate(gts):
            if usados[i] or g.classe != p.classe:
                continue
            v = iou(p, g)
            if v > melhor:
                melhor, idx = v, i
        if idx >= 0 and melhor >= limiar_iou:
            usados[idx] = True
            acertos.append(True)
        else:
            acertos.append(False)
    return acertos, len(gts)


def average_precision(confs: list[float], acertos: list[bool], n_gt: int) -> float:
    """AP com interpolação de 101 pontos (COCO)."""
    if n_gt == 0:
        return float("nan")
    if not confs:
        return 0.0
    ordem = np.argsort(-np.asarray(confs))
    tp = np.asarray(acertos, dtype=float)[ordem]
    tpc, fpc = np.cumsum(tp), np.cumsum(1 - tp)
    rec = tpc / n_gt
    prec = tpc / np.maximum(tpc + fpc, 1e-9)
    prec = np.maximum.accumulate(prec[::-1])[::-1]
    pontos = np.linspace(0, 1, 101)
    idx = np.searchsorted(rec, pontos, side="left")
    return float(np.mean([prec[i] if i < len(prec) else 0.0 for i in idx]))


def avaliar(amostras: list[tuple[list[Caixa], list[Caixa]]], classes: list[str], conf_operacao: float) -> dict:
    """amostras = [(gabarito, predições), ...] por imagem.

    - recall/precisão: no limiar de confiança de operação, IoU ≥ 0,5
    - AP50 / AP50:95: sobre todas as predições (curva completa)
    """
    res = {"por_classe": {}, "conf_operacao": conf_operacao}
    tot_tp = tot_fp = tot_gt = 0
    ap50s, ap5095s = [], []
    for c in classes:
        confs_por_iou = {t: ([], []) for t in LIMIARES_IOU}
        n_gt = 0
        tp = fp = 0
        for gts, preds in amostras:
            g = [x for x in gts if x.classe == c]
            p = [x for x in preds if x.classe == c]
            n_gt += len(g)
            for t in LIMIARES_IOU:
                ac, _ = _casar(g, p, float(t))
                ordenadas = sorted(p, key=lambda x: x.confianca, reverse=True)
                confs_por_iou[t][0].extend(x.confianca for x in ordenadas)
                confs_por_iou[t][1].extend(ac)
            p_op = [x for x in p if x.confianca >= conf_operacao]
            ac, _ = _casar(g, p_op, 0.5)
            tp += sum(ac)
            fp += len(ac) - sum(ac)
        aps = [average_precision(*confs_por_iou[t], n_gt) for t in LIMIARES_IOU]
        ap50, ap5095 = aps[0], float(np.nanmean(aps)) if n_gt else float("nan")
        res["por_classe"][c] = {
            "gabarito": n_gt, "vp": tp, "fp": fp, "fn": n_gt - tp,
            "recall": tp / n_gt if n_gt else None,
            "precisao": tp / (tp + fp) if (tp + fp) else None,
            "ap50": ap50, "ap50_95": ap5095,
        }
        if n_gt:
            ap50s.append(ap50)
            ap5095s.append(ap5095)
        tot_tp += tp
        tot_fp += fp
        tot_gt += n_gt
    res["geral"] = {
        "gabarito": tot_gt, "vp": tot_tp, "fp": tot_fp, "fn": tot_gt - tot_tp,
        "recall": tot_tp / tot_gt if tot_gt else None,
        "precisao": tot_tp / (tot_tp + tot_fp) if (tot_tp + tot_fp) else None,
        "map50": float(np.mean(ap50s)) if ap50s else None,
        "map50_95": float(np.mean(ap5095s)) if ap5095s else None,
    }
    return res


def criterios(res: dict, latencia_media_s: float | None = None) -> dict:
    """Critérios de sucesso 1–3 propostos pelo grupo (Seção 11)."""
    g = res["geral"]
    out = {
        "C1_recall_>=_90%": None if g["recall"] is None else g["recall"] >= 0.90,
        "C2_precisao_>=_70%": None if g["precisao"] is None else g["precisao"] >= 0.70,
    }
    if latencia_media_s is not None:
        out["C3_latencia_<_5s"] = latencia_media_s < 5.0
    return out
