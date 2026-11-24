from fastapi.testclient import TestClient

from app.main import criar_app
from app.service import ServicoInspecao

from .conftest import placa_sintetica, png


def cliente(cfg, det):
    return TestClient(criar_app(cfg, ServicoInspecao(cfg, detector=det)))


def login(c, perfil, **kw):
    return c.post("/login", data={"perfil": perfil, **kw}, follow_redirects=False)


def test_fluxo_completo_e_perfis(cfg, det_padrao):
    c = cliente(cfg, det_padrao)
    assert c.get("/api/status").status_code == 401
    assert login(c, "inspetor", codigo="INSP-07").status_code == 303
    assert c.get("/inspetor").status_code == 200
    assert c.get("/api/painel").status_code == 403       # inspetor não vê painel
    meta = c.get("/api/metadados/simulados").json()
    assert meta["simulado"] is True
    r = c.post("/api/inspecoes", files={"imagem": ("p.png", png(placa_sintetica()), "image/png")},
               data={"lote": "L1", "modelo_placa": "HRIPCB", "turno": "A", "posto": "P01", "etapa_origem": "Furação"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["sugestao"] == "REPROVAR" and len(d["marcacoes"]) == 2
    assert c.get(f"/api/inspecoes/{d['id']}/imagem/anotada").headers["content-type"] == "image/png"
    assert c.post(f"/api/inspecoes/{d['id']}/reprocessar").status_code == 200
    assert c.post(f"/api/inspecoes/{d['id']}/reprocessar").status_code == 409
    ok = c.post(f"/api/inspecoes/{d['id']}/decisao", json={"decisao": "REPROVAR", "descartadas": [1]})
    assert ok.status_code == 200 and ok.json()["correcoes"] == 1
    assert "inspetor_pseudonimo" not in c.get(f"/api/inspecoes/{d['id']}").json()

    login(c, "supervisor", pin="errado")
    assert c.get("/api/painel").status_code == 401
    login(c, "supervisor", pin=cfg.pin_supervisor)
    p = c.get("/api/painel").json()
    assert p["total_inspecoes"] == 1
    assert c.get("/curadoria").status_code == 403

    login(c, "tecnico", pin=cfg.pin_tecnico)
    fila = c.get("/api/curadoria").json()
    assert len(fila) == 1
    assert c.post(f"/api/curadoria/{fila[0]['id']}", json={"aprovar": True}).status_code == 200
    assert c.post("/api/curadoria/exportar").json()["imagens"] == 1


def test_imagem_invalida(cfg, det_padrao):
    c = cliente(cfg, det_padrao)
    login(c, "inspetor", codigo="INSP-07")
    r = c.post("/api/inspecoes", files={"imagem": ("x.png", b"nao e imagem", "image/png")},
               data={"lote": "L1", "modelo_placa": "HRIPCB", "turno": "A", "posto": "P01"})
    assert r.status_code == 422
