from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse  # only for testing
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Optional
from pathlib import Path
from models import ( RankRequest, RankResponse, JobDescription, JobIndex, JobState,
    BaselineRequest, BaselineSummary, SetParamsRequest, GetParamsResponse, DeleteJobResponse,
    CandidateIndex, CandidateList, AttachCandidateRequest,RemoveCandidateResponse, ExplanationRecord,
    DeleteCandidateResponse, RunExperimentRequest, AddCandidatesRequest, AttachFolderRequest)

# Service Methods
from services.ranking_service import RankingService
from services.storage_service import (load_job_index, delete_job_file_if_exists, load_job_requirements, load_candidate_resume, 
    delete_candidate, load_job_state, remove_job_from_index)
from job_service import create_job, run_baseline, get_params, set_params, get_baseline, create_uploaded_job
from services.candidate_service import (list_candidates, add_candidates, attach_candidates, list_job_candidates, 
                               remove_candidate, attach_folder, add_uploaded_candidates)
from experiment_service import run_experiment_set
from services.ui_service import build_summary
from services.explanation_engine import top_rank_cases

app = FastAPI(title="Ranking Engine", version="1.0")

# Next.js front end support for Raj
app.add_middleware( CORSMiddleware, allow_origins=["http://localhost:3000"],  
    allow_credentials=True,  allow_methods=["*"],  allow_headers=["*"])

WEB_DIR = (Path(__file__).resolve().parents[1] / "web_test")
app.mount("/static", StaticFiles(directory=str(WEB_DIR), html=True), name="static")
ranker = RankingService()


# "ep" = "endpoint" to get rid of conflicts
@app.post("/rank", response_model=RankResponse)
def rank_ep(request: RankRequest):
    return ranker.rank(request)

@app.get("/jobs", response_model=JobIndex)
def get_jobs_ep():
    return load_job_index()

@app.get("/candidates", response_model=CandidateIndex)
def list_candidates_ep():
    return list_candidates()

@app.post("/candidates/upload", response_model=CandidateIndex)
def upload_candidates_ep(files: list[UploadFile] = File(...)):
    return add_uploaded_candidates(files)

@app.post("/candidates", response_model=CandidateIndex)
def add_candidates_ep(request: AddCandidatesRequest):
    return add_candidates(request)

@app.post("/jobs/{job_id}/attach-folder", response_model=JobState)
def attach_folder_ep(job_id: str, req: AttachFolderRequest):
    return attach_folder(job_id, req.folder_path)

@app.get("/jobs/{job_id}/candidates/{candidate_id}/resume")
def get_candidate_resume_ep(job_id: str, candidate_id: str):
    return load_candidate_resume(job_id, candidate_id)

@app.post("/jobs", response_model=JobState)
def create__new_job_ep(request: JobDescription):
    return create_job(request)

#new
@app.post("/jobs/upload", response_model=JobState)
def upload_job_ep(file: UploadFile = File(...), description: str = ""):
    return create_uploaded_job(file, description)

@app.get("/jobs/{job_id}", response_model=JobState)
def get_job_ep(job_id: str):
    return load_job_state(job_id)

@app.get("/jobs/{job_id}/requirements")
def get_job_requirements_ep(job_id: str):
    return load_job_requirements(job_id)

@app.post("/jobs/{job_id}/candidates", response_model=JobState)
def attach_candidates_ep(job_id: str, request: AttachCandidateRequest):
    return attach_candidates(job_id, request)

@app.get("/jobs/{job_id}/candidates", response_model=CandidateList)
def list_job_candidates_ep(job_id: str):
    return list_job_candidates(job_id)

@app.delete("/jobs/{job_id}/candidates/{candidate_id}", response_model=RemoveCandidateResponse)
def remove_candidate_ep(job_id: str, candidate_id: str):
    return remove_candidate(job_id, candidate_id)

@app.delete("/candidates/{candidate_id}", response_model=DeleteCandidateResponse)
def delete_candidate_ep(candidate_id: str):
    delete_candidate(candidate_id)  
    return DeleteCandidateResponse(ok=True, candidate_id=candidate_id)

@app.post("/jobs/{job_id}/baseline/run", response_model=JobState)
def run_baseline_ep(job_id: str, request: BaselineRequest):
    return run_baseline(job_id, request)

@app.get("/jobs/{job_id}/baseline", response_model=BaselineSummary)
def get_baseline_ep(job_id: str):
    return get_baseline(job_id)

@app.get("/jobs/{job_id}/params", response_model=GetParamsResponse)
def get_params_ep(job_id: str):
    return get_params(job_id)

@app.put("/jobs/{job_id}/params", response_model=GetParamsResponse)
def set_params_ep(job_id: str, request: SetParamsRequest):
    return set_params(job_id, request)

@app.post("/jobs/{job_id}/experiments/run", response_model=JobState)
def run_experiment_ep(job_id: str, request: Optional [RunExperimentRequest]=None):
    candidate_id = None if request is None else request.candidate_id
    return run_experiment_set(job_id, candidate_id=candidate_id)

@app.get("/jobs/{job_id}/summary")  # this is a results summary
def get_job_summary_ep(job_id: str):
    state = load_job_state(job_id)
    return build_summary(state)

@app.delete("/jobs/{job_id}", response_model=DeleteJobResponse)
def delete_job_ep(job_id: str):
    remove_job_from_index(job_id)
    delete_job_file_if_exists(job_id)
    return DeleteJobResponse(ok = True, deleted_job_id = job_id)

@app.get("/jobs/{job_id}/explanations")
def get_job_explanations_ep(job_id: str):
    state = load_job_state(job_id)
    return { "explanations": state.explanations, "top_rank_cases": top_rank_cases(state)}


# Gus's Front end - web stuff
@app.get("/", response_class=HTMLResponse)
def index():
    index_path = Path(__file__).resolve().parents[1] / "web_test" / "index.html"
    return index_path.read_text(encoding="utf-8")

@app.get("/candidates.html", response_class=HTMLResponse)
def candidates_page():
    p = Path(__file__).resolve().parents[1] / "web_test" / "candidates.html"
    return p.read_text(encoding="utf-8")

@app.get("/job.html", response_class=HTMLResponse)
def job_page():
    p = Path(__file__).resolve().parents[1] / "web_test" / "job.html"
    return p.read_text(encoding="utf-8")

@app.get("/explanations.html", response_class=HTMLResponse)  # no longer used
def explanations_page():
    p = Path(__file__).resolve().parents[1] / "web_test" / "explanations.html"
    return p.read_text(encoding="utf-8")

@app.get("/candidate_results.html", response_class=HTMLResponse)
def candidate_results_page():
    p = Path(__file__).resolve().parents[1] / "web_test" / "candidate_results.html"
    return p.read_text(encoding="utf-8")

