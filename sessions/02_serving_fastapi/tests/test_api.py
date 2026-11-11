"""The API contract, offline: status codes, error body, isolation, the SSE stream, health checks."""
import json
import sys

from conftest import ALICE, BOB

from research_assistant.api.routers.health import model_ready


def new_session(client, headers=ALICE) -> str:
    return client.post("/v1/sessions", headers=headers).json()["session_id"]


def sse_events(text: str) -> list[tuple[str, dict]]:
    """Parse a text/event-stream body into (event, data) pairs."""
    out = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        out.append((fields["event"], json.loads(fields["data"])))
    return out


def test_health_and_ready(client):
    client.app.dependency_overrides[model_ready] = lambda: True  # no provider call in tests
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json()["status"] == "ready"


def test_ready_is_503_when_the_model_is_unusable(client):
    client.app.dependency_overrides[model_ready] = lambda: False  # e.g. a revoked key
    assert client.get("/health").status_code == 200  # alive: a restart would not help
    r = client.get("/ready")
    assert r.status_code == 503 and r.json()["checks"]["model"] is False


def test_info_comes_from_the_release(client):
    info = client.get("/v1/info", headers=ALICE).json()
    assert info["version"] == "0.2.0" and info["model"].startswith("openai:") and len(info["prompt_sha256"]) == 12


def test_missing_token_is_401_problem(client):
    r = client.get("/v1/info")
    assert r.status_code == 401
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json()["request_id"] == r.headers["x-request-id"]  # the id in the body is the one in the logs


def test_empty_message_is_422(client):
    r = client.post(f"/v1/sessions/{new_session(client)}/runs", headers=ALICE, json={"message": ""})
    assert r.status_code == 422
    assert r.json()["errors"][0]["loc"] == ["body", "message"]


def test_user_id_in_body_is_rejected(client):
    r = client.post(f"/v1/sessions/{new_session(client)}/runs", headers=ALICE,
                    json={"message": "hi", "user_id": "bob"})
    assert r.status_code == 422  # extra="forbid": the user comes from the token only


def test_other_users_session_is_404(client):
    alice_session = new_session(client, ALICE)
    assert client.get(f"/v1/sessions/{alice_session}", headers=BOB).status_code == 404
    r = client.post(f"/v1/sessions/{alice_session}/runs", headers=BOB, json={"message": "hi"})
    assert r.status_code == 404  # refused before the stream starts: no agent call, no event
    assert client.get("/v1/sessions", headers=BOB).json() == []


def test_run_streams_events_in_order(client):
    session_id = new_session(client)
    r = client.post(f"/v1/sessions/{session_id}/runs", headers=ALICE, json={"message": "kWh for 12,000 kWh heat?"})
    assert r.headers["content-type"].startswith("text/event-stream")
    events = sse_events(r.text)
    assert [e for e, _ in events] == ["metadata", "step", "tool_call", "step", "tool_result",
                                      "token", "token", "step", "done"]
    done = events[-1][1]
    assert done["answer"] == "It needs 4,800 kWh." and done["model_calls"] == 2 and done["input_tokens"] == 1100
    history = client.get(f"/v1/sessions/{session_id}", headers=ALICE).json()["messages"]
    assert [m["role"] for m in history] == ["user", "assistant"]


def test_owner_is_filtered_out_of_responses(client):
    created = client.post("/v1/sessions", headers=ALICE).json()
    assert "user_id" not in created  # stored on SessionRecord, removed by the `-> Session` return type
    assert "user_id" not in client.get(f"/v1/sessions/{created['session_id']}", headers=ALICE).json()


def test_session_id_must_be_a_uuid(client):
    r = client.get("/v1/sessions/me", headers=ALICE)  # no /me route: the path matches /{session_id}
    assert r.status_code == 422 and r.json()["errors"][0]["type"] == "uuid_parsing"


def test_request_id_is_kept_from_the_client(client):
    assert client.get("/health", headers={"X-Request-ID": "abc-123"}).headers["x-request-id"] == "abc-123"


def test_agent_layer_does_not_import_fastapi():
    for name in [m for m in sys.modules if m == "fastapi" or m.startswith(("fastapi.", "research_assistant"))]:
        del sys.modules[name]
    import research_assistant.agent.agent  # noqa: F401
    import research_assistant.agent.events  # noqa: F401
    assert "fastapi" not in sys.modules
