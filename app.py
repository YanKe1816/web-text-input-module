import re
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request

app = Flask(__name__)

@app.get("/")
def home():
    return "Web Page Text Input Module. Use /health or /fetch?url=..."

@app.get("/privacy")
def privacy():
    return "No user data is stored."

@app.get("/health")
def health():
    return jsonify(ok=True)
OPENAI_VERIFICATION_TOKEN = "nQZ6GaFoaECuTA1e-6cXnCut_7xfkoEc8f7uY4muiFw"

@app.get("/.well-known/openai-domain-verification.txt")
def openai_domain_verification():
    return Response(
        OPENAI_VERIFICATION_TOKEN,
        mimetype="text/plain"
    )
@app.get("/fetch")
def fetch():
    url = request.args.get("url", "").strip()
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return jsonify(error="Invalid or missing url"), 400

    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
    except Exception as e:
        return jsonify(error="Failed to fetch url"), 502

    soup = BeautifulSoup(r.text, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else ""
    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)[:8000]

    return jsonify(title=title, text=text, source_url=url)
