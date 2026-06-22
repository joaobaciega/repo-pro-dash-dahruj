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
    """Unidades para o filtro do app (id + nome de exibição)."""
    eng = get_engine()
    with eng.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, nome_exibicao, marca, loja "
            "FROM unidades ORDER BY nome_exibicao"
        )).mappings().all()
    return [dict(r) for r in rows]


@st.cache_data(ttl=60)
def listar_consultores(unidade_id):
    """Consultores de uma unidade (id + nome)."""
    eng = get_engine()
    with eng.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, nome FROM consultores "
            "WHERE unidade_id = :uid ORDER BY nome"
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


def obter_lancamento(consultor_id, mes):
    """Valores já lançados para (consultor, mês), ou None se ainda não existir.
    Útil para pré-preencher o formulário e permitir edição."""
    eng = get_engine()
    with eng.connect() as conn:
        row = conn.execute(text(
            "SELECT passagens, refil_diant, refil_tras "
            "FROM lancamentos WHERE consultor_id = :cid AND mes = :mes"
        ), {"cid": consultor_id, "mes": mes}).mappings().first()
    return dict(row) if row else None


# ------------------------------- Gravação -------------------------------
def salvar_lancamento(consultor_id, mes, passagens, refil_diant, refil_tras):
    """Insere ou ATUALIZA (upsert) o lançamento de um consultor num mês.
    Após gravar, limpa o cache de leitura para o dashboard refletir na hora."""
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("""
            INSERT INTO lancamentos
                (consultor_id, mes, passagens, refil_diant, refil_tras)
            VALUES (:cid, :mes, :passagens, :rd, :rt)
            ON DUPLICATE KEY UPDATE
                passagens   = VALUES(passagens),
                refil_diant = VALUES(refil_diant),
                refil_tras  = VALUES(refil_tras)
        """), {"cid": consultor_id, "mes": mes, "passagens": passagens,
               "rd": refil_diant, "rt": refil_tras})
    ler_base_tidy.clear()  # invalida o cache para o dashboard atualizar na hora


# -------------------- Teste de conexão standalone --------------------
# Permite verificar a Fase 3 com `python db.py`, sem precisar do app.
if __name__ == "__main__":
    import tomllib
    with open(".streamlit/secrets.toml", "rb") as f:
        cfg = tomllib.load(f)["mysql"]
    eng = create_engine(_build_url(cfg), pool_pre_ping=True)
    print("--- Teste de conexão (db.py) ---")
    with eng.connect() as conn:
        for t in ("precos_marca", "unidades", "consultores", "lancamentos"):
            n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"  {t:14}: {n}")
        s = conn.execute(text("SELECT ROUND(SUM(total_geral), 2) FROM vw_base_tidy")).scalar()
        print(f"  faturamento (view): {s}")
    print("Conexão e leitura OK.")
