# Contrato: CLI do Simulador

```text
python -m simulador [opções]
```

| Opção                 | Env                        | Padrão           | Descrição                                              |
|-----------------------|----------------------------|------------------|--------------------------------------------------------|
| `--pedidos N`          | `SIMULADOR_PEDIDOS`         | `20`             | Pedidos simultâneas mantidas em andamento               |
| `--intervalo-ms MS`   | `SIMULADOR_INTERVALO_MS`   | `500`            | Intervalo entre ciclos; a cada ciclo pedidos sorteadas avançam uma etapa |
| `--duracao-s S`       | `SIMULADOR_DURACAO_S`      | `0` (infinito)   | Encerra após S segundos                                |
| `--max-eventos N`     | `SIMULADOR_MAX_EVENTOS`    | `0` (infinito)   | Encerra após N eventos                                 |
| `--saida DIR`         | `SIMULADOR_SAIDA`          | `dados/eventos`  | Pasta de destino dos arquivos JSON                     |
| `--seed N`            | `SIMULADOR_SEED`           | aleatório        | Semente para execução reprodutível                     |
| `--prob-falha P`      | `SIMULADOR_PROB_FALHA`     | `0.15`           | Probabilidade de falha em cada tentativa de entrega    |
| `--metrics-port P`    | `SIMULADOR_METRICS_PORT`   | `0` (desligado)  | Porta HTTP para `/metrics`                             |

Comportamento:
- Cada evento é gravado em `<saida>/<occurred_at>_<pedido_id>_<event_id>.json` via arquivo
  temporário oculto + rename atômico.
- Todo evento gerado é válido contra [evento-pedido.schema.json](./evento-pedido.schema.json).
- `SIGINT`/`SIGTERM`: termina o ciclo atual, não deixa `.tmp` e sai com código `0`.
- Códigos de saída: `0` sucesso, `2` argumentos inválidos, `1` erro de I/O (ex.: pasta sem
  permissão de escrita).
- Logs JSON em stdout: um resumo a cada 10 s (`eventos_gerados`, `pedidos_ativos`,
  `pedidos_concluidos`).
