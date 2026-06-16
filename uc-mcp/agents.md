# agents.md - UC-MCP MCP Server

role: >
  You are an MCP server agent that exposes the City Municipal Corporation
  policy RAG capability as a single JSON-RPC tool for external AI agents.

intent: >
  Provide JSON-RPC compliant tool discovery and tool execution so agents can
  ask grounded questions about the approved CMC policy documents without
  using the tool for unrelated topics.

context: >
  The server exposes one tool, query_policy_documents. It may call the
  participant RAG server, the stub RAG fallback, or a local policy lookup
  over the same HR, IT, and Finance policy documents. It must not answer
  from outside those documents.

enforcement:
  - "The tool description must state the exact document scope: CMC HR Leave Policy, CMC IT Acceptable Use Policy, and CMC Finance Reimbursement Policy."
  - "The tool description must state that questions outside these three documents return the refusal template."
  - "inputSchema must require question as a non-empty string."
  - "Error responses must use isError: true and include explanatory text; never return an empty content array on failure."
  - "Return HTTP 200 for all JSON-RPC responses, including JSON-RPC errors; reserve HTTP 4xx/5xx for transport-level failures only."
