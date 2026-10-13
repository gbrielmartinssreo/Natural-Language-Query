"""Testes da resolução de caminhos em desenvolvimento e empacotado.

Executar:

    .venv/bin/python -m unittest discover -s tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import nlq.paths as paths


class TestModoDesenvolvimento(unittest.TestCase):
    def test_repo_nao_esta_frozen(self):
        self.assertFalse(paths.is_frozen())

    def test_frontend_tem_index(self):
        self.assertTrue((paths.frontend_dir() / "index.html").is_file())

    def test_prompts_do_agente(self):
        self.assertTrue((paths.prompts_dir() / "system_base.md").is_file())
        self.assertTrue((paths.prompts_dir() / "specific_role.md").is_file())

    def test_skills_do_agente(self):
        skills = list(paths.skills_dir().glob("*/SKILL.md"))
        self.assertGreaterEqual(len(skills), 1)

    def test_dados_ficam_em_sheets(self):
        self.assertEqual(paths.data_dir().name, "sheets")

    def test_env_na_raiz(self):
        self.assertEqual(paths.env_file().name, ".env")


class TestModoEmpacotado(unittest.TestCase):
    def test_recursos_internos_e_externos(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            meipass = tmp / "_internal"

            with (
                mock.patch.object(sys, "frozen", True, create=True),
                mock.patch.object(sys, "_MEIPASS", str(meipass), create=True),
                mock.patch.object(sys, "executable", str(tmp / "NLQ")),
            ):
                self.assertTrue(paths.is_frozen())

                # Recursos internos vão para dentro do pacote.
                self.assertEqual(
                    paths.frontend_dir(),
                    meipass / "frontend",
                )
                self.assertEqual(
                    paths.prompts_dir(),
                    meipass / "nlq" / "agent" / "prompts",
                )
                self.assertEqual(
                    paths.skills_dir(),
                    meipass / "nlq" / "agent" / "skills",
                )

                # Dados e credenciais ficam ao lado do executável.
                self.assertEqual(paths.data_dir(), tmp / "sheets")
                self.assertEqual(paths.env_file(), tmp / ".env")


if __name__ == "__main__":
    unittest.main()
