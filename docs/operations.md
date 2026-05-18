# laumy.tech Operations Guide

这份文档用于日常维护 `laumy.tech` 新站。仓库公开对外，文档中不要写服务器 IP、真实账号、密码、secret、私钥、数据库连接串。

## 1. System Overview

当前站点由两个 Git 仓库和一台服务器组成：

```text
content repo  -> 文章 Markdown 和文章 assets
site repo     -> Hugo 模板、样式、脚本、部署配置
server        -> 拉取两个仓库，构建 Hugo，Nginx 对外服务
```

默认服务器目录：

```text
<site-dir>       = /srv/laumy-site
<content-dir>    = /srv/laumy-notes-content
<public-dir>     = /var/www/laumy-static
```

线上入口：

```text
https://www.laumy.tech/
```

WordPress 已下线：

- Nginx 不再指向 WordPress 目录。
- PHP-FPM 已停止并禁用。
- `/wp-json/`、`/wp-login.php` 应返回 `404`。
- MySQL 仍保留运行，因为 Waline 使用独立数据库。

## 2. Daily Article Workflow

文章只维护在内容仓库。

```bash
cd <local-content-repo>
```

新增文章：

```text
04-AI/
  4.4-推理框架/
    新文章标题.md
    assets/
      figure.png
```

文章中引用图片：

```markdown
![说明](./assets/figure.png)
```

提交并推送：

```bash
git status
git add .
git commit -m "docs: add article title"
git push origin main
```

推送后 GitHub webhook 会通知服务器，服务器自动拉取内容并重新发布站点。

## 3. Site Code Workflow

网站代码只维护在站点仓库。

```bash
cd <local-site-repo>
```

常见修改：

- `layouts/`：页面模板。
- `static/css/main.css`：样式。
- `static/js/`：前端脚本。
- `scripts/`：构建和部署脚本。
- `deploy/`：Nginx、systemd、env 示例。
- `content/about.md`：关于页面。

提交并推送：

```bash
git status
git add .
git commit -m "fix: describe change"
git push origin main
```

服务器会同时检查内容仓库和站点仓库。有任一仓库变更，就会重新构建并发布。

## 4. Automatic Deploy

自动部署链路：

```text
GitHub push -> GitHub webhook -> server webhook service -> update_from_git.sh -> deploy.sh
```

服务器关键脚本：

```text
<site-dir>/scripts/update_from_git.sh
<site-dir>/scripts/deploy.sh
```

`update_from_git.sh` 做三件事：

1. 拉取内容仓库。
2. 拉取站点仓库。
3. 如果任一仓库有变更，调用 `deploy.sh`。

`deploy.sh` 做四件事：

1. 从内容仓库生成 Hugo `content/posts/`。
2. 同步文章图片到 `<public-dir>/shared/assets/posts/`。
3. Hugo 构建到 `<public-dir>/releases/<timestamp>`。
4. 切换 `<public-dir>/current` 软链接。

## 5. Manual Deploy

手动触发一次完整更新：

```bash
ssh <server> 'cd <site-dir> && ./scripts/update_from_git.sh'
```

只重新构建当前服务器已有代码：

```bash
ssh <server> 'cd <site-dir> && ./scripts/deploy.sh'
```

保留更多历史 release：

```bash
ssh <server> 'cd <site-dir> && KEEP_RELEASES=5 ./scripts/deploy.sh'
```

## 6. Health Checks

检查首页：

```bash
curl -I https://www.laumy.tech/
```

检查旧文章 URL：

```bash
curl -I 'https://www.laumy.tech/<post-id>.html/<legacy-slug>/'
```

检查 Waline：

```bash
curl -I https://www.laumy.tech/waline/
```

检查 webhook：

```bash
curl -fsS https://www.laumy.tech/deploy-hook/healthz
```

检查 WordPress 是否仍下线：

```bash
curl -I https://www.laumy.tech/wp-json/
curl -I https://www.laumy.tech/wp-login.php
```

期望结果：

```text
/                 -> 200
旧文章 URL         -> 200
/waline/          -> 200
/deploy-hook/...  -> {"ok": true, ...}
/wp-json/         -> 404
/wp-login.php     -> 404
```

## 7. Logs

部署日志：

```bash
ssh <server> 'tail -100 /var/log/laumy-deploy/deploy.log'
```

Webhook 服务：

```bash
ssh <server> 'systemctl status laumy-deploy-webhook --no-pager'
ssh <server> 'journalctl -u laumy-deploy-webhook -n 100 --no-pager'
```

Nginx：

```bash
ssh <server> 'nginx -t'
ssh <server> 'journalctl -u nginx -n 100 --no-pager'
```

Waline：

```bash
ssh <server> 'systemctl status waline --no-pager'
ssh <server> 'journalctl -u waline -n 100 --no-pager'
```

## 8. Rollback

查看 release：

```bash
ssh <server> 'ls -1 <public-dir>/releases'
```

切回指定 release：

```bash
ssh <server> 'ln -sfn <public-dir>/releases/<release-name> <public-dir>/current'
```

回滚后检查：

```bash
curl -I https://www.laumy.tech/
```

注意：回滚只切换静态站点 release，不回滚 Git 仓库，也不回滚 Waline 数据库。

## 9. Backup

必须备份：

1. 内容仓库：文章 Markdown 和文章 assets。
2. 站点仓库：模板、样式、脚本、部署配置。
3. Waline 数据库：评论、热度、后台用户。
4. 服务器配置：Nginx、systemd、env 文件。

不需要长期备份：

- `<public-dir>/releases/`
- `<public-dir>/shared/assets/posts/`
- `<site-dir>/content/posts/`
- `<site-dir>/public/`
- `<site-dir>/resources/`

这些都可以由 Git 仓库重新生成。

## 10. Waline Backup

Waline 使用独立数据库，不和历史 WordPress 数据库共用。

备份：

```bash
ssh <server>
set -a
. /etc/waline.env
set +a

mysqldump --single-transaction \
  -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DB" \
  wl_Comment wl_Counter wl_Users \
  | gzip > /root/waline_$(date +%Y%m%d-%H%M%S).sql.gz
```

恢复：

```bash
ssh <server>
set -a
. /etc/waline.env
set +a

gunzip -c /root/waline_YYYYmmdd-HHMMSS.sql.gz \
  | mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DB"

systemctl restart waline
```

## 11. Server Config Backup

配置文件可能包含 secret，只能进入私有备份位置，不要提交 Git。

建议备份：

```text
/etc/waline.env
/etc/laumy-deploy.env
/etc/laumy-webhook.env
/etc/nginx/sites-available/default
/etc/nginx/conf.d/*.conf
/etc/systemd/system/laumy*.service
/etc/systemd/system/waline.service
```

示例：

```bash
ssh <server>
mkdir -p /root/laumy-config-backup
cp /etc/waline.env /root/laumy-config-backup/
cp /etc/laumy-deploy.env /root/laumy-config-backup/
cp /etc/laumy-webhook.env /root/laumy-config-backup/
cp /etc/nginx/sites-available/default /root/laumy-config-backup/
cp /etc/nginx/conf.d/*.conf /root/laumy-config-backup/ 2>/dev/null || true
cp /etc/systemd/system/laumy*.service /root/laumy-config-backup/ 2>/dev/null || true
cp /etc/systemd/system/waline.service /root/laumy-config-backup/ 2>/dev/null || true
```

## 12. DNS And Certificate

DNS：

- `www.laumy.tech` 应解析到当前服务器。
- 如果希望裸域 `laumy.tech` 也可访问，需要给裸域添加 A 记录。
- Nginx 已配置裸域跳转到 `https://www.laumy.tech`，但前提是裸域 DNS 能解析到服务器。

证书：

- 需要确认证书覆盖 `www.laumy.tech` 和 `laumy.tech`。
- 定期检查证书有效期。
- 到期前必须完成续期或自动续期配置。

检查证书：

```bash
ssh <server> 'openssl x509 -in /etc/nginx/cert/www.laumy.tech.pem -noout -subject -issuer -dates -ext subjectAltName'
```

## 13. Common Troubleshooting

### 13.1 GitHub push 后没有自动发布

检查 webhook 服务：

```bash
ssh <server> 'systemctl status laumy-deploy-webhook --no-pager'
ssh <server> 'tail -100 /var/log/laumy-deploy/deploy.log'
```

手动跑更新脚本：

```bash
ssh <server> 'cd <site-dir> && ./scripts/update_from_git.sh'
```

### 13.2 页面 404

检查是否构建成功：

```bash
ssh <server> 'ls -l <public-dir>/current'
ssh <server> 'find <public-dir>/current -maxdepth 3 -name index.html | head'
```

检查旧 URL 是否在文章 frontmatter 中保留了 `url`。

### 13.3 图片 404

检查文章图片是否在内容仓库同级 `assets/` 目录。

```bash
grep -R "./assets/" <content-dir>
```

重新部署：

```bash
ssh <server> 'cd <site-dir> && ./scripts/deploy.sh'
```

### 13.4 评论或热度异常

检查 Waline：

```bash
curl -I https://www.laumy.tech/waline/
ssh <server> 'journalctl -u waline -n 100 --no-pager'
```

检查数据库环境文件是否存在：

```bash
ssh <server> 'test -f /etc/waline.env && echo ok'
```

## 14. Security Rules

不要提交：

- 服务器 IP 和 SSH 用户。
- 数据库密码。
- webhook secret。
- JWT。
- SSH 私钥。
- `.env` 文件。
- SQL 备份。
- 服务器真实私有备份路径。

提交公开仓库前检查：

```bash
rg -n "MYSQL_PASSWORD|WEBHOOK_SECRET|JWT|BEGIN OPENSSH|PRIVATE KEY|\\.sql|\\.pem|\\.key" .
```
