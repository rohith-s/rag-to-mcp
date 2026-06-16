"""
UC-MCP - Plain HTTP MCP Server

Implements a small JSON-RPC 2.0 MCP-style server with one tool:
query_policy_documents.
"""

import argparse
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any


BASE_DIR = os.path.dirname(__file__)
RAG_DIR = os.path.abspath(os.path.join(BASE_DIR, "../uc-rag"))
DOCS_DIR = os.path.abspath(os.path.join(BASE_DIR, "../data/policy-documents"))

REFUSAL_TEXT = (
    "This question is outside the scope of the CMC HR Leave Policy, "
    "CMC IT Acceptable Use Policy, and CMC Finance Reimbursement Policy. "
    "Please contact the relevant department for guidance."
)

POLICY_FILES = {
    "policy_hr_leave.txt": "CMC HR Leave Policy",
    "policy_it_acceptable_use.txt": "CMC IT Acceptable Use Policy",
    "policy_finance_reimbursement.txt": "CMC Finance Reimbursement Policy",
}

STOP_WORDS = {
    "a",
    "about",
    "all",
    "am",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "the",
    "to",
    "use",
    "what",
    "when",
    "who",
    "with",
}


def _load_rag_query():
    """Prefer participant RAG, then stub RAG, while keeping MCP stdlib-safe."""
    sys.path.insert(0, RAG_DIR)
    for module_name in ("rag_server", "stub_rag"):
        try:
            module = __import__(module_name)
            query = getattr(module, "query")
            print(f"[mcp_server] Using {module_name}.py")
            return query
        except Exception as exc:
            print(f"[mcp_server] {module_name}.py unavailable: {exc}")
    print("[mcp_server] Using local policy lookup fallback")
    return None


try:
    from llm_adapter import call_llm
except Exception:
    call_llm = None


RAG_QUERY = _load_rag_query()


TOOL_DEFINITION = {
    "name": "query_policy_documents",
    "description": (
        "Answers questions only about the CMC HR Leave Policy, CMC IT "
        "Acceptable Use Policy, and CMC Finance Reimbursement Policy. Returns "
        "answers grounded in those policy documents with cited sources. "
        "Questions outside these three documents return a refusal template "
        "with isError true."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": (
                    "A non-empty question about the CMC HR Leave Policy, "
                    "CMC IT Acceptable Use Policy, or CMC Finance "
                    "Reimbursement Policy."
                ),
                "minLength": 1,
            }
        },
        "required": ["question"],
    },
}


def _content(text: str, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in STOP_WORDS and len(token) > 1
    }


def _split_sections(text: str) -> list[str]:
    sections = re.split(r"\n(?=\d+\.\s+[A-Z])", text)
    return [section.strip() for section in sections if section.strip()]


def _load_policy_sections() -> list[dict[str, Any]]:
    sections = []
    for file_name, policy_name in POLICY_FILES.items():
        path = os.path.join(DOCS_DIR, file_name)
        try:
            with open(path, encoding="utf-8") as policy_file:
                text = policy_file.read()
        except OSError:
            continue
        for index, section in enumerate(_split_sections(text)):
            sections.append(
                {
                    "doc_name": file_name,
                    "policy_name": policy_name,
                    "chunk_index": index,
                    "text": section,
                    "tokens": _tokenize(section),
                }
            )
    return sections


POLICY_SECTIONS = _load_policy_sections()


def _local_policy_query(question: str) -> dict[str, Any]:
    question_tokens = _tokenize(question)
    if not question_tokens:
        return {"answer": REFUSAL_TEXT, "cited_chunks": [], "refused": True}

    question_lower = question.lower()
    scored = []
    for section in POLICY_SECTIONS:
        overlap = question_tokens & section["tokens"]
        score = len(overlap)
        section_text = section["text"].lower()

        if (
            "personal" in question_tokens
            and {"phone", "device", "files", "file"} & question_tokens
            and section["doc_name"] == "policy_it_acceptable_use.txt"
            and ("personal devices" in section_text or "data handling" in section_text)
        ):
            score += 5

        if (
            {"work", "files", "file", "data"} & question_tokens
            and section["doc_name"] == "policy_it_acceptable_use.txt"
            and ("sensitive cmc data" in section_text or "classified or restricted" in section_text)
        ):
            score += 4

        if "budget" in question_lower or "forecast" in question_lower:
            score = 0

        if score:
            scored.append((score, section))

    scored.sort(key=lambda item: item[0], reverse=True)
    best = [section for score, section in scored[:2] if score >= 2]
    if not best:
        return {"answer": REFUSAL_TEXT, "cited_chunks": [], "refused": True}

    answer_parts = []
    cited_chunks = []
    for section in best:
        excerpt = " ".join(section["text"].split())
        if len(excerpt) > 700:
            excerpt = excerpt[:700].rsplit(" ", 1)[0] + "..."
        answer_parts.append(
            f"[{section['policy_name']}, chunk {section['chunk_index']}] {excerpt}"
        )
        cited_chunks.append(
            {
                "doc_name": section["doc_name"],
                "chunk_index": section["chunk_index"],
                "score": 1.0,
            }
        )

    return {
        "answer": "Relevant policy context:\n\n" + "\n\n".join(answer_parts),
        "cited_chunks": cited_chunks,
        "refused": False,
    }


def _format_answer(result: dict[str, Any]) -> str:
    answer = str(result.get("answer") or "").strip()
    cited_chunks = result.get("cited_chunks") or []
    if not cited_chunks:
        return answer or REFUSAL_TEXT

    sources = []
    for chunk in cited_chunks:
        doc = chunk.get("doc_name", "unknown document")
        index = chunk.get("chunk_index", "unknown")
        sources.append(f"{doc}::chunk_{index}")
    return f"{answer}\n\nSources: {', '.join(sources)}"


def query_policy_documents(question: str) -> dict[str, Any]:
    """
    Call the RAG layer or local fallback and return MCP content format.
    """
    if not isinstance(question, str) or not question.strip():
        return _content("Question must be a non-empty string.", is_error=True)

    try:
        if RAG_QUERY is not None:
            result = RAG_QUERY(question.strip(), llm_call=call_llm)
        else:
            result = _local_policy_query(question.strip())
    except Exception as exc:
        print(f"[mcp_server] RAG query failed, using local fallback: {exc}")
        try:
            result = _local_policy_query(question.strip())
        except Exception as fallback_exc:
            return _content(f"Policy query failed: {fallback_exc}", is_error=True)

    refused = bool(result.get("refused"))
    text = _format_answer(result)
    return _content(text, is_error=refused)


def _jsonrpc_result(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _jsonrpc_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


class MCPHandler(BaseHTTPRequestHandler):
    """HTTP request handler implementing JSON-RPC 2.0 over POST."""

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        req_id = None
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)
            try:
                request = json.loads(raw_body.decode("utf-8"))
            except json.JSONDecodeError:
                self._send_json(_jsonrpc_error(None, -32700, "Parse error"))
                return

            if not isinstance(request, dict):
                self._send_json(_jsonrpc_error(None, -32600, "Invalid Request"))
                return

            req_id = request.get("id")
            method = request.get("method")
            if request.get("jsonrpc") != "2.0" or not isinstance(method, str):
                self._send_json(_jsonrpc_error(req_id, -32600, "Invalid Request"))
                return

            if method == "tools/list":
                self._send_json(_jsonrpc_result(req_id, {"tools": [TOOL_DEFINITION]}))
                return

            if method == "tools/call":
                params = request.get("params") or {}
                if not isinstance(params, dict):
                    self._send_json(_jsonrpc_error(req_id, -32602, "Invalid params"))
                    return

                tool_name = params.get("name")
                if tool_name != "query_policy_documents":
                    self._send_json(_jsonrpc_error(req_id, -32601, "Tool not found"))
                    return

                arguments = params.get("arguments") or {}
                if not isinstance(arguments, dict):
                    self._send_json(_jsonrpc_error(req_id, -32602, "Invalid params"))
                    return

                question = arguments.get("question")
                if not isinstance(question, str) or not question.strip():
                    self._send_json(
                        _jsonrpc_result(
                            req_id,
                            _content("Question must be a non-empty string.", is_error=True),
                        )
                    )
                    return

                self._send_json(_jsonrpc_result(req_id, query_policy_documents(question)))
                return

            self._send_json(_jsonrpc_error(req_id, -32601, "Method not found"))
        except Exception as exc:
            self._send_json(_jsonrpc_error(req_id, -32603, f"Internal error: {exc}"))

    def log_message(self, format, *args) -> None:
        print(f"[mcp_server] {args[0]} {args[1]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="UC-MCP Plain HTTP MCP Server")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    args = parser.parse_args()

    server = HTTPServer(("localhost", args.port), MCPHandler)
    print(f"[mcp_server] MCP server running on http://localhost:{args.port}")
    print(f"[mcp_server] Test with: python3 test_client.py --port {args.port}")
    print("[mcp_server] Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[mcp_server] Stopped.")


if __name__ == "__main__":
    main()
