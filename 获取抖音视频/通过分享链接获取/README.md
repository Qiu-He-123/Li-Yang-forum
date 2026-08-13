# 抖音分享链接 -> 无水印直链

粘贴抖音分享口令 / 短链（`v.douyin.com`）/ 完整链接，直接解析出该视频的
**无水印 mp4 直链**，并保存标题、作者、点赞评论等元数据。

## 使用

```bat
REM 命令行直接给链接或整段分享口令
python douyin_share.py "6.92 复制打开抖音... https://v.douyin.com/86q7AqlVBjs/ ..."

REM 解析并同时下载
python douyin_share.py "https://v.douyin.com/86q7AqlVBjs/" --download

REM 不带任何参数，进入粘贴模式
python douyin_share.py
```

结果保存到 `output/作品ID_标题/`：`直链.txt` + `视频信息.json`，下载则多一个 `下载/` 目录。

## 解析路径（自动降级）

1. **Web 详情 API**（推荐）：用登录态 Cookie + `a_bogus` 签名请求
   `aweme/v1/web/aweme/detail/`，得到最高质量无水印直链（douyinvod）。
   Cookie 会自动读取 `通过主页获取/cookies.json` 或本目录 `cookies.json`。
2. **移动端分享页**（无需 Cookie）：解析 `iesdouyin.com/share/video/<id>`
   页面内嵌数据，把 `playwm`（带水印）地址换成 `play` 得到无水印直链。
3. **浏览器兜底**：Playwright 打开视频页，截获详情接口响应。

## 实现原理

1. 分享短链跟随跳转（纯 HTTP），得到真实地址 `douyin.com/video/<aweme_id>`
2. 用 `aweme_id` 请求详情接口 / 移动端分享页
3. 从 `video.play_addr.url_list` 提取 mp4 直链（图集则提取 `images` 图片）

`abogus.py` 为纯 Python 的 `a_bogus` 签名实现（源自
[JoeanAmier/TikTokDownloader](https://github.com/JoeanAmier/TikTokDownloader) 与
[Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)，
GPL-3.0，已保留版权头）。

## 注意事项

- 仅供学习研究，请遵守抖音用户协议
- `--no-cookie` 可强制只走移动端分享页（解析出的直链清晰度可能低于登录态路径）
- 直链带有效期，建议拿到后尽快下载
