# ollama_service.py
import requests
from config import OLLAMA_URL, LLM_MODEL, LLM_NUM_CTX, LLM_TEMPERATURE, LLM_TIMEOUT

_ollama_session = requests.Session()

def ollama_generate(prompt: str) -> str:
    payload = {"model": LLM_MODEL, "prompt": prompt,  "stream": False, "keep_alive": "30m",
        "options": {"temperature": LLM_TEMPERATURE, "num_ctx": LLM_NUM_CTX}}  
    r = _ollama_session.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=LLM_TIMEOUT)  
    r.raise_for_status()
    return (r.json().get("response") or "").strip() 