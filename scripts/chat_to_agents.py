#!/usr/bin/env python3
"""
MaxKB Skill: 根据用户问题自动选择最合适的智能体并调用

流程：
  1. 获取所有已发布智能体（id / name / desc）
  2. 根据关键词匹配打分，选出最相关的智能体
  3. 创建会话并发送问题，解析 SSE 响应
  4. 返回所选智能体名称及其回答

入口函数: main(question: str) -> str
"""

import os
import json
import re
from urllib import request, parse
from urllib.error import HTTPError, URLError
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    # 如果没有 python-dotenv，提供简单的 .env 加载实现
    def load_dotenv(dotenv_path=None):
        if dotenv_path and os.path.exists(dotenv_path):
            with open(dotenv_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip().strip('"').strip("'")


# ── 路径配置 ──────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
ENV_FILE = SKILL_DIR / ".env"

# 加载环境变量
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

MAXKB_DOMAIN = os.environ.get("MAXKB_DOMAIN", "http://127.0.0.1:8080")
MAXKB_TOKEN = os.environ.get("MAXKB_TOKEN", "user-5beabebc2ea15371e44a4222ae4e5fe5")
MAXKB_WORKSPACE_ID = os.environ.get("MAXKB_WORKSPACE_ID", "default")


# ── 内部 HTTP 工具 ────────────────────────────────────────────────────

def _headers() -> dict:
    return {
        "Authorization": f"Bearer {MAXKB_TOKEN}",
        "Content-Type": "application/json",
    }


def _chat_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _get(path: str, token: str = None) -> dict:
    url = f"{MAXKB_DOMAIN}{path}"
    headers = _headers() if token is None else _chat_headers(token)
    req = request.Request(url=url, headers=headers, method="GET")
    try:
        with request.urlopen(req) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return json.loads(resp.read().decode(charset, errors="replace"))
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {path} 失败 HTTP {e.code}: {detail}") from e
    except URLError as e:
        raise RuntimeError(f"GET {path} 请求失败: {e}") from e


def _post_json(path: str, body: dict, token: str = None) -> dict:
    url = f"{MAXKB_DOMAIN}{path}"
    data = json.dumps(body).encode("utf-8")
    headers = _headers() if token is None else _chat_headers(token)
    req = request.Request(url=url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return json.loads(resp.read().decode(charset, errors="replace"))
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {path} 失败 HTTP {e.code}: {detail}") from e
    except URLError as e:
        raise RuntimeError(f"POST {path} 请求失败: {e}") from e


def _post_sse(path: str, body: dict, token: str) -> str:
    """
    发送 POST 请求并逐行解析 SSE（Server-Sent Events）流。
    收集所有 operate==true 的 content 片段，直到 is_end==true。
    """
    url = f"{MAXKB_DOMAIN}{path}"
    data = json.dumps(body).encode("utf-8")
    req = request.Request(url=url, data=data, headers=_chat_headers(token), method="POST")
    chunks = []
    try:
        with request.urlopen(req) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if event.get("operate") is True:
                    chunks.append(event.get("content", ""))
                    if event.get("is_end"):
                        break
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"SSE POST {path} 失败 HTTP {e.code}: {detail}") from e
    except URLError as e:
        raise RuntimeError(f"SSE POST {path} 请求失败: {e}") from e
    return "".join(chunks)


# ── 核心逻辑 ──────────────────────────────────────────────────────────

def get_published_agents() -> list:
    """返回所有已发布智能体，每条包含 id / name / desc。"""
    resp = _get(
        f"/admin/api/workspace/{MAXKB_WORKSPACE_ID}/application/1/100"
    )
    records = resp.get("data", {}).get("records", [])
    agents = [
        {
            "id": r["id"],
            "name": r.get("name", ""),
            "desc": r.get("desc", ""),
        }
        for r in records
        if r.get("is_publish") is True
    ]
    if not agents:
        raise RuntimeError("当前工作空间没有已发布的智能体")
    return agents


def _score(agent: dict, question: str) -> int:
    """
    计算问题与智能体的相关性得分。
    策略：
      - 提取中英文 token（英文按单词，中文按字符）
      - 统计智能体名称 + 描述中命中问题的 token 数
    名称命中权重是描述的 3 倍。
    """
    def tokenize(text: str) -> list:
        # 英文单词
        words = re.findall(r'[a-zA-Z0-9]+', text.lower())
        # 中文字符
        chars = re.findall(r'[\u4e00-\u9fff]', text)
        return words + chars

    q_tokens = set(tokenize(question))
    name_tokens = set(tokenize(agent["name"]))
    desc_tokens = set(tokenize(agent["desc"]))

    return len(q_tokens & name_tokens) * 3 + len(q_tokens & desc_tokens)


def select_agent(agents: list, question: str) -> dict:
    """从已发布智能体列表中选出与问题最相关的一个。"""
    if len(agents) == 1:
        return agents[0]
    return max(agents, key=lambda a: _score(a, question))


def chat_with_agent(agent_id: str, question: str) -> str:
    """
    对指定智能体发起一次对话并返回回答文本。
    """
    # 获取 access_token（匿名会话）
    token_resp = _get(f"/admin/api/workspace/{MAXKB_WORKSPACE_ID}/application/{agent_id}/access_token")
    access_token = token_resp.get("data", {}).get("access_token", "")

    # 创建会话
    chat_resp = _post_json(
        f"/chat/api/auth/anonymous",
        {"access_token": access_token},
    )
    token = chat_resp.get("data", '')
    if not token:
        raise RuntimeError(
            f"创建会话失败，响应：{json.dumps(chat_resp, ensure_ascii=False)}"
        )
    chat_id_resp = _get('/chat/api/open', token)
    chat_id = chat_id_resp.get("data", '')

    answer = _post_sse(
        f"/chat/api/chat_message/{chat_id}",
        {"message": question, 're_chat': False, 'stream': True},
        token
    )
    return answer


# ── 入口函数 ──────────────────────────────────────────────────────────

def main(question: str) -> str:
    """
    根据用户问题自动选择智能体并返回回答。

    参数:
        question: 用户的问题文本

    返回:
        JSON 字符串，包含：
          - agent_name: 被选中的智能体名称
          - answer:     智能体的回答内容
    """
    agents = get_published_agents()
    selected = select_agent(agents, question)
    answer = chat_with_agent(selected["id"], question)
    return json.dumps(
        {"agent_name": selected["name"], "answer": answer},
        ensure_ascii=False,
    )


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "你好，请介绍一下你自己"
    print(main(q))
