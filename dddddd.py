from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.feature_selection import SelectKBest, f_classif,SelectFromModel
import pandas as pd

''''Parte D'''

#D1------------------------------------------
SEED = 42

df = pd.read_csv('bank-additional-full.csv', sep=';')

#Separar as variáveis explicativas (X) da variável alvo (y)
X = df.drop(columns=['y'])
y = df['y']

#Divisão treino/teste 75/25, estratificada por y
X_train, X_test, y_train, y_test = train_test_split(
    X, y, 
    test_size=0.25, 
    stratify=y, 
    random_state=SEED
)

print(f"Dimensões do conjunto de treino (X_train): {X_train.shape}")
print(f"Dimensões do conjunto de teste (X_test): {X_test.shape}")
print("\nDistribuição proporcional da classe 'y' no treino:")

#verificar a distribuição proporcional da classe 'y' no conjunto de treino
print(y_train.value_counts(normalize=True) * 100)

#D2------------------------------------------

#Identificar os tipos de variáveis com base nas colunas de X_train
colunas_numericas = X_train.select_dtypes(include=['int64', 'float64']).columns.tolist()
colunas_categoricas = X_train.select_dtypes(include=['object', 'category']).columns.tolist()

print(f"Variáveis numéricas ({len(colunas_numericas)}): {colunas_numericas}")
print(f"Variáveis categóricas ({len(colunas_categoricas)}): {colunas_categoricas}")

#Construir o ColumnTransformer
preprocessor = ColumnTransformer(
    transformers=[
        ('num', StandardScaler(), colunas_numericas),
        ('cat', OneHotEncoder(handle_unknown='ignore', drop='first'), colunas_categoricas)
    ]
)

#Construir o pipeline com o pré-processador e o modelo de referência
#max_iter elevado para garantir a convergência do solver
modelo_ref = Pipeline(steps=[
    ('preprocessor', preprocessor),
    ('classifier', LogisticRegression(max_iter=1000, random_state=42))
])

# Ajustar no treino e transformar para verificar o número exato de colunas após a codificação
X_train_transformado = preprocessor.fit_transform(X_train)
num_colunas_finais = X_train_transformado.shape[1]

print("\n" + "="*50)
print(f"NÚMERO DE COLUNAS APÓS A CODIFICAÇÃO: {num_colunas_finais}")
print("="*50)

#Validação cruzada estratificada de 5 folds (métrica: ROC-AUC)
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
scores_auc = cross_val_score(modelo_ref, X_train, y_train, cv=cv, scoring='roc_auc')

print(f"\nResultados da Validação Cruzada (AUC por fold): {scores_auc}")
print(f"AUC Média: {scores_auc.mean():.4f} (+/- {scores_auc.std():.4f})")

#Depois da codificação, o número de colunas aumentou para 53. 
# Temos um bom desempenho do modelo de referência, com uma AUC média de 0.933, 
# indicando uma boa capacidade de discriminação entre as classes.

#D3------------------------------------------

#Construir o pipeline com o ColumnTransformer, SelectKBest (k=10) e a Regressão Logística
pipeline_kbest = Pipeline(steps=[
    ('preprocessor', preprocessor), # Usa o pré-processador definido na alínea D2
    ('selector', SelectKBest(score_func=f_classif, k=10)),
    ('classifier', LogisticRegression(max_iter=1000, random_state=42))
])

#Validação cruzada estratificada de 5 folds (métrica: ROC-AUC)
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
scores_auc_kbest = cross_val_score(pipeline_kbest, X_train, y_train, cv=cv, scoring='roc_auc')

print("="*50)
print("RESULTADOS DA VALIDAÇÃO CRUZADA (SelectKBest, k=10)")
print("="*50)
print(f"AUC por fold: {scores_auc_kbest}")
print(f"AUC Média: {scores_auc_kbest.mean():.4f} (+/- {scores_auc_kbest.std():.4f})")

#Obter a lista das 10 colunas escolhidas pelo SelectKBest
preprocessor.fit(X_train)
nomes_features_codificadas = preprocessor.get_feature_names_out()

#Ajustar o seletor SelectKBest no X_train transformado
X_train_trans = preprocessor.transform(X_train)
selector = SelectKBest(score_func=f_classif, k=10)
selector.fit(X_train_trans, y_train)

# Identificar as colunas selecionadas
mascara_features = selector.get_support()
features_selecionadas = nomes_features_codificadas[mascara_features]

print("\n" + "="*50)
print("LISTA DAS 10 COLUNAS ESCOLHIDAS PELO SELECTKBEST:")
print("="*50)
for i, col in enumerate(features_selecionadas, 1):
    print(f"{i}. {col}")


#D4------------------------------------------
# Valores de C a testar
valores_C = [0.01, 0.1, 1.0]

for c in valores_C:
    # Definir o modelo com penalização L1
    modelo_l1 = LogisticRegression(penalty='l1', solver='liblinear', C=c, max_iter=1000, random_state=42)
    
    # Construir o pipeline com o ColumnTransformer, SelectFromModel e a Regressão Logística final
    pipeline_l1 = Pipeline(steps=[
        ('preprocessor', preprocessor), # Utiliza o pré-processador da alínea D2
        ('selector', SelectFromModel(modelo_l1)),
        ('classifier', LogisticRegression(max_iter=1000, random_state=42))
    ])
    
    # Validação cruzada estratificada de 5 folds
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = cross_val_score(pipeline_l1, X_train, y_train, cv=cv, scoring='roc_auc')
    
    print(f"C = {c} | AUC Média: {scores.mean():.4f} (+/- {scores.std():.4f})")

#ESCOLHA DO MELHOR C (exemplo com C = 0.1, podes ajustar conforme os teus resultados) ---
melhor_C = 1.0
modelo_l1_final = LogisticRegression(penalty='l1', solver='liblinear', C=melhor_C, max_iter=1000, random_state=42)

pipeline_escolhido = Pipeline(steps=[
    ('preprocessor', preprocessor),
    ('selector', SelectFromModel(modelo_l1_final)),
    ('classifier', LogisticRegression(max_iter=1000, random_state=42))
])

# Recalcular scores oficiais para o C escolhido
scores_final = cross_val_score(pipeline_escolhido, X_train, y_train, cv=cv, scoring='roc_auc')
print("\n" + "="*50)
print(f"RESULTADOS FINAIS COM C = {melhor_C}")
print("="*50)
print(f"AUC Média: {scores_final.mean():.4f} (+/- {scores_final.std():.4f})")

# Obter a lista das colunas escolhidas pelo SelectFromModel
preprocessor.fit(X_train)
nomes_features = preprocessor.get_feature_names_out()

selector_final = SelectFromModel(modelo_l1_final)
X_train_trans = preprocessor.transform(X_train)
selector_final.fit(X_train_trans, y_train)

features_l1 = nomes_features[selector_final.get_support()]
print(f"\nNúmero de colunas selecionadas: {len(features_l1)}")
print("Lista das colunas escolhidas:")
for i, col in enumerate(features_l1, 1):
    print(f"{i}. {col}")

#D5------------------------------------------
from sklearn.metrics import roc_auc_score
import pandas as pd

# 1. Definir os três modelos / abordagens treinados anteriormente:
# - Abordagem 1: Modelo completo (D2)
# - Abordagem 2: SelectKBest k=10 (D3)
# - Abordagem 3: SelectFromModel com L1 (D4)

# Vamos treinar/ajustar os pipelines no X_train e avaliar no X_test guardado


# Pré-processador
col_num = X_train.select_dtypes(include=['int64', 'float64']).columns.tolist()
col_cat = X_train.select_dtypes(include=['object', 'category']).columns.tolist()

preprocessor = ColumnTransformer(
    transformers=[
        ('num', StandardScaler(), col_num),
        ('cat', OneHotEncoder(handle_unknown='ignore', drop='first'), col_cat)
    ]
)

# 1. Pipeline Completo (D2)
pipe_completo = Pipeline([('preprocessor', preprocessor), ('clf', LogisticRegression(max_iter=1000, random_state=42))])
pipe_completo.fit(X_train, y_train)
auc_teste_completo = roc_auc_score(y_test, pipe_completo.predict_proba(X_test)[:, 1])

# 2. Pipeline SelectKBest (D3)
pipe_kbest = Pipeline([('preprocessor', preprocessor), ('selector', SelectKBest(f_classif, k=10)), ('clf', LogisticRegression(max_iter=1000, random_state=42))])
pipe_kbest.fit(X_train, y_train)
auc_teste_kbest = roc_auc_score(y_test, pipe_kbest.predict_proba(X_test)[:, 1])

# 3. Pipeline SelectFromModel L1 (D4, C=0.1)
modelo_l1 = LogisticRegression(penalty='l1', solver='liblinear', C=0.1, max_iter=1000, random_state=42)
pipe_l1 = Pipeline([('preprocessor', preprocessor), ('selector', SelectFromModel(modelo_l1)), ('clf', LogisticRegression(max_iter=1000, random_state=42))])
pipe_l1.fit(X_train, y_train)
auc_teste_l1 = roc_auc_score(y_test, pipe_l1.predict_proba(X_test)[:, 1])

# Obter listas de variáveis selecionadas em D3 e D4 para a interseção
preprocessor.fit(X_train)
nomes_feat = preprocessor.get_feature_names_out()

# D3 features
sel_kbest = SelectKBest(f_classif, k=10).fit(preprocessor.transform(X_train), y_train)
feat_d3 = set(nomes_feat[sel_kbest.get_support()])

# D4 features
sel_l1 = SelectFromModel(LogisticRegression(penalty='l1', solver='liblinear', C=0.1, max_iter=1000, random_state=42)).fit(preprocessor.transform(X_train), y_train)
feat_d4 = set(nomes_feat[sel_l1.get_support()])

intersecao = feat_d3.intersection(feat_d4)

print("="*60)
print("TABELA COMPARATIVA FINAL (TESTE)")
print("="*60)
print(f"Modelo Completo (D2)         | Colunas: 53 | AUC Teste: {auc_teste_completo:.4f}")
print(f"SelectKBest (D3, k=10)       | Colunas: 10 | AUC Teste: {auc_teste_kbest:.4f}")
print(f"SelectFromModel L1 (D4)      | Colunas: 34 | AUC Teste: {auc_teste_l1:.4f}")
print("-" * 60)
print(f"Interseção entre D3 e D4 ({len(intersecao)} variáveis):")
for f in intersecao:
    print(f" - {f}")

'''
Com $C = 1.0$, o SelectFromModel selecionou 48 colunas (quase o modelo completo), 
o que significa que o L1 foi menos restritivo e reteve praticamente todas as variáveis úteis. 
Por sua vez, o SelectKBest limitou-se estritamente às 10 melhores de forma univariada. 
No entanto, não discordam na essência: as 10 variáveis escolhidas pelo SelectKBest são exatamente as mesmas 10 
que o SelectFromModel considerou absolutamente cruciais e manteve no seu topo de prioridades.'''