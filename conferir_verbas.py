"""Conferência somente leitura no SQL; gera relatório local, sem importar dados.

Uso: python conferir_verbas.py --destino online --saida conferencia_verbas.xlsx
"""

import argparse
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from importar_verbas import destinos, _url
from verbas import calcular_verbas, estoque_por_unidade
from verbas_pagina import tabela_ano, exportar_excel


def ler_bases(destino):
    cfg = destinos(destino)[0][1]
    engine = create_engine(_url(cfg), connect_args={"connect_timeout": 15})
    try:
        with engine.connect() as conn:
            vendas = pd.read_sql(text("SELECT * FROM vendas_verbas"), conn)
            sell_out = pd.read_sql(text(
                "SELECT mes, unidade, SUM(refil_diant) AS refil_diant, "
                "SUM(refil_tras) AS refil_tras FROM vw_base_tidy GROUP BY mes, unidade"
            ), conn)
            flags = pd.read_sql(text("SELECT * FROM verbas_pagamentos"), conn)
            marketing = pd.read_sql(text("SELECT * FROM verbas_marketing_pagos"), conn)
    finally:
        engine.dispose()
    vendas["data"] = pd.to_datetime(vendas["data"])
    sell_out["mes"] = pd.to_datetime(sell_out["mes"])
    pagos = {pd.Timestamp(r.mes): {"consultor": bool(r.consultor_pago), "gerente": bool(r.gerente_pago)}
             for r in flags.itertuples()}
    mkt = {pd.Timestamp(r.mes): float(r.valor) for r in marketing.itertuples()}
    return vendas, sell_out, pagos, mkt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destino", choices=["online", "local", "env"], default="online")
    parser.add_argument("--saida", type=Path, default=Path("conferencia_verbas.xlsx"))
    args = parser.parse_args()
    v, s, pagos, mkt = ler_bases(args.destino)
    mensal = calcular_verbas(v, s, pagos, mkt)
    fim = mensal.index[-1]
    args.saida.write_bytes(exportar_excel(tabela_ano(mensal, fim.year, pagos), estoque_por_unidade(v, s, fim)))
    print(mensal[["paga_consultor", "paga_gerente", "paga_marketing", "estoque_total", "acumulado_total"]].to_string())
    print(f"Relatório: {args.saida.resolve()}")


if __name__ == "__main__":
    main()
