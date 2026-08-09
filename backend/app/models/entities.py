from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class School(Base, TimestampMixin):
    __tablename__ = "schools"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    nickname: Mapped[str] = mapped_column(String(32), index=True)
    # 登录账号：username（新方案，唯一）/ phone（旧字段，保留向后兼容，可空）
    username: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, default=None)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True, default=None)
    password_hash: Mapped[str] = mapped_column(String(255))
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), index=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    background_url: Mapped[str | None] = mapped_column(String(500))
    bio: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 封号管理：封禁截止时间（NULL=未封禁或永久封禁）/ 封禁原因 / 违规次数
    ban_until: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    ban_reason: Mapped[str | None] = mapped_column(String(200), default=None)
    violation_count: Mapped[int] = mapped_column(Integer, default=0)
    # 警告值系统：累计警告值（违规增加，签到/发帖等积极行为减少）
    warning_score: Mapped[int] = mapped_column(Integer, default=0)
    # 圈子扩展：年级（如"高三"）/ 关注数 / 粉丝数
    grade: Mapped[str | None] = mapped_column(String(20), default=None)
    # 年龄系统：生日（设置后动态计算年龄，替代 grade 字段）
    birthday: Mapped[date | None] = mapped_column(Date, default=None)
    # 性别：male / female / unknown（用于漂流瓶和实时匹配）
    gender: Mapped[str] = mapped_column(String(20), default="unknown")
    following_count: Mapped[int] = mapped_column(Integer, default=0)
    followers_count: Mapped[int] = mapped_column(Integer, default=0)
    # 私信权限：everyone / mutual_only / stranger_once（默认）/ no_stranger
    message_permission: Mapped[str] = mapped_column(String(20), default="stranger_once")
    # ===== 邀请码系统（三状态：guest/unverified/verified）=====
    # QQ号（选填，用于找回账号）
    qq: Mapped[str | None] = mapped_column(String(20), default=None)
    # 认证状态：unverified（已注册未填邀请码）/ verified（已填邀请码，解锁全部功能）
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified", index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    # 自己的邀请码（注册时自动生成 8 位字符）
    invite_code: Mapped[str | None] = mapped_column(String(16), unique=True, index=True, default=None)
    # 上次成功分享邀请码时间（用于 3 天冷却）
    invite_code_shared_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    # 邀请人（谁邀请的我）
    invited_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    # 连坐冻结截止时间：被邀请人违规核实后，邀请人 N 天内不能分享邀请码
    invite_privilege_until: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    # 徽章系统：当前佩戴的徽章（每人可拥有多个徽章，选择其中一个佩戴）
    wearing_badge_id: Mapped[int | None] = mapped_column(
        ForeignKey("badges.id"), default=None, index=True
    )

    school: Mapped[School] = relationship()
    wearing_badge: Mapped["Badge | None"] = relationship(
        foreign_keys=[wearing_badge_id], lazy="selectin"
    )


class Badge(Base, TimestampMixin):
    """徽章表（勋章机制）。

    徽章以图标（emoji 或图片 URL）展示，每个用户可以拥有多个徽章，
    通过 users.wearing_badge_id 选择佩戴哪一个，佩戴徽章会在所有
    展示名字的场景中显示在名字之前（如 [🏅] 我的名字）。
    """

    __tablename__ = "badges"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    # 唯一标识 code（如 admin / group_member），也用于种子徽章去重
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    # 徽章图标：优先 emoji（如 🏅），也支持图片 URL
    icon: Mapped[str] = mapped_column(String(500), default="🏅")
    description: Mapped[str | None] = mapped_column(String(200), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # 系统徽章（如管理员/集团成员）不允许删除，只可停用
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)


class BadgeCode(Base, TimestampMixin):
    """徽章激活码表。

    管理员在后台为指定徽章批量生成激活码，用户通过「消息 → 系统」的
    领取徽章入口输入激活码即可获得对应徽章。每个激活码仅可使用一次。
    """

    __tablename__ = "badge_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    badge_id: Mapped[int] = mapped_column(ForeignKey("badges.id"), index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    # 备注（如"发给张三"）与批次号（管理员批量生成时分配）
    note: Mapped[str | None] = mapped_column(String(100), default=None)
    batch_no: Mapped[str | None] = mapped_column(String(32), index=True, default=None)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("admin.id"), default=None)
    used_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class UserBadge(Base):
    """用户徽章关系表（一人可拥有多个徽章）。"""

    __tablename__ = "user_badges"
    __table_args__ = (UniqueConstraint("user_id", "badge_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    badge_id: Mapped[int] = mapped_column(ForeignKey("badges.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Post(Base, TimestampMixin):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    image_urls: Mapped[str] = mapped_column(Text, default="[]")
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[str] = mapped_column(Text, default="[]")
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    # AI 审核状态：pending(审核中) / approved(已通过) / rejected(AI审核失败,待人工复核) / manual_review(人工复核中)
    ai_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # 审核未通过原因（管理员填写）
    reject_reason: Mapped[str | None] = mapped_column(String(200), default=None)
    # 圈子扩展字段：标题 / 是否原创 / 浏览数 / 分享数 / 最后回复时间
    title: Mapped[str | None] = mapped_column(String(100), default=None)
    is_original: Mapped[bool] = mapped_column(Boolean, default=False)
    has_ai_content: Mapped[bool] = mapped_column(Boolean, default=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    share_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reply_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    # 阶段二新增字段
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id"), default=None, index=True)
    location: Mapped[str | None] = mapped_column(String(100), default=None)
    # 邀请码系统：未认证用户到期后隐藏（保留作者本人可见）
    is_hidden_by_unverify: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    author: Mapped[User] = relationship()
    school: Mapped[School] = relationship()


class Comment(Base, TimestampMixin):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("comments.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    # AI 审核状态：pending(审核中) / approved(已通过) / rejected(AI审核失败,待人工复核) / manual_review(人工复核中)
    ai_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # 审核未通过原因（管理员填写）
    reject_reason: Mapped[str | None] = mapped_column(String(200), default=None)
    # 邀请码系统：未认证用户到期后隐藏（保留作者本人可见）
    is_hidden_by_unverify: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class Like(Base, TimestampMixin):
    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("user_id", "target_type", "target_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(20), index=True)
    target_id: Mapped[int] = mapped_column(index=True)


class Favorite(Base, TimestampMixin):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "post_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)


class Message(Base, TimestampMixin):
    """私信消息表。

    支持好友间私信，消息按会话分组（conversation_id）。
    """

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    receiver_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    # 扩展字段：消息类型（text/image），会话分组
    msg_type: Mapped[str] = mapped_column(String(20), default="text")
    conversation_id: Mapped[str | None] = mapped_column(String(64), default=None, index=True)


class FriendRequest(Base):
    """好友请求表。"""

    __tablename__ = "friend_requests"
    __table_args__ = (UniqueConstraint("from_id", "to_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    from_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    to_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending/accepted/rejected
    message: Mapped[str | None] = mapped_column(String(200), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Notification(Base, TimestampMixin):
    """通知中心表。

    通知类型 type：interaction(互动) / comment(评论) / like(点赞) / follow(关注) / system(系统) / announcement(公告)
    - sender_id: 触发通知的用户 id（系统通知为 None）
    - reference_type / reference_id: 关联对象（post/comment/user）
    - read_at: 已读时间（未读为 None）
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    # 通知扩展字段
    type: Mapped[str] = mapped_column(String(20), default="system", index=True)
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None, index=True)
    reference_type: Mapped[str | None] = mapped_column(String(20), default=None)
    reference_id: Mapped[int | None] = mapped_column(Integer, default=None)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class Category(Base, TimestampMixin):
    """圈子（分类）表。

    每个圈子对应一个 slug 用于 URL 友好访问，如 /circles/default。
    """

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    icon: Mapped[str | None] = mapped_column(String(20), default=None)
    description: Mapped[str | None] = mapped_column(String(200), default=None)
    color: Mapped[str] = mapped_column(String(20), default="#007aff")
    post_count: Mapped[int] = mapped_column(Integer, default=0)
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 阶段四：用户自创建吧相关
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None, index=True)
    status: Mapped[str] = mapped_column(String(20), default="approved", index=True)  # pending/approved/rejected
    reject_reason: Mapped[str | None] = mapped_column(String(200), default=None)
    audit_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    audited_by: Mapped[int | None] = mapped_column(ForeignKey("admin.id"), default=None)


class CategoryAdmin(Base, TimestampMixin):
    """吧主表（圈子管理员）。"""

    __tablename__ = "category_admins"
    __table_args__ = (UniqueConstraint("category_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="owner")  # owner/admin


class UserCategory(Base):
    """用户加入圈子关系表（多对多）。"""

    __tablename__ = "user_categories"
    __table_args__ = (UniqueConstraint("user_id", "category_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Follow(Base):
    """用户关注关系表。

    follower_id 关注 followee_id，单向关系。
    """

    __tablename__ = "follows"
    __table_args__ = (UniqueConstraint("follower_id", "followee_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    follower_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    followee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SearchHistory(Base):
    """用户搜索历史表。"""

    __tablename__ = "search_histories"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    keyword: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class HotSearch(Base):
    """热搜词表。"""

    __tablename__ = "hot_searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    last_updated: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Report(Base, TimestampMixin):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(20), index=True)
    target_id: Mapped[int] = mapped_column(index=True)
    reason: Mapped[str] = mapped_column(String(200))
    ai_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")


class Admin(Base, TimestampMixin):
    __tablename__ = "admin"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="admin")


class LoginLog(Base, TimestampMixin):
    __tablename__ = "login_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    phone: Mapped[str | None] = mapped_column(String(20), index=True)
    ip: Mapped[str | None] = mapped_column(String(64))
    device: Mapped[str | None] = mapped_column(String(200))
    success: Mapped[bool] = mapped_column(Boolean, default=False)


class OperationLog(Base, TimestampMixin):
    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("admin.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    # T3-2: action 加 index=True，/admin/user-logs 按 action 过滤性能提升
    action: Mapped[str] = mapped_column(String(100), index=True)
    detail: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(64))


class Token(Base, TimestampMixin):
    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    refresh_token: Mapped[str] = mapped_column(String(700), unique=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Image(Base, TimestampMixin):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    url: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(50))
    size_bytes: Mapped[int] = mapped_column(Integer)
    # P0-1：私密图片（学生证等敏感照片）与公开图片分离，禁止走公开静态目录
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)


class Announcement(Base, TimestampMixin):
    __tablename__ = "announcement"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    school_id: Mapped[int | None] = mapped_column(ForeignKey("schools.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Setting(Base, TimestampMixin):
    """系统设置表（key-value 结构）。

    用于存储管理员可通过后台修改的配置，例如：
    - deepseek_api_key: DeepSeek API 密钥
    - deepseek_base_url: DeepSeek API 基础 URL
    - deepseek_model: DeepSeek 模型名（如 deepseek-chat）
    - deepseek_enabled: 是否启用 DeepSeek 审核（true/false）
    - audit_auto_delete_days: 审核失败内容自动删除天数（整数，0=不自动删除）
    """
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str | None] = mapped_column(String(200))


class CheckIn(Base):
    """每日签到记录表。

    一个用户每天只能签到一次，通过 (user_id, check_in_date) 唯一约束保证。
    consecutive_days 记录连续签到天数，用于奖励计算。
    """

    __tablename__ = "check_ins"
    __table_args__ = (UniqueConstraint("user_id", "check_in_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    check_in_date: Mapped[datetime] = mapped_column(DateTime, index=True)  # 当天 0 点
    consecutive_days: Mapped[int] = mapped_column(Integer, default=1)
    reward_points: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BrowseHistory(Base):
    """用户浏览帖子历史表。

    记录用户浏览过的帖子，用于「浏览历史」功能。
    同一用户重复浏览同一帖子时更新 viewed_at（不重复插入）。
    """

    __tablename__ = "browse_histories"
    __table_args__ = (UniqueConstraint("user_id", "post_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    viewed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Topic(Base, TimestampMixin):
    """话题表。"""
    __tablename__ = "topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None, index=True)
    post_count: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(String(200), default=None)


class Mention(Base, TimestampMixin):
    """帖子 @ 提及关系表。"""
    __tablename__ = "mentions"
    __table_args__ = (UniqueConstraint("post_id", "mentioned_user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    mentioned_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)


class Poll(Base, TimestampMixin):
    """投票表。"""
    __tablename__ = "polls"
    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(100))
    multi_vote: Mapped[bool] = mapped_column(Boolean, default=False)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class PollOption(Base, TimestampMixin):
    """投票选项表。"""
    __tablename__ = "poll_options"
    id: Mapped[int] = mapped_column(primary_key=True)
    poll_id: Mapped[int] = mapped_column(ForeignKey("polls.id"), index=True)
    content: Mapped[str] = mapped_column(String(100))
    vote_count: Mapped[int] = mapped_column(Integer, default=0)


class PollVote(Base):
    """投票记录表。"""
    __tablename__ = "poll_votes"
    __table_args__ = (UniqueConstraint("option_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    option_id: Mapped[int] = mapped_column(ForeignKey("poll_options.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TopicFollow(Base):
    """用户关注话题表。"""
    __tablename__ = "topic_follows"
    __table_args__ = (UniqueConstraint("user_id", "topic_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BanRecord(Base, TimestampMixin):
    """封号记录表。

    记录每次封禁操作，支持时长封禁和永久封禁。
    - duration_hours: 封禁时长（小时），0=永久封禁
    - ban_until: 封禁截止时间（NULL=永久封禁）
    - status: active(生效中) / expired(已过期) / revoked(已撤销解封)
    - appealable: 是否允许申诉
    """
    __tablename__ = "ban_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("admin.id"), default=None)
    reason: Mapped[str] = mapped_column(String(200))
    duration_hours: Mapped[int] = mapped_column(Integer, default=0)
    ban_until: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    banned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    unbanned_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    appealable: Mapped[bool] = mapped_column(Boolean, default=True)


class Appeal(Base, TimestampMixin):
    """用户申诉表。

    用户对封号或内容审核结果提出申诉，管理员审核后给出回复。
    - status: pending(待处理) / approved(申诉成功) / rejected(申诉驳回)
    - ban_record_id: 关联封号记录（可为空：一般申诉）
    - review_comment: 管理员审核回复
    """
    __tablename__ = "appeals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ban_record_id: Mapped[int | None] = mapped_column(ForeignKey("ban_records.id"), default=None)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("admin.id"), default=None)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    review_comment: Mapped[str | None] = mapped_column(Text, default=None)


class AuditLog(Base, TimestampMixin):
    """AI 审核日志表。

    记录每次 AI 审核的完整信息，供管理端查看审核明细和统计分析。
    - target_type: post / comment
    - target_id: 帖子 ID 或评论 ID
    - ai_provider: deepseek / openai / none
    - result: approved(通过) / rejected(违规) / error(异常)
    - reason: 审核原因（违规时为违规说明，通过时为空）
    - category: 违规分类（如 politics/porn/abuse/ad/spam/none）
    - severity: 违规严重程度（high/medium/low/none）
    - content_snapshot: 审核时的内容快照（前 500 字）
    """
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_type: Mapped[str] = mapped_column(String(20), index=True)  # post / comment
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None, index=True)
    ai_provider: Mapped[str] = mapped_column(String(20), default="none")  # deepseek / openai / none
    result: Mapped[str] = mapped_column(String(20), index=True)  # approved / rejected / error
    reason: Mapped[str] = mapped_column(String(500), default="")
    category: Mapped[str] = mapped_column(String(30), default="none")
    severity: Mapped[str] = mapped_column(String(20), default="none")
    content_snapshot: Mapped[str] = mapped_column(Text, default="")


class Feedback(TimestampMixin, Base):
    """用户意见反馈表。"""
    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(String(50), default="other")  # bug/suggestion/question/other
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    contact: Mapped[str | None] = mapped_column(String(200), nullable=True)  # 联系方式（选填）
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/replied/closed
    image_urls: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    replies: Mapped[list["FeedbackReply"]] = relationship(
        back_populates="feedback", cascade="all, delete-orphan", lazy="selectin"
    )


class FeedbackReply(TimestampMixin, Base):
    """反馈回复表（管理员回复用户反馈）。"""
    __tablename__ = "feedback_replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    feedback_id: Mapped[int] = mapped_column(ForeignKey("feedbacks.id", ondelete="CASCADE"), index=True)
    replier_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)  # 回复者（管理员）
    content: Mapped[str] = mapped_column(Text)

    feedback: Mapped["Feedback"] = relationship(back_populates="replies")


class CircleView(Base):
    """用户浏览圈子历史表（我的足迹）。

    记录用户浏览过的圈子，用于「我的足迹」功能。
    同一用户重复浏览同一圈子时更新 viewed_at（不重复插入）。
    """
    __tablename__ = "circle_views"
    __table_args__ = (UniqueConstraint("user_id", "circle_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    circle_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    viewed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class WarningLog(Base):
    """警告值变动记录表。

    每次警告值变化（增加/减少）都写一条记录，用户可在个人主页查看。
    - delta: 变化量（正数增加，负数减少）
    - score_after: 变动后的警告值
    - source: violation(违规) / checkin(签到) / post(发帖审核通过) / comment(评论审核通过) / admin_adjust(管理员调整) / system(系统)
    - related_type/related_id: 关联对象（如 post/comment）
    - operator_id: 操作管理员 ID（仅 admin_adjust 有值）
    """
    __tablename__ = "warning_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    score_after: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(20), default="system", index=True)
    related_type: Mapped[str | None] = mapped_column(String(20), default=None)
    related_id: Mapped[int | None] = mapped_column(Integer, default=None)
    operator_id: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class WarningConfig(Base):
    """警告值系统配置表（单行配置，id 固定为 1）。

    阈值机制：
    - warning_score < warn_threshold: 正常
    - warning_score >= warn_threshold: 发警告通知
    - warning_score >= temp_ban_threshold: 封号 temp_ban_hours 小时
    - warning_score >= perm_ban_threshold: 永久封号
    """
    __tablename__ = "warning_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    warn_threshold: Mapped[int] = mapped_column(Integer, default=30)
    temp_ban_threshold: Mapped[int] = mapped_column(Integer, default=60)
    temp_ban_hours: Mapped[int] = mapped_column(Integer, default=24)
    perm_ban_threshold: Mapped[int] = mapped_column(Integer, default=100)
    violation_base_score: Mapped[int] = mapped_column(Integer, default=20)
    checkin_reduce: Mapped[int] = mapped_column(Integer, default=2)
    post_reduce: Mapped[int] = mapped_column(Integer, default=1)
    comment_reduce: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# ============ 漂流瓶 & 实时匹配 & 公告已读 ============

class AnnouncementRead(Base):
    """公告已读记录：用户阅读过的公告，用于登录后弹窗去重。"""
    __tablename__ = "announcement_reads"
    __table_args__ = (UniqueConstraint("user_id", "announcement_id", name="uq_ann_read_user_ann"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    announcement_id: Mapped[int] = mapped_column(ForeignKey("announcement.id"), index=True)
    read_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Bottle(Base):
    """漂流瓶：用户投放的瓶子，可被其他用户拾取。

    一个瓶子可被无数人拾取（保持 active），同一拾取者对同一作者只能拾取一次。
    作者可主动收回（status=recalled），收回后不再可被拾取。
    """
    __tablename__ = "bottles"
    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str | None] = mapped_column(Text)
    image_urls: Mapped[str] = mapped_column(Text, default="[]")
    # 必选标签
    grade: Mapped[str] = mapped_column(String(20), index=True)        # 高一/高二/高三（旧字段，保留兼容）
    # 年龄系统：作者投放时的年龄（从生日计算，快照）
    author_age: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), index=True)
    gender: Mapped[str] = mapped_column(String(20), default="unknown")  # 作者性别
    # 可选兴趣标签（JSON 数组字符串）
    tags: Mapped[str] = mapped_column(Text, default="[]")
    # 状态：active(可拾取) / picked(旧字段，已弃用，保留向后兼容) / recalled(作者收回) / expired(过期)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    picked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # 旧字段，保留兼容
    picked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 旧字段，保留兼容
    # 联系方式（QQ/微信/手机等，拾取成功后对拾取者可见）
    contact: Mapped[str | None] = mapped_column(String(100), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BottlePick(Base):
    """漂流瓶拾取记录：防止同一用户重复拾取同一作者的瓶子。"""
    __tablename__ = "bottle_picks"
    __table_args__ = (UniqueConstraint("picker_id", "author_id", name="uq_bottle_pick_picker_author"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    picker_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    bottle_id: Mapped[int] = mapped_column(ForeignKey("bottles.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MatchQueue(Base):
    """实时匹配队列：等待匹配的用户。"""
    __tablename__ = "match_queue"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    gender: Mapped[str] = mapped_column(String(20), default="unknown")        # 自己性别
    target_gender: Mapped[str] = mapped_column(String(20), default="any")     # 期望对方性别：male/female/any
    grades: Mapped[str] = mapped_column(Text, default="[]")        # JSON 期望年级（旧字段，保留兼容）
    # 年龄系统：期望年龄范围（13-18）
    age_min: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    age_max: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    school_ids: Mapped[str] = mapped_column(Text, default="[]")   # JSON 期望校区
    tags: Mapped[str] = mapped_column(Text, default="[]")         # JSON 兴趣标签（尽量有，软排序）
    tag_required: Mapped[str] = mapped_column(Text, default="[]")  # JSON 必须有的标签（硬过滤）
    status: Mapped[str] = mapped_column(String(20), default="waiting", index=True)  # waiting/matched/cancelled/timeout
    matched_with: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class MatchSession(Base):
    """实时匹配临时会话：匹配成功后的 180 秒聊天会话。"""
    __tablename__ = "match_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_a: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    user_b: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active/ended/expired
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    mutual_follow: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MatchMessage(Base):
    """临时聊天消息：实时匹配会话中的消息。"""
    __tablename__ = "match_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("match_sessions.id"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ============ 邀请码系统 ============

class InviteCodeUsage(Base):
    """邀请码使用记录：每次有人填邀请码成功解锁时记录一条。

    用于连坐追溯：被邀请人若被核实非学生，邀请人将被冻结 N 天邀请资格。
    """
    __tablename__ = "invite_code_usages"
    __table_args__ = (UniqueConstraint("invitee_id", name="uq_invitee_once"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # 邀请人（分享码的用户）
    inviter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # 被邀请人（填码解锁的用户，每个用户只能填一次）
    invitee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # 实际使用的邀请码（冗余字段，便于审计）
    code: Mapped[str] = mapped_column(String(16), index=True)
    used_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # 连坐状态：active(正常) / frozen(因被邀请人违规而冻结过邀请人资格)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)


class SeedInviteCode(Base):
    """种子邀请码：管理员预生成的初始邀请码，无邀请人。

    冷启动阶段：管理员线下把种子码发给可靠的班长/学生会主席，
    学生用种子码注册即可直接获得 verified 状态（无需再填邀请码）。
    每个种子码只能使用一次。

    状态机：
    - unused: 未使用（可被管理员「复制并标记待使用」选取）
    - reserved: 待使用（已被某位管理员复制带走，其他管理员应避免重复分发）
    - used: 已使用（用户注册/填码消耗）
    """
    __tablename__ = "seed_invite_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    # 备注（如"给张三的种子码"），便于管理员追踪
    note: Mapped[str | None] = mapped_column(String(100), default=None)
    # 批次号（管理员批量生成时分配，便于按批次查询）
    batch_no: Mapped[str | None] = mapped_column(String(32), index=True, default=None)
    # 状态：unused / reserved / used
    status: Mapped[str] = mapped_column(String(20), default="unused", index=True)
    # 待使用状态：由哪位管理员复制带走（其他管理员据此避免重复分发）
    reserved_by: Mapped[int | None] = mapped_column(ForeignKey("admin.id"), default=None)
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    used_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class StudentVerification(Base):
    """学生认证申请：用户上传学生证/校园卡照片，管理员审核后自动发放邀请码。

    流程：
    1. 用户在 InviteCodeDialog 或设置页上传照片
    2. 管理员在后台审核（approve/reject）
    3. approve → 自动生成种子邀请码并分配给用户 → 用户变为 verified
    4. reject → 通知用户重新上传

    防护：
    - 每个用户只能有一个 pending 状态的申请
    - 每天最多提交 3 次（防刷）
    - 管理员审核时记录 reviewer_id
    """
    __tablename__ = "student_verifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # 上传的凭证照片 URL
    image_url: Mapped[str] = mapped_column(String(500))
    # 申请说明（选填）
    note: Mapped[str | None] = mapped_column(String(200), default=None)
    # 状态：pending(待审核) / approved(已通过) / rejected(已驳回)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # 审核人
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("admin.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 驳回原因（reject 时填写）
    reject_reason: Mapped[str | None] = mapped_column(String(200), default=None)
    # 审核通过时自动生成的邀请码（便于追溯）
    granted_invite_code: Mapped[str | None] = mapped_column(String(16), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
