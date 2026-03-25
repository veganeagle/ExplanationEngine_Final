import json, re, os, requests

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

from services.text_service import load_headings, profile, section_parse, normalize_line  # to simulate a proper model
from models import RankRequest, RankResponse, CandidateOut, RankerName

class RankingService:
    def __init__(self):
        self._score_re = re.compile(r"(-?\d+(?:\.\d+)?)")
        self._transformer_model = None  # lazy-load

    def rank(self, req: RankRequest) -> RankResponse:
        ranker: RankerName = req.ranker 
        req.ranker = ranker

        if ranker == "tfidf":
            print("Running TFIDF")
            return self._tfidf_ranker(req)

        if ranker == "bm25":
            print("Running BM25")
            return self._bm25_ranker(req)

        if ranker == "transformer":
            print("Running Sentence Transformer Embeddings")
            return self._sentence_transformer_ranker(req)

        if ranker == "chunk":
            print("Running Chunked Transformer Embeddings")
            return self._chunk_ranker(req)
        raise ValueError(f"Unsupported ranker: {ranker}")


    def _prepare_inputs(self, req: RankRequest):
        job_text = "\n".join(req.job.job_lines)
        cand_ids = [c.candidate_id for c in req.candidates]
        case_ids = [c.case_id for c in req.candidates]
        resumes = ["\n".join(c.resume_lines) for c in req.candidates]
        corpus = resumes + [job_text]  # vocab source for TFIDF
        return job_text, cand_ids, case_ids, resumes, corpus

    def _wrap_output(self, req: RankRequest, cand_ids, case_ids, scores):
        items = [(cand_ids[i], case_ids[i], round(float(scores[i]), 4)) for i in range(len(cand_ids))]
        items.sort(key=lambda t: (-t[2], t[0]))
        ranking = [
            CandidateOut(candidate_id=cand_id, case_id=case_id, ranker=req.ranker, score=score, rank=i + 1)
            for i, (cand_id, case_id, score) in enumerate(items)
        ]
        return RankResponse(run_id=req.run_id, job_id=req.job.job_id, ranking=ranking)


    def _tfidf_ranker(self, req: RankRequest) -> RankResponse:
        job_text, cand_ids, case_ids, resumes, corpus = self._prepare_inputs(req)
        vec = TfidfVectorizer(stop_words=None, ngram_range=(1, 2))
        X = vec.fit_transform(corpus)
        jd_vec = X[-1]
        scores = cosine_similarity(jd_vec, X[:-1]).flatten()
        return self._wrap_output(req, cand_ids, case_ids, [round(s, 3) for s in scores])

    def _bm25_ranker(self, req: RankRequest) -> RankResponse:
        job_text, cand_ids, case_ids, resumes, _ = self._prepare_inputs(req)
        resume_corpus = [doc.lower().split() for doc in resumes]
        bm25 = BM25Okapi(resume_corpus)
        jd_tokens = job_text.lower().split()
        scores = bm25.get_scores(jd_tokens)
        return self._wrap_output(req, cand_ids, case_ids, [round(s, 2) for s in scores])

    def _sentence_transformer_ranker(self, req: RankRequest) -> RankResponse:
        job_text, cand_ids, case_ids, resumes, _ = self._prepare_inputs(req)
        if self._transformer_model is None:
            self._transformer_model = SentenceTransformer("intfloat/e5-base-v2")
        model = self._transformer_model
        E = model.encode([f"passage: {r}" for r in resumes], normalize_embeddings=True)
        jd = model.encode([f"query: {job_text}"], normalize_embeddings=True)[0]
        scores = np.dot(E, jd)
        return self._wrap_output(req, cand_ids, case_ids, scores)

    def _extract_score(self, text: str) -> float:
        text = (text or "").strip()
        i, j = text.find("{"), text.rfind("}")
        if 0 <= i < j:
            try:
                obj = json.loads(text[i:j+1])
                if isinstance(obj, dict) and "score" in obj: return float(obj["score"])
            except Exception:
                pass
        m = re.search(r"(-?\d+(?:\.\d+)?)", text)
        if not m: raise ValueError(f"LLM returned no numeric score. Raw: {text[:200]}")
        return float(m.group(1))

    # improve sentence transformer
    def _chunk_jd(self, job_lines):
        jd_chunks, chunk = [], []
        for raw_line in job_lines:
            line = normalize_line(raw_line)
            chunk_end = not line or line.endswith(":") or len(chunk) >= 4
            if chunk_end and chunk:
                jd_chunks.append("\n".join(chunk))
                chunk = []
            if line: chunk.append(line)
        if chunk: jd_chunks.append("\n".join(chunk))
        return jd_chunks or ["\n".join(job_lines)]


    def _chunk_ranker(self, req: RankRequest) -> RankResponse:
        _, cand_ids, case_ids, _, _ = self._prepare_inputs(req)
        if self._transformer_model is None:
            self._transformer_model = SentenceTransformer("intfloat/e5-base-v2")
        model = self._transformer_model
        headings = load_headings()
        score_all_flag = req.run_id.startswith("base") or req.candidates[0].case_id == "0_validation"
        candidates = req.candidates if score_all_flag else req.candidates[:1]
        cand_ids = [c.candidate_id for c in candidates]
        case_ids = [c.case_id for c in candidates]
        job_chunks = self._chunk_jd(req.job.job_lines)
        jd_E = model.encode([f"query: {t}" for t in job_chunks], normalize_embeddings=True)

        scores = []
        for candidate_scored in candidates: 
            lines = [line for line in candidate_scored.resume_lines if line and line.strip()]
            _, _, _, _, profile_end, used_idx = profile(lines, headings)
            profile_text = "\n".join(
                lines[i] for i in range(1, min(profile_end + 1, len(lines))) if i not in used_idx
            ).strip()
            sections = section_parse(lines, profile_end + 1, headings, profile_text=profile_text)
            texts = [s["text"] for s in sections if s.get("text")]
            if not texts:
                scores.append (0.0)
                continue
            sec_E = model.encode([f"passage: {t}" for t in texts], normalize_embeddings=True)
            sims = sec_E @ jd_E.T
#            sec_scores = sims.max(axis=1)
#            best_idx = sims.argmax(axis=1)
            chunk_scores = sims.max(axis=0)   # one score per JD chunk
            vals = sorted(chunk_scores, reverse=True)
            top2 = vals[:2]
            rest = vals[2:]
            score = sum(top2) + (sum(rest) / len(rest) if rest else 0.0)
            print(
                f"{candidate_scored.candidate_id} | score ={score:.3f} | " +
                ", ".join(f"[j{i}]: {float(chunk_scores[i]):.3f}" for i in range(len(chunk_scores))) )
            scores.append(score)        
        return self._wrap_output(req, cand_ids, case_ids, scores)