"""Testes da escolha de porta do launcher desktop.

Executar:

    .venv/bin/python -m unittest discover -s tests -v
"""

import socket
import unittest

import nlq.desktop as desktop


class TestEscolherSocket(unittest.TestCase):
    def test_retorna_porta_livre(self):
        sock, porta = desktop.escolher_socket(base=0)

        try:
            self.assertGreater(porta, 0)
        finally:
            sock.close()

    def test_pula_porta_ocupada(self):
        ocupado = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ocupado.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ocupado.bind((desktop.HOST, 0))
        ocupado.listen()

        porta = ocupado.getsockname()[1]

        try:
            sock, escolhida = desktop.escolher_socket(
                base=porta,
                tentativas=5,
            )

            try:
                self.assertNotEqual(escolhida, porta)
            finally:
                sock.close()
        finally:
            ocupado.close()


if __name__ == "__main__":
    unittest.main()
