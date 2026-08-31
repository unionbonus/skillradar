"""Public-source collectors with short timeouts; always return a usable payload offline."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Repository, RepoAnalysis

logger = logging.getLogger("skillradar")

CATALOG: dict[str, list[dict[str, Any]]] = {
    "mcp_server": [
        {"name": "modelcontextprotocol/servers", "url": "https://github.com/modelcontextprotocol/servers", "price": "开源", "ease": 4, "community": 5},
        {"name": "Anthropic MCP Inspector", "url": "https://github.com/modelcontextprotocol/inspector", "price": "开源", "ease": 4, "community": 4},
        {"name": "Cursor MCP marketplace", "url": "https://cursor.com", "price": "订阅捆绑", "ease": 5, "community": 5},
        {"name": "Claude Desktop MCP", "url": "https://www.anthropic.com/news/model-context-protocol", "price": "免费额度", "ease": 4, "community": 5},
        {"name": "Continue.dev MCP", "url": "https://github.com/continuedev/continue", "price": "开源", "ease": 3, "community": 4},
        {"name": "OpenAI Apps / GPTs tools", "url": "https://platform.openai.com", "price": "按量", "ease": 4, "community": 5},
    ],
    "claude_skill": [
        {"name": "anthropics/skills", "url": "https://github.com/anthropics/skills", "price": "开源", "ease": 4, "community": 5},
        {"name": "Claude Projects", "url": "https://claude.ai", "price": "订阅", "ease": 5, "community": 5},
        {"name": "OpenAI GPTs", "url": "https://chatgpt.com/gpts", "price": "订阅", "ease": 5, "community": 5},
        {"name": "Cursor Skills / Rules", "url": "https://cursor.com", "price": "订阅", "ease": 4, "community": 5},
        {"name": "LangChain Hub prompts", "url": "https://smith.langchain.com/hub", "price": "免费+付费", "ease": 3, "community": 4},
        {"name": "Flowise custom tools", "url": "https://github.com/FlowiseAI/Flowise", "price": "开源", "ease": 3, "community": 4},
    ],
    "langchain_tool": [
        {"name": "langchain-ai/langchain", "url": "https://github.com/langchain-ai/langchain", "price": "开源", "ease": 3, "community": 5},
        {"name": "LlamaIndex tools", "url": "https://github.com/run-llama/llama_index", "price": "开源", "ease": 3, "community": 5},
        {"name": "Haystack pipelines", "url": "https://github.com/deepset-ai/haystack", "price": "开源", "ease": 3, "community": 4},
        {"name": "Semantic Kernel plugins", "url": "https://github.com/microsoft/semantic-kernel", "price": "开源", "ease": 3, "community": 4},
        {"name": "CrewAI tools", "url": "https://github.com/crewAIInc/crewAI", "price": "开源", "ease": 3, "community": 4},
        {"name": "AutoGen tools", "url": "https://github.com/microsoft/autogen", "price": "开源", "ease": 3, "community": 4},
    ],
}

DEFAULT_CATALOG = CATALOG["claude_skill"]

POLICY_SOURCES = [
    {"title": "中国生成式人工智能服务管理暂行办法", "url": "https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm"},
    {"title": "EU AI Act", "url": "https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai"},
    {"title": "NIST AI RMF", "url": "https://www.nist.gov/itl/ai-risk-management-framework"},
    {"title": "Open-source software security (CISA)", "url": "https://www.cisa.gov/resources-tools/resources/securing-open-source-software-supply-chain"},
]


def collect(db: Session, repo: Repository, timeout: float = 4.0) -> dict[str, Any]:
    analysis = db.scalar(select(RepoAnalysis).where(RepoAnalysis.repository_id == repo.id))
    structure = (analysis.structure if analysis else {}) or {}
    motivation = (analysis.motivation if analysis else {}) or {}
    ftype = repo.fingerprint_type or structure.get("fingerprint_type") or "unknown"
    peers = _peer_repos(db, repo, ftype)
    catalog = list(CATALOG.get(ftype) or DEFAULT_CATALOG)
    issues = [] if os.environ.get("SKILLRADAR_OFFLINE") == "1" else _github_issues(repo, timeout)
    registry = {} if os.environ.get("SKILLRADAR_OFFLINE") == "1" else _registry_hints(repo, timeout)
    return {
        "repo": {
            "id": repo.id,
            "full_name": repo.full_name,
            "html_url": repo.html_url,
            "description": repo.description or "",
            "stargazers_count": repo.stargazers_count or 0,
            "forks_count": repo.forks_count or 0,
            "language": repo.language,
            "topics": repo.topics or [],
            "fingerprint_type": ftype,
        },
        "structure": structure,
        "motivation": motivation,
        "peers": peers,
        "catalog": catalog,
        "issues": issues,
        "registry": registry,
        "policy_sources": POLICY_SOURCES,
        "market_hints": _market_hints(ftype),
    }


def _peer_repos(db: Session, repo: Repository, ftype: str) -> list[dict[str, Any]]:
    stmt = select(Repository).where(Repository.id != repo.id).order_by(Repository.stargazers_count.desc()).limit(12)
    if ftype and ftype != "unknown":
        stmt = select(Repository).where(Repository.id != repo.id, Repository.fingerprint_type == ftype).order_by(
            Repository.stargazers_count.desc()
        ).limit(12)
    rows = list(db.scalars(stmt).all())
    return [
        {
            "name": r.full_name,
            "url": r.html_url,
            "stars": r.stargazers_count,
            "fingerprint_type": r.fingerprint_type,
            "description": (r.description or "")[:160],
        }
        for r in rows
    ]


def _github_issues(repo: Repository, timeout: float) -> list[dict[str, Any]]:
    url = (repo.html_url or "").rstrip("/")
    if "github.com/" not in url:
        return []
    api = url.replace("https://github.com/", "https://api.github.com/repos/") + "/issues?state=open&per_page=8"
    headers: dict[str, str] = {"Accept": "application/vnd.github+json", "User-Agent": "SkillRadar/0.5"}
    tokens = get_settings().token_list()
    if tokens:
        headers["Authorization"] = f"Bearer {tokens[0]}"
    data = _get_json(api, timeout, headers)
    if not isinstance(data, list):
        return []
    out = []
    for item in data[:8]:
        if not isinstance(item, dict) or item.get("pull_request"):
            continue
        out.append(
            {
                "title": item.get("title"),
                "url": item.get("html_url"),
                "comments": item.get("comments") or 0,
            }
        )
    return out


def _registry_hints(repo: Repository, timeout: float) -> dict[str, Any]:
    name = (repo.full_name or "").split("/")[-1].lower()
    hints: dict[str, Any] = {}
    npm = _get_json(f"https://registry.npmjs.org/{name}", timeout)
    if isinstance(npm, dict) and npm.get("name"):
        hints["npm"] = {"name": npm.get("name"), "url": f"https://www.npmjs.com/package/{npm.get('name')}"}
    pypi = _get_json(f"https://pypi.org/pypi/{name}/json", timeout)
    if isinstance(pypi, dict) and pypi.get("info"):
        info = pypi["info"]
        hints["pypi"] = {"name": info.get("name"), "url": info.get("package_url") or f"https://pypi.org/project/{name}/"}
    mcp = _get_json("https://registry.modelcontextprotocol.io/v0/servers?limit=5", timeout)
    if isinstance(mcp, dict):
        hints["mcp_registry"] = {"url": "https://registry.modelcontextprotocol.io", "hit": True}
    return hints


def _market_hints(ftype: str) -> dict[str, Any]:
    if ftype == "mcp_server":
        return {
            "segment": "模型上下文协议 / AI 工具连接层",
            "tam_note": "全球 AI 开发者工具市场（IDE 插件 + Agent 运行时）2025–2030 年公开摘要约百亿美元量级，MCP 为其中高速细分。",
            "cagr": "38%–52%（开发者工具公开摘要区间，非审计数字）",
            "sources": [
                "https://www.gartner.com/en/newsroom",
                "https://modelcontextprotocol.io",
            ],
        }
    if ftype == "langchain_tool":
        return {
            "segment": "LLM 编排框架与可插拔工具",
            "tam_note": "企业级 LLM 应用平台与编排层，公开行业摘要给出高双位数增长。",
            "cagr": "30%–45%",
            "sources": ["https://www.langchain.com", "https://arxiv.org/list/cs.AI/recent"],
        }
    return {
        "segment": "可复用 AI Skill / 提示技能包",
        "tam_note": "面向助手与 IDE 的可分发技能市场，随 Agent 工作流渗透而扩张。",
        "cagr": "35%–50%",
        "sources": [
            "https://www.anthropic.com/news",
            "https://trends.google.com/trends/explore?q=AI%20agent,MCP",
        ],
    }


def _get_json(url: str, timeout: float, headers: dict[str, str] | None = None) -> Any:
    if os.environ.get("SKILLRADAR_OFFLINE") == "1":
        return None
    try:
        with httpx.Client(timeout=min(timeout, 2.5), follow_redirects=True) as client:
            resp = client.get(url, headers=headers or {"User-Agent": "SkillRadar/0.5"})
            if resp.status_code >= 400:
                return None
            return resp.json()
    except Exception:
        return None
