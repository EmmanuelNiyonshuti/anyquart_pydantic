from __future__ import annotations

from typing import Any, cast

import pytest
from anyquart import AnyQuart, jsonify
from anyquart.typing import TestClientProtocol as ClientProtocol
from anyquart.wrappers import Response
from pydantic import BaseModel

from anyquart_pydantic import (
    AnyQuartPydantic,
    RequestValidationError,
    ResponseValidationError,
)


class Item(BaseModel):
    name: str
    quantity: int


@pytest.fixture
def app() -> AnyQuart:
    app = AnyQuart(__name__)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def extension(app: AnyQuart) -> AnyQuartPydantic:
    return AnyQuartPydantic(app)


def _registered_handlers(app: AnyQuart) -> dict[type[Exception], Any]:
    return app.error_handler_spec[None][None]


def test_init_app_registers_error_handlers(app: AnyQuart) -> None:
    extension = AnyQuartPydantic(app)

    handlers = _registered_handlers(app)

    assert handlers[RequestValidationError] == extension._handle_validation_error
    assert (
        handlers[ResponseValidationError] == extension._handle_response_validation_error
    )


async def test_initialize_extension_via_app_factory() -> None:
    anyquart_pydantic = AnyQuartPydantic()

    def create_app() -> AnyQuart:
        app = AnyQuart(__name__)
        anyquart_pydantic.init_app(app)
        return app

    app = create_app()

    @app.get("/")
    async def home():
        return {"msg": "Hello"}

    client = app.test_client()
    response = await client.get("/")
    assert response.status_code == 200
    assert await response.json == {"msg": "Hello"}


def test_init_app_is_idempotent(app: AnyQuart) -> None:
    AnyQuartPydantic(app)
    wrapped = app.add_url_rule

    AnyQuartPydantic(app)

    assert app.add_url_rule == wrapped
    assert len(app.error_handler_spec[None][None]) == 2


async def test_handle_validation_error_returns_422() -> None:
    response, status = await AnyQuartPydantic._handle_validation_error(
        RequestValidationError([{"loc": ["quantity"], "msg": "x", "type": "y"}])
    )

    assert status == 422
    assert response == {"detail": [{"loc": ["quantity"], "msg": "x", "type": "y"}]}


async def test_handle_response_validation_error_returns_500() -> None:
    response, status = await AnyQuartPydantic._handle_response_validation_error(
        ResponseValidationError([{"loc": ["quantity"], "msg": "x", "type": "y"}])
    )

    assert status == 500
    assert response == {"detail": [{"loc": ["quantity"], "msg": "x", "type": "y"}]}


def test_wrap_view_func_returns_identity_without_models(
    app: AnyQuart, extension: AnyQuartPydantic
) -> None:
    async def ping() -> dict[str, Any]:
        return {"pong": True}

    wrapped = extension._wrap_view_func(app, ping, "/ping")

    assert wrapped is ping


def test_wrap_view_func_wraps_body_model(
    app: AnyQuart, extension: AnyQuartPydantic
) -> None:
    async def create_item(item: Item) -> Any:
        return jsonify(item.model_dump())

    wrapped = extension._wrap_view_func(app, create_item, "/items", defaults=None)

    assert wrapped is not create_item
    assert wrapped.__name__ == "create_item"


def test_wrap_view_func_wraps_response_model(
    app: AnyQuart, extension: AnyQuartPydantic
) -> None:
    async def get_item() -> Item:
        return Item(name="widget", quantity=1)

    wrapped = extension._wrap_view_func(app, get_item, "/items", defaults=None)

    assert wrapped is not get_item
    assert wrapped.__name__ == "get_item"


def test_wrap_add_url_rule_wraps_route(
    app: AnyQuart, extension: AnyQuartPydantic
) -> None:
    async def ping() -> dict[str, Any]:
        return {"pong": True}

    extension._wrap_add_url_rule(app, app.add_url_rule)("/ping", view_func=ping)

    assert _rule_for_endpoint(app, "ping") == "/ping"


def test_wrap_existing_view_functions_wraps_pre_registered(app: AnyQuart) -> None:
    @app.route("/items", methods=["POST"])
    async def create_item(item: Item) -> Any:
        return jsonify(item.model_dump())

    original = app.view_functions["create_item"]

    AnyQuartPydantic(app)

    assert app.view_functions["create_item"] is not original


def test_wrap_existing_view_functions_skips_unannotated(app: AnyQuart) -> None:
    @app.route("/ping")
    async def ping() -> dict[str, Any]:
        return {"pong": True}

    original = app.view_functions["ping"]

    AnyQuartPydantic(app)

    assert app.view_functions["ping"] is original


async def test_error_handlers_are_active(
    app: AnyQuart, extension: AnyQuartPydantic, client: ClientProtocol
) -> None:
    @app.route("/items", methods=["POST"])
    async def create_item(item: Item) -> Any:
        return jsonify(item.model_dump())

    bad_request: Response = await client.post("/items", json={"name": "widget"})

    assert bad_request.status_code == 422

    @app.route("/broken")  # type: ignore[type-var]
    async def broken() -> Item:
        return cast(Item, {"name": "widget"})

    bad_response: Response = await client.get("/broken")

    assert bad_response.status_code == 500
    assert await bad_response.get_json() == {
        "detail": [{"loc": ["quantity"], "msg": "Field required", "type": "missing"}]
    }


async def _run(coro: Any) -> tuple[dict[str, Any], int]:
    return await coro


def _rule_for_endpoint(app: AnyQuart, endpoint: str) -> str | None:
    for rule in app.url_map.iter_rules(endpoint):
        return rule.rule
    return None
