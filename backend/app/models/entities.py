from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
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
    # 额外宠物领养位：通过购买商城"宠物领养位"商品累加，可在基础上限(MAX_OWNED_PETS)之上再养更多宠物
    pet_extra_slots: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
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
    # 金币体系：余额 + 新手引导完成标记
    coins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    onboarding_done: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

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
    # 金币购买价格（0 = 不可购买）
    price: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


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


class BadgeRule(Base, TimestampMixin):
    """徽章自动发放规则表。

    将「用户行为动作 + 阈值」绑定到指定徽章：当用户在某个动作上达到阈值时，
    系统自动发放徽章并通知用户。扩展方式：新增动作时在 badge_service 注册
    对应的触发点即可，无需改动规则表结构。

    action 支持（当前已注册）：
    - checkin_consecutive  连续签到天数
    - approved_posts       审核通过的帖子数
    - approved_comments    审核通过的评论数
    - followers_count      粉丝数
    - likes_received       获赞总数
    """

    __tablename__ = "badge_rules"
    __table_args__ = (UniqueConstraint("action", "threshold", name="uq_badge_rule_action_threshold"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    badge_id: Mapped[int] = mapped_column(ForeignKey("badges.id"), index=True)
    # 达到该阈值即自动发放（>= threshold）
    threshold: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str | None] = mapped_column(String(200), default=None)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Post(Base, TimestampMixin):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    image_urls: Mapped[str] = mapped_column(Text, default="[]")
    # 视频（微信朋友圈 mp4 等）：JSON 数组，前端 HTML5 video 渲染
    video_urls: Mapped[str] = mapped_column(Text, default="[]")
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
    # 微信朋友圈同步：来源 / 关联朋友圈动态 / 置顶 / 朋友圈发布时间
    source: Mapped[str] = mapped_column(String(20), default="normal", index=True)
    # 抖音/快手原始分享文本（直链过期后可重新解析换新直链）
    video_share_text: Mapped[str | None] = mapped_column(Text, default=None)
    wechat_moment_id: Mapped[int | None] = mapped_column(
        ForeignKey("wechat_moments.id"), default=None, index=True
    )
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    pinned_until: Mapped[datetime | None] = mapped_column(DateTime, default=None, index=True)
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, index=True)

    # 求助帖：悬赏金币（求助区必填，其他圈子为 None）
    reward_coins: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    # 求助帖：是否已解决（楼主标记）
    is_solved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # 求助帖：最佳回复评论 id（楼主选定）
    best_comment_id: Mapped[int | None] = mapped_column(ForeignKey("comments.id"), default=None)
    solved_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

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
    # 求助帖：是否被楼主选为最佳回复
    is_best: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    best_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class TargetComment(Base, TimestampMixin):
    """通用留言板（组局/活动等非帖子内容的留言与回复）。

    - target_type: gathering（组局）/ activity（活动）
    - target_id: 对应业务表主键
    - parent_id: 回复的留言 id（null=一级留言）
    """

    __tablename__ = "target_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_type: Mapped[str] = mapped_column(String(20), index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("target_comments.id"), index=True)
    content: Mapped[str] = mapped_column(Text)


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
    read_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    # 扩展字段：消息类型（text/image），会话分组
    msg_type: Mapped[str] = mapped_column(String(20), default="text")
    conversation_id: Mapped[str | None] = mapped_column(String(64), default=None, index=True)


class Activity(Base, TimestampMixin):
    """校园活动（活动板块）。"""

    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(200), default=None)
    cover_url: Mapped[str | None] = mapped_column(String(500), default=None)
    start_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    organizer: Mapped[str | None] = mapped_column(String(100), default=None)
    contact: Mapped[str | None] = mapped_column(String(100), default=None)
    max_participants: Mapped[int | None] = mapped_column(Integer, default=None)
    participant_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("admin.id"), default=None)


class ActivityParticipant(Base):
    """活动报名表（一个用户同一活动只能报名一次）。"""

    __tablename__ = "activity_participants"
    __table_args__ = (UniqueConstraint("activity_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


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


class NotificationSetting(Base, TimestampMixin):
    """通知偏好设置（每个用户一行，所有开关默认开启）。"""

    __tablename__ = "notification_settings"
    __table_args__ = (UniqueConstraint("user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    like: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    comment: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    mention: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    follow: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    system: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    dm: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")


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
    # 图片审核状态：pending(待人工审核) / approved(已通过) / rejected(已驳回)
    # 图片不走 AI 审核，一律进入人工审核队列（后台「图片审核」页处理）
    audit_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)


class Announcement(Base, TimestampMixin):
    __tablename__ = "announcement"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    school_id: Mapped[int | None] = mapped_column(ForeignKey("schools.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 可见范围：all=所有人 / guest=仅游客（同一 IP 只投递一次）/ user=仅登录用户
    scope: Mapped[str] = mapped_column(String(10), default="all")


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


class AnnouncementGuestView(Base):
    """游客公告投递记录：(announcement_id, ip) 唯一 —— 同一 IP 对同一"仅游客"公告只投递一次。"""
    __tablename__ = "announcement_guest_views"
    __table_args__ = (UniqueConstraint("announcement_id", "ip", name="uq_ann_guest_ann_ip"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    announcement_id: Mapped[int] = mapped_column(ForeignKey("announcement.id", ondelete="CASCADE"), index=True)
    ip: Mapped[str] = mapped_column(String(64))
    viewed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


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
    # 内容审核状态：pending(AI审核中) / approved(已通过) / rejected(未通过) / manual_review(人工审核中)
    # AI 不可用时不直接放行，转人工审核；只有 approved 的瓶子才会进入拾取池
    audit_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reject_reason: Mapped[str | None] = mapped_column(String(200), default=None)
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
    # 创建管理员（启动自动生成/学生认证发放时为 None → 系统）
    created_by: Mapped[int | None] = mapped_column(ForeignKey("admin.id"), default=None)
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


class PostExploreStat(Base):
    """帖子探索推荐统计（曝光 → 互动反馈闭环）。

    探索推荐（Explore-Exploit）闭环：
    - 热门页按 ε 比例插入冷启动帖子（探索池），每次曝光 impressions + 1
    - 用户在探索曝光后点击详情 → click_count + 1
    - 用户在探索曝光后点赞/评论 → like_count / comment_count + 1（奖励信号）
    - Thompson 采样时：α = 互动数，β = 曝光数 - 互动数（下限 0）
    """

    __tablename__ = "post_explore_stats"

    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), primary_key=True)
    # 探索曝光次数（在推荐流中以探索位展示的次数）
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    # 点击进入详情次数（CTR = click_count / impressions）
    click_count: Mapped[int] = mapped_column(Integer, default=0)
    # 探索曝光后获得的点赞 / 评论数（奖励信号）
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class FeedImpressionLog(Base):
    """Feed 探索曝光日志（后台效果分析与审计用）。"""

    __tablename__ = "feed_impression_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    # 场景内目标（comment 场景 = 评论 id；帖子场景为 None）
    target_id: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    # 匿名用户为 None
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None, index=True)
    # 曝光场景：post_feed(帖子热门流) / comment(评论热门)
    scene: Mapped[str] = mapped_column(String(20), default="post_feed", index=True)
    page: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class VisitLog(Base, TimestampMixin):
    """网站访问记录：前端每次打开页面记录一行，用于后台访问次数 / 独立 IP 统计。"""

    __tablename__ = "visit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    ip: Mapped[str] = mapped_column(String(45), index=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), default=None)
    path: Mapped[str | None] = mapped_column(String(255), default=None)


class AppDownloadLog(Base, TimestampMixin):
    """手机端 APK 下载记录：统计下载次数 / 独立 IP。"""

    __tablename__ = "app_download_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    ip: Mapped[str] = mapped_column(String(45), index=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), default=None)


class WechatFriend(Base, TimestampMixin):
    """微信好友快照（由同步客户端从 contact.db 定期上报）。
    wxid 唯一；wechat_id 为用户设置的微信号（alias），用于绑定匹配。
    """

    __tablename__ = "wechat_friends"

    id: Mapped[int] = mapped_column(primary_key=True)
    wxid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    wechat_id: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    nickname: Mapped[str] = mapped_column(String(100), default="")
    remark: Mapped[str | None] = mapped_column(String(100), default=None)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class WechatBinding(Base, TimestampMixin):
    """用户与微信好友的绑定关系。
    绑定规则：先添加社区微信，再输入自己的微信号/wxid，匹配成功即绑定且不可自改。
    sync_enabled_at 为自动同步的历史分界线：只同步该时间之后发布的朋友圈。
    """

    __tablename__ = "wechat_bindings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    wxid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    wechat_id: Mapped[str | None] = mapped_column(String(64), default=None)
    nickname: Mapped[str] = mapped_column(String(100), default="")
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_enabled_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    bound_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # 分步绑定：status=pending（待消息验证码）-> verified（已绑定）
    status: Mapped[str] = mapped_column(String(20), default="pending")
    verify_code: Mapped[str | None] = mapped_column(String(16), default=None)
    verify_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    unbound_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    unbound_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin.id"), default=None
    )


class WechatMoment(Base, TimestampMixin):
    """同步客户端上报的原始朋友圈动态，tid 全局唯一用于增量去重。"""

    __tablename__ = "wechat_moments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    wxid: Mapped[str] = mapped_column(String(64), index=True)
    author_name: Mapped[str] = mapped_column(String(100), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    create_time: Mapped[datetime | None] = mapped_column(DateTime, default=None, index=True)
    media_json: Mapped[str] = mapped_column(Text, default="[]")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CoinTransaction(Base, TimestampMixin):
    """金币流水：所有增加/扣减必须写流水，可审计、可回溯。"""

    __tablename__ = "coin_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer, default=0)  # 正=增加 负=扣减
    balance_after: Mapped[int] = mapped_column(Integer, default=0)
    type: Mapped[str] = mapped_column(String(32), default="", index=True)
    ref_id: Mapped[str | None] = mapped_column(String(64), default=None)
    description: Mapped[str | None] = mapped_column(String(200), default=None)


class WechatRecentMessage(Base):
    """客户端上报的"社区账号收到的最近消息"，用于绑定验证码校验。"""

    __tablename__ = "wechat_recent_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    peer_wxid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    last_text: Mapped[str] = mapped_column(Text, default="")
    last_time: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ============ 今日竞猜（押注） ============


class Guess(Base, TimestampMixin):
    """每日竞猜主题。

    同一时间只能有 1 条 is_active=True（首页焦点区展示）。
    管理员每天 0 点后创建新竞猜，设置选项与截止时间；
    截止后由管理员调用 settle() 结算（填写 winning_option_id）。
    """

    __tablename__ = "guesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    # 补充说明（支持多行，弹窗与焦点区描述均展示）
    description: Mapped[str | None] = mapped_column(Text, default=None)
    # 押注截止时间（超过后选项置灰不可押）
    deadline: Mapped[datetime] = mapped_column(DateTime, index=True)
    # 结算结果（settle 前为 None）
    winning_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("guess_options.id"), default=None, index=True
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    # 是否处于"今日活跃"（首页焦点区 + 登录弹窗展示）
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # 活跃竞猜的唯一性约束（按日期天然每天一次，由服务层保证 is_active 只有一条 True）
    date_key: Mapped[str] = mapped_column(String(20), index=True, default="")  # YYYY-MM-DD
    created_by: Mapped[int | None] = mapped_column(ForeignKey("admin.id"), default=None)
    settled_by: Mapped[int | None] = mapped_column(ForeignKey("admin.id"), default=None)


class GuessOption(Base):
    """竞猜选项（A/B/…，≥2）。"""

    __tablename__ = "guess_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    guess_id: Mapped[int] = mapped_column(ForeignKey("guesses.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(60))  # 如 "主队赢" "平局" "客队赢"
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # 累计押注积分（来自 bet.amount 之和），结算时用于计算赔率/池
    total_points: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # 累计押注人数（唯一用户），用于焦点区展示热度
    total_users: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class GuessBet(Base):
    """竞猜押注记录（复用 users.coins 金币作为积分；后续可拆分独立 points 字段）。"""

    __tablename__ = "guess_bets"
    __table_args__ = (UniqueConstraint("user_id", "guess_id", name="uq_user_guess_once"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    guess_id: Mapped[int] = mapped_column(ForeignKey("guesses.id"), index=True)
    option_id: Mapped[int] = mapped_column(ForeignKey("guess_options.id"), index=True)
    # 本次押注积分（>0）
    amount: Mapped[int] = mapped_column(Integer, default=0)
    # 结算后拿到的净奖励（可能为负=全输；为 0 表示未结算）
    reward: Mapped[int] = mapped_column(Integer, default=0)
    # win/lose/refund/cancel
    result: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # 用户是否已在今日选择「今日不押注」：仅当 amount=0 时置 1
    skipped: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ============ 宠物商城 ============


class PetCategory(Base, TimestampMixin):
    """宠物商城商品分类（后台可维护，前台分类 Tab 数据源）。"""

    __tablename__ = "pet_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    icon: Mapped[str | None] = mapped_column(String(20), default=None)  # emoji 图标
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class PetProduct(Base, TimestampMixin):
    """宠物商城商品。

    - status: 1=上架（用户侧可见） / 0=下架
    - image_url: 主图 URL（/uploads/... 或完整 http 地址）；也兼容 emoji 占位符
    - model_3d_url: GLB/GLTF 3D 模型地址（选填，详情页用 model-viewer 展示）
    - anim_json: 帧动画配置（DyberPet 像素宠物）：{"slug": "...", "actions": [
        {"key": "stand", "label": "待机", "frames": ["/uploads/pets/x/a_0.png"], "interval": 80}, ...]}
    - price 单位为金币（整数存 Float）；活体宠物每人限领 1 只（adopt 接口校验）
    """

    __tablename__ = "pet_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("pet_categories.id"), index=True)
    price: Mapped[float] = mapped_column(Float)
    original_price: Mapped[float | None] = mapped_column(Float, default=None)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    image_url: Mapped[str | None] = mapped_column(String(500), default=None)
    model_3d_url: Mapped[str | None] = mapped_column(String(500), default=None)
    anim_json: Mapped[str | None] = mapped_column(Text, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    sales: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[int] = mapped_column(Integer, default=1, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("admin.id"), default=None)
    # 商品类型：1=活体宠物（限领1只） 2=食物/玩具/日用/医疗道具（可重复购买进背包） 3=进化道具（用于宠物进化）
    kind: Mapped[int] = mapped_column(Integer, default=1, index=True)
    # 宠物是否能飞行（后台"萌宠领养"可见）：可飞行的宠物在帖子卡片/悬浮宠会自动触发"上抛悬空再落回"的飞行行为
    can_fly: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # 道具按类型定制的数值字段（JSON，后台按商品类型暴露不同编辑框）：
    #   kind=2：{"affinity": 好感+, "satiety": 饱腹+} 食物类(狗粮/猫粮/零食)
    #          {"affinity":N,"mood":N,"play":N} 玩具类
    #          {"affinity":N,"mood":N,"stamina":N,"health":N} 日用/医疗类
    #   kind=1 活体宠物可含 {"idle_interval_sec": N}（非必需）
    # 注意：食物的"好感加成"沿用下方 affinity_gain 列；attrs 存储其余维度（饱腹/心情/玩耍/体力/健康等）。
    attrs: Mapped[str | None] = mapped_column(Text, default=None)
    # 好感加成：食物喂食时增加的好感值；进化道具此值为0
    affinity_gain: Mapped[int] = mapped_column(Integer, default=0)
    # ============ AI 对话（宠物接入大模型） ============
    # 该宠物是否启用 AI 对话（后台可逐宠物管理）
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # 人设 prompt（后台可编辑：性格/口癖/语气/背景小故事），为空时用默认人设
    ai_persona: Mapped[str | None] = mapped_column(Text, default=None)
    # 是否允许"主动找你"（调度器按人设自主规划下次唤醒）
    ai_wake_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # ============ 游戏动作触发宠物说话（陪我玩） ============
    # 自定义宠物可选填的 JSON 常量：{"start":"开始","win":"赢","lose":"输","good":"不错"}
    # 与 ai_persona 同一块后台编辑；为空时前端用内置默认话术
    game_speech: Mapped[str | None] = mapped_column(Text, default=None)


class UserPet(Base, TimestampMixin):
    """用户已领养的宠物（金币购买活体宠物后归属用户，每只宠物限领 1 次）。"""

    __tablename__ = "user_pets"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_user_pet_once"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("pet_products.id"), index=True)
    # 好感度 0-100：喂食/互动累积
    affinity: Mapped[int] = mapped_column(Integer, default=0)
    # 等级 1-6（Lv1幼崽→Lv2幼年→Lv3少年→Lv4青年→Lv5成年→Lv6灵魂伴侣），由好感度阶段决定
    level: Mapped[int] = mapped_column(Integer, default=1)
    # 是否超级进化（好感满100 + 使用进化水晶后）
    evolved: Mapped[bool] = mapped_column(Boolean, default=False)
    evolved_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    # 进化后可自定义昵称
    nickname: Mapped[str | None] = mapped_column(String(20), default=None)
    # 互动冷却时间戳（服务端校验，防止刷好感）
    last_pet_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    last_feed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    last_play_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    # 每日好感上限（防刷）
    daily_affinity_date: Mapped[str | None] = mapped_column(String(10), default=None)
    daily_affinity_gained: Mapped[int] = mapped_column(Integer, default=0)
    # 饱食度 0-100：随时间衰减（每4小时-10），<30 进入饿虚状态，喂食恢复
    satiety: Mapped[int] = mapped_column(Integer, default=100)
    last_satiety_decay: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    # 点击互动计数（用于假随机掉落 pity 机制）
    interact_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class UserPetItem(Base, TimestampMixin):
    """宠物道具背包（食物等，可重复持有）。"""

    __tablename__ = "user_pet_items"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_user_pet_item"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("pet_products.id"), index=True)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class GratitudeList(Base, TimestampMixin):
    """感谢名单（后台可编辑，前端列表 + 详情页展示）。

    - name: 名字
    - avatar_url: 头像
    - bio: 一句话简介（列表展示）
    - detail: 详细介绍（详情页展示）
    - sort_order: 排序（越小越靠前）
    - is_active: 是否上架展示
    """

    __tablename__ = "gratitude_list"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    avatar_url: Mapped[str | None] = mapped_column(String(500), default=None)
    bio: Mapped[str | None] = mapped_column(String(200), default=None)
    detail: Mapped[str | None] = mapped_column(Text, default=None)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# ============ 组局（线上开黑 / 线下活动） ============


class Gathering(Base, TimestampMixin):
    """组局。

    - type: online（线上开黑）/ offline（线下活动）
    - status: recruiting（招募中）/ cancelled（已取消）/ ended（已结束）
    - images: JSON 数组字符串（组局配图 URL 列表）
    - 创建成功后发起人自动占用一个名额（joined_people 从 1 起算）
    """

    __tablename__ = "gatherings"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100), index=True)
    type: Mapped[str] = mapped_column(String(20), default="online", index=True)
    category: Mapped[str] = mapped_column(String(50), default="")
    start_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    location: Mapped[str | None] = mapped_column(String(200), default=None)
    max_people: Mapped[int] = mapped_column(Integer, default=10)
    joined_people: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    images: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), default="recruiting", index=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)


class GatheringParticipant(Base):
    """组局报名记录（一个用户对同一组局只能报名一次）。"""

    __tablename__ = "gathering_participants"
    __table_args__ = (UniqueConstraint("gathering_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    gathering_id: Mapped[int] = mapped_column(ForeignKey("gatherings.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ============ 游戏中心（赚金币小游戏） ============


class Game(Base, TimestampMixin):
    """游戏中心里的游戏（单人/多人），配置每局可赚金币量。

    - type: single（单人）/ multi（多人，暂未开放）
    - source: builtin（内置）/ user（用户「制作游戏」提交）
    - status: active（上架）/ pending（待审核，用户提交）/ rejected（已驳回）
    - html_content: 用户自制游戏源码，通过 GET /games/{slug}/play 在线游玩
    - reward_coins: 刷新最佳战绩可获得的单次金币奖励
    - daily_limit: 每日可领取奖励的次数上限（防刷）
    - affinity_daily_limit: 每日通过该游戏可获得的好感度上限（本地宠物游戏发放好感时控制）
    """

    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(20), default="single", index=True)  # single / multi
    description: Mapped[str | None] = mapped_column(Text, default=None)
    icon_url: Mapped[str | None] = mapped_column(String(255), default=None)
    # 每局可赚金币 + 每日上限（后台可配置）
    reward_coins: Mapped[int] = mapped_column(Integer, default=5)
    daily_limit: Mapped[int] = mapped_column(Integer, default=5)
    # 每日通过该游戏(玩耍)可获得的好感度上限
    affinity_daily_limit: Mapped[int] = mapped_column(Integer, default=20)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(20), default="builtin")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    html_content: Mapped[str | None] = mapped_column(Text, default=None)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)


# ============ 小游戏成绩（首页排行-游戏排行） ============


class GameRecord(Base, TimestampMixin):
    """用户小游戏最佳战绩（higher-better 分值，服务端持久化）。

    前端 PetPlay.vue 每款游戏刷新最佳战绩后上报，user_id + game_key 唯一，
    提交值大于已有值时覆盖（Upsert）。用于「游戏排行」与「全部排行」。
    """

    __tablename__ = "game_records"
    __table_args__ = (UniqueConstraint("user_id", "game_key", name="uq_game_record_user_game"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    game_key: Mapped[str] = mapped_column(String(32))
    best_score: Mapped[int] = mapped_column(Integer, default=0)


class GameAffinity(Base, TimestampMixin):
    """用户每天通过各小游戏获得的好感度累计。

    user_id + game_key + date 唯一（date 为北京日期 YYYY-MM-DD），
    用于按游戏配置的 affinity_daily_limit 限制「玩这个游戏一天最多加多少好感」。
    """

    __tablename__ = "game_affinity_records"
    __table_args__ = (
        UniqueConstraint("user_id", "game_key", "date", name="uq_game_affinity_user_game_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    game_key: Mapped[str] = mapped_column(String(32), index=True)
    date: Mapped[str] = mapped_column(String(10), default="", index=True)
    amount: Mapped[int] = mapped_column(Integer, default=0)


# ============ 宠物 AI 对话（DeepSeek 引擎） ============


class PetAiMessage(Base, TimestampMixin):
    """宠物 AI 聊天记录。

    - role: user（用户消息）/ assistant（AI 回复，content 为单段文本）/
            tool（工具调用结果卡片，content 为 [工具] xxx）/ system（事件触发等系统消息）
    - meta: JSON 字符串，可存放工具名/分段序号等附加信息
    - 分段消息：assistant 回复按「#换行符」拆成多条独立记录，每条 content 为一段
    """

    __tablename__ = "pet_ai_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey("pet_products.id"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="user", index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[str | None] = mapped_column(Text, default=None)
    # 是否已读：宠物 AI 发给用户（assistant/tool）的消息默认未读，用户打开会话后标记已读（用于消息中心红点）"
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class PetAiState(Base, TimestampMixin):
    """宠物 AI 运行时状态（每个用户-宠物一行）。

    - sleeping_until: 睡觉截止时间（UTC naive）；非空且未过期表示 AI 正在睡觉
    - daily_date: 当日日期（北京时间 YYYY-MM-DD），用于按天重置额度
    - daily_token: 今日已消耗 token 数
    - daily_proactive_count: 今日已主动发消息次数（事件触发也计入）
    - last_message_at: 最近一次消息时间（用户/AI 均更新），主动消息调度用
    - next_proactive_at: 决策出的下次主动消息触发时间（UTC naive）
    """

    __tablename__ = "pet_ai_state"
    __table_args__ = (UniqueConstraint("user_id", "pet_id", name="uq_pet_ai_state_user_pet"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey("pet_products.id"), index=True)
    sleeping_until: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    daily_date: Mapped[str | None] = mapped_column(String(10), default=None)
    daily_token: Mapped[int] = mapped_column(Integer, default=0)
    daily_proactive_count: Mapped[int] = mapped_column(Integer, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    next_proactive_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    last_gift_date: Mapped[str | None] = mapped_column(String(10), default=None)
    last_gift_coins: Mapped[int] = mapped_column(Integer, default=0)
    last_affinity_date: Mapped[str | None] = mapped_column(String(10), default=None)
    last_affinity_add: Mapped[int] = mapped_column(Integer, default=0)
    last_affinity_sub: Mapped[int] = mapped_column(Integer, default=0)


class UserActivity(Base):
    """用户行为记录（宠物 AI 主动消息/对话上下文注入）。

    前端上报用户在应用内的关键动作（看帖子/看列表/看商城/发消息/报名组局等），
    仅用于 AI 理解上下文，不写入聊天记录原文。
    """

    __tablename__ = "user_activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
