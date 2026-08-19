# anyquart_pydantic

[anyquart](https://github.com/EmmanuelNiyonshuti/anyquart) extension for request and response validation with [pydantic](https://docs.pydantic.dev/).

Annotate your route handlers with pydantic models and the body and response are validated automatically.

[![Tests](https://github.com/EmmanuelNiyonshuti/anyquart_pydantic/actions/workflows/tests.yml/badge.svg)](https://github.com/EmmanuelNiyonshuti/anyquart_pydantic/actions)
[![PyPI](https://img.shields.io/pypi/v/anyquart_pydantic.svg)](https://pypi.org/project/anyquart_pydantic/)
[![Python](https://img.shields.io/pypi/pyversions/anyquart_pydantic.svg)](https://pypi.org/project/anyquart_pydantic/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![t](https://img.shields.io/badge/status-maintained-yellow.svg)

## Install

```bash
pip install anyquart_pydantic
```

## Usage

```python
# app.py
from pydantic import BaseModel

from anyquart import AnyQuart
from anyquart import jsonify

from anyquart_pydantic import AnyQuartPydantic

app = AnyQuart(__name__)
AnyQuartPydantic(app)


class User(BaseModel):
    name: str
    age: int


@app.route("/users", methods=["POST"])
async def create_user(user: User) -> User:
    return jsonify(user.model_dump()), 201
```

Run it:

```bash
$ anyquart --app app:app run
$ curl -X POST http://localhost:5000/users \
    -H "Content-Type: application/json" \
    -d '{"name": "Ada", "age": 37}'

#response:
{
    "age": 37,
    "name": "Ada"
}
```

## Contributing
Contributions are very welcome.
Tests can be run with [tox](https://tox.wiki/en/latest/tutorial/getting-started.html).
To run tests on all environments in parallel `tox -p`, run test on specific environment
`tox -e py315 -- tests`. You can also use uv `uv sync`.

## License
MIT