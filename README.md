# SkillRadar

AI 基础插件商业情报与市场调研 **桌面应用**（v0.5 / Electron）。关键词扫描 GitHub，拆解结构，生成可溯源市场调研与商业拆解，并经飞书/企微/邮件推送简报。

完整说明见 [用户手册.md](./用户手册.md)。

```bash
./启动SkillRadar.sh                 # 双击：Electron 窗口
./scripts/install-desktop.sh        # 写入桌面图标
./scripts/build-electron.sh         # 打包 AppImage
./test.sh                           # 单测 + health 200
./scripts/AutoDeployToNAS.sh        # 轻量栈部署到极空间
docker compose up --build           # 本机 Postgres + Redis + Neo4j
```

健康检查：`GET /api/v1/health` → `"version":"0.5.0"`。
