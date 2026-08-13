"""微信朋友圈同步业务逻辑。

职责：
- 用户绑定（输入微信号/wxid 匹配好友快照，绑定后不可自改）
- 自动同步开关（sync_enabled_at 为历史分界线）
- 手动导入（可选置顶，置顶按批次第几条 1/2/3 金币/天收费）
- 同步客户端上报（好友快照 + 朋友圈动态 ingest，按 tid 去重）
- 微信朋友圈频道 feed（置顶优先，再按朋友圈发布时间倒序）
"""

import asyncio
import json
import os
import queue
import secrets
import threading
from datetime import timedelta

from fastapi import HTTPException
from loguru import logger
from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.time_utils import now_utc, to_iso_zh
from app.models import (
    Post,
    User,
    WechatBinding,
    WechatFriend,
    WechatMoment,
    WechatRecentMessage,
)
from app.services import coin_service
from app.services.rate_limit_service import check_rate_limit
from app.services.settings_service import get_setting, set_setting
from app.services import wechat_local
from app.utils.wechat_emoji import convert_wechat_emoji

# 置顶单价：同一批第 1/2/3 条分别 1/2/3 金币/天；同一批最多置顶 3 条
PIN_UNIT_PRICES = (1, 2, 3)
PIN_MAX_PER_BATCH = 3

# 频率限制
IMPORT_HOURLY_LIMIT = 20          # 手动导入：每小时最多 20 次
REFRESH_COOLDOWN_SECONDS = 30     # 手动刷新：每 30 秒最多 1 次

BIND_REWARD = 10  # 绑定微信奖励金币
WECHAT_CATEGORY = "朋友圈"
WECHAT_SOURCES = ("wechat_auto", "wechat_manual")
VERIFY_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 排除 0/O/1/I 易混淆字符
BIND_CODE_TTL = timedelta(minutes=10)


def _now() -> object:
    return now_utc()


def _schedule_post_audit(post_id: int) -> None:
    """对刚创建的同步帖子触发后台 AI 审核（pending 状态才会真正审核）。

    普通发帖在 post_service 里会 asyncio.create_task；朋友圈同步发帖
    （自动同步 ingest + 手动导入）之前漏了这一步，导致一直停在"审核中"。
    """
    from app.services import audit_service

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        threading.Thread(
            target=lambda: asyncio.run(audit_service.audit_post_background(post_id)),
            daemon=True,
        ).start()
    else:
        asyncio.create_task(audit_service.audit_post_background(post_id))


def _moment_time(ts: int | None):
    if not ts:
        return None
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
    except (OverflowError, OSError, ValueError):
        return None


def _to_iso(dt) -> str | None:
    return to_iso_zh(dt) if dt else None


# ============ 绑定 ============

def find_friend(db: Session, query: str) -> WechatFriend | None:
    q = (query or "").strip()
    if not q:
        return None
    row = db.scalar(select(WechatFriend).where(WechatFriend.wxid == q))
    if row is None:
        row = db.scalar(select(WechatFriend).where(WechatFriend.wechat_id == q))
    return row


def sync_friends_from_local(db: Session) -> int:
    """后端直读 contact.db，同步好友快照（替代客户端上传）。"""
    total = 0
    for account in wechat_local.list_accounts():
        friends = wechat_local.read_friends(account)
        if friends:
            total += upsert_friends(db, friends)
    return total


def start_bind(db: Session, user: User, query: str) -> WechatBinding | None:
    """分步绑定第 1 步：查找好友并生成消息验证码。查不到返回 None。"""
    existing = db.scalar(
        select(WechatBinding).where(WechatBinding.user_id == user.id)
    )
    if existing is not None and existing.status == "verified":
        return existing
    friend = find_friend(db, query)
    if friend is None:
        # 后端直读 contact.db 同步好友快照后再查一次（不依赖客户端上报）
        try:
            sync_friends_from_local(db)
        except Exception:
            pass
        friend = find_friend(db, query)
    if friend is None:
        return None
    # ============ 微信号占用检查（多人绑定同一微信号的完整逻辑） ============
    # 一个微信号只能被一个用户绑定；别人已绑定（verified）或正在绑定（pending 未过期）时，
    # 直接拒绝，提示去核对微信号；别人开始绑定但超过验证码有效期仍未完成（pending 过期），
    # 视为放弃，自动释放该微信号，允许当前用户继续。
    occupied = db.scalar(
        select(WechatBinding).where(
            WechatBinding.wxid == friend.wxid,
            WechatBinding.status.in_(("pending", "verified")),
            WechatBinding.user_id != user.id,
        )
    )
    if occupied is not None:
        if occupied.status == "verified" or (
            occupied.verify_code_expires_at
            and occupied.verify_code_expires_at >= _now()
        ):
            raise HTTPException(
                status_code=409,
                detail="该微信号已被其他用户绑定，请确认填写的是你自己的微信号",
            )
        # 过期未完成：先释放占位（唯一约束要求先改名再清状态），再继续当前用户绑定
        occupied.wxid = f"__stale_{occupied.id}_{secrets.token_hex(4)}"
        occupied.status = "expired"
        occupied.verify_code = None
        occupied.verify_code_expires_at = None
        db.flush()
    if existing is None:
        binding = WechatBinding(
            user_id=user.id,
            wxid=friend.wxid,
            wechat_id=friend.wechat_id,
            nickname=friend.remark or friend.nickname or friend.wxid,
            status="pending",
        )
        db.add(binding)
    else:
        binding = existing
        binding.wxid = friend.wxid
        binding.wechat_id = friend.wechat_id
        binding.nickname = friend.remark or friend.nickname or friend.wxid
        # 复用旧绑定行（解绑/过期后重绑）：重置为全新 pending 状态
        binding.status = "pending"
        binding.unbound_at = None
        binding.sync_enabled = False
        binding.sync_enabled_at = None
        binding.unbound_by_admin_id = None
    binding.verify_code = "".join(secrets.choice(VERIFY_CODE_CHARS) for _ in range(8))
    binding.verify_code_expires_at = _now() + BIND_CODE_TTL
    db.flush()
    db.commit()
    db.refresh(binding)
    return binding


def verify_bind_code(db: Session, user: User, code: str) -> dict:
    """分步绑定第 2 步：校验用户是否真的把验证码发给了社区微信号。"""
    binding = db.scalar(
        select(WechatBinding).where(
            WechatBinding.user_id == user.id,
            WechatBinding.status == "pending",
        )
    )
    if binding is None:
        raise HTTPException(status_code=404, detail="尚未开始绑定微信")
    code = (code or "").strip().upper()
    if not binding.verify_code or binding.verify_code != code:
        return {"matched": False, "reason": "验证码不正确"}
    if not binding.verify_code_expires_at or binding.verify_code_expires_at < _now():
        raise HTTPException(status_code=400, detail="验证码已过期，请重新绑定")

    # 优先直读本地 message 库实时校验（不再依赖客户端上报）；读不到时退回
    # 客户端历史上报的表。
    last_text = ""
    last_time = 0
    accounts = wechat_local.list_accounts()
    # 1) 实时直连：SQLCipher 只读连接常驻（live_wcdb），毫秒级查询，
    #    微信刚收到的新消息立即可见；失败（无 dll/目录/密钥）自动回退。
    try:
        from app.services import wechat_live_reader

        for account in accounts:
            hit = wechat_live_reader.latest_incoming_text(account, binding.wxid)
            if hit:
                last_time, last_text = hit
                break
    except Exception:
        pass
    # 2) 直连读不到时，回退整库解密（兼容无 SQLCipher 运行库的环境）
    if not last_text:
        for account in accounts:
            msgs = wechat_local.read_recent_incoming_messages(account)
            hit = msgs.get(binding.wxid)
            if hit:
                last_time, last_text = hit
                break
    # 3) 客户端历史上报的表
    if not last_text:
        row = db.scalar(
            select(WechatRecentMessage).where(WechatRecentMessage.peer_wxid == binding.wxid)
        )
        last_text = (row.last_text or "") if row else ""
        last_time = int(row.last_time or 0) if row else 0
    if not last_text:
        return {"matched": False, "reason": "未检测到验证码消息，请确认已发送给社区微信号"}
    if code not in last_text.upper():
        # 收到了消息但内容不是当前验证码：明确提示发错，前端据此停止轮询
        return {"matched": False, "reason": "验证码发错了，请核对后重新发送", "wrong_code": True}
    # 防止用旧消息碰运气：消息时间必须晚于验证码生成时间
    code_start = int(
        (binding.verify_code_expires_at - BIND_CODE_TTL).replace(tzinfo=None).timestamp()
    )
    if last_time and last_time < code_start:
        return {"matched": False, "reason": "未检测到新发送的验证码消息"}

    binding.status = "verified"
    binding.verify_code = None
    binding.verify_code_expires_at = None
    db.flush()
    coins = coin_service.grant_coins(
        db,
        user,
        BIND_REWARD,
        "bind_reward",
        ref_id=str(binding.id),
        description="绑定微信奖励",
    )
    db.commit()
    return {"matched": True, "coins": coins}


def require_binding(db: Session, user: User) -> WechatBinding:
    binding = db.scalar(
        select(WechatBinding).where(
            WechatBinding.user_id == user.id,
            WechatBinding.status == "verified",
            WechatBinding.unbound_at.is_(None),
        )
    )
    if binding is None:
        raise HTTPException(status_code=404, detail="尚未绑定微信")
    return binding


def binding_status(db: Session, user: User) -> dict:
    binding = db.scalar(
        select(WechatBinding).where(WechatBinding.user_id == user.id)
    )
    synced_count = 0
    if binding is not None:
        synced_count = (
            db.scalar(
                select(func.count(Post.id)).where(
                    Post.wechat_moment_id.isnot(None),
                    Post.author_id == user.id,
                )
            )
            or 0
        )
    return {
        "bound": binding is not None and binding.status == "verified" and binding.unbound_at is None,
        "status": binding.status if binding else None,
        "wxid": binding.wxid if binding else None,
        "wechat_id": binding.wechat_id if binding else None,
        "nickname": binding.nickname if binding else None,
        "sync_enabled": bool(binding and binding.sync_enabled),
        "sync_enabled_at": _to_iso(binding.sync_enabled_at) if binding else None,
        "bound_at": _to_iso(binding.bound_at) if binding else None,
        "synced_count": synced_count,
        "coins": coin_service.get_balance(db, user.id),
        "onboarding_done": bool(user.onboarding_done),
    }


def set_sync_enabled(db: Session, user: User, enabled: bool) -> dict:
    binding = require_binding(db, user)
    if enabled and not binding.sync_enabled:
        binding.sync_enabled = True
        binding.sync_enabled_at = _now()
    elif not enabled:
        binding.sync_enabled = False
    db.commit()
    db.refresh(binding)
    return binding_status(db, user)


def unbind_wechat(db: Session, user: User) -> dict:
    """用户自助解绑：解除当前绑定，之后可重新绑定其他微信号。

    与原微信号立即解除关系（wxid 改名释放唯一约束，与管理员解绑一致），
    自动同步一并关闭；已导入/已发布的朋友圈内容不受影响。
    """
    binding = db.scalar(
        select(WechatBinding).where(
            WechatBinding.user_id == user.id,
            WechatBinding.unbound_at.is_(None),
        )
    )
    if binding is None:
        raise HTTPException(status_code=404, detail="尚未绑定微信")
    old_wxid = binding.wxid
    # 释放 wxid 唯一约束：改名 + 标记解绑，原微信号可被重新绑定
    binding.wxid = f"__unbound_{binding.id}_{secrets.token_hex(4)}"
    binding.status = "unbound"
    binding.unbound_at = _now()
    binding.sync_enabled = False
    binding.sync_enabled_at = None
    binding.verify_code = None
    binding.verify_code_expires_at = None
    db.commit()
    return {"unbound": True, "wxid": old_wxid}


# ============ 手动导入 ============

def list_my_moments(db: Session, user: User, page: int = 1, page_size: int = 20) -> dict:
    binding = require_binding(db, user)
    base = select(WechatMoment).where(WechatMoment.wxid == binding.wxid)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = (
        db.scalars(
            base.order_by(desc(WechatMoment.create_time), desc(WechatMoment.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .all()
    )
    imported_ids = set(
        db.scalars(
            select(Post.wechat_moment_id).where(
                Post.wechat_moment_id.isnot(None),
                Post.author_id == user.id,
            )
        )
    )
    items = []
    for m in rows:
        try:
            media = json.loads(m.media_json or "[]")
        except (ValueError, TypeError):
            media = []
        pending = any(x.get("pending") for x in media if isinstance(x, dict))
        if pending:
            # 用户打开页面时按需触发媒体下载（只下载该用户自己的动态）
            _enqueue_media(m.id)
            # 图片还在后台下载：先返回空媒体，前端显示"加载中"占位
            clean_media = []
        else:
            clean_media = [
                {k: v for k, v in x.items() if k not in ("pending", "_acct")} for x in media
            ]
        items.append(
            {
                "id": m.id,
                "tid": m.tid,
                "content": m.content,
                "create_time": _to_iso(m.create_time),
                "media": clean_media,
                "media_pending": pending,
                "imported": m.id in imported_ids,
            }
        )
    if any(it["media_pending"] for it in items):
        _ensure_media_worker()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def _initial_ai_status(db: Session, has_images: bool) -> tuple[str, str | None]:
    from app.services import audit_service, settings_service

    scope = settings_service.get_audit_scope(db)
    triggers = settings_service.get_manual_review_triggers(db)
    if has_images and "image" in scope:
        return "manual_review", "图片/视频内容需人工审核"
    if "post" not in scope:
        return "approved", None
    if audit_service.is_ai_audit_available(db):
        return "pending", None
    if "ai_unavailable" in triggers:
        return "manual_review", "AI 审核服务暂不可用，已转人工审核"
    return "approved", None


def _notify_manual_review(db: Session, user_id: int, post_id: int, reason: str) -> None:
    from app.services.notification_service import create_notification

    create_notification(
        db,
        user_id,
        "内容已进入人工审核",
        f"您的朋友圈同步帖子已提交，当前进入人工审核（{reason}）。"
        "审核可能较慢，请耐心等待，审核结果会第一时间通知您。",
        ntype="system",
        reference_type="post",
        reference_id=post_id,
    )


def _build_post(
    db: Session,
    user: User,
    moment: WechatMoment,
    source: str,
    pin_days: int = 0,
) -> Post:
    try:
        media = json.loads(moment.media_json or "[]")
    except (ValueError, TypeError):
        media = []
    # 未下载成功的媒体（pending）不进帖子，避免引用 CDN 临时链接
    media = [m for m in media if not m.get("pending")]
    image_urls = [m["url"] for m in media if m.get("type") == 2 and m.get("url")]
    # 视频：type 6/3/4 为微信朋友圈视频（已下载为 mp4）
    video_urls = [m["url"] for m in media if m.get("type") in (6, 3, 4) and m.get("url")]
    # 视频封面（本地缓存明文封面）也作为帖子图片
    image_urls += [m["thumb_url"] for m in media if m.get("type") in (6, 3, 4) and m.get("thumb_url")]
    ai_status, reason = _initial_ai_status(db, bool(image_urls) or bool(video_urls))
    pinned = pin_days > 0
    post = Post(
        author_id=user.id,
        school_id=user.school_id,
        category=WECHAT_CATEGORY,
        content=convert_wechat_emoji((moment.content or "").strip()) or "分享了一条朋友圈",
        image_urls=json.dumps(image_urls, ensure_ascii=False),
        video_urls=json.dumps(video_urls, ensure_ascii=False),
        is_anonymous=False,
        is_public=True,
        is_draft=False,
        tags=json.dumps([], ensure_ascii=False),
        ai_status=ai_status,
        reject_reason=reason,
        title=None,
        is_original=False,
        has_ai_content=False,
        source=source,
        wechat_moment_id=moment.id,
        is_pinned=pinned,
        pinned_at=_now() if pinned else None,
        pinned_until=_now() + timedelta(days=pin_days) if pinned else None,
        source_created_at=moment.create_time,
    )
    db.add(post)
    db.flush()
    if ai_status == "manual_review":
        _notify_manual_review(db, user.id, post.id, reason or "内容审核")
    return post


def import_moments(
    db: Session,
    user: User,
    tids: list[str],
    pinned_tids: list[str],
    pin_days: int = 1,
) -> dict:
    if not tids:
        raise HTTPException(status_code=400, detail="请选择要导入的朋友圈")
    if not check_rate_limit(
        db, f"rl:user:{user.id}:wechat_import", IMPORT_HOURLY_LIMIT, 3600
    ):
        raise HTTPException(status_code=429, detail="同步次数已达上限，请稍后再试")

    binding = require_binding(db, user)
    tid_set = list(dict.fromkeys(t.strip() for t in tids if t.strip()))
    if not tid_set:
        raise HTTPException(status_code=400, detail="请选择要导入的朋友圈")

    rows = db.scalars(
        select(WechatMoment).where(
            WechatMoment.tid.in_(tid_set),
            WechatMoment.wxid == binding.wxid,
        )
    ).all()
    found = {m.tid: m for m in rows}
    missing = [t for t in tid_set if t not in found]
    if missing:
        raise HTTPException(status_code=404, detail="部分朋友圈不存在或不属于当前用户")

    existing_ids = set(
        db.scalars(
            select(Post.wechat_moment_id).where(
                Post.wechat_moment_id.in_([m.id for m in rows])
            )
        )
    )
    dup_tids = [
        m.tid
        for m in rows
        if m.id in existing_ids
    ]
    if dup_tids:
        raise HTTPException(status_code=400, detail=f"以下动态已导入过：{','.join(dup_tids[:5])}")

    pinned_set = [t for t in dict.fromkeys(pinned_tids or []) if t in tid_set]
    if len(pinned_set) > PIN_MAX_PER_BATCH:
        raise HTTPException(
            status_code=400, detail=f"同一批最多置顶 {PIN_MAX_PER_BATCH} 条"
        )
    pin_days = max(1, int(pin_days or 1)) if pinned_set else 0

    # 置顶费用：第 1/2/3 条单价 1/2/3 金币/天，按天累计
    cost = 0
    if pinned_set:
        cost = sum(
            PIN_UNIT_PRICES[min(i, len(PIN_UNIT_PRICES) - 1)] for i in range(len(pinned_set))
        ) * pin_days
        coin_service.charge_coins(
            db,
            user,
            cost,
            "pin",
            ref_id=",".join(found[t].tid for t in pinned_set),
            description=f"朋友圈置顶 {len(pinned_set)} 条 × {pin_days} 天",
        )

    created_posts: list[Post] = []
    for tid in tid_set:
        moment = found[tid]
        post = _build_post(
            db,
            user,
            moment,
            source="wechat_manual",
            pin_days=pin_days if tid in pinned_set else 0,
        )
        created_posts.append(post)

    db.commit()
    for post in created_posts:
        if post.ai_status == "pending":
            _schedule_post_audit(post.id)
    return {"cost": cost, "post_ids": [p.id for p in created_posts], "pinned": pinned_set}


# ============ 微信朋友圈频道 feed ============

def moments_feed(
    db: Session,
    user: User | None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    from app.services.post_service import post_dict

    now = _now()
    pinned_expr = case(
        (
            and_(
                Post.is_pinned.is_(True),
                or_(Post.pinned_until.is_(None), Post.pinned_until > now),
            ),
            1,
        ),
        else_=0,
    )
    base = (
        select(Post)
        .options(selectinload(Post.author), selectinload(Post.school))
        .where(
            Post.is_draft.is_(False),
            Post.source.in_(WECHAT_SOURCES),
            Post.is_hidden_by_unverify.is_(False),
        )
    )
    if user is not None:
        # 作者本人可见自己的待审核/未通过内容，其他人只看到审核通过的
        base = base.where(or_(Post.ai_status == "approved", Post.author_id == user.id))
        base = base.where(or_(Post.is_public.is_(True), Post.author_id == user.id))
    else:
        base = base.where(Post.is_public.is_(True))
        base = base.where(Post.ai_status == "approved")

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = (
        db.scalars(
            base.order_by(
                desc(pinned_expr),
                desc(Post.pinned_at),
                desc(Post.source_created_at),
                desc(Post.id),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .all()
    )
    items = []
    for p in rows:
        d = post_dict(p, db=db)
        d.update(
            {
                "source": p.source,
                "is_pinned": bool(
                    p.is_pinned and (p.pinned_until is None or p.pinned_until > now)
                ),
                "pinned_until": _to_iso(p.pinned_until),
                "wechat_created_at": _to_iso(p.source_created_at),
            }
        )
        items.append(d)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ============ 手动刷新（立即扫描）============

def request_force_refresh(db: Session, user: User) -> str:
    """兼容旧客户端：标记需要手动刷新，由客户端心跳触发。"""
    if not check_rate_limit(
        db,
        f"rl:user:{user.id}:wechat_refresh",
        1,
        REFRESH_COOLDOWN_SECONDS,
    ):
        raise HTTPException(status_code=429, detail="刷新太频繁，请稍后再试")
    binding = require_binding(db, user)
    set_setting(db, "wechat_force_refresh", binding.wxid)
    return binding.wxid


def _sync_one_account(db: Session, account: dict, after_ts: int = 0) -> int:
    """直读一个微信账号的 sns.db，增量入库朋友圈。

    只入库文字/元数据（媒体标记 pending）；媒体按需后台下载：
    - 命中"开启自动同步"的动态：立即入队，下载完媒体再发帖；
    - 其余动态：等用户打开手动发布页时按需入队。
    """
    feeds = wechat_local.read_feeds(account, after_ts=after_ts)
    new_feeds = []
    for f in feeds:
        tid = str(f.get("tid") or "").strip()
        if not tid:
            continue
        if db.scalar(select(WechatMoment).where(WechatMoment.tid == tid)) is not None:
            continue
        new_feeds.append(f)

    for f in new_feeds:
        raw_media = f.get("media") or []
        pending_media = [
            dict(md, pending=True, _acct=account["account_id"]) for md in raw_media
        ]
        moment = WechatMoment(
            tid=str(f.get("tid") or "").strip(),
            wxid=(f.get("wxid") or "").strip(),
            author_name="",
            content=convert_wechat_emoji(f.get("text") or ""),
            create_time=_moment_time(f.get("create_time")),
            media_json=json.dumps(pending_media, ensure_ascii=False),
        )
        db.add(moment)
        db.flush()

        # 只对"开启自动同步"的动态立即下载（发帖需要图），其余按需
        auto = False
        wxid = moment.wxid
        if wxid:
            binding = db.scalar(
                select(WechatBinding).where(
                    WechatBinding.wxid == wxid,
                    WechatBinding.sync_enabled.is_(True),
                    WechatBinding.unbound_at.is_(None),
                )
            )
            auto = bool(
                binding is not None
                and moment.create_time
                and binding.sync_enabled_at
                and moment.create_time >= binding.sync_enabled_at
            )
        if auto:
            _enqueue_media(moment.id)
    db.commit()
    _ensure_media_worker()
    return len(new_feeds)


# ============ 媒体后台下载（刷新接口不阻塞） ============

_media_tasks: queue.Queue = queue.Queue()
_media_worker_started = False
_media_worker_lock = threading.Lock()
_media_inflight: set[int] = set()
_media_inflight_lock = threading.Lock()


def _enqueue_media(moment_id: int) -> None:
    """入队媒体下载（去重：同一条动态只下载一次）。"""
    with _media_inflight_lock:
        if moment_id in _media_inflight:
            return
        _media_inflight.add(moment_id)
    _media_tasks.put(moment_id)


def _ensure_media_worker() -> None:
    global _media_worker_started
    with _media_worker_lock:
        if _media_worker_started:
            return
        _media_worker_started = True
        threading.Thread(target=_media_worker_loop, daemon=True).start()


def _media_worker_loop() -> None:
    """后台下载朋友圈媒体：下载完成后回填 media_json，并补自动发帖。"""
    from app.core.database import SessionLocal
    from concurrent.futures import ThreadPoolExecutor

    while True:
        try:
            moment_id = _media_tasks.get()
        except Exception:
            return
        try:
            db = SessionLocal()
            try:
                moment = db.get(WechatMoment, moment_id)
                if moment is None:
                    continue
                try:
                    raw = json.loads(moment.media_json or "[]")
                except (ValueError, TypeError):
                    raw = []
                pending = [m for m in raw if m.get("pending")]
                if pending:
                    account_id = next(
                        (m.get("_acct") for m in pending if m.get("_acct")), ""
                    ) or (
                        (wechat_local.list_accounts() or [{}])[0].get("account_id", "")
                    )

                    def _download(md):
                        try:
                            return wechat_local.download_moment_media(
                                md, account_id, create_time=(
                                    int(moment.create_time.timestamp())
                                    if moment.create_time else 0
                                )
                            )
                        except Exception as exc:  # 单条失败只记日志，不拖垮整批
                            logger.exception(
                                "[WECHAT_MEDIA] 媒体下载失败 type={} md5={} url={}: {}",
                                md.get("type"), md.get("md5"), (md.get("url") or "")[:80], exc,
                            )
                            return None

                    media = []
                    with ThreadPoolExecutor(max_workers=8) as pool:
                        for saved in pool.map(_download, pending):
                            if saved:
                                media.append(saved)
                    if media:
                        moment.media_json = json.dumps(media, ensure_ascii=False)
                    # 全部下载失败：保留原 pending 媒体，等待下次重试（用户播放后缓存有了再补）
                else:
                    moment.media_json = "[]"

                # 媒体就绪后再触发自动发帖（保证帖子里带图）
                post = None
                wxid = moment.wxid
                if wxid:
                    binding = db.scalar(
                        select(WechatBinding).where(
                            WechatBinding.wxid == wxid,
                            WechatBinding.sync_enabled.is_(True),
                            WechatBinding.unbound_at.is_(None),
                        )
                    )
                    if (
                        binding is not None
                        and moment.create_time
                        and binding.sync_enabled_at
                        and moment.create_time >= binding.sync_enabled_at
                    ):
                        user = db.get(User, binding.user_id)
                        if user is not None:
                            # 防重复：该动态已发过帖（含媒体重试成功后再来一次）则跳过
                            already = db.scalar(
                                select(Post.id).where(Post.wechat_moment_id == moment.id)
                            )
                            if already is None:
                                post = _build_post(db, user, moment, source="wechat_auto")
                db.commit()
                if post is not None and post.ai_status == "pending":
                    _schedule_post_audit(post.id)
            finally:
                db.close()
        except Exception as exc:
            logger.exception("[WECHAT_MEDIA] 媒体任务处理异常: {}", exc)
        finally:
            with _media_inflight_lock:
                _media_inflight.discard(moment_id)


def sync_moments_from_local(db: Session, after_ts: int = 0) -> int:
    """全账号直读同步：返回新增朋友圈条数。"""
    total = 0
    for account in wechat_local.list_accounts():
        total += _sync_one_account(db, account, after_ts=after_ts)
    return total


def has_auto_sync_binding(db: Session) -> bool:
    """是否有"开启自动同步"的绑定（没有就不需要扫描 sns.db）。"""
    return bool(
        db.scalar(
            select(func.count())
            .select_from(WechatBinding)
            .where(
                WechatBinding.sync_enabled.is_(True),
                WechatBinding.status == "verified",
                WechatBinding.unbound_at.is_(None),
            )
        )
        or 0
    )


def sns_mtimes() -> dict[str, float | None]:
    """各账号 sns.db 的当前修改时间（定位不到为 None）。只做 stat，开销极小。"""
    out: dict[str, float | None] = {}
    for account in wechat_local.list_accounts():
        p = wechat_local.resolve_sns_db(account)
        try:
            out[account["account_id"]] = os.path.getmtime(p) if p else None
        except OSError:
            out[account["account_id"]] = None
    return out


def refresh_moments(db: Session, user: User) -> dict:
    """用户点刷新：后端当场直读 sns.db 入库并返回结果（不再走客户端轮询）。"""
    if not check_rate_limit(
        db,
        f"rl:user:{user.id}:wechat_refresh",
        1,
        REFRESH_COOLDOWN_SECONDS,
    ):
        raise HTTPException(status_code=429, detail="刷新太频繁，请稍后再试")
    binding = require_binding(db, user)
    sync_friends_from_local(db)
    added = sync_moments_from_local(db)
    return {"added": added, "wxid": binding.wxid}


def consume_force_refresh(db: Session) -> str:
    """读取并清空手动刷新指令，返回需要刷新的 wxid（无则为空串）。"""
    wxid = get_setting(db, "wechat_force_refresh", "")
    if wxid:
        set_setting(db, "wechat_force_refresh", "")
        return wxid
    return ""


def get_auto_sync_cutoffs(db: Session) -> list[dict]:
    """返回所有"已绑定且开启自动同步"的账号及其历史分界线（unix 秒）。
    客户端只会上传这些账号在分界线之后发布的朋友圈，其余一律不传。
    """
    rows = db.scalars(
        select(WechatBinding).where(
            WechatBinding.sync_enabled.is_(True),
            WechatBinding.status == "verified",
            WechatBinding.unbound_at.is_(None),
        )
    ).all()
    out = []
    for b in rows:
        if b.sync_enabled_at:
            out.append(
                {
                    "wxid": b.wxid,
                    "sync_enabled_at": int(b.sync_enabled_at.replace(tzinfo=None).timestamp()),
                }
            )
    return out


def get_bind_guide(db: Session) -> dict:
    """需要添加的社区微信号（后台可在设置里改 wechat_bind_account）。"""
    wechat_id = get_setting(db, "wechat_bind_account", "")
    return {"wechat_id": wechat_id}


def has_pending_bindings(db: Session) -> bool:
    """是否存在待验证的绑定（有则让客户端开始上报收到的消息）。"""
    return (
        db.scalar(
            select(func.count(WechatBinding.id)).where(
                WechatBinding.status == "pending"
            )
        )
        or 0
    ) > 0


def request_friend_refresh(db: Session) -> None:
    set_setting(db, "wechat_force_friends_refresh", "1")


def consume_friend_refresh(db: Session) -> bool:
    if get_setting(db, "wechat_force_friends_refresh", "0") == "1":
        set_setting(db, "wechat_force_friends_refresh", "0")
        return True
    return False


def report_recent_messages(db: Session, items: list[dict]) -> int:
    """客户端上报社区账号收到的最近消息，供绑定验证码校验。"""
    updated = 0
    for item in items or []:
        peer = (item.get("peer") or item.get("peer_wxid") or "").strip()
        if not peer:
            continue
        row = db.scalar(
            select(WechatRecentMessage).where(WechatRecentMessage.peer_wxid == peer)
        )
        text = (item.get("text") or "")[:1000]
        last_time = int(item.get("last_time") or 0)
        if row:
            row.last_text = text
            row.last_time = last_time
            row.updated_at = _now()
        else:
            db.add(
                WechatRecentMessage(
                    peer_wxid=peer,
                    last_text=text,
                    last_time=last_time,
                    updated_at=_now(),
                )
            )
        updated += 1
    db.commit()
    return updated


# ============ 设备令牌（同步客户端鉴权）============

def get_device_token(db: Session) -> str:
    token = get_setting(db, "wechat_device_token", "")
    if not token:
        token = secrets.token_hex(32)
        set_setting(db, "wechat_device_token", token)
    return token


# ============ 同步客户端上报 ============

def upsert_friends(db: Session, friends: list[dict]) -> int:
    added = 0
    now = _now()
    for f in friends or []:
        wxid = (f.get("wxid") or "").strip()
        if not wxid:
            continue
        row = db.scalar(select(WechatFriend).where(WechatFriend.wxid == wxid))
        if row:
            row.wechat_id = (f.get("wechat_id") or "").strip() or row.wechat_id
            row.nickname = f.get("nickname") or row.nickname
            row.remark = f.get("remark") or row.remark
            row.last_seen_at = now
        else:
            db.add(
                WechatFriend(
                    wxid=wxid,
                    wechat_id=(f.get("wechat_id") or "").strip() or None,
                    nickname=f.get("nickname") or "",
                    remark=f.get("remark"),
                    last_seen_at=now,
                )
            )
            added += 1
    db.commit()
    return added


def _detect_image(content: bytes) -> tuple[str, str] | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if content.startswith(b"GIF87a") or content.startswith(b"GIF89a"):
        return "image/gif", ".gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


async def ingest_moment(
    db: Session,
    item: dict,
    media_files: list[tuple[int, bytes]] | None = None,
) -> dict:
    """上报一条朋友圈：入库 + 上传媒体 + 命中自动同步则发帖。"""
    from app.services.storage_service import storage_service

    tid = str(item.get("tid") or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail="tid 不能为空")
    existing = db.scalar(select(WechatMoment).where(WechatMoment.tid == tid))
    if existing is not None:
        return {"ingested": False, "posted": False}

    media = []
    for ftype, raw in media_files or []:
        if raw:
            detected = _detect_image(raw)
            if detected:
                content_type, ext = detected
                # 图片存储前狠狠压缩（统一 JPEG）；GIF 动图保留原样
                if ext != ".gif":
                    compressed = wechat_local.compress_image_bytes(raw)
                    if compressed:
                        raw = compressed
                        content_type = "image/jpeg"
                        ext = ".jpg"
                filename = f"wechat/{secrets.token_hex(8)}{ext}"
                url = await storage_service.upload_image_async(
                    filename, raw, content_type
                )
                media.append({"type": ftype, "url": url})
                continue
        media.append({"type": ftype})

    moment = WechatMoment(
        tid=tid,
        wxid=(item.get("wxid") or "").strip(),
        author_name=item.get("author_name") or "",
        content=convert_wechat_emoji(item.get("content") or ""),
        create_time=_moment_time(item.get("create_time")),
        media_json=json.dumps(media, ensure_ascii=False),
    )
    db.add(moment)
    db.flush()

    created_post: Post | None = None
    wxid = moment.wxid
    if wxid:
        binding = db.scalar(
            select(WechatBinding).where(
                WechatBinding.wxid == wxid,
                WechatBinding.sync_enabled.is_(True),
                WechatBinding.unbound_at.is_(None),
            )
        )
        if (
            binding is not None
            and moment.create_time
            and binding.sync_enabled_at
            and moment.create_time >= binding.sync_enabled_at
        ):
            user = db.get(User, binding.user_id)
            if user is not None:
                created_post = _build_post(db, user, moment, source="wechat_auto")

    db.commit()
    if created_post is not None and created_post.ai_status == "pending":
        _schedule_post_audit(created_post.id)
    return {"ingested": True, "posted": created_post is not None}
