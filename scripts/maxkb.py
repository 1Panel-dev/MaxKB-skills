#!/usr/bin/env python3


import os
import sys
import json
import argparse
from pathlib import Path
from typing import Optional, Dict, Any
from urllib import parse, request
from urllib.error import HTTPError, URLError

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


# ── 辅助函数 ───────────────────────────────────────────────────────────
def die(message: str) -> None:
    """打印错误信息并退出"""
    print(f"错误: {message}", file=sys.stderr)
    sys.exit(1)


def info(message: str) -> None:
    """打印信息"""
    print(f":: {message}", file=sys.stderr)


def check_keys() -> None:
    """检查必需的 API 密钥"""
    if not MAXKB_TOKEN:
        die("未设置 MAXKB_TOKEN")
    if not MAXKB_DOMAIN:
        die("未设置 MAXKB_DOMAIN")


# ── API 封装（Header Key 鉴权）────────────────────────────────────────
def api_request(method: str, url: str, content_type: str, **kwargs) -> str:
    """执行 API 请求"""
    check_keys()

    headers = {
        "X-Access-Key": MAXKB_TOKEN,
        "Content-Type": content_type
    }

    # 合并用户提供的 headers（如果有）
    if 'headers' in kwargs:
        headers.update(kwargs.pop('headers'))

    params = kwargs.pop("params", None)
    data = kwargs.pop("data", None)

    if params:
        if isinstance(params, dict):
            query = parse.urlencode(params)
        else:
            query = str(params).lstrip("?")
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{query}"

    data_bytes = None
    if data is not None:
        if isinstance(data, bytes):
            data_bytes = data
        elif isinstance(data, dict):
            data_bytes = parse.urlencode(data).encode("utf-8")
        else:
            data_bytes = str(data).encode("utf-8")

    try:
        req = request.Request(
            url=url,
            data=data_bytes,
            headers=headers,
            method=method.upper()
        )
        with request.urlopen(req) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(e)
        die(f"请求失败: HTTP {e.code} {detail}")
    except URLError as e:
        die(f"请求失败: {e}")


def api(method: str, url: str, **kwargs) -> str:
    """执行 JSON API 请求"""
    return api_request(method, url, "application/json", **kwargs)


# ── CLI 处理 ──────────────────────────────────────────────────────────
def print_usage():
    """打印使用帮助"""
    usage_text = """
maxkb — MAXKB CLI 工具（X-Access-Key 模式）

使用方法:
  python3 maxkb.py <命令> [参数...]
"""
    print(usage_text)


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]



if __name__ == "__main__":
    main()
