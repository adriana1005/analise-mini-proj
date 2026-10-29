# Vigia da Câmara 7 — Monitorização em Streaming

## Autores
   - **Nome**: Adriana Abreu, 53672
   - **Nome**: Leonor Rebola, 53663
   - **Semente do grupo**: 107335 (53672 + 53663)
   - **Curso**: Inteligência Artificial e Ciência de Dados
   - **UC**: Análise de Dados

## Descrição do Trabalho
Sistema de monitorização em tempo real de uma câmara frigorífica de fruta (Câmara 7). É composto por três processos independentes:

1. **Simulador** (`simulador.py`): gera o fluxo do sensor (1 leitura por segundo, em JSON) com ciclo do compressor, ruído, portas, avaria lenta do compressor e falhas de sensor (valor preso, picos, silêncio, duplicados e desordem). Todos os parâmetros saem da semente.
2. **Servidor** (`servidor.py`, Flask): valida as leituras, mantém estatísticas incrementais com memória limitada (Welford, janela de 5 min, EWMA, tendência por regressão linear), executa o motor de alertas (R1 a R5) e envia o estado ao browser por **Server-Sent Events**.
3. **Dashboard** (`static/index.html`, Chart.js): gráfico dos últimos 15 min, indicadores, registo de alertas com botão de reconhecer, limites configuráveis e estado da ligação.

O servidor nunca lê o código do simulador: descobre as avarias apenas pelos dados.

---

## Estrutura do Projeto
```
cam7/
├── simulador.py
├── servidor.py
├── grafico.py
├── requirements.txt
├── static/
│   └── index.html
├── demo/
│   ├── registo.csv
│   ├── alertas_log.csv
│   └── grafico_demo.png
├── relatorio.pdf
└── README.md
```

---

## Requisitos
Python 3.9 ou superior e ligação à internet (o dashboard carrega o Chart.js por CDN).

```bash
pip install -r requirements.txt
```

---

## Como Executar

1. Num primeiro terminal, arrancar o servidor:
```bash
python servidor.py
```
2. Abrir o dashboard em `http://127.0.0.1:5000`.
3. Num segundo terminal, arrancar o simulador no cenário de demonstração:
```bash
python simulador.py --cenario demo --velocidade 20
```
   O demo demora cerca de 6 minutos reais (`--velocidade 20` = 20 s simulados por leitura).
4. No fim, gerar o gráfico do cenário:
```bash
python grafico.py
```

**Nota:** reiniciar o servidor antes de cada nova execução do simulador. O servidor guarda os `seq` já vistos e trataria um novo arranque como duplicados. Os ficheiros `registo.csv` e `alertas_log.csv` são reescritos ao arrancar o servidor.

### Opções do simulador
| Opção | Efeito |
|---|---|
| `--semente N` | Semente do gerador (por defeito, 107335) |
| `--velocidade V` | Segundos simulados por leitura (1 = tempo real) |
| `--cenario demo` | Corre o cenário de demonstração |
| `--falha {auto,nenhuma,preso,picos,silencio}` | Falha de sensor (auto = a da semente) |
| `--sem-portas`, `--sem-avaria`, `--sem-duplicados` | Desliga cada evento, para testar regras isoladamente |
| `--url URL` | Endpoint do servidor (por defeito, `http://127.0.0.1:5000/ingest`) |

---

## Parâmetros do Grupo (semente 107335)
| Parâmetro | Valor |
|---|---|
| Setpoint | 1,0 °C |
| Limites superior / inferior | 3,0 / −1,0 °C |
| Ruído σ | 0,25 °C |
| Intervalo médio entre aberturas de porta | 15 min |
| Início da avaria (min simulados) | 30 |
| Taxa da avaria | 0,6 °C/h |
| Período do compressor | 13 min |
| Falha de sensor no demo | picos (minutos 60 a 75) |

---

## Motor de Alertas
| Regra | Nível | Condição |
|---|---|---|
| R1 · Limite com persistência | CRÍTICO | EWMA fora dos limites durante mais de N = 2 min (tempo contado fora do período de tolerância da porta) |
| R2 · Histerese | — | A R1 só fecha quando a EWMA volta a estar 0,5 °C dentro da zona segura |
| R3 · Tendência | AVISO | Inclinação acima de 0,35 °C/h durante 5 min, com a porta fechada (fecha abaixo de 0,25 °C/h). Regressão linear sobre 60 min (mínimo de 50 min de dados), só com leituras fora de períodos de porta |
| R4 · Porta | INFO / AVISO | INFO quando abre; AVISO se ficar aberta mais de 2 min. R1 e R3 ficam em tolerância enquanto está aberta e nos 8 min seguintes |
| R5 · Saúde do sensor | CRÍTICO / AVISO | CRÍTICO sem mensagens há mais de 10 s reais; AVISO com 30 leituras idênticas (valor preso); AVISO com mais de 5% de leituras rejeitadas (fecha com ≤ 2%) |

Cada alerta passa por três estados: **ativo**, **reconhecido** (botão no dashboard) e **resolvido**. Um alerta de uma regra não volta a disparar enquanto o anterior dessa regra estiver ativo.

Outras escolhas: EWMA com α = 0,1; janela de 5 min para média, desvio padrão, mínimo e máximo; o tempo simulado (`ts`) governa as janelas e a persistência, e o relógio real do servidor governa o detetor de silêncio.

---

## Outputs
Gerados na pasta onde corre o servidor:
1. **registo.csv** — leituras válidas (temperatura, EWMA, tendência, porta, seq)
2. **alertas_log.csv** — abertura e fecho de cada alerta
3. **grafico_demo.png** — gráfico do cenário de demonstração, com os limites, as faixas de porta aberta, o início real da avaria e o instante de cada alerta

---

## Resultados do Cenário de Demonstração
A execução entregue cobre 98 min simulados (14:00 a 15:38).
- Início real da avaria: 14:30. Primeiro alerta da avaria: **R3 às 15:18**, 48 min depois, com a temperatura ainda longe do limite.
- Nenhum AVISO ou CRÍTICO nos primeiros 30 min (antes da avaria).
- A R1 não disparou: a EWMA chegou a 3,06 °C às 15:24, dentro da tolerância da porta.
- A R5-rejeicoes disparou às 15:13 (7% de leituras rejeitadas), coerente com a falha de picos da semente.

---

## Declaração de Utilização de IA
- **Ferramenta**: Claude (Anthropic).
- **Para quê**: geração do código inicial do simulador, do servidor, do dashboard e do `grafico.py`; ajuste dos parâmetros da R3 depois de analisarmos os CSV do demo (um falso alarme antes da avaria); cálculo dos replays do Q3 sobre os nossos dados; estrutura deste README.
- Revimos todo o código e ambos os elementos conseguem explicá-lo.

---

## Limitações
- O dashboard depende do Chart.js por CDN, por isso precisa de internet.
- O servidor corre num único processo com um bloqueio global e guarda o estado em memória: não escala para muitas câmaras e perde o estado ao reiniciar.
- A R3 é lenta por desenho (janela de 60 min): troca rapidez por menos falsos alarmes.
- A tendência fica congelada durante os períodos de porta, pelo que o indicador mantém o último valor até a tolerância acabar.
- O alerta R5-silencio aparece no fim de qualquer execução, porque o simulador termina.