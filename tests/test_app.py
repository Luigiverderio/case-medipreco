import json
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

import app as webapp  # noqa: E402


class ContratosWebTest(unittest.TestCase):
    def setUp(self):
        self.client = webapp.app.test_client()

    def test_paginas_principais_abrem(self):
        contratos = self.client.get("/contratos")
        self.assertEqual(contratos.status_code, 200)
        self.assertEqual(self.client.get("/aprovacoes").status_code, 200)
        pagina = contratos.get_data(as_text=True)
        self.assertIn("Analisar contrato", pagina)
        self.assertNotIn("NVIDIA", pagina)
        self.assertNotIn("consentimento", pagina)

    def test_upload_exige_pdf(self):
        resposta = self.client.post(
            "/contratos",
            data={"contrato": (io.BytesIO(b"texto"), "contrato.txt")},
            content_type="multipart/form-data",
        )
        self.assertIn("precisa estar em PDF", resposta.get_data(as_text=True))

    def test_contrato_conhecido_vincula_e_novo_vai_para_aprovacao(self):
        pdf = (RAIZ / "dados" / "contratos" / "aurora-logistica.pdf").read_bytes()
        base = {
            "cliente": "Aurora Logística",
            "cnpjs_no_contrato": ["41.220.871/0001-16"],
            "campos": [{"campo": "base", "valor": "vida", "clausula": "5.1"}],
            "regra_id": "M1",
            "justificativa": "Estrutura compatível.",
            "divergencias": [],
            "pontos_de_atencao": [],
            "confianca": 0.95,
        }
        with tempfile.TemporaryDirectory() as pasta:
            temp = Path(pasta)
            with (patch.object(webapp, "ANALISES", temp / "analises"),
                  patch.object(webapp, "UPLOADS", temp / "uploads"),
                  patch.object(webapp, "AUDITORIA", temp / "auditoria.jsonl"),
                  patch.object(webapp, "empresas", return_value={"41.220.871/0001-16": "Aurora Logística"}),
                  patch.object(webapp, "analisar", return_value=base),
                  patch.dict(os.environ, {"NVIDIA_API_KEY": "teste"})):
                vinculado = webapp.processar_pdf("aurora.pdf", pdf)
                self.assertEqual(vinculado["status"], "vinculado")

                diferente = dict(base, regra_id="NENHUMA", divergencias=["método novo"])
                with patch.object(webapp, "analisar", return_value=diferente):
                    pendente = webapp.processar_pdf("novo.pdf", pdf)
                self.assertEqual(pendente["status"], "pendente_aprovacao")
                self.assertTrue((temp / "auditoria.jsonl").exists())
                linhas = (temp / "auditoria.jsonl").read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(linhas), 2)
                self.assertIn("hash", json.loads(linhas[-1]))


if __name__ == "__main__":
    unittest.main()


class AuditoriaTest(unittest.TestCase):
    def test_cadeia_detecta_adulteracao_e_pagina_abre(self):
        from vincular import gravar_auditoria
        import auditoria as aud
        with tempfile.TemporaryDirectory() as pasta:
            log = Path(pasta) / "auditoria.jsonl"
            for nome in ("a.pdf", "b.pdf", "c.pdf"):
                gravar_auditoria(log, {"quando": "2026-11-18T12:00:00+00:00", "acao": "analise_contrato", "arquivo": nome,
                                       "pdf_sha256": "0" * 64, "status": "vinculado", "motivos": [], "analise": {}})
            self.assertTrue(aud.resumo(aud.verificar(log))["integro"])
            linhas = log.read_text(encoding="utf-8").splitlines()
            linhas[1] = linhas[1].replace("b.pdf", "x.pdf")
            log.write_text("\n".join(linhas) + "\n", encoding="utf-8")
            r = aud.resumo(aud.verificar(log))
            self.assertFalse(r["integro"])
            self.assertEqual(r["problemas"], 1)  # so o registro alterado: o hash gravado dele nao mudou
            self.assertIn("conteúdo alterado", aud.verificar(log)[1]["problemas"][0])
