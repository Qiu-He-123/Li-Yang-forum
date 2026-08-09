"""帖子业务逻辑层。"""
import asyncio
import json

from fastapi import HTTPException, Request
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import SessionLocal
from app.core.errors import ErrorCode
from app.core.time_utils import to_iso_zh
from app.models import Category, Comment, Post, School, User
from app.schemas.post import CATEGORIES, PostCreate, PostUpdate
from app.services.ai_service import ai_service
from app.services.audit_log import log_user_action


def _is_valid_category(db: Session, category: str) -> bool:
    """校验分类是否合法：接受圈子 name 或 slug，也兼容旧版硬编码 CATEGORIES。

    前端 PostEditor 现在发送的是圈子 slug（如 'default'、'food'）或圈子 name（如 '校园圈'）。
    旧版硬编码 CATEGORIES（'普通'、'树洞' 等）保留兼容，因为历史帖子仍使用这些值。
    """
    if not category:
        return False
    # 1. 命中旧版硬编码分类（历史数据兼容）
    if category in CATEGORIES:
        return True
    # 2. 命中圈子 name 或 slug（新版圈子系统）
    exists = db.scalar(
        select(Category.id).where(
            (Category.name == category) | (Category.slug == category)
        )
    )
    return exists is not None


def post_dict(post: Post, comment_count: int | None = None, db: Session | None = None) -> dict:
    """序列化帖子为前端响应字典。

    Args:
        post: Post 实例（需已加载 author/school 关系）
        comment_count: 真实评论数（可选，列表场景不需要单独查询）
        db: Session（可选，传入则输出 topic_name/poll/mention_users 等扩展字段）
    """
    author_name = "匿名同学" if post.is_anonymous else post.author.nickname
    from app.services.badge_service import badge_dict as _badge_dict
    author_badge = (
        None if post.is_anonymous else _badge_dict(getattr(post.author, "wearing_badge", None))
    )
    data = {
        "id": post.id,
        "content": post.content,
        "image_urls": json.loads(post.image_urls or "[]"),
        "is_anonymous": post.is_anonymous,
        "category": post.category,
        "school": post.school.name,
        "school_id": post.school_id,
        "author": author_name,
        "author_id": post.author_id,
        "author_avatar_url": post.author.avatar_url if post.author.avatar_url else None,
        "author_badge": author_badge,
        "is_public": post.is_public,
        "is_draft": post.is_draft,
        "like_count": post.like_count,
        "comment_count": post.comment_count if comment_count is None else comment_count,
        "tags": json.loads(post.tags or "[]"),
        "ai_status": post.ai_status,
        "reject_reason": post.reject_reason,
        "created_at": to_iso_zh(post.created_at),
        # 圈子扩展字段
        "title": post.title,
        "is_original": post.is_original,
        "has_ai_content": post.has_ai_content,
        "view_count": post.view_count,
        "share_count": post.share_count,
        "last_reply_at": to_iso_zh(post.last_reply_at),
        # 阶段二新增字段
        "topic_id": post.topic_id,
        "topic_name": None,
        "location": post.location,
        "has_poll": False,  # 默认无投票；下方 db 不为 None 时按实际查询覆盖
    }
    # 扩展字段（需 db）：避免在列表场景下 N+1 查询，默认不输出
    if db is not None:
        if post.topic_id:
            from app.services import topic_service
            data["topic_name"] = topic_service.get_topic_name(db, post.topic_id)
        # 查询是否有关联投票
        from app.models import Poll
        has_poll = db.scalar(select(Poll.id).where(Poll.post_id == post.id)) is not None
        data["has_poll"] = has_poll
    return data


def list_posts(
    view: str,
    db: Session,
    user: User | None,
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    category: str | None = None,
    tag: str | None = None,
) -> dict:
    """查询帖子列表（支持分页/搜索/分类/标签过滤）。

    view: all / school / hot / latest
    user: None 时匿名访问，只返回公开帖子；school view 需登录。
    返回: {items, total, page, page_size}

    搜索时（q 非空）会写入 search_histories 与更新 hot_searches 计数（需登录）。
    """
    from sqlalchemy import func, or_

    query = select(Post).options(selectinload(Post.author), selectinload(Post.school)).where(Post.is_draft.is_(False))
    # 私密帖子只有作者本人可见（匿名用户只看公开）
    if user is not None:
        query = query.where(or_(Post.is_public.is_(True), Post.author_id == user.id))
        if view == "school":
            query = query.where(Post.school_id == user.school_id)
        # AI 审核可见性：他人只能看到 approved；作者本人可见 pending/approved/rejected
        query = query.where(or_(Post.ai_status == "approved", Post.author_id == user.id))
    else:
        query = query.where(Post.is_public.is_(True))
        # 匿名用户只能看到审核通过的帖子
        query = query.where(Post.ai_status == "approved")
    if q:
        # 同时搜索 content 和 title
        keyword = f"%{q}%"
        query = query.where(or_(Post.content.like(keyword), Post.title.like(keyword)))
    if category:
        query = query.where(Post.category == category)
    if tag:
        # T6-8：标签搜索。tags 字段存 JSON 数组字符串，用 LIKE 匹配。
        query = query.where(Post.tags.like(f'%"{tag}"%'))
    # 总数（在排序/分页前计算）
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    # 排序
    if view == "hot":
        query = query.order_by(desc(Post.like_count), desc(Post.comment_count), desc(Post.created_at))
    else:
        query = query.order_by(desc(Post.created_at))
    # 分页
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    posts = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()

    # 搜索时记录历史 + 更新热搜（仅登录用户）
    if q and user is not None:
        try:
            from app.services.search_service import record_search
            record_search(db, user, q)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            from loguru import logger
            logger.warning("[SEARCH] record_search failed: {}", exc)
            db.rollback()

    return {
        "items": [post_dict(post) for post in posts],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def create_post(payload: PostCreate, request: Request, db: Session, user: User) -> dict:
    """创建帖子：校验 → 落库（ai_status=pending）→ 立即返回 → 后台异步审核。

    改造说明（本次功能性 bug 修复）：
    - 之前同步等待 AI 审核结果才落库，发帖延迟 5-10 秒
    - 现在先落库 status=pending 立即返回，AI 审核在后台异步进行
    - 前端通过 ai_status 字段显示「AI审核中/已通过/审核失败」徽标
    - AI 不可用时直接 approved（与原"降级放行"行为一致）

    阶段二新增：
    - topic_name：查询或创建 Topic，关联 post.topic_id
    - location：直接存到 post.location
    - mention_user_ids：创建 Mention 记录 + 发送 mention 通知
    - poll：创建 Poll + PollOption
    - 有 topic_id 时给话题关注者发 type='topic' 通知
    """
    if not _is_valid_category(db, payload.category):
        raise HTTPException(status_code=400, detail=ErrorCode.CATEGORY_NOT_FOUND)
    if not db.get(School, payload.school_id):
        raise HTTPException(status_code=400, detail=ErrorCode.SCHOOL_NOT_FOUND)
    if len(payload.image_urls) > 9:
        raise HTTPException(status_code=400, detail=ErrorCode.IMAGES_TOO_MANY)

    # 封号用户禁止发帖（含草稿）：封号状态由 user_service.get_ban_status 动态计算
    # current_user 依赖允许封号用户通过认证（以便查看封号原因和申诉），但写操作必须拦截
    from app.services import user_service
    ban_status = user_service.get_ban_status(user, db)
    if ban_status["is_banned"]:
        raise HTTPException(status_code=403, detail=ErrorCode.USER_BANNED)

    # AI 审核可用性检查：DeepSeek 或 OpenAI 任一可用即触发审核
    # 之前只检查 OpenAI，导致仅配置 DeepSeek 时审核被跳过
    from app.services import audit_service
    ai_available = audit_service.is_ai_audit_available(db)
    initial_ai_status = "pending" if ai_available else "approved"

    # 阶段二：处理话题（草稿也支持）
    topic_id: int | None = None
    if payload.topic_name:
        from app.services import topic_service
        topic = topic_service.get_or_create_topic(db, payload.topic_name, creator_id=user.id)
        topic_id = topic.id

    post = Post(
        author_id=user.id,
        school_id=payload.school_id,
        category=payload.category,
        content=payload.content,
        image_urls=json.dumps(payload.image_urls, ensure_ascii=False),
        is_anonymous=payload.is_anonymous,
        is_public=payload.is_public,
        is_draft=payload.is_draft,
        tags=json.dumps([], ensure_ascii=False),  # 标签由后台 AI 审核时生成
        ai_status=initial_ai_status,
        # 圈子扩展字段
        title=payload.title,
        is_original=payload.is_original,
        has_ai_content=payload.has_ai_content,
        # 阶段二新增字段
        topic_id=topic_id,
        location=payload.location,
    )
    db.add(post)
    db.flush()

    # 阶段二：处理话题计数（仅非草稿）
    if topic_id is not None and not payload.is_draft:
        from app.models import Topic
        topic_row = db.get(Topic, topic_id)
        if topic_row:
            topic_row.post_count = (topic_row.post_count or 0) + 1

    # 阶段二：处理 @ 提及（草稿不发送通知，但保留 Mention 记录）
    from app.services import mention_service
    final_mention_ids = mention_service.extract_mentions(payload.content, payload.mention_user_ids, db)
    if final_mention_ids:
        mention_service.create_mentions(db, post.id, final_mention_ids)

    # 阶段二：处理投票（草稿不创建投票，避免后续正式发布时重复）
    if payload.poll is not None and not payload.is_draft:
        from app.services import poll_service
        poll_service.create_poll_for_post(
            db,
            post_id=post.id,
            title=payload.poll.title,
            multi_vote=payload.poll.multi_vote,
            deadline=payload.poll.deadline,
            options=payload.poll.options,
        )

    log_user_action(
        db,
        user.id,
        "create_post" if not payload.is_draft else "save_draft",
        json.dumps({"post_id": post.id, "category": payload.category, "anonymous": payload.is_anonymous}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    db.refresh(post)

    # 阶段二：发送通知（非草稿才发送，commit 后避免回滚）
    if not payload.is_draft:
        if final_mention_ids:
            mention_service.send_mention_notifications(db, post.id, final_mention_ids, user.id)
            db.commit()
        if topic_id is not None:
            from app.services import topic_service
            topic_service.notify_topic_followers(db, post.id, topic_id, user.id)
            db.commit()

    # 后台异步审核（仅 pending 状态触发；草稿不审核）
    if initial_ai_status == "pending" and not payload.is_draft:
        asyncio.create_task(audit_service.audit_post_background(post.id, payload.content))

    return post_dict(post, db=db)


async def _audit_post_background(post_id: int, content: str) -> None:
    """[已废弃] 后台异步审核帖子。

    请使用 app.services.audit_service.audit_post_background 替代。
    此函数保留仅为向后兼容，内部委托给 audit_service。
    """
    from app.services import audit_service
    await audit_service.audit_post_background(post_id, content)


async def update_post(post_id: int, payload: PostUpdate, request: Request, db: Session, user: User) -> dict:
    """更新帖子：权限校验 + AI 审核 + 审计日志。

    阶段二新增字段处理：
    - topic_name：变更话题（重新解析，更新 topic_id 与原话题/新话题 post_count）
    - location：直接更新
    - mention_user_ids：重新构建 Mention（先删旧记录再创建）
    - poll：暂不支持更新投票结构（如需修改请删除重发）
    """
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)
    if post.author_id != user.id:
        raise HTTPException(status_code=403, detail=ErrorCode.NO_PERMISSION)
    changes = payload.model_dump(exclude_unset=True)
    if "category" in changes and not _is_valid_category(db, changes["category"]):
        raise HTTPException(status_code=400, detail=ErrorCode.CATEGORY_NOT_FOUND)
    if "school_id" in changes and not db.get(School, changes["school_id"]):
        raise HTTPException(status_code=400, detail=ErrorCode.SCHOOL_NOT_FOUND)
    if "content" in changes:
        post.content = changes.pop("content")
        # 内容变更需重新审核：标记 pending，后台异步审核（与发帖一致）
        from app.services import audit_service
        if audit_service.is_ai_audit_available(db):
            post.ai_status = "pending"
        else:
            post.ai_status = "approved"
        # 编辑后清空旧标签，等审核通过后由后台重新生成
        post.tags = json.dumps([], ensure_ascii=False)
    if "image_urls" in changes:
        changes["image_urls"] = json.dumps(changes["image_urls"], ensure_ascii=False)

    # 阶段二：处理话题变更
    new_topic_id = post.topic_id
    if "topic_name" in changes:
        from app.services import topic_service
        old_topic_id = post.topic_id
        new_name = changes.pop("topic_name")
        if new_name:
            new_topic = topic_service.get_or_create_topic(db, new_name, creator_id=user.id)
            new_topic_id = new_topic.id
        else:
            new_topic_id = None
        # topic_id 由后续 setattr 处理；先把 old/new topic 的 post_count 同步
        if old_topic_id != new_topic_id:
            if old_topic_id is not None:
                from app.models import Topic as _TopicModel
                old_topic = db.get(_TopicModel, old_topic_id)
                if old_topic and old_topic.post_count and old_topic.post_count > 0:
                    old_topic.post_count -= 1
            # 非草稿才累加新话题计数
            if new_topic_id is not None and not post.is_draft:
                from app.models import Topic as _TopicModel
                new_topic = db.get(_TopicModel, new_topic_id)
                if new_topic:
                    new_topic.post_count = (new_topic.post_count or 0) + 1
        post.topic_id = new_topic_id

    # 阶段二：处理位置变更
    if "location" in changes:
        post.location = changes.pop("location")

    # 阶段二：处理提及变更（重新构建 Mention）
    if "mention_user_ids" in changes:
        from app.models import Mention
        from app.services import mention_service
        explicit_ids = changes.pop("mention_user_ids") or []
        # 删除旧 Mention
        db.query(Mention).filter(Mention.post_id == post_id).delete()
        # 重新解析 + 创建
        final_ids = mention_service.extract_mentions(post.content, explicit_ids, db)
        if final_ids:
            mention_service.create_mentions(db, post.id, final_ids)
            # 非草稿才发通知
            if not post.is_draft:
                mention_service.send_mention_notifications(db, post.id, final_ids, user.id)

    # 阶段二：处理投票变更（仅当传入 poll 字段且帖子尚未关联投票时创建）
    if "poll" in changes:
        new_poll = changes.pop("poll")
        if new_poll and not post.is_draft:
            from app.models import Poll
            from app.services import poll_service
            existing_poll = db.scalar(select(Poll).where(Poll.post_id == post.id))
            if existing_poll is None:
                # model_dump 后 new_poll 为 dict，options 已是 list[str]
                poll_service.create_poll_for_post(
                    db,
                    post_id=post.id,
                    title=new_poll["title"],
                    multi_vote=new_poll["multi_vote"],
                    deadline=new_poll["deadline"],
                    options=new_poll["options"],
                )

    for key, value in changes.items():
        if key not in ("content",):  # content 已在上面处理
            setattr(post, key, value)
    log_user_action(db, user.id, "update_post", json.dumps({"post_id": post_id, "fields": list(payload.model_dump(exclude_unset=True).keys())}, ensure_ascii=False), _extract_ip(request))
    db.commit()
    db.refresh(post)

    # 内容变更后触发后台异步审核（与发帖一致）
    if "content" in payload.model_dump(exclude_unset=True) and post.ai_status == "pending" and not post.is_draft:
        from app.services import audit_service
        asyncio.create_task(audit_service.audit_post_background(post.id, post.content))

    return post_dict(post, db=db)


def delete_post(post_id: int, request: Request, db: Session, user: User) -> None:
    """删除帖子：权限校验 + 审计日志。"""
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)
    if post.author_id != user.id:
        raise HTTPException(status_code=403, detail=ErrorCode.NO_PERMISSION)
    # 递减话题 post_count（仅非草稿帖子）
    if post.topic_id is not None and not post.is_draft:
        from app.models import Topic
        topic_row = db.get(Topic, post.topic_id)
        if topic_row and topic_row.post_count and topic_row.post_count > 0:
            topic_row.post_count -= 1
    db.delete(post)
    log_user_action(db, user.id, "delete_post", json.dumps({"post_id": post_id}, ensure_ascii=False), _extract_ip(request))
    db.commit()


def get_post(post_id: int, db: Session, user: User | None) -> dict:
    """查询单个帖子详情（P1：帖子详情页 deeplink 用）。

    权限规则：
    - 草稿仅作者本人可见
    - 私密帖子（is_public=False）仅作者本人可见，非作者访问返回 POST_PRIVATE
    - AI 审核未通过/审核中：仅作者本人可见（他人看到 404）
    - 其余帖子任何人（含匿名）均可查看

    错误码区分：
    - POST_NOT_FOUND：帖子不存在或已被删除（含草稿）
    - POST_PRIVATE：帖子为私密发布，仅作者可见（非作者访问时返回）

    优化：非作者访问审核中/被拒帖子时，返回带 is_viewable=False 的帖子数据，
    前端展示"审核中 暂无法查看原文"提示，而非 404。
    """
    # 第一步：仅按 id + 非草稿 查询，判断帖子是否存在
    post = db.scalar(
        select(Post)
        .options(selectinload(Post.author), selectinload(Post.school))
        .where(Post.id == post_id)
        .where(Post.is_draft.is_(False))
    )
    if not post:
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)

    is_author = (user is not None and post.author_id == user.id)

    # 第二步：私密帖子权限校验——非作者访问返回 POST_PRIVATE（区别于已删除）
    if not post.is_public and not is_author:
        raise HTTPException(status_code=403, detail=ErrorCode.POST_PRIVATE)

    if not is_author and post.ai_status != "approved":
        data = post_dict(post, db=db)
        if post.ai_status == "pending":
            data["title"] = "该帖子正在审核中"
            data["content"] = "审核中，暂无法查看原文"
        elif post.ai_status == "rejected":
            data["title"] = "该帖子未通过审核"
            data["content"] = "该帖子未通过审核，暂无法查看原文"
        elif post.ai_status == "manual_review":
            data["title"] = "该帖子正在人工复核"
            data["content"] = "人工复核中，暂无法查看原文"
        data["image_urls"] = []
        data["tags"] = []
        data["is_viewable"] = False
        data["view_block_reason"] = post.ai_status
        return data

    # 查询真实评论数用于响应展示（不写回 post.comment_count，避免每次详情都触发写锁）
    real_comment_count = db.scalar(select(func.count(Comment.id)).where(Comment.post_id == post_id)) or 0
    data = post_dict(post, comment_count=real_comment_count, db=db)
    data["is_viewable"] = True
    return data


def related_posts(post_id: int, db: Session, user: User | None, limit: int = 4) -> list[dict]:
    """相关推荐：同圈子/同分类的帖子，排除当前帖子和私密帖子（非作者本人）。

    优先同 category + 同 school，不足补充同 category，再不足补充同 school。
    """
    from sqlalchemy import or_

    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)

    # 根据登录状态构建可见性过滤
    if user is not None:
        visibility = or_(Post.is_public.is_(True), Post.author_id == user.id)
        # AI 审核可见性：他人只见 approved；作者本人可见 pending/approved/rejected
        ai_visibility = or_(Post.ai_status == "approved", Post.author_id == user.id)
    else:
        visibility = Post.is_public.is_(True)
        ai_visibility = Post.ai_status == "approved"

    def _build_stmt(extra_filters: list) -> list[Post]:
        stmt = (
            select(Post)
            .options(selectinload(Post.author), selectinload(Post.school))
            .where(
                Post.id != post_id,
                Post.is_draft.is_(False),
                visibility,
                ai_visibility,
                *extra_filters,
            )
            .order_by(desc(Post.like_count), desc(Post.created_at))
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    # 1) 同 category + 同 school
    posts = _build_stmt([Post.category == post.category, Post.school_id == post.school_id])
    # 2) 不足补同 category
    if len(posts) < limit:
        existing_ids = {p.id for p in posts}
        more = db.scalars(
            select(Post)
            .options(selectinload(Post.author), selectinload(Post.school))
            .where(
                Post.id != post_id,
                Post.is_draft.is_(False),
                visibility,
                ai_visibility,
                Post.category == post.category,
            )
            .order_by(desc(Post.like_count), desc(Post.created_at))
            .limit(limit - len(posts))
        ).all()
        # 排除已选中的帖子
        more = [p for p in more if p.id not in existing_ids]
        posts.extend(more)
    # 3) 仍不足补同 school
    if len(posts) < limit:
        existing_ids = {p.id for p in posts}
        more = db.scalars(
            select(Post)
            .options(selectinload(Post.author), selectinload(Post.school))
            .where(
                Post.id != post_id,
                Post.is_draft.is_(False),
                visibility,
                ai_visibility,
                Post.school_id == post.school_id,
            )
            .order_by(desc(Post.like_count), desc(Post.created_at))
            .limit(limit - len(posts))
        ).all()
        more = [p for p in more if p.id not in existing_ids]
        posts.extend(more)

    return [post_dict(p) for p in posts[:limit]]


def share_post(post_id: int, db: Session) -> dict:
    """分享计数（幂等，share_count +1）。

    优化：直接 UPDATE 替代 load+modify+save+refresh，减少 DB 往返与写锁持有时间。
    """
    from sqlalchemy import update

    result = db.execute(
        update(Post)
        .where(Post.id == post_id)
        .values(share_count=func.coalesce(Post.share_count, 0) + 1)
        .returning(Post.share_count)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)
    db.commit()
    return {"id": post_id, "share_count": row[0]}


def view_post(post_id: int, db: Session) -> dict:
    """浏览计数（view_count +1，可前端调用，幂等累加）。

    优化：直接 UPDATE 替代 load+modify+save+refresh，减少 DB 往返与写锁持有时间。
    原 4 次 DB 操作（SELECT + WRITE + SELECT refresh）合并为 1 次 UPDATE...RETURNING。
    """
    from sqlalchemy import update

    result = db.execute(
        update(Post)
        .where(Post.id == post_id)
        .values(view_count=func.coalesce(Post.view_count, 0) + 1)
        .returning(Post.view_count)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)
    db.commit()
    return {"id": post_id, "view_count": row[0]}


def list_drafts(db: Session, user: User) -> list[dict]:
    """获取当前用户的草稿列表（按更新时间倒序，仅本人可见）。

    草稿自动保存：前端定期 PATCH /posts/{id}（is_draft=True），
    后端复用 update_post 落库，此函数仅做列表查询。
    """
    stmt = (
        select(Post)
        .options(selectinload(Post.author), selectinload(Post.school))
        .where(Post.author_id == user.id, Post.is_draft.is_(True))
        .order_by(desc(Post.updated_at))
    )
    posts = db.scalars(stmt).all()
    return [post_dict(p, db=db) for p in posts]


def _extract_ip(request) -> str | None:
    try:
        from app.api.deps import extract_ip

        return extract_ip(request)
    except Exception:
        return None
