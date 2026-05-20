#!/usr/bin/env python3
"""LLM 工具调用代理：基于 urllib 设计文件操作工具。"""

import json
import os
import re
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

SYSTEM_PROMPT = """你是一个专业的文件管理助手。你的任务是根据用户的自然语言指令，自动调用相应的工具来完成任务。

## 工具列表
1. list_files_with_info(directory_path) - 列出目录下的文件
2. rename_file(directory_path, old_name, new_name) - 重命名文件
3. delete_file(directory_path, file_name) - 删除文件
4. create_file(directory_path, file_name, content) - 创建新文件并写入内容，如果文件已存在则覆盖写入
5. read_file_content(directory_path, file_name) - 读取文件内容

## 指令理解示例（中文）
- "删除 test.txt" -> delete_file(directory_path="practice_02", file_name="test.txt")
- "查看 test.txt 的内容" -> read_file_content(directory_path="practice_02", file_name="test.txt")
- "读取 test.txt" -> read_file_content(directory_path="practice_02", file_name="test.txt")
- "列出当前目录" -> list_files_with_info(directory_path="practice_02")
- "查看目录有哪些文件" -> list_files_with_info(directory_path="practice_02")
- "把 old.txt 改名为 new.txt" -> rename_file(directory_path="practice_02", old_name="old.txt", new_name="new.txt")
- "新建 1.txt 并写入 hello" -> create_file(directory_path="practice_02", file_name="1.txt", content="hello")
- "在 1.txt 写入内容 hello" -> create_file(directory_path="practice_02", file_name="1.txt", content="hello")

## 重要规则
1. 除非指定目录，否则默认使用 "practice_02" 作为目录
2. 直接调用工具，不要询问用户确认
3. 用户说"删除X"就是调用delete_file，"查看/读取X"就是调用read_file_content，"列出"就是调用list_files_with_info
4. "新建/创建X并写入Y" 就是调用create_file
5. 根据直觉判断用户意图并立即执行
6. 如果文件已存在且用户要求写入内容，直接覆盖写入
"""

FUNCTIONS = [
    {
        "name": "list_files_with_info",
        "description": "列出目录下的文件",
        "parameters": {
            "type": "object",
            "properties": {
                "directory_path": {"type": "string", "description": "目录路径"}
            },
            "required": ["directory_path"],
        },
    },
    {
        "name": "rename_file",
        "description": "重命名文件",
        "parameters": {
            "type": "object",
            "properties": {
                "directory_path": {"type": "string", "description": "目录路径"},
                "old_name": {"type": "string", "description": "原文件名"},
                "new_name": {"type": "string", "description": "新文件名"},
            },
            "required": ["directory_path", "old_name", "new_name"],
        },
    },
    {
        "name": "delete_file",
        "description": "删除文件",
        "parameters": {
            "type": "object",
            "properties": {
                "directory_path": {"type": "string", "description": "目录路径"},
                "file_name": {"type": "string", "description": "文件名"},
            },
            "required": ["directory_path", "file_name"],
        },
    },
    {
        "name": "create_file",
        "description": "创建新文件并写入内容",
        "parameters": {
            "type": "object",
            "properties": {
                "directory_path": {"type": "string", "description": "目录路径"},
                "file_name": {"type": "string", "description": "文件名"},
                "content": {"type": "string", "description": "文件内容"},
            },
            "required": ["directory_path", "file_name"],
        },
    },
    {
        "name": "read_file_content",
        "description": "读取文件内容",
        "parameters": {
            "type": "object",
            "properties": {
                "directory_path": {"type": "string", "description": "目录路径"},
                "file_name": {"type": "string", "description": "文件名"},
            },
            "required": ["directory_path", "file_name"],
        },
    },
]


def get_project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_path(relative_path):
    project_root = get_project_root()
    target = os.path.abspath(os.path.join(project_root, relative_path))
    if not target.startswith(project_root):
        raise ValueError("Path must be within project root.")
    return target


def load_env_file(env_path):
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def list_files_with_info(directory_path):
    abs_dir = resolve_path(directory_path)
    if not os.path.isdir(abs_dir):
        return {"error": f"Directory not found: {directory_path}"}

    entries = []
    for name in sorted(os.listdir(abs_dir)):
        full_path = os.path.join(abs_dir, name)
        try:
            stat = os.stat(full_path)
            entries.append(
                {
                    "name": name,
                    "is_directory": os.path.isdir(full_path),
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )
        except OSError as exc:
            entries.append({"name": name, "error": str(exc)})
    return {"directory_path": directory_path, "entries": entries}


def rename_file(directory_path, old_name, new_name):
    abs_dir = resolve_path(directory_path)
    old_path = os.path.join(abs_dir, old_name)
    new_path = os.path.join(abs_dir, new_name)

    if not os.path.exists(old_path):
        return {"error": f"File not found: {old_name}"}
    if os.path.exists(new_path):
        return {"error": f"File already exists: {new_name}"}

    os.rename(old_path, new_path)
    return {"success": True, "old_path": old_path, "new_path": new_path}


def delete_file(directory_path, file_name):
    abs_dir = resolve_path(directory_path)
    target_path = os.path.join(abs_dir, file_name)
    if not os.path.exists(target_path):
        return {"error": f"File not found: {file_name}"}
    if os.path.isdir(target_path):
        return {"error": f"Not a file: {file_name}"}

    os.remove(target_path)
    return {"success": True, "deleted_path": target_path}


def create_file(directory_path, file_name, content=""):
    abs_dir = resolve_path(directory_path)
    if not os.path.isdir(abs_dir):
        return {"error": f"Directory not found: {directory_path}"}

    target_path = os.path.join(abs_dir, file_name)

    with open(target_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {"success": True, "created_path": target_path, "bytes_written": len(content)}


def read_file_content(directory_path, file_name):
    abs_dir = resolve_path(directory_path)
    target_path = os.path.join(abs_dir, file_name)
    if not os.path.exists(target_path):
        return {"error": f"File not found: {file_name}"}
    if os.path.isdir(target_path):
        return {"error": f"Not a file: {file_name}"}

    with open(target_path, "r", encoding="utf-8") as f:
        content = f.read()
    return {
        "file_name": file_name,
        "directory_path": directory_path,
        "content": content,
    }


def call_openai(messages, base_url, api_key, model):
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    data = {
        "model": model,
        "messages": messages,
        "functions": FUNCTIONS,
        "function_call": "auto",
    }

    try:
        req = Request(
            url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST"
        )
        with urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError) as e:
        return {"error": str(e)}


def parse_tool_call(text):
    if not text:
        return None

    match = re.search(r"(\w+)\(([^)]+)\)", text)
    if match:
        name = match.group(1)
        args_str = match.group(2)
        if name in [
            "list_files_with_info",
            "rename_file",
            "delete_file",
            "create_file",
            "read_file_content",
        ]:
            args = {}
            for arg in args_str.split(","):
                if "=" in arg:
                    key, val = arg.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    args[key] = val
            return {"name": name, "arguments": json.dumps(args)}

    match = re.search(r"<\|tool_call>call:\s*(\w+)\(([^)]+)\)", text)
    if match:
        name = match.group(1)
        args_str = match.group(2)
        args = {}
        for arg in args_str.split(","):
            if "=" in arg:
                key, val = arg.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                args[key] = val
        return {"name": name, "arguments": json.dumps(args)}

    match = re.search(r"<\|tool_call>call:(\w+)\{([^}]+)\}<tool_call\|>", text)
    if match:
        name = match.group(1)
        args_str = match.group(2)
        args = {}
        for arg in args_str.split(","):
            arg = arg.strip()
            if ":" in arg:
                key, val = arg.split(":", 1)
                key = key.strip()
                val = re.sub(r"<\|\"\|>(.+?)<\|\"\|>", r"\1", val).strip()
                args[key] = val
        return {"name": name, "arguments": json.dumps(args)}

    match = re.search(r"<\|tool_call>call:\s*(\{[^}]+\})<tool_call\|>", text)
    if match:
        try:
            data = json.loads(match.group(1))
            name = (
                data.get("tool_name")
                or data.get("name")
                or data.get("function_call", {}).get("name")
            )
            args = (
                data.get("tool_args")
                or data.get("arguments")
                or data.get("function_call", {}).get("arguments", {})
            )
            if name and args:
                if isinstance(args, str):
                    return {"name": name, "arguments": args}
                return {"name": name, "arguments": json.dumps(args)}
        except:
            pass
    return None


def execute_function_call(function_call):
    name = function_call.get("name")
    args = json.loads(function_call.get("arguments") or "{}")
    if name == "list_files_with_info":
        return list_files_with_info(**args)
    if name == "rename_file":
        return rename_file(**args)
    if name == "delete_file":
        return delete_file(**args)
    if name == "create_file":
        return create_file(**args)
    if name == "read_file_content":
        return read_file_content(**args)
    return {"error": f"Unknown tool: {name}"}


def run_agent():
    root = get_project_root()
    load_env_file(os.path.join(root, ".env"))

    base_url = os.environ.get("BASE_URL", "http://127.0.0.1:8080/v1")
    api_key = os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("MODEL") or os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")

    if not base_url:
        print("Missing BASE_URL in .env")
        return

    print("LLM tool agent started. Input /exit to quit.")
    print("Examples: delete test.txt, view main.py, list directory")

    while True:
        user_input = input("Command: ").strip()
        if not user_input:
            continue
        if user_input == "/exit":
            print("Exit.")
            break

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ]

        response = call_openai(messages, base_url, api_key, model)

        if response.get("error"):
            print(f"Error: {response['error']}")
            continue

        choice = response["choices"][0]
        message = choice.get("message", {})

        try:
            function_call = message.get("function_call")
            if not function_call:
                function_call = parse_tool_call(message.get("content", ""))

            if function_call:
                tool_result = execute_function_call(function_call)
                print(f"Result: {tool_result}")
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "function_call": function_call,
                    }
                )
                messages.append(
                    {
                        "role": "function",
                        "name": function_call["name"],
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )
                second_response = call_openai(messages, base_url, api_key, model)
                if second_response.get("error"):
                    print(f"Error: {second_response['error']}")
                    continue
                final_content = (
                    second_response["choices"][0].get("message", {}).get("content", "")
                )
                print(final_content)
            else:
                print(message.get("content", "No response."))
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    run_agent()
