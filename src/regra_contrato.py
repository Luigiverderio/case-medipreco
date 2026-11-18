"""Do texto do contrato a uma regra de cobranca no formato do motor (regras/*.json).

O agente so le o texto e preenche os campos citando a clausula; quem valida o vocabulario, confere os CNPJs
contra a base e monta a regra e o codigo. Nada vale sem aprovacao humana (ver app.py).
"""
import json
import re

from vincular import MODELO

BASES = ("vida", "titular")
PRECOS = ("valor_unico", "por_plano", "faixa")
METODOS = ("foto_dia", "ativo_1_dia", "pro_rata_dia", "pico_mes")
NOTAS = ("unica", "por_cnpj_rateada")
PAGAMENTOS = ("pos", "pre")

SISTEMA_REGRA = """Voce transcreve a regra de cobranca de um contrato de plano de saude para um formato fixo.
Preencha somente o que o contrato diz, citando a clausula de cada item. Se o contrato nao disser, use null e
registre em pendencias. Nunca invente valores. Se o contrato descrever algo que o formato nao comporta,
registre em pendencias e escolha o valor mais proximo.
- base_tipo: "vida" se cobra todas as vidas; "titular" se cobra so os titulares.
- preco_tipo: "valor_unico" (um valor por vida), "por_plano" (valor por plano) ou "faixa" (valor depende da quantidade).
- contagem_metodo: "foto_dia" (vidas num dia fixo do mes), "ativo_1_dia" (ativo ao menos um dia), "pro_rata_dia"
  (proporcional aos dias ativos) ou "pico_mes" (maior numero de vidas em um dia do mes).
- contagem_mes (so para foto_dia): "referencia" se a foto e do proprio mes cobrado, "anterior" se do mes anterior.
- minimo_vidas: faturamento minimo expresso em numero de vidas; null se nao houver.
- nota_tipo: "unica" ou "por_cnpj_rateada" (uma nota por CNPJ, rateada).
- pagamento_tipo: "pos" ou "pre".
- premissas: interpretacoes que voce precisou fazer. pendencias: o que o contrato deixa em aberto."""

FERRAMENTA_REGRA = {
    "name": "registrar_regra",
    "description": "Registra a regra de cobranca extraida do contrato.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cnpjs": {"type": "array", "items": {"type": "string"}},
            "base_tipo": {"type": "string", "enum": list(BASES)}, "base_clausula": {"type": "string"},
            "preco_tipo": {"type": "string", "enum": list(PRECOS)}, "preco_clausula": {"type": "string"},
            "preco_valor": {"type": ["number", "null"]},
            "preco_planos": {"type": "array", "items": {"type": "object", "properties": {
                "plano": {"type": "string"}, "valor": {"type": "number"}}, "required": ["plano", "valor"]}},
            "preco_faixas": {"type": "array", "description": "ate=null na ultima faixa", "items": {
                "type": "object", "properties": {"ate": {"type": ["number", "null"]}, "valor": {"type": "number"}},
                "required": ["ate", "valor"]}},
            "preco_modo": {"type": ["string", "null"], "enum": ["cheia", "progressiva", None]},
            "contagem_metodo": {"type": "string", "enum": list(METODOS)}, "contagem_clausula": {"type": "string"},
            "contagem_dia": {"type": ["integer", "null"]},
            "contagem_mes": {"type": ["string", "null"], "enum": ["referencia", "anterior", None]},
            "minimo_vidas": {"type": ["integer", "null"]}, "minimo_clausula": {"type": ["string", "null"]},
            "nota_tipo": {"type": "string", "enum": list(NOTAS)}, "nota_clausula": {"type": "string"},
            "pagamento_tipo": {"type": "string", "enum": list(PAGAMENTOS)}, "pagamento_clausula": {"type": "string"},
            "premissas": {"type": "array", "items": {"type": "string"}},
            "pendencias": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["cnpjs", "base_tipo", "base_clausula", "preco_tipo", "preco_clausula", "contagem_metodo",
                     "contagem_clausula", "nota_tipo", "nota_clausula", "pagamento_tipo", "pagamento_clausula",
                     "premissas", "pendencias"],
    },
}


def extrair_regra(cliente_api, contrato):
    """Chama o agente e devolve os campos crus (ainda nao validados)."""
    ferramenta = {"type": "function", "function": {
        "name": FERRAMENTA_REGRA["name"], "description": FERRAMENTA_REGRA["description"],
        "parameters": FERRAMENTA_REGRA["input_schema"]}}
    mensagens = [{"role": "system", "content": SISTEMA_REGRA}, {"role": "user", "content": f"CONTRATO:\n{contrato}"}]
    for _ in range(2):
        resp = cliente_api.chat.completions.create(
            model=MODELO, messages=mensagens, tools=[ferramenta],
            tool_choice={"type": "function", "function": {"name": FERRAMENTA_REGRA["name"]}},
            temperature=0, max_tokens=8000)
        msg = resp.choices[0].message
        texto = msg.tool_calls[0].function.arguments if msg.tool_calls else (msg.content or "")
        try:
            bruto = json.loads(texto[texto.index("{"): texto.rindex("}") + 1])
        except ValueError:
            continue
        if all(k in bruto for k in FERRAMENTA_REGRA["input_schema"]["required"]):
            return bruto
    raise RuntimeError("o modelo nao devolveu a regra no formato esperado")


def montar(bruto, base_empresas):
    """Converte os campos do agente na regra do motor e valida. Devolve (regra, erros)."""
    erros = []
    cnpjs = sorted(set(bruto.get("cnpjs") or []))
    conhecidos = sorted({base_empresas[c] for c in cnpjs if c in base_empresas})
    desconhecidos = [c for c in cnpjs if c not in base_empresas]
    if not cnpjs:
        erros.append("nenhum CNPJ informado")
    if desconhecidos:
        erros.append(f"CNPJ fora da base de empresas, sem histórico para calcular: {desconhecidos}")
    if len(conhecidos) > 1:
        erros.append(f"CNPJs de clientes diferentes: {conhecidos}")

    def cl(chave):
        return bruto.get(chave) or ""

    regra = {"cliente": conhecidos[0] if len(conhecidos) == 1 else "", "modelo": None, "status": "aprovada",
             "cnpjs": cnpjs, "base": {"tipo": bruto.get("base_tipo"), "clausula": cl("base_clausula")}}
    if regra["base"]["tipo"] not in BASES:
        erros.append("base de cobrança inválida")

    tipo = bruto.get("preco_tipo")
    preco = {"tipo": tipo, "clausula": cl("preco_clausula")}
    if tipo == "valor_unico":
        preco["valor"] = bruto.get("preco_valor")
        if not isinstance(preco["valor"], (int, float)) or preco["valor"] <= 0:
            erros.append("preço por vida ausente ou inválido")
    elif tipo == "por_plano":
        planos = {re.sub(r"(?i)^plano\s+", "", p["plano"].strip()): p["valor"] for p in bruto.get("preco_planos") or []}
        preco["planos"] = planos
        if not planos or any(v <= 0 for v in planos.values()):
            erros.append("preços por plano ausentes ou inválidos")
    elif tipo == "faixa":
        faixas = bruto.get("preco_faixas") or []
        preco["faixas"], preco["modo"] = faixas, bruto.get("preco_modo")
        limites = [f["ate"] for f in faixas]
        if not faixas or limites[-1] is not None or any(l is None for l in limites[:-1]) \
                or limites[:-1] != sorted(limites[:-1]):
            erros.append("faixas inválidas: devem crescer e a última não tem limite")
        if preco["modo"] not in ("cheia", "progressiva"):
            erros.append("o contrato não diz se a faixa é cheia ou progressiva: defina antes de aprovar")
    else:
        erros.append("tipo de preço inválido")
    regra["preco"] = preco

    metodo = bruto.get("contagem_metodo")
    contagem = {"metodo": metodo, "clausula": cl("contagem_clausula")}
    if metodo not in METODOS:
        erros.append("método de contagem inválido")
    if metodo == "foto_dia":
        dia, mes = bruto.get("contagem_dia"), bruto.get("contagem_mes")
        contagem.update({"dia": dia, "mes": mes})
        if not isinstance(dia, int) or not 1 <= dia <= 31:
            erros.append("dia da foto ausente ou inválido")
        if mes not in ("referencia", "anterior"):
            erros.append("não ficou claro se a foto é do mês de referência ou do anterior")
    regra["contagem"] = contagem

    try:
        vidas = int(bruto.get("minimo_vidas"))  # o agente as vezes devolve o texto "None"
    except (TypeError, ValueError):
        vidas = None
    regra["minimo"] = {"vidas": vidas, "clausula": cl("minimo_clausula")} if vidas else None
    if bruto.get("nota_tipo") not in NOTAS:
        erros.append("tipo de nota inválido")
    regra["nota"] = {"tipo": bruto.get("nota_tipo"), "clausula": cl("nota_clausula")}
    if bruto.get("pagamento_tipo") not in PAGAMENTOS:
        erros.append("tipo de pagamento inválido")
    regra["pagamento"] = {"tipo": bruto.get("pagamento_tipo"), "clausula": cl("pagamento_clausula")}
    regra["premissas"] = list(bruto.get("premissas") or [])
    regra["pendencias"] = list(bruto.get("pendencias") or [])
    return regra, erros


def linhas_resumo(regra):
    """Pares (item, valor, clausula) para mostrar a regra ao usuario."""
    p, c, m = regra["preco"], regra["contagem"], regra.get("minimo")
    if p["tipo"] == "valor_unico":
        preco = f"R$ {p['valor']:.2f} por vida".replace(".", ",")
    elif p["tipo"] == "por_plano":
        preco = "; ".join(f"{k}: R$ {v:.2f}".replace(".", ",") for k, v in p["planos"].items())
    else:
        preco = "; ".join(f"até {f['ate']:,}".replace(",", ".") + f": R$ {f['valor']:.2f}".replace(".", ",") if f["ate"]
                          else f"acima: R$ {f['valor']:.2f}".replace(".", ",") for f in p["faixas"]) + f" ({p.get('modo')})"
    nomes = {"foto_dia": "Foto da base num dia fixo", "ativo_1_dia": "Ativo pelo menos 1 dia",
             "pro_rata_dia": "Proporcional aos dias ativos", "pico_mes": "Pico de vidas no mês"}
    contagem = nomes.get(c["metodo"], str(c["metodo"]))
    if c["metodo"] == "foto_dia":
        contagem += f": dia {c.get('dia')} do mês {'de referência' if c.get('mes') == 'referencia' else 'anterior'}"
    return [
        ("Cobra", "Todas as vidas" if regra["base"]["tipo"] == "vida" else "Só titulares", regra["base"]["clausula"]),
        ("Preço", preco, p["clausula"]),
        ("Contagem", contagem, c["clausula"]),
        ("Mínimo", f"{m['vidas']} vidas" if m else "Não há", m["clausula"] if m else ""),
        ("Nota", "Uma nota" if regra["nota"]["tipo"] == "unica" else "Uma nota por CNPJ, rateada", regra["nota"]["clausula"]),
        ("Pagamento", "Pós-pago" if regra["pagamento"]["tipo"] == "pos" else "Pré-pago", regra["pagamento"]["clausula"]),
    ]
