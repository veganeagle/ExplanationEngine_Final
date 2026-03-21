# job_service.py
import time, json, shutil
from pathlib import Path
from fastapi import UploadFile

from models import (JobState, JobDescription, BaselineRequest, BaselineSummary, RankerName, BaselineRow, ExperimentParameters,
    SetParamsRequest, GetParamsResponse, RunExperimentRequest, RankRequest, JobIn, CandidateIn, ExperimentRequest)
from services.storage_service import add_job_to_index, save_job_state, load_job_state, load_candidate_library
from services.text_service import extract_lines, normalize_line, build_resume_json
from config import ALL_RANKERS, DEFAULT_ITERATIONS, DEFAULT_RANKER
from services.ranking_service import RankingService
from services.normalization_service import create_norm, normalize
from build_pdf.build_pdf_service import build_resume_pdf
from experiment_service import score_experiment
from services.position_analyzer import analyze

ranking_engine = RankingService()
JOB_FOLDER = Path(__file__).resolve().parents[2] / "data" / "persistence" / "job_uploads"

def create_uploaded_job(file, description: str = ""):
    JOB_FOLDER.mkdir(parents=True, exist_ok=True)
    filename = Path(file.filename or "").name
    if filename == "" or not filename.lower().endswith(".pdf"):
        raise ValueError("Job Description file must be a PDF")
    job_id = Path(filename).stem
    out_path = JOB_FOLDER / filename
    with out_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    job = JobDescription(job_id=job_id, job_pdf_path=str(out_path), description=description)
    return create_job(job)

def create_job(job: JobDescription):
    add_job_to_index(job)
    state = JobState(job=job, status="running", candidate_ids=[], baseline=None, experiments=[],
                     params_current=ExperimentParameters(rankers=DEFAULT_RANKER, num_iterations=DEFAULT_ITERATIONS))
    save_job_state(state)
    
    #make folders and stuff
    experiments_root = Path(__file__).resolve().parents[2] / "data" / "experiments"
    job_dir = experiments_root / job.job_id
    resume_jsons_dir = job_dir / "resume_jsons"
    resume_pdfs_dir = job_dir / "resume_pdfs"
    temp_pdfs = job_dir/ "temp_pdfs"
    job_dir.mkdir(parents=True, exist_ok=True)
    resume_jsons_dir.mkdir(parents=True, exist_ok=True)
    resume_pdfs_dir.mkdir(parents=True, exist_ok=True)
    temp_pdfs.mkdir(parents=True, exist_ok=True)

    # Extract job_lines and key position requirements
    job_lines = extract_lines(state.job.job_pdf_path)
    requirements = analyze(job.job_id, job_lines)  
    state.status = "ready"
    save_job_state(state)
    req_path = job_dir / f"{job.job_id}_requirements.json"
    req_path.write_text(json.dumps(requirements, ensure_ascii=False, indent=2), encoding="utf-8")

    return state


def set_params(job_id: str, request: SetParamsRequest):
    state = load_job_state(job_id)
    state.params_current = request.params
    save_job_state(state)
    return GetParamsResponse(job_id=job_id, params=state.params_current)

def get_params(job_id: str):
    state = load_job_state(job_id)
    return GetParamsResponse(job_id=job_id, params=state.params_current, rankers = ALL_RANKERS)


def baseline_payload(state: JobState, run_id: str, ranker: RankerName):
    job_lines = extract_lines(state.job.job_pdf_path)
    library = load_candidate_library()
    cand_set = set(state.candidate_ids)
    candidates = [c for c in library.candidates if c.candidate_id in cand_set]
    # parse resumes using text_service.
    cand_ins = [CandidateIn(candidate_id=c.candidate_id, case_id="base", resume_lines=extract_lines(c.resume_pdf_path)) for c in candidates]
    return RankRequest(run_id=run_id, ranker=ranker, job=JobIn(job_id=state.job.job_id, job_lines=job_lines), candidates=cand_ins)


def run_baseline(job_id: str, request: BaselineRequest):
    state = load_job_state(job_id)
    state.baseline = None    # reset
    state.norm, state.experiments, state.explanations = None,[],[]
    rankers = state.params_current.rankers
    run_id = time.strftime("baseline_%Y%m%d_%H%M")
    rows =[]
    for ranker in rankers:
        response = ranking_engine.rank(baseline_payload(state=state, run_id=run_id, ranker=ranker ))
        rows.extend([BaselineRow(job_id=job_id, ranker=ranker, candidate_id=r.candidate_id, score=r.score, 
                                 rank=r.rank) for r in response.ranking])

    state.baseline = BaselineSummary(job_id=job_id, rankers=rankers, rows=rows)
    state.norm = create_norm(state.baseline, job_id= job_id, run_id=run_id)
    normalize(state.norm, state.baseline)
    _print_baseline (state.baseline)
    state.status = "baselined"
    save_job_state(state)
    print (f"Initializing folders and base files for {job_id}")
    initialize_experiment(job_id)
    return state


def get_baseline(job_id: str):
    state = load_job_state(job_id)
    return state.baseline

def _print_baseline(baseline: BaselineSummary):  #print to console, so i can monitor
    rankers = baseline.rankers
    b_d = {} # baseline as dict of dict
    for row in baseline.rows:
        score = row.norm_score if row.norm_score is not None else row.score
        b_d.setdefault(row.candidate_id, {})[row.ranker] = (row.rank, score)
    cid_w = max(len("candidate_id"), *(len(cid) for cid in b_d))
    print(f"{'candidate_id':<{cid_w}} " + " ".join(f"{m}_rank score".ljust(14) for m in rankers))
    for cid in sorted(b_d):
        d = b_d[cid]
        print(f"{cid:<{cid_w}} " + "  ".join(f"{d.get(m, ('',''))[0]:>4}    {d.get(m, ('',''))[1]:>7.2f}" for m in rankers))
    return


def initialize_experiment(job_id: str):
    state = load_job_state(job_id)  
    state.experiments = []
    library = load_candidate_library()
    cand_set = set(state.candidate_ids)
    resume_paths = {c.candidate_id: c.resume_pdf_path for c in library.candidates if c.candidate_id in cand_set}
    experiments_root = Path(__file__).resolve().parents[2] / "data" / "experiments"
    job_dir = experiments_root / job_id
    resume_jsons_dir = job_dir / "resume_jsons"
    resume_pdfs_dir = job_dir / "resume_pdfs"
    temp_pdfs = job_dir/ "temp_pdfs"
    init_time = time.strftime("%Y%m%d_%H%M")

    register_path = job_dir / "case_register.csv"  #this is the test case register
    if not register_path.exists():
        register_path.write_text("case_id,case_description,created_at_utc\n", encoding="utf-8")
        with register_path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(f"0, initial parser validation,{init_time}\n")

    # build raw resume_jsons into resume_jsons_dir (never modified directly)    
    for candidate_id in state.candidate_ids:
        resume_json = build_resume_json(candidate_id, pdf_path=resume_paths[candidate_id])
        out_path = resume_jsons_dir / f"{candidate_id}.json"
        out_path.write_text(json.dumps(resume_json, indent=2), encoding="utf-8")
        build_resume_pdf(resume_json=resume_json, file_name=candidate_id, out_path=Path(resume_pdfs_dir), template_name="resume_1")

    # run case 0 (round-trip PDFs) scoring
    req = ExperimentRequest( job_id=job_id, run_id=(f"r{init_time}"),case_id="0_validation", rankers=state.baseline.rankers, job_pdf_path=state.job.job_pdf_path,
        candidates=[(cid, str(Path(resume_pdfs_dir) / f"{cid}.pdf")) for cid in state.candidate_ids], norm=state.norm)
    case0_results = score_experiment(req)
    state.experiments.append(case0_results)
    save_job_state(state)

    # validate to ensure resumes are useable
    validate_resumes (job_id=job_id, case0_results=case0_results)
    return { "job_id": job_id,  "job_dir": str(job_dir),  "resume_jsons_dir": str(resume_jsons_dir),
        "resume_pdfs_dir": str(resume_pdfs_dir),  "case_register_path": str(register_path)}

def validate_resumes(job_id: str, case0_results): # no longer using this really, just on console
    state = load_job_state(job_id)
    ranker_min = {item.ranker: item.raw_min for item in state.norm.items}
    ranker_max = {item.ranker: item.raw_max for item in state.norm.items}

    # dict by candidate and row
    base_map = {(r.candidate_id, r.ranker): r for r in state.baseline.rows}

    for row in case0_results.rows:
        baseline_score = base_map[(row.candidate_id, row.ranker)].score
        case0_score = row.score
        denominator = (ranker_max[row.ranker] - ranker_min[row.ranker])
        variance = None if denominator == 0 else 100 * abs(case0_score - baseline_score) / denominator
        v = "None" if variance is None else f"{variance:0.3f}"
        print(f"{row.candidate_id}, {row.ranker}, {baseline_score}, {case0_score}, {v}")
    return

