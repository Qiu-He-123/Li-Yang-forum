# -*- coding: utf-8 -*-
"""从现有 SQLite 导出宠物商城数据（pet_categories + pet_products），
生成 Alembic 迁移 0062_seed_pet_shop_data.py，供克隆后直接运营。"""
import json
import re
import sqlite3
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DB = BACKEND / "ly_community.sqlite3"
OUT = BACKEND / "alembic" / "versions" / "0062_seed_pet_shop_data.py"

con = sqlite3.connect(str(DB))
con.row_factory = sqlite3.Row
c = con.cursor()

cats = [dict(r) for r in c.execute("SELECT * FROM pet_categories ORDER BY id")]
prods = [dict(r) for r in c.execute("SELECT * FROM pet_products ORDER BY id")]
con.close()

PRODUCT_COLS = [
    "id", "name", "category_id", "price", "original_price", "stock", "image_url",
    "model_3d_url", "description", "sales", "status", "anim_json", "kind",
    "affinity_gain", "ai_enabled", "ai_persona", "ai_wake_enabled", "game_speech",
    "can_fly", "attrs",
]
CAT_COLS = ["id", "name", "icon", "sort_order", "created_at", "updated_at"]


def sql_str(v):
    if v is None:
        return "None"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v)
    s = s.replace("'", "''")
    return "'" + s + "'"


def qmark_rows(rows, cols):
    return ",\n        ".join(
        "(" + ", ".join(sql_str(r.get(col)) for col in cols) + ")"
        for r in rows
    )


header = '''"""0062 导入宠物商城运营数据

把当前线上库的宠物商城数据（pet_categories + pet_products，含 AI 配置/动作帧/道具属性）固化进迁移，
克隆仓库并 `alembic upgrade head` 后即可直接运营宠物商城（无需手工录入）。
按 (name) 幂等写入；已存在的行跳过，不覆盖用户之后修改的数据。
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


_PRODUCT_COLS = [
    __PRODUCT_COLS__
]


_CATS = [
__CATS__
]

_PRODS = [
__PRODS__
]


def _seed(bind) -> None:
    """幂等写入类别与商品。"""
    cat_existing = {r[0] for r in bind.execute(sa.text("SELECT name FROM pet_categories"))}
    for name, icon, sort_order in _CATS:
        if name in cat_existing:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO pet_categories (name, icon, sort_order, created_at, updated_at)"
                " VALUES (:name, :icon, :sort, datetime('now'), datetime('now'))"
            ),
            {"name": name, "icon": icon, "sort": sort_order},
        )
    prod_existing = {r[0] for r in bind.execute(sa.text("SELECT name FROM pet_products"))}
    names = ", ".join(_PRODUCT_COLS)
    markers = ", ".join(f":p{i}" for i in range(len(_PRODUCT_COLS)))
    for row in _PRODS:
        name = row[1]
        if name in prod_existing:
            continue
        params = {f"p{i}": row[i] for i in range(len(_PRODUCT_COLS))}
        bind.execute(
            sa.text(f"INSERT INTO pet_products ({names}) VALUES ({markers})"),
            params,
        )


def upgrade() -> None:
    bind = op.get_bind()
    _seed(bind)


def downgrade() -> None:
    # 不删除已有数据（可能是用户运营后新增/可售商品）
    pass
'''


def build_header(cats_block: str, prods_block: str) -> str:
    return (
        header.replace("__PRODUCT_COLS__", ", ".join(repr(c) for c in PRODUCT_COLS))
        .replace("__CATS__", cats_block)
        .replace("__PRODS__", prods_block)
    )


cats_block = qmark_rows([{"name": r["name"], "icon": r["icon"], "sort_order": r["sort_order"]} for r in cats], ["name", "icon", "sort_order"])
prods_block = qmark_rows(prods, PRODUCT_COLS)

OUT.write_text(build_header(cats_block, prods_block), encoding="utf-8")
print(f"WROTE {OUT}  cats={len(cats)} prods={len(prods)}")