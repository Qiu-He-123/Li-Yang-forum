# 抖音作者视频库拉取工具

输入作者**抖音号或昵称**，自动拉取该作者**整个视频库**的作品链接（作品页链接 +
无水印直链），并输出 TXT / CSV / JSON；也可以一键批量下载视频和图集。

## 功能

- 按 **抖音号**（如 `33042733234`）或**昵称**（如 `人民日报`）模糊搜索作者，列出候选作者（粉丝数、获赞数、认证信息）供选择
- 支持粘贴**主页链接 / 分享口令**（`v.douyin.com` 短链自动解析）
- 打开作者主页自动滚动加载，抓取全部作品（视频 + 图集）
- 输出文件（保存到 `output/作者昵称/`）：
  - `视频链接.txt`：作品页链接，每行一个
  - `直链列表.txt`：无水印视频/图片直链
  - `视频信息.csv` / `视频信息.json`：标题、发布时间、播放/点赞/评论等完整信息
- 可选批量下载（mp4 / 图集图片，断点续传、失败重试）
- 批量模式：`authors.txt` 每行一个作者，一次跑完
- 快速 API 模式：有登录态后可直接输入 sec_uid，用 `a_bogus` 签名直连接口分页拉取
- 纯 HTTP 模式：复制自己浏览器里的 Cookie 即可，全程不弹浏览器窗口

## 安装

```bat
:: 进入本工具目录（双击运行或从仓库任意位置进入）
cd /d "%~dp0"
pip install -r requirements.txt
```

本机需安装 **Microsoft Edge**（或 Chrome）。`playwright` 会自动驱动 Edge，
无需额外下载浏览器。

## 使用

### 交互模式

```bat
python douyin_tool.py
```

选择菜单即可。**第一次运行会弹出浏览器窗口，需要扫码登录一次抖音**
（之后登录态保存在 `cookies.json`，自动复用；过期时窗口会再次弹出）。

### 命令行模式

```bat
REM 按抖音号搜索并拉取
python douyin_tool.py 33042733234

REM 按昵称搜索
python douyin_tool.py 人民日报

REM 主页链接 / 分享口令
python douyin_tool.py --url "https://v.douyin.com/xxxx/"

REM 批量（authors.txt 每行一个）
python douyin_tool.py --file authors.txt

REM 拉取后同时下载视频
python douyin_tool.py 33042733234 --download

REM 快速 API 模式（需先登录过一次）
python douyin_tool.py --api MS4wLjABAAAAxxxxxxxx

REM 主页链接 / 分享口令（纯 HTTP 解析 sec_uid，无需浏览器）
python douyin_tool.py --api "https://www.douyin.com/user/MS4wLjABAAAAxxxxxxxx"

REM 粘贴自己浏览器里的 Cookie（之后 API 模式不再需要打开浏览器）
python douyin_tool.py --set-cookie "sessionid=xxx; ttwid=xxx; ..."
```

### 不用浏览器的工作流（纯 HTTP）

1. 在手机/电脑浏览器登录抖音，按 F12 在 Network/Application 里复制 Cookie 字符串
2. 粘贴一次：`python douyin_tool.py --set-cookie "k=v; k2=v2; ..."`
3. 之后随时用：`python douyin_tool.py --api "作者主页链接或分享口令"`

工具会纯 HTTP 跟随跳转解析出 sec_uid，再用 `a_bogus` 签名分页拉取全部作品。
注意：**“抖音号/昵称 → sec_uid”这一步被抖音风控限制，纯 HTTP 无法完成**，
只有两条路：粘贴主页/分享链接，或先用浏览器模式搜一次。

## 实现原理

抖音 Web 端作者主页通过 `aweme/v1/web/aweme/post/` 接口分页返回作品列表。
该接口带 `a_bogus` 签名 + `msToken` + 登录态，纯 HTTP 直连容易被风控拦截
（返回 `verify_check` 或空响应），因此默认采用**真实浏览器引擎**：

1. Playwright 驱动 Edge，携带已保存的登录 Cookie 打开搜索页
   （`aweme/v1/web/discover/search/` 按抖音号/昵称精确匹配）
2. 打开作者主页，自动滚动，从网络响应中直接截获 `aweme/post` 分页数据
3. 去重后解析每个作品的直链：视频取 `video.play_addr` 的 mp4 地址，
   图集取 `images` 图片地址

快速 API 模式为备选引擎：`abogus.py` 是纯 Python 实现的 `a_bogus` 签名
（源自 [JoeanAmier/TikTokDownloader](https://github.com/JoeanAmier/TikTokDownloader)
与 [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)
的开源实现，GPL-3.0，已保留版权头）。

## 注意事项

- 请仅用于**学习研究 / 个人存档**，遵守抖音用户协议，控制请求频率（程序已内置翻页间隔）
- `cookies.json` 是你的登录凭证，请勿提交到 Git 或泄露给他人
- 大号（如数万作品）滚动抓取耗时较长，建议用 `--api` 模式或分批处理
