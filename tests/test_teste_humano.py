import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import cv2
from fastapi.testclient import TestClient

from app.main import criar_app
from app.service import ServicoInspecao

from .conftest import DetectorFalso, placa_sintetica

RAIZ = Path(__file__).resolve().parent.parent


def _analisador():
    spec = importlib.util.spec_from_file_location("analisar", RAIZ / "scripts/teste_humano/analisar_resultados.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_sessao_ponta_a_ponta(cfg, tmp_path):
    imgs, lbls = tmp_path / "ds/images", tmp_path / "ds/labels"
    imgs.mkdir(parents=True); lbls.mkdir(parents=True)
    for k in range(22):
        cv2.imwrite(str(imgs / f"{k:02d}.png"), placa_sintetica(k))
        (lbls / f"{k:02d}.txt").write_text("3 0.5 0.5 0.1 0.1\n0 0.2 0.2 0.05 0.05\n")
    cfg.pasta_teste = tmp_path / "teste"
    subprocess.run([sys.executable, str(RAIZ / "scripts/teste_humano/gerar_sessao.py"), "--imagens", str(imgs),
                    "--rotulos", str(lbls), "--sessao", "S1", "--sugestoes-do-gabarito", "--exibicao", "600",
                    "--saida", str(cfg.pasta_teste)], check=True, cwd=RAIZ)
    plano = json.loads((cfg.pasta_teste / "S1/sessao.json").read_text())
    assert len(plano["placas"]) == 20
    assert sum(p["erro_proposital"] is not None for p in plano["placas"]) == 2

    c = TestClient(criar_app(cfg, ServicoInspecao(cfg, detector=DetectorFalso())))
    c.post("/login", data={"perfil": "tecnico", "pin": cfg.pin_tecnico})
    assert c.get("/teste/S1").status_code == 200
    por_id = {p["id"]: p for p in plano["placas"]}
    for part in ("V01", "V02"):
        pub = c.get("/api/teste/S1/plano", params={"participante": part}).json()
        assert "gabarito" not in json.dumps(pub)                  # gabarito nunca vai ao navegador
        assert sum(p["com_assistente"] for p in pub["placas"]) == 10
        assert c.get(f"/api/teste/S1/img/{pub['placas'][0]['arquivo']}").status_code == 200
        resp = []
        for p in pub["placas"]:
            gab = por_id[p["id"]]["gabarito"]
            # simula: sem assistente acha só o 1º defeito; com assistente clica nas sugestões
            alvos = p["sugestoes"] if p["com_assistente"] else gab[:1]
            resp.append({"id": p["id"], "tempo_s": 12, "cliques": [[(b["x1"] + b["x2"]) / 2, (b["y1"] + b["y2"]) / 2] for b in alvos]})
        r = c.post("/api/teste/S1/resultado", json={"participante": part, "usabilidade": 4,
                                                    "notou_sugestao_errada": "nao", "respostas": resp})
        assert r.status_code == 200, r.text
    assert c.post("/api/teste/S1/resultado", json={"participante": "V03", "usabilidade": 9, "respostas": []}).status_code == 422

    m = _analisador()
    res = m.analisar(plano, [json.loads(p.read_text()) for p in sorted((cfg.pasta_teste / "S1/resultados").glob("*.json"))])
    assert res["participantes"] == 2
    assert res["escape"]["sem_assistente"]["taxa"] > res["escape"]["com_assistente"]["taxa"]
    assert res["C4_menos_escapes_com_assistente"] is True
    # quem clica em tudo o que o assistente sugere cai no erro proposital → viés de automação
    assert res["vies_automacao"]["perceberam_ao_menos_um_erro"] == 0
    assert res["C5_maioria_percebe_e_usabilidade_>=_3"] is False
