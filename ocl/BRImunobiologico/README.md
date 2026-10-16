# BRImunobiologico: classificação e mapeamento para o SNOMED CT

Revisão de 16/10/2026 dos mapeamentos do CodeSystem BRImunobiologico (org MS no OCL) para o SNOMED CT, conferidos na edição internacional de 2026-10-01. Autoria: Jussara Macedo Pinho Rötzsch.

## Arquivos

- `BRImunobiologico-snomed.tsv`: os 118 conceitos, com a classe (vacina, soro/antitoxina, imunoglobulina, anticorpo monoclonal, diluente), o destino no Sumário do Paciente (IPS Brasil), o mapeamento atual no OCL, o proposto, o ATC e a mudança. É a mesma fonte usada pelo guia do RIA (`ig_InspiraRIA/scripts/dados`).
- `BRImunobiologico-mapeamentos.jsonl`: importação em lote no OCL (uma linha por mapeamento).
  - Linha com `id`: atualiza o mapeamento existente (gera nova versão, preserva o histórico).
  - Linha com `id` e `"retired": true`: retira o mapeamento.
  - Linha sem `id`: cria o mapeamento.

## Resumo

| Mudança | Conceitos |
|---|---|
| Mantém | 33 |
| Troca o alvo (produto mais específico, "only" no lugar de "containing", conceito inativo, erro) | 47 |
| Troca só o tipo | 2 (VIP; MenB+C, 66) |
| Novo | 32 |
| Sem mapeamento | 2 (nirsevimabe, 115 e 116) |
| Retira | 1 (SAR) |
| Corrige a origem | 1 (117) |

Erros corrigidos:

- VPC13 (59): o alvo 1119254000 está inativo desde 2023-12-01.
- PENTA (42): o alvo 871895005 inclui pólio; a penta (DTP/HepB/Hib) não tem.
- SABOT (69): o alvo era o toxoide botulínico (substância, que é vacina); o soro é antitoxina.
- SAR (7): o alvo era a imunoglobulina antirrábica humana (substância); o soro é heterólogo. Não há produto no SNOMED CT internacional; o mapeamento é retirado.
- INF3 alta dosagem (117): o mapeamento usava o código de origem "INF3-alta dosagem", que não existe no CodeSystem.
- Conceito 110: tem o sinônimo "IgG4, H chain", que não pertence ao conceito (corrigir no OCL; não está no lote).

## Antes de importar

1. Conferido em 16/10/2026: todos os alvos do lote estão na fonte `/orgs/SNOMED/sources/gps/`. Dois alvos propostos não estão e ficaram fora do lote até a conferência: 1396376000 (MenB+C only; o conceito 66 fica em 921000221108 com o tipo corrigido para NARROWER-THAN) e 58531000087106 (Nirsevimab only product; 115 e 116 ficam sem mapeamento). Os mapeamentos para o ATC (327 a 331) não são tocados.
2. Conferir o formato da importação em lote na versão do OCL em uso (campos `id`, `retired` e `extras`) com um lote de teste.
3. Os diluentes ficam mapeados para o conceito genérico 74626007 (Drug diluent), que é `product`, não `medicinal product`. Não sobem para o IPS.
