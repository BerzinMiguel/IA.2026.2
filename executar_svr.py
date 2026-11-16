import argparse
import json
from ia_svr.dados import juntar_series
from ia_svr.modelo import ModeloSVR

p = argparse.ArgumentParser(description='Treina e testa SVR demonstrativo')
p.add_argument('--dolar', required=True, help='Excel tratado do dólar')
p.add_argument('--bolsa', required=True, help='Excel tratado da ação')
p.add_argument('--volatilidade', required=True, help='Excel tratado de volatilidade')
p.add_argument('--saida', default='resultados')
a = p.parse_args()
dados = juntar_series(a.dolar, a.bolsa, a.volatilidade)
modelo = ModeloSVR()
metricas = modelo.treinar(dados, a.saida)
modelo.salvar(f'{a.saida}/modelo_svr.joblib')
ultimo = dados.iloc[-1]
resultado = modelo.prever(ultimo['dolar'], ultimo['bolsa'], ultimo['volatilidade'])
print('MÉTRICAS:', json.dumps(metricas, ensure_ascii=False, indent=2))
print('EXEMPLO DE PREVISÃO:', json.dumps(resultado, ensure_ascii=False, indent=2))
print('Atenção: este protótipo usa valores observados, não previsões multistep.')
