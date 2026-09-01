from __future__ import annotations

from pathlib import Path

from app.decomposer.parsers import LangChainParser, MCPServerParser
from app.scanner.fingerprints import detect_fingerprint, list_files, load_rules


def test_detect_claude_skill():
    assert detect_fingerprint(["SKILL.md", "main.py"]) == "claude_skill"
    assert detect_fingerprint([".claude/skills/foo/run.py"]) == "claude_skill"


def test_detect_mcp_and_langchain():
    assert detect_fingerprint(["mcp.json", "server.py"]) == "mcp_server"
    pkg = '{"dependencies":{"langchain":"1.0"}}'
    assert detect_fingerprint(["agents/foo.py"], pkg) == "langchain_tool"


def test_list_files_skips_git(tmp_path: Path):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    git = tmp_path / ".git"
    git.mkdir()
    (git / "config").write_text("x", encoding="utf-8")
    files = list_files(tmp_path)
    assert "a.py" in files
    assert all(not f.startswith(".git/") for f in files)


def test_load_rules_and_parsers(tmp_path: Path):
    cfg = tmp_path / "r.json"
    cfg.write_text('{"custom": {"files": ["X.md"]}}', encoding="utf-8")
    rules = load_rules(str(cfg))
    assert "custom" in rules
    mcp_root = Path(__file__).resolve().parent / "fixtures" / "sample-mcp"
    files = ["mcp.json", "server.py"]
    skills = MCPServerParser().parse(mcp_root, files)
    assert skills[0]["name"] == "demo-mcp"
    (tmp_path / "readme.md").write_text("hello", encoding="utf-8")
    lc = LangChainParser().parse(tmp_path, ["readme.md"])
    assert lc[0]["config"]["fingerprint"] == "langchain_tool"
