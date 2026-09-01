from __future__ import annotations

from typing import Any


CATEGORY = {
    "claude_skill": ("AI Skill 分发与复用", "Claude / Agent 技能包"),
    "mcp_server": ("模型上下文协议工具", "MCP Server"),
    "langchain_tool": ("编排框架工具生态", "LangChain Tool"),
}


def analyze_market(structure: dict[str, Any], repo: dict[str, Any] | None = None) -> dict[str, Any]:
    repo = repo or {}
    ftype = structure.get("fingerprint_type") or repo.get("fingerprint_type") or "unknown"
    name = structure.get("full_name") or repo.get("full_name") or "plugin"
    stars = int(repo.get("stargazers_count") or 0)
    category, label = CATEGORY.get(ftype, ("AI 基础插件", "通用插件"))
    tam = 1.2e9 if ftype == "mcp_server" else 8.0e8
    cagr = 0.34 if stars < 500 else 0.28
    competitors = _competitors(ftype, name)
    pains = [
        {
            "pain": "插件质量与接口不统一，选型成本高",
            "evidence": "雷达扫描中同类项目指纹混杂、文档口径不一",
            "data": f"样本热度星标 {stars}",
        },
        {
            "pain": "缺少咨询级拆解，商业决策只能看 README",
            "evidence": "开源仓库很少同时给出架构、亮点与竞品对照",
            "data": "SkillRadar 报告库填补该空白",
        },
        {
            "pain": "订阅与推送散落在聊天群，无法沉淀",
            "evidence": "飞书/企微机器人多为人工转发",
            "data": "周期简报可量化送达",
        },
    ]
    pest = {
        "political": "开源许可与数据出境政策影响企业采用节奏",
        "economic": "企业把 AI 插件当降本杠杆，付费意愿向可审计工具集中",
        "social": "开发者社区用星标/下载量做信任代理",
        "technological": "MCP / Skill 清单正在成为互操作标准",
    }
    policies = [
        {"name": "生成式人工智能服务管理", "impact": "面向公众的插件需可追溯与内容安全"},
        {"name": "开源软件供应链", "impact": "依赖与许可证需进入采购评估"},
    ]
    mvp = {
        "target_users": ["AI 产品经理", "解决方案架构师"],
        "scope": ["指纹扫描", "结构拆解", "一页商业报告"],
        "metrics": ["从发现到报告 < 10 分钟", "简报送达成功率 > 95%"],
    }
    return {
        "market_definition": {
            "category": category,
            "label": label,
            "subject": name,
            "tam_usd": tam,
            "cagr": cagr,
            "note": "启发式规模，配置 LLM 后可润色为引用公开报告的表述",
        },
        "pest": pest,
        "policies": policies,
        "competitors": competitors,
        "pain_points": pains,
        "mvp": mvp,
        "source": "heuristic",
    }


def _competitors(ftype: str, name: str) -> list[dict[str, Any]]:
    pools = {
        "mcp_server": [
            ("modelcontextprotocol/servers", "官方示例集", "覆盖广、生产封装弱"),
            ("anthropic mcp filesystem", "文件系统参考实现", "场景单一"),
            ("continue.dev", "IDE 助手", "偏编辑器而非独立 Server"),
            ("cursor mcp", "编辑器内置", "不可独立部署"),
            ("open-webui tools", "聊天前端工具", "协议不同"),
        ],
        "claude_skill": [
            ("anthropics/skills", "官方技能示例", "规范源头"),
            ("awesome-claude-skills", "清单聚合", "缺少深度拆解"),
            ("OpenClaw skills", "社区技能", "质量参差"),
            ("custom GPTs", "封闭分发", "不可扫描"),
            ("langchain hub", "提示词中心", "不是 Skill 包"),
        ],
        "langchain_tool": [
            ("langchain-ai/langchain", "框架本体", "重、学习曲线陡"),
            ("langgraph", "图编排", "更偏工作流"),
            ("crewai", "多智能体", "抽象不同"),
            ("haystack", "管道", "检索向"),
            ("semantic-kernel", "微软生态", "企业向"),
        ],
    }
    rows = pools.get(ftype, pools["claude_skill"])
    out = []
    for i, (comp, pos, gap) in enumerate(rows):
        out.append(
            {
                "name": comp,
                "positioning": pos,
                "gap": gap,
                "overlap_with": name,
                "rank": i + 1,
            }
        )
    return out
