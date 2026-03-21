from models import RankerName
NORM_MIN = 0.0
NORM_MAX = 100.0

ALL_RANKERS: list[RankerName] = ["tfidf","bm25", "transformer"] ## can add , "llm" but its very slow.["tfidf", "bm25", "transformer"]
DEFAULT_ITERATIONS = 20
DEFAULT_RANKER = ["transformer"]

# local ollama
OLLAMA_URL = "http://localhost:11434"

LLM_MODEL = "llama3.2:3b"
#LLM_MODEL = "hf.co/hugging-quants/Llama-3.2-3B-Instruct-Q4_K_M-GGUF:Q4_K_M"
LLM_NUM_CTX = 4096
LLM_TEMPERATURE = 0.1
LLM_TIMEOUT = 120

POS_PROMPT = """You are a data extraction engine.
Return ONLY valid JSON.
Do NOT include explanations, markdown, code fences, or extra text.

Extract:
- Job_Title (string)
- Location as City, Province or City, State only (string or null)
- keyTechnicalSkills (array of strings)
- keyNonTechnicalSkills (array of strings)
- requiredEducationLevel as a degree or certification (string or null)
- requiredYearsExperience (integer only or null)


Rules:
- Extract any specific technical skills in the job description and include them in the keyTechnicalSkills list.
- Preserve bundled technical skills only when they are synonymous, otherwise create a separate result per skill.
- Remove leading narrative wording, including variations of words such as 'experience with', 'participating in', 'knowledge of', 'ability to', and 'nice-to-have:'.",
- Generalize skills where possible, so that they apply broadly to resumes.
- Do not add clarifying words, examples, explanations, or parenthetical expansions.
- Do not drop a requirement merely because it is preferred rather than mandatory.
- If a field is not present, return null.
- If an array has no items, return [].
"""
