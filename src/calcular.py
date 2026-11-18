"""Motor de calculo da mensalidade.

Le a regra de cada cliente (regras/*.json) e a base de eventos, e calcula a nota de uma competencia.
Dois modos de contagem:
  como_hoje: foto na hora em que o financeiro consultou (data_processamento <= contagem_em da nota)
  contrato : o metodo que o contrato manda, pela data informada pelo RH
O relatorio compara os dois com a nota emitida.
"""
import json
import sqlite3
import sys
from calendar import monthrange
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DB = RAIZ / "dados" / "base.sqlite"


def brl(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def carregar_regras():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((RAIZ / "regras").glob("*.json"))]


def eventos_do_cliente(con, cnpjs):
    marcas = ",".join("?" * len(cnpjs))
    return con.execute(
        "select pessoa_id, cnpj, tipo_evento, plano, data_processamento, data_informada, evento_id, origem "
        f"from eventos where cnpj in ({marcas})", cnpjs).fetchall()


def sem_cargas_desfeitas(eventos):
    """Anula entradas que o suporte desfez: saida do suporte informada no dia em que a entrada foi
    processada (arquivo errado). Premissa a confirmar com a Medipreco, o case nao traz um evento de 'desfazer'."""
    ultima_entrada, descartar = {}, set()
    for e in sorted(eventos, key=lambda e: (e[4], e[6])):
        chave = (e[0], e[1])
        if e[2] == "entrada":
            ultima_entrada[chave] = e
        elif e[2] == "saida" and e[7] == "suporte_medipreco" and chave in ultima_entrada:
            entrada = ultima_entrada[chave]
            if e[5] == entrada[4][:10]:
                descartar.update({entrada[6], e[6]})
    return [e for e in eventos if e[6] not in descartar]


def aplicar(estado, e):
    estado[(e[0], e[1])] = None if e[2] == "saida" else e[3]


def foto_processamento(eventos, corte):
    """Quem estava ativo, e em que plano, so com o que ja tinha sido processado ate `corte`."""
    estado = {}
    for e in sorted((e for e in eventos if e[4] <= corte), key=lambda e: (e[4], e[6])):
        aplicar(estado, e)
    return {k: v for k, v in estado.items() if v}


def serie_diaria(eventos, ini, fim):
    """{dia: {(pessoa, cnpj): plano}} pela data informada. Quem sai numa data nao conta nesse dia."""
    ordenados = sorted(eventos, key=lambda e: (e[5], e[4], e[6]))
    estado, i, serie, d = {}, 0, {}, ini
    while d <= fim:
        while i < len(ordenados) and ordenados[i][5] <= d.isoformat():
            aplicar(estado, ordenados[i])
            i += 1
        serie[d] = {k: v for k, v in estado.items() if v}
        d += timedelta(days=1)
    return serie


def so_titulares(estado, base, titulares):
    if base["tipo"] != "titular":
        return estado
    return {k: v for k, v in estado.items() if k[0] in titulares}


def resumo(estado):
    return Counter(estado.values()), Counter(k[1] for k in estado)


def contar_contrato(regra, eventos, titulares, competencia):
    """Conta as vidas pelo metodo do contrato. Devolve (vidas_por_plano, vidas_por_cnpj, detalhe)."""
    ano, mes = map(int, competencia.split("-"))
    dias = monthrange(ano, mes)[1]
    ini, fim = date(ano, mes, 1), date(ano, mes, dias)
    c, base = regra["contagem"], regra["base"]
    filtrar = lambda est: so_titulares(est, base, titulares)

    if c["metodo"] == "foto_dia":
        if c["mes"] == "anterior":
            ano, mes = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
        d = date(ano, mes, c["dia"])
        por_plano, por_cnpj = resumo(filtrar(serie_diaria(eventos, d, d)[d]))
        return por_plano, por_cnpj, f"foto em {d.isoformat()}"

    serie = {d: filtrar(est) for d, est in serie_diaria(eventos, ini, fim).items()}
    if c["metodo"] == "ativo_1_dia":
        uniao = {}
        for est in serie.values():
            uniao.update(est)
        por_plano, por_cnpj = resumo(uniao)
        return por_plano, por_cnpj, "ativo ao menos 1 dia no mes"
    if c["metodo"] == "pico_mes":
        pico = max(serie, key=lambda d: len(serie[d]))
        por_plano, por_cnpj = resumo(serie[pico])
        return por_plano, por_cnpj, f"pico de {len(serie[pico])} vidas em {pico.isoformat()}"
    if c["metodo"] == "pro_rata_dia":
        por_plano, por_cnpj = Counter(), Counter()
        for est in serie.values():
            p, n = resumo(est)
            por_plano.update(p)
            por_cnpj.update(n)
        return ({k: v / dias for k, v in por_plano.items()}, {k: v / dias for k, v in por_cnpj.items()},
                f"media diaria em {dias} dias")
    raise ValueError(f"metodo de contagem desconhecido: {c['metodo']}")


def precificar(regra, por_plano):
    """Devolve (itens, valor). Cada item e (descricao, quantidade, valor_unitario)."""
    preco, total = regra["preco"], sum(por_plano.values())
    if preco["tipo"] == "por_plano":
        itens = [(f"Plano {p}", q, preco["planos"][p]) for p, q in sorted(por_plano.items())]
    else:
        qtd = max(total, (regra.get("minimo") or {}).get("vidas", 0))
        if preco["tipo"] == "valor_unico":
            itens = [("Mensalidade", qtd, preco["valor"])]
        elif preco["modo"] == "cheia":
            unit = next(f["valor"] for f in preco["faixas"] if f["ate"] is None or qtd <= f["ate"])
            itens = [("Mensalidade", qtd, unit)]
        else:  # progressiva
            itens, anterior = [], 0
            for f in preco["faixas"]:
                topo = f["ate"] if f["ate"] is not None else float("inf")
                parte = min(qtd, topo) - anterior
                if parte > 0:
                    itens.append((f"Faixa ate {f['ate']}", parte, f["valor"]))
                anterior = topo
                if qtd <= topo:
                    break
    return itens, sum(q * v for _, q, v in itens)


def calcular(regra, por_plano, por_cnpj):
    itens, valor = precificar(regra, por_plano)
    total_vidas = sum(por_cnpj.values()) or 1
    notas = ({c: valor * n / total_vidas for c, n in por_cnpj.items()}
             if regra["nota"]["tipo"] == "por_cnpj_rateada" else {"unica": valor})
    return {"vidas": sum(por_plano.values()), "itens": itens, "valor": valor, "notas": notas}


def hipoteses(regra, eventos, titulares, corte):
    """Contagens alternativas que o financeiro pode ter usado sem querer. Devolve [(descricao, estado)]."""
    bruto = foto_processamento(eventos, corte)
    if regra["base"]["tipo"] == "titular":
        achados = [("contou todas as vidas (titulares e dependentes) em vez de so titulares", bruto)]
    else:
        achados = [("contou so os titulares em vez de todas as vidas",
                    {k: v for k, v in bruto.items() if k[0] in titulares})]
    for horas in (-48, -24, 24, 48):
        outro = (datetime.fromisoformat(corte) + timedelta(hours=horas)).isoformat(sep=" ")
        achados.append((f"usou a foto {abs(horas)}h {'antes' if horas < 0 else 'depois'} do horario de corte",
                        so_titulares(foto_processamento(eventos, outro), regra["base"], titulares)))
    dia = date.fromisoformat(corte[:10])
    achados.append(("contou pela data informada pelo RH, nao pela data em que entrou no sistema",
                    so_titulares(serie_diaria(eventos, dia, dia)[dia], regra["base"], titulares)))
    achados.append(("nao considerou a carga desfeita pelo suporte",
                    so_titulares(foto_processamento(sem_cargas_desfeitas(eventos), corte), regra["base"], titulares)))
    return achados


def diagnosticar(regra, eventos, titulares, corte, valor_emitido):
    """Hipoteses de causa cujo valor coincide com a nota emitida. E um indicio, nao uma prova."""
    achados = []
    for descricao, estado in hipoteses(regra, eventos, titulares, corte):
        r = calcular(regra, *resumo(estado))
        if abs(r["valor"] - valor_emitido) < 0.005:
            achados.append({"hipotese": descricao, "vidas": r["vidas"], "valor": r["valor"]})
    return achados


def analisar_notas(con, titulares):
    """Uma linha por nota emitida: o que foi emitido, o que o motor calcula e, se nao bate, as hipoteses."""
    linhas = []
    for regra in carregar_regras():
        eventos = eventos_do_cliente(con, regra["cnpjs"])
        limpos = sem_cargas_desfeitas(eventos)
        marcas = ",".join("?" * len(regra["cnpjs"]))
        notas = con.execute(
            f"select competencia, max(contagem_em), sum(quantidade), sum(valor_item) from notas_emitidas "
            f"where cnpj_tomador in ({marcas}) group by competencia order by competencia", regra["cnpjs"]).fetchall()
        for comp, corte, qtd_emitida, valor_emitido in notas:
            estado = so_titulares(foto_processamento(eventos, corte), regra["base"], titulares)
            hoje = calcular(regra, *resumo(estado))
            contrato = calcular(regra, *contar_contrato(regra, limpos, titulares, comp)[:2])
            bate = abs(hoje["valor"] - valor_emitido) < 0.005
            linhas.append({
                "regra": regra, "cliente": regra["cliente"], "competencia": comp, "corte": corte,
                "qtd_emitida": qtd_emitida, "valor_emitido": valor_emitido,
                "hoje_vidas": hoje["vidas"], "hoje_valor": hoje["valor"], "bate": bate,
                "contrato_vidas": contrato["vidas"], "contrato_valor": contrato["valor"],
                "dif_contrato": contrato["valor"] - valor_emitido,
                "anulados": len(eventos) - len(limpos),
                "diagnostico": [] if bate else diagnosticar(regra, eventos, titulares, corte, valor_emitido),
            })
    return linhas


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    con = sqlite3.connect(DB)
    titulares = {p for (p,) in con.execute("select pessoa_id from pessoas where tipo = 'titular'")}
    linhas = analisar_notas(con, titulares)
    print(f"{'cliente':18} {'comp.':8} {'EMITIDA (qtd / R$)':>24} {'COMO HOJE R$':>14} {'bate':>5} "
          f"{'CONTRATO (qtd / R$)':>26} {'dif. R$':>12}")
    for l in linhas:
        print(f"{l['cliente']:18} {l['competencia']:8} {l['qtd_emitida']:>9.0f} / {brl(l['valor_emitido']):>12} "
              f"{brl(l['hoje_valor']):>14} {'sim' if l['bate'] else 'NAO':>5} "
              f"{l['contrato_vidas']:>10.1f} / {brl(l['contrato_valor']):>12} {brl(l['dif_contrato']):>12}")
    bateu = sum(l["bate"] for l in linhas)
    print(f"\ncomo hoje reproduz a nota emitida em {bateu} de {len(linhas)} competencias")
    excecoes = [l for l in linhas if not l["bate"]]
    if excecoes:
        print("\nREVISAO SISTEMICA (notas que nao batem)")
    for l in excecoes:
        print(f"{l['cliente']} {l['competencia']}: nota de R$ {brl(l['valor_emitido'])} ({l['qtd_emitida']:.0f}), "
              f"motor calcula R$ {brl(l['hoje_valor'])} ({l['hoje_vidas']:.0f}); diferenca R$ {brl(l['valor_emitido'] - l['hoje_valor'])}")
        for d in l["diagnostico"] or [{"hipotese": "nenhuma hipotese testada explica o valor", "vidas": 0, "valor": 0}]:
            print(f"   coincide com: {d['hipotese']}" + (f" ({d['vidas']:.0f} vidas, R$ {brl(d['valor'])})" if d["vidas"] else ""))


if __name__ == "__main__":
    main()
