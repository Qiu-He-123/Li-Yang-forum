from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    code: int = 0
    msg: str = "success"
    data: Any = None


def ok(data: Any = None) -> dict[str, Any]:
    # 注意：不能用 `data or {}`，空列表/空字符串/0/False 都会被替换成 {}，
    # 导致前端拿到 {} 而不是 []，调用 .filter 时报 "filter is not a function"。
    return {"code": 0, "msg": "success", "data": data if data is not None else {}}

