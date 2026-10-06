"""Aba Verbas: provisão, vendas ao consumidor, estoque e pagamentos."""

import io

import pandas as pd
import plotly.express as px
import streamlit as st

import db
from verbas import CATEGORIAS, calcular_verbas, estoque_por_unidade


MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
COLUNAS = {
    "faturamento": "Faturamento Sell In",
    "entrada_diant": "Sell In dianteiros (pares)", "entrada_tras": "Sell In traseiros (un)",
    "saida_diant": "Sell Out dianteiros (pares)", "saida_tras": "Sell Out traseiros (un)",
    "estoque_diant": "Estoque dianteiros (pares)", "estoque_tras": "Estoque traseiros (un)",
    "gerada_consultor": "Provisão Consultor", "gerada_gerente": "Provisão Gerente",
    "gerada_marketing": "Provisão Marketing", "gerada_total": "Total provisionado (Sell In)",
    "realizada_consultor": "Devido Consultor (Sell Out)",
    "realizada_gerente": "Devido Gerente (Sell Out)",
    "realizada_marketing": "Marketing vinculado ao Sell Out",
    "paga_consultor": "Consultor Pago", "paga_gerente": "Gerente Pago",
    "paga_marketing": "Marketing Pago", "paga_total": "Total Pago",
    "estoque_consultor": "Verba em estoque Consultor", "estoque_gerente": "Verba em estoque Gerente",
    "estoque_marketing": "Verba em estoque Marketing", "estoque_total": "Total de verba em estoque",
    "a_pagar_consultor": "A pagar Consultor no mês", "a_pagar_gerente": "A pagar Gerente no mês",
    "pendente_consultor": "A pagar Consultor acumulado", "pendente_gerente": "A pagar Gerente acumulado",
    "saldo_consultor": "Variação saldo Consultor", "saldo_gerente": "Variação saldo Gerente",
    "saldo_marketing": "Variação saldo Marketing", "saldo_total": "Variação saldo total",
    "acumulado_consultor": "Saldo acumulado Consultor", "acumulado_gerente": "Saldo acumulado Gerente",
    "acumulado_marketing": "Saldo acumulado Marketing", "acumulado_total": "Saldo acumulado total",
}
QUANTIDADES = {c for c in COLUNAS if c.endswith(("_diant", "_tras"))}
SALDOS = {c for c in COLUNAS if c.startswith(("estoque_", "acumulado_", "pendente_"))}


def dinheiro(valor):
    return (f"R$ {valor:,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")


def tabela_ano(mensal, ano, pagos):
    """Fluxos são somados; estoque/saldo na linha total são posições finais."""
    rec = mensal[mensal.index.year == ano]
    tabela = rec[list(COLUNAS)].copy()
    tabela.index = [MESES[m.month] for m in rec.index]
    tabela["status"] = [
        "Sem Sell Out" if not (r.saida_diant or r.saida_tras) else
        "Pago" if all(pagos.get(m, {}).get(c) for c in ("consultor", "gerente")) else
        "Parcial" if any(pagos.get(m, {}).get(c) for c in ("consultor", "gerente")) else "Em aberto"
        for m, r in rec.iterrows()
    ]
    if not rec.empty:
        tabela.loc["TOTAL / POSIÇÃO FINAL"] = {
            **{c: rec[c].iloc[-1] if c in SALDOS else rec[c].sum() for c in COLUNAS}, "status": ""
        }
    return tabela.rename(columns={**COLUNAS, "status": "Status do Sell Out"}).rename_axis("Mês")


def exportar_excel(tabela, estoque):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        tabela.to_excel(writer, sheet_name="Verbas mensais")
        estoque.to_excel(writer, sheet_name="Estoque por unidade")
        pd.DataFrame({"Metodologia": [
            "Sell In provisiona a verba. Sell Out gera o valor devido a consultores e gerentes.",
            "Pago = valor devido pelo Sell Out do mês, apenas quando marcado como pago na planilha.",
            "Estoque = Sell In acumulado menos Sell Out acumulado, desde o início das bases (estoque inicial zero).",
            "Marketing mantém a reserva do Sell In, descontando os pagamentos efetivamente lançados.",
            "Verba de marketing em estoque é informativa e já integra o saldo de marketing; não somar novamente.",
            "TOTAL / POSIÇÃO FINAL soma fluxos; estoques, valores pendentes e saldos acumulados usam a última posição.",
            "Tarifas por tipo vêm da base de Sell In. Divergências de tarifa impedem o cálculo automático.",
            "Valores pagos a consultores/gerentes são calculados das marcações mensais, não de comprovantes bancários.",
        ]}).to_excel(writer, sheet_name="Metodologia", index=False)
        from openpyxl.styles import Font, PatternFill
        for ws in writer.book:
            ws.freeze_panes = "B2"
            ws.auto_filter.ref = ws.dimensions
            for cel in ws[1]:
                cel.font = Font(bold=True, color="FFFFFF")
                cel.fill = PatternFill("solid", fgColor="EB5E33")
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(50, max(18, len(str(col[0].value)) + 2))
            if ws.title == "Verbas mensais":
                for col in ws.iter_cols(min_col=2):
                    formato = "#,##0" if col[0].value in {COLUNAS[c] for c in QUANTIDADES} else 'R$ #,##0.00'
                    for cel in col[1:]:
                        if isinstance(cel.value, (int, float)):
                            cel.number_format = formato
    return buf.getvalue()


def pagina_verbas():
    st.title("💰 Verbas — Estoque, Saldo e Pagamentos")
    try:
        vendas = db.ler_vendas_verbas()
        sell_out = db.ler_base_tidy()
        pagos = db.ler_pagamentos_verba()
        mkt_pagos = db.ler_pagamentos_marketing()
    except Exception:
        st.error("Não foi possível ler as bases de Sell In, Sell Out e pagamentos. Tente novamente após verificar a conexão.")
        return
    if vendas.empty:
        st.info("Importe a planilha Base de dados para Dash Board.xlsx com importar_verbas.py para carregar o Sell In.")
        return
    if sell_out.empty:
        st.warning("A base de Sell Out está vazia. Cadastre as vendas ao consumidor para calcular pagamentos e estoque.")
        return
    try:
        mensal = calcular_verbas(vendas, sell_out, pagos, mkt_pagos)
    except ValueError as exc:
        st.error(str(exc))
        return
    anos = sorted(set(mensal.index.year), reverse=True)
    ca, cm, _ = st.columns([1, 2, 3])
    ano = ca.selectbox("Ano", anos)
    do_ano = mensal[mensal.index.year == ano]
    opcoes = ["Ano todo"] + [MESES[m.month] for m in reversed(do_ano.index)]
    escolha = cm.selectbox("📅 Mês", opcoes, help="Os movimentos são do período selecionado; estoques e saldos acumulam todo o histórico até o fim desse período.")
    rec = do_ano if escolha == "Ano todo" else do_ano[do_ano.index.month == MESES.index(escolha)]
    fim = rec.index[-1]
    periodo = str(ano) if escolha == "Ano todo" else f"{escolha}/{ano}"
    soma, posicao = rec.sum(numeric_only=True), rec.iloc[-1]
    ultima_in = pd.to_datetime(vendas["data"]).max()
    ultima_out = pd.to_datetime(sell_out["mes"]).max()
    st.caption(f"Sell In até {ultima_in:%d/%m/%Y} · Sell Out com lançamentos até {ultima_out:%m/%Y} · exibindo {periodo}. O último mês pode estar parcial.")
    if ultima_out.to_period("M") < ultima_in.to_period("M"):
        st.warning("O Sell Out termina antes do Sell In. O estoque calculado pode incluir produtos cujas vendas ao consumidor ainda não foram lançadas.")

    k = st.columns(3)
    k[0].metric("Faturamento Sell In", dinheiro(soma.faturamento))
    k[1].metric("Sell In dianteiros (pares)", f"{int(soma.entrada_diant):,}".replace(",", "."))
    k[2].metric("Sell In traseiros (un)", f"{int(soma.entrada_tras):,}".replace(",", "."))
    k = st.columns(2)
    k[0].metric("Sell Out dianteiros (pares)", f"{int(soma.saida_diant):,}".replace(",", "."))
    k[1].metric("Sell Out traseiros (un)", f"{int(soma.saida_tras):,}".replace(",", "."))

    def valores(titulo, dados, prefixo, total=True):
        st.subheader(titulo)
        cols = st.columns(4 if total else 3)
        for i, cat in enumerate(CATEGORIAS):
            cols[i].metric(cat.title(), dinheiro(dados[f"{prefixo}_{cat}"]))
        if total:
            cols[3].metric("Total", dinheiro(dados[f"{prefixo}_total"]))

    with st.container(key="verba_gerada"):
        valores(f"Verba provisionada pelo Sell In — {periodo}", soma, "gerada")
    st.subheader(f"Verba devida pelo Sell Out — {periodo}")
    c = st.columns(3)
    c[0].metric("Consultor", dinheiro(soma.realizada_consultor))
    c[1].metric("Gerente", dinheiro(soma.realizada_gerente))
    c[2].metric("Total devido", dinheiro(soma.realizada_consultor + soma.realizada_gerente))
    valores(f"Verba paga — {periodo}", soma, "paga")
    st.caption("Consultor e gerente: Sell Out × tarifa da planilha, nos meses marcados como pagos. Marketing: valores dos pagamentos lançados.")
    valores(f"Saldo acumulado até {MESES[fim.month]}/{fim.year}", posicao, "acumulado")
    st.caption("Consultor e gerente: inclui verba em estoque e verba de vendas ainda não pagas. Marketing: reserva do Sell In menos pagamentos de eventos.")
    c = st.columns(2)
    c[0].metric("Consultor a pagar — Sell Out acumulado", dinheiro(posicao.pendente_consultor))
    c[1].metric("Gerente a pagar — Sell Out acumulado", dinheiro(posicao.pendente_gerente))

    valores(f"Verba vinculada ao estoque até {MESES[fim.month]}/{fim.year}", posicao, "estoque")
    c = st.columns(2)
    c[0].metric("Estoque dianteiros (pares)", int(posicao.estoque_diant))
    c[1].metric("Estoque traseiros (un)", int(posicao.estoque_tras))
    st.caption("Estoque acumulado = entradas Sell In − saídas Sell Out. A parcela de marketing em estoque já está incluída na reserva; não é um saldo adicional.")
    estoque = estoque_por_unidade(vendas, sell_out, fim)
    if (estoque < 0).any().any() or (mensal.loc[:fim, ["estoque_diant", "estoque_tras"]] < 0).any().any():
        st.warning("Há saídas superiores às entradas registradas em alguma loja ou mês. Confira estoque inicial, transferências e cobertura das bases. Os saldos negativos foram preservados para conferência.")
    with st.expander("Estoque por unidade"):
        st.dataframe(estoque, width="stretch")
    with st.expander("Como os valores são calculados"):
        st.markdown(
            "**Provisão:** quantidades do Sell In × verbas unitárias da planilha.\n\n"
            "**Devido a consultor/gerente:** quantidades do Sell Out × respectivas tarifas. "
            "Comprar em janeiro e vender em fevereiro gera pagamento referente a fevereiro.\n\n"
            "**Pago:** valor devido pelo Sell Out somente nos meses marcados na aba Pagamentos. "
            "A marcação de janeiro sem Sell Out não gera pagamento.\n\n"
            "**Saldo acumulado:** provisão de todo o histórico menos pagamentos até o mês selecionado. "
            "Para consultor/gerente, é a soma da verba em estoque com o Sell Out ainda não pago.\n\n"
            "**Marketing:** a reserva nasce no Sell In e os gastos são os valores da aba de marketing.\n\n"
            "O cálculo começa com estoque inicial zero e usa tarifas uniformes por tipo de refil, "
            "conforme a planilha. Diferenças de tarifa exigem revisão da regra, pois o Sell Out não identifica o SKU."
        )
    st.subheader(f"Verbas mês a mês — {ano}")
    tabela = tabela_ano(mensal, ano, pagos)
    formatos = {COLUNAS[c]: ("{:,.0f}" if c in QUANTIDADES else dinheiro) for c in COLUNAS}
    st.dataframe(tabela.style.format(formatos), width="stretch")
    st.caption("A linha TOTAL / POSIÇÃO FINAL soma os movimentos do ano e mostra a última posição de estoque, pendências e saldos, incluindo o histórico anterior ao ano. Meses futuros não são projetados.")
    estoque_ano = estoque_por_unidade(vendas, sell_out, do_ano.index[-1])
    st.download_button("Exportar relatório (.xlsx)", exportar_excel(tabela, estoque_ano),
                       file_name=f"verbas_mes_a_mes_{ano}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.subheader("Provisão e pagamentos mês a mês")
    grafico = do_ano[["gerada_total", "paga_total"]].rename(columns={
        "gerada_total": "Provisionado (Sell In)", "paga_total": "Pago"})
    grafico.index = [MESES[m.month][:3] for m in grafico.index]
    fig = px.bar(grafico, barmode="group", color_discrete_sequence=["#EB5E33", "#F5A623"])
    fig.update_layout(template="plotly_dark", xaxis_title=None, yaxis_title=None,
                      legend_title=None, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_yaxes(tickprefix="R$ ")
    st.plotly_chart(fig, width="stretch")
