import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app import curation, dashboard, lgpd
from app.anomaly import DetectorAnomalias, RepositorioAnomalias
from app.detector import Deteccao
from app.metadata import Metadados
from app.service import ErroFluxo, ServicoInspecao
from app.suggestion import sugerir

from .conftest import DetectorFalso, placa_sintetica, png


def meta(lote="L1", turno="A", etapa="Furação"):
    return Metadados(lote, "HRIPCB", turno, "P01", etapa)


def test_regra_sugestao():
    forte = Deteccao("short", 0.9, 0, 0, 10, 10)
    fraca = Deteccao("spur", 0.5, 0, 0, 10, 10)
    assert sugerir([forte, fraca], None, 0.7).codigo == "REPROVAR"
    assert sugerir([fraca], None, 0.7).codigo == "REVISAR"
    assert sugerir([], None, 0.7).codigo == "APROVAR"


def test_inspecao_registra_e_nao_decide_sozinho(cfg, det_padrao):
    s = ServicoInspecao(cfg, detector=det_padrao)
    r = s.inspecionar(png(placa_sintetica()), meta(), "INSP-01")
    assert r.sugestao == "REPROVAR" and r.modo == "assistido"
    linha = s.con.execute("SELECT * FROM inspecoes").fetchone()
    assert linha["decisao"] is None                       # sistema nunca decide
    assert linha["inspetor_pseudonimo"] != "INSP-01"     # LGPD: código não é gravado em claro
    assert s.storage.caminho(r.id, "original").exists() and s.storage.caminho(r.id, "anotada").exists()


def test_contingencia_quando_detector_indisponivel(cfg):
    s = ServicoInspecao(cfg, detector=DetectorFalso(disponivel=False))
    r = s.inspecionar(png(placa_sintetica()), meta(), "INSP-01")
    assert r.modo == "contingencia" and r.sugestao is None
    s.decidir(r.id, "APROVAR", "INSP-01")                 # a linha não para
    with pytest.raises(ErroFluxo):
        s.reprocessar(r.id)


def test_revisar_1_no_maximo_uma_vez(cfg, det_padrao):
    s = ServicoInspecao(cfg, detector=det_padrao)
    r = s.inspecionar(png(placa_sintetica()), meta(), "INSP-01")
    r2 = s.reprocessar(r.id)
    assert r2.reprocessamentos == 1
    assert det_padrao.chamadas[-1] < cfg.conf_minima_deteccao  # modo "ambos" reduz o limiar
    with pytest.raises(ErroFluxo):
        s.reprocessar(r.id)
    with pytest.raises(ErroFluxo):
        s.decidir(r.id, "REVISAR_1", "INSP-01")


def test_decisao_gera_correcoes_e_e_imutavel(cfg, det_padrao):
    s = ServicoInspecao(cfg, detector=det_padrao)
    r = s.inspecionar(png(placa_sintetica()), meta(), "INSP-01")
    out = s.decidir(r.id, "REPROVAR", "INSP-01", descartadas=[1], reclassificadas={0: "mouse_bite"},
                    adicionadas=[{"x1": 10, "y1": 10, "x2": 40, "y2": 40, "classe": "open_circuit"}])
    assert out == {"id": r.id, "decisao": "REPROVAR", "defeitos_registrados": 2, "correcoes": 3}
    tipos = sorted(x[0] for x in s.con.execute("SELECT tipo FROM defeitos"))
    assert tipos == ["mouse_bite", "open_circuit"]
    with pytest.raises(ErroFluxo):
        s.decidir(r.id, "APROVAR", "INSP-01")


def test_indice_invalido_rejeitado(cfg, det_padrao):
    s = ServicoInspecao(cfg, detector=det_padrao)
    r = s.inspecionar(png(placa_sintetica()), meta(), "INSP-01")
    with pytest.raises(ErroFluxo):
        s.decidir(r.id, "REPROVAR", "INSP-01", descartadas=[9])


def test_banco_disco_sem_orfaos(cfg, det_padrao, monkeypatch):
    s = ServicoInspecao(cfg, detector=det_padrao)
    s.con.execute("DROP TABLE eventos")   # força falha no meio da transação
    with pytest.raises(sqlite3.OperationalError):
        s.inspecionar(png(placa_sintetica()), meta(), "INSP-01")
    assert s.con.execute("SELECT COUNT(*) FROM inspecoes").fetchone()[0] == 0
    assert not list(cfg.pasta_imagens.rglob("*.png"))


def test_anonimizacao_90_dias(cfg, det_padrao):
    s = ServicoInspecao(cfg, detector=det_padrao)
    r = s.inspecionar(png(placa_sintetica()), meta(), "INSP-01")
    futuro = datetime.now(timezone.utc) + timedelta(days=91)
    assert lgpd.anonimizar_vencidos(s.con, 90, agora=futuro) == 1
    assert s.con.execute("SELECT inspetor_pseudonimo FROM inspecoes WHERE id=?", (r.id,)).fetchone()[0] is None


def test_codigo_com_dado_pessoal_rejeitado():
    with pytest.raises(ValueError):
        lgpd.validar_codigo("João da Silva")


def test_painel_sem_inspetor_e_alerta_reincidencia(cfg):
    det = DetectorFalso([Deteccao("short", 0.95, 100, 100, 140, 130)])
    s = ServicoInspecao(cfg, detector=det)
    for _ in range(4):
        r = s.inspecionar(png(placa_sintetica()), meta(lote="L7", etapa="Corrosão/gravação"), "INSP-01")
        s.decidir(r.id, "REPROVAR", "INSP-01")
    res = dashboard.resumo(s.con)
    assert res["total_inspecoes"] == 4 and res["taxa_reprovacao"] == 1.0
    assert "inspetor" not in str(res).lower()
    al = dashboard.alertas_reincidencia(s.con, 3, 0.2)
    assert al and al[0]["lote"] == "L7" and al[0]["etapa_origem"] == "Corrosão/gravação"


def test_curadoria_exporta_somente_aprovadas(cfg, det_padrao):
    s = ServicoInspecao(cfg, detector=det_padrao)
    r = s.inspecionar(png(placa_sintetica()), meta(), "INSP-01")
    s.decidir(r.id, "REPROVAR", "INSP-01", descartadas=[1],
              adicionadas=[{"x1": 10, "y1": 10, "x2": 40, "y2": 40, "classe": "open_circuit"}])
    pend = curation.listar(s.con)
    assert len(pend) == 2
    # com pendência, nada é exportado
    curation.curar(s.con, pend[0]["id"], True)
    assert curation.exportar_yolo(s.con, s.storage, cfg.pasta_curadoria)["imagens"] == 0
    curation.curar(s.con, pend[1]["id"], False)
    out = curation.exportar_yolo(s.con, s.storage, cfg.pasta_curadoria)
    assert out["imagens"] == 1
    linhas = (cfg.pasta_curadoria / "labels" / f"{r.id}.txt").read_text().split()
    assert linhas  # contém a caixa do YOLO mantida conforme a curadoria
    with pytest.raises(curation.ErroCuradoria):
        curation.curar(s.con, pend[0]["id"], True)


def test_detector_anomalias(cfg, tmp_path):
    normais = [placa_sintetica(k) for k in range(12)]
    det = DetectorAnomalias.ajustar(normais, "sint")
    assert not det.pontuar(placa_sintetica(99)).anomala
    r = det.pontuar(placa_sintetica(99, defeito=True))
    assert r.anomala
    x1, y1, x2, y2 = r.regioes[0]
    assert x1 <= 330 <= x2 and y1 <= 300 <= y2
    det.salvar(cfg.pasta_anomalia / "sint.npz")
    s = ServicoInspecao(cfg, detector=DetectorFalso([]), anomalias=RepositorioAnomalias(cfg.pasta_anomalia))
    m = meta(); m.modelo_placa = "sint"
    res = s.inspecionar(png(placa_sintetica(5, defeito=True)), m, "INSP-01")
    assert res.sugestao == "REVISAR" and res.regioes_anomalia


def test_fora_do_contexto(cfg, det_padrao):
    cfg.modelos_placa_validados = ("HRIPCB",)
    s = ServicoInspecao(cfg, detector=det_padrao)
    m = meta(); m.modelo_placa = "OUTRA"
    r = s.inspecionar(png(placa_sintetica()), m, "INSP-01")
    assert r.fora_contexto and r.avisos


def test_placa_grande_usa_blocos(cfg):
    import numpy as np
    from app.detector import detectar_em_blocos

    class DetBloco(DetectorFalso):
        def detectar(self, bgr, conf_minima):
            self.chamadas.append(bgr.shape)
            return [Deteccao("short", 0.9, 10, 10, 30, 30)]

    d = DetBloco()
    grande = np.zeros((1600, 3000, 3), np.uint8)
    res = detectar_em_blocos(d, grande, 0.25, 600)
    assert all(sh[:2] == (600, 600) for sh in d.chamadas) and len(d.chamadas) > 10
    assert len(res) == len(d.chamadas)  # caixas em posições distintas não são fundidas

    s = ServicoInspecao(cfg, detector=DetBloco())
    import cv2
    img = cv2.resize(placa_sintetica(), (3000, 1600))
    r = s.inspecionar(png(img), meta(), "INSP-01")
    assert all(0 <= x.x2 <= 600 and 0 <= x.y2 <= 600 for x in r.deteccoes)
    assert s.storage.caminho(r.id, "exibicao").exists()
