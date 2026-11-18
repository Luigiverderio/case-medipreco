"""Gera a proposta em saida/site/proposta.html, no mesmo visual das demais paginas.
Uso: python src/gerar_proposta.py
"""
import sys

from gerar_paginas import SITE, esc, pagina, tabela


def linhas(*rows):
    return "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)


def lista(itens):
    return "<ul>" + "".join(f"<li>{i}</li>" for i in itens) + "</ul>"


CORPO = (
    "<section class='page-intro'><h1>O fechamento do mês</h1>"
    "<p class='sub'>Cobrar de forma simples, escalável e auditável é separar o que hoje vive misturado numa planilha: "
    "o que aconteceu, o que o contrato manda e a conta. E explicar cada número a quem precisa dele.</p></section>"

    "<h2>O que ouvimos e o que isso pede</h2>"
    + tabela("<tr><th>Quem</th><th>A dor</th><th>O que o sistema faz</th></tr>" + linhas(
        ("Financeiro", "“Levo dois dias. Se erro uma linha, ninguém percebe até o cliente reclamar.”",
         "Refaz cada nota emitida e aponta as que não batem, com a hipótese de causa."),
        ("RH do cliente", "“Baixei a base e deu 718. Vocês cobraram 737.”",
         "Extrato que explica a diferença: parte do que foi cobrado e chega ao que o cliente vê, com as datas."),
        ("Comercial", "“Fico na dúvida se vamos conseguir cobrar antes de prometer.”",
         "Mostra o que o sistema já calcula e o que ainda não cabe. Contrato novo que usa as peças existentes vira só uma regra."),
        ("Customer Success", "“Abro a planilha, o banco e o contrato e não consigo mostrar de onde veio o número.”",
         "Nota → regra → cláusula → pessoas e datas, numa página só.")))

    + "<h2>A ideia</h2>"
    "<p class='section-lead'>Quatro camadas, cada uma com um papel, e a IA só onde existe texto livre.</p>"
    + lista([
        "<b>Fatos.</b> Uma linha do tempo por cliente. Cada entrada, saída ou troca de plano tem <b>duas datas</b>: a que o RH "
        "informou e a em que entrou no sistema. Quase toda reclamação de contagem mora na diferença entre elas.",
        "<b>Regra.</b> O contrato vira uma regra estruturada, com a cláusula de origem de cada valor. Um agente de IA lê o PDF "
        "e <b>propõe</b>; os CNPJs e os campos são conferidos por código; uma pessoa aprova.",
        "<b>Cálculo.</b> Determinístico, sem IA: a mesma entrada dá sempre a mesma saída, e um fechamento antigo pode ser refeito.",
        "<b>Explicação.</b> Cada número chega com a trilha que o sustenta. Tudo o que o agente decide entra numa auditoria "
        "com hash do PDF e hash encadeado entre os registros.",
    ])
    + "<div class='nota'>Por que a IA só no contrato: é onde o texto é livre. O cálculo precisa ser reproduzível e auditável, "
      "e isso um modelo de linguagem não garante.</div>"

    + "<h2>O caminho inteiro, do contrato à nota paga</h2>"
    + tabela("<tr><th>Etapa</th><th>Situação</th></tr>" + linhas(
        ("Ler o contrato e propor a regra", "Construído: o agente classificou os 6 contratos como esperado (4 vinculados, 2 para aprovação)."),
        ("Aprovação humana", "Parcial: a fila lista os pendentes, mas ainda não há botão de aprovar nem registro de quem aprovou."),
        ("Linha do tempo e cálculo", "Construído: 4 formas de contar (foto, ≥ 1 dia, pro rata, pico), 3 de preço, mínimo e nota única ou rateada."),
        ("Conferir a nota emitida", "Construído: reproduz 18 das 19 notas ao centavo; a 19ª é uma divergência real."),
        ("Explicar ao cliente e ao time", "Construído: páginas por perfil e, para o RH, o extrato que explica a diferença entre o que foi cobrado e a base do cliente."),
        ("Nota paga", "Não construído. Proposto: conciliar o pagamento com a nota e com a regra vigente.")))

    + "<h2>O que os dados revelaram</h2>"
    + lista([
        "<b>Bravo, setembro.</b> A nota cobrou 499 titulares (R$ 7.485). A base tinha 332 titulares e 499 vidas no total, e o "
        "contrato cobra só titulares. O valor coerente é R$ 4.980: <b>R$ 2.505 a mais</b>, sem linha de acerto nas notas seguintes. "
        "É um indício de causa, não uma prova.",
        "<b>Aurora, outubro (o caso do RH).</b> 737 cobradas contra 718 na base de 31/10. As 19 saídas chegaram num só arquivo, "
        "em 27/10 às 11:57. 16 delas têm data até 26/10: saíram antes da foto, mas foram informadas depois. A diferença é de R$ 183.",
        "<b>Delta.</b> Uma carga de 600 pessoas (07/10), desfeita pelo suporte dois dias depois, inflava a contagem. "
        "E a faixa muda o sentido da conta: com faixa cheia, cruzar 5.000 vidas <b>reduz</b> a nota (R$ 50.000 com 5.000; R$ 45.009 com 5.001).",
        "<b>Cedro.</b> 126 pessoas mudaram de empresa do grupo em 13/10. O total quase não muda, mas cada nota muda cerca de R$ 1.000, "
        "porque o contrato não diz em que data se rateia.",
        "<b>Estrela.</b> O mínimo de 500 vidas ainda não foi acionado nas notas, mas pela contagem do contrato, em outubro, ele seria.",
    ])

    + "<h2>Decisões e porquês</h2>"
    + lista([
        "<b>Aprofundei a contagem de vidas e a explicação.</b> O próprio enunciado diz que é onde mora boa parte da história, "
        "e é onde nasce a reclamação.",
        "<b>O sistema escala por tipos de cláusula, não por clientes.</b> Contrato novo que usa peças existentes: só uma regra nova. "
        "Peça nova (por exemplo, mínimo em reais): estender o motor uma vez, e vale para qualquer contrato.",
        "<b>Deixei de fora, de propósito:</b> o pagamento da nota, o acerto do pré-pago, mínimo em reais, reajuste, "
        "autenticação por cliente e o botão de aprovação. Não mudam a lógica central e o tempo era curto; estão nos próximos passos.",
        "<b>A página do RH só detalha onde a nota segue o contrato</b> (Aurora e Estrela). Mostrar ao cliente que uma nota não seguiu "
        "o contrato é uma decisão do Financeiro, antes de qualquer envio.",
    ])

    + "<h2>O que precisamos confirmar com a Medipreço</h2>"
    + lista([
        "A faixa do Delta é cheia ou progressiva?",
        "Saída informada com atraso dá crédito? Há um prazo?",
        "Quem aprova uma regra: Financeiro, Jurídico ou Comercial?",
        "Existe um evento explícito de “desfazer” arquivo? Hoje a carga desfeita é deduzida (saída do suporte no mesmo dia).",
        "No Cedro, o rateio entre as empresas usa as vidas de qual data? E o pico é diário?",
        "Qual o prazo do acerto do pré-pago na Bravo (cláusula 4.4)?",
    ])

    + "<h2>Próximos passos</h2>"
    + lista([
        "Aprovação com versão da regra e aprovador na auditoria; o motor só aceita regra aprovada.",
        "O agente extrair os valores do contrato direto para a regra, validando o que cabe no vocabulário do motor.",
        "O extrato que explica a diferença para os contratos de ≥ 1 dia, pro rata e pré-pago.",
        "Conciliar o pagamento da nota.",
        "Acesso por cliente, cada um vendo só o seu extrato.",
    ])
    + "<p class='peq muted'>Como rodar o que foi construído: README.md. Como a IA foi usada: USO_DE_IA.md.</p>"
)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    destino = SITE / "proposta.html"
    destino.write_text(pagina("Proposta · Medipreço", CORPO), encoding="utf-8")
    print("gerado:", destino, f"({destino.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
