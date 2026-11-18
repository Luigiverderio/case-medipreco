r"""Aplicação local do protótipo Medipreço.

Serve as páginas geradas e adiciona o fluxo de contratos:
upload -> análise pelo agente -> vínculo automático ou fila de aprovação.

Uso:
    $env:NVIDIA_API_KEY = Read-Host "NVIDIA API key"
    .\.venv\Scripts\python src\app.py
"""
import base64
import contextlib
import hashlib
import io
import json
import os
import re
import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from html import escape as esc
from pathlib import Path

from flask import Flask, abort, redirect, render_template_string, request, send_from_directory, url_for
from markupsafe import Markup
from openai import OpenAI
from pypdf import PdfReader
from werkzeug.utils import secure_filename

import regra_contrato as rc
from gerar_paginas import ESTILO, slug
from vincular import (CNPJ_RE, como_lista, MODELO, SISTEMA, URL_API, analisar, decidir, empresas,
                      gravar_auditoria)


RAIZ = Path(__file__).resolve().parent.parent
SITE = RAIZ / "saida" / "site"
ANALISES = RAIZ / "saida" / "analises"
UPLOADS = RAIZ / "dados" / "uploads"
AUDITORIA = RAIZ / "saida" / "auditoria.jsonl"
CATALOGO = RAIZ / "catalogo" / "regras.json"
MAX_PDF = 10 * 1024 * 1024

def carregar_env():
    """Le RAIZ/.env (ignorado pelo git) e define as variaveis que ainda nao existem no ambiente."""
    caminho = RAIZ / ".env"
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            nome, valor = linha.split("=", 1)
            os.environ.setdefault(nome.strip(), valor.strip().strip('"').strip("'"))


carregar_env()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_PDF

APP_STYLE = """
.form-box{max-width:760px;border:1px solid var(--borda);border-radius:16px;padding:24px;background:var(--surface)}
.form-box label{display:block;color:var(--navy);font-weight:700;margin-bottom:8px}.form-box input[type=file]{display:block;width:100%;padding:14px;background:#fff;border:1px solid var(--borda);border-radius:8px;margin-bottom:14px}
.button{display:inline-flex;align-items:center;justify-content:center;border:0;border-radius:8px;padding:11px 16px;background:var(--cta);color:#fff;font:700 14px/1.2 Manrope,sans-serif;cursor:pointer;text-decoration:none}.button:hover{background:var(--link);color:#fff}.button:disabled{opacity:.5;cursor:not-allowed}
.status-box{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:18px 20px;border:1px solid var(--borda);border-radius:12px;background:var(--surface);margin:18px 0}.status-box h2{margin:0;font-size:20px}.status-box p{margin:4px 0 0}
.error-box{border:1px solid #efc9c6;border-left:5px solid var(--erro);background:#fff8f7;padding:14px 16px;margin:16px 0;border-radius:0 10px 10px 0;color:var(--erro)}
.empty{padding:30px;border:1px dashed var(--borda);border-radius:12px;color:#627382;text-align:center}
.actions{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}.file-help{font-size:13px;color:#627382}
.console{background:#0e2841;color:#dfeaf5;padding:16px 18px;border-radius:12px;overflow:auto;max-height:520px;font:13px/1.5 Consolas,monospace;white-space:pre-wrap;margin:10px 0}
.pensando{display:flex;gap:12px;align-items:center;margin-top:16px;padding:12px 14px;border:1px solid var(--borda);border-radius:10px;background:var(--surface);color:var(--navy);font-weight:700;font-size:14px}
.spin{width:18px;height:18px;flex:none;border:3px solid #d7e0ea;border-top-color:var(--cta);border-radius:50%;animation:giro .8s linear infinite}@keyframes giro{to{transform:rotate(360deg)}}
.key-form{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.key-form input{flex:1;min-width:260px;padding:11px 12px;border:1px solid var(--borda);border-radius:8px;font:14px Manrope,sans-serif}
"""

BASE = """
<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ title }}</title>
<style>{{ style }}</style></head><body><a class="skip" href="#conteudo">Ir para o conteúdo</a>
<header class="topbar"><div class="topbar-inner"><div class="brand">
<a class="brand-home" href="{{ url_for('inicio') }}" aria-label="Voltar ao início"><img alt="Medipreço" src="data:image/png;base64,{{ logo }}"></a>
<span class="context">Operação de fechamento</span></div>
<nav aria-label="Navegação principal">
<a href="{{ url_for('inicio') }}">Início</a><a href="{{ url_for('pagina_site', arquivo='financeiro.html') }}">Financeiro</a>
<a href="{{ url_for('pagina_site', arquivo='comercial.html') }}">Comercial</a><a class="{{ 'active' if active == 'contratos' else '' }}" href="{{ url_for('contratos') }}">Contratos</a>
<a class="{{ 'active' if active == 'aprovacoes' else '' }}" href="{{ url_for('aprovacoes') }}">Aprovações</a>
<a class="{{ 'active' if active == 'sistema' else '' }}" href="{{ url_for('sistema') }}">Sistema</a>
</nav></div></header><main id="conteudo">{{ body }}</main>
<script>
document.querySelectorAll('form[data-carregando]').forEach(function(f){
  f.addEventListener('submit',function(){
    var msgs=f.dataset.carregando.split('|'), b=f.querySelector('button[type=submit]');
    if(b){setTimeout(function(){b.disabled=true;},0);}
    var box=document.createElement('div'); box.className='pensando'; box.setAttribute('role','status');
    box.innerHTML='<span class="spin"></span><span></span>'; f.appendChild(box);
    var txt=box.lastChild, i=0, ini=Date.now();
    function passo(){
      var seg=Math.round((Date.now()-ini)/1000);
      if(i<msgs.length-1 && Date.now()-ini>(i+1)*9000){i++;}
      txt.textContent=msgs[i]+' ('+seg+'s)';
    }
    passo(); setInterval(passo,1000);
  });
});
</script></body></html>
"""


def pagina(titulo, corpo, ativo=""):
    logo = base64.b64encode((RAIZ / "dados" / "marca" / "logo-branco.png").read_bytes()).decode()
    return render_template_string(
        BASE, title=titulo, body=Markup(corpo), style=Markup(ESTILO + APP_STYLE),
        logo=logo, active=ativo,
    )


def carregar_analises():
    ANALISES.mkdir(parents=True, exist_ok=True)
    registros = []
    for caminho in ANALISES.glob("*.json"):
        try:
            registros.append(json.loads(caminho.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return sorted(registros, key=lambda r: r["quando"], reverse=True)


def carregar_analise(analise_id):
    if not re.fullmatch(r"[0-9a-f]{12}", analise_id):
        abort(404)
    caminho = ANALISES / f"{analise_id}.json"
    if not caminho.exists():
        abort(404)
    return json.loads(caminho.read_text(encoding="utf-8"))


def texto_do_pdf(dados):
    try:
        leitor = PdfReader(io.BytesIO(dados))
        texto = "\n".join((pagina.extract_text() or "") for pagina in leitor.pages)
    except Exception as exc:
        raise ValueError("Não foi possível ler o PDF.") from exc
    if len(texto.strip()) < 100:
        raise ValueError("O PDF não contém texto suficiente para análise.")
    return texto


def processar_pdf(nome_original, dados):
    chave = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not chave:
        raise RuntimeError("O serviço de análise está indisponível. Verifique a configuração do servidor.")
    texto = texto_do_pdf(dados)
    catalogo = json.loads(CATALOGO.read_text(encoding="utf-8"))
    cliente_api = OpenAI(base_url=URL_API, api_key=chave)
    analise = analisar(cliente_api, catalogo, texto)
    cnpjs = sorted(set(CNPJ_RE.findall(texto)))
    status, motivos, clientes = decidir(analise, cnpjs, empresas())
    if como_lista(analise.get("divergencias")):
        motivos.append("há divergências entre o contrato e os modelos do catálogo")
    status = "vinculado" if not motivos else "pendente_aprovacao"

    regra_proposta, erros_regra = None, []
    try:
        regra_proposta, erros_regra = rc.montar(rc.extrair_regra(cliente_api, texto), empresas())
    except Exception:
        app.logger.exception("falha ao extrair a regra do contrato")
        erros_regra = ["o agente não conseguiu extrair a regra deste contrato"]

    analise_id = uuid.uuid4().hex[:12]
    nome_seguro = secure_filename(nome_original) or "contrato.pdf"
    registro = {
        "id": analise_id,
        "quando": datetime.now(timezone.utc).isoformat(),
        "acao": "analise_contrato",
        "arquivo": nome_seguro,
        "pdf_sha256": hashlib.sha256(dados).hexdigest(),
        "modelo_llm": MODELO,
        "versao_prompt": hashlib.sha256((SISTEMA + json.dumps(catalogo, sort_keys=True)).encode()).hexdigest()[:12],
        "cnpjs_regex": cnpjs,
        "clientes": clientes,
        "analise": analise,
        "status": status,
        "motivos": sorted(set(motivos)),
        "regra_proposta": regra_proposta,
        "erros_regra": erros_regra,
    }
    UPLOADS.mkdir(parents=True, exist_ok=True)
    ANALISES.mkdir(parents=True, exist_ok=True)
    (UPLOADS / f"{analise_id}-{nome_seguro}").write_bytes(dados)
    gravar_auditoria(AUDITORIA, registro)
    (ANALISES / f"{analise_id}.json").write_text(
        json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return registro


def tabela_historico(registros):
    if not registros:
        return '<div class="empty">Nenhum contrato analisado.</div>'
    linhas = "".join(
        f"<tr><td>{esc(r['arquivo'])}</td>"
        f"<td>{esc((r.get('clientes') or [r['analise'].get('cliente', 'Não identificado')])[0])}</td>"
        f"<td>{esc(r['analise'].get('regra_id', '—'))}</td><td>{'Vinculado' if r['status'] == 'vinculado' else 'Aprovação necessária'}</td>"
        f"<td style='white-space:nowrap'><a class='button' href='{url_for('analise_contrato', analise_id=r['id'])}'>Ver análise</a> "
        f"{botao_excluir(r['id'], 'Excluir')}</td></tr>"
        for r in registros
    )
    return f'<div class="table-wrap"><table><tr><th>Arquivo</th><th>Cliente</th><th>Regra</th><th>Status</th><th></th></tr>{linhas}</table></div>'


@app.get("/")
def inicio():
    return redirect(url_for("pagina_site", arquivo="index.html"))


@app.get("/site/<path:arquivo>")
def pagina_site(arquivo):
    return send_from_directory(SITE, arquivo)


@app.route("/contratos", methods=["GET", "POST"])
def contratos():
    erro = None
    if request.method == "POST":
        arquivo = request.files.get("contrato")
        if not arquivo or not arquivo.filename:
            erro = "Selecione um contrato em PDF."
        elif Path(arquivo.filename).suffix.lower() != ".pdf":
            erro = "O arquivo precisa estar em PDF."
        else:
            dados = arquivo.read()
            if len(dados) > MAX_PDF:
                erro = "O PDF deve ter no máximo 10 MB."
            else:
                try:
                    registro = processar_pdf(arquivo.filename, dados)
                    return redirect(url_for("analise_contrato", analise_id=registro["id"]))
                except (ValueError, RuntimeError) as exc:
                    erro = str(exc)
                except Exception:
                    app.logger.exception("falha na analise do contrato")
                    erro = "A análise não foi concluída. Tente novamente."
    erro_html = f'<div class="error-box">{esc(erro)}</div>' if erro else ""
    historico = tabela_historico(carregar_analises())
    corpo = f"""
    <section class="page-intro"><h1>Contratos</h1><p class="sub">Envie um contrato para identificar o cliente e a regra de cobrança.</p></section>
    {erro_html}<div class="form-box"><form method="post" enctype="multipart/form-data" data-carregando="Lendo o PDF|O agente está identificando o cliente e o modelo de cobrança|Extraindo valores e cláusulas da regra|Conferindo CNPJs e montando a regra para você revisar">
    <label for="contrato">Contrato assinado</label><input id="contrato" name="contrato" type="file" accept="application/pdf,.pdf" required>
    <p class="file-help">PDF com até 10 MB.</p>
    <button class="button" type="submit">Analisar contrato</button></form></div>
    <h2>Histórico</h2>{historico}
    """
    return pagina("Contratos", corpo, "contratos")


@app.get("/contratos/<analise_id>")
def analise_contrato(analise_id):
    registro = carregar_analise(analise_id)
    analise = registro["analise"]
    campos = "".join(
        f"<tr><td>{esc(c['campo'])}</td><td>{esc(c['valor'])}</td><td>{esc(c['clausula'])}</td></tr>" for c in analise["campos"]
    )
    status = "Vinculado automaticamente" if registro["status"] == "vinculado" else "Aprovação necessária"
    tipo = "ok" if registro["status"] == "vinculado" else "aviso"
    motivos = "".join(f"<li>{esc(m)}</li>" for m in registro["motivos"])
    alertas = "".join(f"<li>{esc(p)}</li>" for p in como_lista(analise.get("pontos_de_atencao")))
    corpo = f"""
    <section class="page-intro"><h1>Análise do contrato</h1><p class="sub">{esc(registro['arquivo'])}</p></section>
    <div class="status-box"><div><h2>{status}</h2><p>{esc((registro.get('clientes') or [analise['cliente']])[0])}</p></div>
    <span class="badge {tipo}">{esc(analise['regra_id'])}</span></div>
    <h2>Resumo</h2><div class="table-wrap"><table><tr><th>Campo</th><th>Valor extraído</th><th>Cláusula</th></tr>{campos}</table></div>
    <h2>Decisão</h2><p>{esc(analise['justificativa'])}</p>{secao_regra(registro)}
    {f'<h3>Motivos para aprovação</h3><ul>{motivos}</ul>' if motivos else ''}
    {f'<h3>Pontos de atenção</h3><ul>{alertas}</ul>' if alertas else ''}
    <div class="actions"><a class="button" href="{url_for('contratos')}">Voltar aos contratos</a>
    {f'<a class="button" href="{url_for("aprovacoes")}">Ver aprovações</a>' if registro['status'] != 'vinculado' else ''}
    {botao_excluir(registro['id'])}</div>
    """
    return pagina("Análise do contrato", corpo, "contratos")


def botao_excluir(analise_id, rotulo="Excluir"):
    return (f"<form method='post' action='{url_for('excluir_analise', analise_id=analise_id)}' style='display:inline' "
            f"onsubmit=\"return confirm('Excluir esta submissão? O PDF e a análise serão apagados.')\">"
            f"<button class='button' type='submit' style='background:#b3382c'>{rotulo}</button></form>")


@app.post("/contratos/<analise_id>/excluir")
def excluir_analise(analise_id):
    registro = carregar_analise(analise_id)
    (ANALISES / f"{analise_id}.json").unlink(missing_ok=True)
    for pdf in UPLOADS.glob(f"{analise_id}-*"):
        pdf.unlink(missing_ok=True)
    gravar_auditoria(AUDITORIA, {
        "quando": datetime.now(timezone.utc).isoformat(), "acao": "exclusao_analise", "id": analise_id,
        "arquivo": registro["arquivo"], "pdf_sha256": registro["pdf_sha256"], "clientes": registro.get("clientes", []),
        "status": "excluida", "motivos": [], "analise": {},
        "regra_ficou_em_vigor": registro.get("decisao_regra", {}).get("resultado") == "aprovada"})
    return redirect(request.form.get("voltar") or url_for("contratos"))


def secao_regra(registro):
    regra, erros = registro.get("regra_proposta"), registro.get("erros_regra", [])
    decisao = registro.get("decisao_regra")
    if decisao:
        aprovada = decisao["resultado"] == "aprovada"
        return (f"<h2 id='regra'>Regra do contrato</h2><div class='status-box'><div><h2>{'Regra aprovada e em vigor' if aprovada else 'Regra rejeitada'}</h2>"
                f"<p>{quando_br(decisao['quando'])}</p></div><span class='badge {'ok' if aprovada else 'rev'}'>{esc(decisao['resultado'])}</span></div>")
    if "regra_proposta" not in registro:
        return ("<h2 id='regra'>Regra do contrato</h2><div class='nota'>Esta análise foi feita antes da extração de regras. "
                "Exclua-a e envie o contrato de novo para receber a regra proposta.</div>")
    if not regra:
        return ("<h2 id='regra'>Regra do contrato</h2><div class='error-box'>Não foi possível extrair uma regra deste contrato. "
                + esc("; ".join(erros)) + "</div>")
    linhas = "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td><td>{esc(c)}</td></tr>" for a, b, c in rc.linhas_resumo(regra))
    existente = (RAIZ / "regras" / f"{slug(regra['cliente'])}.json").exists() if regra["cliente"] else False
    aviso = (f"<div class='nota'>Já existe uma regra para <b>{esc(regra['cliente'])}</b>. Ao aprovar, esta passa a valer e a "
             f"anterior fica guardada em <code>regras/versoes</code>.</div>" if existente else "")
    itens_erro = "".join(f"<li>{esc(e)}</li>" for e in erros)
    problemas = f"<div class='error-box'><b>Não é possível aprovar ainda:</b><ul>{itens_erro}</ul></div>" if erros else ""
    extras = "".join(f"<li>{esc(t)}</li>" for t in regra["premissas"] + regra["pendencias"])
    botoes = ("" if erros else
              f"<form method='post' action='{url_for('decidir_regra', analise_id=registro['id'])}' class='actions' data-carregando='Aplicando a decisão e recalculando as páginas'>"
              f"<button class='button' name='decisao' value='aprovar' type='submit'>Aprovar e ativar a regra</button>"
              f"<button class='button' name='decisao' value='rejeitar' type='submit' style='background:#627382'>Rejeitar</button></form>")
    lista_extras = f"<h3>Premissas e pontos em aberto</h3><ul>{extras}</ul>" if extras else ""
    return (f"<h2 id='regra'>Regra proposta para {esc(regra['cliente'] or 'cliente não identificado')}</h2>"
            f"<p class='peq'>Extraída pelo agente do texto do contrato. Confira com o PDF antes de aprovar: ao aprovar, ela passa a "
            f"valer nos cálculos e nas páginas.</p><div class='table-wrap'><table><tr><th>Item</th><th>Valor</th><th>Cláusula</th></tr>{linhas}</table></div>"
            f"{lista_extras}{aviso}{problemas}{botoes}")


def escrever_regra(regra, registro):
    """Grava regras/<cliente>.json guardando a versao anterior. Devolve (caminho, bytes_anteriores ou None)."""
    pasta = RAIZ / "regras"
    destino = pasta / f"{slug(regra['cliente'])}.json"
    anterior = destino.read_bytes() if destino.exists() else None
    if anterior is not None:
        (pasta / "versoes").mkdir(exist_ok=True)
        (pasta / "versoes" / f"{destino.stem}-{datetime.now(timezone.utc):%Y%m%d%H%M%S}.json").write_bytes(anterior)
    origem = f"extraída do contrato {registro['arquivo']} (sha256 {registro['pdf_sha256'][:12]}) e aprovada por uma pessoa"
    modelo = registro.get("analise", {}).get("regra_id")
    modelo = None if modelo in (None, "NENHUMA") else modelo
    destino.write_text(json.dumps(dict(regra, origem=origem, modelo=modelo), ensure_ascii=False, indent=2), encoding="utf-8")
    return destino, anterior


@app.post("/contratos/<analise_id>/decisao")
def decidir_regra(analise_id):
    registro = carregar_analise(analise_id)
    if registro.get("decisao_regra"):
        return redirect(url_for("analise_contrato", analise_id=analise_id))
    regra, decisao = registro.get("regra_proposta"), request.form.get("decisao")
    if decisao not in ("aprovar", "rejeitar") or not regra or registro.get("erros_regra"):
        abort(400)
    agora = datetime.now(timezone.utc).isoformat()
    destino = anterior = None
    if decisao == "aprovar":
        destino, anterior = escrever_regra(regra, registro)
        ok, texto = capturar(acao_gerar)
        if not ok:  # a regra quebrou o calculo: desfaz e nao aprova
            if anterior is None:
                destino.unlink(missing_ok=True)
            else:
                destino.write_bytes(anterior)
            app.logger.error("regra recusada, o recalculo falhou:\n%s", texto)
            registro["erros_regra"] = ["a regra extraída não pôde ser calculada pelo motor; nada foi alterado"]
            (ANALISES / f"{analise_id}.json").write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
            return redirect(url_for("analise_contrato", analise_id=analise_id))
    resultado = "aprovada" if decisao == "aprovar" else "rejeitada"
    gravar_auditoria(AUDITORIA, {
        "quando": agora, "acao": "aprovacao_regra" if decisao == "aprovar" else "rejeicao_regra",
        "id": analise_id, "arquivo": registro["arquivo"], "pdf_sha256": registro["pdf_sha256"],
        "clientes": registro.get("clientes", []), "status": "regra_ativada" if decisao == "aprovar" else "regra_rejeitada",
        "motivos": [], "analise": {"cliente": regra["cliente"], "regra_id": "—", "campos": [
            {"campo": a, "valor": b, "clausula": c} for a, b, c in rc.linhas_resumo(regra)]},
        "regra_aprovada": regra if decisao == "aprovar" else None,
        "regra_sha256": hashlib.sha256(destino.read_bytes()).hexdigest() if destino else None,
        "substituiu_regra": anterior is not None,
    })
    registro["decisao_regra"] = {"resultado": resultado, "quando": agora}
    (ANALISES / f"{analise_id}.json").write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    return redirect(url_for("analise_contrato", analise_id=analise_id))


def pendentes_de_aprovacao():
    """Submissoes sem decisao sobre a regra: com regra proposta ou que o agente nao vinculou."""
    return [r for r in carregar_analises()
            if not r.get("decisao_regra") and (r.get("regra_proposta") or r["status"] == "pendente_aprovacao")]


def tabela_regras_em_vigor():
    linhas = ""
    for caminho in sorted((RAIZ / "regras").glob("*.json")):
        try:
            regra = json.loads(caminho.read_text(encoding="utf-8"))
            v = {item: valor for item, valor, _ in rc.linhas_resumo(regra)}
        except Exception:
            app.logger.exception("regra ilegivel: %s", caminho.name)
            continue
        aprovada = regra.get("status") == "aprovada"
        selo = ("<span class='badge ok'>Aprovada por uma pessoa</span>" if aprovada
                else "<span class='badge aviso'>Rascunho: transcrita à mão</span>")
        linhas += (f"<tr><td><a href='{url_for('pagina_site', arquivo='cs/' + slug(regra['cliente']) + '.html')}'>{esc(regra['cliente'])}</a></td>"
                   f"<td>{esc(v['Cobra'])}</td><td>{esc(v['Preço'])}</td><td>{esc(v['Contagem'])}</td>"
                   f"<td>{esc(v['Mínimo'])}</td><td>{esc(v['Nota'])}</td><td>{selo}</td></tr>")
    if not linhas:
        return '<div class="empty">Nenhuma regra em vigor.</div>'
    return ("<div class='table-wrap'><table><tr><th>Cliente</th><th>Cobra</th><th>Preço</th><th>Contagem</th>"
            f"<th>Mínimo</th><th>Nota</th><th>Situação</th></tr>{linhas}</table></div>")


@app.get("/aprovacoes")
def aprovacoes():
    pendentes = pendentes_de_aprovacao()
    em_vigor = len(list((RAIZ / "regras").glob("*.json")))
    cartoes = (f"<div class='metrics'><div class='metric'><div class='num'>{len(pendentes)}</div>aguardando decisão</div>"
               f"<div class='metric'><div class='num'>{em_vigor}</div>regras em vigor</div></div>")
    aviso = ("" if pendentes else "<div class='empty'>Nada aguardando decisão.</div>")
    corpo = ("<section class='page-intro'><h1>Aprovações</h1><p class='sub'>O que aguarda a sua decisão e as regras que "
             "hoje valem nos cálculos.</p></section>" + cartoes
             + "<h2>Aguardando decisão</h2>"
             + "<p class='peq'>Abra a análise para conferir a regra extraída do contrato e aprovar ou rejeitar.</p>"
             + (tabela_historico(pendentes) if pendentes else aviso)
             + "<h2>Regras em vigor</h2>"
             + "<p class='peq'>Estas são as regras que o sistema usa agora. Ao aprovar um contrato, a regra do cliente é "
               "substituída e a anterior fica guardada em regras/versoes.</p>"
             + tabela_regras_em_vigor())
    return pagina("Aprovações", corpo, "aprovacoes")


class _Saida(io.StringIO):
    def reconfigure(self, **_opcoes):  # os modulos do projeto chamam sys.stdout.reconfigure
        pass


def capturar(funcao):
    """Roda uma funcao do projeto e devolve (ok, texto) com tudo o que ela imprimiu."""
    saida, ok = _Saida(), True
    try:
        with contextlib.redirect_stdout(saida):
            funcao()
    except SystemExit as fim:
        ok = not fim.code
    except Exception as exc:
        app.logger.exception("falha em %s", getattr(funcao, "__name__", "acao"))
        saida.write(f"\nFalhou: {exc}\n")
        ok = False
    return ok, saida.getvalue()


def acao_gerar():
    import gerar_paginas
    import gerar_proposta
    gerar_paginas.main()
    gerar_proposta.main()


def acao_calcular():
    import calcular
    calcular.main()


def acao_verificar():
    import verificar_auditoria
    verificar_auditoria.main()


def acao_testes():
    resultado = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(
        unittest.defaultTestLoader.discover(str(RAIZ / "tests")))
    if not resultado.wasSuccessful():
        raise RuntimeError("há testes falhando")


def acao_analisar_exemplos():
    for pdf in sorted((RAIZ / "dados" / "contratos").glob("*.pdf")):
        r = processar_pdf(pdf.name, pdf.read_bytes())
        cliente = ", ".join(r["clientes"]) or r["analise"].get("cliente", "")
        print(f"{pdf.name}: {r['status']} | regra {r['analise']['regra_id']} | {cliente}")


ACOES = {
    "gerar": ("Atualizar páginas e proposta",
              "Recalcula tudo e regenera as páginas de Financeiro, Customer Success, RH, Comercial e a proposta.", acao_gerar),
    "calcular": ("Conferir as notas emitidas",
                 "Refaz todas as notas emitidas na base e mostra quais batem e a hipótese de causa das divergências.", acao_calcular),
    "analisar": ("Analisar os contratos de exemplo",
                 "O agente lê os 6 contratos do kit (usa a IA, leva cerca de 1 minuto) e preenche Contratos e Aprovações.",
                 acao_analisar_exemplos),
    "verificar": ("Verificar a auditoria", "Confere a cadeia de hashes do log de auditoria.", acao_verificar),
    "testes": ("Rodar os testes", "Executa os testes automáticos do projeto.", acao_testes),
}


def chave_atual():
    return os.environ.get("NVIDIA_API_KEY", "").strip()


def salvar_chave(valor):
    valor = valor.strip()
    if not re.fullmatch(r"nvapi-[A-Za-z0-9_\-]{20,}", valor):
        raise ValueError("A chave da NVIDIA deve começar com nvapi-.")
    caminho = RAIZ / ".env"
    linhas = ([l for l in caminho.read_text(encoding="utf-8").splitlines() if not l.startswith("NVIDIA_API_KEY=")]
              if caminho.exists() else [])
    caminho.write_text("\n".join(linhas + [f"NVIDIA_API_KEY={valor}"]) + "\n", encoding="utf-8")
    os.environ["NVIDIA_API_KEY"] = valor


@app.route("/sistema", methods=["GET", "POST"])
def sistema():
    titulo, ok, resultado = "", True, ""
    if request.method == "POST":
        qual = request.form.get("acao", "")
        if qual == "chave":
            titulo = "Chave da NVIDIA"
            try:
                salvar_chave(request.form.get("chave", ""))
                resultado = "Chave salva neste computador. A análise de contratos já pode ser usada."
            except ValueError as exc:
                ok, resultado = False, str(exc)
        elif qual in ACOES:
            titulo = ACOES[qual][0]
            if qual == "analisar" and not chave_atual():
                ok, resultado = False, "A chave de acesso à IA não está configurada neste servidor (arquivo .env)."
            else:
                ok, resultado = capturar(ACOES[qual][2])
        else:
            abort(400)
    chave = chave_atual()
    estado = (f'<span class="badge ok">configurada · termina em {esc(chave[-4:])}</span>' if chave
              else '<span class="badge rev">não configurada</span>')
    cartoes = "".join(
        f"<div class='card'><h3>{esc(t)}</h3><p>{esc(d)}</p><form method='post' data-carregando='Executando, aguarde'>"
        f"<input type='hidden' name='acao' value='{k}'><button class='button' type='submit'>Executar</button></form></div>"
        for k, (t, d, _funcao) in ACOES.items())
    saida = (f"<h2>{esc(titulo)} · {'concluído' if ok else 'com problema'}</h2>"
             f"<div class='console'>{esc(resultado)}</div>") if titulo else ""
    corpo = f"""
    <section class="page-intro"><h1>Sistema</h1><p class="sub">Tudo o que o projeto faz fica aqui, sem terminal.</p></section>
    <h2>Chave da NVIDIA {estado}</h2>
    <div class="card"><p>Usada só pela análise de contratos. Fica no arquivo .env deste computador e nunca é exibida.</p>
    <form method="post" class="key-form"><input type="hidden" name="acao" value="chave">
    <input type="password" name="chave" placeholder="nvapi-..." autocomplete="off" required>
    <button class="button" type="submit">Salvar chave</button></form></div>
    <h2>Ações</h2><div class="grid">{cartoes}</div>{saida}
    """
    return pagina("Sistema", corpo, "sistema")


@app.errorhandler(413)
def arquivo_grande(_erro):
    return pagina("Contratos", '<div class="error-box">O PDF deve ter no máximo 10 MB.</div>', "contratos"), 413


if __name__ == "__main__":
    if not (SITE / "index.html").exists():  # primeira vez: gera as paginas sozinho
        capturar(acao_gerar)
    app.run(host="127.0.0.1", port=5000, debug=False)
