import os, warnings, pandas as pd, numpy as np, psycopg2
warnings.filterwarnings("ignore")
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import roc_auc_score, r2_score
E = dict(l.strip().removeprefix("export ").split("=",1) for l in open(os.environ["ENVF"]) if "=" in l)
c = psycopg2.connect(host=E["DBT_PG_HOST"], port=E["DBT_PG_PORT"], dbname=E["DBT_PG_DATABASE"], user=E["DBT_PG_USER"], password=E["DBT_PG_PASSWORD"]); c.set_session(readonly=True)
def enc(X):
    X = X.copy()
    for col in X.columns:
        if not pd.api.types.is_numeric_dtype(X[col]) or X[col].dtype == bool: X[col] = X[col].astype(str).astype("category").cat.codes
    return X
def single(df, feats, y, k, kind="clf", top=6):
    out = {}
    for f in feats:
        X = enc(df[[f]])
        if kind == "clf": m = HistGradientBoostingClassifier(max_iter=60, random_state=0).fit(X.iloc[:k], y.iloc[:k]); out[f] = roc_auc_score(y.iloc[k:], m.predict_proba(X.iloc[k:])[:,1])
        else: m = HistGradientBoostingRegressor(max_iter=60, random_state=0).fit(X.iloc[:k], y.iloc[:k]); out[f] = r2_score(y.iloc[k:], m.predict(X.iloc[k:]))
    return sorted(out.items(), key=lambda t: -t[1])[:top]
# 1) CSAT from the interaction context
df = pd.read_sql("""select s.survey_date, s.main_score, i.interaction_type, i.channel, i.contact_reason, i.duration_seconds, i.wait_time_seconds, i.was_resolved, i.was_escalated, i.requires_followup, i.detected_sentiment, i.sentiment_score, i.agent_used_accent, i.customer_detected_accent, cu.country, cu.segment, cu.credit_score
 from silver.stg_satisfaction_surveys s join silver.stg_call_center_interactions i using (interaction_id) join silver.stg_customers cu on cu.customer_id=s.customer_id where s.survey_type='CSAT' and s.main_score is not null""", c).sort_values("survey_date").reset_index(drop=True)
k = int(len(df)*0.7); y = (df.main_score <= 2).astype(int)
print("CSAT n", len(df), "dissatisfied(<=2) rate %.3f" % y.mean(), "score dist", df.main_score.value_counts().sort_index().to_dict())
feats = [x for x in df.columns if x not in ("survey_date","main_score")]
m = HistGradientBoostingClassifier(max_iter=150, random_state=0).fit(enc(df[feats]).iloc[:k], y.iloc[:k]); print("CSAT all-feature AUC %.3f" % roc_auc_score(y.iloc[k:], m.predict_proba(enc(df[feats]).iloc[k:])[:,1]))
print(" single:", [(f, round(a,3)) for f, a in single(df, feats, y, k)])
pre = ["interaction_type","channel","contact_reason","wait_time_seconds","country","segment","credit_score"]
m = HistGradientBoostingClassifier(max_iter=150, random_state=0).fit(enc(df[pre]).iloc[:k], y.iloc[:k]); print("CSAT pre-call-features AUC %.3f" % roc_auc_score(y.iloc[k:], m.predict_proba(enc(df[pre]).iloc[k:])[:,1]))
# 2) wait time regression
w = pd.read_sql("select interaction_date, interaction_type, channel, contact_reason, wait_time_seconds, extract(hour from interaction_date) hr, extract(dow from interaction_date) dow, customer_detected_accent from silver.stg_call_center_interactions where wait_time_seconds is not null and random()<0.3", c).sort_values("interaction_date").reset_index(drop=True)
k = int(len(w)*0.7); f2 = ["interaction_type","channel","contact_reason","hr","dow"]
m = HistGradientBoostingRegressor(max_iter=150, random_state=0).fit(enc(w[f2]).iloc[:k], w.wait_time_seconds.iloc[:k]); print("wait_time R2 %.3f  (mean %.0fs, sd %.0fs)" % (r2_score(w.wait_time_seconds.iloc[k:], m.predict(enc(w[f2]).iloc[k:])), w.wait_time_seconds.mean(), w.wait_time_seconds.std()))
print(" single R2:", [(f, round(a,3)) for f, a in single(w, f2, w.wait_time_seconds, k, "reg", 5)])
# 3) churn: customer_status in (Closed, Inactive) vs Active from behaviour
ch = pd.read_sql("""select cu.customer_status, cu.registration_date, cu.segment, cu.country, cu.credit_score, cu.estimated_monthly_income, cu.accepts_marketing,
 coalesce(p.n,0) n_products, coalesce(m.n,0) n_complaints, coalesce(i.n,0) n_calls
 from silver.stg_customers cu
 left join (select customer_id, count(*) n from silver.stg_products group by 1) p using (customer_id)
 left join (select customer_id, count(*) n from silver.stg_complaints group by 1) m using (customer_id)
 left join (select customer_id, count(*) n from silver.stg_call_center_interactions group by 1) i using (customer_id)""", c).sort_values("registration_date").reset_index(drop=True)
y = ch.customer_status.isin(["Closed","Inactive"]).astype(int); k = int(len(ch)*0.7); f3 = [x for x in ch.columns if x not in ("customer_status","registration_date")]
m = HistGradientBoostingClassifier(max_iter=150, random_state=0).fit(enc(ch[f3]).iloc[:k], y.iloc[:k]); print("churn(Closed/Inactive) rate %.3f AUC %.3f" % (y.mean(), roc_auc_score(y.iloc[k:], m.predict_proba(enc(ch[f3]).iloc[k:])[:,1])))
print(" single:", [(f, round(a,3)) for f, a in single(ch, f3, y, k, "clf", 4)])
