import os
from pathlib import Path


class Secrets:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    @classmethod
    def load(cls, path: Path = Path(".env")) -> "Secrets":
        values = {}
        if path.exists():
            for line in path.read_text().splitlines():
                key, sep, value = line.strip().partition("=")
                if sep:
                    values[key.strip()] = value.strip()
        return cls(values | dict(os.environ))

    def get(self, key: str) -> str | None:
        value = self._values.get(key)
        if not value or value == "placeholder":
            return None
        return value

    def require(self, key: str) -> str:
        value = self.get(key)
        if value is None:
            raise RuntimeError(
                f"missing required secret {key}: set it in .env"
            )
        return value
