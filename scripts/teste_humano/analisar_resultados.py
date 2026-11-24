"""Analisa o teste controlado (Critérios 4 e 5 da Seção 11).

Critério 4 – Redução de escape humano: menos defeitos despercebidos COM o assistente do que SEM.
Critério 5 – Confiança crítica e usabilidade: a maioria percebe ao menos uma sugestão errada
             proposital E a nota média de facilidade de uso é ≥ 3,0 (escala 1–5).

Percepção do erro proposital (medida objetiva, a partir dos cliques):
  omissão      → percebeu se clicou no defeito real que o assistente "esqueceu";
  falso alarme → percebeu se NÃO clicou dentro da caixa falsa.
A resposta do questionário ("notou sugestão errada?") é reportada à parte (autodeclarada).

Uso:  python scripts/teste_humano/analisar_resultados.py --sessao S1
Limitação (Seção 14): amostra acadêmica pequena → evidência indicativa, não comprovação estatística.
"""
from __future__ import annotations

import argparse
import json
import sys
from math import comb
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _comum import salvar_json  # noqa: E402

from app.config import carregar  # noqa: E402

MARGEM = 8  # px de tolerância ao redor da caixa para considerar o clique


def dentro(c, caixa, m=MARGEM):
    x, y = c
    return caixa["x1"] - m <= x <= caixa["x2"] + m and caixa["y1"] - m <= y <= caixa["y2"] + m


def teste_sinal(melhoraram: int, pioraram: int) -> float | None:
    """p-valor unilateral do teste do sinal (H1: assistente reduz escapes)."""
    n = melhoraram + pioraram
    if n == 0:
        return None
    return sum(comb(n, k) for k in range(melhoraram, n + 1)) / 2 ** n


def analisar(plano: dict, resultados: list[dict]) -> dict:
    placas = {p["id"]: p for p in plano["placas"]}
    por_part = []
    for r in resultados:
        cond = {plid: com for plid, com in plano["grupos"][r["grupo"]]}
        acc = {True: {"defeitos": 0, "despercebidos": 0, "cliques_falsos": 0, "esgotou": 0},
               False: {"defeitos": 0, "despercebidos": 0, "cliques_falsos": 0, "esgotou": 0}}
        percepcoes = []
        for resp in r["respostas"]:
            p = placas[resp["id"]]
            com = cond[resp["id"]]
            a = acc[com]
            a["defeitos"] += len(p["gabarito"])
            a["despercebidos"] += sum(not any(dentro(c, g) for c in resp["cliques"]) for g in p["gabarito"])
            a["cliques_falsos"] += sum(not any(dentro(c, g) for g in p["gabarito"]) for c in resp["cliques"])
            a["esgotou"] += int(resp.get("esgotou", False))
            e = p.get("erro_proposital")
            if com and e:
                if e["tipo"] == "omissao":
                    ok = any(dentro(c, e["caixa"]) for c in resp["cliques"])
                else:
                    ok = not any(dentro(c, e["caixa"]) for c in resp["cliques"])
                percepcoes.append({"placa": p["id"], "tipo": e["tipo"], "percebeu": ok})
        por_part.append({
            "participante": r["participante"], "grupo": r["grupo"], "usabilidade": r["usabilidade"],
            "autodeclarou_notar_erro": r.get("notou_sugestao_errada"),
            "sem_assistente": acc[False], "com_assistente": acc[True],
            "erros_propositais": percepcoes,
            "percebeu_ao_menos_um": any(x["percebeu"] for x in percepcoes) if percepcoes else None,
        })

    n = len(por_part)
    tot = lambda chave, campo: sum(p[chave][campo] for p in por_part)  # noqa: E731
    sem_d, com_d = tot("sem_assistente", "despercebidos"), tot("com_assistente", "despercebidos")
    sem_t, com_t = tot("sem_assistente", "defeitos"), tot("com_assistente", "defeitos")
    melhor = sum(p["com_assistente"]["despercebidos"] / max(1, p["com_assistente"]["defeitos"]) <
                 p["sem_assistente"]["despercebidos"] / max(1, p["sem_assistente"]["defeitos"]) for p in por_part)
    pior = sum(p["com_assistente"]["despercebidos"] / max(1, p["com_assistente"]["defeitos"]) >
               p["sem_assistente"]["despercebidos"] / max(1, p["sem_assistente"]["defeitos"]) for p in por_part)
    perceberam = sum(bool(p["percebeu_ao_menos_um"]) for p in por_part)
    usab = sum(p["usabilidade"] for p in por_part) / n if n else None
    taxa_sem = sem_d / sem_t if sem_t else None
    taxa_com = com_d / com_t if com_t else None
    return {
        "participantes": n,
        "escape": {"sem_assistente": {"despercebidos": sem_d, "defeitos": sem_t, "taxa": taxa_sem},
                   "com_assistente": {"despercebidos": com_d, "defeitos": com_t, "taxa": taxa_com},
                   "participantes_que_melhoraram": melhor, "participantes_que_pioraram": pior,
                   "p_valor_teste_sinal_unilateral": teste_sinal(melhor, pior)},
        "vies_automacao": {"perceberam_ao_menos_um_erro": perceberam,
                           "autodeclararam_notar": sum(p["autodeclarou_notar_erro"] == "sim" for p in por_part)},
        "usabilidade_media": usab,
        # Compara TAXAS (as metades podem ter nº de defeitos diferentes)
        "C4_menos_escapes_com_assistente": None if taxa_sem is None or taxa_com is None else taxa_com < taxa_sem,
        "C5_maioria_percebe_e_usabilidade_>=_3": None if not n else (perceberam > n / 2 and usab >= 3.0),
        "por_participante": por_part,
    }


def main():
    cfg = carregar()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sessao", required=True)
    ap.add_argument("--pasta", type=Path, default=cfg.pasta_teste)
    a = ap.parse_args()
    base = a.pasta / a.sessao
    plano = json.loads((base / "sessao.json").read_text(encoding="utf-8"))
    resultados = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((base / "resultados").glob("*.json"))]
    if not resultados:
        raise SystemExit("Nenhum resultado registrado ainda.")
    r = analisar(plano, resultados)
    e = r["escape"]
    f = lambda v: "—" if v is None else f"{v:.1%}"  # noqa: E731
    print(f"Participantes: {r['participantes']}  (sugestões: {plano.get('sugestoes_fonte')})")
    print(f"Escape SEM assistente: {e['sem_assistente']['despercebidos']}/{e['sem_assistente']['defeitos']} ({f(e['sem_assistente']['taxa'])})")
    print(f"Escape COM assistente: {e['com_assistente']['despercebidos']}/{e['com_assistente']['defeitos']} ({f(e['com_assistente']['taxa'])})")
    print(f"Melhoraram/pioraram: {e['participantes_que_melhoraram']}/{e['participantes_que_pioraram']} "
          f"(teste do sinal, p={e['p_valor_teste_sinal_unilateral']})")
    print(f"Perceberam ≥1 erro proposital: {r['vies_automacao']['perceberam_ao_menos_um_erro']}/{r['participantes']} · "
          f"usabilidade média: {r['usabilidade_media']:.2f}")
    for k in ("C4_menos_escapes_com_assistente", "C5_maioria_percebe_e_usabilidade_>=_3"):
        print(f"  {k}: {'ATENDIDO' if r[k] else 'NÃO atendido'}")
    salvar_json(r, base / "analise.json")


if __name__ == "__main__":
    main()
