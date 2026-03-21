# position_analyzer.py
import json, csv, requests
from pathlib import Path
from services.ollama_service import ollama_generate
from config import POS_PROMPT
from jsonschema import validate

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = PROJECT_ROOT / "application/reference/position_requirements_schema.json"
TEST_JSON = PROJECT_ROOT / "data/experiments/Accounts_Payable_Analyst/job_details.json"
VENDORS_CSV = PROJECT_ROOT / "application/reference/vendors.csv"
TOOLS_CSV = PROJECT_ROOT / "application/reference/vendor_stripped_skills.csv"
EDU_CFG_PATH = PROJECT_ROOT / "application/reference/education.json"  

def vendor_match(lines):
    vendors = set()
    with open(VENDORS_CSV, "r", encoding="utf-8", newline="") as f:
        vend_file = csv.DictReader(f)
        for row in vend_file:
            v = (row.get("short_key") or "").strip()
            if v: vendors.add(v)
    text = " ".join(lines).lower()
    for ch in ",.;:()[]{}<>/\\|\"'`~!@#$%^&*-_=+?":
        text = text.replace(ch, " ")
    tokens = set(text.split())

    matches = [vendor for vendor in vendors if vendor in tokens]
    return matches

def tool_match(lines):
    tools = set()
    with open(TOOLS_CSV, "r", encoding="utf-8", newline="") as f:
        tool_file = csv.DictReader(f)
        for row in tool_file:
            t = (row.get("naked_key") or "").strip()
            if t: tools.add(t)

    text = " ".join(lines).lower() + " "
    matches =[]
    for tool in tools:
        if f"{tool}" in text:
            matches.append(tool)
    return matches

def degree_level_loader():
    with open(EDU_CFG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    map = {}
    for lvl, items in cfg["level"].items():
        for degree in items: map[degree.lower()] = int(lvl)
    return map

def get_edu_level(credential, degree_level):
    if not credential: return 0
    for ch in ",.;:()[]{}<>/\\|\"'`~!@#$%^&*-_=+?":
        text = credential.replace(ch, " ").lower()
    tokens = text.split()
    lvl = None
    for token in tokens:
        x = degree_level.get(token)
        if x is not None: lvl = x if lvl is None else max(lvl, x)
    return lvl


def instantiate_requirements(job_id, job_lines):
    return {
        "job_id": job_id,
        "title": None,
        "generic_title": None,
        "location": None,
        "requirements": {
            "tech": [],
            "other_skills": [],
            "education": {"credential": None, "level": None, "field": None},
            "experience": {"years_min": None},
            "vendors": [],
            "certifications": [],
            "tools": []
        },
        "raw": {"job_lines": job_lines or []}
    }


def analyze(job_id, lines):
    degree_map = degree_level_loader()
    req = instantiate_requirements(job_id, lines)
    joined = "\n".join(lines)
    prompt = f"""{POS_PROMPT}\n\n {joined}"""
    try:
        raw = ollama_generate(prompt).strip()
    except requests.exceptions.RequestException as e:  # for Raj, in case he is not running Ollama (which he is not)
        print(f"[WARN] Ollama unavailable, skipping LLM extraction: {e}")
        req["requirements"]["vendors"] = vendor_match(lines)
        return req
    
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"LLM did not return JSON:\n{raw}")
    raw = raw[start:end+1]
    print(raw)
    llm_response = json.loads(raw)
    print (llm_response)
    req["title"] = llm_response.get("Job_Title")
    loc = llm_response.get("Location")
    if isinstance(loc, dict):
        req["location"] = f"{loc.get('City')}, {loc.get('Province')}"
    else:
        req["location"] = loc
    req["requirements"]["tech"]= llm_response.get("keyTechnicalSkills") or []
    req["requirements"]["other_skills"] = llm_response.get("keyNonTechnicalSkills") or []
    req["requirements"]["education"]["credential"] = llm_response.get("requiredEducationLevel")
#    req["requirements"]["education"]["field"] = llm_response.get("fieldOfStudy")
    req["requirements"]["education"]["level"] = get_edu_level(req["requirements"]["education"]["credential"], degree_map)
    req["requirements"]["experience"]["years_min"] = llm_response.get("requiredYearsExperience")
    req["requirements"]["vendors"] = vendor_match(lines)
    req["requirements"]["tools"] = tool_match(lines)

    ''' with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)
    validate(instance=req, schema=schema)'''

    return req

def main():
    job = json.loads(TEST_JSON.read_text(encoding="utf-8"))
    print(json.dumps(analyze("123",job["job_lines"]), ensure_ascii=False, indent=2))

if __name__ == "__main__": main()