import os, numpy as np, pandas as pd, psycopg2
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score
E = dict(l.strip().removeprefix("export ").split("=",1) for l in open(os.environ["ENVF"]) if "=" in l)
c = psycopg2.connect(host=E["DBT_PG_HOST"], port=E["DBT_PG_PORT"], dbname=E["DBT_PG_DATABASE"], user=E["DBT_PG_USER"], password=E["DBT_PG_PASSWORD"]); c.set_session(readonly=True)
q = """select t.transaction_date, t.amount, t.amount_usd, t.currency, t.channel, t.transaction_type, t.transaction_category,
 t.merchant_category, t.transaction_country, t.transaction_status, t.response_code, t.is_fraud::int y,
 cu.country customer_country, cu.segment, cu.credit_score, p.product_type
 from silver.stg_transactions t join silver.stg_customers cu using (customer_id) left join silver.stg_products p using (product_id)
 where t.is_fraud or random() < 0.2"""
df = pd.read_sql(q, c); print(df.shape, "pos", int(df.y.sum()))
df["hour"] = df.transaction_date.dt.hour; df["dow"] = df.transaction_date.dt.dayofweek
df["foreign"] = (df.transaction_country != df.customer_country).astype(int)
df = df.sort_values("transaction_date"); cut = int(len(df)*0.7); tr, te = df.iloc[:cut], df.iloc[cut:]
cats = ["currency","channel","transaction_type","transaction_category","merchant_category","transaction_country","transaction_status","response_code","customer_country","segment","product_type"]
nums = ["amount","amount_usd","credit_score","hour","dow","foreign"]
X = df[cats+nums].copy()
for k in cats: X[k] = X[k].astype("category").cat.codes
m = HistGradientBoostingClassifier(max_iter=200, categorical_features=[X.columns.get_loc(k) for k in cats], random_state=0)
m.fit(X.iloc[:cut], tr.y); p = m.predict_proba(X.iloc[cut:])[:,1]
print("train pos", int(tr.y.sum()), "test pos", int(te.y.sum()), "test rate %.4f" % te.y.mean())
print("GBM  AUC %.3f  PR-AUC %.4f (random baseline %.4f)" % (roc_auc_score(te.y,p), average_precision_score(te.y,p), te.y.mean()))
print("amount alone AUC %.3f" % roc_auc_score(te.y, te.amount_usd.fillna(0)))
for col in ["foreign","hour","channel","merchant_category","transaction_type","transaction_country","response_code"]:
    g = df.groupby(col).y.agg(["mean","count"]); g = g[g["count"]>200]
    print(col, "fraud rate min %.4f max %.4f" % (g["mean"].min(), g["mean"].max()))
print(df.groupby("is_fraud" if False else "y")[["amount_usd","credit_score"]].median())
