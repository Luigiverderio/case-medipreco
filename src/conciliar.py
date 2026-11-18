"""Extrato de conciliacao: da contagem cobrada ate a contagem que o cliente ve depois.

Compara duas fotos da base (as duas pela data em que o evento entrou no sistema) e explica cada pessoa
que mudou de situacao entre elas, usando a data informada pelo RH para separar o que o contrato cobra
corretamente do que e zona cinzenta (saiu ou entrou antes da data da foto, mas foi informado depois).
Uso: python src/conciliar.py [cliente] [competencia] [corte_do_cliente]
     ex.: python src/conciliar.py Aurora 2026-10 "2026-10-31 23:59:59"
"""
import csv
import sqlite3
import sys
from calendar import monthrange
from collections import Counter, defaultdict
from datetime import date

from calcular import (DB, RAIZ, brl, calcular, carregar_regras, eventos_do_cliente, foto_processamento,
                      resumo, sem_cargas_desfeitas, serie_diaria, so_titulares)

GRUPOS = {
    ("saida", True):    "saiu depois da foto (cobranca correta)",
    ("saida", False):   "saiu ate a foto, informada depois (VERIFICAR CREDITO)",
    ("entrada", True):  "entrou depois da foto (entra na proxima competencia)",
    ("entrada", False): "entrou ate a foto, informada depois (nao foi cobrada)",
    ("troca", True):    "trocou de plano",
    ("troca", False):   "trocou de plano",
}


def ponte(regra, eventos, titulares, corte_a, corte_b, dia_foto):
    """Devolve (foto_a, foto_b, {grupo: [(pessoa, cnpj, plano_antes, plano_depois, evento)]})."""
    a = so_titulares(foto_processamento(eventos, corte_a), regra["base"], titulares)
    b = so_titulares(foto_processamento(eventos, corte_b), regra["base"], titulares)
    janela = defaultdict(list)
    for e in sorted((e for e in eventos if corte_a < e[4] <= corte_b), key=lambda e: (e[4], e[6])):
        janela[(e[0], e[1])].append(e)
    grupos = defaultdict(list)
    for chave in set(a) | set(b):
        antes, depois = a.get(chave), b.get(chave)
        if antes == depois:
            continue
        evs = janela[chave]
        if antes is None:
            tipo, ev = "entrada", next((x for x in evs if x[2] == "entrada"), evs[-1])
        elif depois is None:
            tipo, ev = "saida", next((x for x in reversed(evs) if x[2] == "saida"), evs[-1])
        else:
            tipo, ev = "troca", evs[-1]
        apos_foto = ev[5] > dia_foto
        grupos[GRUPOS[(tipo, apos_foto)]].append((chave[0], chave[1], antes, depois, ev))
    return a, b, grupos


def ponte_pico(regra, eventos, titulares, comp):
    """Do dia de pico ate o ultimo dia do mes, pela data informada. Devolve (pico, fim, a, b, grupos)."""
    ano, mes = map(int, comp.split("-"))
    ini, fim = date(ano, mes, 1), date(ano, mes, monthrange(ano, mes)[1])
    serie = {d: so_titulares(e, regra["base"], titulares) for d, e in serie_diaria(eventos, ini, fim).items()}
    pico = max(serie, key=lambda d: len(serie[d]))
    a, b = serie[pico], serie[fim]
    janela = defaultdict(list)
    for e in sorted(eventos, key=lambda e: (e[5], e[4], e[6])):
        if pico.isoformat() < e[5] <= fim.isoformat():
            janela[(e[0], e[1])].append(e)
    saem = {k for k in a if k not in b}
    entram = {k for k in b if k not in a}
    trocam = {k[0] for k in saem} & {k[0] for k in entram}

    def linha(k, tipo, antes, depois):
        return (k[0], k[1], antes, depois, next(x for x in reversed(janela[k]) if x[2] == tipo))

    grupos = {
        "saiu depois do pico": [linha(k, "saida", a[k], None) for k in sorted(saem) if k[0] not in trocam],
        "entrou depois do pico": [linha(k, "entrada", None, b[k]) for k in sorted(entram) if k[0] not in trocam],
        "mudou de empresa do grupo (muda o rateio, nao o total)":
            [linha(k, "entrada", None, b[k]) for k in sorted(entram) if k[0] in trocam],
    }
    return pico, fim, a, b, grupos


def extrato_pico(regra, eventos, titulares, con, comp):
    pico, fim, a, b, grupos = ponte_pico(regra, eventos, titulares, comp)
    por_plano, por_cnpj = resumo(a)
    calc = calcular(regra, por_plano, por_cnpj)
    marcas = ",".join("?" * len(regra["cnpjs"]))
    emitidas = {c: (q, v) for c, q, v in con.execute(
        f"select cnpj_tomador, sum(quantidade), sum(valor_item) from notas_emitidas where competencia = ? "
        f"and cnpj_tomador in ({marcas}) group by cnpj_tomador", [comp] + regra["cnpjs"])}
    print(f"EXTRATO DE CONCILIACAO | {regra['cliente']} | competencia {comp}")
    print(f"Contrato: maior numero de vidas no mes (clausula {regra['contagem']['clausula']}), "
          f"rateado entre as empresas (clausula {regra['nota']['clausula']})\n")
    print(f"Pico de vidas no mes (em {pico:%d/%m}) ........................ {len(a):5d}   R$ {brl(calc['valor'])}")
    soma = len(a)
    for nome, linhas in grupos.items():
        sinal = "-" if nome.startswith("saiu") else "+" if nome.startswith("entrou") else "~"
        if sinal == "-":
            soma -= len(linhas)
        elif sinal == "+":
            soma += len(linhas)
        print(f" ({sinal}) {nome:58} {len(linhas):4d}")
        if linhas:
            print(f"       por data informada: {datas(linhas)}")
    print(f"Vidas ativas no ultimo dia ({fim:%d/%m}) ................... {len(b):5d}")
    print(f"conferencia: {len(a)} - saidas + entradas = {soma} -> "
          f"{'bate com ' + str(len(b)) if soma == len(b) else 'NAO bate com ' + str(len(b))}\n")
    print(f"{'empresa (CNPJ)':22} {'vidas no pico':>13} {'%':>6} {'R$ pelo contrato':>17} "
          f"{'emitida (qtd / R$)':>22} {'dif. R$':>10}")
    for cnpj in regra["cnpjs"]:
        v, valor = por_cnpj.get(cnpj, 0), calc["notas"].get(cnpj, 0)
        q_e, v_e = emitidas.get(cnpj, (0, 0))
        print(f"{cnpj:22} {v:13d} {100 * v / len(a):5.1f}% {brl(valor):>17} {q_e:>9.0f} / {brl(v_e):>10} {brl(valor - v_e):>10}")
    tot_q, tot_v = sum(q for q, _ in emitidas.values()), sum(v for _, v in emitidas.values())
    print(f"{'total':22} {len(a):13d} {'':>6} {brl(calc['valor']):>17} {tot_q:>9.0f} / {brl(tot_v):>10} {brl(calc['valor'] - tot_v):>10}")


def planos(est):
    p = Counter(est.values())
    return ", ".join(f"{k} {v}" for k, v in sorted(p.items()))


def datas(linhas):
    c = Counter(l[4][5][8:10] + "/" + l[4][5][5:7] for l in linhas)
    return "  ".join(f"{d}: {n}" for d, n in sorted(c.items(), key=lambda x: (x[0][3:], x[0][:2])))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    nome = sys.argv[1] if len(sys.argv) > 1 else "Aurora"
    comp = sys.argv[2] if len(sys.argv) > 2 else "2026-10"
    corte_b = sys.argv[3] if len(sys.argv) > 3 else "2026-10-31 23:59:59"
    regra = next(r for r in carregar_regras() if nome.lower() in r["cliente"].lower())
    con = sqlite3.connect(DB)
    titulares = {p for (p,) in con.execute("select pessoa_id from pessoas where tipo = 'titular'")}
    eventos = eventos_do_cliente(con, regra["cnpjs"])
    metodo = regra["contagem"]["metodo"]
    if metodo == "pico_mes":
        return extrato_pico(regra, sem_cargas_desfeitas(eventos), titulares, con, comp)
    if metodo != "foto_dia" or regra["contagem"]["mes"] != "referencia":
        sys.exit("a ponte ainda nao cobre esse metodo de contagem")
    marcas = ",".join("?" * len(regra["cnpjs"]))
    corte_a = con.execute(f"select max(contagem_em) from notas_emitidas where competencia = ? "
                          f"and cnpj_tomador in ({marcas})", [comp] + regra["cnpjs"]).fetchone()[0]
    ano, mes = map(int, comp.split("-"))
    dia_foto = date(ano, mes, regra["contagem"]["dia"]).isoformat()

    a, b, grupos = ponte(regra, eventos, titulares, corte_a, corte_b, dia_foto)
    va, vb = calcular(regra, *resumo(a)), calcular(regra, *resumo(b))
    print(f"EXTRATO DE CONCILIACAO | {regra['cliente']} | competencia {comp}")
    print(f"Contrato: foto no dia {regra['contagem']['dia']} do mes de referencia (clausula {regra['contagem']['clausula']})\n")
    print(f"Vidas cobradas (base em {corte_a}) ........ {len(a):5d}   ({planos(a)})   R$ {brl(va['valor'])}")
    soma = len(a)
    for chave, sinal in ((("saida", True), -1), (("saida", False), -1), (("entrada", True), 1), (("entrada", False), 1)):
        linhas = grupos.get(GRUPOS[chave], [])
        soma += sinal * len(linhas)
        print(f" ({'-' if sinal < 0 else '+'}) {GRUPOS[chave]:62} {len(linhas):4d}")
        if linhas:
            print(f"       por data informada: {datas(linhas)}")
    trocas = grupos.get(GRUPOS[("troca", True)], [])
    if trocas:
        print(f" (~) {GRUPOS[('troca', True)]:62} {len(trocas):4d}   (muda o valor, nao a quantidade)")
    print(f"Vidas na base do cliente (ate {corte_b}) .. {len(b):5d}   ({planos(b)})   R$ {brl(vb['valor'])}")
    print(f"\nconferencia: {len(a)} - saidas + entradas = {soma}  ->  {'bate com ' + str(len(b)) if soma == len(b) else 'NAO bate com ' + str(len(b))}")

    saida = RAIZ / "saida" / f"conciliacao_{regra['cliente'].split()[0].lower()}_{comp}.csv"
    with open(saida, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["grupo", "pessoa_id", "cnpj", "plano_antes", "plano_depois", "evento", "data_informada",
                    "data_processamento", "origem"])
        for grupo, linhas in sorted(grupos.items()):
            for pessoa, cnpj, antes, depois, ev in sorted(linhas, key=lambda l: l[4][5]):
                w.writerow([grupo, pessoa, cnpj, antes or "", depois or "", ev[2], ev[5], ev[4], ev[7]])
    print(f"lista por pessoa: {saida}")


if __name__ == "__main__":
    main()
