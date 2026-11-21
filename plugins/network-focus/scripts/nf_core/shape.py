"""A tiny JSON Schema subset checker, so the schema files are the single contract for code and agents.
Supports: type, required, properties, items, enum, minItems, maxItems, minLength."""
from dataclasses import asdict, dataclass

_TYPES = {"object": dict, "array": list, "string": str, "number": (int, float), "boolean": bool}


@dataclass
class Problem:
    code: str
    where: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


def _type_ok(value, t: str) -> bool:
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number" and isinstance(value, bool):
        return False
    return isinstance(value, _TYPES[t])


def check_shape(value, schema: dict, where: str) -> list[Problem]:
    """Wrong type / missing field -> SCHEMA. Too few / too many items -> COUNT (callers may rename)."""
    t = schema.get("type")
    if t and not _type_ok(value, t):
        return [Problem("SCHEMA", where, f"{where} should be {t}, got {type(value).__name__}")]
    problems: list[Problem] = []
    if "enum" in schema and value not in schema["enum"]:
        problems.append(Problem("SCHEMA", where, f"{where} must be one of {schema['enum']}, got {value!r}"))
    if isinstance(value, str) and len(value.strip()) < schema.get("minLength", 0):
        problems.append(Problem("SCHEMA", where, f"{where} is empty"))
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                problems.append(Problem("SCHEMA", where, f"{where} is missing '{key}'"))
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                problems += check_shape(value[key], sub, f"{where}.{key}" if where else key)
    if isinstance(value, list):
        lo, hi = schema.get("minItems"), schema.get("maxItems")
        if (lo is not None and len(value) < lo) or (hi is not None and len(value) > hi):
            rng = f"{lo if lo is not None else 0}-{hi if hi is not None else 'any'}"
            problems.append(Problem("COUNT", where, f"{where} has {len(value)} items; it needs {rng}"))
        if "items" in schema:
            for i, item in enumerate(value):
                problems += check_shape(item, schema["items"], f"{where}[{i}]")
    return problems
