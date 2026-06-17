"""
Fase 2 — Carga inicial (seed) do banco `dashboard_dahruj`.

Lê a aba tidy do Excel atual e popula precos_marca, unidades, consultores e
lancamentos. É re-executável (usa UPSERT), então rodar de novo não duplica nada.
Ao final, imprime um relatório de validação comparando o faturamento somado pela
view com o do Excel.

Pré-requisito: rodar antes o schema.sql (cria banco, tabelas e view).

Uso:
    pip install -r requirements.txt
    # configure a conexão por variáveis de ambiente (ou edite os defaults abaixo)
    export DB_USER=root DB_PASSWORD=suasenha DB_HOST=127.0.0.1 DB_PORT=3306
    python seed.py [caminho_do_excel.xlsx]

Se o caminho do Excel não for passado, usa "Ranking_Dahruj_Trimestre_2026.xlsx"
na pasta atual.
"""

import calendar
import datetime as dt
import os
import sys
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

# ---------------------------------------------------------------------------
# Configuração de conexão (sobrescreva via variáveis de ambiente)
# ---------------------------------------------------------------------------
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "0211")
DB_NAME = os.getenv("DB_NAME", "dashboard_dahruj")

EXCEL_PATH = sys.argv[1] if len(sys.argv) > 1 else "C:/Users/Iasmin Baciega/OneDrive/Documents/DASH DAHRUJ/MySQL Dahurj/Ranking Dahruj Trimestre 2026.xlsx"

EXPECTED = {"Consultor", "Loja", "Marca", "Total Geral (R$)"}
RENAME = {
    "Mês (data)": "Mes",
    "Refil Diant. (qtd)": "RD",
    "Refil Tras. (qtd)": "RT",
    "Total Diant. (R$)": "TD",
    "Total Tras. (R$)": "TT",
    "Total Geral (R$)": "TG",
    "Preço Diant. (R$)": "PD",
    "Preço Tras. (R$)": "PT",
}

# Gerente responsável por cada unidade (marca, loja) — conforme o relatório
# semanal da diretoria. Confira/ajuste os nomes conforme necessário.
GERENTES = {
    ("Jeep",   "Ceasa"):          "Waldyr",
    ("Fiat",   "Ceasa"):          "Felipe",
    ("Nissan", "Ceasa"):          "Patrick",
    ("Honda",  "Ceasa"):          "Arnaldo",
    ("Jeep",   "Sumaré"):         "Izalto",
    ("Jeep",   "Guarulhos"):      "Aline",
    ("Jeep",   "W. Luiz"):        "Carlos",
    ("Nissan", "Braz Leme"):      "Diego",
    ("Fiat",   "Nações Unidadas"): "Adriano",
    ("Jeep",   "Vila Guilherme"): "Erasmo",
    ("Fiat",   "Osasco"):         "Arthur",
    ("Jeep",   "Aricanduva"):     "Larissa",
    ("Fiat",   "Aricanduva"):     "José Elias",
}


def segundas_do_mes(mes_ref):
    """Lista as segundas-feiras (datas) dentro do mês de `mes_ref` (date dia 1)."""
    y, m = mes_ref.year, mes_ref.month
    ndays = calendar.monthrange(y, m)[1]
    return [dt.date(y, m, d) for d in range(1, ndays + 1)
            if dt.date(y, m, d).weekday() == 0]


def dividir_inteiro(total, n):
    """Divide um inteiro em n partes o mais iguais possível (sobra nas primeiras)."""
    base, rem = divmod(int(total), n)
    return [base + (1 if i < rem else 0) for i in range(n)]


def carregar_tidy(path):
    """Localiza a aba tidy pelas colunas esperadas e normaliza os tipos."""
    if not os.path.exists(path):
        raise SystemExit(f"Arquivo não encontrado: {path}")
    xls = pd.ExcelFile(path)
    sheet = next(
        (s for s in xls.sheet_names
         if EXPECTED <= set(pd.read_excel(path, sheet_name=s, nrows=0).columns)),
        None,
    )
    if sheet is None:
        raise SystemExit("Aba no formato tidy não encontrada no Excel.")
    df = pd.read_excel(path, sheet_name=sheet).rename(columns=RENAME)
    df["Mes"] = pd.to_datetime(df["Mes"]).dt.date
    for c in ("Consultor", "Loja", "Marca"):
        df[c] = df[c].astype(str).str.strip()
    # refis em branco = 0 (reproduz os totais originais); passagens mantém NULL
    df["RD"] = pd.to_numeric(df["RD"], errors="coerce").fillna(0).astype(int)
    df["RT"] = pd.to_numeric(df["RT"], errors="coerce").fillna(0).astype(int)
    df["Passagens"] = pd.to_numeric(df["Passagens"], errors="coerce")
    df["PD"] = pd.to_numeric(df["PD"], errors="coerce")
    df["PT"] = pd.to_numeric(df["PT"], errors="coerce")
    return df


def seed(df, engine):
    with engine.begin() as conn:
        # 1) precos_marca -----------------------------------------------------
        precos = (df[["Marca", "PD", "PT"]].drop_duplicates("Marca")
                  .rename(columns={"Marca": "marca", "PD": "preco_diant", "PT": "preco_tras"}))
        conn.execute(text("""
            INSERT INTO precos_marca (marca, preco_diant, preco_tras)
            VALUES (:marca, :preco_diant, :preco_tras)
            ON DUPLICATE KEY UPDATE
              preco_diant = VALUES(preco_diant),
              preco_tras  = VALUES(preco_tras)
        """), precos.to_dict("records"))

        # 2) unidades ---------------------------------------------------------
        uni = df[["Marca", "Loja"]].drop_duplicates().copy()
        uni["nome_exibicao"] = uni["Marca"] + " " + uni["Loja"]
        uni["gerente"] = [GERENTES.get((m, l)) for m, l in zip(uni["Marca"], uni["Loja"])]
        conn.execute(text("""
            INSERT INTO unidades (marca, loja, nome_exibicao, gerente)
            VALUES (:Marca, :Loja, :nome_exibicao, :gerente)
            ON DUPLICATE KEY UPDATE
              nome_exibicao = VALUES(nome_exibicao),
              gerente       = VALUES(gerente)
        """), uni.to_dict("records"))

        uni_ids = {(r["marca"], r["loja"]): r["id"]
                   for r in conn.execute(text("SELECT id, marca, loja FROM unidades")).mappings()}

        # 3) consultores ------------------------------------------------------
        cons = df[["Consultor", "Marca", "Loja"]].drop_duplicates().copy()
        cons["unidade_id"] = [uni_ids[(m, l)] for m, l in zip(cons["Marca"], cons["Loja"])]
        conn.execute(text("""
            INSERT INTO consultores (nome, unidade_id)
            VALUES (:Consultor, :unidade_id)
            ON DUPLICATE KEY UPDATE nome = VALUES(nome)
        """), cons[["Consultor", "unidade_id"]].to_dict("records"))

        cons_ids = {(r["nome"], r["unidade_id"]): r["id"]
                    for r in conn.execute(text("SELECT id, nome, unidade_id FROM consultores")).mappings()}

        # 4) lancamentos (mensal -> semanal) ----------------------------------
        #    Cada linha mensal é distribuída pelas semanas (segundas) do mês.
        #    Os totais do mês ficam idênticos; ganha-se a granularidade semanal.
        recs = []
        for _, r in df.iterrows():
            uid = uni_ids[(r["Marca"], r["Loja"])]
            cid = cons_ids[(r["Consultor"], uid)]
            semanas = segundas_do_mes(r["Mes"])
            n = len(semanas)
            tem_pass = not pd.isna(r["Passagens"])
            pas = dividir_inteiro(r["Passagens"], n) if tem_pass else [None] * n
            rd = dividir_inteiro(r["RD"], n)
            rt = dividir_inteiro(r["RT"], n)
            for i, sem in enumerate(semanas):
                recs.append({
                    "consultor_id": cid, "semana": sem, "passagens": pas[i],
                    "refil_diant": rd[i], "refil_tras": rt[i],
                })
        conn.execute(text("""
            INSERT INTO lancamentos (consultor_id, semana, passagens, refil_diant, refil_tras)
            VALUES (:consultor_id, :semana, :passagens, :refil_diant, :refil_tras)
            ON DUPLICATE KEY UPDATE
              passagens   = VALUES(passagens),
              refil_diant = VALUES(refil_diant),
              refil_tras  = VALUES(refil_tras)
        """), recs)


def validar(df, engine):
    print("\n--- Validação ---")
    with engine.connect() as conn:
        counts = {t: conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                  for t in ("precos_marca", "unidades", "consultores", "lancamentos")}
        for t, n in counts.items():
            print(f"  {t:14}: {n}")
        view_sum = conn.execute(text("SELECT ROUND(SUM(total_geral), 2) FROM vw_base_tidy")).scalar()
    excel_sum = round(float((df["RD"] * df["PD"] + df["RT"] * df["PT"]).sum()), 2)
    ok = abs(float(view_sum) - excel_sum) < 0.01
    print(f"\n  Faturamento total — view: {view_sum} | Excel: {excel_sum} -> "
          f"{'OK' if ok else 'DIVERGÊNCIA!'}")
    print("--- Carga concluída ---" if ok else "--- ATENÇÃO: revise as divergências ---")


def main():
    df = carregar_tidy(EXCEL_PATH)
    url = URL.create("mysql+pymysql", username=DB_USER, password=DB_PASSWORD,
                     host=DB_HOST, port=DB_PORT, database=DB_NAME,
                     query={"charset": "utf8mb4"})
    engine = create_engine(url)
    try:
        seed(df, engine)
    except Exception as e:
        raise SystemExit(
            f"Erro ao gravar no banco: {e}\n"
            "Verifique se o schema.sql já foi aplicado e se as credenciais/host estão corretos."
        )
    validar(df, engine)


if __name__ == "__main__":
    main()