from flask import Flask, jsonify, request, Response, make_response
import re
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

OPENAI_VERIFICATION_TOKEN = "nQZ6GaFoaECuTA1e-6cXnCut_7xfkoEc8f7uY4muiFw"

def with_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, HEAD"
    return resp

# --- MCP endpoint (OPTIONS/GET/POST) ---
@app.route("/mcp", methods=["OPTIONS"])
def mcp_options():
    return with_cors(make_response("", 204))

@app.route("/mcp", methods=["GET", "HEAD"])
def mcp_get():
    # 给平台探测用：不要 405
    return with_cors(Response("OK. This is an MCP JSON-RPC endpoint. Use POST.", mimetype="text/plain"))

# --- OpenAI Domain Verification ---
@app.get("/.well-known/openai-apps-challenge")
def openai_domain_verification():
    return Response(OPENAI_VERIFICATION_TOKEN, mimetype="text/plain")

# --- Basic pages for App Info ---
@app.get("/")
def home():
    return "Web Page Text Extractor MCP Server"

@app.get("/health")
def health():
    return jsonify(ok=True)

@app.get("/privacy")
def privacy():
    return "No user data is stored."

@app.get("/terms")
def terms():
    return "Provided as-is. This service only fetches public web pages and extracts readable text. No user data is stored."

# --- Your fetch implementation ---
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

# --- MCP tool list (IMPORTANT: annotations must be nested) ---
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
        },
        "annotations": {
            "readOnlyHint": True,
            "openWorldHint": True,
            "destructiveHint": False
        }
    }
]

# --- Optional: MCP discovery manifest (not required for scan, but nice) ---
@app.get("/.well-known/mcp.json")
def mcp_manifest():
    return with_cors(jsonify({
        "schema_version": "v1",
        "name": "Web Page Text Extractor",
        "description": "Extract clean readable text from a webpage URL",
        "tools": TOOLS
    }))

# --- MCP JSON-RPC ---
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

    if method == "initialize":
        return ok({
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "Web Page Text Extractor", "version": "1.0.0"},
            "capabilities": {"tools": {}}
        })

    if method == "tools/list":
        return ok({"tools": TOOLS})

    if method == "tools/call":
        params = payload.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}

        if name != "extract_web_text":
            return err(-32602, "Unknown tool", {"name": name})

        url = (arguments.get("url") or "").strip()
        if not url:
            return err(-32602, "Missing url")

        with app.test_request_context(f"/fetch?url={url}"):
            resp = fetch()

        if isinstance(resp, tuple):
            body, status = resp
            if status != 200:
                return err(-32000, "Fetch failed", body.get_json() if hasattr(body, "get_json") else None)
            data = body.get_json()
        else:
            data = resp.get_json()

        return ok({
            "content": [{"type": "text", "text": data.get("text", "")}],
            "meta": {
                "title": data.get("title", ""),
                "source_url": data.get("source_url", url)
            }
        })

    return err(-32601, "Method not found", {"method": method})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
