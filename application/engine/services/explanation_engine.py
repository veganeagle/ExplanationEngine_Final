from __future__ import annotations

import json
from pathlib import Path
from services.experiment_engine import apply_combined_case
from models import (JobState, RankerName, ExplanationFactor, ExplanationRecord, 
                    ExperimentCase, JobFactors, JobFactorsByRanker, JobFactorCase)
from config import NORM_MAX 

COMBINED_CASE_ID = "99_combined"
VALIDATION_CASE_ID = "0_validation"
MAX_REASONS = 6
MIN_CONTRIB = 1.0

def build_explanations(state: JobState):
    return {
        "top_rank_cases": top_rank_cases(state),
        "explanations": getattr(state, "explanations", []) or [],
    }

def analyze_explanations(state, case_set, subject_candidate_id = None):
    job_id = state.job.job_id
    exp_root = Path(__file__).resolve().parents[3] / "data" / "experiments" / job_id
    resume_dir = exp_root / "resume_jsons"
    pos_req_path = exp_root / f"{job_id}_requirements.json"  
    pos_req = json.loads(pos_req_path.read_text(encoding="utf-8"))  
    case_by_id = {c.case_id: c for c in case_set}
    combined_resumes = {}   # ranker x candidate -> super-resume
    combined_plans = {}
    top = top_rank_cases(state, subject_candidate_id)   # call top rank case function
    
    for ranker, cand_map in top.items():
        for candidate_id, items in cand_map.items():
            if not items: continue
            resume_path = resume_dir / f"{candidate_id}.json"
            resume_json = json.loads(resume_path.read_text(encoding="utf-8"))
            components = []
            for it in items:
                case_id = it["case_id"]
                c = case_by_id[case_id]  
                components.append(c)
            combined_resume, combined_sum = apply_combined_case(components, pos_req, resume_json)
            combined_resumes[(ranker, candidate_id)] = combined_resume
            combined_plans[(ranker, candidate_id)] = {"case_ids":[c.case_id for c in components],
                                                      "change_summary": combined_sum.get("change_summary", "combined")}
    
    return {"top_rank_cases": top, "combined_resumes": combined_resumes,  "combined_plans": combined_plans}
    
def top_rank_cases(state: JobState, subject_candidate_id= None):
    baseline_norm = {}
    baseline_rank = {}
    for r in state.baseline.rows:
        baseline_norm[(r.ranker, r.candidate_id)] = r.norm_score
        baseline_rank[(r.ranker, r.candidate_id)] = r.rank
    validation_norm = {}
    for exp in state.experiments:
        if subject_candidate_id and exp.subject_candidate_id != subject_candidate_id:
            continue
        for r in exp.rows:
            if r.case_id == VALIDATION_CASE_ID:
                validation_norm[(r.ranker, r.candidate_id)] = r.norm_score  
    best_cases = {}
    for exp in state.experiments:
        if subject_candidate_id and exp.subject_candidate_id != subject_candidate_id: 
            continue
        change_summary = exp.change_summary
        for r in exp.rows:
            if r.case_id in (VALIDATION_CASE_ID,COMBINED_CASE_ID): continue
            ranker = r.ranker
            candidate_id = r.candidate_id
            b_norm = baseline_norm[(ranker, candidate_id)]
            b_rank = baseline_rank[(ranker, candidate_id)]
            rank_lift = b_rank - r.rank
            v_norm = validation_norm.get((ranker, candidate_id), b_norm)
            d_norm = r.norm_score - v_norm
            if d_norm <= 0: continue   #no or negative impact of change
            case_type = (r.case_id.split("_", 1)[1] if "_" in r.case_id else r.case_id)
            key = (ranker, candidate_id, r.case_id)
            cur = best_cases.get(key)
            if cur is None or abs(d_norm) > abs(cur["delta_norm"]) or (abs(d_norm) == abs(cur["delta_norm"]) and abs(rank_lift) > abs(cur["delta_rank"])):
                best_cases[key] = { "case_type": case_type,  "case_id": r.case_id, "change_summary": change_summary,  "baseline_norm": b_norm, "validation_norm": v_norm,
                    "experiment_norm": r.norm_score, "delta_norm": d_norm,  "baseline_rank": b_rank,  "experiment_rank": r.rank, "delta_rank": rank_lift}
    out = {}

#now using validation norm
    for (ranker, candidate_id, case_id), item in best_cases.items():
        out.setdefault(ranker, {}).setdefault(candidate_id, []).append(item)
    for ranker, cand_map in out.items():
        for candidate_id, items in cand_map.items():
            items.sort(key=lambda x: (abs(x["delta_norm"]), abs(x["delta_norm"])), reverse=True)
            selected = []
            validation_norm0 = float(items[0]["validation_norm"])
            estimated_norm = validation_norm0
            for it in items:
                delta = float(it["delta_norm"])
                if estimated_norm >= NORM_MAX or len(selected) >= MAX_REASONS or delta <MIN_CONTRIB:  break
                selected.append(it)
                estimated_norm += float(it["delta_norm"])
            cand_map[candidate_id] = selected
    return out

def build_explanation_records(state, top):
    explanations: list[ExplanationRecord] = []
    combined = {}   # build combined dict
    for exp in state.experiments:
        for r in exp.rows:
            if r.case_id == COMBINED_CASE_ID:
                combined[(r.ranker, r.candidate_id)] = {
                "row": r, "full_reason": exp.change_summary or "combined"}
    for ranker, cand_map in top.items():
        for candidate_id, items in cand_map.items():
            if not items:  continue
            baseline_rank = items[0]["baseline_rank"]
            baseline_norm = items[0]["baseline_norm"]
            factors: list[ExplanationFactor] = []
            top_score = 0.0
            for it in items:
                case_id = it["case_id"]
                ctype = (case_id.split("_", 1)[1] if "_" in case_id else case_id)
                desc_raw = it.get("change_summary") or it.get("description") or it.get("case_id") or ""
                description = desc_raw.split("[", 1)[0].strip()         
                dn = float (it["delta_norm"])
                if dn > top_score: top_score =dn
                factors.append(ExplanationFactor(case_id=case_id, case_type=ctype, short_reason=description,
                    full_reason= desc_raw,delta_norm=dn, delta_rank=it["delta_rank"] ))
            validation_norm = items[0].get("validation_norm", baseline_norm)
            combined_item = combined.get((ranker, candidate_id))
            combined_row = combined_item["row"] if combined_item is not None else None
            if combined_item is not None:
                full = combined_item["full_reason"]
                short = full.split("[", 1)[0].strip()
                factors.append(ExplanationFactor(case_id=COMBINED_CASE_ID, case_type="combined", short_reason=short,
                    full_reason=full, delta_norm=(combined_row.norm_score - validation_norm), delta_rank=(baseline_rank - combined_row.rank)))

            record = ExplanationRecord(ranker=ranker, candidate_id=candidate_id,
                baseline_rank=baseline_rank, baseline_norm=baseline_norm, factors=factors)

            gap = max(0.0, NORM_MAX - float(baseline_norm))
            record.explanation_gap = gap
            record.top_factor_explains = 0.0
            if gap > 0:
                record.top_factor_explains = min (1.0, top_score/gap)
                if combined_row is not None:
                    record.combined_factor_explains = min (1.0, float((combined_row.norm_score - validation_norm) /gap))
                else: record.combined_factor_explains = 0.0
                
            explanations.append(record)
    seen = {(e.ranker, e.candidate_id) for e in explanations}
    for r in state.baseline.rows:
        key = (r.ranker, r.candidate_id)
        if key in seen: continue
        explanations.append( ExplanationRecord(
                ranker=r.ranker, candidate_id=r.candidate_id,  baseline_rank=r.rank,
                baseline_norm=r.norm_score, factors=[]))
    explanations.sort(key=lambda e: (e.ranker or "", e.baseline_rank if e.baseline_rank is not None else 999999))
            
    return explanations


# new - job analyzer
def job_factors(state):
    def make_bucket(case_id):
        return {"case_id": case_id, "description": None, "score_lift_sum": 0.0,
            "applicant_ids_lift": set(), "top1_count": 0,"topN_count": 0}

    by_ranker: dict[str, dict[str, dict]] = {}

    for exp in state.experiments:
        for row in exp.rows:
            ranker_map = by_ranker.setdefault(row.ranker, {})
            case_id = row.case_id
            if case_id in (VALIDATION_CASE_ID, COMBINED_CASE_ID):
                continue
            ranker_map.setdefault(case_id, make_bucket(case_id))

    for rec in state.explanations or []:
        ranker_map = by_ranker.setdefault(rec.ranker, {})
        factors = [f for f in rec.factors if f.case_id != COMBINED_CASE_ID]
        if not factors: continue
        top_case_id = max(factors, key=lambda f: f.delta_norm).case_id
        for f in factors:
            bucket = ranker_map.setdefault(f.case_id, make_bucket(f.case_id))
            if bucket["description"] is None:
                desc = f.full_reason or f.short_reason or "unknown"
                if f.case_type in ("other", "tech", "tools", "vendors"):
                    lb = desc.find("[")
                    rb = desc.find("]", lb + 1)
                    desc = f"added Skill: {desc[lb+1:rb].strip()}"
                bucket["description"] = desc
            bucket["score_lift_sum"] += float(f.delta_norm)
            bucket["applicant_ids_lift"].add(rec.candidate_id)
            bucket["topN_count"] += 1
            if f.case_id == top_case_id:  bucket["top1_count"] += 1

    rankers: list[JobFactorsByRanker] = []
    total_candidates = len(state.candidate_ids) or 1
    for ranker, case_map in by_ranker.items():
        cases = [JobFactorCase(case_id=item["case_id"], description=item["description"], avg_score_lift = item["score_lift_sum"] / total_candidates,
                               applicant_count_lift=len(item["applicant_ids_lift"]), top1_count=item["top1_count"], topN_count=item["topN_count"])
                 for item in case_map.values()]
        rankers.append(JobFactorsByRanker(ranker=ranker, cases=cases))

    rankers.sort(key=lambda r: r.ranker)
    return JobFactors(job_id=state.job.job_id, rankers=rankers)