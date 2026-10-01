import os, warnings, numpy as np, pandas as pd, psycopg2
warnings.filterwarnings("ignore")
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score
E = dict(l.strip().removeprefix("export ").split("=",1) for l in open(os.environ["ENVF"]) if "=" in l)
c = psycopg2.connect(host=E["DBT_PG_HOST"], port=E["DBT_PG_PORT"], dbname=E["DBT_PG_DATABASE"], user=E["DBT_PG_USER"], password=E["DBT_PG_PASSWORD"]); c.set_session(readonly=True)
def enc(X):
    X = X.copy()
    for col in X.columns:
        if not pd.api.types.is_numeric_dtype(X[col]) or X[col].dtype == bool: X[col] = X[col].astype(str).astype("category").cat.codes
    return X
def fit_eval(X, y, groups=None, name=""):
    rng = np.random.RandomState(0)
    ids = groups if groups is not None else np.arange(len(y))
    u = np.unique(ids); te_ids = set(rng.choice(u, int(len(u)*0.3), replace=False)); te = np.array([i in te_ids for i in ids])
    m = HistGradientBoostingClassifier(max_iter=150, random_state=0).fit(X[~te], y[~te]); p = m.predict_proba(X[te])[:,1]
    print(f"{name:55s} AUC {roc_auc_score(y[te], p):.3f}  PR-AUC {average_precision_score(y[te], p):.3f}  base {y[te].mean():.3f}")
# product level
pr = pd.read_sql("""select p.product_id, p.customer_id, p.product_type, p.currency, p.credit_limit, p.current_balance, p.interest_rate, p.days_past_due, p.product_status, p.opening_date, p.opening_channel,
  cu.credit_score, cu.estimated_monthly_income, cu.segment, cu.country, cu.registration_date
  from silver.stg_products p join silver.stg_customers cu using (customer_id) where p.credit_limit is not null""", c)
pr["util"] = pr.current_balance / pr.credit_limit.replace(0, np.nan)
y = (pr.days_past_due.fillna(0) > 0).astype(int).values
print("credit-limit products", len(pr), "delinquent rate %.3f" % y.mean())
fe = ["product_type","currency","credit_limit","current_balance","interest_rate","util","product_status","opening_channel","credit_score","estimated_monthly_income","segment","country"]
fit_eval(enc(pr[fe]), y, pr.customer_id.values, "product-level, customer-grouped split")
for f in ["credit_score","util","segment","interest_rate","product_status","product_type"]:
    fit_eval(enc(pr[[f]]), y, pr.customer_id.values, f"  single: {f}")
# customer level (the proposal's design)
cu = pr.groupby("customer_id").agg(n_prod=("product_id","count"), max_dpd=("days_past_due","max"), mean_util=("util","mean"), score=("credit_score","first"), income=("estimated_monthly_income","first"), segment=("segment","first"), country=("country","first")).reset_index()
yc = (cu.max_dpd.fillna(0) > 0).astype(int).values
print("customers with credit products", len(cu), "delinquent rate %.3f" % yc.mean())
fit_eval(enc(cu[["n_prod","mean_util","score","income","segment","country"]]), yc, None, "customer-level, all features (incl. n_prod)")
fit_eval(enc(cu[["mean_util","score","income","segment","country"]]), yc, None, "customer-level, WITHOUT n_prod")
fit_eval(enc(cu[["n_prod"]]), yc, None, "customer-level, n_prod ONLY")
print(cu.groupby("n_prod").apply(lambda d: pd.Series({"customers": len(d), "delinq_rate": (d.max_dpd.fillna(0)>0).mean()})).round(3).to_string())
# baseline of proposal
base = ((cu.score < 620) | (cu.mean_util > 0.8)).astype(int)
print("proposal baseline (score<620 or util>80%%): AUC %.3f" % roc_auc_score(yc, base))
