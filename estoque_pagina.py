"""Acompanhamento interno de estoque, protegido pelo acesso da aplicação."""

import io

import pandas as pd
import plotly.express as px
import streamlit as st

import db
from verbas import CATEGORIAS, calcular_verbas, movimentacao_por_unidade, reposicao_por_unidade
from verbas_pagina import MESES, dinheiro


COLUNAS_ESTOQUE = {
    "inicial_diant": "Inicial diant. (pares)", "entrada_diant": "Entradas diant. (pares)",
    "saida_diant": "Saídas diant. (pares)", "estoque_diant": "Saldo diant. (pares)",
    "inicial_tras": "Inicial tras. (un)", "entrada_tras": "Entradas tras. (un)",
    "saida_tras": "Saídas tras. (un)", "estoque_tras": "Saldo tras. (un)",
}


def exportar_estoque(movimento, historico, verba, reposicao=None):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        movimento.rename(columns=COLUNAS_ESTOQUE).to_excel(writer, sheet_name="Estoque por unidade")
        historico.rename(columns=COLUNAS_ESTOQUE).to_excel(writer, sheet_name="Evolução mensal")
        verba.to_excel(writer, sheet_name="Verba em estoque", index=False)
        if reposicao is not None:
            reposicao.drop(columns="Oferecer pedido").to_excel(writer, sheet_name="Reposição", index=False)
        from openpyxl.styles import Font, PatternFill
        for ws in writer.book:
            ws.freeze_panes = "B2"
            ws.auto_filter.ref = ws.dimensions
            for cel in ws[1]:
                cel.font = Font(bold=True, color="FFFFFF")
                cel.fill = PatternFill("solid", fgColor="EB5E33")
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = 28
                for cel in col[1:]:
                    if isinstance(cel.value, (int, float)):
                        cel.number_format = ('R$ #,##0.00' if ws.title == "Verba em estoque" else
                                             "0.00" if col[0].value in ("Consumo médio/mês", "Cobertura (meses)") else "#,##0")
    return buf.getvalue()


def pagina_estoque():
    # Além de ficar fora do menu público, protege leituras e downloads caso a
    # função seja chamada diretamente. O app revalida o prazo antes de rotear.
    if not st.session_state.get("lanc_ok"):
        st.error("Área restrita. Libere o acesso no cadeado da barra lateral.")
        return

    st.title("📦 Estoque")
    st.caption("Acompanhamento interno · entradas, vendas e posição de estoque por unidade.")
    try:
        vendas = db.ler_vendas_verbas()
        sell_out = db.ler_base_tidy()
        if vendas.empty or sell_out.empty:
            st.info("As bases de Sell In e Sell Out precisam estar preenchidas para acompanhar o estoque.")
            return
        # Valida classificação e tarifas com as mesmas regras da conciliação.
        mensal = calcular_verbas(vendas, sell_out, {}, {})
    except ValueError as exc:
        st.error(str(exc))
        return
    except Exception:
        st.error("Não foi possível carregar as bases de estoque. Verifique a conexão e tente novamente.")
        return

    ultima_in = pd.to_datetime(vendas["data"]).max()
    ultima_out = pd.to_datetime(sell_out["mes"]).max()
    st.caption(f"Sell In até {ultima_in:%d/%m/%Y} · Sell Out com lançamentos até {ultima_out:%m/%Y}. O último mês pode estar parcial.")
    if ultima_out.to_period("M") < ultima_in.to_period("M"):
        st.warning("O Sell Out termina antes do Sell In. O estoque pode incluir produtos cujas vendas ainda não foram lançadas.")

    ca, cm = st.columns([1, 2])
    ano = ca.selectbox("Ano", sorted(set(mensal.index.year), reverse=True), key="estoque_ano")
    meses = list(reversed(mensal[mensal.index.year == ano].index))
    mes = cm.selectbox("Posição ao final de", meses,
                       format_func=lambda m: f"{MESES[m.month]}/{m.year}", key="estoque_mes")
    movimento = movimentacao_por_unidade(vendas, sell_out, mes)
    unidades = st.multiselect("Unidades", list(movimento.index),
                              placeholder="Todas as unidades", key="estoque_unidades")
    selecionadas = unidades or list(movimento.index)
    movimento = movimento.loc[selecionadas]
    totais = movimento.sum()
    reposicao = reposicao_por_unidade(vendas, sell_out, mes)
    reposicao = reposicao[reposicao["Unidade"].isin(selecionadas)]
    alertas = reposicao[reposicao["Oferecer pedido"]]
    unidades_repor = alertas["Unidade"].nunique()

    historico = pd.DataFrame([
        movimentacao_por_unidade(vendas, sell_out, m).reindex(selecionadas, fill_value=0).sum()
        for m in mensal.index if m.year == ano and m <= mes
    ], index=[m for m in mensal.index if m.year == ano and m <= mes])
    historico.index.name = "Mês"
    divergencias = movimento[(movimento[["estoque_diant", "estoque_tras"]] < 0).any(axis=1)]

    cards = st.columns(4)
    cards[0].metric("Dianteiros em estoque (pares)", int(totais.estoque_diant))
    cards[1].metric("Traseiros em estoque (un)", int(totais.estoque_tras))
    cards[2].metric("Unidades com saldo negativo", len(divergencias))
    cards[3].metric("Unidades para novo pedido", unidades_repor)
    if not divergencias.empty:
        st.warning("Há saídas superiores às entradas registradas. Confira estoque inicial, transferências e cobertura das bases nas unidades destacadas abaixo.")
        with st.expander("Unidades para conferência", expanded=True):
            st.dataframe(divergencias[["estoque_diant", "estoque_tras"]].rename(columns=COLUNAS_ESTOQUE),
                         width="stretch")
    elif (historico[["estoque_diant", "estoque_tras"]] < 0).any().any():
        st.warning("O histórico do recorte contém saldo negativo. Confira as entradas e saídas nos meses anteriores.")

    st.subheader("Oportunidades de reposição")
    if unidades_repor:
        st.info(f"Oferecer novo pedido a {unidades_repor} unidade(s): o estoque de pelo menos um tipo está abaixo do consumo médio mensal.")
        st.dataframe(alertas.drop(columns="Oferecer pedido").style.format({
            "Consumo médio/mês": "{:.2f}", "Cobertura (meses)": "{:.2f}",
        }, na_rep="—"), hide_index=True, width="stretch")
    else:
        st.info("Nenhuma unidade com consumo registrado está abaixo da média mensal no recorte selecionado.")
    st.caption("Consumo médio = vendas totais ao consumidor ÷ meses com registros da unidade, desde o início do histórico até a posição selecionada, incluindo anos anteriores. Meses registrados com zero entram na média; meses sem registros não entram. O mês mais recente pode estar parcial.")
    with st.expander("Consumo médio de todas as unidades selecionadas"):
        st.dataframe(reposicao.drop(columns="Oferecer pedido").style.format({
            "Consumo médio/mês": "{:.2f}", "Cobertura (meses)": "{:.2f}",
        }, na_rep="—"), hide_index=True, width="stretch")
        st.caption("Cobertura = estoque ÷ consumo médio mensal. Menos de 1 mês indica reposição. Dianteiros e traseiros são avaliados separadamente; saldo negativo também exige conferência.")

    st.subheader("Movimentação por unidade")
    st.caption("Estoque inicial + entradas do mês − vendas do mês = saldo final. Dianteiros em pares; traseiros em unidades.")
    exibicao = movimento.copy()
    exibicao.loc["TOTAL"] = totais
    exibicao = exibicao.rename(columns=COLUNAS_ESTOQUE)
    st.dataframe(exibicao.style.format("{:,.0f}"), width="stretch")

    st.subheader("Evolução do estoque")
    grafico = historico[["estoque_diant", "estoque_tras"]].rename(columns={
        "estoque_diant": "Dianteiros (pares)", "estoque_tras": "Traseiros (un)"})
    grafico.index = [MESES[m.month][:3] for m in grafico.index]
    fig = px.line(grafico, markers=True, color_discrete_sequence=["#EB5E33", "#F5A623"])
    fig.update_layout(template="plotly_dark", xaxis_title=None, yaxis_title="Quantidade",
                      legend_title=None, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch")
    hist_exibicao = historico.copy()
    hist_exibicao.index = [f"{MESES[m.month]}/{m.year}" for m in historico.index]
    hist_exibicao.index.name = "Mês"
    with st.expander("Entradas e saídas mês a mês"):
        st.dataframe(hist_exibicao.rename(columns=COLUNAS_ESTOQUE).style.format("{:,.0f}"), width="stretch")

    valores = {}
    for cat, campo in CATEGORIAS.items():
        valores[cat] = sum(
            float(vendas.loc[vendas.tipo_refil == tipo, f"verba_{campo}"].iloc[0]) * totais[f"estoque_{tipo}"]
            for tipo in ("diant", "tras") if (vendas.tipo_refil == tipo).any()
        )
    verba = pd.DataFrame([{"Categoria": cat.title(), "Verba em estoque": round(valor, 2)}
                          for cat, valor in valores.items()])
    verba.loc[len(verba)] = ["Total", round(sum(valores.values()), 2)]
    with st.expander("Verba associada ao estoque"):
        st.dataframe(verba.style.format({"Verba em estoque": dinheiro}), hide_index=True, width="stretch")
        st.caption("Quantidade em estoque × tarifa por tipo de refil. Esta verba já integra o saldo geral de Verbas; não deve ser somada novamente. Os valores acompanham as unidades selecionadas.")
    with st.expander("Critérios de conferência"):
        st.markdown(
            "O estoque acumula todo o histórico disponível, com saldo inicial zero no início das bases. "
            "O filtro de ano não reinicia o saldo. Entradas vêm do Sell In e saídas, do Sell Out.\n\n"
            "Saldos negativos são mantidos para identificar entradas faltantes ou transferências entre lojas. "
            "Nissan Ceasa e Braz Leme são acompanhadas separadamente. Jeep Interlagos corresponde a Jeep W. Luiz."
        )
    st.download_button("Exportar acompanhamento de estoque (.xlsx)",
                       exportar_estoque(movimento, hist_exibicao, verba, reposicao),
                       file_name=f"estoque_{mes:%Y_%m}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
