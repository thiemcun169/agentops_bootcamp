"""Research assistant: the Session 01 agent (web search + calculator), now also served as an HTTP API.

Layers (an import only goes downwards):
    api/       HTTP only: FastAPI app, routers, dependencies, middleware, error handlers
    schemas/   request and response bodies (the API contract)
    services/  application logic with no HTTP: which user owns which session
    agent/     the agent runtime (LangChain); never imports FastAPI, so the CLI and a worker can reuse it
    core/      settings and logging, shared by every layer
"""
