import json, re, os, sys
import fitz  # PyMuPDF (installed via: pip install pymupdf)
import geonamescache
from services.section_parser import education_parse, experience_parse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
IN_DIR = PROJECT_ROOT /"data/resumes_pdf_in"
OUT_DIR = PROJECT_ROOT /"data/resumes_parsed_data"
SCHEMA_PATH = PROJECT_ROOT /"application/reference/resume_schema.json"
HEADINGS_PATH = PROJECT_ROOT /"application/reference/headings_dictionary.json"

geo_cache = geonamescache.GeonamesCache()
CITIES = {c["name"].lower() for c in geo_cache.get_cities().values()}

EMAIL_PAT = r"\S+@\S+"
PHONE_PAT = r"\d{3}.*\d{3}.*\d{4}"
YEAR_PAT = r"\b(19|20)\d{2}\b"
GPA_PAT = r"\b(?:GPA[:\s]*([0-4]\.\d{1,2})|([0-4]\.\d{1,2})\s*GPA)\b"

def valid_city_name(s):
    s = re.sub(r"\s+", " ", (s or "").strip().lower())
    return s in CITIES

def load_headings():
    with open(HEADINGS_PATH, "r", encoding="utf-8") as f:
        headings_map = json.load(f)
        reversed_headings = {}
        for section, variants in headings_map.items():
            for v in variants:
                reversed_headings[v] = section
    return reversed_headings

def normalize_line(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^[^A-Za-z0-9]+", "", s)
    s = re.sub(r"\s+", " ", s)
    s = s.replace("–", "-").replace("—", "-")
    return s

def extract_lines(pdf_path):
    doc = fitz.open(pdf_path)
    out_lines = []
    for page in doc:                                     # page
        d = page.get_text("dict")
        blocks = [b for b in d.get("blocks", []) if b.get("type") == 0]
        blocks.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))
        for b in blocks:                                 # block
            for ln in b.get("lines", []):                # line
                line = normalize_line("".join(sp.get("text", "") for sp in ln.get("spans", [])))
                if line:
                    if out_lines and line[0].islower():
                        out_lines[-1]+=" " + line
                    else:
                        out_lines.append(line)
    return out_lines


def profile(lines,headings):
    name = lines[0].split(",",1)[0].strip() if lines else None
    profile_end = 0
    email, phone, location = None, None, None
    used_idx = set ([0])  #index of items included in profile, so we can get anything missed, like a "statement"
    for i, l in enumerate(lines[:20]):
        if headings.get(l.lower().strip().rstrip(":-–—.")):
            break
        s = l.strip().replace(" ,", ",").replace("  ", " ")
        if email is None and re.search(EMAIL_PAT, l):
            email = re.search(EMAIL_PAT, l).group(0).lower()
            profile_end = max(profile_end, i)
            used_idx.add(i)

        if phone is None and re.search(PHONE_PAT, l):
            phone = re.sub(r"[()\-\s]", "", re.search(PHONE_PAT, l).group(0))
            profile_end = max(profile_end, i)
            used_idx.add(i)
        if location is None and i >= 1 and len(s) <= 120:
            t = re.sub(EMAIL_PAT, " ", s)
            t = re.sub(PHONE_PAT, " ", t)
            t = re.sub(r"[|•·,/]", " ", t)
            words = re.sub(r"\s+", " ", t).strip().split()

            for n in (3, 2, 1):
                for j in range(len(words) - n + 1):
                    city_text = " ".join(words[j:j+n]).strip(" .'-")
                    if valid_city_name(city_text):
                        province_text = words[j+n].strip(" ,.-") if j + n < len(words) and re.fullmatch(r"[A-Za-z]{2,12}", words[j+n].strip(" ,.-")) else None
                        location = f"{city_text}, {province_text}" if province_text else city_text
                        profile_end = max(profile_end, i)
                        used_idx.add(i)
                        break
                if location:
                    break

    return name, email, phone, location, profile_end, used_idx


def section_parse(lines, start,headings, profile_text = ""):
    sections = []

    def hit(line):
        l = line.lower().strip().rstrip(":-–—.")
        return headings.get(l) or (len(line.split()) <= 4 and next((v for h, v in headings.items() if h in l), None)) 
         
    def add_section (type, label, text):
        text = text.strip()   # let's not pass a section unless it has text - no point otherwise
        label = label or ""
        if type in {"summary", "work_experience", "education"} and sections and type == sections[-1]["type"]:
            sections[-1]["text"] = (sections[-1]["text"] + "\n" + text).strip()
            return
        sections.append({"type": type, "label": label, "text": text})
        return

    current = None
    label = None
    buffer = []

    if profile_text:
        add_section("summary", "", profile_text)
        current = "summary"
    for l in lines[start:]:
        heading = hit(l)
        if heading:
            if len(buffer)>0:        # append existing.
                add_section(current, label, "\n".join(buffer))
            current = heading
            label = l
            buffer = []
            continue
        if current is None:
            current = "summary"
        buffer.append(l)
    if len(buffer)>0:
        add_section(current, label, "\n".join(buffer))
    return sections


def build_resume_json(resume_id: str, pdf_path:str):
    headings = load_headings()
    lines = extract_lines(pdf_path)
# profile section
    name, email, phone, location, profile_end, used_idx = profile(lines,headings)
    pre_lines = [lines[i] for i in range(1, min(profile_end + 1, len(lines))) if i not in used_idx]
    profile_text = "\n".join(pre_lines).strip()

# section processing
    sections = section_parse(lines, profile_end + 1, headings, profile_text = profile_text)
    for section in sections:
        if section["type"] == "education":
            section ["subsections"] = {"education_items": education_parse(section["text"])}
        elif section["type"] == "work_experience":
            section ["subsections"] = {"experience_items": experience_parse(section["text"])}
        # FUTURE:  skills_parse(section) - if we do.

    return {"metadata": {"resume_id": resume_id, "file_path":pdf_path},
        "profile": {"name": name, "email": email, "phone": phone, "location": location, "links": []},
        "sections": sections}


def main():
    resume_id = os.path.splitext(sys.argv[1])[0]
    out_filepath = os.path.join(OUT_DIR, resume_id + ".json")
    resume_obj = build_resume_json(resume_id, IN_DIR, OUT_DIR)

    with open(out_filepath, "w", encoding="utf-8") as f:
        json.dump(resume_obj, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    main()
