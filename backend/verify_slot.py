"""宠物领养位核心逻辑实测（临时数据，跑完自动清理）。
验证：2 只上限 → 第 3 只被拒 → 购买领养位 → 可养第 3 只。
"""
import sys, uuid
sys.path.insert(0, '.')
from app.core.database import SessionLocal
from app.models import User
from app.services import pet_shop_service, coin_service
from fastapi import HTTPException
from sqlalchemy import text


def _third_id(db, ids):
    return db.execute(
        text("select id from pet_products where kind=1 and status=1 and id not in (:a,:b) limit 1"),
        {"a": ids[0], "b": ids[1]}).scalar()


pw = uuid.uuid4().hex[:10]
with SessionLocal.begin() as db:
    u = User(username=f"__slot_test_{pw}", nickname="slot测试")
    db.add(u)
    db.flush()
    uid = u.id
    pet_ids = [r[0] for r in db.execute(text(
        "select id from pet_products where kind=1 and status=1 and stock>5 order by price limit 2")).fetchall()]
    slot_id = db.execute(text("select id from pet_products where name='宠物领养位'")).scalar()
    coin_service.grant_coins(db, u, 5000, "pet_slot_test", "测试资金")
    db.commit()

win = {}
try:
    pet_shop_service.adopt_product(db, u, pet_ids[0]); win["PET1"] = True
    pet_shop_service.adopt_product(db, u, pet_ids[1]); win["PET2"] = True
    try:
        pet_shop_service.adopt_product(db, u, _third_id(db, pet_ids))
        win["PET3_BLOCKED"] = False
        print("✗ 第3只竟然领养成功！")
    except HTTPException:
        win["PET3_BLOCKED"] = True
        print("✓ 第3只被上限拦截")
    r = pet_shop_service.purchase_pet_slot(db, u, slot_id); win["SLOT_OK"] = True
    print("✓ 购买领养位后 limit =", r["max_owned"], "extra =", r["pet_extra_slots"])
    pet_shop_service.adopt_product(db, u, _third_id(db, pet_ids)); win["PET3_OK"] = True
    print("✓ 领养位后第3只领养成功")
except Exception as e:
    print("✗ 异常：", e); win["ERR"] = True
finally:
    S = SessionLocal()
    try:
        S.execute(text("delete from user_pets where user_id=:u"), {"u": uid})
        S.execute(text("delete from coin_transactions where user_id=:u"), {"u": uid})
        S.execute(text("delete from users where id=:u"), {"u": uid})
        S.commit()
    except Exception:
        S.rollback()
    finally:
        S.close()
    print("已清理临时数据")

print("结果：", win)