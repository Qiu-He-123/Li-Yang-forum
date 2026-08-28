"""搜索业务逻辑层。

- 用户搜索时写入 search_histories，并更新 hot_searches 计数
- 热搜榜取前 10，仅展示真实搜索数据
- 历史记录最近 20 条，按 keyword 去重
"""
from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app.core.time_utils import to_iso_zh
from app.models import HotSearch, SearchHistory, User


def record_search(db: Session, user: User, keyword: str) -> None:
    """记录用户搜索：写入历史 + 更新热搜计数（不 commit，由调用方提交）。

    Args:
        db: Session
        user: 当前用户
        keyword: 搜索关键词（已去空白）
    """
    keyword = (keyword or "").strip()
    if not keyword:
        return

    # 写搜索历史
    db.add(SearchHistory(user_id=user.id, keyword=keyword[:100]))

    # 更新热搜计数（upsert）
    hot = db.scalar(select(HotSearch).where(HotSearch.keyword == keyword[:100]))
    if hot:
        hot.count = (hot.count or 0) + 1
    else:
        db.add(HotSearch(keyword=keyword[:100], count=1))


def list_search_history(user: User, db: Session, limit: int = 20) -> list[dict]:
    """查询当前用户搜索历史（最近 limit 条，按 keyword 去重）。

    思路：先按时间倒序取出最近 limit*5 条，再在内存里按 keyword 去重，保留 limit 条。
    SQLite 不支持 DISTINCT ON，用 Python 去重简单可靠。
    """
    rows = db.scalars(
        select(SearchHistory)
        .where(SearchHistory.user_id == user.id)
        .order_by(SearchHistory.created_at.desc())
        .limit(limit * 5)
    ).all()

    seen: set[str] = set()
    result: list[dict] = []
    for row in rows:
        if row.keyword in seen:
            continue
        seen.add(row.keyword)
        result.append(
            {
                "id": row.id,
                "keyword": row.keyword,
                "created_at": to_iso_zh(row.created_at),
            }
        )
        if len(result) >= limit:
            break
    return result


def clear_search_history(user: User, db: Session) -> int:
    """清空当前用户搜索历史，返回删除条数。"""
    result = db.execute(
        delete(SearchHistory).where(SearchHistory.user_id == user.id)
    )
    db.commit()
    return int(result.rowcount or 0)


def delete_search_history_by_keyword(user: User, keyword: str, db: Session) -> int:
    """删除当前用户指定 keyword 的所有搜索历史，返回删除条数。"""
    if not keyword:
        return 0
    result = db.execute(
        delete(SearchHistory).where(
            SearchHistory.user_id == user.id, SearchHistory.keyword == keyword
        )
    )
    db.commit()
    return int(result.rowcount or 0)


def list_hot_searches(db: Session, limit: int = 10) -> list[dict]:
    """查询热搜榜（前 limit 条，按 count 降序）。

    仅返回真实搜索数据，不使用预设词兜底。
    """
    rows = db.scalars(
        select(HotSearch).order_by(desc(HotSearch.count), HotSearch.id).limit(limit)
    ).all()
    return [
        {
            "id": r.id,
            "keyword": r.keyword,
            "count": r.count,
        }
        for r in rows
    ]
