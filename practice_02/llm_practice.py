#!/usr/bin/env python3
"""基于本地 OpenAI 兼容 LLM API 的目录与文件操作工具代理。
遵循标准 agent 流程：
1) 将用户输入发送给模型
2) 模型返回 JSON 工具调用（`tool` / `args` 或 `tool_name` / `args`）
3) 本程序执行对应工具并将结果作为 `function` 消息回传给模型
4) 模型基于函数结果生成最终自然语言回复

此文件已包含常用别名和对 markdown 代码块中 JSON 的解析支持。
"""

import os
import re
import json
import time
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

SYSTEM_PROMPT = """You are a professional AI assistant specializing in local file management for a Python agent.
When the user requests a file or directory operation, reply with a JSON object only in the exact format below:

{
  "tool": "tool_name",
  "args": {
    ...
  }
}

If the user's request does not require a tool, respond with plain text only.

Available tools:
- list_files_with_info(directory_path)
- rename_file(directory_path, old_name, new_name)
- delete_file(directory_path, file_name)
- create_file(directory_path, file_name, content)
- read_file_content(directory_path, file_name)
- write_file_content(file_path, content)

Example tool-call format:
{
  "tool_name": "delete_file",
  "args": {
    "directory_path": ".",
    "file_name": "2.txt"
  }
}

For any add, read, update, delete, rename, or list operation, choose the most appropriate tool and return only the JSON object.
Do not return natural language when a tool call is required.

If the user asks about a file path, use relative paths from the project root.
If the user does not specify a directory for listing, use the project root.
If the user asks only for information, respond with plain text instead of a tool call.
"""


def get_project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_path(relative_path):
    project_root = get_project_root()
    target = os.path.abspath(os.path.join(project_root, relative_path))
    if not target.startswith(project_root):
        raise ValueError('目录路径必须在项目根目录之内。')
    return target


def load_env_file(env_path):
    if not os.path.exists(env_path):
        return
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())


def list_files_with_info(directory_path):
    abs_dir = resolve_path(directory_path)
    if not os.path.isdir(abs_dir):
        return {"error": f"目录不存在：{directory_path}"}

    entries = []
    for name in sorted(os.listdir(abs_dir)):
        full_path = os.path.join(abs_dir, name)
        try:
            stat = os.stat(full_path)
            entries.append({
                "name": name,
                "is_directory": os.path.isdir(full_path),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
        except OSError as exc:
            entries.append({
                "name": name,
                "error": str(exc)
            })
    return {"directory_path": directory_path, "entries": entries}


def rename_file(directory_path, old_name, new_name):
    abs_dir = resolve_path(directory_path)
    old_path = os.path.join(abs_dir, old_name)
    new_path = os.path.join(abs_dir, new_name)

    if not os.path.exists(old_path):
        return {"error": f"旧文件不存在：{old_name}"}
    if os.path.exists(new_path):
        return {"error": f"目标文件已存在：{new_name}"}

    os.rename(old_path, new_path)
    return {"success": True, "old_path": old_path, "new_path": new_path}


def delete_file(directory_path, file_name):
    abs_dir = resolve_path(directory_path)
    target_path = os.path.join(abs_dir, file_name)
    if not os.path.exists(target_path):
        return {"error": f"文件不存在：{file_name}"}
    if os.path.isdir(target_path):
        return {"error": f"目标不是文件：{file_name}"}

    os.remove(target_path)
    return {"success": True, "deleted_path": target_path}


def create_file(directory_path, file_name, content=""):
    abs_dir = resolve_path(directory_path)
    if not os.path.isdir(abs_dir):
        return {"error": f"目录不存在：{directory_path}"}

    target_path = os.path.join(abs_dir, file_name)
    if os.path.exists(target_path):
        return {"error": f"文件已存在：{file_name}"}

    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return {"success": True, "created_path": target_path, "bytes_written": len(content)}


def read_file_content(directory_path, file_name):
    abs_dir = resolve_path(directory_path)
    target_path = os.path.join(abs_dir, file_name)
    if not os.path.exists(target_path):
        return {"error": f"文件不存在：{file_name}"}
    if os.path.isdir(target_path):
        return {"error": f"目标不是文件：{file_name}"}

    with open(target_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return {"file_name": file_name, "directory_path": directory_path, "content": content}


def check_model_loaded(base_url, api_key):
    url = get_api_url(base_url, 'models')
    headers = build_headers(api_key)

    try:
        req = Request(url, headers=headers, method='GET')
        with urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            if isinstance(result, dict) and ('data' in result or 'models' in result):
                model_list = result.get('data') or result.get('models')
                if model_list:
                    print('本地模型加载成功。')
                    return True
            print('无法确认本地模型已加载，请检查模型服务。')
    except HTTPError as e:
        print(f"模型状态检查失败: HTTP {e.code} - {e.reason}")
    except URLError as e:
        print(f"模型状态检查失败: URL错误 - {e.reason}")
    except json.JSONDecodeError:
        print('模型状态检查失败：返回结果不是有效JSON。')
    except Exception as e:
        print(f"模型状态检查失败: {e}")

    return False


def get_api_url(base_url, path):
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def build_headers(api_key):
    headers = {
        'Content-Type': 'application/json'
    }
    if api_key and api_key.strip():
        headers['Authorization'] = f'Bearer {api_key.strip()}'
    return headers


def extract_file_name(text):
    match = re.search(r'([A-Za-z0-9_\-]+\.[A-Za-z0-9]+)', text)
    if match:
        return match.group(1)
    return None


def extract_file_content(text):
    # 优先匹配引号内内容
    match = re.search(r'[“"\'`‘]([^“"\'`‘]+)[”"\'’]', text)
    if match:
        return match.group(1).strip()

    # 如果存在文件名，则提取文件名后的内容
    file_name = extract_file_name(text)
    if file_name:
        idx = text.find(file_name)
        if idx != -1:
            suffix = text[idx + len(file_name):].strip()
            suffix = re.sub(r'^(?:文件(?:[，,])?)?(?:并?写入内容|并?写入|写入内容|写入|内容|修改|追加)[:：]?\s*', '', suffix)
            return suffix.strip().rstrip(' .。')

    # fallback: 写入/内容后面的文字
    match = re.search(r'(?:写入内容|写入|内容)[:：]?\s*(.+)$', text)
    if match:
        return match.group(1).strip().rstrip(' .。')
    return ''


def parse_tool_call(text):
    text = text.strip()
    # 抽取 markdown 代码块中的 JSON（如 ```json ... ```）
    if text.startswith('```') and '```' in text:
        start = text.find('```')
        end = text.rfind('```')
        if start != -1 and end != -1 and end > start:
            inner = text[start+3:end].strip()
            if inner.lower().startswith('json'):
                inner = inner[4:].strip()
            text = inner

    # 如果仍不以 { 开头，尝试在文本中提取第一个 JSON 对象
    if not text.startswith('{'):
        left = text.find('{')
        right = text.rfind('}')
        if left != -1 and right != -1 and right > left:
            text = text[left:right+1]

    if not text.startswith('{'):
        return None

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    tool_name = data.get('tool') or data.get('tool_name')
    tool_args = data.get('args') if isinstance(data.get('args'), dict) else {}
    if not tool_name:
        return None

    alias_map = {
        'list_files': 'list_files_with_info',
        'list_files_with_info': 'list_files_with_info',
        'list_directory': 'list_files_with_info',
        'rename_file': 'rename_file',
        'move_file': 'rename_file',
        'delete_file': 'delete_file',
        'remove_file': 'delete_file',
        'del_file': 'delete_file',
        'create_file': 'create_file',
        'add_file': 'create_file',
        'read_file_content': 'read_file_content',
        'read_file': 'read_file_content',
        'open_file': 'read_file_content',
        'write_file_content': 'write_file_content',
        'update_file': 'write_file_content',
        'modify_file': 'write_file_content',
        'edit_file': 'write_file_content'
    }

    normalized = alias_map.get(tool_name)
    if normalized is None:
        return None

    if normalized == 'list_files_with_info' and 'directory_path' not in tool_args:
        tool_args['directory_path'] = '.'

    return {'tool': normalized, 'args': tool_args}


def normalize_tool_args(args):
    normalized = dict(args)
    if 'file_path' in normalized:
        path = normalized.pop('file_path')
        normalized['directory_path'] = os.path.dirname(path) or '.'
        normalized['file_name'] = os.path.basename(path)
    return normalized


def write_file_content(file_path, content):
    abs_path = resolve_path(file_path)
    parent_dir = os.path.dirname(abs_path)
    if not os.path.isdir(parent_dir):
        return {"error": f"目录不存在：{parent_dir}"}

    with open(abs_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return {"success": True, "created_path": abs_path, "bytes_written": len(content)}


def execute_function_call(function_call):
    name = function_call.get('name')
    args = normalize_tool_args(json.loads(function_call.get('arguments') or '{}'))
    if name == 'list_files_with_info':
        return list_files_with_info(**args)
    if name == 'rename_file':
        return rename_file(**args)
    if name == 'delete_file':
        return delete_file(**args)
    if name == 'create_file':
        return create_file(**args)
    if name == 'read_file_content':
        return read_file_content(**args)
    if name == 'write_file_content':
        return write_file_content(**args)
    return {"error": f"未知工具：{name}"}


def format_tool_result(tool_name, tool_result):
    if isinstance(tool_result, dict) and tool_result.get('error'):
        return f"工具执行失败：{tool_result['error']}"

    if tool_name == 'list_files_with_info':
        lines = [f"当前目录: {tool_result.get('directory_path', '.')}", "文件列表:"]
        for entry in tool_result.get('entries', []):
            if entry.get('is_directory'):
                lines.append(f"  [DIR]  {entry['name']}  修改: {entry.get('modified_at', '')}")
            else:
                lines.append(f"  [FILE] {entry['name']}  大小: {entry.get('size_bytes', 0)} 字节  修改: {entry.get('modified_at', '')}")
        return "\n".join(lines)

    if tool_name == 'read_file_content':
        return f"文件: {tool_result.get('file_name', '')}\n内容:\n{tool_result.get('content', '')}"

    if tool_name == 'create_file':
        return f"已创建文件: {tool_result.get('created_path', '')}，写入 {tool_result.get('bytes_written', 0)} 字节。"

    if tool_name == 'write_file_content':
        return f"已写入文件: {tool_result.get('created_path', '')}，写入 {tool_result.get('bytes_written', 0)} 字节。"

    if tool_name == 'delete_file':
        return f"已删除文件: {tool_result.get('deleted_path', '')}。"

    if tool_name == 'rename_file':
        return f"已重命名: {tool_result.get('old_path', '')} -> {tool_result.get('new_path', '')}。"

    return json.dumps(tool_result, ensure_ascii=False, indent=2)


def call_openai(model, messages, base_url, api_key):
    url = get_api_url(base_url, 'chat/completions')
    headers = build_headers(api_key)

    data = {
        'messages': messages,
        'max_tokens': int(os.environ.get('MAX_TOKENS', '500') or 500),
        'temperature': 0.7,
        'stream': False
    }

    if model and model.strip():
        data['model'] = model

    try:
        req = Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method='POST')
        with urlopen(req) as response:
            raw = response.read().decode('utf-8')
            return json.loads(raw)
    except HTTPError as e:
        print(f"LLM API HTTP 错误: {e.code} - {e.reason}")
    except URLError as e:
        print(f"LLM API URL 错误: {e.reason}")
    except json.JSONDecodeError as e:
        print(f"LLM API 返回解析失败: {e}")
    except Exception as e:
        print(f"LLM API 调用错误: {e}")
    return None


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_file = os.path.join(project_root, '.env')

    try:
        load_env_file(env_file)

        base_url = os.environ.get('BASE_URL')
        model = os.environ.get('MODEL', '').strip()
        api_key = os.environ.get('API_KEY', '').strip() or os.environ.get('OPENAI_API_KEY', '').strip()
        context_length = int(os.environ.get('CONTEXT_LENGTH', '64000') or 64000)

        if not base_url:
            print("错误: 缺少必要的环境变量 BASE_URL")
            return

        print(f"使用模型: {model or '<默认模型>'}")
        print(f"API地址: {base_url}")
        print(f"对话上下文最大长度: {context_length} tokens")
        print("-" * 50)
        print("输入 /exit 退出对话，输入 /clear 清除对话历史")

        if not check_model_loaded(base_url, api_key):
            print('请先检查本地模型服务是否已启动并加载模型。')
            return

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        while True:
            user_input = input("请输入问题或指令: ").strip()
            if not user_input:
                continue
            if user_input == "/exit":
                print("已退出对话。")
                break
            if user_input == "/clear":
                messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                print("对话历史已清除。\n")
                continue

            messages.append({"role": "user", "content": user_input})
            response = call_openai(model, messages, base_url, api_key)
            if not response or 'choices' not in response or not response['choices']:
                print('LLM 未返回有效响应。')
                continue

            assistant_message = response['choices'][0].get('message', {})
            assistant_text = assistant_message.get('content', '')

            tool_call = parse_tool_call(assistant_text)
            if tool_call:
                tool_name = tool_call['tool']
                tool_args = tool_call['args']
                tool_result = execute_function_call({
                    'name': tool_name,
                    'arguments': json.dumps(tool_args, ensure_ascii=False)
                })
                # Immediate formatted result so user sees action outcome even if model fails later
                formatted_result = format_tool_result(tool_name, tool_result)
                print(formatted_result)
                # Add assistant message with tool call and the function result to the context
                messages.append({"role": "assistant", "content": assistant_text})
                messages.append({"role": "function", "name": tool_name, "content": json.dumps(tool_result, ensure_ascii=False)})
                # Ask model to produce a final natural-language response based on the function result
                final_response = call_openai(model, messages, base_url, api_key)
                if final_response and 'choices' in final_response and final_response['choices']:
                    final_assistant_text = final_response['choices'][0].get('message', {}).get('content', '')
                    if final_assistant_text and final_assistant_text.strip() and final_assistant_text.strip() != assistant_text.strip():
                        print(final_assistant_text)
                        messages.append({"role": "assistant", "content": final_assistant_text})
                # otherwise: we've already printed the formatted_result as a reliable fallback
            else:
                print(assistant_text)
                messages.append({"role": "assistant", "content": assistant_text})

    except FileNotFoundError as e:
        print(f"错误: {e}")
        print("请确保项目根目录下存在 .env 文件")
    except KeyboardInterrupt:
        print("\n已通过键盘中断退出。")
    except Exception as e:
        print(f"程序执行错误: {e}")


if __name__ == "__main__":
    main()
