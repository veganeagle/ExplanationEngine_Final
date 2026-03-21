# ATS Simulator & Ranking Black Box

This document describes the **Job Applicant Explanation Engine** and the **ranking black box service** (TF-IDF / BM25 / Sentence Transformers), how they interact, and how to run them locally.

The goal is to simulate an ATS-style batch ranking of resumes against a single job description in a **deterministic, model-agnostic** way suitable for sensitivity analysis.

---

## 1. Architecture Overview


---

## 2. Folder Structure 
├───application
│   ├───engine
│   │   ├───build_pdf
│   │   │   ├───templates
│   │   ├───services
│   ├───reference
│   └───web_test
├───data
│   ├───experiments
│   └───persistence
│       ├───candidate_uploads
│       └───job_uploads
└───Job_Packs
---

## 3. End-to-End Data Flow


python -m uvicorn app:app --host 127.0.0.1 --port 8010

## 4. Ranking Service

### 4.1 Supported Models

### 4.2 API Endpoint

---

## 5. Request / Response Schema (Conceptual)

### Request

pip install -r requirements.txt


## OLLAMA  !
run Ollama from Windows
C:>  ollama list    <--- shows models

## 6. HTML to PDF
pip install xhtml2pdf 

