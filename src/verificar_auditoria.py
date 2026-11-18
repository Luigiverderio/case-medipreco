"""Confere a integridade do log de auditoria.

Verifica, registro a registro: (1) o encadeamento com o hash anterior, (2) se o conteudo bate com o
proprio hash e (3) se o PDF guardado e o mesmo que foi lido (pdf_sha256). A logica fica em auditoria.py.
Uso: python src/verificar_auditoria.py [caminho_do_log]
"""
import sys
from pathlib import Path

from auditoria import CAMINHO, resumo, verificar


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    caminho = Path(sys.argv[1]) if len(sys.argv) > 1 else CAMINHO
    entradas = verificar(caminho)
    for e in entradas:
        nome = (e["registro"] or {}).get("arquivo", "?")
        for p in e["problemas"]:
            print(f"linha {e['n']} ({nome}): {p}")
    r = resumo(entradas)
    print(f"{r['total']} registros, ultimo hash {r['ultimo_hash'][:12]}...")
    print("INTEGRO" if r["integro"] else f"{r['problemas']} problema(s) encontrado(s)")
    sys.exit(0 if r["integro"] else 1)


if __name__ == "__main__":
    main()
