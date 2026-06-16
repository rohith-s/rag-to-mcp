# skills.md - UC-MCP MCP Server

skills:
  - name: query_policy_documents
    description: >
      Execute the query_policy_documents MCP tool for questions about the CMC
      HR Leave Policy, IT Acceptable Use Policy, and Finance Reimbursement
      Policy only.
    input: >
      A non-empty question string supplied through tools/call arguments.
    output: >
      MCP result object with content as a non-empty text array and isError
      set to false for grounded answers or true for refusals and failures.
    error_handling: >
      If the question is empty, out of scope, refused by RAG, or raises an
      exception, return explanatory text with isError: true. Do not return an
      empty content array.

  - name: serve_mcp
    description: >
      Start a plain HTTP JSON-RPC server that supports tools/list and
      tools/call for the query_policy_documents tool.
    input: >
      HTTP POST request with a JSON-RPC 2.0 body. The port is configurable
      and defaults to 8765.
    output: >
      JSON-RPC 2.0 response returned over HTTP 200 for valid JSON-RPC
      handling, including method errors.
    error_handling: >
      Unknown methods return JSON-RPC error -32601, malformed JSON returns
      -32700, invalid requests return -32600, invalid params return -32602,
      and unknown tools return -32601.
