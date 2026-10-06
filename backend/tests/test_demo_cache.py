import asyncio
import time

import pytest

from app.db import BankStore


def make_store(build):
    store = object.__new__(BankStore)
    store._demo_cache = None
    store._demo_refresh = None
    store._build_demo_scenarios = build.__get__(store)
    return store


def build_counting(results):
    async def build(self):
        results.append(1)
        await asyncio.sleep(0.05)
        value = [{"scenario": "n", "built": len(results)}]
        self._demo_cache = (time.monotonic(), value)
        return value

    return build


@pytest.mark.anyio
async def test_first_call_builds_and_the_next_calls_use_the_cache():
    builds: list[int] = []
    store = make_store(build_counting(builds))
    first = await store.demo_scenarios()
    second = await store.demo_scenarios()
    assert first == second
    assert len(builds) == 1


@pytest.mark.anyio
async def test_an_old_cache_is_returned_at_once_and_rebuilt_in_the_background():
    builds: list[int] = []
    store = make_store(build_counting(builds))
    await store.demo_scenarios()
    old = store._demo_cache[1]
    store._demo_cache = (time.monotonic() - BankStore.DEMO_CACHE_SECONDS - 1, old)

    started = time.monotonic()
    answer = await store.demo_scenarios()
    assert time.monotonic() - started < 0.04, "the visitor must not wait for the rebuild"
    assert answer == old

    await store._demo_refresh
    assert len(builds) == 2
    assert (await store.demo_scenarios())[0]["built"] == 2


@pytest.mark.anyio
async def test_many_visitors_during_a_rebuild_start_only_one():
    builds: list[int] = []
    store = make_store(build_counting(builds))
    await store.demo_scenarios()
    store._demo_cache = (time.monotonic() - BankStore.DEMO_CACHE_SECONDS - 1, store._demo_cache[1])
    await asyncio.gather(*[store.demo_scenarios() for _ in range(10)])
    await store._demo_refresh
    assert len(builds) == 2


@pytest.mark.anyio
async def test_a_failed_rebuild_keeps_serving_the_cached_answer():
    store = make_store(build_counting([]))
    await store.demo_scenarios()
    cached = store._demo_cache[1]

    async def broken(self):
        raise RuntimeError("database down")

    store._build_demo_scenarios = broken.__get__(store)
    store._demo_cache = (time.monotonic() - BankStore.DEMO_CACHE_SECONDS - 1, cached)
    assert await store.demo_scenarios() == cached
    await store._demo_refresh
    assert await store.demo_scenarios() == cached
