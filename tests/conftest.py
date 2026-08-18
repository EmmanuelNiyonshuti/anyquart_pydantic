from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from anyquart import AnyQuart
from anyquart.typing import TestClientProtocol as ClientProtocol

from anyquart_pydantic import AnyQuartPydantic


@pytest.fixture
def app() -> AnyQuart:
    app = AnyQuart(__name__)
    app.config["TESTING"] = True
    AnyQuartPydantic(app)
    return app


@pytest.fixture
async def client(app: AnyQuart) -> AsyncIterator[ClientProtocol]:
    async with app.test_app() as test_app:
        yield test_app.test_client()
