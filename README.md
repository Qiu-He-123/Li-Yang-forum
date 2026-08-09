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
```

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

## 安全说明

- Cookie：HttpOnly + SameSite=Strict，生产环境 Secure
- 登录失败锁定（SQLite 持久化，可选 Redis）与 IP 限流（登录/注册/改密/填邀请码/管理员登录）
- 私密图片与公开图片隔离存储，私密图片仅本人/管理员可读
- 图片上传 magic bytes 校验 + 分块限流、帖子图片 URL 协议白名单
- 用户/管理员操作审计日志（`operation_logs`），管理员操作记录 `admin_id`
