"""预检：估算每个宠物 ZIP 按 admin_import_pet_zip 逻辑压缩后的总大小，判断是否超 20MB 上限。"""
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.pet_shop_service import (
    _compress_frame_bytes,
    _collect_frames,
    _MAX_ACTIONS,
    _parse_dyber_actions,
    MAX_PET_ZIP_COMPRESSED_BYTES,
)

ZIPS = [
    r"F:\BaiduNetdiskDownload\椿.zip",
    r"F:\BaiduNetdiskDownload\流浪者(1).zip",
    r"F:\BaiduNetdiskDownload\流萤.zip",
    r"F:\BaiduNetdiskDownload\纳西妲.zip",
    r"F:\BaiduNetdiskDownload\露西亚·深红囚影.zip",
    r"F:\BaiduNetdiskDownload\像素猫meme.zip",
    r"F:\BaiduNetdiskDownload\守岸人.zip",
    r"F:\BaiduNetdiskDownload\像素猫meme_扩充版.zip",
    r"F:\BaiduNetdiskDownload\像素四妹.zip",
    r"F:\BaiduNetdiskDownload\魈.zip",
]


def check(zip_path: str) -> dict:
    name = Path(zip_path).stem
    try:
        with zipfile.ZipFile(zip_path) as zf:
            # 直接读取内部文件
            names = [n for n in zf.namelist() if "__MACOSX" not in n]
            conf_name = next((n for n in names if n.endswith("act_conf.json")), None)
            if not conf_name:
                return {"name": name, "ok": False, "reason": "无 act_conf.json"}
            conf_dir = conf_name.rsplit("/", 1)[0] if "/" in conf_name else ""
            # 收集 png 帧列表（含路径）
            conf = json.loads(zf.read(conf_name).decode("utf-8"))
            frame_files = {n: zf.read(n) for n in names if n.endswith(".png")}
    except Exception as e:  # noqa: BLE001
        return {"name": name, "ok": False, "reason": f"读取失败: {e}"}

    # 逐动作压缩统计
    total = 0
    written = 0
    first = None
    act_keys = []
    acts = _parse_dyber_actions.__wrapped__ if hasattr(_parse_dyber_actions, "__wrapped__") else None
    # 简化：直接复用 parse 收集前缀，再手动读帧
    act_list = []
    for conf_key, cfg in (conf.items() if isinstance(conf, dict) else []):
        if not isinstance(cfg, dict):
            continue
        act_keys_local = {
            "stand": ("stand", "站立"),
            "sleep": ("sleep", "睡觉"),
            "interact": ("interact", "互动"),
            "walk": ("walk", "行走"),
            "fly": ("fly", "飞行"),
        }
        act_key, label = act_keys_local.get(conf_key, ("interact", conf_key))
        prefix = str(cfg.get("images") or conf_key)
        # 收集该前缀帧
        base = conf_dir + "/" if conf_dir else ""
        frames = sorted(
            [
                n
                for n in frame_files
                if Path(n).name.startswith(prefix + "_") and Path(n).name.endswith(".png")
            ],
            key=lambda n: int(Path(n).name.rsplit("_", 1)[1][:-4]),
        )
        if not frames:
            continue
        act_list.append((act_key, label, prefix, frames))

    # 按优先级排序，仅取前 _MAX_ACTIONS
    pri = {"stand": 1, "sleep": 2, "interact": 3, "walk": 4, "fly": 5}
    act_list.sort(key=lambda a: pri.get(a[0], 9))
    act_list = act_list[:_MAX_ACTIONS]

    for act_key, label, prefix, frames in act_list:
        for n in frames:
            comp = _compress_frame_bytes(frame_files[n])
            if comp is None:
                continue
            total += len(comp)
            written += 1
            if first is None:
                first = n

    over = total > MAX_PET_ZIP_COMPRESSED_BYTES
    return {
        "name": name,
        "ok": not over and written > 0,
        "reason": "ok" if (not over and written > 0) else ("超20MB" if over else "无可用帧"),
        "compressed_mb": round(total / 1024 / 1024, 2),
        "limit_mb": 20,
        "actions": [a[0] for a in act_list],
        "frames": written,
    }


if __name__ == "__main__":
    for z in ZIPS:
        if not Path(z).exists():
            print(f"[缺失] {z}")
            continue
        r = check(z)
        print(f"[{r['ok']}] {r['name']}: 压缩后 {r.get('compressed_mb')}MB / 上限 {r.get('limit_mb')}MB | {r.get('reason')} | 动作={r.get('actions')} 帧={r.get('frames')}")