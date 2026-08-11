# 立洋社区 iOS 版（与安卓同款套壳）

功能与安卓版一致：

- WKWebView 打开同一个网页（`Config.swift` 里的 `appUrl`）
- 自定义 UA 标记 `LYCommunityApp/1.0`：网页端自动隐藏「下载手机端」按钮，后台统计手机端进入
- 浅色渐变启动页「立洋社区」，加载完成淡出
- 服务器连不上/5xx 时显示维护面板：自动拉取微云笔记公告、联系管理员复制 QQ、重新连接、退出
- 左边缘右滑 = 返回上一页；Cookie 自动持久化，重开保持登录
- 网页传图走系统相册（PHPicker）

## 重要前提

iOS 应用**只能在 macOS 上用 Xcode 编译签名**，Windows 上做不出可安装的 ipa。
这套工程源码已经备好，到 Mac 上即可构建：

```bash
brew install xcodegen
cd ios
xcodegen generate --spec project.yml
open LiyangCommunity.xcodeproj
```

真机安装还需要 Apple 开发者账号：

- 免费 Apple ID：可以装，但 7 天过期，需要每 7 天重新签名
- 付费开发者账号（$99/年）：可长期安装、上架 App Store

## GitHub Actions 自动构建

仓库已带 `.github/workflows/ios-build.yml`：推送到 `ios/**` 或手动触发后，
会在 macOS 云服务器上自动生成工程并打包出未签名 ipa（Actions 产物里下载）。
未签名包不能直接装真机，需要签名后才能安装。

## 与安卓版的差异

- 内核：iOS 固定用系统 WebKit（自动跟随系统更新，无需内核检查）
- 登录态：WKWebsiteDataStore 自动持久化 Cookie，不存在安卓那个"退出丢登录"问题
- 「退出」按钮：iOS 不允许 App 主动退出（App Store 规范），这里用 `exit(0)` 实现，仅用于自用包

## 配置修改

全部在 `LiyangCommunity/Config.swift`：网址、微云公告链接、联系 QQ、UA 标记。
