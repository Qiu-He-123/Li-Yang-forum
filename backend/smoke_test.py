"""生产环境烟囱测试脚本（OpenAPI 自驱动）。

用法（后端已在 localhost:8000 运行）：
    python smoke_test.py
 或指定地址：
    python smoke_test.py http://127.0.0.1:8000

它从 /openapi.json 读取真实路由，校验"关键端点是否存在/是否可访问"，
避免硬编码错误路径。既可验证服务已正常启动，也可做上线前的快速探活。
"""
import sys
import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

# 关键端点（存在性校验，路由不漏）：
# 前缀即可，脚本会在 openapi 中模糊匹配（不区分 method/大小写）
CRITICAL_PATHS = [
    "/api/posts",
    "/api/circles",
    "/api/coins/",        # 金币
    "/api/guess/",        # 今日竞猜
    "/pet-shop/",         # 宠物商城
    "/pet-shop/my-pets",  # 我的宠物（含已养/上限）
    "/pet-shop/products/",# 宠物/道具/领养位
    "/pet-ai/",           # 宠物 AI
    "/api/games",
    "/api/gatherings/",
    "/api/messages/",
    "/api/notifications",
    "/api/admin/",
    "/api/settings",
    "/api/announcements",
    "/api/badges",
    "/api/users/",
]

def main():
    ok = True
    try:
        spec = httpx.get(f"{BASE}/openapi.json", timeout=15).json()
    except Exception as e:
        print(f"✗ 无法获取 {BASE}/openapi.json：{e}")
        return 1

    paths = list(spec.get("paths", {}).keys())
    print(f"已发现 {len(paths)} 个路由")

    for c in CRITICAL_PATHS:
        hit = next((p for p in paths if c in p), None)
        if hit:
            print(f"  ✓ {c}  ->  {hit}")
        else:
            print(f"  ✗ 缺少 {c}")
            ok = False

    # 对少数公开 GET 做真实请求探活
    print("\n-- 公开 GET 探活 --")
    for p in ["/pet-shop/categories", "/pet-shop/products?page=1&page_size=1", "/docs"]:
        try:
            r = httpx.get(f"{BASE}{p}", timeout=15)
            print(f"  {'✓' if r.status_code < 500 else '✗'} {p} -> {r.status_code}")
            if r.status_code >= 500:
                ok = False
        except Exception:
            print(f"  ✗ {p} -> 请求失败")
            ok = False

    print("\n" + ("✅ 通过" if ok else "❌ 存在缺失"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())