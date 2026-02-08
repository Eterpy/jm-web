# JM Web

基于 `JMComic-Crawler-Python` 与 `image2pdf` 思路实现的禁漫下载网站骨架。

## 功能状态

已落地：
- 前端登录（管理员/用户）
- 管理员用户管理（创建/删除用户，无注册入口）
- 用户通过ID下载：单本子、单章节、多个本子
- 搜索本子并创建下载任务
- JM账号登录校验与保存
- 下载完成后合并为 PDF（多本子会打 ZIP）
- 1小时有效下载令牌 + 定时清理 PDF 和原始图片
- 可选：周排行、收藏夹接口

## 目录

- `backend/` FastAPI 后端
- `frontend/` Vue3 前端
- `reference/` 参考资料

## 启动后端

> 建议使用 Python 3.13（当前依赖组合在 Python 3.14 下会遇到 `pydantic-core` 构建兼容问题）。

```bash
cd /Users/interpy/Downloads/jm-web
/opt/homebrew/bin/python3.13 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

## 网络/代理排障（JM请求失败时）

如果日志出现 `请求不是json格式`、`/setting 404`、Cloudflare challenge 页面，通常是当前网络到 JM API 域名不可用。请在 `backend/.env` 调整：

```env
JM_CLIENT_IMPL=html
JM_FALLBACK_IMPL=api

# 本地代理（按你的实际端口）
JM_PROXY=127.0.0.1:7890

# 可选：手动指定网页域名（逗号分隔）
JM_HTML_DOMAINS=18comic.vip,18comic.org,jmcomic1.me,jmcomic.me

# 可选：手动指定API域名（逗号分隔）
JM_API_DOMAINS=
```

改完后重启后端服务生效。

## 用户下载限流（按本子数量）

后端已按用户限制“本子下载数量”，并且 `multi_album` 会按本子 ID 个数计数。可在 `backend/.env` 调整：

```env
# 单次任务最多多少本子（multi_album 会按 ID 数量计）
USER_ALBUM_LIMIT_PER_JOB=20

# 同时进行中的本子总量上限（queued/running/merging）
USER_ALBUM_LIMIT_INFLIGHT=20

# 时间窗口内累计本子总量上限（queued/running/merging/done）
USER_ALBUM_LIMIT_WINDOW_COUNT=100
USER_ALBUM_LIMIT_WINDOW_MINUTES=60
```

## 启动前端

```bash
cd /Users/interpy/Downloads/jm-web/frontend
npm install
npm run dev
```

前端默认访问 `http://localhost:8000/api/v1`。

## 默认管理员

- 用户名：`admin`
- 密码：`admin123`

请在首次启动后修改 `backend/.env` 中默认管理员密码并重建数据库，或登录后新建管理员再删除默认账户。

## Docker 部署

- 生产部署文档见 `DEPLOY_DOCKER.md`
- 关键文件：`docker-compose.yml`、`backend/Dockerfile`、`frontend/Dockerfile`、`deploy/Caddyfile`
