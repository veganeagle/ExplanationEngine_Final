# storage_service.py
import json
from pathlib import Path
from models import JobDescription, JobIndex, Candidate, CandidateIndex, JobState

STORAGE_DIR = Path(__file__).resolve().parents[3] / "data" / "persistence"
JOB_INDEX_PATH = STORAGE_DIR / "index.json"
CANDIDATE_LIBRARY_PATH = STORAGE_DIR / "candidates.json"
JOB_DIR =  Path(__file__).resolve().parents[3] / "data" / "experiments"

# Job Index functions
def load_job_index():
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    if not JOB_INDEX_PATH.exists():
        return JobIndex(jobs=[])
    with open(JOB_INDEX_PATH, "r", encoding="utf-8") as f:
        return JobIndex.model_validate(json.load(f))

def save_job_index(index: JobIndex):
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    with open(JOB_INDEX_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(index.model_dump_json(indent=2))

def add_job_to_index(job: JobDescription):
    index = load_job_index()
    index.jobs.append(job)
    save_job_index(index)
    return index

def remove_job_from_index(job_id: str) -> bool:
    index = load_job_index()
    index.jobs = [job for job in index.jobs if job.job_id != job_id]
    save_job_index(index)
    return True  # no False response possible here yet... maybe later

def delete_job_file_if_exists(job_id:str):
    p = STORAGE_DIR / f"{job_id}.json"
    if p.exists():  p.unlink()


# Candidate Library Functions
def load_candidate_library():
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    if not CANDIDATE_LIBRARY_PATH.exists():
        return CandidateIndex(candidates=[])
    with open(CANDIDATE_LIBRARY_PATH, "r", encoding="utf-8") as f:
        return CandidateIndex.model_validate(json.load(f))

def save_candidate_library(library: CandidateIndex):
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CANDIDATE_LIBRARY_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(library.model_dump_json(indent=2))

def add_candidates_to_library(candidates: list[Candidate]):
    library = load_candidate_library()
    library.candidates.extend(candidates)
    save_candidate_library(library)
    return library

def delete_candidate(candidate_id: str):
    library = load_candidate_library()
    library.candidates = [c for c in library.candidates if c.candidate_id != candidate_id]
    save_candidate_library(library)
    return True  # no False response possible here yet... maybe later

def load_candidate_resume(job_id: str, candidate_id: str) -> dict:
    p = (JOB_DIR / job_id / "resume_jsons" / f"{candidate_id}.json")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

# Job State Functions
def load_job_state(job_id: str):
    p = STORAGE_DIR / f"{job_id}.json"
    with open(p, "r", encoding="utf-8") as f:
        return JobState.model_validate(json.load(f))

def save_job_state(state: JobState) -> None:
    p = STORAGE_DIR / f"{state.job.job_id}.json"
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(state.model_dump_json(indent=2))

def load_job_requirements(job_id: str):
    experiments_root = Path(__file__).resolve().parents[3] / "data" / "experiments"
    req_path = experiments_root / job_id / f"{job_id}_requirements.json"
    if not req_path.exists():
        return None
    with open(req_path, "r", encoding="utf-8") as f:
        return json.load(f)