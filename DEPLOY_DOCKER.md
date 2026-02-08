# VPS + Docker 部署指南

## 1. 前置条件

- 一台 Linux VPS（建议 Ubuntu 22.04+）
- 已安装 Docker 与 Docker Compose 插件
- 一个已解析到 VPS 公网 IP 的域名（用于 HTTPS）

## 2. 上传项目

将项目上传到服务器，例如：

```bash
sudo mkdir -p /opt/jm-web
sudo chown -R $USER:$USER /opt/jm-web
cd /opt/jm-web
# 这里放你的项目文件
```

## 3. 配置后端环境变量

```bash
cd /opt/jm-web
cp backend/.env.example backend/.env
```

编辑 `backend/.env`，至少修改：

- `SECRET_KEY`（强随机）
- `CREDENTIAL_KEY`（强随机）
- `DEFAULT_ADMIN_PASSWORD`
- `CORS_ORIGINS`（改成你的前端域名）
- `JM_CLIENT_IMPL` / `JM_FALLBACK_IMPL`
- `JM_PROXY`（如果 VPS 需要代理访问 JM）

## 4. 配置域名

```bash
cp .env.docker.example .env
```

编辑 `.env`：

```env
APP_DOMAIN=你的域名
```

## 5. 启动服务

```bash
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
docker compose logs -f caddy
docker compose logs -f backend
```

首次签发 HTTPS 证书时，确保 80/443 端口已放行。

## 6. 更新部署

```bash
cd /opt/jm-web
# 更新代码后
docker compose up -d --build
```

## 7. 备份

当前使用 SQLite，核心数据位于 Docker 卷 `backend_storage`。

建议定期备份（示例：将数据库导出到宿主机）：

```bash
docker run --rm \
  -v jm-web_backend_storage:/from \
  -v $(pwd)/backup:/to \
  alpine sh -c 'cp /from/app.db /to/app-$(date +%F-%H%M%S).db'
```

> 注意：卷名可能因目录名不同而变化，可用 `docker volume ls` 查看。

## 8. 常见问题

- 访问 502：先看 `docker compose logs -f backend`
- HTTPS 不生效：检查域名解析和 80/443 防火墙
- JM 请求失败：检查 `backend/.env` 中 `JM_PROXY`、`JM_CLIENT_IMPL`、`JM_FALLBACK_IMPL`

