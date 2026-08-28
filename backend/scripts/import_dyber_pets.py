"""DyberPet 宠物资源导入脚本。

把 D:\\Users\\Downloads\\宠物\\DyperPet\\res 下的宠物帧动画：
1. 复制帧图到 backend/uploads/pets/{slug}/
2. 生成 anim_json（动作 → 帧列表 + 播放间隔）写入 PetProduct.anim_json
3. 上架 9 只宠物商品（分类「萌宠领养」，金币计价，每人限领 1 只）

可重复运行（幂等）：同名商品只更新 anim_json/图片，不重复插入。

用法：cd backend && python scripts/import_dyber_pets.py
"""

import json
import re
import shutil
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models import PetCategory, PetProduct  # noqa: E402

DYBER_RES = Path(r"D:\Users\Downloads\宠物\DyperPet\res")
UPLOADS_PETS = BACKEND_DIR / "uploads" / "pets"

CATEGORY_NAME = "萌宠领养"
CATEGORY_ICON = "🐾"

# 宠物定义：(slug, 源目录, 展示名, 金币价, 原价, 描述, 动作列表)
# 动作: (key, label, 帧文件前缀, 帧间隔ms)
PETS = [
    (
        "paimon", "pet/派蒙", "派蒙", 888, 1288,
        "原神天下第一·应急食品参上！会陪你唠嗑的最好伙伴，就是有点话痨（和有点好吃）。"
        "领养后她会在你的页面里蹦跶个不停。",
        [("stand", "待机", "pm", 80)],
    ),
    (
        "lightfury", "pet/LF", "光煞", 666, 966,
        "来自隐秘之境的纯白光煞，性格高冷但内心柔软。领养后会在你页面里优雅地悬浮呼吸，"
        "静静陪你度过每个深夜。",
        [("stand", "悬浮", "LF", 500)],
    ),
    (
        "toothless", "role/Toothless", "无牙仔", 588, 888,
        "博克岛最强夜煞，缺一颗牙的傻狗龙。别看它长得凶，其实最爱撒娇和打盹，"
        "生气的时候腮帮子会鼓起来。",
        [
            ("stand", "站立", "stand", 400),
            ("walk", "散步", "rightwalk", 200),
            ("sleep", "打盹", "sleep", 500),
            ("interact", "生气", "angry", 400),
        ],
    ),
    (
        "kitty", "role/Kitty", "凯蒂猫", 159, 239,
        "戴蝴蝶结的经典小猫，会走路会睡觉，生气的时候也很可爱。全宇宙最温柔的陪伴系小伙伴。",
        [
            ("stand", "站立", "stand", 400),
            ("walk", "散步", "rightwalk", 200),
            ("sleep", "打盹", "sleep", 500),
            ("interact", "生气", "angry", 400),
        ],
    ),
    (
        "chriskitty", "role/ChrisKitty", "克里斯猫", 128, 188,
        "圆滚滚的克里斯猫，特长是趴地撒泼。走两步就累，是最适合陪伴式躺平的宠物。",
        [
            ("stand", "站立", "stand", 400),
            ("interact", "趴趴", "onfloor", 100),
        ],
    ),
    (
        "sancat", "role/散猫猫", "散猫猫", 388, 588,
        "一只很忙的小猫，走路带风。摸摸头会害羞，是群聊里最活跃的显眼包。",
        [
            ("stand", "待机", "m", 300),
            ("walk", "散步", "w1", 50),
            ("interact", "摸摸", "c", 40),
        ],
    ),
    (
        "pikechuu", "role/皮克啾", "皮克啾", 99, 139,
        "电力满格的黄色小家伙，蹦蹦跳跳停不下来。养它不需要充电线，好心情就是它的电源。",
        [("stand", "蹦跳", "pikechuu", 200)],
    ),
    (
        "xunshou", "role/蕈兽", "蕈兽", 199, 299,
        "提瓦特大陆的草之精粹，摸起来软乎乎。会慢悠悠散步，被摸摸的时候最开心。",
        [
            ("stand", "待机", "stand", 200),
            ("walk", "散步", "walk2", 60),
            ("interact", "摸摸", "touch", 80),
        ],
    ),
    (
        "xiaoniao", "role/魈鸟", "魈鸟", 299, 399,
        "三眼五显仙人同款小鸟，平时安静站立，放飞自我时全场扑腾。护法夜叉的心头好。",
        [
            ("stand", "待机", "stand", 200),
            ("walk", "飞行", "fly2", 60),
            ("interact", "扑腾", "cc", 80),
        ],
    ),
]


def collect_frames(action_dir: Path, prefix: str) -> list[str]:
    """按前缀收集帧文件（自然数字排序）。"""
    frames = [
        f for f in action_dir.iterdir()
        if f.is_file() and f.name.startswith(prefix + "_") and f.suffix.lower() == ".png"
    ]
    frames.sort(key=lambda f: int(re.search(r"_(\d+)\.png$", f.name).group(1)))
    return frames


def main() -> None:
    if not DYBER_RES.exists():
        print(f"[ERROR] 源目录不存在: {DYBER_RES}")
        sys.exit(1)

    db = SessionLocal()
    try:
        # 1. 分类
        cat = db.scalar(select(PetCategory).where(PetCategory.name == CATEGORY_NAME))
        if not cat:
            max_order = db.scalar(select(PetCategory.sort_order).order_by(PetCategory.sort_order.desc())) or 0
            cat = PetCategory(name=CATEGORY_NAME, icon=CATEGORY_ICON, sort_order=max_order + 1)
            db.add(cat)
            db.flush()
            print(f"[OK] 创建分类: {CATEGORY_NAME} (id={cat.id})")
        else:
            print(f"[SKIP] 分类已存在: {CATEGORY_NAME} (id={cat.id})")

        for slug, src_rel, name, price, original_price, desc, actions in PETS:
            src_dir = DYBER_RES / src_rel / "action"
            if not src_dir.exists():
                print(f"[WARN] {name}: 源目录缺失 {src_dir}，跳过")
                continue

            # 2. 复制帧图
            dst_dir = UPLOADS_PETS / slug
            dst_dir.mkdir(parents=True, exist_ok=True)
            copied = 0
            for f in src_dir.iterdir():
                if f.is_file() and f.suffix.lower() == ".png":
                    shutil.copy2(f, dst_dir / f.name)
                    copied += 1

            # 3. 生成 anim_json
            anim_actions = []
            first_frame_url = None
            for key, label, prefix, interval in actions:
                frames = collect_frames(src_dir, prefix)
                if not frames:
                    print(f"[WARN] {name}: 动作 {key}({prefix}) 无帧文件，跳过该动作")
                    continue
                urls = [f"/uploads/pets/{slug}/{f.name}" for f in frames]
                if first_frame_url is None:
                    first_frame_url = urls[0]
                anim_actions.append({"key": key, "label": label, "frames": urls, "interval": interval})

            if not anim_actions:
                print(f"[ERROR] {name}: 无可用动作，跳过上架")
                continue

            anim_json = json.dumps({"slug": slug, "actions": anim_actions}, ensure_ascii=False)

            # 4. 商品（幂等：同名更新，否则插入）
            product = db.scalar(select(PetProduct).where(PetProduct.name == name))
            if product:
                product.anim_json = anim_json
                product.image_url = first_frame_url
                db.add(product)
                print(f"[UPDATE] {name}: anim_json 已更新（{len(anim_actions)} 动作 / {copied} 帧）")
            else:
                product = PetProduct(
                    name=name,
                    category_id=cat.id,
                    price=float(price),
                    original_price=float(original_price),
                    stock=999,
                    image_url=first_frame_url,
                    anim_json=anim_json,
                    description=desc,
                    sales=0,
                    status=1,
                )
                db.add(product)
                print(f"[OK] 上架 {name}: {price} 金币（{len(anim_actions)} 动作 / {copied} 帧）")

        db.commit()
        total = len(db.scalars(select(PetProduct)).all())
        print(f"\n[DONE] 当前宠物商品总数: {total}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
