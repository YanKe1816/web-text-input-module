from flask import Flask, jsonify, request, Response, make_response
import re
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

OPENAI_VERIFICATION_TOKEN = "nQZ6GaFoaECuTA1e-6cXnCut_7xfkoEc8f7uY4muiFw"

# ---------- helpers ----------
def with_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, HEAD"
    return resp

@app.route("/mcp", methods=["OPTIONS"])
def mcp_options():
    return with_cors(make_response("", 204))

@app.route("/mcp", methods=["GET", "HEAD"])
def mcp_get():
    # 让平台探测 GET/HEAD 不会 405
    return with_cors(jsonify(ok=True, endpoint="/mcp"))

# ---------- OpenAI Domain Verification ----------
@app.get("/.well-known/openai-apps-challenge")
def openai_domain_verification():
    return Response(OPENAI_VERIFICATION_TOKEN, mimetype="text/plain")

# ---------- MCP Manifest ----------
@app.get("/.well-known/mcp.json")
def mcp_manifest():
    return with_cors(jsonify({
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
                        "url": {"type": "string", "description": "The webpage URL"}
                    },
                    "required": ["url"]
                }
            }
        ]
    }))

# ---------- basic ----------
@app.get("/")
def home():
    return "Web Page Text Extractor MCP Server"

@app.get("/health")
def health():
    return jsonify(ok=True)

@app.get("/privacy")
def privacy():
    return "No user data is stored."

# ---------- your existing fetch ----------
@app.get("/fetch")
def fetch():
    url = request.args.get("url", "").strip()
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return jsonify(error="Invalid or missing url"), 400

    try:
        r = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; WebTextExtractor/1.0)"}
        )
        r.raise_for_status()
        html = r.text
    except Exception as e:
        return jsonify(error="Failed to fetch url", detail=str(e)), 502

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = (soup.title.get_text(strip=True) if soup.title else "")
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)[:20000]

    return jsonify(title=title, text=text, source_url=url)

# ---------- REAL MCP JSON-RPC ----------
TOOLS = [
    {
        "name": "extract_web_text",
        "description": "Fetch a webpage and extract its readable text content",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The webpage URL"}
            },
            "required": ["url"]
        }
    }
]

@app.route("/mcp", methods=["POST"])
def mcp_post():
    payload = request.get_json(silent=True) or {}
    method = payload.get("method")
    req_id = payload.get("id")

    def ok(result):
        return with_cors(jsonify({"jsonrpc": "2.0", "id": req_id, "result": result}))

    def err(code, message, data=None):
        e = {"code": code, "message": message}
        if data is not None:
            e["data"] = data
        return with_cors(jsonify({"jsonrpc": "2.0", "id": req_id, "error": e}))

    # 1) initialize
    if method == "initialize":
        return ok({
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "Web Page Text Extractor", "version": "1.0.0"},
            "capabilities": {"tools": {}}
        })

    # 2) tools/list
    if method == "tools/list":
        return ok({"tools": TOOLS})

    # 3) tools/call
    if method == "tools/call":
        params = payload.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}

        if name != "extract_web_text":
            return err(-32602, "Unknown tool", {"name": name})

        url = (arguments.get("url") or "").strip()
        if not url:
            return err(-32602, "Missing url")

        # 复用 /fetch
        with app.test_request_context(f"/fetch?url={url}"):
            resp = fetch()
        # resp 可能是 (json, status) 也可能是 Response
        if isinstance(resp, tuple):
            body, status = resp
            if status != 200:
                return err(-32000, "Fetch failed", body.get_json() if hasattr(body, "get_json") else None)
            data = body.get_json()
        else:
            data = resp.get_json()

        # MCP tool result format: content array
        return ok({
            "content": [
                {"type": "text", "text": data.get("text", "")}
            ],
            "meta": {
                "title": data.get("title", ""),
                "source_url": data.get("source_url", url)
            }
        })

    # unknown
    return err(-32601, "Method not found", {"method": method})
