import re
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request, Response

app = Flask(__name__)

# =========================
# OpenAI Domain Verification
# =========================
OPENAI_VERIFICATION_TOKEN = "nQZ6GaFoaECuTA1e-6cXnCut_7xfkoEc8f7uY4muiFw"

@app.get("/.well-known/openai-apps-challenge")
def openai_domain_verification():
    return Response(
        OPENAI_VERIFICATION_TOKEN,
        mimetype="text/plain"
    )

# =========================
# MCP Manifest (Scan Tools 用)
# =========================
@app.get("/.well-known/mcp.json")
def mcp_manifest():
    return jsonify({
        "schema_version": "v1",
        "name": "Web Page Text Extractor",
        "description": "Extract clean readable text from a webpage URL",
        "tools": [
            {
                "name": "extract_web_text",
                "description": "Fetch a webpage and extract its readable text content",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The webpage URL to extract text from"
                        }
                    },
                    "required": ["url"]
                }
            }
        ]
    })

# =========================
# MCP Tool 执行入口
# =========================
@app.post("/mcp")
def mcp_handler():
    data = request.json or {}
    tool = data.get("tool")
    args = data.get("arguments", {})

    if tool == "extract_web_text":
        url = args.get("url")
        if not url:
            return jsonify({"error": "url is required"}), 400

        # 复用 /fetch 逻辑
        with app.test_request_context(f"/fetch?url={url}"):
            return fetch()

    return jsonify({"error": "Unknown tool"}), 400

# =========================
# 基础接口
# =========================
@app.get("/")
def home():
    return "Web Page Text Extractor MCP Server"

@app.get("/health")
def health():
    return jsonify(ok=True)

@app.get("/privacy")
def privacy():
    return "No user data is stored."

# =========================
# 实际网页抓取逻辑
# =========================
@app.get("/fetch")
def fetch():
    url = request.args.get("url", "").strip()

    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return jsonify(error="Invalid or missing url"), 400

    try:
        # 先把网页抓下来
        r = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; WebTextExtractor/1.0)"}
        )
        r.raise_for_status()
        html = r.text
    except Exception as e:
        return jsonify(error="Failed to fetch url", detail=str(e)), 502

    # 下面是你原来的解析逻辑（你可以先用最简单的，保证能跑起来）
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = (soup.title.get_text(strip=True) if soup.title else "")
    text = soup.get_text("\n", strip=True)

    # 简单裁剪，避免太长
    text = re.sub(r"\n{3,}", "\n\n", text)[:20000]

    return jsonify(
        title=title,
        text=text,
        source_url=url
    )
