from __future__ import annotations

__all__ = [
    "BodyParam",
    "RequestValidationError",
    "ResponseParam",
    "ResponseValidationError",
    "find_body_params",
    "validate_request_body",
    "validate_response",
]

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, get_args, get_type_hints

from anyquart import Response
from anyquart.di import build_route_handler_dependency_map
from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic_core import ErrorDetails


class RequestValidationError(Exception):
    """Raised when the request body fails validation against a handler model.

    Attributes:
        errors: Normalised validation errors, each with ``loc``, ``msg`` and
            ``type`` keys, ready for JSON serialization.
    """

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        super().__init__(f"Request validation failed with {len(errors)} error(s)")


class ResponseValidationError(Exception):
    """Raised when a handler's return value fails response validation.

    Attributes:
        errors: Normalised validation errors, each with ``loc``, ``msg`` and
            ``type`` keys, ready for JSON serialization.
    """

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        super().__init__(f"Response validation failed with {len(errors)} error(s)")


@dataclass(frozen=True)
class BodyParam:
    name: str
    model: type[BaseModel]


@dataclass(frozen=True)
class ResponseParam:
    models: tuple[type[BaseModel], ...]
    type_adapter: TypeAdapter[Any]

class RequestWithJson(Protocol):
    """The subset of a request API needed to read a JSON body."""

    async def get_json(self, *, silent: bool = False) -> Any: ...


_MISSING_BODY_ERROR: dict[str, Any] = {
    "loc": ["body"],
    "msg": "Field required",
    "type": "missing",
}

_NON_OBJECT_BODY_ERROR: dict[str, Any] = {
    "loc": ["body"],
    "msg": "Input should be a valid dictionary",
    "type": "dict_type",
}


def find_body_params(
    func: Callable[..., Any],
) -> tuple[list[BodyParam], list[ResponseParam]]:
    """Find the parameters of ``func`` annotated with a pydantic model.

    Arguments:
        func: The route handler to inspect.

    Returns:
        A tuple of the body parameters declared by the handler and the
        response parameters derived from its return annotation, each
        possibly empty.
    """
    # Parameters resolved by dependency injection are ignored
    dependency_parameters = frozenset(build_route_handler_dependency_map(func))
    body_params: list[BodyParam] = []
    response_params: list[ResponseParam] = []
    type_hints = get_type_hints(func)
    for name, annot in type_hints.items():
        if name in dependency_parameters:
            continue
        if name == "return":
            models = tuple(_find_models(annot))
            if models:
                response_params.append(
                    ResponseParam(models=models, type_adapter=TypeAdapter[Any](annot))
                )
        elif isinstance(annot, type) and issubclass(annot, BaseModel):
            body_params.append(BodyParam(name, annot))

    return body_params, response_params

def _find_models(annotation: Any) -> list[type[BaseModel]]:
    """Collect the pydantic models nested in ``annotation``."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    models: list[type[BaseModel]] = []
    for argument in get_args(annotation):
        models.extend(_find_models(argument))
    return models

async def validate_request_body(
    request: RequestWithJson, body_params: list[BodyParam]
) -> dict[str, BaseModel]:
    """Validate the JSON body of ``request`` against the body parameters.

    Arguments:
        request: The incoming request whose JSON body is validated.
        body_params: The body parameters to validate against.

    Returns:
        A mapping of parameter name to its validated model instance.

    Raises:
        RequestValidationError: If the request body is missing or fails
            validation against any of the models.
    """
    data = await request.get_json(silent=True)
    if data is None:
        raise RequestValidationError([_MISSING_BODY_ERROR])

    if len(body_params) == 1:
        param = body_params[0]
        try:
            return {param.name: param.model.model_validate(data)}
        except ValidationError as error:
            raise RequestValidationError(
                [_error_payload(detail) for detail in error.errors()]
            ) from error

    if not isinstance(data, dict):
        raise RequestValidationError([_NON_OBJECT_BODY_ERROR])

    instances: dict[str, BaseModel] = {}
    errors: list[dict[str, Any]] = []
    for body_param in body_params:
        if body_param.name not in data:
            errors.append(
                {"loc": [body_param.name], "msg": "Field required", "type": "missing"}
            )
            continue
        try:
            instances[body_param.name] = body_param.model.model_validate(
                data[body_param.name]
            )
        except ValidationError as error:
            errors.extend(
                _error_payload(detail, prefix=(body_param.name,))
                for detail in error.errors()
            )

    if errors:
        raise RequestValidationError(errors)
    return instances


def _error_payload(
    detail: ErrorDetails, prefix: tuple[str, ...] = ()
) -> dict[str, Any]:
    """Normalise a pydantic error detail to a JSON-serialisable dictionary.
    """
    return {
        "loc": [*prefix, *detail["loc"]],
        "msg": detail["msg"],
        "type": detail["type"],
    }


def validate_response(
    result: Any, response_params: list[ResponseParam]
) -> Any:
    """Validate a handler's return value against the response parameters.

    Arguments:
        result: The value returned by the route handler.
        response_params: The response parameters to validate against.

    Returns:
        A JSON-serialisable representation of ``result``. Manual responses
        (e.g. ``Response`` objects, ``(body, status)`` tuples, streams) are
        returned unchanged.

    Raises:
        ResponseValidationError: If ``result`` fails validation against any of
            the response models.
    """
    if not response_params or isinstance(result, (Response, tuple)):
        return result
    if inspect.isgenerator(result) or inspect.isasyncgen(result):
        return result

    for response_param in response_params:
        try:
            validated = response_param.type_adapter.validate_python(result)
        except ValidationError as error:
            raise ResponseValidationError(
                [_error_payload(detail) for detail in error.errors()]
            ) from error
        result = response_param.type_adapter.dump_python(validated, mode="json")
    return result
