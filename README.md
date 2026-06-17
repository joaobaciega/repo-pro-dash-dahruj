# Dashboard Dahruj — Ranking Refis para Palhetas (MVP)

App em Streamlit + MySQL com duas telas:
- **Dashboard**: acompanhamento trimestral móvel (últimos 3 meses) por consultor,
  unidade e marca, lendo direto do banco.
- **Lançamento**: o gestor informa Passagens e Refis por consultor; o faturamento
  é calculado automaticamente e gravado no banco. Ao salvar, o dashboard atualiza.

## Arquivos

| Arquivo          | Função                                                        |
|------------------|---------------------------------------------------------------|
| `schema.sql`     | Cria o banco `dashboard_dahruj`, as tabelas e a view.         |
| `seed.py`        | Carga inicial dos dados a partir do Excel (formato tidy).     |
| `db.py`          | Camada de dados: conexão e funções de leitura/gravação.       |
| `app.py`         | App integrado (Dashboard + Lançamento).                       |
| `requirements.txt`| Dependências Python.                                          |
| `.streamlit/secrets.toml` | Credenciais do MySQL (criar manualmente).            |

## Instalação (uma vez)

1. **MySQL 8.0+** instalado e rodando. Aplique o esquema:
   ```
   mysql -u root -p < schema.sql
   ```
2. **Dependências**:
   ```
   pip install -r requirements.txt
   ```
3. **Conexão**: crie `.streamlit/secrets.toml` na pasta do projeto:
   ```toml
   [mysql]
   host = "127.0.0.1"
   port = 3306
   user = "root"
   password = "suasenha"
   database = "dashboard_dahruj"
   ```
4. **Carga inicial** (com o Excel tidy na pasta):
   ```
   python seed.py
   ```

## Rodar o app

```
streamlit run app.py
```
Abre em `http://localhost:8501`. Use o menu lateral para alternar entre
**Dashboard** e **Lançamento**.

## Como funciona

- A view `vw_base_tidy` recalcula aproveitamento e faturamento (quantidade ×
  preço da marca) a partir da tabela `lancamentos`. O dashboard lê dessa view.
- Salvar um lançamento faz *upsert* (chave consultor + mês): uma linha por
  consultor por mês, sem duplicar. Após salvar, o cache é limpo e o dashboard
  reflete a mudança.
- A janela de 3 meses é automática: quando entra um mês novo, o mais antigo sai.

## Trocar dados dummy pelos oficiais

Para começar limpo com os dados reais: rode `schema.sql` de novo (zera as
tabelas) e depois `python seed.py` apontando para o Excel oficial. O app não
precisa de nenhuma alteração.
