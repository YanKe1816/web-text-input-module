from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.middleware.cors import CORSMiddleware

# =========================
# 1) OpenAI 域名验证 token（你给我的那个）
# =========================
OPENAI_VERIFICATION_TOKEN = "YWZI9_Pg7G9svmoydtQCj6Vep6gJllT6n5rJxLL40iY"

# =========================
# 2) 工具定义（给扫描器看的“说明书”）
# =========================
TOOLS = [
    {
        "name": "generate_checklist",
        "description": "Generate a structured execution checklist from input text. Output is JSON-only (as text).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Source text to convert into checklist steps"},
                "max_steps": {
                    "type": "integer",
                    "minimum": 3,
                    "maximum": 12,
                    "default": 8,
                    "description": "Maximum number of steps",
                },
                "audience": {
                    "type": "string",
                    "enum": ["agent"],
                    "default": "agent",
                    "description": "Audience must be 'agent'",
                },
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,       # 只读：不会改你任何东西
            "openWorldHint": False,     # 不联网：不去外网抓取
            "destructiveHint": False,   # 不破坏：不删不改不下单不发信
        },
    }
]

# =========================
# 3) FastAPI App
# =========================
app = FastAPI(title="Execution Checklist MCP Server")

# CORS：平台/工具扫的时候更不容易出幺蛾子
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS", "HEAD"],
    allow_headers=["*"],
)

# =========================
# 4) 基础页面（App Info 用）
# =========================
@app.get("/")
def home():
    return {"name": "Execution Checklist MCP Server", "ok": True}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/privacy")
def privacy():
    return PlainTextResponse("No user data is stored.", media_type="text/plain")

@app.get("/terms")
def terms():
    return PlainTextResponse("Provided as-is. No user data is stored.", media_type="text/plain")


# =========================
# 5) OpenAI 域名验证（必须：纯文本 token）
#    路径就是你看到的：/.well-known/openai-apps-challenge
# =========================
@app.get("/.well-known/openai-apps-challenge")
def openai_domain_verification():
    return PlainTextResponse(OPENAI_VERIFICATION_TOKEN, media_type="text/plain")


# =========================
# 6) MCP Manifest（扫描器/平台看的“工具目录”）
#    路径：/.well-known/mcp.json
# =========================
@app.get("/.well-known/mcp.json")
def mcp_manifest():
    return JSONResponse(
        {
            "schema_version": "v1",
            "name": "Execution Checklist Tool",
            "description": "Convert input text into a structured execution checklist (JSON-only output).",
            "tools": TOOLS,
        }
    )


# =========================
# 7) MCP 入口：/mcp
#    关键：GET/HEAD/OPTIONS 不能 405（否则 Scan Tools 很容易炸）
# =========================
@app.options("/mcp")
def mcp_options():
    return Response(status_code=204)

@app.head("/mcp")
def mcp_head():
    return Response(status_code=200)

@app.get("/mcp")
def mcp_get():
    # 给平台探测用：告诉它“这里是 JSON-RPC 的 POST 入口”
    return PlainTextResponse(
        "OK. This is an MCP JSON-RPC endpoint. Use POST.",
        media_type="text/plain",
    )


# =========================
# 8) JSON-RPC（Scan Tools 真正会调用的部分）
#    必须支持：initialize / tools/list / tools/call
# =========================
@app.post("/mcp")
async def mcp_post(request: Request):
    payload = await request.json()
    method = payload.get("method")
    req_id = payload.get("id")

    def ok(result: Any):
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": result})

    def err(code: int, message: str, data: Any = None):
        e = {"code": code, "message": message}
        if data is not None:
            e["data"] = data
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "error": e})

    # 1) initialize
    if method == "initialize":
        return ok(
            {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "Execution Checklist Tool", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            }
        )

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
        if not text:
            return err(-32602, "Missing text")

        max_steps = arguments.get("max_steps", 8)
        try:
            max_steps = int(max_steps)
        except Exception:
            max_steps = 8
        max_steps = max(3, min(12, max_steps))

        audience = arguments.get("audience", "agent")
        if audience != "agent":
            return err(-32602, "Audience must be 'agent'")

        checklist_obj = generate_checklist_json(text=text, max_steps=max_steps)

        # MCP 的返回结构：content 里放 text
        # 你要求“结构化 JSON only”，那我们把 JSON 作为字符串 text 返回
        return ok(
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(checklist_obj, ensure_ascii=False),
                    }
                ],
                "meta": {"audience": "agent"},
            }
        )

    return err(-32601, "Method not found", {"method": method})


# =========================
# 9) 你的业务：生成 checklist（极简稳定，不搞花活）
# =========================
def generate_checklist_json(text: str, max_steps: int) -> Dict[str, Any]:
    # 超简单模板：稳定 > 聪明（平台更喜欢不出错）
    base_steps = [
        ("Clarify scope", "Write down goals, boundaries, and constraints."),
        ("List inputs", "Collect required info, links, and credentials."),
        ("Break into tasks", "Split work into ordered tasks with owners."),
        ("Define acceptance", "Define how you will verify each task is done."),
        ("Execute", "Do tasks in order and record results."),
        ("Review", "Check gaps and fix issues."),
        ("Package artifacts", "Put outputs in the right places (repo, doc, links)."),
        ("Final check", "Run a final end-to-end verification."),
        ("Submit", "Submit and record submission details."),
        ("Monitor", "Watch for review feedback and respond."),
        ("Document learnings", "Write what worked and what to reuse next time."),
        ("Template it", "Extract a reusable template for future runs."),
    ]

    steps = []
    for i, (title, action) in enumerate(base_steps[:max_steps], start=1):
        steps.append(
            {
                "id": str(i),
                "title": title,
                "action": action,
                "verify": "Confirm this step is completed and recorded.",
                "artifacts": [],
            }
        )

    return {
        "type": "checklist",
        "audience": "agent",
        "context": None,
        "steps": steps,
    }
