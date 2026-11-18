"""Gera as paginas HTML por perfil de usuario em saida/site/.

  index.html            entrada interna, com a lista de paginas
  financeiro.html       fechamento: todas as notas, o que bate e a revisao sistemica
  cs/<cliente>.html     detalhe por cliente (regra, clausulas, ponte de conciliacao)
  comercial.html        o que o sistema sabe cobrar e o que ainda nao cabe
  rh/<cliente>.html     extrato de UM cliente, em linguagem simples. Um arquivo por cliente: o isolamento e
                        real porque o arquivo so contem os dados daquele cliente.
Uso: python src/gerar_paginas.py
"""
import base64
import html
import sqlite3
import sys
import unicodedata
from calendar import monthrange
from datetime import date
from pathlib import Path

from calcular import (DB, RAIZ, analisar_notas, brl, calcular, carregar_regras, eventos_do_cliente,
                      foto_processamento, resumo, sem_cargas_desfeitas, so_titulares)
from conciliar import GRUPOS, datas, planos, ponte, ponte_pico

SITE = RAIZ / "saida" / "site"
esc = html.escape
MESES = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]
MESES[2] = "março"

ESTILO = """
@import url("https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;700;800&display=swap");
:root{--navy:#0e2841;--deep:#081420;--ciano:#00c2ff;--logo-azul:#257cae;--logo-verde:#06c4a9;
--cta:#0080a8;--link:#00688c;--surface:#f4f8fd;--branco:#fff;--borda:#d7e0ea;--neutro:#4a5a68;
--erro:#b3261e;--ok:#087457;--aviso:#805400;--shadow:0 1px 2px #0e28410f,0 10px 24px -14px #0e28412e}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;font-family:Manrope,ui-sans-serif,system-ui,sans-serif;color:var(--neutro);background:var(--branco);line-height:1.6}
.skip{position:absolute;left:-9999px;top:10px;background:var(--branco);color:var(--navy);padding:8px 12px;z-index:20}
.skip:focus{left:12px}
.topbar{background:var(--navy);border-bottom:3px solid var(--ciano);color:var(--surface)}
.topbar-inner{max-width:1180px;min-height:74px;margin:0 auto;padding:0 28px;display:flex;align-items:center;justify-content:space-between;gap:28px}
.brand{display:flex;align-items:center;gap:18px;min-width:0}.brand img{width:154px;height:auto;display:block}
.brand-home{display:block;border-radius:8px}.brand-home:focus-visible{outline:3px solid #ffffff80;outline-offset:5px}
.context{padding-left:18px;border-left:1px solid #ffffff38;font-size:13px;font-weight:700;line-height:1.2;color:#dfeaf5}
nav{display:flex;align-items:center;gap:6px}nav a{color:#dfeaf5;font-size:14px;font-weight:700;text-decoration:none;padding:10px 12px;border-radius:8px}
nav a:hover,nav a.active{background:#ffffff12;color:var(--branco)}
.secure-chip{display:inline-flex;align-items:center;gap:8px;color:#dfeaf5;font-size:13px;font-weight:700}
.secure-chip:before{content:"";width:8px;height:8px;border-radius:50%;background:var(--logo-verde);box-shadow:0 0 0 4px #06c4a924}
main{max-width:1180px;margin:0 auto;padding:48px 28px 72px}
.page-intro{padding:0 0 30px;border-bottom:1px solid var(--borda);margin-bottom:34px;position:relative}
.page-intro:after{content:"";position:absolute;left:0;bottom:-2px;width:72px;height:3px;background:linear-gradient(90deg,var(--logo-azul),var(--logo-verde));border-radius:3px}
h1{color:var(--navy);font-size:clamp(32px,4vw,46px);line-height:1.12;letter-spacing:-.035em;margin:0 0 10px;max-width:850px}
h2{color:var(--navy);font-size:24px;line-height:1.25;letter-spacing:-.02em;margin:44px 0 14px}
h3{color:var(--navy);font-size:16px;line-height:1.4;margin:20px 0 8px}
.sub{font-size:17px;max-width:760px;margin:0;color:var(--neutro)}
p,li{max-width:78ch}.section-lead{max-width:760px}
.card{background:var(--branco);border:1px solid var(--borda);border-radius:16px;padding:22px 24px;box-shadow:var(--shadow);margin:14px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.metrics{display:grid;grid-template-columns:repeat(3,1fr);border:1px solid var(--borda);border-radius:16px;overflow:hidden;background:var(--surface);margin:8px 0 38px}
.metrics .metric{padding:24px 26px;border-right:1px solid var(--borda);min-height:112px}.metrics .metric:last-child{border-right:0}
.num{font-size:34px;font-weight:800;color:var(--navy);letter-spacing:-.04em;line-height:1.05;margin-bottom:8px;font-variant-numeric:tabular-nums}
.table-wrap{width:100%;overflow-x:auto;border:1px solid var(--borda);border-radius:14px;background:var(--branco);box-shadow:0 8px 24px -22px var(--navy);margin:10px 0}
table{width:100%;border-collapse:collapse;background:var(--branco);font-size:14px;margin:0}
th,td{padding:12px 14px;border-bottom:1px solid var(--borda);text-align:left;vertical-align:top}
tr:last-child td{border-bottom:0}tbody tr:hover td{background:#f8fbfe}
th{background:#eaf1f9;color:var(--navy);font-size:12px;line-height:1.35;font-weight:800}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.badge{display:inline-flex;align-items:center;gap:6px;padding:4px 9px;border-radius:6px;font-size:12px;font-weight:800;white-space:nowrap}
.badge:before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.ok{background:#e3f5ef;color:var(--ok)}.rev{background:#fdeceb;color:var(--erro)}.aviso{background:#fff3d6;color:var(--aviso)}
.nota{border:1px solid #b9dce8;border-left:5px solid var(--cta);background:#f3fbfe;padding:14px 16px;border-radius:0 10px 10px 0;margin:14px 0}
.review{border-color:#efc9c6;border-left-color:var(--erro);background:#fff8f7}.review h3{margin-top:0}
.ponte td:first-child{width:64%}.ponte .tot td{border-top:2px solid var(--logo-azul)}
.tot td{font-weight:800;color:var(--navy);background:#eef6fc}
details{margin:8px 0;border-bottom:1px solid var(--borda);padding:0 0 8px}summary{cursor:pointer;color:var(--link);font-weight:700;padding:8px 0}
.technical-details{margin:22px 0;background:var(--surface);border:1px solid var(--borda);border-radius:12px;padding:4px 16px}.technical-details[open]{padding-bottom:14px}
.recon{border:1px solid var(--borda);border-radius:16px;overflow:hidden;background:var(--branco);margin:16px 0 10px}
.recon-row{display:grid;grid-template-columns:92px minmax(0,1fr) auto;gap:16px;align-items:center;padding:17px 20px;border-bottom:1px solid var(--borda)}
.recon-row:last-child{border-bottom:0}.recon-row.start,.recon-row.end{background:var(--surface)}.recon-row.end{border-top:2px solid var(--logo-azul)}
.recon-count{font-size:23px;font-weight:800;color:var(--navy);font-variant-numeric:tabular-nums;white-space:nowrap}.recon-label strong{display:block;color:var(--navy)}
.recon-label span{display:block;font-size:13px;color:#627382;margin-top:2px}.recon-value{font-size:13px;font-weight:700;color:var(--navy);white-space:nowrap}
.recon-tag{display:inline-block;padding:4px 8px;border-radius:6px;background:#e3f5ef;color:var(--ok);font-size:11px;font-weight:800;white-space:nowrap}.recon-tag.attention{background:#fff3d6;color:var(--aviso)}
.peq{font-size:13px}.muted{color:#677886}
a{color:var(--link);text-underline-offset:3px}a:hover{color:var(--navy)}
a:focus-visible,summary:focus-visible{outline:3px solid #00688c55;outline-offset:3px;border-radius:4px}
.role-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:30px 0 42px}.role-card{display:grid;grid-template-columns:54px 1fr;gap:18px;align-items:start;background:var(--branco);border:1px solid var(--borda);border-radius:16px;padding:24px;text-decoration:none;color:var(--neutro);box-shadow:var(--shadow)}
.role-card:hover{border-color:#91b9cb;color:var(--neutro)}.role-card img{width:42px;height:42px;padding:9px;border-radius:12px;background:var(--surface)}
.role-card h3{margin:0 0 5px;font-size:19px}.role-card p{margin:0 0 12px}.role-card strong{color:var(--link);font-size:14px}
.link-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 24px;padding:0;list-style:none}.link-list a{display:block;padding:10px 0;border-bottom:1px solid var(--borda);font-weight:700;text-decoration:none}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}.filter-button{border:1px solid var(--borda);border-radius:8px;background:#fff;color:var(--navy);padding:8px 12px;font:700 13px/1.2 Manrope,sans-serif;cursor:pointer}.filter-button:hover,.filter-button[aria-pressed=true]{background:var(--navy);border-color:var(--navy);color:#fff}
footer{margin-top:56px;padding-top:22px;border-top:1px solid var(--borda);font-size:12px;color:#627382}
@media(max-width:760px){.topbar-inner{align-items:flex-start;flex-direction:column;padding:18px 20px}.brand{width:100%;justify-content:space-between}.context{border-left:0;padding-left:0;text-align:right}nav{width:100%;overflow-x:auto}main{padding:34px 18px 54px}.metrics{grid-template-columns:1fr}.metrics .metric{border-right:0;border-bottom:1px solid var(--borda)}.metrics .metric:last-child{border-bottom:0}.role-grid,.link-list{grid-template-columns:1fr}.table-wrap{border-radius:10px}.recon-row{grid-template-columns:72px 1fr;padding:14px}.recon-tag,.recon-value{grid-column:2;justify-self:start}h1{font-size:32px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@media print{.topbar nav,.skip{display:none}.topbar{background:var(--branco);color:var(--navy);border-bottom:1px solid var(--borda)}.context{color:var(--navy)}main{max-width:none;padding:24px}.card,.role-card{box-shadow:none}}
"""


def slug(nome):
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    return "-".join(s.split())


def nome_comp(comp):
    ano, mes = comp.split("-")
    return f"{MESES[int(mes) - 1]} de {ano}"


def dt(iso):
    """2026-10-26 09:00:00 -> 26/10/2026 às 09:00"""
    d = date.fromisoformat(iso[:10])
    return f"{d:%d/%m/%Y}" + (f" às {iso[11:16]}" if len(iso) > 10 else "")


def pagina(titulo, corpo, nav=True, base="", contexto="Operação de fechamento"):
    logo = base64.b64encode((RAIZ / "dados" / "marca" / "logo-branco.png").read_bytes()).decode()
    ativo = ("financeiro" if "Financeiro" in titulo else "comercial" if "Comercial" in titulo
             else "inicio" if "Fechamento do mês" in titulo else "")

    def link(href, texto, chave):
        classe = "active" if ativo == chave else ""
        return f'<a class="{classe}" href="{base}{href}">{texto}</a>'

    menu = (f'<nav aria-label="Navegação principal">{link("index.html", "Início", "inicio")}'
            f'{link("financeiro.html", "Financeiro", "financeiro")}'
            f'{link("comercial.html", "Comercial", "comercial")}'
            f'<a href="http://127.0.0.1:5000/contratos">Contratos</a>'
            f'<a href="http://127.0.0.1:5000/aprovacoes">Aprovações</a>'
            f'<a href="http://127.0.0.1:5000/sistema">Sistema</a></nav>') if nav else ""
    logo_href = f"{base}index.html" if nav else "#conteudo"
    logo_label = "Voltar ao início" if nav else "Voltar ao início do extrato"
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(titulo)}</title>'
            f'<style>{ESTILO}</style></head><body><a class="skip" href="#conteudo">Ir para o conteúdo</a>'
            f'<header class="topbar"><div class="topbar-inner"><div class="brand"><a class="brand-home" href="{logo_href}" '
            f'aria-label="{logo_label}"><img alt="Medipreço" src="data:image/png;base64,{logo}"></a>'
            f'<span class="context">{esc(contexto)}</span></div>{menu}</div></header>'
            f'<main id="conteudo">{corpo}</main></body></html>')


def icone(nome):
    dados = base64.b64encode((RAIZ / "dados" / "marca" / "icones" / f"{nome}.svg").read_bytes()).decode()
    return f'<img alt="" aria-hidden="true" src="data:image/svg+xml;base64,{dados}">'


def tabela(conteudo, classe=""):
    return f'<div class="table-wrap"><table class="{classe}">{conteudo}</table></div>'


def badge(texto, tipo):
    return f'<span class="badge {tipo}">{esc(texto)}</span>'


# ---------- descricao da regra em linguagem simples ----------

def descrever(regra):
    b, p, c, m, n, pg = (regra[k] for k in ("base", "preco", "contagem", "minimo", "nota", "pagamento"))
    unidade = "titular" if b["tipo"] == "titular" else "vida"
    if p["tipo"] == "valor_unico":
        preco = f"R$ {brl(p['valor'])} por {unidade}"
    elif p["tipo"] == "por_plano":
        preco = " · ".join(f"plano {k}: R$ {brl(v)}" for k, v in p["planos"].items()) + f" por {unidade}"
    else:
        partes = [(f"até {f['ate']:,}".replace(",", ".") if f["ate"] else "acima") + f": R$ {brl(f['valor'])}"
                  for f in p["faixas"]]
        preco = " · ".join(partes) + f" por {unidade} (faixa {p['modo']})"
    contagem = {
        "foto_dia": lambda: f"foto da base no dia {c['dia']} do mês " +
                            ("anterior ao de referência" if c["mes"] == "anterior" else "de referência"),
        "ativo_1_dia": lambda: "quem ficou ativo ao menos 1 dia no mês conta inteiro",
        "pro_rata_dia": lambda: "proporcional aos dias em que cada vida esteve ativa",
        "pico_mes": lambda: "maior número de vidas ativas em um dia do mês",
    }[c["metodo"]]()
    return [
        ("Quem é cobrado", "todas as vidas (titular e dependentes)" if b["tipo"] == "vida" else "só os titulares", b["clausula"]),
        ("Preço", preco, p["clausula"]),
        ("Como contamos", contagem, c["clausula"]),
        ("Mínimo", f"mínimo de {m['vidas']} vidas por mês" if m else "não há", m["clausula"] if m else "—"),
        ("Nota fiscal", "uma nota para o cliente" if n["tipo"] == "unica"
         else "uma nota por empresa, com o valor dividido pelas vidas de cada uma", n["clausula"]),
        ("Pagamento", "depois do mês (pós-pago)" if pg["tipo"] == "pos" else "antes do mês (pré-pago), com acerto depois", pg["clausula"]),
    ]


def tabela_regra(regra):
    linhas = "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td><td>cláusula {esc(str(c))}</td></tr>"
                     for a, b, c in descrever(regra))
    return tabela(f"<tr><th>Item</th><th>O que o contrato diz</th><th>Onde</th></tr>{linhas}")


# ---------- pontes de conciliacao ----------

ROT_RH = {
    GRUPOS[("saida", True)]: ("-", "Saíram depois da data de corte. Continuam cobradas neste mês e saem da cobrança no mês seguinte."),
    GRUPOS[("saida", False)]: ("-", "Saíram até a data de corte, mas só foram informadas depois. O tratamento delas depende do contrato e será confirmado pela Medipreço."),
    GRUPOS[("entrada", True)]: ("+", "Entraram depois da data de corte. Entram na cobrança no mês seguinte."),
    GRUPOS[("entrada", False)]: ("+", "Entraram até a data de corte, mas só foram informadas depois. Não foram cobradas neste mês."),
    GRUPOS[("troca", True)]: ("~", "Trocaram de plano depois da data de corte."),
}
ROT_INTERNO = {k: (v[0], k) for k, v in ROT_RH.items()}


def lista_pessoas(grupos, rotulos, interno):
    partes = []
    for nome, linhas in grupos.items():
        if not linhas:
            continue
        cab = "<tr><th>Pessoa</th><th>Plano</th><th>Data informada</th><th>Chegou ao sistema em</th>" + \
              ("<th>Origem</th>" if interno else "") + "</tr>"
        corpo = "".join(
            f"<tr><td>{esc(p)}</td><td>{esc(antes or depois or '')}</td><td>{dt(ev[5])}</td><td>{dt(ev[4])}</td>"
            + (f"<td>{esc(ev[7])}</td>" if interno else "") + "</tr>"
            for p, _c, antes, depois, ev in sorted(linhas, key=lambda l: l[4][5]))
        resumo_nome = rotulos[nome][1].split(".")[0]
        partes.append(f"<details><summary>{esc(resumo_nome)} ({len(linhas)})</summary>{tabela(cab + corpo)}</details>")
    return "".join(partes)


def bloco_ponte_foto_rh(regra, corte_a, corte_b, a, b, grupos):
    """Conta visual que explica por que a base posterior difere da usada na cobrança."""
    va, vb = calcular(regra, *resumo(a)), calcular(regra, *resumo(b))
    config = {
        ("saida", True): ("-", "Saíram depois do corte", "Entram na próxima competência", "próximo mês", False),
        ("saida", False): ("-", "Já tinham saído, mas a informação chegou depois", "Não estavam na base disponível no corte", "avaliar ajuste", True),
        ("entrada", True): ("+", "Entraram depois do corte", "Entram na próxima competência", "próximo mês", False),
        ("entrada", False): ("+", "Já tinham entrado, mas a informação chegou depois", "Não entraram na nota deste mês", "avaliar ajuste", True),
    }
    linhas, soma = [], len(a)
    for chave, (sinal, titulo, detalhe, tag, atencao) in config.items():
        grupo = grupos.get(GRUPOS[chave], [])
        if not grupo:
            continue
        soma += len(grupo) if sinal == "+" else -len(grupo)
        classe = "recon-tag attention" if atencao else "recon-tag"
        linhas.append(
            f"<div class='recon-row'><div class='recon-count'>{sinal} {len(grupo)}</div>"
            f"<div class='recon-label'><strong>{esc(titulo)}</strong><span>{esc(detalhe)} · {esc(datas(grupo))}</span></div>"
            f"<span class='{classe}'>{esc(tag)}</span></div>"
        )
    trocas = grupos.get(GRUPOS[("troca", True)], [])
    if trocas:
        linhas.append(
            f"<div class='recon-row'><div class='recon-count'>~ {len(trocas)}</div>"
            f"<div class='recon-label'><strong>Trocaram de plano</strong><span>Muda o valor, não a quantidade · {esc(datas(trocas))}</span></div>"
            f"<span class='recon-tag attention'>revisar valor</span></div>"
        )
    conta = (
        f"<div class='recon'><div class='recon-row start'><div class='recon-count'>{len(a)}</div>"
        f"<div class='recon-label'><strong>Vidas usadas na cobrança</strong><span>Base disponível em {dt(corte_a)}</span></div>"
        f"<div class='recon-value'>R$ {brl(va['valor'])}</div></div>{''.join(linhas)}"
        f"<div class='recon-row end'><div class='recon-count'>= {len(b)}</div>"
        f"<div class='recon-label'><strong>Vidas na base depois das atualizações</strong><span>Posição em {dt(corte_b)}</span></div>"
        f"<div class='recon-value'>R$ {brl(vb['valor'])}</div></div></div>"
    )
    confere = "A conta fecha." if soma == len(b) else f"A conta não fecha: os movimentos somam {soma}, mas a base tem {len(b)}."
    return (conta + f"<p class='peq muted'>{confere}</p>"
            + f"<details class='technical-details'><summary>Ver pessoas e datas que formam a diferença</summary>"
            + lista_pessoas(grupos, ROT_RH, False) + "</details>")


def bloco_ponte_foto(regra, comp, corte_a, corte_b, a, b, grupos, interno):
    if not interno:
        return bloco_ponte_foto_rh(regra, corte_a, corte_b, a, b, grupos)
    rotulos = ROT_INTERNO if interno else ROT_RH
    va, vb = calcular(regra, *resumo(a)), calcular(regra, *resumo(b))
    linhas, soma = [], len(a)
    for chave in (("saida", True), ("saida", False), ("entrada", True), ("entrada", False)):
        g = grupos.get(GRUPOS[chave], [])
        sinal, texto = rotulos[GRUPOS[chave]]
        soma += len(g) if sinal == "+" else -len(g)
        det = f'<br><span class="peq">por data informada: {esc(datas(g))}</span>' if g else ""
        linhas.append(f"<tr><td>({sinal}) {esc(texto)}{det}</td><td class='n'>{len(g)}</td><td></td></tr>")
    trocas = grupos.get(GRUPOS[("troca", True)], [])
    if trocas:
        linhas.append(f"<tr><td>(~) {esc(rotulos[GRUPOS[('troca', True)]][1])}<br><span class='peq'>muda o valor, não a quantidade</span></td>"
                      f"<td class='n'>{len(trocas)}</td><td></td></tr>")
    fecha = "bate" if soma == len(b) else "NÃO bate"
    ponte = (f"<tr><th>Item</th><th class='n'>Vidas</th><th class='n'>Valor</th></tr>"
            f"<tr class='tot'><td>Vidas cobradas (base em {dt(corte_a)}) <span class='peq'>{esc(planos(a))}</span></td>"
            f"<td class='n'>{len(a)}</td><td class='n'>R$ {brl(va['valor'])}</td></tr>{''.join(linhas)}"
            f"<tr class='tot'><td>Vidas na base em {dt(corte_b)} <span class='peq'>{esc(planos(b))}</span></td>"
            f"<td class='n'>{len(b)}</td><td class='n'>R$ {brl(vb['valor'])}</td></tr>")
    return (tabela(ponte, "ponte") + f"<p class='peq muted'>Conferência: {len(a)} − saídas + entradas = {soma} → {fecha} com {len(b)}.</p>"
            + lista_pessoas(grupos, rotulos, interno))


def bloco_pico(regra, eventos, titulares, comp):
    pico, fim, a, b, grupos = ponte_pico(regra, eventos, titulares, comp)
    por_plano, por_cnpj = resumo(a)
    calc = calcular(regra, por_plano, por_cnpj)
    rot = {"saiu depois do pico": "-", "entrou depois do pico": "+"}
    linhas, soma = [], len(a)
    for nome, g in grupos.items():
        sinal = rot.get(nome, "~")
        soma += len(g) if sinal == "+" else -len(g) if sinal == "-" else 0
        det = f'<br><span class="peq">por data informada: {esc(datas(g))}</span>' if g else ""
        linhas.append(f"<tr><td>({sinal}) {esc(nome)}{det}</td><td class='n'>{len(g)}</td></tr>")
    rateio = "".join(f"<tr><td>{esc(c)}</td><td class='n'>{por_cnpj.get(c, 0)}</td>"
                     f"<td class='n'>{100 * por_cnpj.get(c, 0) / len(a):.1f}%</td><td class='n'>R$ {brl(calc['notas'].get(c, 0))}</td></tr>"
                     for c in regra["cnpjs"])
    ponte = (f"<tr><th>Item</th><th class='n'>Vidas</th></tr>"
            f"<tr class='tot'><td>Pico de vidas no mês (em {pico:%d/%m})</td><td class='n'>{len(a)}</td></tr>{''.join(linhas)}"
            f"<tr class='tot'><td>Vidas ativas no último dia ({fim:%d/%m})</td><td class='n'>{len(b)}</td></tr>")
    rateio_html = (f"<tr><th>Empresa (CNPJ)</th><th class='n'>Vidas</th>"
                   f"<th class='n'>%</th><th class='n'>Valor pelo contrato</th></tr>{rateio}")
    return (tabela(ponte, "ponte") +
            f"<p class='peq muted'>Conferência: {len(a)} − saídas + entradas = {soma} → {'bate' if soma == len(b) else 'NÃO bate'} com {len(b)}.</p>"
            f"<h3>Rateio entre as empresas, no dia do pico</h3>{tabela(rateio_html)}"
            + lista_pessoas(grupos, {k: ("", k) for k in grupos}, True))


def ponte_foto_de(con, regra, eventos, titulares, comp):
    """(corte_a, corte_b, a, b, grupos) para contratos de foto no mes de referencia."""
    marcas = ",".join("?" * len(regra["cnpjs"]))
    corte_a = con.execute(f"select max(contagem_em) from notas_emitidas where competencia = ? "
                          f"and cnpj_tomador in ({marcas})", [comp] + regra["cnpjs"]).fetchone()[0]
    ano, mes = map(int, comp.split("-"))
    corte_b = f"{date(ano, mes, monthrange(ano, mes)[1]).isoformat()} 23:59:59"
    dia_foto = date(ano, mes, regra["contagem"]["dia"]).isoformat()
    a, b, grupos = ponte(regra, eventos, titulares, corte_a, corte_b, dia_foto)
    return corte_a, corte_b, a, b, grupos


def e_foto_referencia(regra):
    return regra["contagem"]["metodo"] == "foto_dia" and regra["contagem"]["mes"] == "referencia"


# ---------- paginas ----------

JS_FILTROS = """
(function(){
  var primeira=document.querySelector('tr[data-status]');
  if(!primeira){return;}
  var corpo=primeira.parentNode;
  var linhas=Array.prototype.slice.call(corpo.querySelectorAll('tr[data-status]'));
  var seletor=document.getElementById('filtro-cliente');
  var botoes=document.querySelectorAll('.filter-button');
  var contagem=document.getElementById('contagem-notas');
  var status='todas';
  function aplicar(){
    var cliente=seletor.value, visiveis=0;
    linhas.sort(function(a,b){
      if(cliente==='todos'){return a.dataset.ordem-b.dataset.ordem;}
      return a.dataset.comp<b.dataset.comp?-1:(a.dataset.comp>b.dataset.comp?1:0);
    });
    linhas.forEach(function(l){
      var mostrar=(cliente==='todos'||l.dataset.cliente===cliente)&&(status==='todas'||l.dataset.status===status);
      l.hidden=!mostrar;
      if(mostrar){visiveis++;}
      corpo.appendChild(l);
    });
    contagem.textContent=visiveis+' de '+linhas.length+' notas';
  }
  seletor.addEventListener('change',aplicar);
  botoes.forEach(function(b){
    b.addEventListener('click',function(){
      status=b.dataset.filter;
      botoes.forEach(function(x){x.setAttribute('aria-pressed',x===b?'true':'false');});
      aplicar();
    });
  });
  aplicar();
})();
"""


def pg_financeiro(linhas):
    exc = [l for l in linhas if not l["bate"]]
    rotulo_divergencias = "nota com divergência" if len(exc) == 1 else "notas com divergências"
    cards = (f'<div class="metrics"><div class="metric"><div class="num">{len(linhas)}</div>notas conferidas</div>'
             f'<div class="metric"><div class="num">{len(linhas) - len(exc)}</div>notas corretas</div>'
             f'<div class="metric"><div class="num">{len(exc)}</div>{rotulo_divergencias}</div></div>')
    corpo = "".join(
        f"<tr data-status='{'correta' if l['bate'] else 'divergencia'}' data-cliente='{slug(l['cliente'])}' data-comp='{l['competencia']}' data-ordem='{i}'>"
        f"<td><a href='cs/{slug(l['cliente'])}.html'>{esc(l['cliente'])}</a></td><td>{l['competencia']}</td>"
        f"<td class='n'>{l['qtd_emitida']:.0f}</td><td class='n'>R$ {brl(l['valor_emitido'])}</td>"
        f"<td class='n'>R$ {brl(l['hoje_valor'])}</td><td>{badge('correta', 'ok') if l['bate'] else badge('divergência', 'rev')}</td>"
        f"<td class='n'>R$ {brl(l['contrato_valor'])}</td><td class='n'>{brl(l['dif_contrato'])}</td></tr>"
        for i, l in enumerate(sorted(linhas, key=lambda item: (item["bate"], item["cliente"], item["competencia"]))))
    opcoes = "".join(f"<option value='{slug(n)}'>{esc(n)}</option>" for n in sorted({l["cliente"] for l in linhas}))
    detalhes = ""
    for l in exc:
        hip = next(iter(l["diagnostico"]), None)
        unidade_esperada = "titulares" if l["regra"]["base"]["tipo"] == "titular" else "vidas"
        causa = (f"A quantidade emitida coincide com <b>{hip['vidas']:.0f} vidas</b>, mas o contrato cobra "
                 f"<b>{l['hoje_vidas']:.0f} {unidade_esperada}</b>." if hip else "O valor não coincide com nenhuma hipótese testada.")
        detalhes += (f"<div class='nota review'><h3>{esc(l['cliente'])} · {l['competencia']}</h3>"
                     f"<p>{causa} Diferença: <b>R$ {brl(l['valor_emitido'] - l['hoje_valor'])}</b>.</p>"
                     f"<p class='peq'>Confirme a regra antes de corrigir a nota. "
                     f"<a href='cs/{slug(l['cliente'])}.html'>Abrir cliente</a></p></div>")
    return pagina("Financeiro · Medipreço", (
        f"<section class='page-intro'><h1>Fechamento</h1><p class='sub'>Conferência das notas emitidas e das diferenças encontradas.</p></section>"
        f"{cards}<h2>Notas com divergências</h2>{detalhes or '<p>Nenhuma divergência.</p>'}<h2>Notas</h2>"
        f"<div class='filters' role='group' aria-label='Filtrar notas'>"
        f"<label for='filtro-cliente' style='align-self:center;font-weight:700;color:var(--navy);font-size:13px'>Cliente</label>"
        f"<select id='filtro-cliente' style='border:1px solid #d7e0ea;border-radius:8px;padding:8px 12px;font:700 13px Manrope,sans-serif;color:#0e2841;background:#fff'>"
        f"<option value='todos'>Todos os clientes</option>{opcoes}</select>"
        f"<button class='filter-button' type='button' aria-pressed='true' data-filter='todas'>Todas ({len(linhas)})</button>"
        f"<button class='filter-button' type='button' aria-pressed='false' data-filter='correta'>Corretas ({len(linhas)-len(exc)})</button>"
        f"<button class='filter-button' type='button' aria-pressed='false' data-filter='divergencia'>Com divergências ({len(exc)})</button>"
        f"<span id='contagem-notas' class='peq muted' style='align-self:center'></span></div>"
        + tabela(f"<tr><th>Cliente</th><th>Competência</th><th class='n'>Quantidade</th><th class='n'>Nota emitida</th><th class='n'>Valor conferido</th>"
                  f"<th>Status</th><th class='n'>Pelo contrato</th><th class='n'>Dif. contrato × emitida</th></tr>{corpo}") +
        f"<details class='technical-details'><summary>Como ler as colunas de conferência</summary>"
        f"<p class='peq'>“Valor conferido” refaz a nota com a mesma base usada na emissão. “Pelo contrato” aplica o método de contagem descrito no contrato.</p></details>"
        f"<script>{JS_FILTROS}</script>"))


def pg_cs(regra, linhas, con, titulares):
    ponte_html = ""  # a ponte de conciliação foi retirada das páginas de cliente (pedido do usuário)
    comps = "".join(
        f"<tr><td>{l['competencia']}</td><td class='n'>R$ {brl(l['valor_emitido'])}</td>"
        f"<td class='n'>R$ {brl(l['contrato_valor'])}</td><td class='n'>R$ {brl(l['dif_contrato'])}</td>"
        f"<td>{badge('confere', 'ok') if l['bate'] else badge('revisar', 'rev')}</td></tr>" for l in linhas)
    lista = lambda xs: "".join(f"<li>{esc(x)}</li>" for x in xs) or "<li>nenhuma</li>"
    exc = [l for l in linhas if not l["bate"]]
    aviso = "".join(f"<div class='nota'><b>{l['competencia']}:</b> a nota não bate com o sistema. "
                    f"{' '.join(esc(d['hipotese']) + '.' for d in l['diagnostico'])}</div>" for l in exc)
    return pagina(f"{regra['cliente']} · CS", (
        f"<section class='page-intro'><h1>{esc(regra['cliente'])}</h1><p class='sub'>Cobranças, regra vigente e movimentos que explicam cada valor.</p>"
        f"<p><a href='../rh/{slug(regra['cliente'])}.html'>Visualizar como o RH recebe</a></p></section>{aviso}"
        f"<h2>Regra de cobrança</h2>{tabela_regra(regra)}"
        f"<details class='technical-details'><summary>Detalhes técnicos da regra</summary>"
        f"<p class='peq'>Modelo: {esc(regra['modelo'] or 'sem modelo no catálogo')} · CNPJs: {esc(', '.join(regra['cnpjs']))} · status: {esc(regra['status'])}</p>"
        f"<h3>Premissas adotadas</h3><ul>{lista(regra['premissas'])}</ul>"
        f"<h3>Pendências de interpretação</h3><ul>{lista(regra['pendencias'])}</ul></details>"
        f"<h2>Competências</h2>" + tabela(f"<tr><th>Competência</th><th class='n'>Nota emitida</th>"
        f"<th class='n'>Pelo contrato</th><th class='n'>Diferença</th><th>Status</th></tr>{comps}") +
        f"{ponte_html}"), base="../", contexto="Visão de Customer Success")


def pg_rh(regra, linhas, con, titulares):
    """Pagina do RH: so este cliente, em linguagem simples."""
    ult = linhas[-1]
    comp = ult["competencia"]
    eventos = eventos_do_cliente(con, regra["cnpjs"])
    unidade = "titulares" if regra["base"]["tipo"] == "titular" else "vidas"
    como = next(t for k, t, _ in descrever(regra) if k == "Como contamos")
    clausula = next(c for k, _, c in descrever(regra) if k == "Como contamos")
    estado_emissao = so_titulares(foto_processamento(eventos, ult["corte"]), regra["base"], titulares)
    calculo_emissao = calcular(regra, *resumo(estado_emissao))

    def quantidade(qtd):
        return f"{qtd:.0f}" if float(qtd).is_integer() else f"{qtd:.2f}".replace(".", ",")

    itens = "".join(
        f"<tr><td>{esc(descricao)}</td><td class='n'>{quantidade(qtd)}</td>"
        f"<td class='n'>R$ {brl(unitario)}</td><td class='n'>R$ {brl(qtd * unitario)}</td></tr>"
        for descricao, qtd, unitario in calculo_emissao["itens"]
    )
    criterios = tabela(
        f"<tr><th>Critério</th><th>Regra</th><th>Cláusula</th></tr>"
        f"<tr><td>Quem é contado</td><td>{'Somente titulares' if unidade == 'titulares' else 'Titulares e dependentes'}</td>"
        f"<td>{esc(str(regra['base']['clausula']))}</td></tr>"
        f"<tr><td>Data da base</td><td>{esc(como).capitalize()}</td><td>{esc(str(clausula))}</td></tr>"
        f"<tr><td>Preço</td><td>{esc(next(t for k, t, _ in descrever(regra) if k == 'Preço'))}</td>"
        f"<td>{esc(str(regra['preco']['clausula']))}</td></tr>"
    )
    memoria_calculo = tabela(
        f"<tr><th>Item</th><th class='n'>Quantidade</th><th class='n'>Valor unitário</th>"
        f"<th class='n'>Subtotal</th></tr>{itens}"
        f"<tr class='tot'><td>Total</td><td></td><td></td><td class='n'>R$ {brl(calculo_emissao['valor'])}</td></tr>"
    )
    ano, mes = comp.split("-")
    topo = (f"<section class='page-intro'><h1>Mensalidade de {esc(MESES[int(mes) - 1])}</h1>"
            f"<p class='sub'>{esc(regra['cliente'])} · {ano}</p></section>"
            f"<div class='metrics'><div class='metric'><div class='num'>{ult['qtd_emitida']:.0f}</div>"
            f"{'titulares cobrados' if unidade == 'titulares' else 'vidas cobradas'}</div>"
            f"<div class='metric'><div class='num'>R$ {brl(ult['valor_emitido'])}</div>valor da nota</div></div>"
            f"<h2>Critérios do contrato</h2>{criterios}"
            f"<h2>Cálculo da nota</h2><p>A base usada na emissão foi consultada em <b>{dt(ult['corte'])}</b>.</p>"
            f"{memoria_calculo}")
    if e_foto_referencia(regra) and ult["bate"]:
        ca, cb, a, b, g = ponte_foto_de(con, regra, eventos, titulares, comp)
        if len(a) == len(b) and not any(g.values()):
            corpo = (f"<p>Cobramos <b>{len(a)} {unidade}</b>, que é a posição da base em <b>{dt(ca)}</b>. "
                     f"No fim do mês a sua base continuava com <b>{len(b)}</b>: não houve nenhuma entrada ou saída "
                     f"depois da data de corte, então não há diferença a explicar.</p>")
        else:
            corpo = (f"<p>Cobramos <b>{len(a)} {unidade}</b>, que é a posição da base em <b>{dt(ca)}</b>. "
                     f"No fim do mês a sua base tinha <b>{len(b)}</b>. Veja abaixo de onde vem a diferença.</p>"
                     f"<h2>De {len(a)} para {len(b)}</h2>" + bloco_ponte_foto(regra, comp, ca, cb, a, b, g, False))
    elif regra["contagem"]["metodo"] == "foto_dia" and regra["contagem"]["mes"] == "anterior" and ult["bate"]:
        corpo = (f"<h2>Base utilizada</h2><p>A mensalidade de {esc(MESES[int(mes) - 1])} usa a base do mês anterior. "
                 f"Na consulta de <b>{dt(ult['corte'])}</b>, havia <b>{len(estado_emissao)} {unidade}</b> elegíveis. "
                 f"{'Dependentes não entram na cobrança.' if unidade == 'titulares' else ''}</p>")
    else:
        corpo = ("<div class='nota'>O extrato detalhado por pessoa para este contrato está em preparação. "
                 "Para conferir uma movimentação específica, fale com o atendimento da Medipreço.</div>")
    return pagina(f"Extrato · {regra['cliente']}", topo + corpo, nav=False, contexto="Extrato mensal do RH")


VOCABULARIO = [
    ("Quem é cobrado", "todas as vidas · só titulares", "pronto"),
    ("Preço", "valor único · por plano · por faixa de tamanho da base (cheia ou progressiva)", "pronto"),
    ("Como contar as vidas", "foto num dia fixo · ativo ao menos 1 dia · proporcional aos dias · pico do mês", "pronto"),
    ("Mínimo garantido", "em número de vidas", "pronto"),
    ("Nota fiscal", "uma nota · uma por empresa com valor dividido pelas vidas", "pronto"),
    ("Pagamento", "pós-pago · pré-pago", "pré-pago: o acerto da diferença ainda não é calculado"),
    ("Desfazer um arquivo errado", "carga anulada quando o suporte desfaz no mesmo dia", "premissa a confirmar"),
]
AINDA_NAO = ["mínimo em reais", "reajuste anual", "desconto por tempo de contrato", "taxa fixa de implantação",
             "média de vidas no mês", "cobrança por uso (consumo do benefício)", "acerto do pré-pago", "conciliação do pagamento da nota"]


def pg_comercial(regras):
    voc = "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td><td>{esc(c)}</td></tr>" for a, b, c in VOCABULARIO)
    clientes = "".join(
        f"<tr><td><a href='cs/{slug(r['cliente'])}.html'>{esc(r['cliente'])}</a></td>"
        f"<td>{esc(' · '.join(t for k, t, _ in descrever(r) if k in ('Quem é cobrado', 'Como contamos')))}</td>"
        f"<td>{esc('; '.join(r['pendencias']) or 'nenhuma')}</td></tr>" for r in regras)
    return pagina("Comercial · Medipreço", (
        "<section class='page-intro'><h1>Capacidades de cobrança</h1><p class='sub'>Consulte o que já pode ser oferecido antes de fechar uma proposta.</p></section>"
        f"<h2>Peças que o sistema já calcula</h2>" + tabela(f"<tr><th>Peça</th><th>Opções</th><th>Situação</th></tr>{voc}") +
        f"<details class='technical-details'><summary>O que ainda exige desenvolvimento</summary>"
        f"<ul>{''.join(f'<li>{esc(x)}</li>' for x in AINDA_NAO)}</ul></details>"
        f"<h2>Os contratos de hoje</h2>" + tabela(f"<tr><th>Cliente</th><th>Modelo de cobrança</th><th>Pontos em aberto</th></tr>{clientes}")))


def pg_index(regras):
    lis = lambda pre: "".join(f"<li><a href='{pre}/{slug(r['cliente'])}.html'>{esc(r['cliente'])}</a></li>" for r in regras)
    return pagina("Medipreço · Fechamento do mês", (
        "<section class='page-intro'><h1>Fechamento do mês</h1><p class='sub'>Acesse a área correspondente ao seu trabalho.</p></section>"
        "<div class='role-grid'>"
        f"<a class='role-card' href='financeiro.html'>{icone('wallet')}<span><h3>Financeiro</h3><p>Conferência de todas as notas e exceções antes do envio.</p><strong>Abrir fechamento</strong></span></a>"
        f"<a class='role-card' href='comercial.html'>{icone('trending-up')}<span><h3>Comercial</h3><p>Capacidades de cobrança e pontos que ainda exigem desenvolvimento.</p><strong>Consultar capacidades</strong></span></a></div>"
        f"<h2>Customer Success</h2><p class='section-lead'>Consulte as cobranças e os cálculos de cada cliente.</p><ul class='link-list'>{lis('cs')}</ul>"
        f"<h2>RH do cliente · arquivos para enviar a cada cliente</h2><p class='peq'>Cada arquivo contém só os dados daquele cliente. "
        f"Não compartilhe os outros.</p><ul class='link-list'>{lis('rh')}</ul>"))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    con = sqlite3.connect(DB)
    titulares = {p for (p,) in con.execute("select pessoa_id from pessoas where tipo = 'titular'")}
    linhas = analisar_notas(con, titulares)
    regras = carregar_regras()
    (SITE / "cs").mkdir(parents=True, exist_ok=True)
    (SITE / "rh").mkdir(parents=True, exist_ok=True)
    arquivos = {"index.html": pg_index(regras), "financeiro.html": pg_financeiro(linhas), "comercial.html": pg_comercial(regras)}
    for r in regras:
        meus = [l for l in linhas if l["cliente"] == r["cliente"]]
        arquivos[f"cs/{slug(r['cliente'])}.html"] = pg_cs(r, meus, con, titulares)
        arquivos[f"rh/{slug(r['cliente'])}.html"] = pg_rh(r, meus, con, titulares)
    for nome, conteudo in arquivos.items():
        (SITE / nome).write_text(conteudo, encoding="utf-8")
    print(f"{len(arquivos)} paginas em {SITE}")
    for nome in sorted(arquivos):
        print(f"  {nome:40} {len(arquivos[nome]) // 1024:4d} KB")


if __name__ == "__main__":
    main()
