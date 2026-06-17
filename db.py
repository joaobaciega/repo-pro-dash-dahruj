"""
Fase 3 — Camada de dados (db.py)

Centraliza a conexão com o MySQL e as funções de leitura/gravação usadas pelo
app Streamlit. O app nunca escreve SQL direto: chama estas funções.

Configuração: arquivo .streamlit/secrets.toml (na mesma pasta), com:

    [mysql]
    host = "127.0.0.1"
    port = 3306
    user = "root"
    password = "suasenha"
    database = "dashboard_dahruj"

Para testar a conexão isoladamente, rode na pasta do projeto:
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
    df["semana"] = pd.to_datetime(df["semana"])
    return df


def obter_lancamento(consultor_id, semana):
    """Valores já lançados para (consultor, semana), ou None se não existir.
    Útil para pré-preencher o formulário e permitir edição."""
    eng = get_engine()
    with eng.connect() as conn:
        row = conn.execute(text(
            "SELECT passagens, refil_diant, refil_tras "
            "FROM lancamentos WHERE consultor_id = :cid AND semana = :semana"
        ), {"cid": consultor_id, "semana": semana}).mappings().first()
    return dict(row) if row else None


# ------------------------------- Gravação -------------------------------
def salvar_lancamento(consultor_id, semana, passagens, refil_diant, refil_tras):
    """Insere ou ATUALIZA (upsert) o lançamento de um consultor numa semana.
    Após gravar, limpa o cache de leitura para o dashboard refletir na hora."""
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("""
            INSERT INTO lancamentos
                (consultor_id, semana, passagens, refil_diant, refil_tras)
            VALUES (:cid, :semana, :passagens, :rd, :rt)
            ON DUPLICATE KEY UPDATE
                passagens   = VALUES(passagens),
                refil_diant = VALUES(refil_diant),
                refil_tras  = VALUES(refil_tras)
        """), {"cid": consultor_id, "semana": semana, "passagens": passagens,
               "rd": refil_diant, "rt": refil_tras})
    ler_base_tidy.clear()  # invalida o cache para o dashboard atualizar na hora


def excluir_lancamento(consultor_id, semana):
    """Remove o lançamento de um consultor numa semana (linha inserida por engano).
    Após excluir, limpa o cache de leitura para o dashboard refletir na hora."""
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text(
            "DELETE FROM lancamentos WHERE consultor_id = :cid AND semana = :semana"
        ), {"cid": consultor_id, "semana": semana})
    ler_base_tidy.clear()


# -------------------- Teste de conexão standalone --------------------
# Permite verificar a conexão com `python db.py`, sem precisar do app.
if __name__ == "__main__":
    import tomllib
    from pathlib import Path
    cfg_path = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
    if not cfg_path.exists():
        raise SystemExit(
            f"Não encontrei {cfg_path}.\n"
            "Crie a pasta .streamlit (na mesma pasta do db.py) com o secrets.toml."
        )
    with open(cfg_path, "rb") as f:
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