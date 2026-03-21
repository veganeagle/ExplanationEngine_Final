# build_pdf/build_pdf_service.py
import json
from pathlib import Path
from typing import Dict, Any
from xhtml2pdf import pisa
from jinja2 import Environment, FileSystemLoader, select_autoescape

def render_pdf_xhtml2pdf(html: str, pdf_path: Path):
    with pdf_path.open("wb") as f:
        pisa.CreatePDF(html, dest=f, encoding="utf-8")


def build_resume_pdf(resume_json: Dict[str, Any], file_name: str, out_path: Path, template_name: str = "resume_1",):
    # file stuff
    out_path = Path(out_path)
    out_path.mkdir(parents=True, exist_ok=True)
    template_path = str(Path(__file__).resolve().parent / "templates" / template_name)
    env = Environment(loader=FileSystemLoader(template_path), autoescape=select_autoescape(['html',"xml"]))
    this_template = env.get_template(f"base.html")
    css_text = (Path(template_path) / "resume.css").read_text(encoding="utf-8")

    html_path = out_path / f"{file_name}.html"
    pdf_path = out_path / f"{file_name}.pdf"
    
    # resume sections
    profile = resume_json.get("profile") or {}
    sections = resume_json.get("sections") or []
    html = this_template.render(profile = profile, sections = sections)

    html_with_css = html.replace("</head>", f"<style>\n{css_text}\n</style>\n</head>")
    html_path.write_text(html_with_css,encoding = "utf-8")    # use to write interim html only
    render_pdf_xhtml2pdf(html_with_css, pdf_path)
    return pdf_path


# for testing only
if __name__ == "__main__":
    '''    
    #no longer needed
    import json
    resume = Path(__file__).resolve().parents[3] / "data/resumes_parsed_data/CV_LAAMRI_F.json"
    out_dir = Path(__file__).resolve().parents[3] / "data"
    resume_json = json.loads(resume.read_text(encoding="utf-8"))
    html_path = build_resume_pdf(resume_json=resume_json, file_name="test_resume", out_path=out_dir, template_name="resume_1")
    print(f"Resume at: {html_path}")
    '''

