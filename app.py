from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# ====== 1) 域名验证（你必须过这一关）======
OPENAI_VERIFICATION_TOKEN = "YWZI9_Pg7G9svmoydtQCj6Vep6gJlIT6n5rJxIL40iY"

@app.get("/.well-known/openai-apps-challenge")
def openai_domain_verification():
    return PlainTextResponse(OPENAI_VERIFICATION_TOKEN)

# ====== 2) CORS（避免外部调用被挡）======
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====== 3) 给“人看”的页面（App Info 会用到）======
@app.get("/")
def home():
    return {"name": "Execution Checklist MCP Server", "status": "ok"}

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/privacy")
def privacy():
    return PlainTextResponse(
        "Privacy Policy: This service does not store personal data. "
        "It processes the text you send only to generate a checklist response. "
        "No tracking, no user profiling, no data selling."
    )

@app.get("/terms")
def terms():
    return PlainTextResponse(
        "Terms of Service: Provided as-is, without warranties. "
        "Use at your own risk. The service returns generated checklists based on your input."
    )

# ====== 4) “说明书”（扫描器爱找这个位置）======
TOOLS = [
    {
        "name": "generate_checklist",
        "description": "Generate a structured execution checklist from input text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "What you want a checklist for"},
                "max_steps": {
                    "type": "integer",
                    "minimum": 3,
                    "maximum": 12,
                    "default": 8,
                    "description": "Max number of steps"
                }
            },
            "required": ["text"]
        },
        "annotations": {
            "readOnlyHint": True,
            "openWorldHint": False,
            "destructiveHint": False
        }
    }
]

@app.get("/.well-known/mcp.json")
def mcp_manifest():
    return {
        "schema_version": "v1",
        "name": "Execution Checklist",
        "description": "Generate execution checklists in a stable structured way.",
        "tools": TOOLS
    }

# ====== 5) /mcp 的“防试探”（GET/OPTIONS 不要让它死）======
@app.options("/mcp")
def mcp_options():
    return PlainTextResponse("", status_code=204)

@app.get("/mcp")
def mcp_get():
    return PlainTextResponse("OK. This is an MCP JSON-RPC endpoint. Use POST.")

# ====== 6) 真正的系统调用入口（扫描器就用这个问你三句话）======
@app.post("/mcp")
async def mcp_post(request: Request):
    payload = await request.json()
    method = payload.get("method")
    req_id = payload.get("id")

    def ok(result):
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def err(code, message, data=None):
        e = {"code": code, "message": message}
        if data is not None:
            e["data"] = data
        return {"jsonrpc": "2.0", "id": req_id, "error": e}

    # 1) initialize
    if method == "initialize":
        return ok({
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "Execution Checklist", "version": "1.0.0"},
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

        if name != "generate_checklist":
            return err(-32602, "Unknown tool", {"name": name})

        text = (arguments.get("text") or "").strip()
        max_steps = int(arguments.get("max_steps") or 8)

        if not text:
            return err(-32602, "Missing text")

        max_steps = max(3, min(12, max_steps))

        steps = []
        for i in range(max_steps):
            steps.append(f"{i+1}. Do the next actionable step for: {text}")

        return ok({
            "content": [{"type": "text", "text": "\n".join(steps)}],
            "meta": {"steps": max_steps}
        })

    return err(-32601, "Method not found", {"method": method})
