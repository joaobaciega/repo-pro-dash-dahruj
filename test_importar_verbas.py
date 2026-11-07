"""Leitura da aba Pagamentos (marcação Sim/Não + valor pago opcional)."""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from importar_verbas import ler_pagamentos


class PagamentosTest(unittest.TestCase):
    def ler(self, linhas):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as pasta:
            caminho = Path(pasta) / "base.xlsx"
            pd.DataFrame(linhas).to_excel(caminho, sheet_name="Pagamentos", index=False)
            return ler_pagamentos(caminho)

    def test_sem_colunas_de_valor_continua_funcionando(self):
        r = self.ler([{"Mês": dt.date(2026, 9, 1), "Consultor Pago": "Não", "Gerente Pago": "Não"}])
        self.assertEqual(r, [{"mes": dt.date(2026, 9, 1), "consultor_pago": 0, "gerente_pago": 0,
                              "valor_consultor": None, "valor_gerente": None}])

    def test_valor_informado_em_mes_pago(self):
        r = self.ler([
            {"Mês": dt.date(2026, 8, 1), "Consultor Pago": "Sim", "Gerente Pago": "Sim",
             "Valor Consultor": None, "Valor Gerente": None},
            {"Mês": dt.date(2026, 10, 15), "Consultor Pago": "Sim", "Gerente Pago": "Sim",
             "Valor Consultor": 10425, "Valor Gerente": "2.606,25"},
        ])
        self.assertEqual(r[0]["valor_consultor"], None)
        self.assertEqual(r[1]["mes"], dt.date(2026, 10, 1))
        self.assertEqual((r[1]["valor_consultor"], r[1]["valor_gerente"]), (10425.0, 2606.25))

    def test_valor_em_mes_nao_pago_trava(self):
        with self.assertRaises(SystemExit):
            self.ler([{"Mês": dt.date(2026, 9, 1), "Consultor Pago": "Não", "Gerente Pago": "Não",
                       "Valor Consultor": 500, "Valor Gerente": None}])

    def test_zero_em_mes_nao_pago_e_coerente(self):
        r = self.ler([{"Mês": dt.date(2026, 9, 1), "Consultor Pago": "Não", "Gerente Pago": "Não",
                       "Valor Consultor": 0, "Valor Gerente": 0}])
        self.assertEqual((r[0]["valor_consultor"], r[0]["valor_gerente"]), (None, None))

    def test_valor_ilegivel_trava(self):
        with self.assertRaises(SystemExit):
            self.ler([{"Mês": dt.date(2026, 10, 1), "Consultor Pago": "Sim", "Gerente Pago": "Sim",
                       "Valor Consultor": "dez mil", "Valor Gerente": None}])


if __name__ == "__main__":
    unittest.main()
