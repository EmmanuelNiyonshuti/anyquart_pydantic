from __future__ import annotations

import inspect
from typing import Any, cast

import pytest
from anyquart import AnyQuart, jsonify
from anyquart.di import Needs
from anyquart.typing import TestClientProtocol as ClientProtocol
from anyquart.wrappers import Response
from pydantic import BaseModel, Field

from anyquart_pydantic import (
    AnyQuartPydantic,
    RequestValidationError,
    ResponseValidationError,
)
from anyquart_pydantic.validation import (
    BodyParam,
    ResponseParam,
    find_body_params,
    validate_request_body,
    validate_response,
)


class Item(BaseModel):
    name: str
    quantity: int


class Address(BaseModel):
    street: str
    city: str


class PositiveItem(BaseModel):
    amount: int = Field(gt=0)


class FakeRequest:
    """Minimal request stand-in returning a canned JSON body."""

    def __init__(self, data: Any) -> None:
        self._data = data

    async def get_json(self, *, silent: bool = False) -> Any:
        return self._data


@pytest.fixture
def item_response_param() -> ResponseParam:
    def handler() -> Item:
        return Item(name="x", quantity=1)

    _, response_params = find_body_params(handler)
    return response_params[0]


def test_find_body_params() -> None:
    def handler(item: Item) -> None: ...

    assert find_body_params(handler) == ([BodyParam("item", Item)], [])


def test_find_body_params_with_response_model() -> None:
    def handler(address: Address) -> Item:
        return Item(name="x", quantity=1)

    body_params, response_params = find_body_params(handler)

    assert body_params == [BodyParam("address", Address)]
    assert len(response_params) == 1
    assert response_params[0].models == (Item,)


def test_find_body_params_collection_response_model() -> None:
    def handler() -> list[Item]:
        return []

    _, response_params = find_body_params(handler)

    assert len(response_params) == 1
    assert response_params[0].models == (Item,)


def test_find_body_params_union_response_model() -> None:
    def handler() -> Item | None:
        return None

    _, response_params = find_body_params(handler)

    assert len(response_params) == 1
    assert response_params[0].models == (Item,)


def test_find_body_params_dict_response_model() -> None:
    def handler() -> dict[str, Item]:
        return {}

    _, response_params = find_body_params(handler)

    assert len(response_params) == 1
    assert response_params[0].models == (Item,)


def test_find_body_params_tuple_response_models() -> None:
    def handler() -> tuple[Address, Item]:
        return Address(street="Main", city="Town"), Item(name="x", quantity=1)

    _, response_params = find_body_params(handler)

    assert len(response_params) == 1
    assert response_params[0].models == (Address, Item)


def test_find_body_params_plain_return_has_no_response_param() -> None:
    def handler() -> int:
        return 1

    assert find_body_params(handler) == ([], [])


def test_find_body_params_skips_needs_dependency() -> None:
    def dependency() -> Item:
        return Item(name="dep", quantity=1)

    def handler(item: Item = Needs(dependency)) -> None: ...  # noqa: B008

    assert find_body_params(handler) == ([], [])


def test_find_body_params_multiple_models() -> None:
    def handler(item: Item, address: Address) -> None: ...

    assert find_body_params(handler) == (
        [
            BodyParam("item", Item),
            BodyParam("address", Address)
        ],
        []
        )


async def test_validate_request_body_single_coerces() -> None:
    request = FakeRequest({"name": "widget", "quantity": "3"})

    instances = await validate_request_body(request, [BodyParam("item", Item)])

    assert instances == {"item": Item(name="widget", quantity=3)}


async def test_validate_request_body_single_invalid() -> None:
    request = FakeRequest({"name": "widget"})

    with pytest.raises(RequestValidationError) as excinfo:
        await validate_request_body(request, [BodyParam("item", Item)])

    assert excinfo.value.errors == [
        {"loc": ["quantity"], "msg": "Field required", "type": "missing"}
    ]


async def test_validate_request_body_keyed() -> None:
    request = FakeRequest(
        {
            "item": {"name": "widget", "quantity": 1},
            "address": {"street": "Main", "city": "Town"},
        }
    )

    instances = await validate_request_body(
        request, [BodyParam("item", Item), BodyParam("address", Address)]
    )

    assert instances == {
        "item": Item(name="widget", quantity=1),
        "address": Address(street="Main", city="Town"),
    }


async def test_validate_request_body_keyed_missing_and_invalid() -> None:
    request = FakeRequest({"item": {"name": "widget"}})

    with pytest.raises(RequestValidationError) as excinfo:
        await validate_request_body(
            request, [BodyParam("item", Item), BodyParam("address", Address)]
        )

    assert excinfo.value.errors == [
        {"loc": ["item", "quantity"], "msg": "Field required", "type": "missing"},
        {"loc": ["address"], "msg": "Field required", "type": "missing"},
    ]


async def test_validate_request_body_keyed_non_object() -> None:
    request = FakeRequest([1, 2, 3])

    with pytest.raises(RequestValidationError) as excinfo:
        await validate_request_body(
            request, [BodyParam("item", Item), BodyParam("address", Address)]
        )

    assert excinfo.value.errors == [
        {
            "loc": ["body"],
            "msg": "Input should be a valid dictionary",
            "type": "dict_type",
        }
    ]


async def test_validate_request_body_missing_body() -> None:
    request = FakeRequest(None)

    with pytest.raises(RequestValidationError) as excinfo:
        await validate_request_body(request, [BodyParam("item", Item)])

    assert excinfo.value.errors == [
        {"loc": ["body"], "msg": "Field required", "type": "missing"}
    ]


async def test_valid_body_is_injected(app: AnyQuart, client: ClientProtocol) -> None:
    @app.route("/items", methods=["POST"])
    async def create_item(item: Item) -> Any:
        return jsonify(item.model_dump()), 201

    response: Response = await client.post(
        "/items", json={"name": "widget", "quantity": "3"}
    )

    assert response.status_code == 201
    assert await response.get_json() == {"name": "widget", "quantity": 3}


async def test_invalid_body_returns_422(app: AnyQuart, client: ClientProtocol) -> None:
    @app.route("/items", methods=["POST"])
    async def create_item(item: Item) -> Any:
        return jsonify(item.model_dump())

    response: Response = await client.post("/items", json={"name": "widget"})

    assert response.status_code == 422
    assert await response.get_json() == {
        "detail": [
            {"loc": ["quantity"], "msg": "Field required", "type": "missing"}
        ]
    }


async def test_missing_body_returns_422(app: AnyQuart, client: ClientProtocol) -> None:
    @app.route("/items", methods=["POST"])
    async def create_item(item: Item) -> Any:
        return jsonify(item.model_dump())

    response: Response = await client.post("/items")

    assert response.status_code == 422
    assert await response.get_json() == {
        "detail": [{"loc": ["body"], "msg": "Field required", "type": "missing"}]
    }


async def test_multiple_models_keyed_body(
    app: AnyQuart, client: ClientProtocol
) -> None:
    @app.route("/orders", methods=["POST"])
    async def create_order(item: Item, address: Address) -> Any:
        return jsonify(
            {"item": item.model_dump(), "address": address.model_dump()}
        ), 201

    response: Response = await client.post(
        "/orders",
        json={
            "item": {"name": "widget", "quantity": 1},
            "address": {"street": "Main", "city": "Town"},
        },
    )

    assert response.status_code == 201
    assert await response.get_json() == {
        "item": {"name": "widget", "quantity": 1},
        "address": {"street": "Main", "city": "Town"},
    }


async def test_multiple_models_invalid_returns_422(
    app: AnyQuart, client: ClientProtocol
) -> None:
    @app.route("/orders", methods=["POST"])
    async def create_order(item: Item, address: Address) -> Any:
        return jsonify(item.model_dump())

    response: Response = await client.post(
        "/orders", json={"item": {"name": "widget"}}
    )

    assert response.status_code == 422
    assert await response.get_json() == {
        "detail": [
            {"loc": ["item", "quantity"], "msg": "Field required", "type": "missing"},
            {"loc": ["address"], "msg": "Field required", "type": "missing"},
        ]
    }


async def test_route_without_model_is_untouched(
    app: AnyQuart, client: ClientProtocol
) -> None:
    @app.route("/ping")
    async def ping() -> Any:
        return jsonify({"pong": True})

    response: Response = await client.get("/ping")

    assert response.status_code == 200
    assert await response.get_json() == {"pong": True}


async def test_url_converter_with_body(app: AnyQuart, client: ClientProtocol) -> None:
    @app.route("/items/<int:item_id>", methods=["PUT"])
    async def update_item(item_id: int, item: Item) -> Any:
        return jsonify({"item_id": item_id, "name": item.name})

    response: Response = await client.put(
        "/items/7", json={"name": "widget", "quantity": 1}
    )

    assert response.status_code == 200
    assert await response.get_json() == {"item_id": 7, "name": "widget"}


async def test_sync_handler(app: AnyQuart, client: ClientProtocol) -> None:
    @app.route("/items", methods=["POST"])
    def create_item(item: Item) -> Any:
        return jsonify({"name": item.name, "quantity": item.quantity}), 201

    response: Response = await client.post(
        "/items", json={"name": "widget", "quantity": 2}
    )

    assert response.status_code == 201
    assert await response.get_json() == {"name": "widget", "quantity": 2}


async def test_needs_dependency_with_body(
    app: AnyQuart, client: ClientProtocol
) -> None:
    def get_prefix() -> str:
        return "pre"

    @app.route("/items", methods=["POST"])
    async def create_item(item: Item, prefix: str = Needs(get_prefix)) -> Any:
        return jsonify({"prefix": prefix, "name": item.name})

    response: Response = await client.post(
        "/items", json={"name": "widget", "quantity": 1}
    )

    assert response.status_code == 200
    assert await response.get_json() == {"prefix": "pre", "name": "widget"}


async def test_error_payload_is_json_safe(
    app: AnyQuart, client: ClientProtocol
) -> None:
    @app.route("/items", methods=["POST"])
    async def create_item(item: PositiveItem) -> Any:
        return jsonify(item.model_dump())

    response: Response = await client.post("/items", json={"amount": -1})

    assert response.status_code == 422
    detail = (await response.get_json())["detail"][0]
    assert detail == {
        "loc": ["amount"],
        "msg": "Input should be greater than 0",
        "type": "greater_than",
    }

def test_extension_init_app_is_idempotent() -> None:
    app = AnyQuart(__name__)
    AnyQuartPydantic(app)
    AnyQuartPydantic(app)


async def test_extension_wraps_pre_registered_routes() -> None:
    app = AnyQuart(__name__)
    app.config["TESTING"] = True

    @app.route("/items", methods=["POST"])
    def create_item(item: Item) -> Any:
        return jsonify(item.model_dump())

    AnyQuartPydantic(app)

    async with app.test_app() as test_app:
        client = test_app.test_client()
        response: Response = await client.post(
            "/items", json={"name": "widget", "quantity": 1}
        )
        invalid: Response = await client.post("/items", json={"name": "widget"})

    assert response.status_code == 200
    assert await response.get_json() == {"name": "widget", "quantity": 1}
    assert invalid.status_code == 422


async def test_validate_response_valid_coerces(
    item_response_param: ResponseParam
    ) -> None:
    param = item_response_param
    result = validate_response({"name": "widget", "quantity": "3"}, [param])

    assert result == {"name": "widget", "quantity": 3}


async def test_validate_response_invalid_raises(
    item_response_param: ResponseParam
    ) -> None:
    param = item_response_param

    with pytest.raises(ResponseValidationError) as excinfo:
        validate_response({"name": "widget"}, [param])

    assert excinfo.value.errors == [
        {"loc": ["quantity"], "msg": "Field required", "type": "missing"}
    ]


async def test_validate_response_skips_response_object(
    item_response_param: ResponseParam
    ) -> None:
    param = item_response_param
    response = Response(b'{"name": "widget"}')
    result = validate_response(response, [param])

    assert result is response


async def test_validate_response_skips_tuple(
    item_response_param: ResponseParam
    ) -> None:
    param = item_response_param
    result = validate_response(({"name": "widget", "quantity": 1}, 201), [param])

    assert result == ({"name": "widget", "quantity": 1}, 201)


async def test_validate_response_skips_streams(
    item_response_param: ResponseParam
    ) -> None:
    param = item_response_param
    async def stream() -> Any:
        yield {"name": "widget", "quantity": 1}

    result = validate_response(stream(), [param])

    assert inspect.isasyncgen(result)


async def test_validate_response_collection() -> None:
    def handler() -> list[Item]:
        return []

    _, response_params = find_body_params(handler)
    result = validate_response([{"name": "a", "quantity": "1"}], response_params)

    assert result == [{"name": "a", "quantity": 1}]


async def test_validate_response_union_allows_none() -> None:
    def handler() -> Item | None:
        return None

    _, params = find_body_params(handler)
    result = validate_response(None, params)

    assert result is None


async def test_valid_response_is_dumped(app: AnyQuart, client: ClientProtocol) -> None:
    @app.route("/items/<int:item_id>")  # type: ignore[type-var]
    async def get_item(item_id: int) -> Item:
        return Item(name="widget", quantity=item_id)

    response: Response = await client.get("/items/7")

    assert response.status_code == 200
    assert await response.get_json() == {"name": "widget", "quantity": 7}


async def test_valid_response_is_dumped_from_dict(
    app: AnyQuart, client: ClientProtocol
) -> None:
    @app.route("/items")
    async def get_items() -> list[Item]:
        return cast(list[Item], [{"name": "widget", "quantity": 1}])

    response: Response = await client.get("/items")

    assert response.status_code == 200
    assert await response.get_json() == [{"name": "widget", "quantity": 1}]


async def test_invalid_response_returns_500(
    app: AnyQuart, client: ClientProtocol
) -> None:
    @app.route("/items")  # type: ignore[type-var]
    async def get_item() -> Item:
        return Item(name="widget", quantity=1)

    @app.route("/broken")  # type: ignore[type-var]
    async def broken() -> Item:
        return cast(Item, {"name": "widget"})

    response: Response = await client.get("/broken")

    assert response.status_code == 500
    assert await response.get_json() == {
        "detail": [
            {"loc": ["quantity"], "msg": "Field required", "type": "missing"}
        ]
    }


async def test_response_validation_manual_response_untouched(
    app: AnyQuart, client: ClientProtocol
) -> None:
    @app.route("/items")
    async def get_item() -> Any:
        return jsonify({"name": "widget", "quantity": 1}), 202

    response: Response = await client.get("/items")

    assert response.status_code == 202
    assert await response.get_json() == {"name": "widget", "quantity": 1}
