# FreeBSD / Serv00 无 sudo 部署

不需要 Docker，也不在服务器运行模型。Python 伴随服务调用在线 ModelBest API，FFmpeg 负责压缩视频，字幕 OCR 可选。以下路径、端口均为示例，需要按自己的服务器调整。

## 前置条件

- 已安装并可运行 Python 3.12、FFmpeg / ffprobe 和 nginx；nginx 需要 HTTP sub 模块。
- 已有正常运行的 OpenList、管理员 API token，以及当前区域有效的模型 API key。
- 本项目随附的 `service.sh` 使用 FreeBSD `/usr/sbin/daemon`，默认 Python 位于 `.venv312`，nginx 位于 `/usr/local/sbin/nginx`。

部分 FreeBSD 环境没有可直接安装的 pydantic-core wheel，需要系统提供匹配的 Python 包或自行编译。没有 root 权限且缺少这些依赖时，先解决依赖环境；不能保证所有共享主机一键安装。

## 安装

```sh
git clone https://github.com/imHansiy/openlist-ai-tags.git "$HOME/apps/openlist-ai-tags"
cd "$HOME/apps/openlist-ai-tags"
python3.12 -m venv .venv312
.venv312/bin/python -m pip install .
cp .env.example .env
chmod 600 .env
mkdir -p runtime/client_temp runtime/proxy_temp data
chmod 700 runtime data
```

修改 `.env`：设置 `OPENLIST_URL` 为原 OpenList 直连地址，例如 `http://127.0.0.1:5244`；填写管理员 token、模型地址、模型名和密钥；根据实际媒体下载域名配置白名单。国内与海外平台的密钥不能混用，需要分别注册。

从模板生成用户目录下的 nginx 配置：

```sh
.venv312/bin/python - <<'PY'
from pathlib import Path
root=Path.cwd()
text=(root/'deploy/freebsd/nginx.conf.template').read_text()
text=text.replace('__ROOT__',str(root)).replace('__PORT__','43647')
# 将模板示例里的原 OpenList 端口改为自己的端口。
text=text.replace('127.0.0.1:43646','127.0.0.1:5244')
(root/'deploy/freebsd/nginx.conf').write_text(text)
PY
/usr/local/sbin/nginx -t -p "$PWD/" -c "$PWD/deploy/freebsd/nginx.conf"
sh deploy/freebsd/service.sh start
curl -f http://127.0.0.1:43647/ai/health
```

网关只监听本机 `43647`，AI 服务使用 `runtime/ai.sock`。将现有 HTTPS 虚拟主机的代理目标指向此网关；普通文件请求继续交给原 OpenList。切换之前备份原代理配置，切换之后验证登录、文件、播放和 `/ai/health`。

模板通过 HTML 中的 OpenList generator 标记注入脚本。如果当前前端 HTML 标记不同，可按 [部署说明](DEPLOYMENT.md) 使用 `scripts/integrate.py` 安装自定义 body 脚本；两种注入方式只选一种。

## 运行与恢复

```sh
sh deploy/freebsd/service.sh status
sh deploy/freebsd/service.sh restart-api
sh deploy/freebsd/service.sh restart-gateway
sh deploy/freebsd/service.sh disable-ai
sh deploy/freebsd/service.sh enable-ai
```

重启命令后检查健康状态；旧进程退出较慢时，等待退出后再次运行 `service.sh start`。识别期间优先等待任务完成再更新后端。若只发布静态 UI，可以备份后原子替换静态资源，避免重启。

可将以下行加入自己的 crontab（不要覆盖已有任务），把路径换为实际安装目录：

```cron
@reboot /bin/sh /home/USER/apps/openlist-ai-tags/deploy/freebsd/service.sh start
*/5 * * * * /bin/sh /home/USER/apps/openlist-ai-tags/deploy/freebsd/service.sh start
```

日志在 `runtime/api.log`、`runtime/gateway.log`、`runtime/nginx-error.log`。数据在 `data/aitags.sqlite3`，新模型密钥写入 `data/model-secret.json`。不要发布 `.env`、数据、日志、数据库备份或模型请求证据。

## 备份与卸载

通过 OpenList 管理后台「AI 视频标签」下载一致性数据库备份。备份不包含模型密钥；`.env` 和服务端密钥文件应另行私密备份。

停止 AI 而保留原文件服务时用 `disable-ai`，不要停止仍承接原站流量的 nginx。完全卸载前先移除自定义脚本（如安装过），把 HTTPS 入口恢复到原 OpenList，移除自己添加的 cron，再停止伴随进程。最后备份并移除项目目录；不修改 OpenList 的原挂载数据库。

## 验证范围

本项目已在一个无 sudo 的 FreeBSD 共享主机上完成在线 1B / 35B-A3B、OneDrive、整片压缩、字幕联合识别和原界面集成。其他主机的依赖与资源限额仍需实测，视频理解仍可能出现细节误判，见 [实际验证记录](VERIFICATION.md)。
