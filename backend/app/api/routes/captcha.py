"""图形验证码接口。

- GET  /api/captcha         获取验证码图片（base64）
- POST /api/captcha/verify  校验验证码；通过后签发 10 分钟挑战通行证 Cookie
"""
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import extract_ip
from app.core.database import get_db
from app.schemas.common import ok
from app.services.captcha_service import generate_captcha, set_challenge_pass, verify_captcha

router = APIRouter(prefix="/captcha", tags=["captcha"])


class CaptchaVerifyIn(BaseModel):
    captcha_id: str = Field(min_length=1, max_length=64)
    captcha_text: str = Field(min_length=1, max_length=16)


@router.get("")
def get_captcha(request: Request, db: Session = Depends(get_db)) -> dict:
    """获取图形验证码（base64 图片）。"""
    return ok(generate_captcha(db, extract_ip(request)))


@router.post("/verify")
def verify(
    request: Request,
    response: Response,
    payload: CaptchaVerifyIn,
    db: Session = Depends(get_db),
) -> dict:
    """校验验证码；通过后签发 10 分钟挑战通行证 Cookie。"""
    ip = extract_ip(request)
    verify_captcha(db, payload.captcha_id, payload.captcha_text, ip)
    set_challenge_pass(response, ip)
    return ok({"verified": True})
