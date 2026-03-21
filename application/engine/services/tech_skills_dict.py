import csv
from functools import cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TECH_SKILLS_PATH = PROJECT_ROOT /"application/reference/Technology Skills.txt"
# technology skills is from O*NET, a recognized framework for this stuff.
VENDORS_PATH = PROJECT_ROOT /"application/reference/vendors.csv"

def normalize_skill(s: str) -> str:
    return " ".join((s or "").lower().replace("–", "-").replace("—", "-").split())


def load_vendors():
    vendors = set()
    with open(VENDORS_PATH, "r", encoding="utf-8", newline="") as f:
        vendor_file = csv.DictReader(f)
        for row in vendor_file:
            v = row["short_key"].strip()
            vendors.add(v)
    return vendors


@cache
def load_tech_skills():
    skills_dict = {}
    code_lookup = {}

    with open(TECH_SKILLS_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            example = (row.get("Example") or "").strip()
            if example.lower().endswith(" software"): example = example[:-9]
            norm = normalize_skill(example)
            skill = skills_dict.get(norm)
            if skill is None:
                skill = {"example": example, "hot": False, "code": set()}
                skills_dict[norm] = skill

            skill["hot"] = skill["hot"] or (row.get("Hot Technology") == "Y")
            code = row.get("Commodity Code").strip()
            skill["code"].add(code)
            code_lookup[code] = (row.get("Commodity Title") or "").strip()

    vendors = load_vendors()
    naked_skills = {} #skills without vendor name
    naked_index = {}
    exclusions = {"","cloud","database","analytics", "director","flex","inventory","ios"}
    special_naked = {"ios": "apple ios", "aws": "amazon web services aws", "gcp": "google cloud", "oci": "oracle cloud"}

    for skill, record in skills_dict.items():
        vendor = skill.split()[0]
        if vendor in vendors:
            naked_skill = skill[len(vendor) + 1:]
            if (naked_skill in exclusions): continue
            else:
                naked_skills[naked_skill] = skill
                naked_index.setdefault(naked_skill, []).append(skill)   

    #clean up duplicate naked skills and add special 
    conflicts = {k for k, v in naked_index.items() if len(v) > 1}
    for k in conflicts: 
        del naked_skills[k]
        del naked_index[k]
    for k, v in special_naked.items(): naked_skills[k] = v

    print (f'Technology Skills Dictionary Extracted, {len(skills_dict)} items')

    with open(Path(__file__).resolve().parents[3] / "application/reference/tech_skills.csv", "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows([["skill_key","example","hot","code"]] + [[k, v["example"], int(v["hot"]), "|".join(sorted(v["code"]))] for k, v in sorted(skills_dict.items())])

    with open(Path(__file__).resolve().parents[3] / "application/reference/code_lookup.csv", "w", encoding="utf-8", newline="") as f2:
        csv.writer(f2).writerows([["code","commodity_title"]] + [[c, t] for c, t in sorted(code_lookup.items())])

    out_path = Path(__file__).resolve().parents[3] / "application/reference/vendor_stripped_skills.csv"
    with open(out_path, "w", encoding="utf-8", newline="") as f3:
        csv.writer(f3).writerows( [["naked_key", "full_skill_key"]]+ [[nk, fk] for nk, fk in sorted(naked_skills.items())])

    return skills_dict
