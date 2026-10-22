import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


'''Parte A'''

#A1------------------------------------------
'''
Grupo: Cliente
age: Numérica (contínua/discreta, representa a idade do cliente).  
job: Categórica nominal (tipo de emprego).   
marital: Categórica nominal (estado civil).   
education: Categórica ordinal (nível de escolaridade)   
default: Categórica nominal (crédito em incumprimento).   
housing: Categórica nominal (crédito habitação).   
loan: Categórica nominal (crédito pessoal).   

Grupo: Último contacto
contact: Categórica nominal (tipo de canal de comunicação).   
month: Categórica nominal (mês do último contacto).  
day_of_week: Categórica nominal (dia da semana do último contacto).
duration: Numérica (duração da chamada em segundos).   

Grupo: Campanhas
campaign: Numérica (número de contactos efetuados nesta campanha).   
pdays: Categórica nominal (número de dias desde o último contacto, 999 significa que o cliente não foi contactado anteriormente). 
previous: Numérica (número de contactos antes desta campanha).   
poutcome: Categórica nominal (resultado da campanha anterior).   

Grupo: Economia
emp.var.rate: Numérica (taxa de variação do emprego).   
cons.price.idx: Numérica (índice de preços ao consumidor).   
cons.conf.idx: Numérica (índice de confiança do consumidor).   
euribor3m: Numérica (taxa euribor a 3 meses).   
nr.employed: Numérica (número de empregados). 
'''

#A2------------------------------------------
df = pd.read_csv('bank-additional-full.csv', sep=';')

# 2. Calcular a proporção (frequência relativa) da variável alvo 'y'
proporcao = df['y'].value_counts(normalize=True) * 100
contagem = df['y'].value_counts()

# 3. Mostrar os resultados
print("="*50)
print("CONTAGEM ABSOLUTA:")
print(contagem)
print("\nPROPORÇÃO (%):")
print(proporcao.round(2))
print("="*50)

#Como o conjunto de dados é fortemente desequilibrado, a acurácia global deixa de ser fiável, 
# exigindo o recurso a métricas focadas na classe minoritária, como a Precision, o Recall, 
# a F1-Score ou a ROC-AUC.

#A3------------------------------------------

df['y_num'] = df['y'].apply(lambda x: 1 if x == 'yes' else 0)

# ==========================================
# GRÁFICO 1: Taxa de yes por poutcome
# ==========================================
plt.figure(figsize=(9, 6))
taxa_poutcome = df.groupby('poutcome')['y_num'].mean() * 100
ax1 = sns.barplot(x=taxa_poutcome.index, y=taxa_poutcome.values, palette='viridis')

plt.title("Qual é a taxa de subscrição (yes) de acordo com o resultado da campanha anterior (poutcome)?", 
          fontsize=11, fontweight='bold', pad=15)
plt.xlabel("Resultado da Campanha Anterior (poutcome)")
plt.ylabel("Taxa de Yes (%)")

# Caixa de resposta por baixo
plt.figtext(0.5, 0.02, "Resposta: Clientes com sucesso prévio (success) apresentam taxas de subscrição\nmuito superiores face aos restantes.", 
            ha='center', fontsize=10, style='italic', 
            bbox=dict(boxstyle='round,pad=0.6', facecolor='lightyellow', edgecolor='orange', alpha=0.9))

plt.tight_layout(rect=[0, 0.1, 1, 1])
plt.savefig('grafico_1_poutcome.png', dpi=300)
plt.close()


# ==========================================
# GRÁFICO 2: Taxa de yes por month
# ==========================================
plt.figure(figsize=(10, 6))
ordem_meses = ['mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
taxa_month = df.groupby('month')['y_num'].mean().reindex(ordem_meses) * 100
sns.lineplot(x=taxa_month.index, y=taxa_month.values, marker='o', color='teal', linewidth=2.5)

plt.title("Como varia a taxa de subscrição (yes) ao longo dos diferentes meses do ano (month)?", 
          fontsize=11, fontweight='bold', pad=15)
plt.xlabel("Mês (month)")
plt.ylabel("Taxa de Yes (%)")
plt.grid(True, linestyle='--', alpha=0.6)

# Caixa de resposta por baixo
plt.figtext(0.5, 0.02, "Resposta: Meses como março, outubro, setembro e dezembro registam taxas de conversão\nsubstancialmente mais elevadas do que os meses de pico de chamadas.", 
            ha='center', fontsize=10, style='italic', 
            bbox=dict(boxstyle='round,pad=0.6', facecolor='lightyellow', edgecolor='orange', alpha=0.9))

plt.tight_layout(rect=[0, 0.1, 1, 1])
plt.savefig('grafico_2_month.png', dpi=300)
plt.close()


# ==========================================
# GRÁFICO 3: Boxplot de campaign
# ==========================================
plt.figure(figsize=(9, 6))
sns.boxplot(x=df['campaign'], color='skyblue')

plt.title("Qual é a distribuição e a presença de valores atípicos (outliers) no número de contactos da campanha atual (campaign)?", 
          fontsize=11, fontweight='bold', pad=15)
plt.xlabel("Número de Contactos na Campanha Atual (campaign)")

# Caixa de resposta por baixo
plt.figtext(0.5, 0.02, "Resposta: A grande maioria das chamadas concentra-se nos valores mais baixos (1 a 3),\nexistindo uma cauda longa com vários outliers em número elevado de contactos.", 
            ha='center', fontsize=10, style='italic', 
            bbox=dict(boxstyle='round,pad=0.6', facecolor='lightyellow', edgecolor='orange', alpha=0.9))

plt.tight_layout(rect=[0, 0.1, 1, 1])
plt.savefig('grafico_3_campaign.png', dpi=300)
plt.close()