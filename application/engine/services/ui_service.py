# generate a front-end friendly data structure.
from __future__ import annotations
from typing import List
from models import JobState, RankerName

def build_summary(state: JobState):
    model_list: List[RankerName] = []
    if state.baseline and state.baseline.rankers:
        model_list = list(state.baseline.rankers)
    candidate_ids = list(state.candidate_ids or [])
    baseline = {}
    if state.baseline:
        for r in state.baseline.rows:
            baseline.setdefault(r.ranker,{})[r.candidate_id] = {"rank":r.rank,"norm": r.norm_score}
    cases = {}
    for summary in state.experiments or []:
        for r in (summary.rows or []):
            case_id = r.case_id
            cid = r.candidate_id
            ranker = r.ranker
            cases.setdefault(case_id,{}).setdefault(ranker,{})[cid] = {"rank": r.rank, "norm": r.norm_score}

    experiment_case_ids = list(cases.keys())
    experiment_case_ids.sort(key=lambda s: (int(s.split("_", 1)[0]) if s.split("_", 1)[0].isdigit() else 999999, s))    
    model_tables = {}

    for ranker in model_list:
        columns = ["candidate_id", "baseline_norm", "baseline_rank"]
        for c in experiment_case_ids:
            columns += [f"{c}_rank", f"{c}_delta_norm"]
        rows = []
        for cid in candidate_ids:
            b = baseline.get(ranker, {}).get(cid)  
            b_norm = None if not b else b.get("norm")
            b_rank = None if not b else b.get("rank")
            v = cases.get("0_validation", {}).get(ranker, {}).get(cid)
            v_norm = None if not v else v.get("norm")
            row = {  "candidate_id": cid, "baseline_norm": b_norm,  "baseline_rank": b_rank}
            for case in experiment_case_ids:
                e = cases.get(case, {}).get(ranker, {}).get(cid)
                e_norm = None if not e else e.get("norm")
                e_rank = None if not e else e.get("rank")
                prefix = case
                row[f"{prefix}_rank"] = e_rank
                if case =="0_validation":
                    row[f"{prefix}_delta_norm"] = (
                        None if (b_norm is None or e_norm is None) else (e_norm - b_norm))
                else:
                    row[f"{prefix}_delta_norm"] = (
                        None if (v_norm is None or e_norm is None) else (e_norm - v_norm))
            rows.append(row)
        model_tables[ranker] = {"table_id": f"model_{ranker}",  "ranker": ranker,
            "row_key": "candidate_id",  "columns": columns,  "rows": rows}

    return {"ui": { "model_list": model_list, "case_ids": experiment_case_ids,  "model_tables": model_tables}}
