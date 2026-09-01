from __future__ import annotations

from typing import Any


def render_business_report(
    repo: dict[str, Any],
    structure: dict[str, Any],
    motivation: dict[str, Any],
    deep_dive: dict[str, Any],
    highlights: dict[str, Any],
    market: dict[str, Any],
) -> str:
    name = repo.get("full_name") or structure.get("full_name") or "Untitled Plugin"
    ftype = repo.get("fingerprint_type") or structure.get("fingerprint_type") or "unknown"
    stars = repo.get("stargazers_count") or 0
    arch = (deep_dive.get("architecture") or {})
    mods = deep_dive.get("modules") or []
    hl = highlights.get("highlights") or []
    md = market.get("market_definition") or {}
    pest = market.get("pest") or {}
    comps = market.get("competitors") or []
    pains = market.get("pain_points") or []
    mvp = market.get("mvp") or {}
    principles = "；".join(motivation.get("design_principles") or [])
    summary = (
        f"{name} 是一个 {ftype} 插件，当前热度 {stars} stars。"
        f"架构偏向{arch.get('label') or '模块化'}，适合作为 {md.get('category') or 'AI 基础插件'} 赛道的对标样本。"
    )
    mod_lines = "\n".join(f"- **{m.get('name')}**（{m.get('role')}，度 {m.get('degree')}）" for m in mods[:8]) or "- （待拆解）"
    hl_lines = "\n".join(
        f"### {h.get('title')}\n{h.get('summary')}\n- 影响力：{h.get('impact')} · 通用性：{h.get('generality')}\n"
        for h in hl
    ) or "- （暂无）"
    comp_lines = "\n".join(
        f"| {c.get('name')} | {c.get('positioning')} | {c.get('gap')} |" for c in comps[:8]
    )
    pain_lines = "\n".join(
        f"- **{p.get('pain')}**：{p.get('evidence')}（{p.get('data')}）" for p in pains
    )
    mermaid = (deep_dive.get("call_flow") or {}).get("mermaid") or "graph TD; A[Plugin] --> B[Runtime]"
    return f"""# 商业拆解报告 · {name}

> SkillRadar v0.5 自动生成，可在报告库中编辑后导出。

## 1. 执行摘要
{summary}

## 2. 插件概览
- 来源：`{repo.get('source') or 'github'}`
- 标识：`{repo.get('identifier') or name}`
- 指纹：`{ftype}`
- 热度：⭐ {stars}（Δ {repo.get('star_delta') or 0}）
- 许可证：{repo.get('license') or '未知'}
- 链接：{repo.get('html_url') or ''}

## 3. 架构设计
- 风格：{arch.get('label') or '—'}（`{arch.get('style')}`）
- 设计原则：{principles or '结构可扫描、接口显式'}

### 3.1 核心模块
{mod_lines}

### 3.2 调用链
```mermaid
{mermaid}
```

## 4. 设计亮点
{hl_lines}

## 5. 需求调研详细分析
### 5.1 宏观环境（PEST）
- 政治：{pest.get('political')}
- 经济：{pest.get('economic')}
- 社会：{pest.get('social')}
- 技术：{pest.get('technological')}

### 5.2 产业政策
{chr(10).join(f"- {p.get('name')}：{p.get('impact')}" for p in (market.get('policies') or []))}

### 5.3 竞品分析
| 竞品 | 定位 | 差异缺口 |
|------|------|----------|
{comp_lines}

市场规模启发式 TAM ≈ ${md.get('tam_usd') or 0:,.0f}，CAGR {float(md.get('cagr') or 0):.0%}。

### 5.4 市场痛点及论证
{pain_lines}

### 5.5 MVP 建议
- 目标用户：{', '.join(mvp.get('target_users') or [])}
- 功能范围：{', '.join(mvp.get('scope') or [])}
- 验证指标：{', '.join(mvp.get('metrics') or [])}

## 6. 商业机会
把「可扫描的插件结构」产品化：雷达发现 → 深度拆解 → 订阅简报，缩短从开源信号到采购决策的路径。

## 7. 应用场景建议
- 投资/赛道扫描周报
- 内部技术选型对照
- 插件生态运营的对标库

## 8. 风险评估
- 启发式市场数据需用公开报告校准
- 浅克隆无法覆盖私有依赖与运行时行为
- 许可证与供应链需人工复核

## 9. 结论与建议
优先验证 `{name}` 的扩展点是否可被自家运行时加载；若调用链清晰且许可证友好，可作为 MVP 对标实现。
"""


def report_summary(repo: dict[str, Any], market: dict[str, Any]) -> str:
    name = repo.get("full_name") or "plugin"
    md = market.get("market_definition") or {}
    return f"{name} · {md.get('label') or repo.get('fingerprint_type') or 'plugin'} 商业拆解摘要"
