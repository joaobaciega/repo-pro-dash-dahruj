# Conferência da metodologia — 06/10/2026

Fonte: consultas somente leitura ao Aiven e arquivo `Controle de Estoque Dahruj
29-09.xlsx`. Sell In até 29/09/2026; Sell Out por competência até setembro/2026.
Os valores abaixo são uma fotografia da conferência, não constantes do código.

## Comparação com o Excel

| Medida | Recalculado | Excel |
|---|---:|---:|
| Sell In dianteiros (pares) | 9.435 | 9.435 |
| Sell In traseiros (un) | 3.840 | 3.840 |
| Sell Out dianteiros (pares) | 7.783 | 7.783 |
| Sell Out traseiros (un) | 3.009 | 3.009 |
| Estoque dianteiros (pares) | 1.652 | 1.652 |
| Estoque traseiros (un) | 831 | 831 |
| Verba provisionada pelo Sell In | R$ 164.647,50 | R$ 164.647,50 |
| Verba vinculada ao Sell Out (três categorias) | R$ 134.668,75 | R$ 134.668,75 |
| Verba em estoque — consultor | R$ 20.675,00 | R$ 20.675,00 |
| Verba em estoque — gerente | R$ 5.168,75 | R$ 5.168,75 |
| Verba em estoque — marketing | R$ 4.135,00 | R$ 4.135,00 |
| Verba em estoque — total | R$ 29.978,75 | R$ 29.978,75 |

As quantidades do Sell Out também foram comparadas por mês e unidade com a
base do Excel, sem divergências. As tarifas do Sell In são uniformes: dianteiro
R$ 10 / R$ 2,50 / R$ 2 e traseiro R$ 5 / R$ 1,25 / R$ 1 (consultor/gerente/marketing).

## Correção dos pagamentos calculados

As marcações existentes indicam consultor/gerente pagos de janeiro a agosto;
setembro está em aberto. Janeiro não tem Sell Out, logo o valor pago é zero.
Os números representam pagamentos calculados a partir dessas marcações, não
uma auditoria de comprovantes de transferência.

| Medida | Cálculo anterior (Sell In) | Corrigido (Sell Out) |
|---|---:|---:|
| Consultor pago | R$ 98.950,00 | R$ 80.020,00 |
| Gerente pago | R$ 24.737,50 | R$ 20.005,00 |
| Marketing pago | R$ 14.696,99 | R$ 14.696,99 |
| Total pago | R$ 138.384,49 | R$ 114.721,99 |
| Saldo acumulado | R$ 26.263,01 | R$ 49.925,51 |

O saldo corrigido se decompõe em R$ 33.530,00 de consultor, R$ 8.382,50 de
gerente e R$ 8.013,01 de marketing. Consultor/gerente incluem R$ 25.843,75
vinculados ao estoque e R$ 16.068,75 de Sell Out de setembro ainda não pago.
Marketing mantém a regra existente de reserva no Sell In menos gastos reais.
A parcela de marketing em estoque já integra a reserva, não é somada novamente.

## Diferença de apresentação por unidade

O Excel soma Nissan Ceasa e Braz Leme sob o nome Nissan Ceasa: 226 dianteiros e
68 traseiros. Separadamente, Ceasa tem 167 dianteiros e 70 traseiros; Braz Leme
tem 59 dianteiros e **−2 traseiros** (100 entradas, 102 saídas). O total confere;
a diferença negativa precisa de conferência de entradas, estoque inicial ou
transferências, sem alterar automaticamente vendas válidas.

## Validação e aplicação

- Nove testes automatizados da metodologia e exportação passaram.
- A tela foi executada com dados reais do Aiven pelo teste do Streamlit,
  validando a visão anual e o filtro de fevereiro (R$ 5.987,50 de consultor/gerente).
- O relatório `Conferencia Verbas - 06-10-2026.xlsx` usa os mesmos cálculos da tela.
- Nenhum dado SQL foi alterado; a correção é calculada na leitura das bases.
- A base local de Sell Out termina em julho; os valores acima usam o Aiven.
- Alteração feita no projeto local. Para aplicar ao dashboard publicado, publicar
  juntos `app.py`, `db.py`, `verbas.py` e `verbas_pagina.py`.
