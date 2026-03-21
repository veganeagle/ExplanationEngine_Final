# normalization_service.py
from __future__ import annotations
from models import BaselineSummary, ExperimentSummary, NormalizerVals, NormModel
from config import NORM_MIN, NORM_MAX

def create_norm(baseline: BaselineSummary, job_id: str, run_id: str):
    items: list[NormModel] = []
    for ranker in baseline.rankers:
        raw_min, raw_max = None, None
        for row in baseline.rows:
            if row.ranker != ranker: continue
            s = row.score
            raw_min = s if raw_min is None or s < raw_min else raw_min
            raw_max = s if raw_max is None or s > raw_max else raw_max

        # special case - one score only, or all scored the same (llm problem)
        if raw_max == raw_min:
            coef = ((NORM_MIN + NORM_MAX) / 2.0) / raw_max if raw_max !=0 else 100
            bias = 0.0            
        else:  # standard case
            coef = (NORM_MAX - NORM_MIN) / (raw_max - raw_min)
            bias = NORM_MIN - (coef * raw_min)
        items.append(NormModel(ranker=ranker, bias=bias, coef=coef, raw_min=raw_min, raw_max=raw_max))
    return NormalizerVals(job_id=job_id, run_id=run_id, items=items)


def normalize(norm: NormalizerVals, summary: BaselineSummary | ExperimentSummary):
    p = {i.ranker: i for i in norm.items}  # normalizer dictionary
    for row in summary.rows:
        norm_model = p[row.ranker]
        row.norm_score = round((row.score * norm_model.coef) + norm_model.bias, 2)
