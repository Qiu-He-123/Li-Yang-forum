"""今日竞猜服务：创建/上下架/押注/跳过/结算/获取当日竞猜聚合。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import Guess, GuessBet, GuessOption, User
from app.services import coin_service


def _today_key(d: date | None = None) -> str:
    d = d or date.today()
    return d.strftime("%Y-%m-%d")


def get_active_guess(db: Session, for_date: date | None = None) -> Guess | None:
    """获取当前日期活跃的竞猜（首页焦点区 + 登录弹窗展示）。"""
    key = _today_key(for_date)
    stmt = (
        select(Guess)
        .where(and_(Guess.is_active.is_(True), Guess.date_key == key))
        .order_by(Guess.id.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _get_options(db: Session, guess_id: int) -> list[GuessOption]:
    stmt = select(GuessOption).where(GuessOption.guess_id == guess_id).order_by(GuessOption.sort_order, GuessOption.id)
    return list(db.execute(stmt).scalars())


def guess_with_options(db: Session, guess: Guess) -> dict[str, Any]:
    """把竞猜 + 选项 + 每个选项的汇总返回给前端（用于焦点区实时数据）。"""
    options = _get_options(db, guess.id)
    all_bet_users = db.scalar(select(func.sum(GuessOption.total_users)).where(GuessOption.guess_id == guess.id)) or 0
    all_bet_points = db.scalar(select(func.sum(GuessOption.total_points)).where(GuessOption.guess_id == guess.id)) or 0
    return {
        "id": guess.id,
        "title": guess.title,
        "description": guess.description,
        "deadline": guess.deadline.isoformat() if guess.deadline else None,
        "is_active": guess.is_active,
        "date_key": guess.date_key,
        "winning_option_id": guess.winning_option_id,
        "settled_at": guess.settled_at.isoformat() if guess.settled_at else None,
        "total_users": int(all_bet_users),
        "total_points": int(all_bet_points),
        "options": [
            {
                "id": o.id,
                "label": o.label,
                "sort_order": o.sort_order,
                "total_points": int(o.total_points or 0),
                "total_users": int(o.total_users or 0),
            }
            for o in options
        ],
    }


def get_my_bet(db: Session, user_id: int, guess_id: int) -> GuessBet | None:
    stmt = select(GuessBet).where(and_(GuessBet.user_id == user_id, GuessBet.guess_id == guess_id))
    return db.execute(stmt).scalar_one_or_none()


# --------------------- 用户侧：押注 / 跳过 ---------------------

def place_bet(db: Session, user: User, guess_id: int, option_id: int, amount: int) -> GuessBet:
    if amount is None or amount < 10:
        raise HTTPException(status_code=400, detail="最少押注 10 积分")
    if amount > 10_000:
        raise HTTPException(status_code=400, detail="单次最多押注 10000 积分")

    guess = db.get(Guess, guess_id)
    if not guess or not guess.is_active:
        raise HTTPException(status_code=400, detail="竞猜不存在或已结束")
    if datetime.now() >= guess.deadline:
        raise HTTPException(status_code=400, detail="押注已截止")
    if guess.settled_at is not None:
        raise HTTPException(status_code=400, detail="该竞猜已结算")

    option = db.get(GuessOption, option_id)
    if not option or option.guess_id != guess_id:
        raise HTTPException(status_code=400, detail="押注选项不合法")

    existing = get_my_bet(db, user.id, guess_id)
    if existing and not existing.skipped:
        raise HTTPException(status_code=400, detail="今日竞猜您已参与")

    # 扣除金币（积分），记录流水
    coin_service.charge_coins(
        db, user, amount, "guess_bet",
        ref_id=f"g{guess_id}:o{option_id}",
        description=f"今日竞猜押注：{guess.title} · {option.label}",
    )

    if existing and existing.skipped:
        # 覆盖"今日不押注"记录为实际押注
        existing.option_id = option.id
        existing.amount = amount
        existing.skipped = False
        existing.result = "pending"
        bet = existing
    else:
        bet = GuessBet(
            user_id=user.id,
            guess_id=guess.id,
            option_id=option.id,
            amount=amount,
        )
        db.add(bet)

    # 聚合：total_points 直接累加；total_users 只有该选项第一次押注该用户时+1
    option.total_points = (option.total_points or 0) + amount
    already_cnt = db.scalar(
        select(func.count(GuessBet.id))
        .where(and_(GuessBet.option_id == option.id, GuessBet.skipped.is_(False), GuessBet.id != (bet.id or 0)))
    ) or 0
    if already_cnt == 0:
        option.total_users = (option.total_users or 0) + 1

    db.flush()
    return bet


def skip_today(db: Session, user: User, guess_id: int) -> GuessBet:
    guess = db.get(Guess, guess_id)
    if not guess:
        raise HTTPException(status_code=400, detail="竞猜不存在")
    existing = get_my_bet(db, user.id, guess_id)
    if existing:
        return existing  # 已押或已跳过，均返回不变
    # 跳过：选 winning_option 为兜底（实际结算时 result=refund 不扣），amount=0
    first_opt = _get_options(db, guess.id)[0]
    bet = GuessBet(
        user_id=user.id,
        guess_id=guess.id,
        option_id=first_opt.id,
        amount=0,
        skipped=True,
        result="refund",
    )
    db.add(bet)
    db.flush()
    return bet


# --------------------- 管理员侧：创建 / 激活 / 结束 / 结算 ---------------------

def create_guess(
    db: Session,
    *,
    title: str,
    description: str | None,
    deadline: datetime,
    date_key: str | None,
    options: list[str],
    admin_id: int,
) -> Guess:
    if not title or len(title) > 120:
        raise HTTPException(status_code=400, detail="标题不能为空且不超过 120 字")
    if deadline <= datetime.now():
        raise HTTPException(status_code=400, detail="截止时间必须晚于当前")
    if not options or len(options) < 2:
        raise HTTPException(status_code=400, detail="至少 2 个选项")
    if len(options) > 8:
        raise HTTPException(status_code=400, detail="选项最多 8 个")
    date_key = date_key or _today_key()

    # 把同日期其他活跃竞猜置为非活跃（保证当日只展示 1 个）
    db.query(Guess).where(Guess.date_key == date_key).update({Guess.is_active: False}, synchronize_session=False)

    guess = Guess(
        title=title,
        description=description,
        deadline=deadline,
        date_key=date_key,
        is_active=True,
        created_by=admin_id,
    )
    db.add(guess)
    db.flush()
    for i, label in enumerate(options):
        db.add(GuessOption(guess_id=guess.id, label=label.strip(), sort_order=i))
    db.flush()
    return guess


def toggle_active(db: Session, guess_id: int, is_active: bool, admin_id: int) -> Guess:
    guess = db.get(Guess, guess_id)
    if not guess:
        raise HTTPException(status_code=404, detail="竞猜不存在")
    if is_active:
        db.query(Guess).where(Guess.date_key == guess.date_key).update({Guess.is_active: False}, synchronize_session=False)
    guess.is_active = is_active
    db.flush()
    return guess


def delete_guess(db: Session, guess_id: int, admin_id: int) -> None:
    guess = db.get(Guess, guess_id)
    if not guess:
        raise HTTPException(status_code=404, detail="竞猜不存在")
    if guess.settled_at is not None:
        raise HTTPException(status_code=400, detail="已结算的竞猜不能删除")
    # 所有已押注的用户按原路退款
    bets = list(db.execute(select(GuessBet).where(GuessBet.guess_id == guess_id)).scalars())
    for b in bets:
        if b.skipped or b.amount <= 0:
            continue
        u = db.get(User, b.user_id)
        if not u:
            continue
        coin_service.grant_coins(
            db, u, b.amount, "guess_refund",
            ref_id=f"g{guess_id}:b{b.id}",
            description=f"竞猜删除退款：{guess.title}",
        )
        b.result = "cancel"
        b.settled_at = datetime.now()
        b.reward = 0
    db.delete(guess)
    db.flush()


def settle_guess(db: Session, guess_id: int, winning_option_id: int, admin_id: int) -> Guess:
    guess = db.get(Guess, guess_id)
    if not guess:
        raise HTTPException(status_code=404, detail="竞猜不存在")
    if guess.settled_at is not None:
        raise HTTPException(status_code=400, detail="该竞猜已结算")
    opt = db.get(GuessOption, winning_option_id)
    if not opt or opt.guess_id != guess_id:
        raise HTTPException(status_code=400, detail="中奖选项不合法")

    options = _get_options(db, guess.id)
    total_pool = sum(int(o.total_points or 0) for o in options)
    winner_pool = int(opt.total_points or 0)
    winning_option_id = opt.id
    now = datetime.now()

    bets = list(db.execute(select(GuessBet).where(GuessBet.guess_id == guess_id)).scalars())
    for b in bets:
        if b.skipped or b.amount <= 0:
            b.result = "refund"
            b.settled_at = now
            continue
        u = db.get(User, b.user_id)
        if not u:
            continue
        if b.option_id == winning_option_id:
            # 按胜方池子占比分红：净奖励 = 总池 * (该用户押注/胜方池) - 该用户押注
            # 胜方池为 0 时退本金
            if winner_pool <= 0:
                reward_net = 0
                coin_service.grant_coins(db, u, b.amount, "guess_win_refund", ref_id=f"g{guess_id}:b{b.id}", description="胜方池为空，退本金")
            else:
                share = (total_pool * b.amount) // winner_pool
                reward_net = share - b.amount
                coin_service.grant_coins(
                    db, u, share, "guess_win",
                    ref_id=f"g{guess_id}:b{b.id}",
                    description=f"竞猜赢取：{guess.title} · {opt.label}",
                )
            b.result = "win"
            b.reward = reward_net
        else:
            b.result = "lose"
            b.reward = -b.amount
        b.settled_at = now

    guess.winning_option_id = winning_option_id
    guess.settled_at = now
    guess.settled_by = admin_id
    db.flush()
    return guess
