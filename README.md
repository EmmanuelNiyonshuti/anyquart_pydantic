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

Here is a simple example:
```python
# app.py
from pydantic import BaseModel

from anyquart import AnyQuart
from anyquart import jsonify

from anyquart_pydantic import AnyQuartPydantic

app = AnyQuart(__name__)
AnyQuartPydantic(app)


class User(BaseModel):
    email: str

class UserIn(User):
    password: str
    username: str | None = None

class UserOut(User):
    uid: str
    username: str

@app.route("/users", methods=["POST"])
async def create_user(user: UserIn) -> UserOut:
    if user.username is None:
        user.username = user.email.split("@")[0]
    # do other stuffs(e.g: save to the database)
    #
    # and return a new registered user with a generated uuid primary key from the database
    new_user = UserOut(
        uid="66b652e0-f114-46d7-b426-e0601233bab2",
        username=user.username
    )
    return new_user, 201
```

Run the application:

```bash
$ anyquart --app app:app run
```
send a request:
```bash
$ curl -X POST http://localhost:5000/users \
    -H "Content-Type: application/json" \
    -d '{"email": "foo@bar.com", "password": "super_secret!"}'

#response:
{
    "uid": "66b652e0-f114-46d7-b426-e0601233bab2",
    "username": "foo"
}
```

## Contributing
Contributions are very welcome.
Tests can be run with [tox](https://tox.wiki/en/latest/tutorial/getting-started.html).
To run tests on all environments in parallel `tox -p`, run test on specific environment
`tox -e py315 -- tests`. You can also use uv `uv sync`.

## License
MIT
