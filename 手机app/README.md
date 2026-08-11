# 立洋论坛 手机 App（套壳版）

一个极简的 Android 套壳应用：打开一个 WebView 加载立洋社区网页，不做任何二次开发。

## 功能

- 打开 `MainActivity.java` 常量里配置的网址，站内链接留在 App 内打开，站外链接交给系统浏览器。
- 支持网页里的图片/文件选择上传（头像、帖子图片等）。
- 启动时检查手机 WebView 内核版本，过低会提示"更新内核"（可跳过）。
- 打开 App 先拉取微云笔记公告，按"标签{内容}"格式（取中间文本）解析全部字段。
- 服务器连不上 / 返回 5xx 时，显示维护面板：
  - 展示从微云公告页拉到的公告内容，取不到就显示"请检查网络连接是否正常以及联系管理员"；
  - 「联系管理员」自动复制 QQ 号 `qhqe2623655749`；
  - 「重新连接」重试加载；
  - 「退出」关闭 App。
- 返回键优先回退网页历史（帖子详情 → 首页），而不是直接退出 App；
  已在最顶层时 2 秒内连按两次返回才退出，防止误触。
- 状态栏/刘海安全区适配在 App 内完成：检测到内容顶到状态栏下面时
  自动补状态栏高度内边距，顶部文字不会被摄像头遮挡（不动网页端）。

## 需要修改的配置

全部在 `app/src/main/java/com/liyang/community/MainActivity.java` 顶部的常量里（不用 strings.xml）：

| 配置 | 说明 |
|---|---|
| `APP_URL` | 要打开的网页地址。正式上线建议改成 `https://` 域名 |
| `NOTICE_URL` | 微云公告分享页 |
| `CONTACT_QQ` | 联系管理员按钮复制的 QQ 号 |
| `DEFAULT_NOTICE` | 公告取不出来时的兜底文案 |

> 微云公告的维护方式：编辑微云笔记，笔记正文按"标签{内容}"写，例如：
>
> ```text
> 公告{服务器维护中}
> 打开网址{https://...}
> 管理员账号{qq号}
> ```
>
> App 会按"取中间文本"方式解析花括号里的内容，标签（花括号前面的文字）不要改，
> 以后新增字段也会被自动显示出来。

## 网页版和 App 怎么区分

App 会给 WebView 追加一个 UA 标记：`LYCommunityApp/1.0`（在系统 UA 末尾）。
前端代码里这样判断：

```js
const isApp = navigator.userAgent.includes('LYCommunityApp')
```

如果不想动 UA，也可以让 App 加载时带上 `?from=app` 参数，二选一即可。
需要调样式时，在 App 环境下给顶部加 `padding-top: env(safe-area-inset-top)` 即可避开刘海。

## 关于"网页内核"

Android 套壳 App 用的是手机系统自带的 **Android System WebView**（和 Chrome 同内核，系统商店里持续更新）。App 本身无法内置一个"最新内核"——真要内置得打包整个浏览器引擎，APK 会从几 MB 涨到 100MB 以上，得不偿失。

所以本项目做了两层保证：
1. 系统 WebView 本来就是持续更新的，手机上装了多新就用多新；
2. 启动时检测内核版本，主版本低于 100（约 2022 年）会弹提示引导去应用商店更新，避免旧内核渲染异常。

如果你在手机上看到"网页内核版本过低"，去应用商店把「Android System WebView」更新一下即可（小米/华为等手机商店里可能叫"系统 WebView"或"浏览器内核"）。

## 打包 APK

### 方式一：Android Studio（推荐）

1. 用 Android Studio 打开本目录（`手机app`）。
2. 等 Gradle 同步完成。
3. 菜单 Build → Build App Bundle(s) / APK(s) → Build APK(s)。
4. 产物在 `app/build/outputs/apk/debug/app-debug.apk`。

### 方式二：命令行

需要 JDK 17+ 和 Android SDK（`local.properties` 里已指向本机 SDK）：

```bat
gradlew assembleDebug
```

调试版产物：`app/build/outputs/apk/debug/app-debug.apk`。

正式版（已配置签名）：

```bat
gradlew assembleRelease
```

正式版产物：`app/build/outputs/apk/release/app-release.apk`。

> **重要：正式版签名密钥**。`liyang-release.keystore` 和 `keystore-password.txt`
> 是正式版签名用的密钥和密码（在 `手机app/` 目录下，已加入 .gitignore，不会上传 GitHub）。
> 请务必备份这两个文件：以后更新版本必须用同一把钥匙签名，
> 丢了之后用户将无法覆盖安装新版本，只能卸载重装。

> 本机已经装好环境，直接跑 `gradlew.bat` 即可；第一次会下载构建插件，比较慢。

## 安装到手机

1. 把 APK 发到手机（微信/QQ/数据线均可）。
2. 手机上点开 APK 安装。调试版 APK 是 debug 签名，安装时如提示未知来源，允许即可。
3. 注意：App 打开的是 `APP_URL` 指向的服务器，**电脑端的服务/内网穿透必须开着**，否则会进维护面板。

## 常见问题

**打开一直显示"服务器维护更新中"**
电脑端没启动服务，或内网穿透域名失效。先在电脑上把后端 + 前端 + 内网穿透跑起来，再点「重新连接」。

**点「联系管理员」后没反应**
按钮会把 QQ 号复制到剪贴板，去 QQ 搜索框粘贴即可。

**换了正式域名**
改 `MainActivity.java` 顶部的 `APP_URL`，并确认域名是 `https`（或已加入 `network_security_config.xml` 的明文白名单），重新打包。

**能做 iOS 版吗**
打包 iOS 需要 Mac 和 Apple 开发者账号；这套项目只覆盖 Android。

**首屏加载慢**
如果服务器返回的静态资源没有长缓存（响应头是 `Cache-Control: no-cache`），每次打开 App 都会重新校验全部 JS/CSS，内网穿透线路慢的话会更明显。建议在服务器（Nginx）给带内容哈希的文件加缓存，例如：

```nginx
location /assets/ {
    expires 30d;
    add_header Cache-Control "public, max-age=2592000, immutable";
}
```

另外正式上线建议用国内服务器 + 备案域名，隧道中转的延迟和带宽都会拖慢首屏。
