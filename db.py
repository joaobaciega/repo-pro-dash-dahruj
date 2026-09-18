"""
Fase 3 — Camada de dados (db.py)

Centraliza a conexão com o MySQL e as funções de leitura/gravação usadas pelo
app Streamlit (Fases 4 e 5). O app nunca escreve SQL direto: chama estas funções.

Configuração: crie o arquivo .streamlit/secrets.toml com:

    [mysql]
    host = "127.0.0.1"
    port = 3306
    user = "root"
    password = "suasenha"
    database = "dashboard_dahruj"

Para testar a conexão isoladamente (fora do Streamlit), rode na pasta do projeto:
    python db.py
"""

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


def _build_url(cfg):
    """Monta a URL de conexão a partir de um dicionário de config."""
    return URL.create(
        "mysql+pymysql",
        username=cfg["user"],
        password=cfg["password"],
        host=cfg.get("host", "127.0.0.1"),
        port=int(cfg.get("port", 3306)),
        database=cfg["database"],
        query={"charset": "utf8mb4"},
    )


@st.cache_resource
def get_engine():
    """Engine SQLAlchemy criada uma única vez e reaproveitada (cache_resource)."""
    return create_engine(_build_url(st.secrets["mysql"]), pool_pre_ping=True)


# ------------------------------- Leituras -------------------------------
@st.cache_data(ttl=60)
def listar_unidades():
    """Unidades para o filtro do app (id, nome de exibição e preços da marca).
    Os preços vêm junto para a tela calcular a prévia do faturamento."""
    eng = get_engine()
    with eng.connect() as conn:
        rows = conn.execute(text(
            "SELECT u.id, u.nome_exibicao, u.marca, u.loja, u.gerente, "
            "       p.preco_diant, p.preco_tras "
            "FROM unidades u "
            "JOIN precos_marca p ON p.marca = u.marca "
            "ORDER BY u.nome_exibicao"
        )).mappings().all()
    saida = []
    for r in rows:
        d = dict(r)
        d["preco_diant"] = float(d["preco_diant"])
        d["preco_tras"] = float(d["preco_tras"])
        saida.append(d)
    return saida


@st.cache_data(ttl=60)
def listar_consultores(unidade_id):
    """Consultores ATUALMENTE lotados numa unidade (id + nome).
    A lotação vem de `consultor_unidade` (vínculo vigente = vigencia_fim IS NULL),
    então um consultor transferido deixa de aparecer na unidade antiga e passa
    a aparecer na nova, sem afetar o histórico de lançamentos já feitos."""
    eng = get_engine()
    with eng.connect() as conn:
        rows = conn.execute(text(
            "SELECT c.id, c.nome FROM consultores c "
            "JOIN consultor_unidade cu ON cu.consultor_id = c.id "
            "WHERE cu.unidade_id = :uid AND cu.vigencia_fim IS NULL "
            "ORDER BY c.nome"
        ), {"uid": unidade_id}).mappings().all()
    return [dict(r) for r in rows]


@st.cache_data(ttl=60)
def ler_base_tidy():
    """Base completa já calculada (a partir da view) para o dashboard."""
    eng = get_engine()
    with eng.connect() as conn:
        df = pd.read_sql(text("SELECT * FROM vw_base_tidy"), conn)
    df["mes"] = pd.to_datetime(df["mes"])
    return df


@st.cache_data(ttl=60)
def ler_vendas_verbas():
    """Base da aba Verbas: vendas por produto, com as três verbas por linha.

    Vem de `vendas_verbas`, alimentada por `importar_verbas.py` a partir do Excel
    — não da view `vw_base_tidy`, que é outra base (lançamentos por consultor).

    Devolve DataFrame vazio se a tabela ainda não existir: o app trata isso como
    "base não importada" em vez de estourar erro de conexão.
    """
    eng = get_engine()
    try:
        with eng.connect() as conn:
            df = pd.read_sql(text("SELECT * FROM vendas_verbas"), conn)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    df["data"] = pd.to_datetime(df["data"])
    # DECIMAL chega como Decimal; float evita Decimal × float nas agregações.
    for c in ("preco_unit", "total_item", "verba_consultor", "total_consultor",
              "verba_gerente", "total_gerente", "verba_reserva", "total_reserva"):
        df[c] = df[c].astype(float)
    df["qtde"] = df["qtde"].astype(int)
    return df


@st.cache_data(ttl=60)
def ler_pagamentos_verba():
    """Meses cuja verba já foi paga: {Timestamp(1º dia do mês): {consultor, gerente}}.

    Marketing não entra — a reserva nunca é paga a ninguém, então é sempre saldo.
    Mês ausente do dicionário = nada pago naquele mês.
    """
    eng = get_engine()
    try:
        with eng.connect() as conn:
            rows = conn.execute(text(
                "SELECT mes, consultor_pago, gerente_pago FROM verbas_pagamentos"
            )).mappings().all()
    except Exception:
        return {}
    return {pd.Timestamp(r["mes"]): {"consultor": bool(r["consultor_pago"]),
                                     "gerente": bool(r["gerente_pago"])}
            for r in rows}


@st.cache_data(ttl=60)
def ler_pagamentos_marketing():
    """Verba de marketing paga por mês: {Timestamp(1º dia do mês): valor}.

    Consultor e gerente são pagos por mês inteiro (daí o SIM/NÃO de
    `verbas_pagamentos`); marketing é um caixa acumulado, gasto em pedaços — por
    isso aqui vem VALOR, da tabela `verbas_marketing_pagos`.

    Alimentada pela aba `VERBAS DE MARKETING` do Excel via `importar_verbas.py`.
    Mês ausente = nada pago naquele mês. Devolve {} se a tabela ainda não existir,
    para o app mostrar saldo cheio em vez de estourar erro de conexão.
    """
    eng = get_engine()
    try:
        with eng.connect() as conn:
            rows = conn.execute(text(
                "SELECT mes, valor FROM verbas_marketing_pagos"
            )).mappings().all()
    except Exception:
        return {}
    return {pd.Timestamp(r["mes"]): float(r["valor"]) for r in rows}


@st.cache_data(ttl=60)
def ler_historico_lancamentos():
    """Trilha de TODOS os lançamentos já gravados (a página "Histórico" lê daqui).

    Vem da view `vw_lancamentos_historico`, que numera o lançamento dentro do mês
    e calcula a diferença para o lançamento anterior — o que foi vendido naquele
    período. É a base das análises semanais, já que `lancamentos` só guarda o
    acumulado mais recente do mês.

    NÃO engole erro: se a leitura falhar, a exceção sobe e a página mostra o
    motivo junto com `diagnostico_historico()`. Engolir aqui era o que fazia a
    tela dizer só "verifique a conexão" sem dizer o quê.
    """
    eng = get_engine()
    with eng.connect() as conn:
        df = pd.read_sql(text("SELECT * FROM vw_lancamentos_historico"), conn)
    if df.empty:
        return df
    df["mes"] = pd.to_datetime(df["mes"])
    df["registrado_em"] = pd.to_datetime(df["registrado_em"])
    # DECIMAL/None chegam como object dependendo da versão do pandas e do driver.
    # `to_numeric` converte os dois e transforma o que não der em NaN; o
    # `astype(float)` que estava aqui quebrava conforme a versão do ambiente.
    for c in ("n_lancamento", "passagens", "refil_diant", "refil_tras",
              "aproveitamento", "total_geral", "passagens_periodo",
              "refil_diant_periodo", "refil_tras_periodo", "total_periodo"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def diagnostico_historico():
    """Onde o app está conectado e o que existe lá — a tela de erro do Histórico
    mostra isto. É o que separa "estou no banco errado" de "a migração não rodou
    neste banco" de "a view existe mas veio diferente do esperado"."""
    info = {}
    try:
        eng = get_engine()
    except Exception as e:
        return {"conexão": f"ERRO: {type(e).__name__}: {e}"}
    u = eng.url
    info["servidor"] = f"{u.host}:{u.port}"
    info["banco"] = u.database
    info["usuário"] = u.username
    for rotulo, sql in (
        ("lancamentos", "SELECT COUNT(*) FROM lancamentos"),
        ("lancamentos_historico", "SELECT COUNT(*) FROM lancamentos_historico"),
        ("vw_lancamentos_historico", "SELECT COUNT(*) FROM vw_lancamentos_historico"),
    ):
        try:
            with eng.connect() as conn:
                info[rotulo] = conn.execute(text(sql)).scalar()
        except Exception as e:
            info[rotulo] = f"ERRO: {type(e).__name__}: {str(e)[:200]}"
    try:
        with eng.connect() as conn:
            cols = pd.read_sql(text("SELECT * FROM vw_lancamentos_historico LIMIT 0"), conn)
        info["colunas da view"] = ", ".join(cols.columns)
    except Exception as e:
        info["colunas da view"] = f"ERRO: {type(e).__name__}: {str(e)[:200]}"
    info["pandas"] = pd.__version__
    return info


def obter_lancamento(consultor_id, mes, unidade_id):
    """Valores já lançados para (consultor, mês, unidade), ou None se ainda não
    existir. A unidade faz parte da chave: um mesmo consultor pode ter, no mesmo
    mês, lançamentos em unidades diferentes (transferência no meio do mês)."""
    eng = get_engine()
    with eng.connect() as conn:
        row = conn.execute(text(
            "SELECT passagens, refil_diant, refil_tras "
            "FROM lancamentos "
            "WHERE consultor_id = :cid AND mes = :mes AND unidade_id = :uid"
        ), {"cid": consultor_id, "mes": mes, "uid": unidade_id}).mappings().first()
    return dict(row) if row else None


# ------------------------------- Gravação -------------------------------
# Toda gravação faz DUAS coisas na MESMA transação: mexe em `lancamentos` (o
# estado atual, que o dashboard lê) e acrescenta um evento em
# `lancamentos_historico` (a trilha, que nunca é sobrescrita). O histórico usa
# INSERT ... SELECT para pegar nome do consultor, nome da unidade e marca no
# próprio SQL — assim a exportação continua legível mesmo se o cadastro mudar
# depois, e estas funções não precisam receber parâmetro novo.
_SQL_EVENTO_HISTORICO = """
    INSERT INTO lancamentos_historico
        (consultor_id, unidade_id, mes, tipo, passagens, refil_diant, refil_tras,
         consultor_nome, unidade_nome, marca, origem)
    SELECT :cid, :uid, :mes, :tipo, :passagens, :rd, :rt,
           c.nome, u.nome_exibicao, u.marca, 'app'
    FROM consultores c
    JOIN unidades u ON u.id = :uid
    WHERE c.id = :cid
"""


def salvar_lancamento(consultor_id, mes, unidade_id, passagens, refil_diant, refil_tras):
    """Insere ou ATUALIZA (upsert) o lançamento de um consultor num mês/unidade.
    A chave é (consultor_id, mes, unidade_id): o mesmo consultor pode ter linhas
    em unidades diferentes no mesmo mês. Após gravar, limpa o cache de leitura
    para o dashboard refletir na hora.

    O upsert sobrescreve o valor anterior de propósito — o mês vale o acumulado
    mais recente. O que não pode se perder é o RASTRO, então o mesmo save
    acrescenta um evento em `lancamentos_historico`. Todo clique em "Salvar" vira
    um evento, mesmo sem mudança de valor: uma semana sem venda é informação."""
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("""
            INSERT INTO lancamentos
                (consultor_id, mes, unidade_id, passagens, refil_diant, refil_tras)
            VALUES (:cid, :mes, :uid, :passagens, :rd, :rt)
            ON DUPLICATE KEY UPDATE
                passagens   = VALUES(passagens),
                refil_diant = VALUES(refil_diant),
                refil_tras  = VALUES(refil_tras)
        """), {"cid": consultor_id, "mes": mes, "uid": unidade_id,
               "passagens": passagens, "rd": refil_diant, "rt": refil_tras})
        conn.execute(text(_SQL_EVENTO_HISTORICO),
                     {"cid": consultor_id, "mes": mes, "uid": unidade_id,
                      "tipo": "lancamento", "passagens": passagens,
                      "rd": refil_diant, "rt": refil_tras})
    ler_base_tidy.clear()  # invalida o cache para o dashboard atualizar na hora
    ler_historico_lancamentos.clear()


def excluir_lancamento(consultor_id, mes, unidade_id):
    """Remove o lançamento de um consultor num mês/unidade (inserido por engano).
    Após excluir, limpa o cache de leitura para o dashboard refletir na hora.

    A exclusão também vira evento no histórico, com zeros: o estado do mês depois
    dela é zero, então a diferença registrada é negativa e "devolve" o acumulado.
    Assim o próximo lançamento do mês volta a contar do zero e a soma das
    diferenças continua batendo com o acumulado."""
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text(
            "DELETE FROM lancamentos "
            "WHERE consultor_id = :cid AND mes = :mes AND unidade_id = :uid"
        ), {"cid": consultor_id, "mes": mes, "uid": unidade_id})
        conn.execute(text(_SQL_EVENTO_HISTORICO),
                     {"cid": consultor_id, "mes": mes, "uid": unidade_id,
                      "tipo": "exclusao", "passagens": 0, "rd": 0, "rt": 0})
    ler_base_tidy.clear()
    ler_historico_lancamentos.clear()


# -------------------- Teste de conexão standalone --------------------
# Permite verificar a Fase 3 com `python db.py`, sem precisar do app.
if __name__ == "__main__":
    import tomllib
    with open(".streamlit/secrets.toml", "rb") as f:
        cfg = tomllib.load(f)["mysql"]
    eng = create_engine(_build_url(cfg), pool_pre_ping=True)
    print("--- Teste de conexão (db.py) ---")
    with eng.connect() as conn:
        for t in ("precos_marca", "unidades", "consultores", "lancamentos",
                  "lancamentos_historico"):
            try:
                n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            except Exception:
                # Só o histórico pode faltar: é opcional até a migração rodar.
                # O rollback devolve a conexão ao estado usável para o próximo SELECT.
                conn.rollback()
                n = "ausente (rode aplicar_migracao_historico.py)"
            print(f"  {t:21}: {n}")
        s = conn.execute(text("SELECT ROUND(SUM(total_geral), 2) FROM vw_base_tidy")).scalar()
        print(f"  faturamento (view): {s}")
    print("Conexão e leitura OK.")
