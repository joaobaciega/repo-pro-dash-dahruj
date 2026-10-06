# Dashboard Dahruj — Ranking Refis para Palhetas (MVP)

App em Streamlit + MySQL:
- **Dashboard**: acompanhamento trimestral móvel (últimos 3 meses) por consultor,
  unidade e marca, lendo direto do banco.
- **💰 Verbas**: verba gerada, verba já paga e **saldo** (consultor / gerente /
  marketing), com conciliação de Sell In, Sell Out e estoque — ver "Aba Verbas".
- **Relatório Por Gerente** e **Relatório Por Consultor**: rankings do mês.
- **Lançamento** (acesso restrito): o gestor informa Passagens e Refis por consultor;
  o faturamento é calculado automaticamente e gravado no banco. Ao salvar, o
  dashboard atualiza.
- **🗂️ Histórico** (acesso restrito, mesmo cadeado): a trilha de **todos** os
  lançamentos já gravados, inclusive os que foram sobrescritos, com o número do
  lançamento dentro do mês, a diferença para o anterior (a venda da semana) e
  exportação em Excel. Ver "Histórico de lançamentos".

## Arquivos

| Arquivo          | Função                                                        |
|------------------|---------------------------------------------------------------|
| `schema.sql`     | Cria o banco `dashboard_dahruj`, as tabelas e a view.         |
| `seed.py`        | Carga inicial dos dados a partir do Excel (formato tidy).     |
| `importar_verbas.py` | Carga semanal da aba Verbas a partir da planilha de vendas. |
| `verbas.py` | Cálculo de provisão, Sell Out, estoque e pagamentos mensais. |
| `verbas_pagina.py` | Tela de Verbas e exportação Excel da conciliação. |
| `test_verbas.py` | Testes da metodologia e da exportação (`python -m unittest test_verbas`). |
| `conferir_verbas.py` | Conferência somente leitura e geração de relatório Excel a partir do SQL. |
| `db.py`          | Camada de dados: conexão e funções de leitura/gravação.       |
| `app.py`         | App integrado (Dashboard + Verbas + Relatórios + Lançamento). |
| `aplicar_migracao_historico.py` | Cria a tabela/view do histórico nos bancos.    |
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
Abre em `http://localhost:8501`. O menu lateral alterna entre **Dashboard** e os
dois relatórios.

## Acesso ao Lançamento

A aba **Lançamento** não aparece no menu. Para abrir, clique no **cadeado 🔒** no
fim da barra lateral e informe a senha; a aba passa a aparecer no menu.

- A senha está em `SENHA_LANCAMENTO`, no topo do `app.py`. Para não deixá-la no
  repositório, basta acrescentar ao `.streamlit/secrets.toml` (que é gitignored) —
  o valor do secrets tem prioridade sobre a constante:
  ```toml
  [acesso]
  senha_lancamento = "outra-senha"
  ```
- Volta a trancar: clicando no 🔓, após **30 min sem uso** ou ao recarregar a
  página (F5 abre uma sessão nova). Cada aba do navegador é uma sessão à parte.
- Após 3 senhas erradas, aguarda 1 minuto antes de aceitar nova tentativa.

## Como funciona

- A view `vw_base_tidy` recalcula aproveitamento e faturamento (quantidade ×
  preço da marca) a partir da tabela `lancamentos`. O dashboard lê dessa view.
- Salvar um lançamento faz *upsert* (chave consultor + mês + unidade): uma linha
  por consultor/mês/unidade, sem duplicar. Após salvar, o cache é limpo e o
  dashboard reflete a mudança.
- O mesmo save acrescenta um registro em `lancamentos_historico` — o upsert
  continua sobrescrevendo o mês, mas o valor anterior não se perde mais. Ver
  "Histórico de lançamentos".
- A janela de 3 meses é automática: quando entra um mês novo, o mais antigo sai.

## Histórico de lançamentos

O dashboard mostra, de cada mês, o **acumulado mais recente** — é o certo, mas
apagava o rastro: depois do 2º lançamento não dava para saber quanto tinha sido
vendido em cada semana. A tabela `lancamentos_historico` resolve isso sem mudar
nada no dashboard.

- É **append-only**: cada "Salvar lançamento" e cada exclusão vira uma linha,
  nunca atualizada e nunca apagada pelo app. Guarda o estado do mês *depois* do
  evento (na exclusão, zeros) e um snapshot do nome do consultor, da unidade e da
  marca, para a exportação continuar legível se o cadastro mudar depois.
- A view `vw_lancamentos_historico` calcula na leitura o **nº do lançamento no
  mês** (por consultor e unidade) e as colunas *no período* — a diferença para o
  lançamento anterior, ou seja, a venda daquela semana. A soma das diferenças de
  um mês sempre bate com o acumulado que o dashboard mostra.
- A página **🗂️ Histórico** filtra por mês/unidade/consultor e exporta um Excel
  com duas abas: `Histórico` (evento a evento) e `Semanal` (consultor × nº do
  lançamento, com o faturamento de cada período).

### Instalação (uma vez, em cada banco)

```
python aplicar_migracao_historico.py                  # local + online
python aplicar_migracao_historico.py --destino online # só o online
python aplicar_migracao_historico.py --conferir       # não grava, só confere
```

O script roda `alteracoes no sql/add_historico_lancamentos.sql`, que cria a
tabela e a view e copia os lançamentos que já existem como o nº 1 de cada mês.
É idempotente: rodar de novo não duplica nada. Existe como script (em vez de
colar o SQL no console) porque no Aiven o autocommit vem desligado e a alteração
feita na mão fica pendente — aqui o COMMIT é explícito.

> **Cargas em massa não alimentam o histórico.** `seed.py` e `carregar_base.py`
> escrevem direto em `lancamentos`, sem passar pelo `db.py`. Só a tela de
> Lançamento gera eventos — que é o fluxo do dia a dia. Se um dia a carga em
> massa virar rotina, ela precisa gravar o evento também.

## Aba Verbas

A aba cruza `vendas_verbas` (Sell In importado da planilha) com `vw_base_tidy`
(Sell Out lançado por consultor no mesmo banco das outras abas). O importador
continua gravando o Sell In integral; a conciliação é recalculada ao ler as bases.

- **Provisão:** verba gerada pelas compras das concessionárias (Sell In).
- **Devido a consultor/gerente:** quantidade do Sell Out do mês × tarifa por tipo
  da planilha (dianteiro em pares, traseiro em unidades).
- **Pago:** valor devido do Sell Out, apenas se a categoria/mês está marcada em
  `verbas_pagamentos`. Comprar em janeiro e vender em fevereiro gera verba
  devida em fevereiro. Uma marcação de janeiro sem Sell Out paga zero.
- **Estoque:** Sell In acumulado − Sell Out acumulado, com estoque inicial zero
  no início das bases. A verba em estoque usa as respectivas tarifas.
- **Saldo acumulado:** provisão − pagamentos, incluindo anos anteriores ao
  filtro. Para consultor/gerente, separa estoque de Sell Out ainda não pago.
- **Marketing:** mantém a reserva no Sell In e desconta os pagamentos reais de
  `verbas_marketing_pagos`. A parcela vinculada ao estoque é informativa e já
  integra essa reserva; não somá-la novamente ao saldo.

As tarifas são lidas do Sell In, sem valores fixos no código. Como o Sell Out
não identifica SKU, tarifas diferentes para o mesmo tipo no histórico impedem
o cálculo e pedem revisão da regra, em vez de aplicar uma média arbitrária.
Saldos físicos negativos são exibidos para conferência de estoque inicial,
transferências ou entradas faltantes; não se reduzem vendas reais para escondê-los.
Nissan Ceasa e Braz Leme aparecem separadamente. O Excel de referência de 29/09
somava ambas na linha Nissan Ceasa.

A tabela e o Excel somam os movimentos do ano, mas usam a última posição para
estoques, pendências e saldos acumulados. O filtro de mês não reinicia estoque.
Os dados acompanham as atualizações das duas bases com o cache existente de 60s.
Falhas ao ler pagamentos interrompem a tela, para não exibir saldo inflado.

Publique `app.py`, `db.py`, `verbas.py` e `verbas_pagina.py` juntos. Esta correção
não exige migração nem regravação dos dados de Sell In/Sell Out no SQL.

Para conferir com o Aiven sem alterar o banco:

```
python conferir_verbas.py --destino online --saida conferencia_verbas.xlsx
```

Na conferência de 06/10/2026, o Sell Out local ia somente até julho, enquanto
o Aiven ia até setembro. Os resultados da conferência usam o destino online.
O dashboard continua usando a conexão `[mysql]` configurada em cada ambiente.

### Instalação (uma vez, em cada banco)

```
mysql -u root -p dashboard_dahruj < "alteracoes no sql/add_verbas.sql"
mysql -u root -p dashboard_dahruj < "alteracoes no sql/verbas_pagamentos_inicial.sql"
mysql -u root -p dashboard_dahruj < "alteracoes no sql/add_verbas_marketing_pagos.sql"
```

O segundo grava o estado inicial dos pagamentos (Fev–Jul/2026 pagos). Depois
disso quem manda é a planilha. O terceiro cria a tabela dos pagamentos de
marketing (nasce vazia).

### Rotina semanal (sexta-feira)

1. Atualize a planilha: novas vendas entram no topo da aba `Total`; as fórmulas
   recalculam as três verbas sozinhas.
2. Rode:
   ```
   python importar_verbas.py
   ```
3. Confira o relatório impresso — ele compara o que foi gravado no banco com o
   que estava no Excel (linhas, faturamento e as três verbas). Tudo `OK` = pronto.

O script **apaga e regrava** `vendas_verbas` inteira dentro de uma transação: a
planilha é a fonte da verdade, então rodar duas vezes dá o mesmo resultado. O
dashboard reflete a mudança em até 60s (TTL do cache de leitura).

### Fechar o pagamento de um mês

Na aba **`Pagamentos`** da planilha (colunas `Mês` · `Consultor Pago` ·
`Gerente Pago`), marque `Sim` no mês que foi pago e rode `importar_verbas.py`.
A verba do **Sell Out daquele mês** sai do saldo. A verba dos itens ainda em
estoque permanece provisionada. Os valores pagos são calculados com essas
marcações, não lidos de comprovantes bancários; retificar o Sell Out de um mês
marcado como pago também recalcula seu valor.

- Marketing não entra nessa aba: ele tem a sua própria (veja abaixo), porque o
  que se paga é um **valor**, não um mês inteiro.
- Um mês sem Sell Out não baixa verba de consultor/gerente, mesmo marcado como
  pago. Não há transferência automática dessas categorias para marketing.
- Se a aba `Pagamentos` não existir, o script preserva o que já está no banco e
  avisa — nunca zera em silêncio.

### Lançar um pagamento de verba de MARKETING

A reserva de marketing não é paga a ninguém: ela se acumula e é gasta em pedaços,
em eventos. Por isso não tem "Sim/Não" — tem valor e mês.

Na aba **`VERBAS DE MARKETING`** da planilha (cabeçalho na linha 1):

| Mês do pgto | valor |
|-------------|-------|
| 01/09/2026  | 5000  |
| 01/09/2026  | 1200  |
| out/26      | 3000  |

Rode `python importar_verbas.py` e pronto: cada valor é descontado do saldo de
marketing **no mês do pagamento**, aparece no card "Verba já paga → Marketing" e
nas colunas `Marketing Pago` e `Saldo Marketing` da tabela mês a mês.

- **O nome da aba é tolerante**: `VERBA DE MARKETING`, `VERBAS DE MARKETING` ou
  qualquer variação de caixa/acento serve — o script pega a aba que tiver
  "marketing" no nome (e reclama se houver mais de uma).
- **Vários pagamentos no mesmo mês**: repita o mês em linhas diferentes; o
  importador soma (no exemplo acima, set/2026 fica com R$ 6.200,00).
- **O mês aceita** data (`01/09/2026`), `09/2026` ou `set/26`. **O valor aceita**
  `5000`, `5.000,00` ou `R$ 5.000,00`. Uma linha que não der para ler **para a
  importação inteira** e aponta a linha — pagamento perdido em silêncio inflaria
  o saldo.
- **Saldo negativo no mês não é erro**: o gasto sai do caixa acumulado, então um
  evento caro pode consumir o que sobrou dos meses anteriores.
- **Apagou a linha da planilha?** O pagamento some do banco na próxima rodada e o
  saldo volta a subir — a planilha é a fonte da verdade.
- Se a aba não existir, o script preserva o que está no banco e avisa.

### Atualizar também o banco online

Acrescente uma seção `[mysql_online]` ao `.streamlit/secrets.toml` local (o
arquivo é gitignored) com as credenciais do Streamlit Cloud. Sem `--destino`, o
script grava em todos os bancos configurados numa rodada só:

```
python importar_verbas.py                     # local + online
python importar_verbas.py --destino online    # só o online
```

## Trocar dados dummy pelos oficiais

Para começar limpo com os dados reais: rode `schema.sql` de novo (zera as
tabelas) e depois `python seed.py` apontando para o Excel oficial. O app não
precisa de nenhuma alteração.
