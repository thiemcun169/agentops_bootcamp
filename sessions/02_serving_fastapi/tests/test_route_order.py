"""The route-order trap of FastAPI ("Order matters" in the docs), shown on two small routers."""
from uuid import UUID

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient


def make_app(me_first: bool) -> TestClient:
    router = APIRouter(prefix="/sessions")

    def me() -> dict:
        return {"route": "me"}

    def by_id(session_id: UUID) -> dict:
        return {"route": "by_id"}

    routes = [("/me", me), ("/{session_id}", by_id)]
    for path, fn in routes if me_first else reversed(routes):
        router.add_api_route(path, fn)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_me_declared_after_the_parameter_route_never_runs():
    r = make_app(me_first=False).get("/sessions/me")
    assert r.status_code == 422  # "me" was parsed as a session_id (UUID)


def test_me_declared_first_works():
    assert make_app(me_first=True).get("/sessions/me").json() == {"route": "me"}
