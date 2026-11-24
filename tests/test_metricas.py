from app.metricas import Caixa, avaliar, criterios

CL = ["short", "spur"]


def test_metricas_perfeitas_e_com_erros():
    gt = [Caixa("short", 0, 0, 10, 10), Caixa("spur", 50, 50, 60, 60)]
    perf = avaliar([(gt, [Caixa(c.classe, c.x1, c.y1, c.x2, c.y2, 0.9) for c in gt])], CL, 0.25)
    assert perf["geral"]["recall"] == 1 and perf["geral"]["precisao"] == 1 and perf["geral"]["map50"] == 1
    preds = [Caixa("short", 0, 0, 10, 10, 0.9), Caixa("short", 100, 100, 110, 110, 0.8)]  # 1 VP, 1 FP, 1 FN
    r = avaliar([(gt, preds)], CL, 0.25)
    assert r["geral"]["recall"] == 0.5 and r["geral"]["precisao"] == 0.5
    assert criterios(r, 2.0) == {"C1_recall_>=_90%": False, "C2_precisao_>=_70%": False, "C3_latencia_<_5s": True}
    # abaixo da confiança de operação não conta para recall/precisão
    r2 = avaliar([(gt, [Caixa("short", 0, 0, 10, 10, 0.1)])], CL, 0.25)
    assert r2["geral"]["recall"] == 0 and r2["por_classe"]["short"]["ap50"] == 1
