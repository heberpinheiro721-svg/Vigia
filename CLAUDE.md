# VIGIA — Contexto do Projeto para Claude Code

## O que é este projeto
VIGIA é um dashboard de análise de investimentos em Streamlit para o **IAJA** (Instituto Adventista de Jubilação e Assistência), uma EFPC supervisionada pela PREVIC. Está participando de um desafio interno de automação com IA (deadline: 26/jun, apresentação: 30/jun). Prêmios: iPad Air M4 / iPad 10 / AirPods 4.

## Como rodar
```bash
# Em qualquer computador (via OneDrive)
# Duplo clique em iniciar.bat
```
O app roda em http://localhost:8501

## Estrutura de arquivos
```
VIGIA/
├── app.py                  # Arquivo principal — toda a UI Streamlit
├── ai_analysis.py          # Groq API: PERSONAS, chat_persona(), gerar_analise_compliance()
├── noticias.py             # RSS feeds paralelos (ThreadPoolExecutor), cache 30min
├── email_sender.py         # Envio de PDF por SMTP (SSL/TLS)
├── parser.py               # Leitura do CSV S3 Caceis
├── rules_engine.py         # Compliance CMN 4.661/2018
├── report_generator.py     # Geração de PDF com ReportLab
├── performance.py          # Leitura de cotas, última posição
├── balancete_parser.py     # Parse do PDF do balancete
├── bcb_api.py              # Benchmarks do Banco Central (CDI, IPCA, Ibovespa)
├── analytics.py            # Risco/retorno, concentração, atribuição de performance
├── risco_avancado.py       # VaR, CVaR, Drawdown, Correlação, Stress Test
├── projecao.py             # Monte Carlo, cenários determinísticos
├── historico.py            # Snapshots mensais de compliance
├── requirements.txt        # Dependências Python (97 pacotes)
├── iniciar.bat             # Script de inicialização para qualquer PC
└── data/
    ├── Composição/         # CSV do relatório S3 Caceis (carteira)
    ├── Balancete/          # PDF do balancete contábil
    ├── cotas/              # CSV Mapa de Evolução de Cotas
    └── .cache/             # Cache persistente em pickle (gerado automaticamente)
```

## Dados do IAJA
- **Patrimônio Social:** R$ 2.107.321.289,97
- **Planos:** Alpha, Beta, Gama
- **Regulação:** Resolução CMN 4.661/2018 (limites por segmento)
- **Supervisão:** PREVIC

## Módulos implementados (sidebar)
1. Dashboard — KPIs, compliance resumido, benchmarks, rendimento dos planos
2. Performance — Evolução, ranking, heatmap diário, Sharpe, atribuição, gestores
3. Meta Atuarial — IPCA ou CDI + spread, status por plano
4. Risco Avançado — VaR/CVaR, Drawdown, Correlação, Stress Test
5. Projeção de Patrimônio — Monte Carlo + cenários determinísticos
6. Simulador — Realocação por segmento com impacto no compliance
7. Compliance CMN 4.661 — Gauges por segmento + alertas + detalhamento
8. Análise IA — Diagnóstico executivo via Groq (Llama 3.3 70B)
9. Chat VIGIA — Chat com 4 personas (VIGIA, Buffett, Barsi, Soros)
10. Envio por E-mail — PDF por SMTP com configuração SSL/TLS
11. Balancete — Parse do PDF contábil, distribuição PS por plano
12. Relatório PDF — Geração e download do relatório executivo
13. Notícias — Duas colunas: EFPC e Previdência | Mercado Financeiro
14. Histórico — Snapshots mensais de compliance

**Botão especial:** Modo Conselho — apresentação limpa para reuniões (esconde sidebar)

## Tecnologias
- Python 3.12+ / Streamlit (port 8501, layout="wide")
- Groq API — modelo llama-3.3-70b-versatile (gratuito em console.groq.com)
- Plotly (gráficos), ReportLab (PDF), feedparser (RSS), smtplib (email)
- @st.cache_data + cache persistente em disco (pickle) para performance

## Feature: Personas de Investidores (ai_analysis.py)
- PERSONAS dict com: vigia, buffett, barsi, soros
- Função principal: chat_persona(mensagens, contexto, api_key, persona_key='vigia')
- Cada persona recebe os dados reais do portfólio IAJA no system prompt
- Trocar persona limpa o histórico do chat automaticamente

## Cache de dados (performance)
- @st.cache_data — cache em memória durante a sessão
- data/.cache/*.pkl — cache persistente em disco por arquivo
- Cache invalidado automaticamente quando o arquivo fonte é modificado (mtime)

## Fontes de notícias (noticias.py)
- EFPC: PREVIC, Ministério Previdência, Google News, ABRAPP, Agência Brasil
- Mercado: CVM, Tesouro Nacional, Banco Central, Infomoney, CNN Brasil, Valor Econômico

## Venv (ambiente virtual)
- NÃO está no OneDrive — fica em C:\Users\<usuario>\vigia_venv
- Recriado automaticamente pelo iniciar.bat em qualquer PC
- Dependências salvas em requirements.txt (97 pacotes)

## Estado atual (junho/2026)
- App funcionando com todas as 14 abas
- Performance otimizada com cache em disco (primeira carga salva pickle)
- Gauges de compliance com height=260 (corrigido corte visual)
- OneDrive sincronizando apenas código + dados (venv fora do OneDrive)
- iniciar.bat cria o venv e instala dependências automaticamente em qualquer PC

## Próximos passos possíveis
- Melhorias visuais adicionais
- Mais personas de investidores
- Integração com dados em tempo real
- Autenticação para acesso externo
