# 立洋校园社区（LY Community）

面向校园的社区产品：帖子流、圈子（表白墙 / 失物招领 / 二手 / 学习互助等）、随机匹配、漂流瓶、学生认证、邀请码体系与管理员后台。

## 技术栈

- 后端：FastAPI + SQLAlchemy 2 + Alembic + SQLite（开发）/ MySQL（生产）
- 前端：Vue 3 + TypeScript + Vite + Element Plus + Tailwind CSS
- 存储与中间件：MinIO（图片）、Redis、Nginx
- AI：OpenAI 兼容接口封装（文本审核 / 标签生成 / 举报摘要，带超时与熔断降级）

## 目录结构

```text
backend/            FastAPI 后端（app/ 业务代码、alembic/ 迁移、scripts/ 工具）
frontend/           Vue3 前端
deploy/             Docker Compose 与 Nginx 配置
tests/ → backend/tests  回归测试（pytest）
微信同步客户端/     朋友圈同步客户端（config.json 本机私有，不入库）
获取微信朋友圈/     朋友圈图片/密钥工具
获取抖音视频/       抖音视频分享解析（登录态本机私有，不入库）
获取快手视频/       快手视频分享解析
工具/               微信密钥工具（db 密钥抓取、解密等）
方便bat/            日常运维脚本（git 同步、数据库备份、启动服务器入口）
docs/               文档与设计稿（反爬说明、项目索引、UI 设计 mockup）
启动立洋社区.bat    首次安装/启动（自动装环境）
重启服务器.bat      日常重启（自动自检修复）
server_config.json  服务器访问配置（bind_host 对外开放开关 / 端口，本机私有）
更新指南.md         更新流程与常见问题
```

> 根目录只保留核心入口；工具类脚本集中在 `方便bat/`，文档在 `docs/`。
> 本机私有文件（`.env`、`微信同步客户端/config.json`、`账号配置/`、`server_config.json` 等）已被 `.gitignore` 排除，不会上传。

## 本地开发

Windows 直接双击根目录 `启动立洋社区.bat`：自动创建虚拟环境、安装依赖、执行 `alembic upgrade head`、启动前后端并打开浏览器。

手动启动：

```bash
# 后端（backend/ 目录）
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\uvicorn app.main:app --reload --port 8000

# 前端（frontend/ 目录）
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`。注册契约为「用户名 + 密码」，邀请码选填（填了直接 verified，可发帖；不填为 unverified，只能浏览）。启动时会自动生成种子邀请码，管理员可在后台批量生成并线下分发。

## 测试

```bash
cd backend
.venv\Scripts\python -m pytest tests -q
```

当前 105 个用例全绿，覆盖注册/登录/邀请码/发帖/评论/互动/后台/安全。
早期阶段的验证脚本已归档到 `backend/scripts/legacy_e2e/`，接口契约已过期，仅作历史参考。

## 生产部署

1. 准备服务器与域名（中国大陆服务器需 ICP 备案），申请 TLS 证书。
2. 配置环境变量：
   ```bash
   cp backend/.env.example backend/.env
   ```
   生产至少修改：`ENV=prod`、`JWT_SECRET`（≥32 位强随机，否则启动拒绝）、`DATABASE_URL=mysql+pymysql://...`、`FRONTEND_ORIGIN=正式域名`、清空 `EXTRA_ORIGINS` 中的内网穿透域名、MinIO 密钥。
3. 启动（密钥通过环境变量传入 compose，避免硬编码默认口令）：
   ```bash
   MYSQL_ROOT_PASSWORD=... MINIO_ACCESS_KEY=... MINIO_SECRET_KEY=... \
   docker compose -f deploy/docker-compose.yml up -d --build
   ```
4. 数据库迁移随后端启动自动执行（镜像已包含 `alembic.ini` 与 `alembic/`）。
5. 创建管理员（无默认后门）：
   ```bash
   docker compose exec backend python scripts/create_admin.py <用户名> <密码>
   ```
6. 外层 Nginx 配置 TLS 与 HSTS（`deploy/nginx.conf` 为 HTTP 模板，生产需补证书与强制跳转）。
7. 配置定时备份：MySQL `mysqldump` + MinIO 数据目录，定期做恢复演练。

## 徽章系统（勋章机制）

- 徽章以图标展示在所有展示名字的场景中，位于名字之前（如 `[🏅] 昵称`），
  覆盖帖子作者行、评论、个人主页、私信会话、通讯录、关注/粉丝、获赞列表、聊天页、漂流瓶、实时匹配等。
- 每人可拥有多个徽章，但同一时间只能**佩戴一个**；佩戴入口在「我的 → 我的徽章」，
  消息中心的徽章卡片也会引导用户前往佩戴与领取。
- 激活码机制：管理员在后台生成激活码，用户在「消息 → 系统」的领取入口输入激活码即可获得徽章，
  领取成功自动写入系统通知。
- 启动时自动初始化 22 个种子徽章（幂等），必须包含**管理员徽章**与**集团成员徽章**，
  其余为签到达人 / 社区之星 / 圈子达人等校园场景徽章。
- 后台新增「徽章管理」页面：徽章增删改（名称 / 标识 / 描述 / 排序 / 启用状态）、
  图标上传（服务端自动极限压缩到 96px 内，徽章展示很小不影响观感）、
  批量生成激活码（B + 8 位安全字符）、激活码列表与删除、按用户 ID 直接发放。

## 种子邀请码后台优化

- 种子邀请码引入三态：`unused`（未使用）/ `reserved`（待使用）/ `used`（已使用）。
- 「复制未使用并标记待使用」：管理员可一键复制 N 个未使用种子码，
  选中的种子自动标记为「待使用」并记录**当前管理员账号与时间**（追加到备注），
  其他管理员在列表中看到后不会再重复分发同一批种子；预留后不再进入「未使用」池。
- 「待使用」种子可一键**释放**回未使用池（清除管理员信息与待使用备注）。
- 列表页新增未使用 / 待使用 / 已使用统计卡片、状态筛选、预留管理员信息列；
  只有「未使用」状态的种子可删除。
- 启动自动补种只统计「未使用」状态的种子，预留中的种子不会被重复计入。

## 内容审核机制

- **AI 不可用不再直接放行**：API Key 未开启 / 无余额 / 调用失败时，
  帖子与评论一律转入 `manual_review`（人工审核中），并弹窗提示作者
  「AI 审核服务暂不可用，已转人工审核」，由管理员在「帖子审核 / 评论审核」页人工处理，
  审核结果通过系统通知告知作者。
- **图片一律人工审核**：上传的图片不走 AI 审核，默认进入待审核队列；
  带图帖子发布时同步挂起（人工审核中）并在发帖页弹窗提示「图片需人工审核，可能较慢」；
  后台新增「图片审核」页，通过图片后关联帖子自动放行，驳回则通知作者更换图片。
- **标题 + 正文一起审核**：AI 审核时同时校验标题与正文，标题违规同样拦截。
- **禁止灌水**：DeepSeek 审核提示词内置「灌水无意义内容」维度
  （如标题仅"12"、内容仅"......"、纯标点、凑字数），拦截但按轻微违规处理
  （severity=low，警告值按 0.5 倍基础分累计，扣分较少）。
- **发帖最少字数**：标题 + 正文合计至少 10 个有效字符（不含空白），前后端双重校验。
- 首页瀑布流「已显示全部内容」底部状态已移出多列容器，不再出现在帖子右侧。
- **漂流瓶也走 AI 审核**：投放的瓶子内容进入 AI 审核，AI 不可用时转人工审核（不直接放行）；
  只有审核通过的瓶子才进入拾取池；后台新增「漂流瓶审核」页（通过/驳回 + 通知作者）。
- **删除帖子即时生效**：从详情页或卡片删除后立即从帖子流与 SWR 缓存移除，
  返回首页/圈子页不再残留已删除帖子。
- **种子码创建人可追溯**：种子码列表新增「创建管理员」列，
  管理员生成的显示管理员账号，系统自动补种的显示「系统自动生成」，
  不再误以为是管理员生成。
- **徽章自动发放规则**：后台「徽章自动发放」页可将「行为动作 + 阈值」绑定到徽章
  （连续签到 / 审核通过帖子数 / 审核通过评论数 / 粉丝数 / 获赞总数），
  用户达成后系统自动发放并通知；动作类型集中在后端注册，扩展性高。
- **头像免审**：头像上传不走内容审核（直接 approved），只有帖子图片进入人工审核。
- **消息详情内领取徽章**：消息中心不再常驻徽章卡片，改在「系统消息详情」页提供
  「领取徽章」按钮输入激活码领取。
- 登录/注册文案：注册字段统一为「账号」，登录明确提示“用注册时的账号登录，不是昵称”。
- 发帖页：发布按钮下方显示最少字数提示（标题+正文合计 ≥ 10 字），
  图片审核说明改为“带图需人工审核，审核通过前其他人看不到，通过后自动发布”。

## 游客引导与注册转化

- 游客首次浏览首页时弹出轻量引导卡片（只提示一次）：
  “登录解锁点赞 / 评论 / 收藏 / 发帖 / 徽章 / 签到 / 漂流瓶，注册 30 秒”，
  可“先逛逛”或“立即登录/注册”。
- 游客点击点赞 / 评论 / 收藏 / 关注 / 加入圈子 / 投票 / 搜索 / 漂流瓶等任一互动入口，
  直接弹出登录注册框，不再只是轻提示。
- 顶部导航对游客显示醒目的「登录 / 注册」按钮；底部 Tab 的“我的”对游客显示为「登录」。
- 帖子详情评论区对游客显示“登录后参与评论”入口，替代空输入框。
- 注册后即使未填邀请码，也可立即点赞、收藏、签到（低风险互动）；
  发帖 / 评论 / 漂流瓶仍需要邀请码解锁。

## 我的页邀请码入口

- 未认证用户：我的页顶部显示「填写邀请码解锁全部功能」卡片，点击直接弹窗填码，
  验证成功即时解锁，无需再去设置页。
- 已认证用户：我的页顶部显示「我的邀请码」卡片（邀请码 + 冷却/冻结状态），
  一键复制分享；功能宫格同时提供「填写邀请码 / 分享邀请码」入口。

## 我的页直接编辑

- 「我的」页点头像直接调起系统相册上传，头像即时生效，无需进入设置。
- 「我的」页点昵称直接弹窗改名；点校区直接弹窗切换校区（首页「本校区」随之更新）。
- 资料完整编辑仍保留在「设置」页。

## 管理后台移动端适配

- 后台侧边栏在手机端改为抽屉菜单（汉堡按钮唤起 + 遮罩点击关闭）。
- 后台所有页面共用响应式样式：筛选栏纵向堆叠、表格横向滚动、弹窗适配屏幕宽度、
  分页器移动端精简，保证手机和电脑都能顺畅操作。

## 上线前 Checklist

已随本次整改修复：

- 外键错误：`student_verifications.reviewer_id` 原指向不存在的 `admins` 表，已修正为 `admin`（模型 + 迁移 0022），全新 MySQL 部署可正常迁移
- Docker 镜像缺少 Alembic 迁移文件，已补 `COPY alembic.ini` 与 `COPY alembic/`
- `JWT_SECRET` 默认值已替换为强随机密钥（`backend/.env`，ENV 仍为 dev）
- 生产 Cookie 自动加 `Secure` 标记（`ENV=prod` 时）
- compose 弱口令改为环境变量注入（保留开发默认值），并补 MinIO 容器内 endpoint 与上传卷
- 回归测试从 111 个错误恢复为 105 个全绿（同步到新的注册/邀请码契约，顺带修复编辑帖子不生效的 bug）
- `cookies.txt`、开发数据库、日志等敏感文件已移出版本控制（历史提交中的内容需在公开前清理）

第二轮安全加固（P0–P2）：

- **私密图片隔离**：学生证等敏感照片改走 `/images/verification` 私密上传 + `/images/private/*` 鉴权读取（仅本人/管理员），不再落公开静态目录；认证提交改为必须传本人私密图片 id，拒绝任意 URL
- **管理员登录防爆破**：IP 限流 + 失败锁定（复用登录锁定机制），`create_admin.py` 强制强密码（≥12 位，含大小写/数字/符号）
- **部署模式修正**：compose 强制 `ENV=prod`（Secure Cookie / 强校验生效），后端/MinIO/MySQL/Redis 端口不再映射公网，仅暴露 Nginx 80
- **上传防 DoS**：图片上传分块读取 + Content-Length 预检，Nginx `client_max_body_size 6m`
- **依赖升级**：fastapi 0.141 / starlette 1.5 / python-multipart 0.0.32 / Pillow 12.3 / PyJWT 2.13（替换已停维护的 python-jose），npm 侧 nanoid 升级后 audit 清零
- **Cookie SameSite=Strict** + WebSocket Origin 校验；Nginx 增加 CSP / X-Frame-Options / nosniff / Referrer-Policy
- **MinIO 双桶**：公开图片桶只读策略 + 同源 `/minio/` 反代；私密图片独立私有桶；新增 `MINIO_PRIVATE_BUCKET` 配置
- **前端可构建**：修复 Admin 页面 38 处历史遗留 TS 类型错误，`npm run build` 通过

正式运营前仍需完成：

- 正式域名 + 备案 + TLS + HSTS（`deploy/nginx.conf` 已预留注释），清掉内网穿透域名
- 生产 MySQL / Redis / MinIO 强密钥；多 worker 部署时限流建议切 Redis（当前 SQLite 持久化，单 worker 正确）
- 内容治理：AI 图片审核当前直接放行，文本审核降级时无敏感词兜底，需管理员值班与举报 SLA
- 学生证照片等敏感个人信息的隐私政策、用户协议正式文本
- 备份恢复演练、监控告警（磁盘 / 内存 / 进程 / 外网可达性）；git 历史中的旧敏感文件需用 filter-repo 清理并确认远端仓库为 private

## 数据库备份与恢复（备份到 GitHub）

备份脚本会把数据库做成一致性快照（SQLite 用官方 backup API，MySQL 用 `mysqldump`），压缩后上传到私有备份仓库 [Qiu-He-123/liyang-backups](https://github.com/Qiu-He-123/liyang-backups) 的 Releases 里，并按 `BACKUP_KEEP` 自动清理旧备份。上传走 GitHub API，不占用代码仓库的 git 历史，也不会碰到本仓库的 `.gitignore` 限制。

### 首次配置（在真正跑数据的服务器上做一次）

1. 给 GitHub 生成一个访问令牌：GitHub → Settings → Developer settings → Personal access tokens → Generate new token (classic)，勾选 `repo`，复制下来。
2. 打开服务器的 `backend/.env`（不要提交它），加入：

   ```env
   GITHUB_TOKEN=你生成的令牌
   BACKUP_DIR=backups
   BACKUP_KEEP=30
   # 强烈建议开启加密：
   # BACKUP_PASSPHRASE=一个只有你知道的密码
   ```

3. 如果生产 MySQL 跑在 Docker 里，再按实际情况加（路径换成服务器上的部署路径）：

   ```env
   BACKUP_MYSQL_PASSWORD=MySQL root 密码
   BACKUP_MYSQL_CMD=docker compose -f /opt/liyang/deploy/docker-compose.yml exec -T mysql mysqldump -uroot -p"{password}" --single-transaction --routines --triggers {db}
   BACKUP_MYSQL_RESTORE_CMD=docker compose -f /opt/liyang/deploy/docker-compose.yml exec -T mysql mysql -uroot -p"{password}" {db} < {file}
   ```

   如果 MySQL 直接装在服务器上（非 Docker），这两项不用配，脚本会用 `DATABASE_URL` 自动调用本机 `mysqldump`。

### 手动备份

```bash
cd backend
.venv/bin/python scripts/backup_db.py            # Linux
.venv\Scripts\python scripts\backup_db.py        # Windows
```

Windows 也可以直接双击 `方便bat\备份数据库.bat`。备份完成后到 https://github.com/Qiu-He-123/liyang-backups/releases 查看。

### 定时自动备份

Linux（生产服务器，每天凌晨 3 点）：

```bash
crontab -e
# 加入一行：
0 3 * * * cd /opt/liyang/backend && .venv/bin/python scripts/backup_db.py >> logs/backup.log 2>&1
```

Windows（推荐）：右键 `方便bat\安装定时备份.bat` → 以管理员身份运行，一次即可，之后每天 03:00 自动备份。

Windows（手动，等价操作）：

```bat
:: 把 <仓库绝对路径> 换成你自己电脑上仓库的实际路径
schtasks /Create /SC DAILY /ST 03:00 /TN "LY Community DB Backup" /TR "<仓库绝对路径>\方便bat\定时备份数据库.bat"
```

### 恢复数据

先停掉后端服务，然后在 backend 目录执行（会自动把当前数据库先备份成 `.pre-restore-时间戳`）：

```bash
.venv/bin/python scripts/restore_db.py --latest        # 恢复最近一次 GitHub 备份
.venv/bin/python scripts/restore_db.py --tag backup-20260811_030000   # 恢复指定那次
.venv/bin/python scripts/restore_db.py --file /path/to/ly_community_20260811_030000.sqlite3.gz
```

恢复 SQLite 会做 `PRAGMA integrity_check` 校验；恢复 MySQL 会执行 SQL 导入。完成后重启后端服务。

### 注意事项

- 备份仓库必须是 **Private**，并强烈建议设置 `BACKUP_PASSPHRASE` 加密（备份里有用户密码哈希、手机号、学生证照片引用等敏感数据）。
- 本脚本只备份数据库。图片存在 MinIO 卷（`uploads_data` / `uploads_private_data`），需要另外用 rsync / duplicati 等工具做异地备份，否则只恢复数据库会丢图。
- 服务器磁盘上也会保留最近 `BACKUP_KEEP` 份本地备份，防止 GitHub 临时不可用。

## 安全说明

- Cookie：HttpOnly + SameSite=Strict，生产环境 Secure
- 登录失败锁定（SQLite 持久化，可选 Redis）与 IP 限流（登录/注册/改密/填邀请码/管理员登录）
- 私密图片与公开图片隔离存储，私密图片仅本人/管理员可读
- 图片上传 magic bytes 校验 + 分块限流、帖子图片 URL 协议白名单
- 用户/管理员操作审计日志（`operation_logs`），管理员操作记录 `admin_id`

## 微信朋友圈同步（新增）

目标：提升社区活跃度。用户添加社区微信并绑定后，可把朋友圈内容同步到社区。

- **绑定**：加社区微信 → 在「微信朋友圈」页输入自己的微信号/wxid → 匹配好友快照成功即绑定（不可自改，后台可人工解绑）
- **自动同步**：用户开启后，只同步开启时间之后发布的朋友圈；同步客户端每 10 秒增量扫描（按 tid 去重），后端命中绑定+开关才发帖
- **手动导入**：微信朋友圈页勾选动态发布到论坛；支持置顶（同批第 1/2/3 条 1/2/3 金币/天，时长自选）
- **微信朋友圈频道**：首页第三 tab，朋友圈时间线样式，全局按发布时间倒序，置顶优先；同步帖也出现在推荐/最新
- **金币体系**：绑定送 10、签到可赚；用于置顶与购买徽章（皮肤后续扩展）
- **新手引导**：首次登录（含老用户）未完成引导时触发，可跳过

### 部署

1. 后端：`alembic upgrade head`（0036 新增绑定/朋友圈/金币表）
2. 设备令牌：`backend/scripts/init_wechat_sync.py` 查看，填入 `微信同步客户端/config.json`
3. 同步客户端：双击 `微信同步客户端/启动同步客户端.bat`，自检通过后启动；微信需保持登录并打开朋友圈页面
4. 启动自检不通过时按弹窗指引：登录微信 → 打开朋友圈点开浏览 2-3 张图片 → 重新抓取图片密钥（微信重启不影响图片密钥，无需重抓）

### 重启服务器（推荐入口）

双击 `重启服务器.bat`：
1. 自动停止旧的后端/前端进程
2. 分步向导：
   - 第 1 步：选择微信号（昵称（微信号）），列表始终显示微信数据目录下的全部账号；找不到时可点「手动选择目录」指定 xwechat_files 位置
   - 第 2 步：朋友圈数据库密钥——能解密自动跳过；失败则引导运行密钥工具重抓 db_key
   - 第 3 步：图片密钥——能解密自动跳过；失败则引导在微信里点开两三张图片后运行「解密图片」
   - 第 4 步：通过后自动跑数据库迁移，启动后端 + 前端（可勾选同步客户端），并打开浏览器
3. 服务器运行期间由 `图片密钥监控.py` 每 30 秒检测图片能否解密；微信闪退/重登导致密钥失效时
   会弹出「解密图片」窗口引导补密钥，**不需要重启服务器**
