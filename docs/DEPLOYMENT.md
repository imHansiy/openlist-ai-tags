# 部署、备份和卸载

## 方式一：整页网关（推荐首次部署）

附带 Compose 启动 AI 服务和 nginx 网关，复用已有 OpenList。nginx 把 `/ai/` 交给 AI 服务，其余路径继续交给 OpenList；仅在 HTML 中插入一个脚本标签，不改源文件或数据库配置。

填写 `.env` 后执行：

```bash
docker compose up -d --build
docker compose logs --tail 100 ai
```

默认网关 `127.0.0.1:8787`。现有 HTTPS 入口可反向代理到该端口。新入口域名涉及 OpenList 的 OAuth 回调、下载代理、站点 URL 时，仍需按 OpenList 本身规则配置；本项目不会自动改这些设置。

AI 容器非 root、只读根文件系统、临时目录 640 MiB、内存 2 GiB、CPU 配额 2、最多 128 个进程。默认并发 1。每个转码任务最多使用 512 MiB 无损中间视频和 23 MiB 压缩 MP4。增加并发或 `VIDEO_WORK_MAX_BYTES` 时同步提高临时目录和内存限额。SQLite 和密钥文件位于 Docker 命名卷 `ai-data`。这些限额用于视频压缩和调度服务，外部模型进程使用单独的计算资源。

未运行 Docker Engine 或未安装 Compose v2 时，`docker compose` 不会工作。当前开发机器就是此情况，需安装 / 启动 Docker Desktop 或在 Linux 服务器验证容器。

## 方式二：只在原域名增加 `/ai/`

适合不希望改变原域名入口的部署。AI 服务监听内网 `8787`，在现有反向代理中加入：

```nginx
location /ai/ {
    proxy_pass http://127.0.0.1:8787;
    proxy_read_timeout 1900s;
    client_max_body_size 64k;
}
```

此方式运行 Python 服务时保持 `AI_PROXY_ENABLED=false`；不要将 `/` 转发到 AI 服务。确认浏览器能访问同域名 `/ai/health` 后，在项目目录执行：

```bash
python scripts/integrate.py install
```

脚本使用 `.env` 中 OpenList 管理凭据，保留原有 `customize_body` 内容，只添加带边界标记的脚本，再回读校验。**没有同源路由时脚本拒绝安装**，避免把不可用功能注入生产页面。此方式和整页网关二选一即可。

如果服务的 `.env` 使用原 OpenList 直连地址，它通常没有 `/ai/health` 路由。为安装命令临时指定已配置同源路由的公开域名，例如 `OPENLIST_URL=https://files.example.com python scripts/integrate.py install`；服务本身继续使用 `.env` 中的直连地址，不要把上游指回 AI 网关。完整安装示例见 [README](../README.md#方案-apython--原域名接入)。

卸载脚本：

```bash
python scripts/integrate.py uninstall
```

## 本地模型

插件默认将压缩后的整片 MP4 通过 `video_url` 发送给模型。对仅接受 `image_url` 的服务，设置 `MODEL_NATIVE_VIDEO=false` 可启用抽帧兼容模式。签名下载地址始终留在 AI 服务端。

1B 和 35B-A3B 均按官方模型指南安装兼容 Transformers 版本；模型服务需加载对应 checkpoint。官方当前示例使用 `transformers[serving]>=5.18.0`；具体驱动 / torch / 解码库以官方部署文档为准。量化模型和 llama.cpp / vLLM 等服务必须实际支持该模型架构及所选的媒体输入格式。

本地模型不需要密钥时可留空；独立部署时给推理服务配置内网防火墙或认证。插件只控制自身并发，不负责模型的显存调度。

## 媒体白名单

服务自动信任配置的 OpenList **同 origin**，其余 CDN / 网盘媒体域名及每一跳重定向都必须匹配 `MEDIA_ALLOWED_HOSTS`，并解析到公网 IP。不要使用 `*`。遇到“媒体主机未加入白名单”时，根据错误中的主机名逐个添加可信域名并重启。

私有 NAS、内网网盘请通过 OpenList 本身的代理返回媒体；不要把整个内网加入泛域名信任。OpenList token 不会转发给第三方 CDN。

## 持久化与备份

- Python 默认数据目录 `data/`；可用 `AI_DATA_DIR` 指定绝对路径。
- `aitags.sqlite3` 存放结果、任务、扫描游标、人工覆盖、别名、常用标签、设置和历史。WAL 属于活跃数据库的一部分，不要在线直接复制单个 SQLite 主文件。
- 管理界面“下载数据备份”使用 SQLite backup API；也可运行 `python scripts/backup.py data/aitags.sqlite3 backup.sqlite3`。
- `model-secret.json` 为设置页写入的模型密钥，覆盖环境变量中的密钥。该文件及 `.env` **不在数据库备份中**，需另行安全保存；不要提交 Git。
- 恢复前停止服务，把经过完整性检查的备份放回原数据库位置，同时移除旧 `-wal` / `-shm` 文件，再启动。保留单独备份后操作。运行中的任务会重新入队，暂停 / 取消状态保留。
- AI 结果提交有幂等检查；进程恰好在模型响应后、SQLite 提交前崩溃时，重启可能再次消耗一次模型请求，无法保证外部推理严格 exactly-once。
- 首版没有自动清理历史和失效路径。大量定时扫描需监控数据卷大小；已删除文件仍可能保留索引，但即时权限 / 存在性检查使其无法显示给用户。

## 升级和移除

升级前备份，保持单副本，执行 `docker compose up -d --build`。新 OpenList 前端版本先在测试入口检查 `.list-item`、`.grid-item`、`.body`、`.solid-contextmenu` 和 token / 密码存储约定。

停止 `docker compose down` 不删除命名卷。方式一将公开入口恢复直连 OpenList 后即可停网关；方式二先卸载脚本再停 AI 服务。**不要使用 `down -v`，除非明确要删除全部标签数据。** 不需要删除或改动任何视频、网盘挂载或 OpenList 数据目录。

## 当前验证范围

本机 Python 网关和 FreeBSD 伴随部署已完成实际联调，在线模型与公网原生界面集成已有验证。Docker Engine 启动、Linux systemd 及其他驱动仍需在目标环境验收。请按 [README](../README.md) 从健康检查、同源接入到短视频识别逐项验证，历史与当前状态见 [验证记录](VERIFICATION.md)。
