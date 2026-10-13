"""Conciliação mensal Sell In / Sell Out, sem acesso ao banco ou ao Streamlit."""

import re
import unicodedata

import pandas as pd


CATEGORIAS = {"consultor": "consultor", "gerente": "gerente", "marketing": "reserva"}


def calcular_verbas(vendas, sell_out, pagos, marketing_pagos):
    """Calcula todo o histórico antes de qualquer filtro de ano/mês.

    Sell In provisiona; Sell Out gera direito ao pagamento de consultor/gerente.
    Flags de pagamento referem-se ao mês do Sell Out. Marketing mantém o caixa
    provisionado no Sell In e desconta os valores efetivamente lançados.
    Estoque inicial = zero no início das bases; diferenças negativas são visíveis.

    O Sell Out só identifica dianteiro/traseiro, não SKU. Por isso as tarifas
    da planilha precisam ser uniformes por tipo no histórico. Havendo tarifas
    diferentes, não é seguro inventar uma média ou uma regra de alocação.
    """
    v, s = vendas.copy(), sell_out.copy()
    v["data"] = pd.to_datetime(v["data"], errors="raise")
    s["mes"] = pd.to_datetime(s["mes"], errors="raise")
    if v["data"].isna().any() or s["mes"].isna().any():
        raise ValueError("Há registros sem data nas bases de Sell In/Sell Out.")
    if not v["tipo_refil"].isin(["diant", "tras"]).all():
        raise ValueError("Há produtos sem tipo de refil no Sell In. Complete a aba Verbas e importe novamente.")
    for frame, cols in ((v, ["qtde"]), (s, ["refil_diant", "refil_tras"])):
        for col in cols:
            frame[col] = pd.to_numeric(frame[col], errors="raise")
            if frame[col].isna().any() or (frame[col] < 0).any() or (frame[col] % 1 != 0).any():
                raise ValueError(f"Quantidades inválidas em {col}; revise a base antes de calcular as verbas.")
    v["mes"] = v["data"].dt.to_period("M").dt.to_timestamp()
    s["mes"] = s["mes"].dt.to_period("M").dt.to_timestamp()
    datas = list(v["mes"]) + list(s["mes"]) + list(pagos) + list(marketing_pagos)
    if not datas:
        raise ValueError("Não há histórico para calcular as verbas.")
    meses = pd.date_range(min(datas), max(datas), freq="MS")
    mensal = pd.DataFrame(index=meses)
    mensal.index.name = "mes"
    mensal["faturamento"] = v.groupby("mes")["total_item"].sum().reindex(meses, fill_value=0)
    for cat in CATEGORIAS:
        mensal[f"gerada_{cat}"] = 0.0
        mensal[f"realizada_{cat}"] = 0.0
    for tipo in ("diant", "tras"):
        vt = v[v["tipo_refil"] == tipo]
        mensal[f"entrada_{tipo}"] = vt.groupby("mes")["qtde"].sum().reindex(meses, fill_value=0)
        mensal[f"saida_{tipo}"] = s.groupby("mes")[f"refil_{tipo}"].sum().reindex(meses, fill_value=0)
        mensal[f"estoque_{tipo}"] = (mensal[f"entrada_{tipo}"] - mensal[f"saida_{tipo}"]).cumsum()
        for cat, campo in CATEGORIAS.items():
            tarifas = pd.to_numeric(vt[f"verba_{campo}"], errors="raise")
            if tarifas.isna().any() or (tarifas < 0).any() or tarifas.nunique() > 1:
                raise ValueError(f"Tarifas de {cat} para refil {tipo} divergentes. O Sell Out não identifica o produto; revise a regra de tarifa antes de calcular.")
            if tarifas.empty and mensal[f"saida_{tipo}"].sum():
                raise ValueError(f"Sell Out de refil {tipo} sem tarifa correspondente no Sell In.")
            tarifa = float(tarifas.iloc[0]) if not tarifas.empty else 0.0
            totais = pd.to_numeric(vt[f"total_{campo}"], errors="raise")
            if totais.isna().any() or ((totais - vt["qtde"] * tarifas).abs() > 0.011).any():
                raise ValueError(f"Total de {cat} não confere com quantidade × tarifa no Sell In.")
            mensal[f"gerada_{cat}"] += vt.assign(valor=totais).groupby("mes")["valor"].sum().reindex(meses, fill_value=0)
            mensal[f"realizada_{cat}"] += mensal[f"saida_{tipo}"] * tarifa
    for cat in CATEGORIAS:
        if cat == "marketing":
            mensal[f"paga_{cat}"] = [float(marketing_pagos.get(m, 0)) for m in meses]
        else:
            mensal[f"paga_{cat}"] = mensal[f"realizada_{cat}"] * [bool(pagos.get(m, {}).get(cat)) for m in meses]
        mensal[f"estoque_{cat}"] = (mensal[f"gerada_{cat}"] - mensal[f"realizada_{cat}"]).cumsum()
        mensal[f"saldo_{cat}"] = mensal[f"gerada_{cat}"] - mensal[f"paga_{cat}"]
        mensal[f"acumulado_{cat}"] = mensal[f"saldo_{cat}"].cumsum()
        if cat != "marketing":
            mensal[f"a_pagar_{cat}"] = mensal[f"realizada_{cat}"] - mensal[f"paga_{cat}"]
            mensal[f"pendente_{cat}"] = mensal[f"a_pagar_{cat}"].cumsum()
    for prefixo in ("gerada", "realizada", "paga", "estoque", "saldo", "acumulado"):
        mensal[f"{prefixo}_total"] = mensal[[f"{prefixo}_{c}" for c in CATEGORIAS]].sum(axis=1)
    return mensal.round(2)


def _chave_unidade(nome):
    nome = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode().upper()
    nome = nome.rsplit(" - ", 1)[-1]
    nome = re.sub(r"[^A-Z0-9]+", " ", nome).strip()
    return {"JEEP INTERLAGOS": "JEEP W LUIZ", "JEEP VL GUILHERME": "JEEP VILA GUILHERME",
            "NISSAN B LEME": "NISSAN BRAZ LEME"}.get(nome, nome)


def estoque_por_unidade(vendas, sell_out, ate):
    """Saldo físico acumulado, por loja, incluindo diferenças negativas."""
    v, s = vendas.copy(), sell_out.copy()
    limite = pd.Timestamp(ate).to_period("M").end_time
    v = v[pd.to_datetime(v["data"]) <= limite]
    s = s[pd.to_datetime(s["mes"]) <= limite]
    v["unidade"] = v["cliente"].map(_chave_unidade)
    s["unidade"] = s["unidade"].map(_chave_unidade)
    unidades = sorted(set(v["unidade"]) | set(s["unidade"]))
    estoque = pd.DataFrame(index=pd.Index(unidades, name="Unidade"))
    for tipo, rotulo in (("diant", "Dianteiros (pares)"), ("tras", "Traseiros (un)")):
        entrada = v[v["tipo_refil"] == tipo].groupby("unidade")["qtde"].sum()
        saida = s.groupby("unidade")[f"refil_{tipo}"].sum()
        estoque[rotulo] = entrada.reindex(unidades, fill_value=0) - saida.reindex(unidades, fill_value=0)
    return estoque.astype(int)


def movimentacao_por_unidade(vendas, sell_out, mes):
    """Estoque inicial + entradas − saídas = estoque final, por loja e tipo."""
    periodo = pd.Period(mes, "M")
    atual = estoque_por_unidade(vendas, sell_out, periodo.start_time)
    anterior = estoque_por_unidade(vendas, sell_out, (periodo - 1).start_time)
    v, s = vendas.copy(), sell_out.copy()
    v = v[pd.to_datetime(v["data"]).dt.to_period("M") == periodo]
    s = s[pd.to_datetime(s["mes"]).dt.to_period("M") == periodo]
    v["unidade"] = v["cliente"].map(_chave_unidade)
    s["unidade"] = s["unidade"].map(_chave_unidade)
    resultado = pd.DataFrame(index=atual.index)
    for tipo, rotulo in (("diant", "Dianteiros (pares)"), ("tras", "Traseiros (un)")):
        entrada = v[v["tipo_refil"] == tipo].groupby("unidade")["qtde"].sum()
        saida = s.groupby("unidade")[f"refil_{tipo}"].sum()
        resultado[f"inicial_{tipo}"] = anterior[rotulo].reindex(atual.index, fill_value=0)
        resultado[f"entrada_{tipo}"] = entrada.reindex(atual.index, fill_value=0)
        resultado[f"saida_{tipo}"] = saida.reindex(atual.index, fill_value=0)
        resultado[f"estoque_{tipo}"] = atual[rotulo]
    return resultado.astype(int)


def reposicao_por_unidade(vendas, sell_out, ate):
    """Compara estoque com a média de todos os meses registrados por loja.

    A base tidy contém o acumulado vigente por consultor/mês. Primeiro somamos
    os consultores; depois calculamos a média mensal, sem somar versões da
    trilha de alterações. Meses registrados com zero entram na média; ausência
    de lançamento não é interpretada como venda zero. Não usa meses futuros
    em relação à posição selecionada nem limita o histórico ao ano do filtro.
    """
    estoque = estoque_por_unidade(vendas, sell_out, ate)
    s = sell_out.copy()
    s["mes"] = pd.to_datetime(s["mes"]).dt.to_period("M")
    s = s[s["mes"] <= pd.Period(ate, "M")]
    s["unidade"] = s["unidade"].map(_chave_unidade)
    mensal = s.groupby(["unidade", "mes"])[["refil_diant", "refil_tras"]].sum()
    medias = mensal.groupby(level="unidade").mean()
    meses = mensal.groupby(level="unidade").size()
    linhas = []
    for unidade, saldos in estoque.iterrows():
        n = int(meses.get(unidade, 0))
        for tipo, rotulo in (("diant", "Dianteiros (pares)"), ("tras", "Traseiros (un)")):
            saldo = int(saldos[rotulo])
            media = float(medias.loc[unidade, f"refil_{tipo}"]) if n else None
            oferecer = n > 0 and media > 0 and saldo < media
            situacao = ("Oferecer novo pedido" if oferecer else
                        "Sem histórico" if not n else
                        "Sem consumo registrado" if media == 0 else "Estoque suficiente")
            if saldo < 0:
                situacao += " · conferir saldo negativo"
            linhas.append({
                "Unidade": unidade, "Tipo": rotulo, "Estoque": saldo,
                "Consumo médio/mês": media, "Meses com registro": n,
                "Cobertura (meses)": saldo / media if n and media > 0 else None,
                "Oferecer pedido": oferecer, "Situação": situacao,
            })
    return pd.DataFrame(linhas, columns=[
        "Unidade", "Tipo", "Estoque", "Consumo médio/mês", "Meses com registro",
        "Cobertura (meses)", "Oferecer pedido", "Situação",
    ])
