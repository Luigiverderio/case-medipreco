"""Experimento 1: o agente le um contrato, compara com o catalogo de regras e propoe o vinculo.

O agente so extrai e classifica. O vinculo com o CNPJ e deterministico (regex + tabela empresas).
Quando algo nao fecha, o contrato vai para aprovacao manual. Tudo entra em saida/auditoria.jsonl.
"""
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI
from pypdf import PdfReader

RAIZ = Path(__file__).resolve().parent.parent
MODELO = "nvidia/nemotron-3.5-super-vl-120b-a12b"
URL_API = "https://integrate.api.nvidia.com/v1"
LIMIAR_CONFIANCA = 0.8
CNPJ_RE = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")

# O que espero ler nos contratos, para medir o agente. Faro e Cedro nao estao no catalogo.
ESPERADO = {
    "aurora-logistica": "M1",
    "bravo-tecnologia": "M2",
    "estrela-industria": "M3",
    "delta-beneficios": "M4",
    "faro-servicos": "NENHUMA",
    "grupo-cedro": "NENHUMA",
}

SISTEMA = """Voce analisa contratos de cobranca da Medipreco. Sua tarefa:
1. Extrair do contrato como a cobranca funciona, citando a clausula de cada informacao.
2. Comparar com o catalogo de modelos e dizer qual modelo se enquadra, ou NENHUMA.

Regras:
- Use somente o texto do contrato. Nao invente informacao que nao esta escrita.
- Um modelo se enquadra apenas se TODOS os aspectos da estrutura coincidem: base de cobranca, forma do preco,
  metodo de contagem das vidas, pagamento, minimo e regra de nota. Valores em reais, dia da foto e faixas sao
  parametros e nao contam na comparacao.
- Se qualquer aspecto estrutural diferir, responda NENHUMA e liste a divergencia.
- Em pontos_de_atencao, registre ambiguidades do contrato que podem mudar o valor cobrado.
- confianca vai de 0 a 1."""

FERRAMENTA = {
    "name": "registrar_analise",
    "description": "Registra a analise do contrato.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cliente": {"type": "string"},
            "cnpjs_no_contrato": {"type": "array", "items": {"type": "string"}},
            "campos": {
                "type": "array",
                "description": "Aspectos da cobranca: base, preco, metodo_contagem, pagamento, minimo, nota.",
                "items": {
                    "type": "object",
                    "properties": {
                        "campo": {"type": "string"},
                        "valor": {"type": "string"},
                        "clausula": {"type": "string"},
                    },
                    "required": ["campo", "valor", "clausula"],
                },
            },
            "regra_id": {"type": "string", "enum": ["M1", "M2", "M3", "M4", "NENHUMA"]},
            "justificativa": {"type": "string"},
            "divergencias": {"type": "array", "items": {"type": "string"}},
            "pontos_de_atencao": {"type": "array", "items": {"type": "string"}},
            "confianca": {"type": "number"},
        },
        "required": ["cliente", "cnpjs_no_contrato", "campos", "regra_id", "justificativa",
                     "divergencias", "pontos_de_atencao", "confianca"],
    },
}


def texto_pdf(caminho):
    return "\n".join(p.extract_text() for p in PdfReader(caminho).pages)


def empresas():
    con = sqlite3.connect(RAIZ / "dados" / "base.sqlite")
    return dict(con.execute("select cnpj, cliente from empresas"))


def analisar(cliente_api, catalogo, contrato):
    ferramenta = {"type": "function", "function": {
        "name": FERRAMENTA["name"], "description": FERRAMENTA["description"],
        "parameters": FERRAMENTA["input_schema"]}}
    mensagens = [
        {"role": "system", "content": SISTEMA},
        {"role": "user", "content":
         f"CATALOGO DE MODELOS:\n{json.dumps(catalogo, ensure_ascii=False, indent=1)}\n\n"
         f"CONTRATO:\n{contrato}"},
    ]
    for _ in range(2):  # uma nova tentativa se o modelo devolver JSON quebrado
        resp = cliente_api.chat.completions.create(
            model=MODELO, messages=mensagens, tools=[ferramenta],
            tool_choice={"type": "function", "function": {"name": FERRAMENTA["name"]}},
            temperature=0, max_tokens=8000,
        )
        msg = resp.choices[0].message
        texto = msg.tool_calls[0].function.arguments if msg.tool_calls else (msg.content or "")
        try:
            analise = json.loads(texto[texto.index("{"): texto.rindex("}") + 1])
        except ValueError:
            continue
        if all(k in analise for k in FERRAMENTA["input_schema"]["required"]):
            return analise
    raise RuntimeError("o modelo nao devolveu a analise no formato esperado")


def decidir(analise, cnpjs_texto, base_empresas):
    """Decisao deterministica: so vincula se agente e regex concordam e todos os CNPJs sao conhecidos."""
    motivos = []
    if analise["regra_id"] == "NENHUMA":
        motivos.append("nenhum modelo do catalogo se enquadra")
    if analise["confianca"] < LIMIAR_CONFIANCA:
        motivos.append(f"confianca {analise['confianca']:.2f} abaixo de {LIMIAR_CONFIANCA}")
    if not cnpjs_texto:
        motivos.append("nenhum CNPJ encontrado no contrato")
    desconhecidos = sorted(c for c in cnpjs_texto if c not in base_empresas)
    if desconhecidos:
        motivos.append(f"CNPJ fora da tabela empresas: {desconhecidos}")
    if set(analise["cnpjs_no_contrato"]) != set(cnpjs_texto):
        motivos.append("CNPJs do agente diferem do regex")
    clientes = sorted({base_empresas[c] for c in cnpjs_texto if c in base_empresas})
    if len(clientes) > 1:
        motivos.append(f"CNPJs de clientes diferentes: {clientes}")
    return ("vinculado" if not motivos else "pendente_aprovacao"), motivos, clientes


def hash_registro(registro):
    """SHA-256 do registro sem o campo 'hash', em JSON canonico (inclui o hash_anterior)."""
    corpo = {k: v for k, v in registro.items() if k != "hash"}
    canonico = json.dumps(corpo, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def ultimo_hash(caminho):
    if not caminho.exists():
        return "0" * 64
    linhas = [l for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]
    return json.loads(linhas[-1])["hash"] if linhas else "0" * 64


def gravar_auditoria(caminho, registro):
    """Acrescenta o registro ao log, encadeado ao hash do registro anterior."""
    registro["hash_anterior"] = ultimo_hash(caminho)
    registro["hash"] = hash_registro(registro)
    with open(caminho, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    catalogo = json.loads((RAIZ / "catalogo" / "regras.json").read_text(encoding="utf-8"))
    base_empresas = empresas()
    cliente_api = OpenAI(base_url=URL_API, api_key=os.environ["NVIDIA_API_KEY"])
    versao_prompt = hashlib.sha256((SISTEMA + json.dumps(catalogo)).encode()).hexdigest()[:12]
    saida = RAIZ / "saida"
    saida.mkdir(exist_ok=True)

    resumo = []
    for pdf in sorted((RAIZ / "dados" / "contratos").glob("*.pdf")):
        contrato = texto_pdf(pdf)
        cnpjs_texto = sorted(set(CNPJ_RE.findall(contrato)))
        analise = analisar(cliente_api, catalogo, contrato)
        status, motivos, clientes = decidir(analise, cnpjs_texto, base_empresas)
        gravar_auditoria(saida / "auditoria.jsonl", {
            "quando": datetime.now(timezone.utc).isoformat(),
            "arquivo": pdf.name, "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "modelo_llm": MODELO, "versao_prompt": versao_prompt,
            "cnpjs_regex": cnpjs_texto, "clientes": clientes,
            "analise": analise, "status": status, "motivos": motivos,
        })
        resumo.append((pdf.stem, analise, status, motivos))
        print(f"{pdf.stem}: {analise['regra_id']} ({analise['confianca']:.2f}) -> {status}")

    print("\n=== Agente x esperado ===")
    acertos = 0
    for stem, analise, status, motivos in resumo:
        ok = analise["regra_id"] == ESPERADO[stem]
        acertos += ok
        print(f"{'OK ' if ok else 'ERRO'} {stem:20} esperado={ESPERADO[stem]:8} agente={analise['regra_id']:8} {status}")
        for d in analise["divergencias"]:
            print(f"       divergencia: {d}")
        for p in analise["pontos_de_atencao"]:
            print(f"       atencao: {p}")
        for m in motivos:
            print(f"       motivo: {m}")
    print(f"\n{acertos}/{len(resumo)} classificacoes iguais ao esperado")


if __name__ == "__main__":
    main()
