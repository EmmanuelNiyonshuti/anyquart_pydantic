from __future__ import annotations

import weakref
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar, cast

from anyquart import AnyQuart, request

from .validation import (
    RequestValidationError,
    ResponseValidationError,
    find_body_params,
    validate_request_body,
    validate_response,
)

_P = ParamSpec("_P")
_R = TypeVar("_R")

_initialized_apps: weakref.WeakSet[AnyQuart] = weakref.WeakSet()


class AnyQuartPydantic:
    """An `anyquart.AnyQuart` extension adding pydantic validation.

    Register the extension against any anyquart app to enable it:

        from anyquart import AnyQuart
        from anyquart_pydantic import AnyQuartPydantic

        app = AnyQuart(__name__)
        AnyQuartPydantic(app)

    Example:
        .. code-block:: python

            from pydantic import BaseModel

            class User(BaseModel):
                name: str
                age: int

            @app.route("/users", methods=["POST"])
            async def create_user(user: User):
                return {"name": user.name, "age": user.age}
    """

    def __init__(self, app: AnyQuart | None = None) -> None:
        if app is not None:
            self.init_app(app)

    def init_app(self, app: AnyQuart) -> None:
        """Register pydantic validation with ``app``.

        This is a no-op on subsequent calls for the same app.
        """
        if app in _initialized_apps:
            return
        _initialized_apps.add(app)

        app.register_error_handler(
            RequestValidationError, self._handle_validation_error
        )
        app.register_error_handler(
            ResponseValidationError, self._handle_response_validation_error
        )
        # Shadow add_url_rule so every route registration is wrapped.
        app.add_url_rule = self._wrap_add_url_rule(app, app.add_url_rule)
        self._wrap_existing_view_functions(app)

    def _wrap_add_url_rule(
        self,
        app: AnyQuart,
        add_url_rule: Callable[..., Any],
    ) -> Callable[..., Any]:
        @wraps(add_url_rule)
        def wrapper(
            rule: str,
            endpoint: str | None = None,
            view_func: Callable[..., Any] | None = None,
            **options: Any,
        ) -> None:
            if view_func is not None:
                view_func = self._wrap_view_func(
                    app, view_func, rule, options.get("defaults")
                )
            add_url_rule(rule, endpoint, view_func, **options)

        return wrapper

    def _wrap_existing_view_functions(self, app: AnyQuart) -> None:
        """Wrap routes registered before the extension was initialized."""
        for endpoint, view_func in app.view_functions.items():
            rule = self._rule_for_endpoint(app, endpoint)
            if rule is not None:
                app.view_functions[endpoint] = self._wrap_view_func(
                    app, cast(Callable[..., Awaitable[Any]], view_func), rule
                )

    def _wrap_view_func(
        self,
        app: AnyQuart,
        view_func: Callable[_P, Awaitable[_R]],
        rule: str,
        defaults: dict[str, Any] | None = None,
    ) -> Callable[_P, Awaitable[_R]]:
        body_params, response_params = find_body_params(view_func)
        if not body_params and not response_params:
            return view_func

        @wraps(view_func)
        async def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            if body_params:
                instances = await validate_request_body(request, body_params)
                kwargs.update(instances)
            result = await app.ensure_async(view_func)(*args, **kwargs)
            return validate_response(result, response_params)

        return wrapper

    @staticmethod
    def _rule_for_endpoint(app: AnyQuart, endpoint: str) -> str | None:
        for rule in app.url_map.iter_rules(endpoint):
            return rule.rule
        return None

    @staticmethod
    async def _handle_validation_error(
        error: RequestValidationError,
    ) -> tuple[dict[str, Any], int]:
        return {"detail": error.errors}, 422

    @staticmethod
    async def _handle_response_validation_error(
        error: ResponseValidationError,
    ) -> tuple[dict[str, Any], int]:
        return {"detail": error.errors}, 500
