"""微信朋友圈守护客户端（不再"投递"数据）。

后端现在直读本机微信数据库（sns.db / contact.db / message），客户端只负责：
1. 定时模拟点击朋友圈窗口，让微信把最新动态拉到本地缓存（sns.db）；
2. 检查微信登录/密钥是否正常，异常时在日志里提示。

启动前请先运行 启动检查.py 完成解密自检。
"""

import datetime
import importlib.util
import os
import time
from pathlib import Path

import client_common
import sns_reader


_last_window_warning = 0.0


def log(msg: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(Path(__file__).parent / "client.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_config() -> dict:
    return client_common.load_effective_config()


def _load_click_moments():
    click_path = Path(__file__).resolve().parent.parent / "方便bat" / "click_moments.py"
    spec = importlib.util.spec_from_file_location("click_moments", click_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def refresh_cache(cfg: dict, sns_src: str) -> bool:
    """点击朋友圈窗口触发微信拉取最新动态，更新本地 sns.db 缓存。"""
    try:
        click_moments = _load_click_moments()
        return click_moments.refresh_moments_cache(
            sns_src=sns_src,
            click_pos=(
                int(cfg.get("refresh_click_x", 96)),
                int(cfg.get("refresh_click_y", 19)),
            ),
            wait_seconds=float(cfg.get("refresh_wait_seconds", 0.8)),
            quiet=True,
        )
    except Exception as exc:
        log(f"朋友圈刷新失败（不影响后续读取）: {exc}")
        return False


def main() -> None:
    cfg = load_config()
    scan_interval = max(3, int(cfg.get("scan_interval_seconds", 8)))
    # 节流：抢焦点点朋友圈很打扰人，只在"数据确实旧了"且"距上次点击够久"时才点
    min_click_interval = max(5, int(cfg.get("refresh_min_interval_seconds", 8)))
    stale_after = max(0, int(cfg.get("refresh_stale_after_seconds", 30)))
    log("守护客户端启动（后端直读模式，客户端仅刷新本地缓存）")
    global _last_window_warning
    last_click = 0.0

    while True:
        try:
            key_file = cfg.get("key_file") or ""
            key_hex = ""
            if key_file and os.path.isfile(key_file):
                key_hex = Path(key_file).read_text(encoding="utf-8").strip()
            _, _account_dir, sns_src = (
                sns_reader.find_sns_db(cfg.get("datadir"), key_hex) if key_hex else (None, None, None)
            )
            if sns_src:
                now = time.time()
                # sns.db 在 stale_after 秒内有更新 => 微信自己已在拉取，完全不用抢焦点
                fresh = False
                try:
                    fresh = (now - os.path.getmtime(sns_src)) < stale_after
                except OSError:
                    pass
                need_click = (not fresh) and (now - last_click >= min_click_interval)
                if need_click:
                    ok = refresh_cache(cfg, sns_src)
                    if ok:
                        last_click = now
                    elif time.time() - _last_window_warning >= 60:
                        _last_window_warning = time.time()
                        log("朋友圈窗口未打开，跳过本次刷新（后端仍会读取现有缓存）")
                # else: 数据新鲜或未到点击间隔 -> 静默跳过，不打断用户
            else:
                log("未找到可解密的 sns.db：请确认微信已登录、已完成解密门禁")
                time.sleep(10)
        except KeyboardInterrupt:
            log("已停止")
            break
        except Exception as exc:
            log(f"循环异常: {exc}")
        time.sleep(scan_interval)


if __name__ == "__main__":
    main()
