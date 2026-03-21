# models.py
from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field

# literals
RankerName = Literal["tfidf", "bm25", "transformer", "llm"]
JobStatus = Literal["draft", "ready", "baselined", "running", "complete"]
CaseType = Literal["validation","education", "position", "skills", "tools", "vendors", "location", "tech", "gender", "other", "combined"]
CaseOp = Literal["add", "change", "remove", "combined"]

# class shapes
class JobDescription(BaseModel):
    job_id: str = Field(..., min_length=1)
    job_pdf_path: str = Field(..., min_length=1)
    description: str = Field(..., min_length=0)

class JobIn(BaseModel):
    job_id: str = Field(..., min_length=1)
    job_lines: List[str]
    job_title: str | None = None
    job_skills: list[str] | None = None 
    job_education: str | None = None

class JobIndex(BaseModel):
    jobs: List[JobDescription] = Field(default_factory=list)


class Candidate(BaseModel):
    candidate_id: str = Field(..., min_length=1)
    candidate_name: str | None = None    #new
    resume_pdf_path: str = Field(..., min_length=1)  

class AddCandidatesRequest(BaseModel):
    resume_pdf_paths: List[str] = Field(..., min_length=1)

class CandidateIndex(BaseModel):
    candidates: List[Candidate] = Field(default_factory=list)

class CandidateList(BaseModel):
    job_id: str
    candidates: List[Candidate] = Field(default_factory=list)

class CandidateIn(BaseModel):
    candidate_id: str = Field(..., min_length=1)
    case_id: str = Field(..., min_length=1)   # for managing perturbation
    resume_lines: List[str]

class AttachFolderRequest(BaseModel):
    folder_path: str

class RankRequest(BaseModel):
    run_id: str = Field(..., min_length=1)    # experiment id
    job: JobIn
    candidates: List[CandidateIn]
    ranker: Optional[RankerName] = None

class CandidateOut(BaseModel):
    candidate_id: str
    case_id: str
    ranker: RankerName
    score: float
    norm_score: float| None = None
    rank: int

class RankResponse(BaseModel):
    run_id: str
    job_id: str
    ranking: List[CandidateOut]

class BaselineRequest(BaseModel):   
    rankers: Optional[List[RankerName]] = None

class BaselineRow(BaseModel):
    job_id: str
    ranker: RankerName
    candidate_id: str
    score: float
    norm_score: float | None = None
    rank: int

class BaselineSummary(BaseModel):
    job_id: str
    rankers: List[RankerName] = Field(default_factory=list)
    rows: List[BaselineRow] = Field(default_factory=list)

class ExperimentParameters (BaseModel):
    rankers: List[RankerName] = Field(default_factory=list)
    num_iterations: Optional[int] = Field(default=12, ge=1)

class SetParamsRequest(BaseModel):
    params: ExperimentParameters

class GetParamsResponse(BaseModel):
    job_id: str
    params: ExperimentParameters
    rankers: list[RankerName] = Field(default_factory=list)

class RunExperimentRequest(BaseModel):
    candidate_id: Optional[str]

class ExperimentRow(BaseModel):
    experiment_id: str
    ranker: RankerName
    candidate_id: str
    case_id: str
    score: float
    norm_score: float | None = None
    rank: int

class ExperimentSummary(BaseModel):
    job_id: str
    experiment_id: str
    name: str
    params: ExperimentParameters = Field(default_factory=ExperimentParameters)
    rows: List[ExperimentRow] = Field(default_factory=list)
    subject_candidate_id: str | None = None
    change_summary: str | None = None

class NormalizerVals(BaseModel):
    job_id: str
    run_id: str
    items: list[NormModel]

class NormModel(BaseModel):
    ranker: RankerName
    bias: float
    coef: float
    raw_min: float
    raw_max: float

class ExplanationFactor(BaseModel):
    case_id: str = Field(..., min_length=1)
    case_type: CaseType
    short_reason: str | None = None
    full_reason: str | None = None
    delta_norm: float
    delta_rank: int

class ExplanationRecord(BaseModel):
    ranker: RankerName
    candidate_id: str = Field(..., min_length=1)
    baseline_rank: int
    baseline_norm: float
    factors: List[ExplanationFactor] = Field(default_factory=list)
    explanation_gap: float | None = None          # top_score - baseline_norm (floored at 0)
    top_factor_explains: float | None = None      # ratio in [0,1]: best single-factor delta_norm/gap
    combined_factor_explains: float | None = None # ratio in [0,1]: combined delta_norm /gap

class JobState(BaseModel):  # core model component here
    job: JobDescription
    status: JobStatus
    candidate_ids: List[str] = Field(default_factory=list)
    params_current: ExperimentParameters = Field(default_factory=ExperimentParameters)
    baseline: Optional[BaselineSummary] = None
    experiments: List[ExperimentSummary] = Field(default_factory=list)
    explanations: list[ExplanationRecord] = Field(default_factory=list)
    norm: NormalizerVals | None = None

class DeleteJobResponse(BaseModel):
    ok: bool
    deleted_job_id: str

class AttachCandidateRequest(BaseModel):  # to job
    candidate_ids: List[str] = Field(..., min_length=1)

class DeleteCandidateResponse(BaseModel):  # from library
    ok: bool
    candidate_id: str   

class RemoveCandidateResponse(BaseModel):  # delete from job
    ok: bool
    candidate_id: str   

class ExperimentRequest (BaseModel):
    job_id: str
    run_id: str
    case_id: str
    rankers: list[RankerName]
    job_pdf_path: str
    candidates: list[tuple[str, str]]  # [(candidate_id, resume_pdf_path), ...] rebuilt PDFs
    norm: Optional[NormalizerVals]

class ResumeSection (BaseModel):
    type: str
    label: str
    text: str

class ExperimentCase (BaseModel):
    job_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_num: int = Field(ge=0)
    case_type: CaseType
    target: str | None = None
    value: str | None = None
    description: str | None = None

