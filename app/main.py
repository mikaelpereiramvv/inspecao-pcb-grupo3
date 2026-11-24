"""Aplicação web (FastAPI) – Interface do Inspetor, Painel e Curadoria.

Executar:  uvicorn app.main:app --reload   →  http://localhost:8000
"""
from __future__ import annotations

import hmac
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from . import curation, dashboard, lgpd, metadata
from .config import CLASSES, PERFIS, ROTULOS_PT, Config, carregar
from .preprocess import ImagemInvalida
from .service import ErroFluxo, ServicoInspecao

AQUI = Path(__file__).parent
TAMANHO_MAX_UPLOAD = 15 * 1024 * 1024


class Decisao(BaseModel):
    decisao: str
    descartadas: list[int] = Field(default_factory=list)
    reclassificadas: dict[int, str] = Field(default_factory=dict)
    adicionadas: list[dict] = Field(default_factory=list)
    observacao: str | None = None


class Curadoria(BaseModel):
    aprovar: bool
    obs: str | None = None


def criar_app(cfg: Config | None = None, servico: ServicoInspecao | None = None) -> FastAPI:
    cfg = cfg or carregar()
    app = FastAPI(title="Assistente de Inspeção Visual de PCBs – Grupo 3")
    app.add_middleware(SessionMiddleware, secret_key=cfg.chave_sessao, same_site="strict")
    app.mount("/static", StaticFiles(directory=AQUI / "static"), name="static")
    tpl = Jinja2Templates(directory=AQUI / "templates")
    app.state.servico = servico or ServicoInspecao(cfg)
    app.state.cfg = cfg

    def srv() -> ServicoInspecao:
        return app.state.servico

    # ------------------------------------------------------------ sessão/perfil
    def sessao(request: Request) -> dict:
        s = request.session
        if s.get("perfil") not in PERFIS:
            raise HTTPException(401, "Faça login.")
        return s

    def exige(*perfis: str):
        def dep(request: Request) -> dict:
            s = sessao(request)
            if s["perfil"] not in perfis:
                raise HTTPException(403, "Seu perfil não tem acesso a esta área.")
            return s
        return dep

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException):
        if request.url.path.startswith("/api/"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        if exc.status_code == 401:
            return RedirectResponse("/", status_code=303)
        return HTMLResponse(f"<h1>{exc.status_code}</h1><p>{exc.detail}</p><a href='/'>Voltar</a>",
                            status_code=exc.status_code)

    @app.get("/", response_class=HTMLResponse)
    def login_page(request: Request, erro: str | None = None):
        return tpl.TemplateResponse(request, "login.html", {"erro": erro})

    @app.post("/login")
    def login(request: Request, perfil: str = Form(...), codigo: str = Form(""), pin: str = Form("")):
        request.session.clear()  # tentativa de login sempre encerra a sessão anterior
        if perfil not in PERFIS:
            return RedirectResponse("/?erro=Perfil+inválido", status_code=303)
        if perfil == "inspetor":
            try:
                codigo = lgpd.validar_codigo(codigo)
            except ValueError:
                return RedirectResponse("/?erro=Código+funcional+inválido", status_code=303)
            request.session.clear()
            request.session.update({"perfil": perfil, "codigo": codigo})
            return RedirectResponse("/inspetor", status_code=303)
        esperado = cfg.pin_supervisor if perfil == "supervisor" else cfg.pin_tecnico
        if not hmac.compare_digest(pin, esperado):
            return RedirectResponse("/?erro=PIN+incorreto", status_code=303)
        request.session.clear()
        request.session.update({"perfil": perfil})
        return RedirectResponse("/painel" if perfil == "supervisor" else "/curadoria", status_code=303)

    @app.get("/sair")
    def sair(request: Request):
        request.session.clear()
        return RedirectResponse("/", status_code=303)

    # ---------------------------------------------------------------- páginas
    def ctx(s: dict, **extra) -> dict:
        return {"perfil": s["perfil"], "classes": CLASSES, "rotulos": ROTULOS_PT, **extra}

    @app.get("/inspetor", response_class=HTMLResponse)
    def pagina_inspetor(request: Request, s=Depends(exige("inspetor"))):
        return tpl.TemplateResponse(request, "inspetor.html", ctx(s, cfg=cfg))

    @app.get("/painel", response_class=HTMLResponse)
    def pagina_painel(request: Request, s=Depends(exige("supervisor", "tecnico"))):
        return tpl.TemplateResponse(request, "painel.html", ctx(s))

    @app.get("/curadoria", response_class=HTMLResponse)
    def pagina_curadoria(request: Request, s=Depends(exige("tecnico"))):
        return tpl.TemplateResponse(request, "curadoria.html", ctx(s))

    # --------------------------------------------------------------- API
    @app.get("/api/status")
    def api_status(s=Depends(sessao)):
        return srv().status()

    @app.get("/api/metadados/simulados")
    def api_meta_simulados(modelo_placa: str = "HRIPCB", s=Depends(exige("inspetor"))):
        return metadata.simular(modelo_placa).to_dict()

    @app.post("/api/metadados/qr")
    def api_meta_qr(texto: str = Form(...), s=Depends(exige("inspetor"))):
        try:
            return metadata.ler_codigo_qr(texto).to_dict()
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.post("/api/inspecoes")
    async def api_inspecionar(
        imagem: UploadFile = File(...), lote: str = Form(...), modelo_placa: str = Form(...),
        turno: str = Form(...), posto: str = Form(...), etapa_origem: str | None = Form(None),
        data_hora_producao: str | None = Form(None), simulado: bool = Form(False),
        s=Depends(exige("inspetor")),
    ):
        conteudo = await imagem.read(TAMANHO_MAX_UPLOAD + 1)
        if len(conteudo) > TAMANHO_MAX_UPLOAD:
            raise HTTPException(413, "Imagem maior que 15 MB.")
        meta = metadata.Metadados(lote, modelo_placa, turno, posto, etapa_origem, data_hora_producao, simulado)
        try:
            r = srv().inspecionar(conteudo, meta, s["codigo"])
        except (ImagemInvalida, ValueError) as e:
            raise HTTPException(422, str(e))
        d = r.to_dict()
        d["marcacoes"] = srv().deteccoes_vigentes(r.id)
        return d

    @app.post("/api/inspecoes/{id_insp}/reprocessar")
    def api_reprocessar(id_insp: str, s=Depends(exige("inspetor"))):
        try:
            r = srv().reprocessar(id_insp)
        except ErroFluxo as e:
            raise HTTPException(409, str(e))
        d = r.to_dict()
        d["marcacoes"] = srv().deteccoes_vigentes(id_insp)
        return d

    @app.post("/api/inspecoes/{id_insp}/decisao")
    def api_decidir(id_insp: str, body: Decisao, s=Depends(exige("inspetor"))):
        try:
            return srv().decidir(id_insp, body.decisao, s["codigo"], body.descartadas, body.reclassificadas,
                                 body.adicionadas, body.observacao)
        except ErroFluxo as e:
            raise HTTPException(409, str(e))
        except (KeyError, TypeError, ValueError) as e:
            raise HTTPException(422, f"Dados inválidos: {e}")

    @app.get("/api/inspecoes/{id_insp}")
    def api_obter(id_insp: str, s=Depends(sessao)):
        try:
            return srv().obter(id_insp)
        except ErroFluxo as e:
            raise HTTPException(404, str(e))

    @app.get("/api/inspecoes/{id_insp}/imagem/{tipo}")
    def api_imagem(id_insp: str, tipo: str, s=Depends(sessao)):
        try:
            dados = srv().storage.ler(id_insp, tipo)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, "Imagem não encontrada.")
        return Response(dados, media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.get("/api/painel")
    def api_painel(lote: str | None = None, turno: str | None = None, desde: str | None = None,
                   ate: str | None = None, s=Depends(exige("supervisor", "tecnico"))):
        return dashboard.resumo(srv().con, lote or None, turno or None, desde or None, ate or None)

    @app.get("/api/alertas")
    def api_alertas(desde: str | None = None, s=Depends(exige("supervisor", "tecnico"))):
        return dashboard.alertas_reincidencia(srv().con, cfg.alerta_min_ocorrencias, cfg.alerta_taxa_minima,
                                              desde or None)

    @app.get("/api/curadoria")
    def api_curadoria(status: str = "pendente", s=Depends(exige("tecnico"))):
        if status not in ("pendente", "aprovada", "rejeitada"):
            raise HTTPException(422, "Status inválido.")
        return curation.listar(srv().con, status)

    @app.post("/api/curadoria/exportar")
    def api_exportar(s=Depends(exige("tecnico"))):
        return curation.exportar_yolo(srv().con, srv().storage, cfg.pasta_curadoria, cfg.tamanho_imagem)

    @app.post("/api/curadoria/{id_corr}")
    def api_curar(id_corr: int, body: Curadoria, s=Depends(exige("tecnico"))):
        try:
            curation.curar(srv().con, id_corr, body.aprovar, body.obs)
        except curation.ErroCuradoria as e:
            raise HTTPException(409, str(e))
        return {"ok": True}

    return app


app = criar_app()
