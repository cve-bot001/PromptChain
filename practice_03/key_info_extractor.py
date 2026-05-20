#!/usr/bin/env python3
"""关键信息提取器 - 从聊天记录中提取5W关键信息并记录到本地文件。

功能：
- 从用户聊天记录中提取关键信息
- 按照5W规则：Who, What, When, Where, Why
- 增量更新到 chat_log\log.txt
"""

import os
import json
import re
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


def load_env_file(env_path):
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def get_project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_api_url(base_url, path):
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def build_headers(api_key):
    headers = {"Content-Type": "application/json"}
    if api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    return headers


def call_openai(messages, base_url, api_key, model=None):
    url = get_api_url(base_url, "chat/completions")
    headers = build_headers(api_key)
    data = {
        "messages": messages,
        "max_tokens": int(os.environ.get("MAX_TOKENS", 2000)),
        "temperature": 0.7,
    }
    if model:
        data["model"] = model

    try:
        req = Request(
            url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST"
        )
        with urlopen(req) as response:
            raw = response.read().decode("utf-8")
            result = json.loads(raw)
            if result.get("choices"):
                return result["choices"][0].get("message", {}).get("content", "")
    except Exception as e:
        print(f"LLM调用错误: {e}")
    return None


def extract_key_info(user_messages, base_url, api_key, model):
    if not user_messages:
        return None

    history = "\n".join(f"{i + 1}. {msg}" for i, msg in enumerate(user_messages))

    prompt = f"""请从以下用户聊天记录中提取关键信息，按照5W规则提取：

{history}

请以JSON格式输出，字段说明：
- who: 谁（用户身份或角色）
- what: 做了什么事
- when: 什么时候（可选）
- where: 在何处（可选）
- why: 为什么要做这个事（可选）

只提取用户的消息内容，不需要提取AI回复。

请直接输出JSON数组格式，不要有其他文字。例如：
[
  {{"who": "用户", "what": "询问如何配置本地模型", "when": "", "where": "", "why": ""}},
  {{"who": "用户", "what": "报告流式输出错误", "when": "2024年", "where": "", "why": "解决问题"}}
]"""

    messages = [
        {
            "role": "system",
            "content": "你是一个专业的关键信息提取助手。请从用户聊天记录中提取5W关键信息。只提取用户的消息内容，按JSON数组格式输出。",
        },
        {"role": "user", "content": prompt},
    ]

    result = call_openai(messages, base_url, api_key, model)
    return result


def ensure_log_dir():
    project_root = get_project_root()
    log_dir = os.path.join(project_root, "chat_log")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    return log_dir


def append_to_log(key_infos):
    log_dir = ensure_log_dir()
    log_file = os.path.join(log_dir, "log.txt")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n{'=' * 50}\n")
        f.write(f"提取时间: {timestamp}\n")
        f.write(f"{'=' * 50}\n")

        for info in key_infos:
            who = info.get("who", "")
            what = info.get("what", "")
            when_info = info.get("when", "")
            where = info.get("where", "")
            why = info.get("why", "")

            f.write(f"Who: {who}\n")
            f.write(f"What: {what}\n")
            if when_info:
                f.write(f"When: {when_info}\n")
            if where:
                f.write(f"Where: {where}\n")
            if why:
                f.write(f"Why: {why}\n")
            f.write("-" * 30 + "\n")


def parse_json_result(text):
    text = text.strip()
    if text.startswith("```"):
        start = text.find("```")
        end = text.rfind("```")
        if start != -1 and end != -1 and end > start:
            text = text[start + 3 : end].strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()

    if text.startswith("["):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return []


def run_extractor(user_messages):
    project_root = get_project_root()
    load_env_file(os.path.join(project_root, "practice_03", ".env"))

    base_url = os.environ.get("BASE_URL")
    api_key = os.environ.get("API_KEY") or "not-needed"
    model = os.environ.get("MODEL") or "本地模型"

    if not user_messages:
        print("没有用户消息需要提取")
        return

    print(f"正在从{len(user_messages)}条用户消息中提取关键信息...")

    result = extract_key_info(user_messages, base_url, api_key, model)
    if not result:
        print("提取失败")
        return

    key_infos = parse_json_result(result)
    if not key_infos:
        print("解析结果失败")
        return

    append_to_log(key_infos)
    print(f"已提取{len(key_infos)}条关键信息并记录到chat_log\\log.txt")


if __name__ == "__main__":
    test_messages = [
        "你好",
        "我需要配置本地llama.cpp模型",
        "模型输出没有正确显示",
    ]
    run_extractor(test_messages)
