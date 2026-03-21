import json, re
from pathlib import Path
from services.tech_skills_dict import load_tech_skills, normalize_skill
from datetime import date

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EDU_CFG_PATH = PROJECT_ROOT / "application/reference/education.json"
WORK_CFG_PATH = PROJECT_ROOT / "application/reference/work_experience.json"
WORD_RE = re.compile(r"[A-Za-z]+")  # standalone "words"
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
DEG_STOP_WORDS =["with", "summa", "magna","cum","gpa", ";","-", ":",
                "(","0","1","2","3","4","5","6","7","8","9"]


def education_parse(source):
    with open(EDU_CFG_PATH, "r", encoding="utf-8") as f:
        education_config = json.load(f)
    degrees = set(education_config["degrees"])
    degree_level = {}
    for lvl, items in education_config["level"].items():
        for degree in items:  degree_level[degree] = int(lvl)
    institutions = set(education_config["institutions"])
    gpa_re = re.compile(education_config["gpa"][0], re.IGNORECASE)
    records = []
    degree_flag, inst_flag = False, False
    record = {}

    def close_record():
        nonlocal record, degree_flag, inst_flag
        years = YEAR_RE.findall(" ".join(record.get("record", [])))
        if record.get("level") is None: record["level"] = 0
        record["year"] = max((int(y) for y in years), default=None)
        gpas = [g1 or g2 for (g1, g2) in gpa_re.findall(" ".join(record.get("record", [])))]
        record["gpa"] = max((float(g) for g in gpas), default=None)
        records.append(record)
        record = {}
        degree_flag, inst_flag = False, False
        return

    for line_no, line in enumerate(source.splitlines(), 1):
        clean_line = line.replace(".", "")   #no periods for degrees

        for m in WORD_RE.finditer(clean_line):             # find degree
            token = m.group(0)
            if token[0].isupper() and token.lower() in degrees:
                if degree_flag: close_record() # new degree - close last record
                d_start = m.start()
                tail = clean_line[d_start:].lower()
                stop_word_idxs = [tail.find(s) for s in DEG_STOP_WORDS if tail.find(s) != -1]
                stop_idx = min(stop_word_idxs) if stop_word_idxs else len(tail)
                degree_str = clean_line[d_start:(d_start+stop_idx)].strip()
                record["credential"] = degree_str
                record["level"] = degree_level.get(token.lower())
                record["deg_loc"] = line_no  #line number only
                degree_flag = True
                break

        for m in WORD_RE.finditer(clean_line):    # find institution
            token = m.group(0)
            if token[0].isupper() and token.lower() in institutions:
                if inst_flag: close_record() # new institution  - close last  record
                i_start = m.start()
                if degree_flag and record.get("deg_loc") == line_no: # same line processing                        
                    if i_start < d_start:          # institution appears before the degree
                        inst_str = clean_line[:d_start].strip()
                    else:                          # institution appears after the degree
                        inst_str = clean_line[d_start + stop_idx:].strip()
                else: #not on same line as degree
                    inst_str = clean_line.strip()
                inst_lower = inst_str.lower()
                inst_stop_idxs = [inst_lower.find(s) for s in DEG_STOP_WORDS if inst_lower.find(s) != -1]
                inst_str = inst_str[:min(inst_stop_idxs) if inst_stop_idxs else len(inst_str)].strip()
                record["institution"] = inst_str
                record["inst_loc"] = line_no  
                inst_flag = True
        record.setdefault("record",[]).append(line)
    close_record()

    return records

def experience_parse (source):
    with open(WORK_CFG_PATH, "r", encoding="utf-8") as f:
        work_config = json.load(f)
    records =[]
    record = {}
    in_header = True

    def close_record():
        nonlocal record, in_header
        record["start_year"], record["end_year"] = year_range(record.get("header", []))
        records.append(record)
        record = {}
        in_header = True
        return
    
    def year_range(header_lines):
        ys = [int(y) for y in YEAR_RE.findall(" ".join(header_lines or []))]
        if not ys:
            return None, None
        if len(ys) == 1:
            return ys[0], date.today().year
        return min(ys), max(ys)

    for line_no, line in enumerate(source.splitlines(), 1):
        words = WORD_RE.findall(line)     

        # rules to determine if line is part of header (True)
        cap_share = ((sum(w[0].isupper() for w in words) / len(words)) if words else 0.0)
        s = line.strip()
        header_line = all([cap_share > 0.5, len(words) <= 10,
                           (not s or s[-1] not in {".", ",", ";", ":"}),
                           not s.startswith(("I ", "In "))  ])     
        if header_line and not in_header:
            close_record()    # we hit a new record
            record.setdefault("header",[]).append(line)
        elif header_line:   
            record.setdefault("header",[]).append(line)
        else: 
            in_header = False
            record.setdefault("accountabilities",[]).append(line)
    close_record()

    return records

# not used... it was a good idea, may come back to it. 
def skills_parse(source):
    use_sections=("summary", "skills", "other")
    tech_dict = load_tech_skills()
    other_skills = []
    #cycle through Summary, Skills, Other
    for section in use_sections:
        block = source.get(section)
        if block in None or block.len() ==0: continue
        lines = block.splitlines()
        for i, line in enumerate(lines, 1):
            raw = line.strip()
            if not raw: continue 
    return