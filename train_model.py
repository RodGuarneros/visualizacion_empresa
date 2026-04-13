import os
import sys
import pandas as pd
import joblib
from sqlalchemy import create_engine

from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score, f1_score, classification_report
from sklearn.ensemble import RandomForestClassifier
import sklearn

CONN = "postgresql+psycopg://postgres@127.0.0.1:5432/app_movil"
MODEL_PATH = r"C:\Proyecto en venta\1. Churn\churn_model.joblib"

print("PYTHON:", sys.executable)
print("SKLEARN:", sklearn.__version__)
print("MODEL_PATH:", MODEL_PATH)

engine = create_engine(CONN, pool_pre_ping=True)

df = pd.read_sql("SELECT * FROM app.v_features_churn", engine)

y = df["churn_30d"].astype(int)
X = df.drop(columns=["churn_30d", "customer_id"])

cat_cols = [c for c in X.columns if X[c].dtype == "object"]
num_cols = [c for c in X.columns if c not in cat_cols]

pre = ColumnTransformer(
    transformers=[
        ("num", Pipeline([("imp", SimpleImputer(strategy="median"))]), num_cols),
        ("cat", Pipeline([
            ("imp", SimpleImputer(strategy="most_frequent")),
            ("oh", OneHotEncoder(handle_unknown="ignore")),
        ]), cat_cols),
    ]
)

model = RandomForestClassifier(
    n_estimators=500,
    random_state=42,
    n_jobs=-1,
    class_weight="balanced",
)

pipe = Pipeline([("pre", pre), ("model", model)])

Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
pipe.fit(Xtr, ytr)

proba = pipe.predict_proba(Xte)[:, 1]
pred = (proba >= 0.5).astype(int)

print("ROC AUC:", roc_auc_score(yte, proba))
print("F1:", f1_score(yte, pred))
print(classification_report(yte, pred, digits=3))

# BORRA y recrea el archivo para evitar que quede el viejo
if os.path.exists(MODEL_PATH):
    os.remove(MODEL_PATH)

joblib.dump(pipe, MODEL_PATH)

print("SAVED:", MODEL_PATH)
print("SIZE:", os.path.getsize(MODEL_PATH), "bytes")
print("MTIME:", int(os.path.getmtime(MODEL_PATH)))
