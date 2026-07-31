# 立洋校园社区

面向立洋学校内部使用的 Web 校园社区，Logo 文案为 `LY Community`。

## 目录

- `frontend/`: Vue3 + TypeScript + Vite + Pinia + Vue Router + Axios + Element Plus + TailwindCSS
- `backend/`: FastAPI + SQLAlchemy + Pydantic + JWT + Alembic + WebSocket
- `deploy/`: Nginx 和 Docker Compose 配置
- `backend/alembic/`: 数据库迁移脚本（T3-1 引入）

## 本地启动

Windows 下可以直接双击根目录的 `启动立洋社区.bat`，它会：
1. 首次运行自动创建 Python `.venv` 并安装 `requirements.txt`
2. 首次运行自动执行 `npm install`
3. **每次启动前自动执行 `alembic upgrade head`（T3-1/T9-3），保证数据库 schema 最新**
4. 启动后端（uvicorn 127.0.0.1:8000）+ 前端（vite 127.0.0.1:5173）并打开浏览器

> 若 Alembic 迁移失败，脚本会暂停并提示检查 `backend/.env` 的 `DATABASE_URL`。

不要直接双击 `frontend/index.html`。它是 Vite 源码入口，需要开发服务器编译 Vue、TypeScript 和依赖；浏览器用 `file://` 打开会因为路径、ES Module 和依赖编译问题显示为空白或兜底提示。

### 后端

```powershell
cd backend
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# 【必做】首次启动前执行 Alembic 迁移，创建全部数据库表
alembic upgrade head
uvicorn app.main:app --reload
```

接口文档：`http://127.0.0.1:8000/docs`

### 前端

```powershell
cd frontend
npm install
npm run dev
```

访问：`http://127.0.0.1:5173`

## 生产部署

### 1. 配置环境变量

复制 `backend/.env.example` 为 `backend/.env`，并修改以下必填项：

| 变量 | 必改 | 说明 |
|---|---|---|
| `ENV` | 是 | 生产环境必须设为 `prod`（触发 jwt_secret 强校验，T2-4） |
| `JWT_SECRET` | 是 | **必改**，默认值 `change-me` 在 `ENV=prod` 下会启动失败（T2-4） |
| `DATABASE_URL` | 是 | 生产建议 MySQL：`mysql+pymysql://user:pwd@host:3306/ly_community` |
| `FRONTEND_ORIGIN` | 是 | 前端实际访问域名，如 `https://community.lyschool.cn` |
| `OPENAI_API_KEY` | 否 | 留空则 AI 审核自动降级（T7-1），不阻塞业务 |
| `MINIO_*` | 否 | 留空时图片上传回退到 `backend/uploads/` 本地目录 |

### 2. 数据库迁移（必做）

```powershell
cd backend
alembic upgrade head
```

- 首次部署：创建全部数据库表（schools / users / posts / comments / likes / favorites / tokens / admin / operation_logs / login_logs / rate_limits / login_failures / images / announcement / reports / notifications / messages）
- 升级部署：自动增量迁移到最新 schema

**禁止**删除 `alembic/` 目录或回退到 `Base.metadata.create_all`（T3-1）。

### 3. 创建管理员账号（必做）

T2-3 已移除默认 `admin/admin123456` 后门，首次部署必须通过 CLI 脚本创建管理员：

```powershell
cd backend
python scripts/create_admin.py admin MyStrongPwd@2026
# 或指定角色
python scripts/create_admin.py ops AdminOpsPwd@2026 --role admin
```

- 用户名 1-32 字符
- 密码至少 8 位（建议 ≥ 12 位，包含大小写+数字+符号）
- 创建后可通过 `/admin/login` 接口登录管理后台

### 4. 启动服务

#### 方式 A：Docker Compose（推荐）

```powershell
docker compose -f deploy/docker-compose.yml up -d --build
```

#### 方式 B：手动启动

```powershell
# 后端
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 前端构建
cd frontend
npm run build
# 用 nginx 托管 dist/ 目录，配置参考 deploy/nginx.conf
```

### 5. 安全检查清单（上线前必做）

- [ ] `ENV=prod` 已设置
- [ ] `JWT_SECRET` 已修改为强随机字符串（≥ 32 位）
- [ ] `alembic upgrade head` 已执行
- [ ] 管理员账号已通过 CLI 创建（非默认后门）
- [ ] `FRONTEND_ORIGIN` 已配置为生产域名
- [ ] HTTPS 已启用（Nginx 反向代理 + TLS 证书）
- [ ] CORS 已收紧到生产域名（T7-12，main.py 已配置）
- [ ] 数据库定期备份策略已就绪

## 安全机制（T2 / T7 阶段实现）

| 机制 | 说明 |
|---|---|
| JWT Cookie 鉴权 | access_token 30 分钟过期 + refresh_token 30 天（T2-6/T2-7 自动续期） |
| 独立 admin_token Cookie | 管理员与用户鉴权隔离，避免越权（T2-1/T2-2） |
| jwt_secret 强校验 | 生产环境默认值启动失败（T2-4） |
| logout 撤销 refresh_token | 防止旧 token 复用（T2-5） |
| 登录失败锁定 | 10 次失败锁 30 分钟，SQLite 持久化（T7-8） |
| IP 限流 | 登录/注册/验证码接口每分钟 10 次（T7-9） |
| 图片 magic bytes 校验 | 防伪装 content_type 上传可执行文件（T7-10） |
| 图片 URL 协议白名单 | 拒绝 `javascript:` 等 XSS URL（T7-11） |
| CORS 收紧 | 仅允许 GET/POST/PATCH/DELETE/PUT（T7-12） |
| XFF IP 校验 | 防伪造 `X-Forwarded-For`（T7-13） |
| AI 服务降级 | 网络异常 2 秒超时 + 5 分钟熔断，不阻塞业务（T7-1/T8-1） |

## 测试（T9-1）

```powershell
cd backend
python -m pytest tests/ -v
```

覆盖 110 个测试用例，包含：
- `test_auth.py`: 注册/登录/登出/refresh/修改密码/失败锁定
- `test_post.py`: 发帖/编辑/删除/草稿/分页/搜索/is_public 过滤
- `test_comment.py`: 发评论/二级回复/删除/分页/**级联删除子回复**（T9-1 新增）
- `test_interaction.py`: 点赞/取消/收藏/取消/举报/幂等性
- `test_user.py`: 个人主页/编辑资料/我的草稿/收藏/点赞
- `test_admin.py`: admin 登录/鉴权/各管理接口/OperationLog.admin_id
- `test_security.py`: 未登录访问/IP 伪造/伪装上传/XSS URL/CORS/jwt_secret 校验

## 已覆盖的功能（V1）

### 用户系统
- 注册/登录（密码 + 验证码 dev stub `123456`）/登出/会话校验
- access_token 自动续期（refresh_token 轮转）
- 修改密码（撤销其他设备 token）
- 个人主页（头像 banner + 帖子/收藏/点赞 Tab）
- 编辑资料（昵称/头像/背景图/简介）
- 设置页（基本资料 + 账号安全）

### 帖子系统
- 发帖（含图片上传 ≤ 9 张）+ AI 文本审核 + AI 标签生成
- 编辑/删除帖子（作者权限）
- 4 视图切换（全校/本校区/热门/最新）
- 分页（page/page_size）+ 关键词搜索 + 标签搜索 + 分类过滤
- 草稿（保存/列表/发布）+ 私密帖子（仅作者可见）
- 帖子点赞/收藏/举报（带具体理由）+ active 态回填

### 评论系统
- 一级评论 + 二级回复（parent_id 分层渲染）
- 评论点赞 + 删除（作者权限）
- **级联删除：删除根评论时自动删除其所有回复，保证 comment_count 与列表一致**（T9-1 Bug 修复）
- 评论分页 + `post_comment_count` 接口同步（绝对值覆盖，避免前后端不一致）

### 通知系统
- 通知中心 + 已读/未读状态
- 互动（点赞/评论/收藏）触发通知写入

### 管理员后台
- 独立登录页 + admin_token Cookie 鉴权
- 7 个子页面：帖子/评论/用户/举报/公告/操作日志/用户日志
- 管理员删除任意帖子 + 创建公告
- admin_id 写入操作日志（可追溯）

### 其他
- 公告按校区过滤
- 404/500 兜底页 + 全局 errorHandler
- 用户协议页
- SQLite WAL 模式（并发读写优化）
- N+1 查询优化（selectinload）
