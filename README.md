# SkillRadar

AI 基础插件 **商业情报与市场调研** 桌面应用（v0.5.3 / Electron）。多渠道扫描 GitHub / npm / PyPI / MCP Registry 等，深度拆解与市场调研后生成商业报告，支持报告库检索与飞书/企微/邮件订阅。

完整说明见 [用户手册.md](./用户手册.md)。

```bash
./启动SkillRadar.sh                 # 双击：Electron 窗口
./scripts/install-desktop.sh        # 写入桌面图标
./scripts/build-electron.sh         # 打包 AppImage
./test.sh                           # 单测 + health 200
./scripts/AutoDeployToNAS.sh        # 轻量栈部署到极空间
docker compose up --build           # Postgres + Redis + Neo4j + Qdrant + MinIO
```

健康检查：`GET /api/v1/health` → `"version":"0.5.3"`。
