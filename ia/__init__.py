"""Camada de inteligência do projeto.

- `ia.tratamento`  coleta e tratamento das séries (Ryan)
- `ia.bases`       divisão temporal e normalização Min-Max (Ryan)
- `ia.multistep`   previsão multistep por mínimos quadrados (Ryan)
- `ia.svr`         SVR, regra de decisão e pipeline integrado (Lays)
- `ia.adaptador`   ponte com o backend: `gerar_recomendacao` (Miguel)
- `ia.exemplo`     modelo mínimo do contrato, para consulta

Nada é importado aqui para manter o custo de `import ia` baixo e evitar
depender de scikit-learn quando só o tratamento de dados é usado.
"""
