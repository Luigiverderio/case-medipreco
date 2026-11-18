"""Leitura e verificacao do log de auditoria (saida/auditoria.jsonl).

Cada linha e um registro de uma acao, encadeado ao anterior por hash. Para registrar uma acao nova
(aprovacao, rejeicao, mudanca de regra...), basta gravar com vincular.gravar_auditoria incluindo o campo
"acao" e cadastrar o rotulo em ACOES: a pagina Auditoria, os filtros e a verificacao ja funcionam.
"""
import hashlib
import json
from pathlib import Path

from vincular import RAIZ, hash_registro

CAMINHO = RAIZ / "saida" / "auditoria.jsonl"
UPLOADS = RAIZ / "dados" / "uploads"
EXEMPLOS = RAIZ / "dados" / "contratos"
ZERO = "0" * 64

ACOES = {
    "analise_contrato": "Análise de contrato",
    "aprovacao_regra": "Aprovação de regra",
    "rejeicao_regra": "Rejeição de regra",
    "exclusao_analise": "Exclusão de submissão",
}
ACAO_PADRAO = "analise_contrato"  # registros antigos nao tem o campo "acao"


def acao_de(registro):
    return registro.get("acao", ACAO_PADRAO)


def rotulo_acao(acao):
    return ACOES.get(acao, acao)


def referencia(registro):
    """Identificador curto e estavel do registro (inicio do hash), usado na URL de detalhe."""
    return registro.get("hash", "")[:12]


def pdf_do_registro(registro):
    if registro.get("id"):
        caminho = UPLOADS / f"{registro['id']}-{registro.get('arquivo', '')}"
    else:
        caminho = EXEMPLOS / registro.get("arquivo", "")
    return caminho if caminho.is_file() else None


def verificar(caminho=CAMINHO):
    """Devolve uma entrada por linha do log: {"n", "registro", "problemas"}.

    Confere (1) o encadeamento com o hash anterior, (2) se o conteudo bate com o proprio hash e
    (3) se o PDF guardado e o mesmo que foi lido.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        return []
    entradas, anterior = [], ZERO
    linhas = [l for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]
    for n, linha in enumerate(linhas, 1):
        try:
            registro = json.loads(linha)
        except json.JSONDecodeError:
            entradas.append({"n": n, "registro": None, "problemas": ["linha ilegível"]})
            continue
        problemas = []
        if registro.get("hash_anterior") != anterior:
            problemas.append("encadeamento quebrado: falta ou sobra registro antes dele")
        if hash_registro(registro) != registro.get("hash"):
            problemas.append("conteúdo alterado depois de gravado")
        pdf = pdf_do_registro(registro)
        if pdf and hashlib.sha256(pdf.read_bytes()).hexdigest() != registro.get("pdf_sha256"):
            problemas.append("o PDF guardado é diferente do que foi analisado")
        anterior = registro.get("hash", "")
        entradas.append({"n": n, "registro": registro, "problemas": problemas})
    return entradas


def resumo(entradas):
    com_problema = [e for e in entradas if e["problemas"]]
    return {
        "total": len(entradas),
        "integro": not com_problema,
        "problemas": len(com_problema),
        "ultimo_hash": next((e["registro"].get("hash", "") for e in reversed(entradas) if e["registro"]), ZERO),
    }


def filtrar(entradas, acao="", resultado="", busca=""):
    busca = busca.strip().lower()
    saida = []
    for e in entradas:
        r = e["registro"] or {}
        if acao and acao_de(r) != acao:
            continue
        if resultado and r.get("status") != resultado:
            continue
        if busca:
            alvo = " ".join([r.get("arquivo", ""), " ".join(r.get("clientes", [])), r.get("hash", ""),
                             r.get("pdf_sha256", ""), r.get("analise", {}).get("cliente", "")]).lower()
            if busca not in alvo:
                continue
        saida.append(e)
    return saida
