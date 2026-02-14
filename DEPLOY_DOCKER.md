# Docker 部署指南

## 前置条件

- 一台 Linux VPS
- 已安装 Docker 与 Docker Compose 插件
- 项目目录：`/opt/jm-web`

```bash
sudo mkdir -p /opt/jm-web
sudo chown -R $USER:$USER /opt/jm-web
cd /opt/jm-web
git clone https://github.com/Eterpy/jm-web.git
```

## 后端配置

```bash
cd /opt/jm-web
cp backend/.env.example backend/.env
```

编辑 `backend/.env`，至少修改：

- `SECRET_KEY`（强随机）
- `CREDENTIAL_KEY`（强随机）
- `DEFAULT_ADMIN_PASSWORD`
- `CORS_ORIGINS`（填你的前端域名）
- `JM_CLIENT_IMPL` / `JM_FALLBACK_IMPL`
- `JM_PROXY`（如果 VPS 需要代理访问 JM）

## 启动应用容器

```bash
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
docker compose logs -f frontend
docker compose logs -f backend
```

默认应用端口（仅本机回环）：

- 前端：`127.0.0.1:18080`
- 后端：`127.0.0.1:18000`

---

## 配置反向代理
### 方案 A：1Panel OpenResty

在 1Panel 网站配置里添加反向代理：
```nginx
# /opt/1panel/www/sites/jm.eternge.cc/proxy/root.conf
location / {
    proxy_pass http://127.0.0.1:18080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```
```nginx
# /opt/1panel/www/sites/jm.eternge.cc/proxy/backend.conf
location ^~ /api/v1/ {
    proxy_pass http://127.0.0.1:18000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

HTTPS 证书建议直接用 1Panel 的证书管理申请并绑定。

---

### 方案 B：外部 Nginx

如果你自己装了 Nginx，配置逻辑与上面一致：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /api/ {
        proxy_pass http://127.0.0.1:18000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
    }

    location / {
        proxy_pass http://127.0.0.1:18080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

再结合 `certbot` / acme.sh 配置 HTTPS。

---

### 方案 C：Docker 内置 Caddy

如果你不想在宿主机单独管理反代，可启用 Caddy 覆盖 compose：

```bash
cd /opt/jm-web
cp .env.docker.example .env
# 编辑 .env: APP_DOMAIN=你的域名

docker compose -f docker-compose.yml -f docker-compose.caddy.yml up -d --build
```

查看 Caddy 日志：

```bash
docker compose -f docker-compose.yml -f docker-compose.caddy.yml logs -f caddy
```

说明：

- `docker-compose.yml` 负责应用服务（backend/frontend）
- `docker-compose.caddy.yml` 负责 80/443、TLS 和反代

---

## 更新部署

```bash
cd /opt/jm-web
docker compose up -d --build
```

若你使用 Caddy 方案，更新命令改为：

```bash
docker compose -f docker-compose.yml -f docker-compose.caddy.yml up -d --build
```

## 备份（SQLite）

当前核心数据在 Docker 卷 `backend_storage`。

备份示例：

```bash
docker run --rm \
  -v jm-web_backend_storage:/from \
  -v $(pwd)/backup:/to \
  alpine sh -c 'cp /from/app.db /to/app-$(date +%F-%H%M%S).db'
```

## 常见问题

- 访问 502：先看 `docker compose logs -f backend`
- 反代不通：检查代理目标是否为 `127.0.0.1:18080/18000`
- HTTPS 不生效：检查证书与域名解析
- JM 请求失败：检查 `backend/.env` 中 `JM_PROXY`、`JM_CLIENT_IMPL`、`JM_FALLBACK_IMPL`
