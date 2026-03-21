#  experiment_engine.py - takes cases and runs them
from __future__ import annotations
from pathlib import Path
import json, re
from copy import deepcopy
from models import ExperimentCase
import gender_guesser.detector as gender_guess

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENDER_FILE_PATH = PROJECT_ROOT / "reference" / "gender.json"
PROVINCE_MAP = {"on": "ontario", "qc": "quebec", "pq": "quebec", "bc": "british columbia", "ab": "alberta", "mb": "manitoba",
    "sk": "saskatchewan","ns": "nova scotia",  "nb": "new brunswick",  "nl": "newfoundland",  "pe": "prince edward island",
    "pei": "prince edward island", "yt": "yukon",  "nt": "northwest territories",  "nu": "nunavut"}


def normalize_location(s):
    s = re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())
    parts = s.split()
    parts = [PROVINCE_MAP.get(p, p) for p in parts]
    return " ".join(parts)

def run_experiment(case: ExperimentCase, pos_req, resume_json):
    resume_out = deepcopy(resume_json)  
    c_type = case.case_type
    if c_type == "validation": result = _apply_validation_case(case, pos_req,resume_out)
    elif c_type == "gender": result = _apply_gender_case(case, pos_req,resume_out)
    elif c_type == "location": result = _apply_location_case(case, pos_req,resume_out)
    elif c_type == "education":  result = _apply_education_case(case, pos_req,resume_out)
    elif c_type == "position":  result = _apply_position_case(case, pos_req,resume_out)
    elif c_type in ("tools","tech", "skills","vendors","other"): result = _apply_skill_case(case, pos_req, resume_out)
    return result

def _apply_validation_case(case, pos_req,resume_json):
    return (resume_json, "0_validation")

def _apply_gender_case(case, pos_req, resume_json):
    detector = gender_guess.Detector()
    gender_subs = json.loads(GENDER_FILE_PATH.read_text(encoding="utf-8"))
    name_sub = gender_subs["gender_name_map"]
    token_sub = gender_subs["gender_token_map"]
    full_name = resume_json["profile"]["name"]
    first_name = full_name.split()[0]
    gender = detector.get_gender(first_name)
    if gender in ("male","mostly male"):  change = "m2f"
    elif gender in ("female","mostly female"):   change = "f2m"
    else: 
        change = None
        return (resume_json, "name ambiguous, no changes")

    if change: 
        new_name = name_sub[change][0]
        resume_json["profile"]["name"] = full_name.replace(first_name,new_name ,1)

    token_changes = 0  # apply other changes for gender
    for section in resume_json.get ("sections",[]):
        text = section.get("text", "")
        for src, tgt in token_sub[change].items():
            pattern = rf"\b{re.escape(src)}\b"
            matches = re.findall(pattern, text, flags=re.IGNORECASE)
            if matches:
                token_changes += len(matches)
                text = re.sub(pattern, tgt, text, flags=re.IGNORECASE)
        section["text"] = text
    change_sum = f"gender {change}: {first_name} to {new_name} [{token_changes} other changes]"
    return (resume_json, change_sum) 


def _apply_location_case(case, pos_req, resume_json):
    target = case.value.strip()
    cur = resume_json["profile"].get("location")
    r = normalize_location(cur)
    t = normalize_location(target)    
    matches = bool(r) and ((t in r) or (r in t))
    if matches:
        return (resume_json, f"location matches ({cur}), no changes")
    resume_json["profile"]["location"] = target
    return (resume_json, f"location: {target}")


def _apply_education_case(case, pos_req, resume_json):
    req_level = pos_req["requirements"]["education"]["level"]
    req_cred = case.value 
    sections = resume_json["sections"]  
    max_level = 0
    max_section = None
    for s in sections:
        if s.get ("type")!= "education": continue
        subs = s.get("subsections") or {}
        items = subs.get("education_items")   # how do we deal with 
        if items is None: continue
        if max_section is None: max_section = s
        for it in items:
            if it.get("level", 0) > max_level:
                max_level = it.get("level", 0)
                max_section = s
    if max_level >= req_level:
        return (resume_json, f"education level {max_level} meets requirement {req_level}, no changes")
    if max_section is None:
        max_section = {"type": "education", "label": "Education", "text": "", "subsections": {"education_items": []}}
        sections.append(max_section)
    items = max_section["subsections"].setdefault("education_items", [])
    items.insert(0, {"credential": req_cred, "level": req_level, "deg_loc": 0, "institution": "University of Toronto",
        "inst_loc": 0, "record": [req_cred, "University of Toronto"], "year": None, "gpa": None})
    return (resume_json, f"education: added {req_cred} [University of Toronto]")


def _apply_position_case(case, pos_req, resume_json):
    COMPANY_NAME = "WLU Consultants Ltd"
    ACCOUNTABILITY_LINE = "Completed tasks as assigned."
    START_YEAR = 2022
    END_YEAR = 2023

    title = (pos_req.get("title") or "").strip()
    header = [f"{title}", f"{COMPANY_NAME} | {START_YEAR} - {END_YEAR}"]
    accountabilities = [ACCOUNTABILITY_LINE]
    item = {"header": header, "accountabilities": accountabilities, "start_year": START_YEAR, "end_year": END_YEAR}

    sections = resume_json["sections"]
    wx = next((s for s in sections if s.get("type") == "work_experience"), None)
    if wx is None:
        wx = {"type": "work_experience", "label": "Work Experience", "text": "", "subsections": {"experience_items": []}}
        sections.append(wx)
    subs = wx.setdefault("subsections", {})
    items = subs.setdefault("experience_items", [])
    items.insert(1 if len(items) >= 1 else 0, item) 
    wx["text"] = (wx.get("text") or "").rstrip() + "\n\n" + header[0] + "\n" + header[1]    
    return (resume_json, f"position: add '{title}' [{START_YEAR}-{END_YEAR}]")


def _apply_skill_case(case, pos_req, resume_json):
    sections = resume_json["sections"]
    target_label = "Technology " if case.case_type in ("tech" ,"tools","vendors") else ""
    skills = json.loads(case.value)    
    skill_section = None
    for s in sections:
        if s.get("type") in ("skills", "other"):
            t = s.get("text") or ""
            if all(skill in t for skill in skills):
                return (resume_json, f"{case.case_type}: all items already present, no changes")
            skill_section = s
            break

    if skill_section is None:
            skill_section = {"type": "skills", "label": f"{target_label}Skills", "text": "\n".join(skills)}
            sections.append(skill_section)
            return (resume_json, f"{case.case_type}: {len(skills)} added to {skill_section.get('label')} [{', '.join(skills)}]")

    new_skills = []
    for skill in skills:
        if skill in (skill_section.get("text") or ""):
            continue
        if skill_section.get("text"):
            skill_section["text"] = skill_section["text"].rstrip() + "\n" + skill
        else:   # empty text - issue if label mis-read
            skill_section["text"] = skill
        new_skills.append(skill)

    return (resume_json, f"{case.case_type}: {len(new_skills)} added to {skill_section.get('label')} [{', '.join(new_skills)}]")

def apply_combined_case(components: list[ExperimentCase], pos_req, resume_json):
    c_changes = []
    for case in components:
        ctype = case.case_type
        if ctype == "gender":
            resume_json, _ = _apply_gender_case(case, pos_req, resume_json)
            c_changes.append(ctype)
        elif ctype == "location":
            resume_json, _ = _apply_location_case(case, pos_req, resume_json)
            c_changes.append(ctype)
        elif ctype == "education":
            resume_json, _ = _apply_education_case(case, pos_req, resume_json)
            c_changes.append(ctype)
        elif ctype == "position":
            resume_json, _ = _apply_position_case(case, pos_req, resume_json)
            c_changes.append(ctype)
        elif ctype in ("tech", "tools", "vendors", "other"):
            resume_json, _ = _apply_skill_case(case, pos_req, resume_json)
            c_changes.append(ctype)
        else:
            raise ValueError(f"Unknown combined component case_type: {ctype}")

    return resume_json, {"change_summary": f"combined: {', '.join(c_changes)}"}