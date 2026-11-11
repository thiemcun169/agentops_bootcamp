"""Send 5 requests at the same time to each route of examples/blocking_demo.py and print their latencies."""
import asyncio
import time

import httpx

URL = "http://127.0.0.1:8020"


async def timed(client: httpx.AsyncClient, path: str) -> float:
    started = time.perf_counter()
    await client.get(path)
    return time.perf_counter() - started


async def main() -> None:
    async with httpx.AsyncClient(base_url=URL, timeout=30) as client:
        for path in ("/async-blocking", "/async-awaiting", "/sync"):
            started = time.perf_counter()
            latencies = await asyncio.gather(*(timed(client, path) for _ in range(5)))
            each = " ".join(f"{s:.1f}" for s in sorted(latencies))
            print(f"{path:16} 5 requests: each {each} s | all done in {time.perf_counter() - started:.1f} s")


asyncio.run(main())
