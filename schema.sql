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
DROP VIEW  IF EXISTS vw_base_tidy;
DROP TABLE IF EXISTS lancamentos;
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
--    Cada consultor pertence a uma unidade.
-- -----------------------------------------------------------------------------
CREATE TABLE consultores (
  id          INT          NOT NULL AUTO_INCREMENT,
  nome        VARCHAR(120) NOT NULL,
  unidade_id  INT          NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_consultor (nome, unidade_id),
  KEY idx_consultor_unidade (unidade_id),
  CONSTRAINT fk_consultor_unidade
    FOREIGN KEY (unidade_id) REFERENCES unidades (id)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 4) lancamentos  (TABELA-FATO)
--    O que o gerente digita por consultor e por SEMANA: Passagens, Refil
--    Dianteiro e Refil Traseiro. `semana` é sempre a SEGUNDA-FEIRA da semana
--    de referência (início da semana).
--    A chave única (consultor_id, semana) viabiliza o UPSERT: relançar o mesmo
--    consultor/semana ATUALIZA o registro em vez de duplicar.
--    O dashboard agrega as semanas por mês; o relatório semanal usa a semana.
-- -----------------------------------------------------------------------------
CREATE TABLE lancamentos (
  id           INT       NOT NULL AUTO_INCREMENT,
  consultor_id INT       NOT NULL,
  mes          DATE      NOT NULL,
  passagens    INT       NULL,
  refil_diant  INT       NOT NULL DEFAULT 0,
  refil_tras   INT       NOT NULL DEFAULT 0,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_lancamento (consultor_id, mes),
  KEY idx_lancamento_mes (mes),
  CONSTRAINT fk_lancamento_consultor
    FOREIGN KEY (consultor_id) REFERENCES consultores (id)
    ON UPDATE CASCADE ON DELETE CASCADE,
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
JOIN consultores  c ON c.id    = l.consultor_id
JOIN unidades     u ON u.id    = c.unidade_id
JOIN precos_marca p ON p.marca = u.marca;

