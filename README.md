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

## 上线前 Checklist

已随本次整改修复：

- 外键错误：`student_verifications.reviewer_id` 原指向不存在的 `admins` 表，已修正为 `admin`（模型 + 迁移 0022），全新 MySQL 部署可正常迁移
- Docker 镜像缺少 Alembic 迁移文件，已补 `COPY alembic.ini` 与 `COPY alembic/`
- `JWT_SECRET` 默认值已替换为强随机密钥（`backend/.env`，ENV 仍为 dev）
- 生产 Cookie 自动加 `Secure` 标记（`ENV=prod` 时）
- compose 弱口令改为环境变量注入（保留开发默认值），并补 MinIO 容器内 endpoint 与上传卷
- 回归测试从 111 个错误恢复为 105 个全绿（同步到新的注册/邀请码契约，顺带修复编辑帖子不生效的 bug）
- `cookies.txt`、开发数据库、日志等敏感文件已移出版本控制（历史提交中的内容需在公开前清理）

正式运营前仍需完成：

- 正式域名 + 备案 + TLS + HSTS，清掉内网穿透域名
- 生产 MySQL / Redis / MinIO 密钥与多 worker 部署（限流当前为 SQLite 持久化，多 worker 建议切 Redis）
- 内容治理：AI 图片审核当前直接放行，文本审核降级时无敏感词兜底，需管理员值班与举报 SLA
- 学生证照片等敏感个人信息的隐私政策、用户协议正式文本
- 备份恢复演练、监控告警（磁盘 / 内存 / 进程 / 外网可达性）

## 安全说明

- Cookie：HttpOnly + SameSite=Lax，生产环境 Secure
- 登录失败锁定（SQLite 持久化）与 IP 限流
- 图片上传 magic bytes 校验、帖子图片 URL 协议白名单
- 用户/管理员操作审计日志（`operation_logs`），管理员操作记录 `admin_id`
