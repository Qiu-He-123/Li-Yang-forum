"""漂流瓶业务逻辑层。

实现规则：
- 投放：必选校区(future/main/xiangshan/east) + 自动从生日计算年龄；可选兴趣标签
  文本/图片至少一个；图片可多张；可选填写联系方式（拾取者可见）
  （旧字段 grade 保留向后兼容，新逻辑以年龄为主）
- 拾取：用户可设置期望年龄范围/校区/兴趣标签；按优先级匹配
  匹配优先级：同校区 + 年龄匹配 + 兴趣标签重叠 > 同校区 + 年龄匹配 > 同校区
              > 年龄匹配 + 兴趣标签重叠 > 年龄匹配 > 任意 active
  匹配过一次的人不能再匹配第二次（通过 BottlePick 唯一索引 picker_id+author_id）
  每日拾取上限：3 次（可配置），保留稀缺感
- 多人拾取：一个瓶子可被无数人拾取，瓶子状态保持 active，不因被拾取而变化
- 收回：作者可主动收回瓶子（status=recalled），收回后不再可被拾取
- 防重复：BottlePick (picker_id, author_id) 唯一约束保证同一拾取者不会重复拾取同一作者
- 安全：拾取到的瓶子暴露作者基本信息 + 联系方式，但隐藏 uid/phone 等敏感信息
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ErrorCode
from app.core.time_utils import calculate_age, to_iso_zh
from app.models import Bottle, BottlePick, School, User
from app.services.connection_manager import manager

# 每日拾取上限
DAILY_PICK_LIMIT = 3

# 兴趣标签预设（前端可补充自定义）
DEFAULT_INTEREST_TAGS = [
    "音乐", "运动", "游戏", "电影", "阅读", "动漫", "摄影", "编程",
    "美食", "旅行", "学习", "宠物", "舞蹈", "绘画", "其他",
]

# 有效年龄范围（13~18 岁）
AGE_MIN, AGE_MAX = 13, 18

# 有效年级（含初中三个年级）— 旧字段，保留向后兼容
VALID_GRADES = {"初一", "初二", "初三", "高一", "高二", "高三"}


def _parse_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def _bottle_dict(
    b: Bottle,
    author: User | None = None,
    school_name: str | None = None,
    *,
    show_contact: bool = False,
) -> dict:
    """序列化漂流瓶。

    拾取到的瓶子暴露作者基本信息（昵称/头像/年级/校区/性别），但隐藏 uid/phone 等敏感信息。
    联系方式 contact 仅在拾取成功时（show_contact=True）返回给拾取者。
    作者查看自己的瓶子时也可看到 contact（用于编辑）。
    """
    if author is None:
        author = b.author if hasattr(b, "author") else None
    # 优先使用快照 author_age；若为空则从 author.birthday 动态计算
    author_age = b.author_age
    if author_age is None and author is not None:
        author_age = calculate_age(author.birthday)
    return {
        "id": b.id,
        "author_id": b.author_id,
        "author_nickname": author.nickname if author else None,
        "author_avatar_url": author.avatar_url if author else None,
        "author_gender": b.gender or "unknown",
        "author_grade": b.grade,           # 旧字段，保留兼容
        "author_age": author_age,          # 新字段：作者年龄
        "school_id": b.school_id,
        "school_name": school_name,
        "content": b.content,
        "image_urls": _parse_json(b.image_urls, []),
        "tags": _parse_json(b.tags, []),
        "status": b.status,
        "contact": b.contact if show_contact else None,
        "created_at": to_iso_zh(b.created_at),
        "picked_at": to_iso_zh(b.picked_at) if b.picked_at else None,
    }


def list_interest_tags() -> list[str]:
    """返回预设兴趣标签列表。"""
    return DEFAULT_INTEREST_TAGS


def create_bottle(
    db: Session,
    user: User,
    content: str | None,
    image_urls: list[str],
    school_id: int,
    tags: list[str],
    contact: str | None = None,
    target_gender: str | None = None,
    grade: str | None = None,
) -> dict:
    """投放漂流瓶。

    规则：
    - content 和 image_urls 至少一个非空
    - school_id 必须是用户所在校区（与 user.school_id 一致）— 为简化匹配维度，强制使用用户所在校区
    - grade 可选（旧字段，保留向后兼容）；新逻辑以 author_age 为主
    - author_age 自动从 user.birthday 计算快照，存入 bottle.author_age
    - tags 可选，最多 5 个
    - contact 可选，联系方式（QQ/微信/手机等），拾取成功后对拾取者可见
    - target_gender: 期望对方性别（male/female/any），存到 bottle.tags 中以 _target_gender:xxx 形式
      实际存储在 Bottle.gender 字段为作者性别；target_gender 期望对方性别
    """
    content = (content or "").strip()
    image_urls = [u for u in (image_urls or []) if u]
    if not content and not image_urls:
        raise HTTPException(status_code=400, detail=ErrorCode.PARAM_ERROR)
    # 校区必须是用户所在校区（防止伪造）
    if school_id != user.school_id:
        raise HTTPException(status_code=400, detail=ErrorCode.PARAM_ERROR)
    # grade 可选，但若传了必须合法
    if grade is not None and grade not in VALID_GRADES:
        raise HTTPException(status_code=400, detail=ErrorCode.PARAM_ERROR)
    # 自动从生日计算年龄快照
    author_age = calculate_age(user.birthday)
    # 标签最多 5 个
    tags = tags[:5]
    # 联系方式最多 100 字符
    contact = (contact or "").strip()[:100] if contact else None

    # 用户的 gender 必须已设置（male/female），否则按 unknown
    bottle_gender = (user.gender or "unknown")
    if bottle_gender not in ("male", "female", "unknown"):
        bottle_gender = "unknown"

    bottle = Bottle(
        author_id=user.id,
        content=content or None,
        image_urls=json.dumps(image_urls, ensure_ascii=False),
        grade=grade or user.grade or "",
        author_age=author_age,
        school_id=school_id,
        gender=bottle_gender,
        tags=json.dumps(tags, ensure_ascii=False),
        contact=contact,
        status="active",
    )
    db.add(bottle)
    db.commit()
    db.refresh(bottle)

    school = db.get(School, bottle.school_id)
    return _bottle_dict(bottle, author=user, school_name=school.name if school else None, show_contact=True)


def _today_start() -> datetime:
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def get_today_pick_count(db: Session, user_id: int) -> int:
    """查询当前用户今日已拾取次数。"""
    today = _today_start()
    count = db.scalar(
        select(func.count())
        .select_from(BottlePick)
        .where(BottlePick.picker_id == user_id, BottlePick.created_at >= today)
    ) or 0
    return int(count)


def pick_bottle(
    db: Session,
    user: User,
    school_ids: list[int],
    tags: list[str],
    tag_required: list[str] | None = None,
    tag_preferred: list[str] | None = None,
    target_gender: str = "any",
    age_min: int | None = None,
    age_max: int | None = None,
    grades: list[str] | None = None,
) -> dict:
    """拾取漂流瓶。

    匹配优先级（逐渐放宽条件，确保每次拾取都有结果）：
    1. 同校区 + 年龄匹配 + 性别匹配 + 兴趣标签重叠
    2. 同校区 + 年龄匹配 + 性别匹配
    3. 同校区 + 年龄匹配
    4. 同校区 + 性别匹配
    5. 年龄匹配 + 性别匹配
    6. 同校区
    7. 年龄匹配
    8. 性别匹配
    9. 任意 active 瓶子

    防重复：BottlePick (picker_id, author_id) 唯一约束保证不会重复拾取同一作者。
    若匹配到的瓶子作者已被当前用户拾取过，会跳过该瓶子，继续匹配下一个。

    性别筛选：
    - target_gender=male: 只匹配 gender=male 的瓶子
    - target_gender=female: 只匹配 gender=female 的瓶子
    - target_gender=any: 不限性别

    年龄筛选：
    - age_min/age_max 为期望作者年龄范围（None 表示不限）
    - 优先使用瓶子的 author_age 快照；若为空则跳过年龄过滤（兼容老数据）

    标签三态机制：
    - tag_required（必须有）：瓶子必须包含所有这些标签才能匹配，硬过滤条件
    - tag_preferred（尽量有）：候选中按重叠度排序优先，软排序条件
    - 其他（无所谓）：不影响匹配

    grades 参数保留向后兼容（旧字段，已不推荐使用）。
    """
    # 1. 检查每日拾取上限
    today_count = get_today_pick_count(db, user.id)
    if today_count >= DAILY_PICK_LIMIT:
        raise HTTPException(status_code=400, detail="今日拾取次数已达上限，明天再来吧")

    # 2. 不能拾取自己投放的瓶子
    # 3. 已经拾取过的作者不能再次拾取
    picked_author_ids = set(
        db.scalars(
            select(BottlePick.author_id).where(BottlePick.picker_id == user.id)
        ).all()
    )

    # 4. 按优先级匹配
    base_filter = [
        Bottle.status == "active",
        Bottle.author_id != user.id,
    ]
    if picked_author_ids:
        base_filter.append(Bottle.author_id.notin_(picked_author_ids))

    # 性别筛选
    gender_filter = []
    if target_gender in ("male", "female"):
        gender_filter.append(Bottle.gender == target_gender)

    # 校区筛选
    valid_school_ids = [s for s in (school_ids or []) if s]
    # 年龄筛选（期望对方年龄范围）
    has_age_filter = age_min is not None or age_max is not None
    # SQL 端年龄过滤：Bottle.author_age 在范围内（None 的瓶子不参与年龄筛选候选）
    age_filter_sql: list = []
    if has_age_filter:
        # author_age 为空的瓶子无法满足年龄筛选，直接排除
        age_filter_sql.append(Bottle.author_age.isnot(None))
        if age_min is not None:
            age_filter_sql.append(Bottle.author_age >= age_min)
        if age_max is not None:
            age_filter_sql.append(Bottle.author_age <= age_max)
    # 旧字段 grades（向后兼容）
    valid_grades = [g for g in (grades or []) if g in VALID_GRADES]
    # 兴趣标签（兼容旧字段 tags 与新字段 tag_preferred 合并）
    valid_preferred_tags = {t for t in (tag_preferred or []) if t}
    valid_preferred_tags.update({t for t in (tags or []) if t})
    # 必须有的标签（硬过滤）
    required_tags = [t for t in (tag_required or []) if t]

    # 构造"必须包含所有 required 标签"的 SQL 过滤条件。
    # Bottle.tags 以 JSON 数组字符串存储，使用 JSON_EXTRACT/LIKE 兜底匹配。
    # SQLite/MySQL 兼容写法：对每个 required tag，要求 tags 列包含该字符串。
    required_tag_filter = []
    for rt in required_tags:
        # tags 字段是 JSON 数组字符串，如 ["音乐","运动"]
        # 使用 LIKE 兜底匹配（包含 "tagname" 字符串）
        required_tag_filter.append(Bottle.tags.like(f'%"{rt}"%'))

    def _query_with_filter(extra_filters: list) -> Bottle | None:
        """应用额外过滤条件查询一个瓶子。"""
        stmt = select(Bottle).where(*base_filter, *extra_filters)
        # 随机选一个，按 id desc 取最新的若干条再随机
        stmt = stmt.order_by(Bottle.created_at.desc()).limit(20)
        rows = db.scalars(stmt).all()
        if not rows:
            return None
        # 如果有"尽量有"标签要求，按标签重叠度排序
        if valid_preferred_tags:
            def _overlap(b: Bottle) -> int:
                btags = set(_parse_json(b.tags, []))
                return len(btags & valid_preferred_tags)
            rows = sorted(rows, key=_overlap, reverse=True)
            return rows[0]
        # 否则取最新的
        return rows[0]

    # 优先级匹配：从最严格到最宽松
    # 注意：required_tag_filter 是硬过滤，会附加到每个候选条件上
    candidates: list[list] = []

    # 1. 同校区 + 年龄匹配 + 性别匹配
    if valid_school_ids and has_age_filter and gender_filter:
        candidates.append([
            Bottle.school_id.in_(valid_school_ids),
            *age_filter_sql,
            *gender_filter,
            *required_tag_filter,
        ])
    # 2. 同校区 + 年龄匹配
    if valid_school_ids and has_age_filter:
        candidates.append([
            Bottle.school_id.in_(valid_school_ids),
            *age_filter_sql,
            *required_tag_filter,
        ])
    # 3. 同校区 + 性别匹配
    if valid_school_ids and gender_filter:
        candidates.append([
            Bottle.school_id.in_(valid_school_ids),
            *gender_filter,
            *required_tag_filter,
        ])
    # 4. 年龄匹配 + 性别匹配
    if has_age_filter and gender_filter:
        candidates.append([
            *age_filter_sql,
            *gender_filter,
            *required_tag_filter,
        ])
    # 5. 同校区
    if valid_school_ids:
        candidates.append([Bottle.school_id.in_(valid_school_ids), *required_tag_filter])
    # 6. 年龄匹配
    if has_age_filter:
        candidates.append([*age_filter_sql, *required_tag_filter])
    # 7. 性别匹配
    if gender_filter:
        candidates.append([*gender_filter, *required_tag_filter])
    # 8. 旧字段：同年级（仅当用户传了 grades 时启用，向后兼容）
    if valid_grades:
        candidates.append([Bottle.grade.in_(valid_grades), *required_tag_filter])
    # 9. 任意 active（仍要满足 required_tag_filter）
    candidates.append([*required_tag_filter])

    bottle = None
    for filters in candidates:
        bottle = _query_with_filter(filters)
        if bottle:
            break

    if not bottle:
        # 完全没有可拾取的瓶子
        if required_tags:
            raise HTTPException(
                status_code=404,
                detail="海里暂时没有符合你『必须有』标签的瓶子了，过会儿再来看看吧",
            )
        raise HTTPException(status_code=404, detail="海里暂时没有瓶子了，过会儿再来看看吧")

    # 5. 写入拾取记录（瓶子状态保持 active，可被无数人继续拾取）
    # 不再修改 bottle.status / picked_by / picked_at —— 一个瓶子可被多人拾取
    pick_record = BottlePick(
        picker_id=user.id,
        bottle_id=bottle.id,
        author_id=bottle.author_id,
    )
    db.add(pick_record)
    db.commit()
    db.refresh(bottle)

    # 6. 加载作者信息和校区名，返回时暴露联系方式
    author = db.get(User, bottle.author_id)
    school = db.get(School, bottle.school_id)
    result = _bottle_dict(
        bottle,
        author=author,
        school_name=school.name if school else None,
        show_contact=True,  # 拾取成功，向拾取者展示作者的联系方式
    )
    # 附加本次拾取剩余次数
    result["remaining_picks_today"] = max(0, DAILY_PICK_LIMIT - today_count - 1)
    return result


def my_bottles(db: Session, user: User) -> dict:
    """查询当前用户投放的瓶子列表 + 被拾取统计。

    每个瓶子包含 picked_count（该瓶子被拾取的次数）。
    作者查看自己的瓶子时，contact 字段可见。
    """
    bottles = db.scalars(
        select(Bottle).where(Bottle.author_id == user.id).order_by(Bottle.created_at.desc())
    ).all()

    # 总被拾取次数
    picked_count = db.scalar(
        select(func.count())
        .select_from(BottlePick)
        .where(BottlePick.author_id == user.id)
    ) or 0

    # 每个瓶子被拾取的次数
    bottle_pick_counts: dict[int, int] = {}
    if bottles:
        bottle_ids = [b.id for b in bottles]
        rows = db.execute(
            select(BottlePick.bottle_id, func.count())
            .where(BottlePick.bottle_id.in_(bottle_ids))
            .group_by(BottlePick.bottle_id)
        ).all()
        bottle_pick_counts = {row[0]: int(row[1]) for row in rows}

    school_map = {}
    if bottles:
        school_ids = {b.school_id for b in bottles}
        schools = db.scalars(select(School).where(School.id.in_(school_ids))).all()
        school_map = {s.id: s.name for s in schools}

    items = []
    for b in bottles:
        d = _bottle_dict(b, author=user, school_name=school_map.get(b.school_id), show_contact=True)
        d["picked_count"] = bottle_pick_counts.get(b.id, 0)
        items.append(d)

    return {
        "bottles": items,
        "total": len(bottles),
        "picked_count": int(picked_count),
    }


def my_picks(db: Session, user: User) -> list[dict]:
    """查询当前用户拾取过的瓶子列表。"""
    picks = db.scalars(
        select(BottlePick)
        .where(BottlePick.picker_id == user.id)
        .order_by(BottlePick.created_at.desc())
    ).all()
    if not picks:
        return []
    bottle_ids = [p.bottle_id for p in picks]
    author_ids = list({p.author_id for p in picks})
    bottles = {b.id: b for b in db.scalars(select(Bottle).where(Bottle.id.in_(bottle_ids))).all()}
    authors = {u.id: u for u in db.scalars(select(User).where(User.id.in_(author_ids))).all()}
    school_ids = {b.school_id for b in bottles.values()}
    schools = {s.id: s.name for s in db.scalars(select(School).where(School.id.in_(school_ids))).all()}

    result = []
    for p in picks:
        b = bottles.get(p.bottle_id)
        if not b:
            continue
        author = authors.get(p.author_id)
        # 拾取记录中的瓶子，联系方式对拾取者可见
        d = _bottle_dict(b, author=author, school_name=schools.get(b.school_id), show_contact=True)
        d["picked_at"] = to_iso_zh(p.created_at)
        result.append(d)
    return result


def get_pick_status(db: Session, user: User) -> dict:
    """查询当前用户今日拾取状态。"""
    today_count = get_today_pick_count(db, user.id)
    return {
        "today_count": today_count,
        "daily_limit": DAILY_PICK_LIMIT,
        "remaining": max(0, DAILY_PICK_LIMIT - today_count),
    }


def recall_bottle(db: Session, user: User, bottle_id: int) -> dict:
    """作者主动收回瓶子。

    收回后瓶子状态变为 recalled，不再可被拾取。
    已有的拾取记录保留（拾取者仍可在"我的拾取"中看到瓶子内容）。
    """
    bottle = db.get(Bottle, bottle_id)
    if not bottle:
        raise HTTPException(status_code=404, detail=ErrorCode.TARGET_NOT_FOUND)
    if bottle.author_id != user.id:
        raise HTTPException(status_code=403, detail=ErrorCode.NO_PERMISSION)
    if bottle.status != "active":
        raise HTTPException(status_code=400, detail=f"当前状态为 {bottle.status}，无法收回")

    bottle.status = "recalled"
    db.commit()
    db.refresh(bottle)

    school = db.get(School, bottle.school_id)
    return _bottle_dict(bottle, author=user, school_name=school.name if school else None, show_contact=True)
