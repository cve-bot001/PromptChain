#!/usr/bin/env python3
"""带聊天记录自动摘要功能的终端聊天客户端。

功能：
- 支持流式输出和历史上下文自动续接
- 对话超过5轮时自动触发摘要压缩
- 上下文超过3k tokens时自动触发摘要压缩
- 支持 /search 或查找聊天历史时搜索log.txt
"""

import os
import sys
import json
import signal
import math
import re
import threading
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from anythingllm_query import anythingllm_query as query_workspace


FUNCTIONS = [
    {
        "name": "search_chat_history",
        "description": "搜索聊天历史记录，从log.txt中查找相关信息",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "搜索关键词"}},
            "required": ["query"],
        },
    },
    {
        "name": "anythingllm_query",
        "description": "查询AnythingLLM工作区中的文档仓库/文件仓库内容。当用户提到'文档仓库'、'文件仓库'、'仓库'并想要查询里面的内容时使用此工具",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "要查询的内容"}},
            "required": ["query"],
        },
    },
]


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


def count_tokens(text):
    return math.ceil(len(text) / 4)


def get_api_url(base_url, path):
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def build_headers(api_key):
    headers = {"Content-Type": "application/json"}
    if api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    return headers


def call_openai_stream(messages, base_url, api_key, model=None):
    url = get_api_url(base_url, "chat/completions")
    headers = build_headers(api_key)
    data = {
        "messages": messages,
        "stream": True,
        "max_tokens": int(os.environ.get("MAX_TOKENS", 2000)),
        "temperature": 0.7,
    }
    if model:
        data["model"] = model

    full_content = ""
    req = Request(
        url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urlopen(req) as response:
            buffer = b""
            while True:
                chunk = response.read(4096)
                if not chunk:
                    break
                buffer += chunk
                text = buffer.decode("utf-8", errors="replace")
                buffer = b""
                if "\n" in text:
                    lines = text.split("\n")
                    for line in lines[:-1]:
                        line = line.strip()
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk_data = json.loads(data_str)
                                delta = chunk_data.get("choices", [{}])[0].get(
                                    "delta", {}
                                )
                                content = delta.get("content", "")
                                if content:
                                    full_content += content
                                    print(content, end="", flush=True)
                            except (
                                json.JSONDecodeError,
                                IndexError,
                                KeyError,
                                TypeError,
                            ):
                                pass
                    buffer = lines[-1].encode("utf-8")
    except Exception as e:
        print(f"\n流式输出错误: {e}")
        return None
    print()
    return full_content


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


def should_summarize(messages, max_turns=5, max_tokens=3000):
    non_system = [m for m in messages if m.get("role") != "system"]
    if len(non_system) > max_turns:
        return True

    total_text = "".join(m.get("content", "") for m in messages if m.get("content"))
    if count_tokens(total_text) > max_tokens:
        return True

    return False


def search_chat_history(query):
    project_root = get_project_root()
    log_file = os.path.join(project_root, "chat_log", "log.txt")

    if not os.path.exists(log_file):
        return {"error": "聊天历史记录文件不存在"}

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()

        if not query.strip():
            return {"content": content[:5000]}

        query_lower = query.lower()
        lines = content.split("\n")
        results = []
        for i, line in enumerate(lines):
            if query_lower in line.lower():
                context = lines[max(0, i - 2) : i + 3]
                results.append("\n".join(context))

        if results:
            return {"query": query, "results": "\n---\n".join(results[:10])}
        else:
            return {"query": query, "results": "未找到匹配结果"}
    except Exception as e:
        return {"error": str(e)}


def call_openai_with_functions(messages, base_url, api_key, model=None):
    url = get_api_url(base_url, "chat/completions")
    headers = build_headers(api_key)
    data = {
        "messages": messages,
        "functions": FUNCTIONS,
        "function_call": "auto",
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
            return json.loads(raw)
    except Exception as e:
        return {"error": str(e)}


def parse_tool_call(text):
    if not text:
        return None

    patterns = [
        r"<\|tool_call>call:\s*(\w+)\(([^)]+)\)",
        r"search_chat_history\(['\"]?([^'\"]+)['\"]?\)",
        r"anythingllm_query\(['\"]?([^'\"]+)['\"]?\)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1)
            args = match.group(2) if match.lastindex >= 2 else ""
            return {
                "name": name,
                "arguments": json.dumps({"query": args.strip().strip('"').strip("'")}),
            }

    if "search_chat_history" in text:
        match = re.search(r'"query"\s*:\s*"([^"]+)"', text)
        if match:
            return {
                "name": "search_chat_history",
                "arguments": json.dumps({"query": match.group(1)}),
            }

    if "anythingllm_query" in text:
        match = re.search(r'"query"\s*:\s*"([^"]+)"', text)
        if match:
            return {
                "name": "anythingllm_query",
                "arguments": json.dumps({"query": match.group(1)}),
            }

    return None


def execute_search(query, base_url, api_key, model):
    from key_info_extractor import call_openai as llm_call

    project_root = get_project_root()
    log_file = os.path.join(project_root, "chat_log", "log.txt")

    if not os.path.exists(log_file):
        return "聊天历史记录文件不存在"

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return f"读取失败: {e}"

    prompt = f"""请从以下聊天历史记录中查找与 "{query}" 相关的信息：

{content[:8000]}

请返回找到的相关内容，如果没有找到请说明未找到。"""

    messages = [
        {
            "role": "system",
            "content": "你是一个聊天历史搜索助手。请在给定的历史记录中查找相关信息。",
        },
        {"role": "user", "content": prompt},
    ]

    result = llm_call(messages, base_url, api_key, model)
    return result or "搜索失败"


def summarize_conversation(messages, base_url, api_key, model):
    non_system = [
        m
        for m in messages
        if m.get("role") in ["user", "assistant"] and m.get("content")
    ]
    total = len(non_system)
    if total < 2:
        return None, []

    split_idx = int(total * 0.7)
    if split_idx < 1:
        return None, []

    user_messages = [
        m["content"] for m in non_system[:split_idx] if m["role"] == "user"
    ]

    first_part = non_system[:split_idx]
    last_part = non_system[split_idx:]

    first_history = []
    for m in first_part:
        role = "用户" if m["role"] == "user" else "AI"
        first_history.append(f"{role}: {m['content']}")

    last_history = []
    for m in last_part:
        role = "用户" if m["role"] == "user" else "AI"
        last_history.append(f"{role}: {m['content']}")

    prompt = f"""请将以下聊天记录（前75%的内容）压缩成简短的摘要，保留关键信息和用户需求：

{"=" * 40}
"""

    summary_messages = [
        {
            "role": "system",
            "content": "你是一个专业的聊天记录摘要助手。请简洁地压缩聊天内容，保留关键信息和用户意图。",
        },
        {"role": "user", "content": prompt + "\n".join(first_history)},
    ]

    print("\n[正在进行聊天记录摘要（前75%内容压缩 + 后30%保留）...]")
    summary = call_openai(summary_messages, base_url, api_key, model)

    if summary and last_history:
        final_content = f"""【聊天记录摘要】
{summary}

【最近对话保留】（后30%内容：
{chr(10).join(last_history)}
）"""
        return final_content, user_messages

    return summary, user_messages


def background_summarize(messages, base_url, api_key, model, today):
    try:
        summary, user_msgs = summarize_conversation(messages, base_url, api_key, model)
        if summary and user_msgs:
            try:
                import key_info_extractor

                key_info_extractor.run_extractor(user_msgs)
            except Exception as e:
                print(f"\n[后台关键信息提取失败: {e}]")
            return summary
    except Exception as e:
        print(f"\n[后台摘要失败: {e}]")
    return None


def signal_handler(sig, frame):
    print("\n\n已退出聊天。再见!")
    sys.exit(0)


def chat():
    project_root = get_project_root()
    load_env_file(os.path.join(project_root, ".env"))

    base_url = os.environ.get("BASE_URL")
    if not base_url:
        print("错误: 缺少 BASE_URL，请检查 .env 文件")
        return

    api_key = os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        api_key = "not-needed"
        print("注意: 未配置API_KEY，使用本地llama.cpp无需API_KEY")

    model = os.environ.get("MODEL") or os.environ.get("OPENAI_MODEL", "")
    if not model:
        model = "本地模型"
        print("注意: 未配置MODEL，将使用本地模型")

    max_context_tokens = int(os.environ.get("CONTEXT_LENGTH", 3000) or 3000)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"终端聊天客户端已启动 (模型: {model})")
    print(f"API地址: {base_url}")
    print(f"触发摘要条件: 对话超过{max_context_tokens}tokens或超过5轮")
    print("输入消息开始聊天，输入 /clear 清除历史，输入 /exit 或 Ctrl+C 退出")
    print("-" * 50)

    messages = []
    today = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
    messages.append(
        {
            "role": "system",
            "content": f"""你现在是一个专业的AI助手。请根据用户的问题给出有用的回答。今天的日期和时间是: {today}。

可用工具：
1. search_chat_history - 搜索本地聊天历史记录
2. anythingllm_query - 查询AnythingLLM文档仓库/文件仓库中的内容。当用户提到"文档仓库"、"文件仓库"、"仓库"并想要查询里面的内容时，必须使用此工具。""",
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
                    "content": f"""你现在是一个专业的AI助手。请根据用户的问题给出有用的回答。今天的日期和时间是: {today}。

可用工具：
1. search_chat_history - 搜索本地聊天历史记录
2. anythingllm_query - 查询AnythingLLM文档仓库/文件仓库中的内容。当用户提到"文档仓库"、"文件仓库"、"仓库"并想要查询里面的内容时，必须使用此工具。""",
                }
            ]
            print("对话历史已清除。")
            continue

        is_search = (
            user_input.startswith("/search")
            or "查找聊天历史" in user_input
            or "搜索历史" in user_input
        )

        search_result = None
        if is_search:
            query = user_input.replace("/search", "").strip() or user_input
            print(f"\n[正在搜索聊天历史: {query}]")
            search_result = execute_search(query, base_url, api_key, model)
            print(f"[搜索完成]")

        messages.append({"role": "user", "content": user_input})

        print("\nAI: ", end="", flush=True)

        if search_result and "未找到" not in search_result:
            messages.append(
                {"role": "system", "content": f"【搜索结果】{search_result}"}
            )

        content = call_openai_stream(messages, base_url, api_key, model)

        if content:
            messages.append({"role": "assistant", "content": content})

            tool_call = parse_tool_call(content)
            if tool_call:
                func_name = tool_call.get("name")
                if func_name == "anythingllm_query":
                    try:
                        import json

                        args = json.loads(tool_call.get("arguments", "{}"))
                        query = args.get("query", "")
                        print(f"\n[正在查询AnythingLLM文档仓库: {query}]")
                        from anythingllm_query import query_workspace

                        result = query_workspace(query)
                        print(f"[查询完成]")
                        messages.append(
                            {
                                "role": "system",
                                "content": f"【文档仓库查询结果】{result}",
                            }
                        )
                    except Exception as e:
                        print(f"\n[调用anythingllm_query失败: {e}]")

            if should_summarize(messages, max_turns=5, max_tokens=max_context_tokens):
                messages_copy = [m.copy() for m in messages]
                thread = threading.Thread(
                    target=background_summarize,
                    args=(messages_copy, base_url, api_key, model, today),
                )
                thread.start()
                print("\n[后台进行聊天记录摘要压缩...]")

                messages = [
                    {
                        "role": "system",
                        "content": f"""你现在是一个专业的AI助手。请根据用户的问题给出有用的回答。今天的日期和时间是: {today}。

可用工具：
1. search_chat_history - 搜索本地聊天历史记录
2. anythingllm_query - 查询AnythingLLM文档仓库/文件仓库中的内容。当用户提到"文档仓库"、"文件仓库"、"仓库"并想要查询里面的内容时，必须使用此工具。""",
                    },
                ]
                print("[已压缩，继续新对话]")


if __name__ == "__main__":
    chat()
