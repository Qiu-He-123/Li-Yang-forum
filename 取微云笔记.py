# -*- coding: utf-8 -*-
"""取微云笔记：从微云分享链接中提取笔记正文。

原理：微云分享页会把笔记数据以内嵌 JSON（window.syncData）的形式
直接放在 HTML 里，无需登录即可拿到笔记的 html_content 正文。
"""

import html
import json
import re
import sys
import urllib.request

DEFAULT_URL = "https://share.weiyun.com/SpmKBnmC"
EXPECTED = "公告{停机公告}"


def fetch_note(url: str) -> str:
    """请求分享链接，解析 syncData，返回笔记正文（纯文本）。"""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            ),
            "Referer": "https://share.weiyun.com/",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        page = resp.read().decode("utf-8", errors="replace")

    m = re.search(r"window\.syncData\s*=\s*(\{.*?\});\s*</script>", page, re.S)
    if not m:
        raise RuntimeError("页面中没有找到 syncData 数据（链接可能失效或需要密码）")

    data = json.loads(m.group(1))
    share = data.get("shareInfo", {})
    note_list = share.get("note_list") or []
    if note_list:
        content = (
            note_list[0].get("html_content")
            or note_list[0].get("note_title")
            or share.get("share_name")
            or ""
        )
    else:
        content = share.get("share_name") or ""

    text = re.sub(r"<[^>]+>", "", content)
    return html.unescape(text).strip()


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    try:
        text = fetch_note(url)
    except Exception as e:
        print(f"取内容失败: {e}")
        sys.exit(1)

    print(f"取到的内容: {text}")
    if text == EXPECTED or EXPECTED in text:
        print("成功")
    else:
        print("内容不匹配，未成功")


if __name__ == "__main__":
    main()
