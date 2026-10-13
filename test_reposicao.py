import io
import unittest

import pandas as pd
from openpyxl import load_workbook

from estoque_pagina import exportar_estoque, duracao_estoque, tabela_reposicao, destacar_reposicao
from test_verbas import entrada, saida
from verbas import movimentacao_por_unidade, reposicao_por_unidade


class ReposicaoTest(unittest.TestCase):
    def test_media_mensal_soma_consultores_inclui_zero_e_anos_anteriores(self):
        v = pd.DataFrame([entrada("2025-11-01", qtde=70)])
        s = pd.DataFrame([saida("2025-11-01", diant=20), saida("2025-11-01", diant=10),
                          saida("2025-12-01", diant=0), saida("2026-02-01", diant=30),
                          saida("2026-03-01", diant=1000)])
        # Novembro soma 30, dezembro 0, fevereiro 30: 60 / 3 = 20.
        # Janeiro não tem registros e março fica fora da posição selecionada.
        r = reposicao_por_unidade(v, s, "2026-02-01").iloc[0]
        self.assertEqual(r["Meses com registro"], 3)
        self.assertEqual(r["Consumo médio/mês"], 20)
        self.assertEqual(r["Estoque"], 10)
        self.assertEqual(r["Cobertura (meses)"], 0.5)
        self.assertTrue(r["Oferecer pedido"])

    def test_tipos_independentes_e_limite_estrito(self):
        v = pd.DataFrame([entrada(qtde=100), entrada(qtde=19, tipo="tras")])
        s = pd.DataFrame([saida(diant=50, tras=10)])
        r = reposicao_por_unidade(v, s, "2026-02-01")
        self.assertFalse(r.iloc[0]["Oferecer pedido"])  # Estoque igual à média.
        self.assertTrue(r.iloc[1]["Oferecer pedido"])   # Traseiro não compensado pelo dianteiro.

    def test_sem_historico_sem_consumo_e_saldo_negativo(self):
        v = pd.DataFrame([entrada(qtde=10), entrada(qtde=10, cliente="CLIENTE - HONDA CEASA")])
        s = pd.DataFrame([saida(diant=12)])
        r = reposicao_por_unidade(v, s, "2026-02-01")
        fiat = r[r.Unidade == "FIAT CEASA"]
        honda = r[r.Unidade == "HONDA CEASA"]
        self.assertTrue(fiat.iloc[0]["Oferecer pedido"])
        self.assertIn("conferir saldo negativo", fiat.iloc[0]["Situação"])
        self.assertEqual(fiat.iloc[1]["Situação"], "Sem consumo registrado")
        self.assertTrue(pd.isna(fiat.iloc[1]["Cobertura (meses)"]))
        self.assertTrue((honda["Situação"] == "Sem histórico").all())
        self.assertFalse(honda["Oferecer pedido"].any())

    def test_alias_e_inicio_individual_do_historico(self):
        v = pd.DataFrame([entrada(qtde=100), entrada(qtde=10, cliente="CLIENTE - JEEP INTERLAGOS")])
        s = pd.DataFrame([saida("2026-01-01", diant=20), saida("2026-02-01", diant=20),
                          saida("2026-02-01", diant=6, unidade="Jeep W. Luiz")])
        r = reposicao_por_unidade(v, s, "2026-02-01")
        nissan = r[(r.Unidade == "JEEP W LUIZ") & (r.Tipo == "Dianteiros (pares)")].iloc[0]
        self.assertEqual(nissan["Meses com registro"], 1)
        self.assertEqual(nissan["Consumo médio/mês"], 6)
        self.assertTrue(nissan["Oferecer pedido"])

    def test_exportacao_exibe_media_inteira_sem_alterar_calculo(self):
        v = pd.DataFrame([entrada(qtde=15)])
        s = pd.DataFrame([saida("2026-01-01", diant=5), saida("2026-02-01", diant=6)])
        r = reposicao_por_unidade(v, s, "2026-02-01")
        movimento = movimentacao_por_unidade(v, s, "2026-02-01")
        wb = load_workbook(io.BytesIO(exportar_estoque(movimento, movimento, pd.DataFrame(), r)), data_only=True)
        ws = wb["Reposição"]
        cols = {c.value: c.column for c in ws[1]}
        self.assertEqual(ws.cell(2, cols["Consumo dianteiro/mês"]).value, 6)
        self.assertEqual(ws.cell(2, cols["Consumo dianteiro/mês"]).number_format, "#,##0")
        self.assertEqual(ws.cell(2, cols["Oferecer pedido de"]).value, "Dianteiros")
        self.assertEqual(ws.cell(2, cols["Duração dianteiros"]).value, "21d")
        self.assertEqual(r.iloc[0]["Consumo médio/mês"], 5.5)
        self.assertEqual(wb["Estoque por unidade"].cell(1, 2).value, "Saldo diant. (pares)")
        self.assertTrue(wb["Estoque por unidade"].column_dimensions["D"].hidden)

    def test_duracao_em_dias_e_meses(self):
        for dias, esperado in [(0, "0d"), (0.5, "<1d"), (17.9, "17d"), (30, "30d"),
                               (31, "1m e 1d"), (42, "1m e 12d"), (60, "2m"), (75, "2m e 15d")]:
            with self.subTest(dias=dias):
                self.assertEqual(duracao_estoque(dias / 30), esperado)
        self.assertEqual(duracao_estoque(None), "—")
        self.assertEqual(duracao_estoque(-1), "Conferir saldo")

    def test_todas_unidades_ambos_produtos_e_destaques_independentes(self):
        v = pd.DataFrame([entrada(qtde=100), entrada(qtde=15, tipo="tras"),
                          entrada(qtde=10, cliente="CLIENTE - JEEP CEASA"),
                          entrada(qtde=10, tipo="tras", cliente="CLIENTE - JEEP CEASA"),
                          entrada(qtde=200, cliente="CLIENTE - HONDA CEASA")])
        s = pd.DataFrame([saida(diant=50, tras=10), saida(diant=6, tras=6, unidade="Jeep Ceasa"),
                          saida(diant=20, unidade="Honda Ceasa")])
        t = tabela_reposicao(reposicao_por_unidade(v, s, "2026-02-01")).set_index("Unidade", drop=False)
        self.assertEqual(len(t), 3)
        self.assertEqual(t.loc["FIAT CEASA", "Oferecer pedido de"], "Traseiros")
        self.assertEqual(t.loc["JEEP CEASA", "Oferecer pedido de"], "Dianteiros e traseiros")
        self.assertEqual(t.loc["HONDA CEASA", "Oferecer pedido de"], "—")
        cores = dict(zip(t.columns, destacar_reposicao(t.loc["FIAT CEASA"])))
        self.assertTrue(cores["Saldo traseiro (un)"])
        self.assertFalse(cores["Saldo dianteiro (pares)"])
        self.assertEqual(t.loc["HONDA CEASA", "Duração dianteiros"], "9m")
        self.assertEqual(t.loc["HONDA CEASA", "Duração traseiros"], "Sem consumo")


if __name__ == "__main__":
    unittest.main()
