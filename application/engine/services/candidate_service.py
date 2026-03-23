# candidate_service.py 
from pathlib import Path
from fastapi import UploadFile 
import shutil, time
from services.text_service import build_resume_json
from models import (AddCandidatesRequest, Candidate, AttachCandidateRequest, 
                    CandidateList, RemoveCandidateResponse)
from services.storage_service import (load_candidate_library, add_candidates_to_library,
                            load_job_state, save_job_state, load_job_index)
CANDIDATE_FOLDER = Path(__file__).resolve().parents[3] / "data" / "persistence" / "candidate_uploads"


def copy_upload(file, out_path):
    with out_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

def _add_candidate_service(paths: list[str] | None = None, files: list[UploadFile] | None = None): #need None as it's either or
    CANDIDATE_FOLDER.mkdir(parents=True, exist_ok=True)
    library = load_candidate_library()
    existing_ids = {c.candidate_id for c in library.candidates}
    sources, candidates = [], []
    if paths:  #old flow with paths
        for path in paths:
            src_path = Path(path)
            sources.append((src_path.name, (lambda out_path, src_path=src_path: shutil.copy2(src_path, out_path))))
    if files:  #new flow with upload
        for file in files:
            sources.append((Path(file.filename).name, (lambda out_path, file=file: copy_upload(file, out_path))))
    for filename, writer in sources:
        if filename == "" or not filename.lower().endswith(".pdf"): continue
        candidate_id = Path(filename).stem
        if candidate_id in existing_ids: continue
        out_path = CANDIDATE_FOLDER / filename
        writer(out_path)
        resume_json = build_resume_json(candidate_id, str(out_path))
        candidate_name = (resume_json.get("profile") or {}).get("name")
        candidates.append(Candidate(candidate_id=candidate_id, candidate_name=candidate_name, 
                                    resume_pdf_path=str(out_path),added_at=time.strftime("%Y-%m-%d %H:%M:%S")))
        existing_ids.add(candidate_id)
    return add_candidates_to_library(candidates)

def _count_jobs():
    counts = {}
    for job in load_job_index().jobs:
        for cid in load_job_state(job.job_id).candidate_ids:
            counts[cid] = counts.get(cid, 0) + 1
    return counts


# Candidate Library functions
def list_candidates():
    library = load_candidate_library()
    counts = _count_jobs()
    for c in library.candidates:
        c.jobs_count = counts.get(c.candidate_id, 0)
    return library

def add_candidates(request: AddCandidatesRequest):
    return _add_candidate_service(paths=request.resume_pdf_paths)

def add_uploaded_candidates(files: list[UploadFile]):
    return _add_candidate_service(files=files)


# Inside a Job functions
def list_job_candidates(job_id):
    state = load_job_state(job_id)
    library = load_candidate_library()
    this_job_candidates = set(state.candidate_ids)
    resolved = [c for c in library.candidates if c.candidate_id in this_job_candidates]
    return CandidateList(job_id=job_id, candidates=resolved)

def attach_candidates(job_id, request: AttachCandidateRequest):
    job_state = load_job_state(job_id)
    for cid in request.candidate_ids:
        if cid not in job_state.candidate_ids:
            job_state.candidate_ids.append(cid)
    job_state.status = "ready"
    save_job_state(job_state)
    return job_state

def remove_candidate(job_id, candidate_id):  # not implemented yet on my web FE
    state = load_job_state(job_id)
    state.candidate_ids = [cid for cid in state.candidate_ids if cid != candidate_id]
    state.status = "ready"
    if len(state.candidate_ids) == 0:
        state.status = "draft"
    save_job_state(state)
    return RemoveCandidateResponse(ok=True, candidate_id=candidate_id)

def attach_folder(job_id, folder_path):
    paths = [str(path) for path in sorted(Path(folder_path).glob("*.pdf"))]
    _add_candidate_service(paths=paths)
    state = load_job_state(job_id)
    job_ids = set()
    for cid in state.candidate_ids: job_ids.add(cid)
    library = load_candidate_library()
    library_ids = set()
    for c in library.candidates: library_ids.add(c.candidate_id)
    for path in sorted(Path(folder_path).glob("*.pdf")):
        candidate_id = path.stem
        if candidate_id in library_ids and candidate_id not in job_ids:
            attach_candidates(job_id, AttachCandidateRequest(candidate_ids=[candidate_id]))

    return load_job_state(job_id)

