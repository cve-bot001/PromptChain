#!/usr/bin/env python3
"""终端聊天客户端：支持流式输出和历史上下文自动续接。"""

import os
import sys
import json
import signal
import openai
from datetime import datetime


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


def signal_handler(sig, frame):
    print("\n\n已退出聊天。再见!")
    sys.exit(0)


def stream_chat(messages, model, base_url, api_key):
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    data = {
        "model": model,
        "messages": messages,
        "stream": True,
        "max_tokens": int(os.environ.get("MAX_TOKENS", 2000)),
        "temperature": 0.7,
    }

    import urllib.request

    full_content = ""
    req = urllib.request.Request(
        url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        response = urllib.request.urlopen(req)
        buffer = ""
        while True:
            chunk = response.read(1)
            if not chunk:
                break
            chunk = chunk.decode("utf-8")
            buffer += chunk
            if buffer.endswith("\n"):
                buffer = buffer.strip()
                if buffer.startswith("data: "):
                    data_str = buffer[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(data_str)
                        delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_content += content
                            print(content, end="", flush=True)
                    except (json.JSONDecodeError, IndexError, KeyError, TypeError):
                        pass
                buffer = ""
    except Exception as e:
        print(f"\n流式输出错误: {e}")
        return None
    print()
    return full_content


def chat():
    project_root = get_project_root()
    load_env_file(os.path.join(project_root, ".env"))

    openai.api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("API_KEY", "")
    openai.api_base = os.environ.get("BASE_URL", "http://127.0.0.1:8080/v1")
    model = os.environ.get("MODEL", "") or os.environ.get(
        "OPENAI_MODEL", "gpt-3.5-turbo"
    )

    if not openai.api_key:
        print("错误: 缺少 API_KEY，请检查 .env 文件")
        return

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"终端聊天客户端已启动 (模型: {model})")
    print("输入消息开始聊天，输入 /clear 清除历史，输入 /exit 或 Ctrl+C 退出")
    print("-" * 50)

    messages = []
    today = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
    messages.append(
        {
            "role": "system",
            "content": f"你现在是一个专业的AI助手。请根据用户的问题给出有用的回答。今天的日期和时间是: {today}。",
        }
    )

    while True:
        try:
            user_input = input("\n你: ").strip()
        except EOFError:
            print("\n\n已退出聊天。再见!")
            break

        if not user_input:
            continue
        if user_input == "/exit":
            print("已退出聊天。再见!")
            break
        if user_input == "/clear":
            messages = [
                {
                    "role": "system",
                    "content": f"你现在是一个专业的AI助手。请根据用户的问题给出有用的回答。今天的日期和时间是: {today}。",
                }
            ]
            print("对话历史已清除。")
            continue

        messages.append({"role": "user", "content": user_input})

        print("\nAI: ", end="", flush=True)
        content = stream_chat(messages, model, openai.api_base, openai.api_key)

        if content:
            messages.append({"role": "assistant", "content": content})


if __name__ == "__main__":
    chat()
