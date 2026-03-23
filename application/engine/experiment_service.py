# experiment_service.py   this is where the magic will happen!
from __future__ import annotations
from pathlib import Path
import json, time
from services.text_service import extract_lines
from services.ranking_service import RankingService
from services.normalization_service import normalize
from models import (ExperimentRow, ExperimentRequest, ExperimentSummary, CandidateIn,  RankRequest, JobIn, ExperimentCase)
from services.storage_service import load_job_state, save_job_state
from services.experiment_engine import run_experiment
from build_pdf.build_pdf_service import build_resume_pdf
from services.explanation_engine import analyze_explanations, build_explanation_records, job_factors

ranking_engine = RankingService()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_FOLDER_ROOT = PROJECT_ROOT / "data" / "experiments"

def score_experiment(request: ExperimentRequest):
    rows = []
    # core payload here:
    job_desc = JobIn(job_id=request.job_id, job_lines=(extract_lines(request.job_pdf_path)))
    cand_ins = [ CandidateIn(candidate_id=candidate_id, case_id=request.case_id, resume_lines=extract_lines(pdf_path))
        for (candidate_id, pdf_path) in request.candidates]

    for ranker in request.rankers:
        payload = RankRequest(run_id=request.run_id, ranker=ranker, job=job_desc,candidates=cand_ins)
        response = ranking_engine.rank(payload)
        rows.extend([  ExperimentRow( experiment_id=request.run_id, ranker=ranker, candidate_id=r.candidate_id, 
                                     case_id=request.case_id,  score=r.score, rank=r.rank)
            for r in response.ranking])
    results = ExperimentSummary(  job_id=request.job_id,  experiment_id=request.run_id,  name=request.case_id,
            rankers=request.rankers,  rows=rows )
    normalize(request.norm, results)  # uses job-specific 
    return results


def build_case_set(pos_req, iterations: int):
    job_id = pos_req["job_id"]
    requirements = pos_req.get("requirements", {})
    cases: list[ExperimentCase] = []
    case_count = 0

    def add_case(case_type: str, target: str | None, value: str | None, desc: str | None):
        nonlocal case_count
        if case_count > iterations: return
        cases.append(ExperimentCase(job_id=job_id, case_id=f"{case_count}_{case_type}",
            case_num=case_count, case_type=case_type, target=target, 
            value=value,  description=desc))
        case_count += 1

    #0 Validate
    add_case("validation", "none", "", "validation rebuild with no perturbation")

    # 1 Gender
    add_case ("gender", "name + ", "N/A", "Apply gender swap algorithm to resume")

    # 2 Location
    loc = pos_req.get("location")
    if loc:
        add_case ("location", "profile_location",loc,  f"Change resume location to {loc}")

    # 3 Education - bump up credentials
    education = requirements.get("education", {}) 
    if education.get("level", 0) > 0:
        edu = education.get("credential")
        add_case ("education", "education_items", edu, f"If resume highest education level is less than {edu}, add to resume")
    
    # 4 Job Position with title - create a matching job with same title
    title = pos_req.get ("title")
    if title:
        add_case ("position", "experience_items", title, f"Added {title} for 1 year with generic accountabilities")

    # 5 Skills – round-robin approach
    skill_buckets = [("tech",    "Technology Skills", requirements.get("tech", []) or []),
        ("tools",   "Skills",            requirements.get("tools", []) or []),
        ("vendors", "Skills",            requirements.get("vendors", []) or []),
        ("other",   "Other_Skills",      requirements.get("other_skills", []) or [])]
    for i in range(max(len(items) for _,_,items in skill_buckets)):  #iterate for longest bucket
        for case_type, target, items in skill_buckets:
            if i >= len(items):  continue
            if case_count >= iterations:  return cases
            item = items[i]
            add_case(case_type, target, json.dumps([item]), f"add 1 {case_type} item: {item}")
    return cases


def run_experiment_set(job_id: str, candidate_id:str | None = None):
    from job_service import run_baseline

    requirements_path = EXPERIMENT_FOLDER_ROOT / job_id / f"{job_id}_requirements.json"
    pos_req = json.loads(requirements_path.read_text(encoding="utf-8"))
    state = load_job_state(job_id)
    temp_dir = EXPERIMENT_FOLDER_ROOT / job_id / "temp_pdfs"
    [p.unlink() for p in temp_dir.iterdir() if p.is_file()]  # delete old temp files
    if candidate_id is None: state.experiments = []   # clean out old data
    else:
        state.experiments = [e for e in state.experiments if e.subject_candidate_id != candidate_id]  #delete only this candidate
    
    if state.baseline is None or state.status == "draft":
        run_baseline(job_id)
        state = load_job_state(job_id)

    state.status = "running"
    save_job_state(state)
    iterations = (state.params_current.num_iterations or 10)
    case_set = build_case_set(pos_req, iterations)
    main_experiment_loop( job_id=job_id, state=state, pos_req=pos_req, case_set=case_set, subject_candidate_id=candidate_id)

    state.status = "complete"
    save_job_state(state)
    return state


def main_experiment_loop(job_id, state,pos_req, case_set,subject_candidate_id: str | None = None):
    job_dir = EXPERIMENT_FOLDER_ROOT / job_id
    resume_jsons_dir = job_dir / "resume_jsons"
    resume_pdfs_dir = job_dir / "resume_pdfs"
    temp_pdfs_dir = job_dir / "temp_pdfs"
    register_path = job_dir / "case_register.csv"
    run_id = time.strftime("r%Y%m%d_%H%M")
    combined_case_id = "99_combined"
    rankers = state.params_current.rankers or state.baseline.rankers

    # helper to score
    def _score_subject_pdf(subject_cid: str, subject_pdf_path: Path, case_id: str, rankers):
        candidates_for_ranking = [(subject_cid, str(subject_pdf_path))]
        for cid in state.candidate_ids:
            if cid != subject_cid:
                candidates_for_ranking.append((cid, str(Path(resume_pdfs_dir) / f"{cid}.pdf")))
        req = ExperimentRequest( job_id=job_id, run_id=run_id, case_id=case_id, rankers=rankers,
            job_pdf_path=state.job.job_pdf_path,  candidates=candidates_for_ranking, norm=state.norm)
        result = score_experiment(req)
        result.rows = [r for r in result.rows if r.candidate_id == subject_cid]
        result.subject_candidate_id = subject_cid
        return result

    subject_ids = [subject_candidate_id] if subject_candidate_id else list(state.candidate_ids)
    for subject_cid in subject_ids:
        resume_json_path = resume_jsons_dir / f"{subject_cid}.json"
        resume_json = json.loads(resume_json_path.read_text(encoding="utf-8"))
        for case in case_set:
            subject_resume_json, _change_summary = run_experiment(case, pos_req, resume_json)
            subject_pdf_name = f"{subject_cid}__{case.case_id}"
            subject_pdf_path = build_resume_pdf(resume_json=subject_resume_json, file_name=subject_pdf_name,
                out_path=Path(temp_pdfs_dir), template_name="resume_1")
            result = _score_subject_pdf(subject_cid, Path(subject_pdf_path), case.case_id, rankers)
            result.params = state.params_current
            result.change_summary = _change_summary
            state.experiments.append(result)
            line = f"{subject_cid} {_change_summary}"
            for r in result.rows:
                line += f" | {r.ranker}: rank={r.rank}, score={r.norm_score:0.1f}"
            print(line)
    analysis = analyze_explanations(state, case_set, subject_candidate_id)
    top = analysis ["top_rank_cases"]
    combined_resumes = analysis.get("combined_resumes", {})
    combined_plans = analysis.get("combined_plans", {})
   
    #run combined
    for (ranker, subject_cid), combined_resume_json in combined_resumes.items():
        subject_pdf_name = f"{subject_cid}__{combined_case_id}"
        subject_pdf_path = build_resume_pdf( resume_json=combined_resume_json,
            file_name=subject_pdf_name,  out_path=Path(temp_pdfs_dir),  template_name="resume_1")
        result = _score_subject_pdf(subject_cid, Path(subject_pdf_path), combined_case_id, [ranker])
        result.params = state.params_current
        plan = combined_plans.get((ranker, subject_cid), {})
        result.change_summary = plan.get("change_summary", "combined")        
        state.experiments.append(result)        
        line = f"{subject_cid} combined top factors"
        for r in result.rows:
            line += f" | {r.ranker}: rank={r.rank}, score={r.norm_score:0.1f}"
        print(line)

    state.explanations = build_explanation_records(state, top)

    # write cases to register
    with register_path.open("a", encoding="utf-8", newline="\n") as f:
        for case in case_set:
            desc = (case.description or "").replace(",", ";")
            f.write(f"{case.case_id},{desc},{run_id}\n")
        f.write(f"{combined_case_id},combined: top factors,{run_id}\n")
    save_job_state(state) 
    

    return
    