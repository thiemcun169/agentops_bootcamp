"""Extension: what a blocking call inside `async def` does to every other request.

time.sleep(1) stands for any blocking call that takes 1 s: a sync SDK call, requests.get, agent.invoke(...).
    uv run fastapi run examples/blocking_demo.py --port 8020
    uv run python examples/concurrent_requests.py
"""
import asyncio
import time

from fastapi import FastAPI

app = FastAPI(title="Blocking demo")


@app.get("/async-blocking")
async def async_blocking() -> dict:
    time.sleep(1)  # WRONG: runs on the event loop thread; nothing else is served for 1 s
    return {"ok": True}


@app.get("/async-awaiting")
async def async_awaiting() -> dict:
    await asyncio.sleep(1)  # an awaitable call (like agent.ainvoke / agent.astream): the loop serves others meanwhile
    return {"ok": True}


@app.get("/sync")
def sync() -> dict:
    time.sleep(1)  # a plain `def` route runs in a thread pool, so blocking here does not stop the loop
    return {"ok": True}
