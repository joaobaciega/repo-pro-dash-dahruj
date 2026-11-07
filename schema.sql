-- =============================================================================
--  Projeto: Dashboard Dahruj — Ranking Refis para Palhetas
--  Fase 1 — Esquema do banco (MySQL 8.0+)
--
--  Como aplicar (via cliente mysql ou MySQL Workbench):
--      mysql -u root -p < schema.sql
--
--  Cria o banco `dashboard_dahruj`, as 4 tabelas e a view `vw_base_tidy`,
--  que entrega os dados já no formato consumido pelo dashboard.
-- =============================================================================

CREATE DATABASE IF NOT EXISTS dashboard_dahruj
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE dashboard_dahruj;

-- A ordem de criação respeita as chaves estrangeiras.
-- (DROPs na ordem inversa para permitir recriação limpa do esquema.)
--
-- `vendas_verbas`, `verbas_pagamentos` e `verbas_marketing_pagos` (fim do
-- arquivo) NÃO entram nos DROPs de propósito: são criadas com IF NOT EXISTS e
-- sobrevivem a uma recriação do esquema. Rodar este arquivo zera os lançamentos sem derrubar a base de verbas
-- — que, de qualquer forma, se recompõe com `python importar_verbas.py`.
DROP VIEW  IF EXISTS vw_base_tidy;
DROP TABLE IF EXISTS lancamentos;
DROP TABLE IF EXISTS consultor_unidade;
DROP TABLE IF EXISTS consultores;
DROP TABLE IF EXISTS unidades;
DROP TABLE IF EXISTS precos_marca;

-- -----------------------------------------------------------------------------
-- 1) precos_marca
--    Preço unitário do refil por marca. Usado para CALCULAR o faturamento
--    (o gerente nunca digita valores em R$, só quantidades).
-- -----------------------------------------------------------------------------
CREATE TABLE precos_marca (
  marca        VARCHAR(50)   NOT NULL,
  preco_diant  DECIMAL(10,2) NOT NULL,
  preco_tras   DECIMAL(10,2) NOT NULL,
  PRIMARY KEY (marca)
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 2) unidades
--    Uma concessionária = combinação de marca + loja (ex.: "Jeep" + "Guarulhos").
--    nome_exibicao é o rótulo amigável usado no filtro do app (ex.: "Jeep Guarulhos").
-- -----------------------------------------------------------------------------
CREATE TABLE unidades (
  id             INT          NOT NULL AUTO_INCREMENT,
  marca          VARCHAR(50)  NOT NULL,
  loja           VARCHAR(80)  NOT NULL,
  nome_exibicao  VARCHAR(120) NOT NULL,
  gerente        VARCHAR(120) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_unidade (marca, loja),
  CONSTRAINT fk_unidade_marca
    FOREIGN KEY (marca) REFERENCES precos_marca (marca)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 3) consultores
--    A PESSOA (identidade estável). NÃO guarda mais a unidade: um consultor pode
--    ser transferido entre unidades ao longo do tempo (ver `consultor_unidade`).
--    Mantendo um único `id` por consultor, todos os lançamentos históricos
--    continuam ligados a ele — nada é perdido numa transferência.
-- -----------------------------------------------------------------------------
CREATE TABLE consultores (
  id    INT          NOT NULL AUTO_INCREMENT,
  nome  VARCHAR(120) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_consultor (nome)
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 3b) consultor_unidade  (VÍNCULO COM VIGÊNCIA / histórico de lotação)
--    Diz em QUE unidade cada consultor esteve em CADA período. É isto que
--    permite transferir alguém "a partir de tal mês" sem reescrever o passado:
--    a unidade passa a depender do MÊS do lançamento, não do consultor.
--
--    vigencia_inicio  = primeiro mês (inclusive) na unidade  (use o 1º dia do mês)
--    vigencia_fim     = último  mês (inclusive) na unidade; NULL = vínculo vigente
--
--    Regras de uso:
--      * Os períodos de um mesmo consultor NÃO devem se sobrepor.
--      * O vínculo mais antigo deve começar cedo o bastante para cobrir o
--        primeiro lançamento do consultor (senão a view "esconde" o lançamento).
--
--    OBS: desde que a unidade passou a ser gravada em CADA lançamento
--    (lancamentos.unidade_id), esta tabela NÃO é mais usada pela view. Ela serve
--    apenas para a tela de Lançamento saber quais consultores listar em cada
--    unidade (lotação vigente = vigencia_fim IS NULL). Por isso ela consegue
--    representar até transferência no MEIO de um mês: o mês do lançamento não
--    determina mais a unidade — o próprio lançamento é que a carrega.
--
--    Ex.: Rafael saiu da Nissan Braz Leme no meio de Junho/2026 e foi para a
--         Nissan Ceasa. Ele pode ter DOIS lançamentos em 06/2026 (um em cada
--         unidade). Para a tela, fecha-se a Braz Leme e abre-se a Ceasa:
--      (Rafael, Braz Leme, '2024-01-01', '2026-05-01')
--      (Rafael, Ceasa,     '2026-06-01',  NULL)
-- -----------------------------------------------------------------------------
CREATE TABLE consultor_unidade (
  id               INT  NOT NULL AUTO_INCREMENT,
  consultor_id     INT  NOT NULL,
  unidade_id       INT  NOT NULL,
  vigencia_inicio  DATE NOT NULL,
  vigencia_fim     DATE NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_cu (consultor_id, unidade_id, vigencia_inicio),
  KEY idx_cu_consultor (consultor_id),
  KEY idx_cu_unidade   (unidade_id),
  CONSTRAINT fk_cu_consultor
    FOREIGN KEY (consultor_id) REFERENCES consultores (id)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_cu_unidade
    FOREIGN KEY (unidade_id) REFERENCES unidades (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT chk_cu_vigencia CHECK (
    vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio
  )
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 4) lancamentos  (TABELA-FATO)
--    O que o gerente digita por consultor, por UNIDADE e por MÊS: Passagens,
--    Refil Dianteiro e Refil Traseiro. `mes` é sempre o 1º dia do mês.
--    A unidade é gravada AQUI (unidade_id): assim o mesmo consultor pode ter,
--    no MESMO mês, lançamentos em unidades diferentes (transferência no meio do
--    mês). É a view que lê a unidade daqui — não mais da vigência.
--    A chave única (consultor_id, mes, unidade_id) viabiliza o UPSERT: relançar
--    o mesmo consultor/mês/unidade ATUALIZA o registro em vez de duplicar.
-- -----------------------------------------------------------------------------
CREATE TABLE lancamentos (
  id           INT       NOT NULL AUTO_INCREMENT,
  consultor_id INT       NOT NULL,
  unidade_id   INT       NOT NULL,
  mes          DATE      NOT NULL,
  passagens    INT       NULL,
  refil_diant  INT       NOT NULL DEFAULT 0,
  refil_tras   INT       NOT NULL DEFAULT 0,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_lancamento (consultor_id, mes, unidade_id),
  KEY idx_lancamento_mes (mes),
  KEY idx_lancamento_unidade (unidade_id),
  CONSTRAINT fk_lancamento_consultor
    FOREIGN KEY (consultor_id) REFERENCES consultores (id)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_lancamento_unidade
    FOREIGN KEY (unidade_id) REFERENCES unidades (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT chk_lancamento_nao_negativo CHECK (
    (passagens IS NULL OR passagens >= 0)
    AND refil_diant >= 0
    AND refil_tras  >= 0
  )
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- VIEW vw_base_tidy
--    "Ponte" para o dashboard: junta as 4 tabelas e RECALCULA, na leitura,
--    o aproveitamento e o faturamento (quantidade × preço da marca).
--    Devolve exatamente o formato tidy que o dashboard consome.
--
--    - aproveitamento = refil_diant / passagens (NULL quando não há passagens)
--    - total_diant    = refil_diant × preco_diant
--    - total_tras     = refil_tras  × preco_tras
--    - total_geral    = total_diant + total_tras
-- -----------------------------------------------------------------------------
CREATE VIEW vw_base_tidy AS
SELECT
  c.id                                     AS consultor_id,
  c.nome                                   AS consultor,
  u.id                                     AS unidade_id,
  u.nome_exibicao                          AS unidade,
  u.loja                                   AS loja,
  u.marca                                  AS marca,
  u.gerente                                AS gerente,
  l.mes                                    AS mes,
  DATE_FORMAT(l.mes, '%m/%Y')              AS mes_label,
  l.passagens                              AS passagens,
  l.refil_diant                            AS refil_diant,
  l.refil_tras                             AS refil_tras,
  CASE WHEN l.passagens > 0
       THEN ROUND(l.refil_diant / l.passagens, 4)
       ELSE NULL
  END                                      AS aproveitamento,
  ROUND(l.refil_diant * p.preco_diant, 2)  AS total_diant,
  ROUND(l.refil_tras  * p.preco_tras,  2)  AS total_tras,
  ROUND(l.refil_diant * p.preco_diant
      + l.refil_tras  * p.preco_tras,  2)  AS total_geral
FROM lancamentos l
JOIN consultores       c  ON c.id  = l.consultor_id
-- A unidade vem do PRÓPRIO lançamento (l.unidade_id). Assim o mesmo consultor
-- pode ter, no mesmo mês, lançamentos em unidades diferentes — inclusive quando
-- a transferência ocorre no meio do mês (ex.: Rafael em 06/2026 na Braz Leme e
-- na Ceasa ao mesmo tempo).
JOIN unidades          u  ON u.id  = l.unidade_id
JOIN precos_marca      p  ON p.marca = u.marca;

-- =============================================================================
--  HISTÓRICO DE LANÇAMENTOS — a trilha por trás do upsert
--
--  `lancamentos` guarda o ESTADO do mês: o upsert sobrescreve o valor anterior,
--  e é isso mesmo que o dashboard precisa (o mês vale o acumulado mais recente).
--  O efeito colateral é que o rastro some: depois do 2º lançamento não dá para
--  saber quanto foi vendido em CADA semana.
--
--  As duas estruturas abaixo resolvem isso sem tocar em nada acima: cada save e
--  cada exclusão da tela de Lançamento acrescenta um evento, e a view calcula na
--  leitura o número do lançamento no mês e a diferença para o anterior.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 5) lancamentos_historico  (TABELA DE EVENTOS — append-only)
--
--    Uma linha por EVENTO, nunca atualizada e nunca apagada pelo app.
--
--    `passagens`/`refil_*` guardam o ESTADO APÓS o evento: no salvamento, os
--    valores gravados (o acumulado do mês); na exclusão, zeros — assim a
--    diferença do evento de exclusão é negativa e zera o acumulado, e o próximo
--    lançamento volta a contar do zero. As diferenças sempre somam o acumulado.
--
--    SEM FOREIGN KEY de propósito: a FK de `lancamentos` para `consultores` é
--    ON DELETE CASCADE, e o histórico não pode ser levado junto se um consultor
--    for removido do cadastro. Pelo mesmo motivo guardamos os NOMES por snapshot
--    (consultor_nome/unidade_nome/marca): a exportação continua legível mesmo
--    depois de renomeação, transferência ou exclusão de cadastro.
-- -----------------------------------------------------------------------------
CREATE TABLE lancamentos_historico (
  id             BIGINT    NOT NULL AUTO_INCREMENT,
  consultor_id   INT       NOT NULL,
  unidade_id     INT       NOT NULL,
  mes            DATE      NOT NULL,
  tipo           ENUM('lancamento','exclusao') NOT NULL DEFAULT 'lancamento',
  -- Estado APÓS o evento (na exclusão, zeros).
  passagens      INT       NULL,
  refil_diant    INT       NOT NULL DEFAULT 0,
  refil_tras     INT       NOT NULL DEFAULT 0,
  -- Snapshot do cadastro no momento do evento.
  consultor_nome VARCHAR(120) NULL,
  unidade_nome   VARCHAR(120) NULL,
  marca          VARCHAR(50)  NULL,
  -- 'app' = tela de Lançamento; 'backfill' = carga inicial da migração.
  origem         VARCHAR(20) NOT NULL DEFAULT 'app',
  registrado_em  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_hist_chave (consultor_id, unidade_id, mes, registrado_em),
  KEY idx_hist_mes (mes)
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- VIEW vw_lancamentos_historico
--    O que a página "Histórico" do app lê e exporta. Tudo é calculado na
--    leitura, então nada no banco fica desatualizado.
--
--    - n_lancamento      : número do lançamento DENTRO do mês, por consultor e
--                          unidade. Conta só os eventos 'lancamento' (a soma
--                          corrente de tipo='lancamento'), então "nº 3" é sempre
--                          o 3º lançamento de verdade. Um evento de exclusão
--                          repete o número do lançamento que ele cancelou — a
--                          coluna `tipo` desambigua.
--    - *_periodo         : diferença para o evento anterior = o que foi vendido
--                          NAQUELE período (a "semana"). LAG(..., 1, 0) faz o
--                          primeiro evento do mês valer ele mesmo por inteiro.
--    - total_geral       : faturamento acumulado no mês até aquele evento.
--    - total_periodo     : faturamento DAQUELE período — é a base da análise
--                          semanal. Mesma fórmula de preço da vw_base_tidy.
--
--    A cláusula OVER (...) é repetida inline em cada coluna, em vez de uma
--    WINDOW nomeada, por compatibilidade dentro de CREATE VIEW.
-- -----------------------------------------------------------------------------
CREATE VIEW vw_lancamentos_historico AS
SELECT
  h.id                                       AS evento_id,
  -- CAST porque SUM() devolve DECIMAL: sem ele o número do lançamento chega no
  -- Python como Decimal e quebra as comparações/pivots do relatório.
  CAST(SUM(h.tipo = 'lancamento') OVER (
    PARTITION BY h.consultor_id, h.unidade_id, h.mes
    ORDER BY h.registrado_em, h.id
    ROWS UNBOUNDED PRECEDING) AS SIGNED)     AS n_lancamento,
  h.tipo                                     AS tipo,
  h.registrado_em                            AS registrado_em,
  h.origem                                   AS origem,
  h.consultor_id                             AS consultor_id,
  h.consultor_nome                           AS consultor,
  h.unidade_id                               AS unidade_id,
  h.unidade_nome                             AS unidade,
  h.marca                                    AS marca,
  h.mes                                      AS mes,
  DATE_FORMAT(h.mes, '%m/%Y')                AS mes_label,

  -- Acumulado no mês até este evento (o que estava gravado em `lancamentos`).
  h.passagens                                AS passagens,
  h.refil_diant                              AS refil_diant,
  h.refil_tras                               AS refil_tras,
  CASE WHEN h.passagens > 0
       THEN ROUND(h.refil_diant / h.passagens, 4)
       ELSE NULL
  END                                        AS aproveitamento,
  ROUND(h.refil_diant * p.preco_diant
      + h.refil_tras  * p.preco_tras, 2)     AS total_geral,

  -- Diferença para o evento anterior = venda do período (a "semana").
  COALESCE(h.passagens, 0) - LAG(COALESCE(h.passagens, 0), 1, 0) OVER (
    PARTITION BY h.consultor_id, h.unidade_id, h.mes
    ORDER BY h.registrado_em, h.id)          AS passagens_periodo,
  h.refil_diant - LAG(h.refil_diant, 1, 0) OVER (
    PARTITION BY h.consultor_id, h.unidade_id, h.mes
    ORDER BY h.registrado_em, h.id)          AS refil_diant_periodo,
  h.refil_tras - LAG(h.refil_tras, 1, 0) OVER (
    PARTITION BY h.consultor_id, h.unidade_id, h.mes
    ORDER BY h.registrado_em, h.id)          AS refil_tras_periodo,
  ROUND(
    (h.refil_diant - LAG(h.refil_diant, 1, 0) OVER (
       PARTITION BY h.consultor_id, h.unidade_id, h.mes
       ORDER BY h.registrado_em, h.id)) * p.preco_diant
  + (h.refil_tras - LAG(h.refil_tras, 1, 0) OVER (
       PARTITION BY h.consultor_id, h.unidade_id, h.mes
       ORDER BY h.registrado_em, h.id)) * p.preco_tras
  , 2)                                       AS total_periodo
FROM lancamentos_historico h
-- LEFT JOIN: se a marca do snapshot sumir de precos_marca, a linha do histórico
-- continua aparecendo (sem faturamento) em vez de desaparecer do relatório.
LEFT JOIN precos_marca p ON p.marca = h.marca;

-- =============================================================================
--  ABA VERBAS — tabelas independentes
--
--  Estas duas tabelas atendem SÓ a aba "Verbas" do dashboard e vivem sobre uma
--  base diferente: a planilha "Base de dados para Dash Board.xlsx" (sell-in —
--  pedidos faturados para as concessionárias, linha a linha por produto), não os
--  lançamentos por consultor.
--
--  São ilhas de propósito: sem FK para as tabelas acima, sem trigger, fora da
--  view. Nada aqui altera um número sequer do Dashboard/Relatórios.
--
--  Quem escreve: `importar_verbas.py` (rodado toda sexta, depois de atualizar o
--  Excel). O mesmo DDL está isolado em `alteracoes no sql/add_verbas.sql`, para
--  aplicar num banco que já existe sem recriar o esquema inteiro.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 5) vendas_verbas  (TABELA-FATO da aba Verbas)
--    Uma linha por linha da aba `Total` do Excel: um produto dentro de um pedido.
--    O mesmo `pedido` se repete quando o cliente levou mais de um produto — por
--    isso a PK é sintética e a contagem de pedidos é COUNT(DISTINCT pedido).
--
--    Os pares verba/total já vêm calculados pelas fórmulas do Excel; guardamos
--    os dois para conferência, mas o dashboard soma sempre as colunas `total_*`.
--
--    tipo_refil: 'diant' (produto vendido em Par) ou 'tras' (Unitário), resolvido
--    pelo código do produto na aba auxiliar `Verbas` do Excel.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vendas_verbas (
  id               INT           NOT NULL AUTO_INCREMENT,
  data             DATE          NOT NULL,
  pedido           VARCHAR(30)   NOT NULL,
  cnpj             VARCHAR(24)   NULL,
  cliente          VARCHAR(180)  NULL,
  codigo           VARCHAR(24)   NULL,
  produto          VARCHAR(180)  NULL,
  tipo_refil       ENUM('diant', 'tras') NULL,
  preco_unit       DECIMAL(10,2) NULL,
  qtde             INT           NOT NULL DEFAULT 0,
  total_item       DECIMAL(12,2) NOT NULL DEFAULT 0,
  verba_consultor  DECIMAL(10,2) NOT NULL DEFAULT 0,
  total_consultor  DECIMAL(12,2) NOT NULL DEFAULT 0,
  verba_gerente    DECIMAL(10,2) NOT NULL DEFAULT 0,
  total_gerente    DECIMAL(12,2) NOT NULL DEFAULT 0,
  verba_reserva    DECIMAL(10,2) NOT NULL DEFAULT 0,
  total_reserva    DECIMAL(12,2) NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  KEY idx_vv_data   (data),
  KEY idx_vv_pedido (pedido)
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 6) verbas_pagamentos  (CONTROLE DE PAGAMENTO POR MÊS)
--    Para cada mês, se a verba de Consultor e a de Gerente já foram pagas. É o
--    que separa "verba gerada" de "saldo de verba" no dashboard.
--    `mes` é sempre o 1º dia do mês (mesma convenção de `lancamentos.mes`).
--
--    Marketing não tem coluna: a reserva de marketing nunca é paga a ninguém,
--    então entra inteira no saldo, em todo mês.
--
--    Janeiro/2026 fica 0/0 de propósito — não se pagou verba de consultor nem de
--    gerente daquelas vendas, tudo virou marketing; o mês inteiro é saldo.
--
--    Alimentada pela aba `Pagamentos` do Excel: para fechar o pagamento de um
--    mês, marque "Sim" lá e reimporte — sem tocar em SQL nem em código.
--
--    `valor_consultor` / `valor_gerente`: valor efetivamente pago (colunas
--    opcionais da aba). NULL = não informado, vale o devido pelo Sell Out do mês
--    marcado. DDL isolado em `alteracoes no sql/add_verbas_pagamentos_valor.sql`.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS verbas_pagamentos (
  mes              DATE          NOT NULL,
  consultor_pago   TINYINT(1)    NOT NULL DEFAULT 0,
  gerente_pago     TINYINT(1)    NOT NULL DEFAULT 0,
  valor_consultor  DECIMAL(12,2) NULL DEFAULT NULL,
  valor_gerente    DECIMAL(12,2) NULL DEFAULT NULL,
  PRIMARY KEY (mes)
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 7) verbas_marketing_pagos  (PAGAMENTOS DA VERBA DE MARKETING)
--    Consultor e gerente são pagos por mês inteiro, daí o SIM/NÃO da tabela 6.
--    Marketing não: a reserva se acumula e é gasta em pedaços, em eventos. O que
--    se guarda aqui é um VALOR por mês de pagamento, que o dashboard desconta do
--    saldo de marketing daquele mês.
--
--    O valor pago pode passar a verba gerada no mês — a reserva é um caixa
--    acumulado, então um evento caro consome o que sobrou dos meses anteriores.
--    O saldo do mês fica negativo na tabela mês a mês e o do ano segue correto.
--
--    Alimentada pela aba `VERBAS DE MARKETING` do Excel (`Mês do pgto` · `valor`).
--    Vários pagamentos no mesmo mês: repita o mês em linhas diferentes, o
--    importador soma antes de gravar. DDL isolado em
--    `alteracoes no sql/add_verbas_marketing_pagos.sql`.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS verbas_marketing_pagos (
  mes    DATE          NOT NULL,
  valor  DECIMAL(12,2) NOT NULL DEFAULT 0,
  PRIMARY KEY (mes)
) ENGINE=InnoDB;

