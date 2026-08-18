# anyquart_pydantic

[anyquart](https://github.com/EmmanuelNiyonshuti/anyquart) extension for request and response validation with [pydantic](https://docs.pydantic.dev/).

Annotate your route handlers with pydantic models and the body and response are validated automatically.

## Install

```bash
pip install anyquart_pydantic
```

## Usage

```python
# app.py
from anyquart import AnyQuart
from pydantic import BaseModel
from anyquart_pydantic import AnyQuartPydantic

app = AnyQuart(__name__)
AnyQuartPydantic(app)


class User(BaseModel):
    name: str
    age: int


@app.route("/users", methods=["POST"])
async def create_user(user: User) -> User:
    return user
```

Run it:

```bash
$ anyquart --app app:app run
$ curl -X POST http://localhost:5000/users \
    -H "Content-Type: application/json" \
    -d '{"name": "Ada", "age": 37}'
```

## License
MIT