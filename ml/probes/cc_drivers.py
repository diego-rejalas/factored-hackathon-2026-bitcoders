import os, warnings, pandas as pd, numpy as np, psycopg2
warnings.filterwarnings("ignore")
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
E = dict(l.strip().removeprefix("export ").split("=",1) for l in open(os.environ["ENVF"]) if "=" in l)
c = psycopg2.connect(host=E["DBT_PG_HOST"], port=E["DBT_PG_PORT"], dbname=E["DBT_PG_DATABASE"], user=E["DBT_PG_USER"], password=E["DBT_PG_PASSWORD"]); c.set_session(readonly=True)
df = pd.read_sql("select * from silver.stg_call_center_interactions where random()<0.3", c).sort_values("interaction_date")
drop = ["interaction_id","customer_id","agent_id","transcript_id","process_date","interaction_date","mentioned_products"]
for tgt in ["was_resolved","requires_followup"]:
    feats = [x for x in df.columns if x not in drop+["was_escalated","was_resolved","requires_followup"]]
    k = int(len(df)*0.7); y = df[tgt].astype(int)
    print("==", tgt, "single-feature test AUC")
    res = {}
    for f in feats:
        X = df[[f]].copy()
        if not pd.api.types.is_numeric_dtype(X[f]) or X[f].dtype==bool: X[f] = X[f].astype(str).astype("category").cat.codes
        m = HistGradientBoostingClassifier(max_iter=60, random_state=0).fit(X.iloc[:k], y.iloc[:k]); res[f] = roc_auc_score(y.iloc[k:], m.predict_proba(X.iloc[k:])[:,1])
    for f, a in sorted(res.items(), key=lambda t: -t[1])[:6]: print(f"  {f:28s} {a:.3f}")
print(df.groupby("detected_sentiment").was_resolved.mean().round(3).to_dict())
print(df.groupby("interaction_type").was_resolved.mean().round(3).to_dict())
print(df.groupby("channel").was_resolved.mean().round(3).to_dict())
print(df.groupby("contact_reason").was_resolved.mean().round(3).to_dict())
