"""Postgres-backed FSM storage for aiogram.

Behaves exactly like aiogram's MemoryStorage while the bot is running (an
in-process dict is the source of truth), and writes every change through to the
``fsm_state`` table. After a restart/deploy the first access for a user loads
their state back from the table, so half-finished entries and inline-button
flows survive deploys instead of silently dying.

Persistence is best-effort: a DB or pickle error is logged and the bot keeps
working from memory, i.e. never worse than plain MemoryStorage.
"""
from __future__ import annotations

import asyncio
import copy
import logging
import pickle
from typing import Any, Mapping

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

STALE_DAYS = 7  # rows untouched this long are dropped at startup


def _key(k: StorageKey) -> str:
    return ":".join(
        str(x) if x is not None else ""
        for x in (k.bot_id, k.chat_id, k.user_id, k.thread_id, k.business_connection_id, k.destiny)
    )


class PgStorage(BaseStorage):
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._cache: dict[str, tuple[str | None, dict[str, Any]]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def setup(self) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE IF NOT EXISTS fsm_state ("
                " k TEXT PRIMARY KEY,"
                " state TEXT,"
                " data BYTEA,"
                " updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            ))
            res = await conn.execute(text(
                f"DELETE FROM fsm_state WHERE updated_at < now() - interval '{STALE_DAYS} days'"
            ))
            count = (await conn.execute(text("SELECT count(*) FROM fsm_state"))).scalar()
        logger.info(f"FSM storage ready (Postgres): {count} saved sessions, {res.rowcount} stale removed")

    def _lock(self, k: str) -> asyncio.Lock:
        lock = self._locks.get(k)
        if lock is None:
            lock = self._locks[k] = asyncio.Lock()
        return lock

    async def _load(self, k: str) -> tuple[str | None, dict[str, Any]]:
        if k in self._cache:
            return self._cache[k]
        state, data = None, {}
        try:
            async with self._engine.connect() as conn:
                row = (await conn.execute(
                    text("SELECT state, data FROM fsm_state WHERE k = :k"), {"k": k}
                )).first()
            if row is not None:
                state = row[0]
                data = pickle.loads(row[1]) if row[1] else {}
        except Exception as e:
            logger.warning(f"FSM load failed for {k}: {e}")
        # another coroutine may have filled the cache while we awaited
        return self._cache.setdefault(k, (state, data))

    async def _persist(self, k: str) -> None:
        async with self._lock(k):
            state, data = self._cache.get(k, (None, {}))
            try:
                async with self._engine.begin() as conn:
                    if state is None and not data:
                        await conn.execute(text("DELETE FROM fsm_state WHERE k = :k"), {"k": k})
                    else:
                        await conn.execute(text(
                            "INSERT INTO fsm_state (k, state, data, updated_at)"
                            " VALUES (:k, :s, :d, now())"
                            " ON CONFLICT (k) DO UPDATE SET state = EXCLUDED.state,"
                            " data = EXCLUDED.data, updated_at = now()"
                        ), {"k": k, "s": state, "d": pickle.dumps(data)})
            except Exception as e:
                logger.warning(f"FSM persist failed for {k} (kept in memory): {e}")

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        k = _key(key)
        _, data = await self._load(k)
        value = state.state if isinstance(state, State) else state
        self._cache[k] = (value, data)
        await self._persist(k)

    async def get_state(self, key: StorageKey) -> str | None:
        state, _ = await self._load(_key(key))
        return state

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        if not isinstance(data, dict):
            raise TypeError(f"Data must be a dict, got {type(data).__name__}")
        k = _key(key)
        state, _ = await self._load(k)
        self._cache[k] = (state, copy.copy(data))
        await self._persist(k)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        _, data = await self._load(_key(key))
        return copy.copy(data)

    async def close(self) -> None:
        pass
