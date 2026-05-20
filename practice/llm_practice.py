#!/usr/bin/env python3
"""
使用Python标准库访问用户定义的LLM API
读取项目根目录的.env文件中的配置
"""

import os
import re
import json
import time
import gc
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

def load_env_file(env_path):
    """从.env文件加载环境变量"""
    if not os.path.exists(env_path):
        raise FileNotFoundError(f"环境配置文件 {env_path} 不存在")

    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()


def get_api_url(base_url, path):
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def build_headers(api_key):
    headers = {
        'Content-Type': 'application/json'
    }
    if api_key and api_key.strip():
        headers['Authorization'] = f'Bearer {api_key}'
    return headers


def get_project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_path(relative_path):
    project_root = get_project_root()
    target = os.path.abspath(os.path.join(project_root, relative_path))
    if not target.startswith(project_root):
        raise ValueError('目录路径必须在项目根目录之内。')
    return target


def create_file(directory_path, file_name, content=''):
    abs_dir = resolve_path(directory_path)
    if not os.path.isdir(abs_dir):
        return {'error': f'目录不存在：{directory_path}'}

    target_path = os.path.join(abs_dir, file_name)
    if os.path.exists(target_path):
        return {'error': f'文件已存在：{file_name}'}

    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return {'success': True, 'created_path': target_path, 'bytes_written': len(content)}


def read_file_content(directory_path, file_name):
    abs_dir = resolve_path(directory_path)
    target_path = os.path.join(abs_dir, file_name)
    if not os.path.exists(target_path):
        return {'error': f'文件不存在：{file_name}'}
    if os.path.isdir(target_path):
        return {'error': f'目标不是文件：{file_name}'}

    with open(target_path, 'r', encoding='utf-8') as f:
        content = f.read()

    return {'file_name': file_name, 'directory_path': directory_path, 'content': content}


def write_file_content(file_path, content):
    abs_path = resolve_path(file_path)
    parent_dir = os.path.dirname(abs_path)
    if not os.path.isdir(parent_dir):
        return {'error': f'目录不存在：{parent_dir}'}

    with open(abs_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return {'success': True, 'created_path': abs_path, 'bytes_written': len(content)}


def list_files_with_info(directory_path):
    abs_dir = resolve_path(directory_path)
    if not os.path.isdir(abs_dir):
        return {'error': f'目录不存在：{directory_path}'}

    entries = []
    for name in sorted(os.listdir(abs_dir)):
        full_path = os.path.join(abs_dir, name)
        stat = os.stat(full_path)
        entries.append({
            'name': name,
            'is_directory': os.path.isdir(full_path),
            'size_bytes': stat.st_size,
            'modified_at': time.ctime(stat.st_mtime)
        })
    return {'directory_path': directory_path, 'entries': entries}


def extract_file_name(text):
    match = re.search(r'([A-Za-z0-9_\-]+\.[A-Za-z0-9]+)', text)
    if match:
        return match.group(1)
    return None


def extract_file_content(text):
    # 优先匹配双引号或中文引号之间的内容
    match = re.search(r'[“"\'`‘]([^“"\'`‘]+)[”"\'`’]', text)
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


def parse_direct_user_command(text):
    normalized = text.strip()
    file_name = extract_file_name(normalized)
    content = extract_file_content(normalized)

    if file_name and re.search(r'新建|创建', normalized):
        return {
            'tool': 'create_file',
            'args': {
                'directory_path': '.',
                'file_name': file_name,
                'content': content
            }
        }

    if file_name and re.search(r'读取|查看|打开', normalized):
        return {
            'tool': 'read_file_content',
            'args': {
                'directory_path': '.',
                'file_name': file_name
            }
        }

    if file_name and re.search(r'写入|修改|追加', normalized):
        return {
            'tool': 'write_file_content',
            'args': {
                'file_path': file_name,
                'content': content
            }
        }

    if re.search(r'列出|查看目录|当前目录|list', normalized):
        return {
            'tool': 'list_files_with_info',
            'args': {
                'directory_path': '.'
            }
        }

    return None


def estimate_tokens(text):
    return max(1, len(text) // 4)


def trim_message_history(messages, max_context_tokens):
    total_tokens = sum(estimate_tokens(message['content']) for message in messages)
    while messages and total_tokens > max_context_tokens:
        oldest = messages.pop(0)
        total_tokens -= estimate_tokens(oldest['content'])


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


def call_llm_api(base_url, model, api_key, messages, max_tokens=500, context_length=None, stream=True):
    """调用LLM API，支持多轮对话和流式输出"""
    url = get_api_url(base_url, 'chat/completions')
    headers = build_headers(api_key)

    data = {
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': 0.7,
        'stream': stream
    }

    if model and model.strip():
        data['model'] = model

    if context_length is not None:
        data['context_length'] = context_length

    try:
        req = Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method='POST')

        with urlopen(req) as response:
            if stream:
                try:
                    result = json.loads(response.read().decode('utf-8'))
                    if 'choices' in result and result['choices']:
                        full_content = result['choices'][0]['message']['content']
                        for char in full_content:
                            print(char, end='', flush=True)
                            time.sleep(0.02)
                        print()
                        return full_content
                    print(f"API响应格式异常: {result}")
                    return None
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    print(f"解析响应失败: {e}")
                    try:
                        raw_response = response.read().decode('utf-8')
                        print(f"原始响应: {raw_response[:200]}...")
                    except Exception:
                        print('无法读取原始响应')
                    return None
            else:
                result = json.loads(response.read().decode('utf-8'))
                if 'choices' in result and result['choices']:
                    return result['choices'][0]['message']['content']

    except HTTPError as e:
        print(f"HTTP错误: {e.code} - {e.reason}")
        try:
            error_content = e.read().decode('utf-8')
            print(f"响应内容: {error_content}")
        except Exception:
            pass
    except URLError as e:
        print(f"URL错误: {e.reason}")
    except json.JSONDecodeError as e:
        print(f"JSON解析错误: {e}")
    except Exception as e:
        print(f"其他错误: {e}")

    return None


def cleanup(messages):
    messages.clear()
    gc.collect()
    print('资源已清理。')

def main():
    # 项目根目录路径
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # .env文件路径
    env_file = os.path.join(project_root, '.env')

    try:
        # 加载环境变量
        load_env_file(env_file)

        # 获取配置
        base_url = os.environ.get('BASE_URL')
        model = os.environ.get('MODEL', '').strip()
        api_key = os.environ.get('API_KEY', '').strip()
        max_tokens = int(os.environ.get('MAX_TOKENS', '500') or 500)
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

        # 初始化对话历史
        messages = []

        try:
            while True:
                user_input = input("请输入问题或指令: ").strip()
                if not user_input:
                    continue

                if user_input == "/exit":
                    print("已退出对话。")
                    break
                elif user_input == "/clear":
                    messages = []
                    print("对话历史已清除。\n")
                    continue

                direct_command = parse_direct_user_command(user_input)
                if direct_command:
                    tool_name = direct_command['tool']
                    tool_args = direct_command['args']
                    tool_result = None
                    if tool_name == 'create_file':
                        tool_result = create_file(**tool_args)
                    elif tool_name == 'read_file_content':
                        tool_result = read_file_content(**tool_args)
                    elif tool_name == 'write_file_content':
                        tool_result = write_file_content(**tool_args)
                    elif tool_name == 'list_files_with_info':
                        tool_result = list_files_with_info(**tool_args)

                    if tool_result is not None:
                        if isinstance(tool_result, dict) and tool_result.get('error'):
                            print(f"工具执行失败：{tool_result['error']}")
                        else:
                            if tool_name == 'create_file':
                                print(f"已创建文件: {tool_result.get('created_path', '')}，写入 {tool_result.get('bytes_written', 0)} 字节。")
                            elif tool_name == 'read_file_content':
                                print(f"文件: {tool_result.get('file_name', '')}\n内容:\n{tool_result.get('content', '')}")
                            elif tool_name == 'write_file_content':
                                print(f"已写入文件: {tool_result.get('created_path', '')}，写入 {tool_result.get('bytes_written', 0)} 字节。")
                            elif tool_name == 'list_files_with_info':
                                entries = tool_result.get('entries', [])
                                print(f"当前目录: {tool_result.get('directory_path', '.')}")
                                for entry in entries:
                                    print(f"  {'[DIR]' if entry.get('is_directory') else '[FILE]'} {entry['name']}  大小: {entry.get('size_bytes', 0)}  修改: {entry.get('modified_at', '')}")
                        continue

                # 添加用户消息到历史
                messages.append({"role": "user", "content": user_input})
                trim_message_history(messages, context_length)

                print(f"\nLLM回复: ", end='', flush=True)

                response = call_llm_api(
                    base_url,
                    model,
                    api_key,
                    messages,
                    max_tokens=max_tokens,
                    context_length=context_length,
                    stream=False
                )

                if response is not None:
                    if response == "":
                        print("(API返回空响应)")
                        messages.pop()
                    else:
                        print(response)
                        messages.append({"role": "assistant", "content": response})
                else:
                    print("\n调用失败!")
                    messages.pop()
        finally:
            cleanup(messages)

    except FileNotFoundError as e:
        print(f"错误: {e}")
        print("请确保项目根目录下存在 .env 文件")
    except KeyboardInterrupt:
        print("\n已通过键盘中断退出。")
    except Exception as e:
        print(f"程序执行错误: {e}")

if __name__ == "__main__":
    main()