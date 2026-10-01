import os, warnings, numpy as np, pandas as pd, psycopg2
warnings.filterwarnings("ignore")
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
E = dict(l.strip().removeprefix("export ").split("=",1) for l in open(os.environ["ENVF"]) if "=" in l)
c = psycopg2.connect(host=E["DBT_PG_HOST"], port=E["DBT_PG_PORT"], dbname=E["DBT_PG_DATABASE"], user=E["DBT_PG_USER"], password=E["DBT_PG_PASSWORD"]); c.set_session(readonly=True)
def load(sql): return pd.read_sql(sql, c)
def scan(name, df, time_col, targets, drop=()):
    df = df.sort_values(time_col).reset_index(drop=True); cut = int(len(df)*0.7)
    for tgt, ydef in targets.items():
        try: y = ydef(df)
        except AttributeError: print(f'{name:12s} {tgt:28s} column missing'); continue
        ok = y.notna(); d = df[ok]; yy = y[ok].astype(int)
        if yy.nunique() < 2 or yy.sum() < 50: print(f"{name:12s} {tgt:28s} skipped (n_pos={int(yy.sum())})"); continue
        X = d.drop(columns=[time_col, *drop, *[t for t in targets if t in d.columns]], errors="ignore").copy()
        for col in X.columns:
            if not pd.api.types.is_numeric_dtype(X[col]) or X[col].dtype == bool:
                X[col] = X[col].astype(str).astype("category").cat.codes
        k = int(len(d)*0.7); catcols = [i for i, col in enumerate(X.columns) if str(X[col].dtype) == "int8" or str(X[col].dtype) == "int16" or str(X[col].dtype)=="int32" and X[col].nunique()<60]
        m = HistGradientBoostingClassifier(max_iter=150, random_state=0).fit(X.iloc[:k], yy.iloc[:k])
        auc = roc_auc_score(yy.iloc[k:], m.predict_proba(X.iloc[k:])[:,1])
        print(f"{name:12s} {tgt:28s} n={len(d):7d} rate={yy.mean():.3f} AUC={auc:.3f}")
cm = load("""select c.*, cu.country customer_country, cu.segment, cu.credit_score, cu.customer_status from silver.stg_complaints c join silver.stg_customers cu using (customer_id)""")
cm = cm.drop(columns=["complaint_id","customer_id","description","open_comments","affected_product_id","origin_interaction_id","assigned_agent_id","related_branch_id"], errors="ignore")
tc = [x for x in ["creation_date"] if x in cm.columns][0]
scan("complaints", cm, tc, {
 "sla_breached": lambda d: d.sla_breached.map({True:1,False:0}) if d.sla_breached.dtype==bool else d.sla_breached.astype(float),
 "requires_followup": lambda d: d.requires_followup.astype(float),
 "is_repeat_complainer": lambda d: d.is_repeat_complainer.astype(float),
 "compensation_granted>0": lambda d: (pd.to_numeric(d.compensation_granted, errors="coerce")>0).astype(float).where(d.compensation_granted.notna()),
 "resolved_late(>median)": lambda d: (pd.to_numeric(d.resolution_days, errors="coerce")>pd.to_numeric(d.resolution_days, errors="coerce").median()).astype(float).where(d.resolution_days.notna()),
}, drop=["resolution_days","resolution_date","closing_date","first_response_date","assignment_date","resolution","status","resolution_satisfaction","sla_breached","requires_followup","is_repeat_complainer","compensation_granted"])
cc = load("""select i.*, cu.country customer_country, cu.segment, cu.credit_score from silver.stg_call_center_interactions i join silver.stg_customers cu using (customer_id)""")
cc = cc.drop(columns=["interaction_id","customer_id","agent_id","transcript_id","process_date","mentioned_products"], errors="ignore")
scan("callcenter", cc, "interaction_date", {
 "was_escalated": lambda d: d.was_escalated.astype(float),
 "was_resolved": lambda d: d.was_resolved.astype(float),
 "requires_followup": lambda d: d.requires_followup.astype(float),
 "long_call(>median)": lambda d: (d.duration_seconds>d.duration_seconds.median()).astype(float),
}, drop=["was_escalated","was_resolved","requires_followup","duration_seconds","wait_time_seconds"])
sv = load("""select s.*, cu.country customer_country, cu.segment from silver.stg_satisfaction_surveys s left join silver.stg_customers cu using (customer_id)""")
sv = sv.drop(columns=["survey_id","customer_id","interaction_id","complaint_id","open_comments"], errors="ignore")
scan("surveys", sv, "survey_date", {"low_score(<=3)": lambda d: (d.main_score<=3).astype(float).where(d.main_score.notna())}, drop=["main_score","nps_category"])
