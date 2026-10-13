import io
import unittest

import pandas as pd
from openpyxl import load_workbook

from estoque_pagina import exportar_estoque
from test_verbas import entrada, saida
from verbas import estoque_por_unidade, movimentacao_por_unidade, reposicao_por_unidade


class ConsolidacaoNissanTest(unittest.TestCase):
    def test_saldos_conservados_sem_duplicacao_e_consumo_so_da_ceasa(self):
        v = pd.DataFrame([
            entrada("2026-05-01", 190, cliente="CLIENTE - NISSAN B.LEME"),
            entrada("2026-05-01", 100, "tras", "CLIENTE - NISSAN B.LEME"),
            entrada("2026-05-01", 940, cliente="CLIENTE - NISSAN CEASA"),
            entrada("2026-05-01", 730, "tras", "CLIENTE - NISSAN CEASA"),
        ])
        s = pd.DataFrame([saida("2026-06-01", 131, 102, "Nissan Braz Leme"),
                          saida("2026-09-01", 773, 660, "Nissan Ceasa")])
        original_v, original_s = v.copy(deep=True), s.copy(deep=True)
        estoque = estoque_por_unidade(v, s, "2026-09-01")
        self.assertEqual(estoque.index.tolist(), ["NISSAN CEASA"])
        self.assertEqual(estoque.iloc[0].tolist(), [226, 68])
        self.assertFalse((estoque < 0).any().any())
        pd.testing.assert_frame_equal(estoque_por_unidade(v, s, "2026-09-01"), estoque)
        for mes in pd.date_range("2026-05-01", "2026-10-01", freq="MS"):
            mov = movimentacao_por_unidade(v, s, mes)
            for tipo in ("diant", "tras"):
                self.assertTrue((mov[f"inicial_{tipo}"] + mov[f"entrada_{tipo}"] -
                                 mov[f"saida_{tipo}"] == mov[f"estoque_{tipo}"]).all())
        r = reposicao_por_unidade(v, s, "2026-09-01")
        self.assertEqual(r.Unidade.unique().tolist(), ["NISSAN CEASA"])
        self.assertEqual(r["Consumo médio/mês"].tolist(), [773, 660])
        self.assertEqual(r["Meses com registro"].tolist(), [1, 1])
        self.assertEqual(r.Estoque.tolist(), [226, 68])
        mov = movimentacao_por_unidade(v, s, "2026-09-01")
        wb = load_workbook(io.BytesIO(exportar_estoque(mov, mov, pd.DataFrame(), r)), data_only=True)
        for ws in wb:
            for row in ws:
                self.assertFalse(any("LEME" in str(c.value).upper() for c in row))
        pd.testing.assert_frame_equal(v, original_v)
        pd.testing.assert_frame_equal(s, original_s)


if __name__ == "__main__":
    unittest.main()
