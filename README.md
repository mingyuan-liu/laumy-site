# laumy.tech Hugo Site

这是 `laumy.tech` 的 Hugo 静态站点代码仓库。它只保存网站程序、模板、样式、构建脚本和部署模板；文章 Markdown 和文章图片应放在独立的内容仓库中。

公开仓库注意事项：

- 不提交服务器 IP、SSH 用户、真实绝对路径、数据库密码、JWT、webhook secret、SSH 私钥。
- 不提交生成目录、发布目录、文章图片共享目录和数据库导出。
- 示例命令里的 `<server>`、`<site-dir>`、`<content-dir>`、`<public-dir>` 都是占位符，需要按自己的服务器环境替换。

## 1. Architecture

仓库职责分离：

```text
content repo  -> Markdown 文章和文章 assets
site repo     -> Hugo 配置、模板、样式、脚本、部署模板
server        -> 拉取两个仓库，构建 Hugo，Nginx 对外服务
```

服务器建议目录：

```text
<content-dir>                 # 内容仓库 clone
<site-dir>                    # 本仓库 clone
<public-dir>/current          # 当前线上 release 软链接
<public-dir>/releases         # 发布历史
<public-dir>/shared           # 共享静态资源，存文章图片
```

当前部署脚本默认使用：

```text
<site-dir>    = /srv/laumy-site
<content-dir> = /srv/laumy-notes-content
<public-dir>  = /var/www/laumy-static
```

这些默认值可以通过 `/etc/laumy-deploy.env` 覆盖。

## 2. Repository Layout

```text
.
├── hugo.toml                    # Hugo 配置
├── layouts/                     # 页面模板
├── static/
│   ├── css/                     # 样式
│   ├── js/                      # 前端脚本
│   ├── images/                  # 头像、二维码、默认图
│   └── vendor/                  # KaTeX、Waline 前端资源
├── content/about.md             # 独立页面
├── data/                        # 分类、历史统计、迁移元数据
├── scripts/
│   ├── build_content.py         # 从内容仓库生成 Hugo content
│   ├── deploy.sh                # 构建并发布 release
│   ├── update_from_git.sh       # 拉取 GitHub 变更并触发部署
│   ├── deploy_webhook.py        # GitHub webhook 服务
│   └── seed_waline_views.py     # 初始化 Waline 热度
└── deploy/
    ├── systemd/                 # systemd 单元模板
    ├── nginx/                   # Nginx 配置模板
    └── *.env.example            # 环境变量示例
```

不要手动修改：

```text
content/posts/
public/
resources/
static/assets/
```

这些目录要么是生成物，要么应放在服务器共享静态目录中。

## 3. Content Repo

内容仓库面向写作，推荐目录：

```text
01-Linux/
  1.1-中断管理/
    文章标题.md
    assets/
      figure.png
04-AI/
  4.4-推理框架/
    解构LLM.md
    assets/
      cover.png
```

规则：

- 目录层级就是分类层级。
- 编号只用于排序，构建时会被去掉。
- 文章图片放在同级 `assets/` 目录。
- 文章中使用相对路径引用图片：

```markdown
![说明](./assets/figure.png)
```

构建后图片会复制到：

```text
<public-dir>/shared/assets/posts/<hash>/figure.png
```

页面中引用路径会变成：

```text
/assets/posts/<hash>/figure.png
```

## 4. Frontmatter

历史文章建议保留：

```yaml
---
id: 3254
title: "解构LLM： 以llama.cpp分析模型推理过程"
slug: "解构llm：-以llama-cpp分析模型推理过程"
url: "/3254.html/解构llm：-以llama-cpp分析模型推理过程/"
date: "2026-03-15T02:36:39+00:00"
modified: "2026-03-24T03:06:28+00:00"
category: "推理框架"
author: "laumy"
canonical: "https://www.example.com/3254.html/解构llm：-以llama-cpp分析模型推理过程/"
views: 1013
status: publish
---
```

字段说明：

- `id`：历史文章 ID，评论、热度、迁移数据会用到。
- `url`：保留旧文章 URL，避免搜索引擎权重丢失。
- `canonical`：规范化 URL。
- `views`：历史热度初始值，不再作为实时热度来源。
- `status`：`publish` 才发布，`draft` 不发布。

封面不需要手动维护。构建时会使用文章正文里的第一张图片作为封面；如果文章没有图片，就使用默认封面 `/images/default-thumb.jpg`。

新文章最小示例：

```yaml
---
title: "新文章标题"
date: "2026-05-18T10:00:00+08:00"
modified: "2026-05-18T10:00:00+08:00"
author: "laumy"
status: publish
---
```

## 5. Local Build

安装依赖：

```bash
sudo apt-get install hugo python3 rsync
```

本地预览：

```bash
CONTENT_DIR=/path/to/content-repo
SITE_DIR=/path/to/laumy-site
python3 scripts/build_content.py "$CONTENT_DIR" --site "$SITE_DIR"
hugo server --source "$SITE_DIR" --bind 127.0.0.1 --port 1313
```

本地构建：

```bash
CONTENT_DIR=/path/to/content-repo
SITE_DIR=/path/to/laumy-site
python3 scripts/build_content.py "$CONTENT_DIR" --site "$SITE_DIR"
hugo --source "$SITE_DIR" --destination "$SITE_DIR/public" --minify
```

## 6. Deployment

部署脚本：

```bash
<site-dir>/scripts/deploy.sh
```

流程：

1. 从内容仓库读取 Markdown。
2. 生成 Hugo `content/posts/`。
3. 生成分类树数据。
4. 将文章图片同步到 `<public-dir>/shared/assets/posts/`。
5. 构建 Hugo 到 `<public-dir>/releases/<timestamp>`。
6. 切换 `<public-dir>/current` 软链接。
7. 默认保留最近 3 个 release。

手动部署：

```bash
ssh <server> 'cd <site-dir> && ./scripts/deploy.sh'
```

保留更多 release：

```bash
ssh <server> 'cd <site-dir> && KEEP_RELEASES=5 ./scripts/deploy.sh'
```

回滚：

```bash
ssh <server> 'ls -1 <public-dir>/releases'
ssh <server> 'ln -sfn <public-dir>/releases/<release-name> <public-dir>/current'
```

## 7. GitHub Webhook

推荐发布链路：

```text
git push content repo -> GitHub webhook -> server pulls repo -> Hugo deploy
```

服务端组件：

```text
scripts/update_from_git.sh
scripts/deploy_webhook.py
deploy/systemd/laumy-git-deploy.service
deploy/systemd/laumy-deploy-webhook.service
deploy/nginx/laumy-static-preview.conf
```

### 7.1 Deploy Env

复制并修改：

```bash
sudo cp deploy/laumy-deploy.env.example /etc/laumy-deploy.env
sudo editor /etc/laumy-deploy.env
```

示例：

```env
SITE_DIR=/srv/laumy-site
CONTENT_DIR=/srv/laumy-notes-content
SITE_BRANCH=main
CONTENT_BRANCH=main
FORCE=0
DEPLOY_CMD=/srv/laumy-site/scripts/deploy.sh
LOG_DIR=/var/log/laumy-deploy
```

### 7.2 Webhook Env

复制并修改：

```bash
sudo cp deploy/laumy-webhook.env.example /etc/laumy-webhook.env
sudo chmod 600 /etc/laumy-webhook.env
sudo editor /etc/laumy-webhook.env
```

示例：

```env
WEBHOOK_HOST=127.0.0.1
WEBHOOK_PORT=8789
WEBHOOK_PATH=/deploy-hook
WEBHOOK_HEALTH_PATH=/deploy-hook/healthz
WEBHOOK_SECRET=<random-long-secret>
ALLOWED_REPOSITORIES=<owner>/<content-repo>
ALLOWED_REFS=refs/heads/main
DEPLOY_SERVICE=laumy-git-deploy.service
LOG_LEVEL=INFO
```

生成 secret：

```bash
openssl rand -hex 32
```

不要把 `/etc/laumy-webhook.env` 提交到 GitHub。

### 7.3 systemd

```bash
sudo cp deploy/systemd/laumy-git-deploy.service /etc/systemd/system/
sudo cp deploy/systemd/laumy-deploy-webhook.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now laumy-deploy-webhook.service
```

手动触发部署：

```bash
sudo systemctl start laumy-git-deploy.service
```

查看日志：

```bash
sudo journalctl -u laumy-deploy-webhook.service -n 100 --no-pager
sudo journalctl -u laumy-git-deploy.service -n 100 --no-pager
tail -100 /var/log/laumy-deploy/deploy.log
```

### 7.4 Nginx

Nginx 需要提供：

- `/`：静态站点 release。
- `/assets/posts/`：共享文章图片。
- `/waline/`：Waline 服务代理。
- `/deploy-hook`：webhook 代理。

参考配置见：

```text
deploy/nginx/laumy-static-preview.conf
```

生产环境建议使用 HTTPS，并把 GitHub webhook 的 Payload URL 配成：

```text
https://www.example.com/deploy-hook
```

GitHub webhook 设置：

```text
Payload URL: https://www.example.com/deploy-hook
Content type: application/json
Secret: WEBHOOK_SECRET
Events: Just the push event
```

## 8. Private Content Repo

如果内容仓库是私有仓库，服务器需要只读 deploy key：

```bash
ssh-keygen -t ed25519 -C "content-deploy-key" -f ~/.ssh/content_deploy -N ""
cat ~/.ssh/content_deploy.pub
```

把公钥添加到内容仓库：

```text
Settings -> Deploy keys -> Add deploy key
Allow write access: off
```

服务器 `~/.ssh/config` 示例：

```sshconfig
Host github-content
  HostName github.com
  User git
  IdentityFile ~/.ssh/content_deploy
  IdentitiesOnly yes
```

clone：

```bash
git clone -b main git@github-content:<owner>/<content-repo>.git <content-dir>
```

不要把私钥提交到任何仓库。

## 9. Images

文章图片统一放在内容仓库的 `assets/` 目录中。部署后图片不进入 release，而是生成到共享目录：

```text
<public-dir>/shared/assets/posts/
```

Nginx 直接服务 `/assets/posts/`，所以每次 Hugo 发布只处理 HTML、CSS、JS 和少量固定静态资源。这样可以避免每次复制大量图片。

文章封面由构建脚本自动生成：优先使用正文第一张图片；如果没有图片，就使用默认封面。

## 10. Comments And Views

评论和热度使用 Waline 自托管。推荐使用独立 MySQL 数据库或其他长期可维护数据库，不建议依赖即将停止服务的第三方存储，也不建议和其他历史归档库共用同一个 database。

站点侧：

```toml
[params.waline]
  enabled = true
  serverURL = "/waline"
```

说明：

- 文章页会更新热度。
- 首页和列表页只读取热度，不增加计数。
- 同一浏览器同一文章会用 `localStorage` 去重，刷新不重复增加。
- 评论审核由 Waline 服务端环境变量控制，例如 `COMMENT_AUDIT=true`。

Waline 环境配置应放在服务器本地，例如：

```text
/etc/waline.env
```

推荐数据库配置形态：

```env
MYSQL_DB=waline_db
MYSQL_PREFIX=wl_
```

不要提交数据库连接、JWT 或管理员凭据。

## 11. Math

站点使用自托管 KaTeX：

```text
static/vendor/katex/
static/js/math.js
```

支持：

```markdown
$inline$
$$ block $$
\( inline \)
\[ block \]
```

迁移文章里常见的 `x\_{k}` 这类转义会在前端渲染前做兼容处理。

## 12. Backup

备份目标不是保存所有生成物，而是保存不可重建的数据源。当前站点的数据可以分成三类：

```text
必须备份：
1. 内容仓库：Markdown 和文章 assets。
2. 站点仓库：Hugo 模板、脚本、部署模板。
3. Waline 独立数据库：评论、热度、后台用户。

可重建：
1. <public-dir>/shared/assets/posts/：由内容仓库文章 assets 生成。
2. <public-dir>/releases/：由 Hugo 重新构建。
3. <site-dir>/content/posts/：由 build_content.py 重新生成。
4. <site-dir>/public/ 和 <site-dir>/resources/。
```

### 12.1 Git Repositories

内容仓库和站点仓库应推送到 GitHub 或其他 Git 服务：

```bash
cd /path/to/content-repo
git status
git push

cd /path/to/laumy-site
git status
git push
```

内容仓库里的 `assets/` 是文章图片源文件。只要它们已经进 Git，`<public-dir>/shared/assets/posts/` 就可以在部署时重新生成。

### 12.2 Waline Database

Waline 备份示例：

```bash
set -a
. /etc/waline.env
set +a

mysqldump --single-transaction \
  -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DB" \
  wl_Comment wl_Counter wl_Users \
  | gzip > waline_$(date +%Y%m%d-%H%M%S).sql.gz
```

恢复 Waline：

```bash
set -a
. /etc/waline.env
set +a

gunzip -c waline_YYYYmmdd-HHMMSS.sql.gz \
  | mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DB"

sudo systemctl restart waline
```

### 12.3 Shared Static Files

共享静态目录只保存构建后的文章图片：

```text
<public-dir>/shared/assets/posts/   # 可重建，来自内容仓库 assets
```

它可以由内容仓库重新生成，通常不需要单独备份。如果希望完整保留线上静态资源，也可以备份整个 shared：

```bash
rsync -a --delete <public-dir>/shared/ /path/to/backup/shared/
```

### 12.4 Server Config

服务器配置不要提交 Git，但需要做离线备份：

```bash
sudo mkdir -p /path/to/backup/config
sudo cp /etc/waline.env /path/to/backup/config/
sudo cp /etc/laumy-deploy.env /path/to/backup/config/
sudo cp /etc/laumy-webhook.env /path/to/backup/config/
sudo cp /etc/nginx/conf.d/laumy*.conf /path/to/backup/config/ 2>/dev/null || true
sudo cp /etc/systemd/system/laumy*.service /path/to/backup/config/ 2>/dev/null || true
sudo cp /etc/systemd/system/waline.service /path/to/backup/config/ 2>/dev/null || true
```

这些文件可能包含数据库密码、webhook secret 或服务路径，只能放在私有备份位置。

### 12.5 Restore Order

迁移到新服务器时按这个顺序恢复：

1. 安装基础组件：Nginx、Hugo、Python、MySQL、Node/Waline。
2. clone 内容仓库到 `<content-dir>`。
3. clone 站点仓库到 `<site-dir>`。
4. 恢复 `/etc/waline.env`、`/etc/laumy-deploy.env`、`/etc/laumy-webhook.env`。
5. 创建 Waline 数据库和用户，并导入 Waline SQL。
6. 运行 `<site-dir>/scripts/deploy.sh`，重新生成 release 和 `shared/assets/posts/`。
7. 启动 Waline、webhook、Nginx。
8. 验证首页、历史文章 URL、文章图片、评论和热度。

### 12.6 Cleanup Policy

不需要长期备份：

- `<public-dir>/releases/`，可由源码重新构建。
- `<site-dir>/content/posts/`，可由内容仓库重新生成。
- `<site-dir>/public/` 和 `<site-dir>/resources/`。
- `<public-dir>/shared/assets/posts/`，在确认内容仓库 assets 完整后可清理重建。

确认 Waline 已稳定使用独立数据库后，可以清理旧库里遗留的 `wl_*` 表；删除前先保留一份 `waline_*.sql.gz`。

## 13. Security Checklist

公开仓库提交前检查：

```bash
rg -n "([0-9]{1,3}\\.){3}[0-9]{1,3}|r[o]ot@|/h[o]me/|WEBHOOK_SECRET[=].+|MYSQL_PASSWORD[=].+|J[W]T|PRIVATE[ ]KEY|BEGIN[ ]OPENSSH" .
git status --short
```

不得提交：

```text
.env
*.pem
*.key
*.sql
*.sql.gz
/etc/*.env
static/assets/
public/
resources/
content/posts/
```

## 14. Troubleshooting

检查 Hugo 构建：

```bash
hugo --source <site-dir> --destination /tmp/laumy-public --minify
```

检查部署日志：

```bash
sudo journalctl -u laumy-git-deploy.service -n 100 --no-pager
tail -100 /var/log/laumy-deploy/deploy.log
```

检查 webhook：

```bash
curl -fsS http://127.0.0.1:8789/deploy-hook/healthz
```

检查图片：

```bash
curl -I https://www.example.com/assets/posts/<hash>/<image>
```

检查 Waline：

```bash
curl -I https://www.example.com/waline/
sudo journalctl -u waline -n 100 --no-pager
```
