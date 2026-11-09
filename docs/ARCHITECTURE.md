# 架构与兼容性依据

## 组成

浏览器仍加载 OpenList 自己的 SolidJS 前端。附加 `ai.js` 在 `.list-item` / `.grid-item` 内放紧凑 AI 标记，在悬浮卡片展示简介与标签，在 `.solid-contextmenu` 追加操作；管理选项位于原 `/@manage` 内容区，首页没有管理工具栏。原生搜索请求保持原样，同时补充经权限校验的 AI 匹配。图片视图复用原目录响应补充视频卡片。所有文件原链接、播放器、挂载、原 API 保留，服务不可用时原文件管理继续运行。

同源 `/ai/api/` 由 FastAPI 提供，SQLite WAL 存任务和标签。后台一个目录线程、最多四个视频线程，默认只启用一个视频线程。扫描目录和分页游标持久化，活跃路径唯一索引防止重复排队。OS 文件锁阻止多个调度器同时处理同一数据库。

取视频时使用扫描管理员调用 OpenList `/api/fs/get` 获取短期媒体地址。媒体限流网关只绑定 127.0.0.1，随机令牌路径供 FFmpeg 使用；检查域名与重定向，限制转发字节 / 总时长。FFmpeg 禁用任意协议，只允许 HTTP/TCP 并限制普通文件 demuxer，禁止播放列表递归读取。默认提交整段压缩 MP4，可结合字幕时间轴和有限补充画面；仅在显式兼容模式下抽帧。文件名可作为电影片名候选，但不是人物关系证据；模型不接收云盘认证信息和签名下载地址。压缩及字幕证据可按私有缓存策略短期保留，见[视频处理说明](VIDEO_PIPELINE.md)。

模型返回 JSON 经 Pydantic 校验，时间范围检查、标签去重后入库。开始和提交前均检查视频指纹，取消后不提交结果。模型不合规输出不会伪造成功。结果可包含摘要、标签、实际文字、时间段、不确定性和抽样证据。

## 权限与身份

浏览器只携带自己的 OpenList token。每次 API 先调用原 `/api/me`，结果读取再以**相同 token** 调用原 `/api/fs/get`。管理员扫描凭据仅用于后台发现和读取媒体，不能为普通用户授权读取结果。

存储键为全局物理路径；根据用户 `base_path` 映射相对路径，再调用原 API 校验。限制请求数量、输入长度、路径遍历和请求体大小，不设置跨域 CORS，不把第三方原始错误或签名地址输出到浏览器。管理 API 要求 OpenList `role=2`；不支持用户自定义的共享链接 `/@s` 场景。

搜索先查候选，再逐文件验证权限，返回已授权的项；不返回全局计数或标签聚合。搜索游标是数据库候选位置，不是全站可访问数量。修改 / 撤销权限后下次服务端查询重新检查；已经显示在客户端的内容无法被事后撤回。

AI 标签、人工标签和隐藏 AI 标签分别存储。别名按单级规范化映射展示，不做不可逆物理合并；取消别名可以恢复原始词。可靠 full-file SHA1 / SHA256 / MD5 与大小构成复用标识，没有哈希就不冒险迁移结果。

## 官方源码 / 文档依据（2026-11-05）

- [OpenList 后端](https://github.com/OpenListTeam/OpenList)，研究提交 `ef5d8c8d41ce3b300f7d7c47803e9d5082c9f64f`：`server/handles/fsread.go`、`server/middlewares/auth.go`、`internal/model/user.go`、`server/handles/setting.go`、`server/router.go`。
- [OpenList 前端](https://github.com/OpenListTeam/OpenList-Frontend)，研究提交 `e2cff387a213d9d555e1889fef73e396fc14d52a`：`src/pages/home/folder/ListItem.tsx`、`GridItem.tsx`、`context-menu.tsx`、`src/utils/customize.ts`、`src/utils/request.ts`、`src/store/obj.ts`。
- [MiniCPM-V 4.7 模型指南](https://github.com/OpenBMB/MiniCPM-V/blob/main/docs/minicpm_v4dot7_en.md)：1B / 35B-A3B、Transformers 本地服务、多图像 / 视频能力。
- [ModelBest 官方 API](https://github.com/OpenBMB/MiniCPM-V/blob/main/docs/api.md)：`https://api.modelbest.cn/v1`、Bearer 认证、4.7 两种模型名、`image_url` / `video_url`。

真实部署已完成 DOM 与接口联调，首轮记录包括 OpenList v4.2.3。上述官方源码还完成了代码层兼容分析，但不代表每个上游版本均已构建并运行验收。项目不是 OpenList 官方维护插件，前端 DOM 属于适配边界；升级需要回归测试，后续界面验证见[实际验证记录](VERIFICATION.md)。
