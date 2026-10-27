"""Pytest fixtures for async testing with SQLite in-memory database."""

import asyncio
from typing import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.llm.mock_llm import MockLLMProvider
from app.stt.mock_stt import MockSTTProvider
from app.tts.mock_tts import MockTTSProvider


@pytest.fixture(scope="session")
def event_loop():
    """Creates a session-scoped asyncio event loop."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Provides an isolated async in-memory SQLite engine for each test."""
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///file:testmemdb?mode=memory&cache=shared&uri=true",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()




@pytest.fixture
async def db_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Yields a database session bound to the in-memory SQLite engine."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
def mock_stt() -> MockSTTProvider:
    return MockSTTProvider()


@pytest.fixture
def mock_llm() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.fixture
def mock_tts() -> MockTTSProvider:
    return MockTTSProvider(chunk_delay_sec=0.0)
