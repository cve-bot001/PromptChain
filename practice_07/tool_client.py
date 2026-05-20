#!/usr/bin/env python3
"""Chained Tool Client — 链式工具调用代理

在 practice_06 基础上实现：前一个工具的输出作为后一个工具的输入参数，
LLM 根据中间结果自主决定下一步工具调用。
"""

import json
import os
import re
import platform
import subprocess
import sys
import time
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ---------------------------------------------------------------------------
# 0. 调试系统
# ---------------------------------------------------------------------------

DEBUG = False


def debug_init():
    """在 load_env_file 之后调用，初始化调试开关。"""
    global DEBUG
    DEBUG = os.environ.get("DEBUG", "").strip() in ("1", "true", "yes", "on")


def debug_print(*args, **kwargs):
    """打印调试信息到 stderr，带 [D] 前缀。"""
    if DEBUG:
        msg = " ".join(str(a) for a in args)
        print(f"[D] {msg}", file=sys.stderr, **kwargs)


# ---------------------------------------------------------------------------
# 1. 工具函数
# ---------------------------------------------------------------------------

def get_project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env_file(env_path):
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())


def _resolve_path(relative_path):
    root = get_project_root()
    target = os.path.abspath(os.path.join(root, relative_path))
    if not target.startswith(root):
        raise ValueError("Path must be within project root")
    return target


# --- 文件操作工具 ---

def tool_list_files(directory_path):
    abs_dir = _resolve_path(directory_path)
    if not os.path.isdir(abs_dir):
        return {"error": f"Directory not found: {directory_path}"}
    entries = []
    for name in sorted(os.listdir(abs_dir)):
        full = os.path.join(abs_dir, name)
        try:
            st = os.stat(full)
            entries.append({
                "name": name,
                "is_directory": os.path.isdir(full),
                "size_bytes": st.st_size,
                "modified_at": datetime.fromtimestamp(st.st_mtime).isoformat(),
            })
        except OSError as exc:
            entries.append({"name": name, "error": str(exc)})
    return {"directory_path": directory_path, "entries": entries}


def tool_search_files(directory_path, keyword):
    abs_dir = _resolve_path(directory_path)
    if not os.path.isdir(abs_dir):
        return {"error": f"Directory not found: {directory_path}"}
    results = []
    for name in os.listdir(abs_dir):
        file_path = os.path.join(abs_dir, name)
        if os.path.isfile(file_path):
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if keyword.lower() in content.lower():
                    results.append({"name": name, "line_count": content.count("\n") + 1})
            except Exception as exc:
                results.append({"name": name, "error": str(exc)})
    return {"directory_path": directory_path, "keyword": keyword, "matches": results}


def tool_read_file(directory_path, file_name):
    abs_dir = _resolve_path(directory_path)
    target = os.path.join(abs_dir, file_name)
    if not os.path.exists(target):
        return {"error": f"File not found: {file_name}"}
    if os.path.isdir(target):
        return {"error": f"Path is a directory: {file_name}"}
    with open(target, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    return {"file_name": file_name, "directory_path": directory_path, "content": content, "char_count": len(content)}


def tool_write_file(directory_path, file_name, content):
    abs_dir = _resolve_path(directory_path)
    if not os.path.isdir(abs_dir):
        return {"error": f"Directory not found: {directory_path}"}
    target = os.path.join(abs_dir, file_name)
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    return {"success": True, "file_name": file_name, "directory_path": directory_path, "bytes_written": len(content)}


def tool_web_fetch(url):
    try:
        req = Request(url, headers={"User-Agent": "ChainedToolClient/1.0"})
        with urlopen(req, timeout=15) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            content = resp.read().decode(charset, errors="replace")
    except Exception as exc:
        return {"error": str(exc)}
    text = _strip_html(content)
    text = text.replace("\ufeff", "").replace("\u200b", "")
    return {"url": url, "content": text[:6000], "char_count": len(text)}


def _strip_html(html):
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


DANGER_PATTERNS = [
    # Windows 危险命令
    (re.compile(r"\bformat\b", re.IGNORECASE), "磁盘格式化"),
    (re.compile(r"\bdiskpart\b", re.IGNORECASE), "磁盘分区操作"),
    (re.compile(r"\bshutdown\b", re.IGNORECASE), "系统关机/重启"),
    (re.compile(r"\bdel\s+/[Ff]\s+/[Ss]\s+C:\\", re.IGNORECASE), "递归删除C盘"),
    (re.compile(r"\brmdir\s+/[Ss]\s+C:\\", re.IGNORECASE), "递归删除C盘"),
    (re.compile(r"iex\s*\(.*iwr", re.IGNORECASE), "下载并执行远程脚本"),
    # Linux 危险命令
    (re.compile(r"\brm\s+-rf\s+/", re.IGNORECASE), "递归删除根目录"),
    (re.compile(r"\brm\s+-rf\s+--no-preserve-root", re.IGNORECASE), "强制删除根目录"),
    (re.compile(r"\bmkfs\.", re.IGNORECASE), "格式化文件系统"),
    (re.compile(r"\bdd\s+if=", re.IGNORECASE), "磁盘写入操作"),
    (re.compile(r"\breboot\b", re.IGNORECASE), "系统重启"),
    (re.compile(r"\bshutdown\b", re.IGNORECASE), "系统关机"),
    (re.compile(r">\s*/dev/sd[a-z]", re.IGNORECASE), "写入块设备"),
    (re.compile(r"\bchmod\s+777\s+/", re.IGNORECASE), "修改根目录权限"),
    (re.compile(r"curl\s+.*\|\s*(ba)?sh\b", re.IGNORECASE), "下载并管道执行脚本"),
    (re.compile(r"wget\s+.*-O\s+-\s*\|\s*(ba)?sh\b", re.IGNORECASE), "下载并管道执行脚本"),
    # 通用危险操作
    (re.compile(r"/etc/(passwd|shadow|sudoers)", re.IGNORECASE), "修改系统认证文件"),
    (re.compile(r"C:\\Windows\\System32", re.IGNORECASE), "修改 Windows 系统目录"),
]


def tool_run_command(command, working_directory=".", description=""):
    """执行系统命令，自动检测平台，执行前展示命令并等待用户确认。

    参数:
      command: 要执行的完整命令
      working_directory: 工作目录（相对于项目根目录）
      description: 命令用途的一句话说明"""

    # 安全检查
    for pattern, reason in DANGER_PATTERNS:
        if pattern.search(command):
            return {
                "error": f"命令被拒绝执行（安全规则）",
                "reason": f"匹配危险模式: {reason}",
                "command": command,
            }

    # 解析工作目录
    try:
        workdir = _resolve_path(working_directory)
    except Exception:
        workdir = get_project_root()

    # 确认展示
    os_type = platform.system()
    if os_type == "Windows":
        default_shell = "PowerShell"
        default_flag = ""
    else:
        default_shell = "bash"
        default_flag = ""

    print("\n" + "!" * 60)
    print(f" 工具: run_command ({default_shell})")
    print(f" 用途: {description or '(无说明)'}")
    print(f" 目录: {os.path.relpath(workdir, get_project_root())}")
    print(f" 命令: {command}")
    print("!" * 60)
    try:
        confirm = input(" 确认执行? (y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return {"error": "用户取消操作", "command": command, "executed": False}

    if confirm not in ("y", "yes"):
        return {"error": "用户拒绝执行", "command": command, "executed": False}

    # 执行命令
    try:
        if os_type == "Windows":
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command],
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
        else:
            result = subprocess.run(
                command,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=30,
                shell=True,
                encoding="utf-8",
                errors="replace",
            )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if len(stdout) > 3000:
            stdout = stdout[:3000] + f"\n... (截断，共 {len(result.stdout)} 字符)"
        if len(stderr) > 1000:
            stderr = stderr[:1000] + f"\n... (截断，共 {len(result.stderr)} 字符)"

        return {
            "command": command,
            "working_directory": working_directory,
            "executed": True,
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "platform": os_type,
            "shell": default_shell,
        }

    except subprocess.TimeoutExpired:
        return {"error": "命令执行超时（30秒）", "command": command, "executed": False}
    except FileNotFoundError:
        return {"error": "找不到 powershell.exe，请检查系统环境", "command": command, "executed": False}
    except Exception as exc:
        return {"error": str(exc), "command": command, "executed": False}


# 工具注册表
TOOL_REGISTRY = {
    "list_files": {
        "function": tool_list_files,
        "description": "列出指定目录下的所有文件和子目录",
        "parameters": {
            "type": "object",
            "properties": {
                "directory_path": {"type": "string", "description": "目录路径"},
            },
            "required": ["directory_path"],
        },
    },
    "search_files": {
        "function": tool_search_files,
        "description": "在目录下的所有文件中搜索包含指定关键词的文件，返回匹配文件列表",
        "parameters": {
            "type": "object",
            "properties": {
                "directory_path": {"type": "string", "description": "目录路径"},
                "keyword": {"type": "string", "description": "要搜索的关键词"},
            },
            "required": ["directory_path", "keyword"],
        },
    },
    "read_file": {
        "function": tool_read_file,
        "description": "读取指定文件的内容",
        "parameters": {
            "type": "object",
            "properties": {
                "directory_path": {"type": "string", "description": "目录路径"},
                "file_name": {"type": "string", "description": "文件名"},
            },
            "required": ["directory_path", "file_name"],
        },
    },
    "write_file": {
        "function": tool_write_file,
        "description": "将内容写入指定文件，如果文件已存在则覆盖",
        "parameters": {
            "type": "object",
            "properties": {
                "directory_path": {"type": "string", "description": "目录路径"},
                "file_name": {"type": "string", "description": "文件名"},
                "content": {"type": "string", "description": "要写入的内容"},
            },
            "required": ["directory_path", "file_name", "content"],
        },
    },
    "web_fetch": {
        "function": tool_web_fetch,
        "description": "访问指定URL并获取网页文本内容",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "网页URL"},
            },
            "required": ["url"],
        },
    },
    "run_command": {
        "function": tool_run_command,
        "description": "在终端中执行系统命令。Windows 使用 PowerShell，Linux 使用 bash。每次执行前会询问用户确认。用户要求执行命令、运行脚本、查看系统信息、操作文件/目录时使用",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的完整命令。Windows: PowerShell 语法; Linux: bash 语法"},
                "description": {"type": "string", "description": "一句话说明该命令的用途（必填，用于展示给用户确认）"},
                "working_directory": {"type": "string", "description": "工作目录，默认为项目根目录"},
            },
            "required": ["command", "description"],
        },
    },
    "activate_coach": {
        "function": None,
        "description": "激活写作/软实力教练模式。可用 skill: soft-skills-coach(沟通/活动/表达/情绪陪跑), academic-paper-writer(毕业论文/期刊论文/引用格式), article-writer(博客/公众号/评论/科普文章), book-review-writer(读书心得/书评/读后感)。用户提到读书心得/读后感/书评/这本书时必须用 book-review-writer；提到论文/文献/引用/期刊投稿时必须用 academic-paper-writer；提到文章/博客/公众号写作时必须用 article-writer；提到沟通困难/活动焦虑/表达紧张时必须用 soft-skills-coach",
        "parameters": {
            "type": "object",
            "properties": {
                "skill": {"type": "string", "description": "教练 skill 名称: soft-skills-coach / academic-paper-writer / article-writer / book-review-writer"},
            },
            "required": ["skill"],
        },
    },
}


# ---------------------------------------------------------------------------
# 2. ChainedCallContext — 链式调用上下文管理器
# ---------------------------------------------------------------------------

class ChainedCallContext:
    """管理链式工具调用之间的数据和状态。"""

    def __init__(self, max_iterations=10):
        self.max_iterations = max_iterations
        self.steps = []          # 每一步的记录: {step, tool_name, arguments, result}
        self.variables = {}      # 中间变量存储，供后续步骤引用
        self.current_step = 0

    def record_step(self, tool_name, arguments, result):
        self.current_step += 1
        step = {
            "step": self.current_step,
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result,
        }
        self.steps.append(step)
        return step

    def set_variable(self, key, value):
        self.variables[key] = value

    def get_variable(self, key):
        return self.variables.get(key)

    def is_exceeded(self):
        return self.current_step >= self.max_iterations

    def get_history_summary(self):
        lines = []
        for s in self.steps:
            args_str = json.dumps(s["arguments"], ensure_ascii=False)
            result_preview = json.dumps(s["result"], ensure_ascii=False)
            if len(result_preview) > 300:
                result_preview = result_preview[:300] + "...(truncated)"
            lines.append(
                f"步骤{s['step']}: 调用 {s['tool_name']}({args_str})\n"
                f"  结果: {result_preview}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3. LLM 调用与响应解析
# ---------------------------------------------------------------------------

def call_openai(messages, base_url, api_key, model):
    """调用 LLM，纯文本模式，不依赖 OpenAI function calling API。"""
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    data = {"model": model, "messages": messages}

    try:
        req = Request(url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST")
        with urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError) as e:
        return {"error": str(e)}


def parse_chained_response(message):
    """解析 LLM 响应，从文本 content 中提取 JSON 决策。

    返回: dict 或 None
      {"done": true, "answer": "..."}  任务完成
      {"done": false, "tool_call": {"name": "...", "arguments": {...}}}  需要继续调用
    """
    if message is None:
        return None

    content = message.get("content", "")
    if not content or not content.strip():
        return None

    # 提取 JSON 并解析
    json_str = _extract_json(content)
    if json_str is None:
        debug_print(f"  _extract_json returned None for content: {content[:80]}...")
        return {"done": True, "answer": content.strip()}

    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, TypeError) as e:
        debug_print(f"  json.loads failed: {e}, json_str[:80]: {json_str[:80]}")
        return {"done": True, "answer": content.strip()}

    # 检查是否为合法的决策格式
    if isinstance(data, dict):
        if "done" in data:
            if data["done"] is True:
                return {"done": True, "answer": data.get("answer", "")}
            elif data["done"] is False:
                tc = data.get("tool_call", {})
                if isinstance(tc, dict) and "name" in tc:
                    return {"done": False, "tool_call": tc}

    return {"done": True, "answer": content.strip()}


def _extract_json(text):
    """从文本中提取 JSON 字符串，处理 markdown 代码块。"""
    # 1. ```json ... ```
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    # 2. ``` ... ```
    m = re.search(r"```\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        candidate = m.group(1).strip()
        if candidate.startswith("{"):
            return candidate
    # 3. 直接找最外层的 { ... }
    return _find_outer_json(text)


def _find_outer_json(text):
    """从文本中提取最外层 {} 包裹的 JSON。"""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return None


# ---------------------------------------------------------------------------
# 4. 分析提示词构建
# ---------------------------------------------------------------------------

def build_analysis_prompt(user_request, context):
    """构建分析提示词，包含用户请求、执行历史和决策规则。

    参数:
      user_request: 用户原始请求字符串
      context: ChainedCallContext 实例"""
    if context.steps:
        history_text = context.get_history_summary()
    else:
        history_text = "（暂无步骤）"

    remaining = context.max_iterations - context.current_step

    prompt = f"""## 用户原始请求
{user_request}

## 已执行步骤
{history_text}

## 决策规则
1. 分析当前进度：上述步骤的结果是否已经满足用户请求？
2. 如果**已满足**（任务完成），输出完成标志
3. 如果**未满足**，判断还需要什么信息，选择正确的工具继续执行
4. 你可以将前一步工具的结果作为下一步的参数输入（链式调用）
5. 最多还可以执行 {remaining} 步，请高效规划

## 环境信息
当前操作系统: {platform.system()}（若调用 run_command 请使用该系统原生命令）

## 可用工具
"""
    for name, info in TOOL_REGISTRY.items():
        desc = info["description"]
        params_str = json.dumps(info["parameters"]["properties"], ensure_ascii=False)
        prompt += f"- **{name}**: {desc}\n  参数: {params_str}\n"

    prompt += """
## 输出格式（严格遵循）

**任务完成时**，输出：
```json
{"done": true, "answer": "根据所有执行结果给出的最终回答"}
```

**需要继续调用工具时**，输出：
```json
{"done": false, "tool_call": {"name": "工具名称", "arguments": {"参数名": "参数值"}}}
```

**重要**: 只输出 JSON，不要输出任何解释、分析或其他文字！"""
    return prompt


# ---------------------------------------------------------------------------
# 5. 工具执行 + 技能动态注入
# ---------------------------------------------------------------------------

SKILL_MD_PATTERN = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _get_skill_body(tool_name):
    """加载工具的 SKILL.md 正文，动态注入运行时信息（平台等）。

    返回: 正文内容字符串，若技能不存在返回 None"""
    skill_dir = os.path.join(get_project_root(), ".agent", "skill", tool_name)
    if not os.path.isdir(skill_dir):
        return None

    for md_name in ["SKILL.md", "skill.md"]:
        md_path = os.path.join(skill_dir, md_name)
        if os.path.isfile(md_path):
            break
    else:
        return None

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    m = SKILL_MD_PATTERN.match(content)
    body = content[m.end():].strip() if m else content.strip()

    # 动态注入运行时平台信息
    os_type = platform.system()
    body = body.replace("{{PLATFORM}}", os_type)
    body = body.replace("{{SHELL}}", "PowerShell" if os_type == "Windows" else "bash")

    return body


def execute_tool(tool_name, arguments):
    """根据工具名和参数执行对应的工具函数。"""
    if tool_name == "activate_coach":
        return {"error": "activate_coach 由主循环特殊处理，不应直接调用"}
    if tool_name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        func = TOOL_REGISTRY[tool_name]["function"]
        return func(**arguments)
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# 6. System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是一个链式工具调用助手。你可以连续调用多个工具，前一个工具的输出可以作为后一个工具的输入。

## 链式调用规则

1. **顺序依赖**：如果需要多个步骤，必须按依赖顺序执行。例如：
   - 先搜索文件 → 再读取找到的文件 → 最后总结内容
   - 先访问网页 → 再分析内容 → 最后保存结果

2. **中间结果利用**：每一步的结果可能包含下一步需要的信息：
   - `search_files` 返回匹配的文件名列表 → 用这些文件名调用 `read_file`
   - `read_file` 返回文件内容 → 基于内容进行分析或写入
   - `web_fetch` 返回网页内容 → 分析内容后调用 `write_file` 保存

3. **上下文变量引用**：你可以引用前面步骤的结果。例如：
   - 如果步骤1搜索到文件 "a.py" 和 "b.py"，步骤2可以分别读取它们
   - 如果步骤1读取了两个数字，步骤2可以计算它们的和

4. **任务完成判断**：
   - 用户请求"搜索文件并总结" → 必须完成搜索+读取+总结才算完成
   - 用户请求"计算两个数并保存" → 必须完成读取+计算+写入才算完成
   - 用户请求"访问网站并保存摘要" → 必须完成访问+分析+保存才算完成

5. **高效执行**：尽量减少不必要的步骤，但确保所有要求都已完成

6. **结果呈现规则**：用户在意的数据（进程列表、文件内容、配置值等）要**直接展示**，不要用"已成功获取…"来敷衍。如果工具返回了具体数据，原样呈现给用户。

7. **错误处理**：如果工具返回错误，检查参数是否正确后重试，或报告错误

7. **run_command 工具**：执行系统命令。调用时系统会自动注入平台信息（Windows/Linux）和语法提示，LLM 据此生成正确命令。description 参数必填。

8. **activate_coach 工具**：激活写作/软实力教练模式进行持续对话。参数 skill 选:
   - `soft-skills-coach`：沟通困难、活动焦虑、表达紧张、人际冲突、谈判受阻
   - `academic-paper-writer`：毕业论文、期刊论文、文献综述、引用格式(APA/MLA/GB-T7714)、期刊投稿。用户说"论文"/"文献"/"引用格式"时触发
   - `article-writer`：博客、公众号文章、评论、科普文、专栏稿。用户说"写文章"/"博客"/"公众号"时触发（注意与论文区分）
   - `book-review-writer`：读书心得、读后感、书评。用户说"心得"/"读后感"/"书评"/"这本书"时触发（注意与普通文章区分）

9. **天气查询**：用户查询某地天气时，优先使用以下 URL 模板：
   - 中文详细天气: https://www.tianqi.com/{城市拼音}/
   - 英文简洁天气: https://wttr.in/{CityName}?format=4
   例如查询都江堰: https://www.tianqi.com/dujiangyan/ 或 https://wttr.in/Dujiangyan?format=4

## 链式调用示例

### 示例1: 文件搜索并总结
用户: "查找 practice06 目录下包含 def 的文件并总结"
步骤1: search_files(directory_path="practice06", keyword="def")
  → 结果: {"matches": [{"name": "tool_client.py"}, ...]}
步骤2: read_file(directory_path="practice06", file_name="tool_client.py")
  → 结果: {"content": "文件内容..."}
步骤3: 输出 {"done": true, "answer": "总结内容..."}

### 示例2: 多文件计算
用户: "读取 1.txt 和 2.txt，计算两数之和写入 result.txt"
步骤1: read_file(directory_path="practice07", file_name="1.txt")
  → 结果: {"content": "42"}
步骤2: read_file(directory_path="practice07", file_name="2.txt")
  → 结果: {"content": "58"}
步骤3: write_file(directory_path="practice07", file_name="result.txt", content="100")
  → 结果: {"success": true}
步骤4: 输出 {"done": true, "answer": "已计算 42+58=100，结果已写入 result.txt"}"""



# ---------------------------------------------------------------------------
# 7. 链式调用执行
# ---------------------------------------------------------------------------

def execute_chained_tool_call(user_request, base_url, api_key, model):
    """执行链式工具调用的完整流程。

    返回: 最终答案字符串
    """
    context = ChainedCallContext(max_iterations=10)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    while not context.is_exceeded():
        # 构建包含历史信息的分析提示词
        analysis_prompt = build_analysis_prompt(user_request, context)

        # 发送给 LLM（纯 JSON content 模式，不依赖 function calling API）
        round_messages = messages + [
            {"role": "user", "content": analysis_prompt},
        ]

        debug_print(f"[iter={context.current_step+1}] calling LLM ({len(json.dumps(round_messages, ensure_ascii=False))} chars)...")
        t0 = time.time()
        response = call_openai(round_messages, base_url, api_key, model)
        elapsed = time.time() - t0

        if response.get("error"):
            debug_print(f"[iter={context.current_step+1}] LLM error: {response['error']}")
            return f"LLM 调用错误: {response['error']}"

        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {}) if choice else {}
        debug_print(f"[iter={context.current_step+1}] resp {elapsed:.1f}s, finish={choice.get('finish_reason','?')}, content={len(message.get('content',''))}chars: {message.get('content','')[:100]}")

        # 记录助手消息（如果有内容）
        if message.get("content"):
            messages.append({"role": "assistant", "content": message["content"]})

        decision = parse_chained_response(message)
        debug_print(f"[iter={context.current_step+1}] decision: done={decision.get('done') if decision else 'None'}, tool={decision.get('tool_call',{}).get('name','-') if decision else '-'}")
        if decision is None:
            messages.append({"role": "assistant", "content": "无法解析响应"})
            context.record_step("__parse_error__", {}, {"raw_message": str(message)})
            continue

        # 任务完成
        if decision.get("done"):
            debug_print(f"[iter={context.current_step+1}] chain complete: {context.current_step} tools called, answer={len(decision.get('answer',''))} chars")
            return decision.get("answer", "")

        # 需要调用工具
        tool_call = decision.get("tool_call", {})
        tool_name = tool_call.get("name", "")
        arguments = tool_call.get("arguments", {})

        # activate_coach: 进入教练对话模式（特殊处理）
        if tool_name == "activate_coach":
            skill_name = arguments.get("skill", "")
            if skill_name in COACH_SKILLS:
                debug_print(f"[iter={context.current_step+1}] entering coaching mode: {skill_name}")
                execute_coaching_session(skill_name, user_request, base_url, api_key, model)
                return ""  # 教练模式已处理，返回空字符串让 run_agent 不重复打印
            else:
                debug_print(f"[iter={context.current_step+1}] unknown coach skill: {skill_name}")
                context.record_step(tool_name, arguments, {"error": f"Unknown coach skill: {skill_name}"})
                messages.append({"role": "user", "content": f"未知的教练 skill: {skill_name}，请重新选择。"})
                continue

        if not tool_name or tool_name not in TOOL_REGISTRY:
            err = f"未知或不可用的工具: {tool_name}"
            messages.append({"role": "assistant", "content": err})
            context.record_step(tool_name, arguments, {"error": err})
            continue

        # 如果工具有关联的 SKILL.md，注入正文提醒 LLM 纠正命令
        skill_body = _get_skill_body(tool_name)
        debug_print(f"[iter={context.current_step+1}] skill_body for {tool_name}: {'found' if skill_body else 'NOT FOUND'} ({len(skill_body) if skill_body else 0} chars)")
        if skill_body:
            refine_prompt = f"""[系统注入] 你决定调用工具「{tool_name}」，当前参数为：
{json.dumps(arguments, ensure_ascii=False, indent=2)}

该工具的详细操作规范见下方。请对照规范检查参数（特别是 command 字段），纠正后重新输出完整的工具调用 JSON：

{skill_body}

只输出 JSON: {{"done": false, "tool_call": {{"name": "{tool_name}", "arguments": {{...}}}}}}"""
            messages.append({"role": "user", "content": refine_prompt})

            refine_response = call_openai(messages, base_url, api_key, model)
            debug_print(f"[iter={context.current_step+1}] refine resp: error={bool(refine_response.get('error'))}")
            if not refine_response.get("error"):
                refine_choice = refine_response.get("choices", [{}])[0]
                refine_message = refine_choice.get("message", {}) if refine_choice else {}
                if refine_message.get("content"):
                    messages.append({"role": "assistant", "content": refine_message["content"]})
                refined_decision = parse_chained_response(refine_message)
                if refined_decision and not refined_decision.get("done"):
                    refined_tc = refined_decision.get("tool_call", {})
                    if refined_tc.get("name") == tool_name:
                        arguments = refined_tc.get("arguments", arguments)
                        debug_print(f"[iter={context.current_step+1}] skill refine OK -> command: {arguments.get('command','')[:80]}")
                    else:
                        debug_print(f"[iter={context.current_step+1}] skill refine FAIL: tool name mismatch ({refined_tc.get('name')} != {tool_name})")
                else:
                    debug_print(f"[iter={context.current_step+1}] skill refine FAIL: done=True or no valid JSON in refined response")
            else:
                debug_print(f"[iter={context.current_step+1}] skill refine FAIL: LLM error - {refine_response.get('error')}")

        debug_print(f"[iter={context.current_step+1}] executing: {tool_name}({', '.join(f'{k}={str(v)[:30]}' for k,v in arguments.items())})")
        t0 = time.time()
        result = execute_tool(tool_name, arguments)
        elapsed = time.time() - t0
        debug_print(f"[iter={context.current_step+1}] tool done in {elapsed:.1f}s, success={not result.get('error')}")
        context.record_step(tool_name, arguments, result)

        # 将工具执行结果以纯文本形式加入消息历史
        result_str = json.dumps(result, ensure_ascii=False)
        if len(result_str) > 2000:
            result_str = result_str[:2000] + "...(truncated)"
        result_msg = f"[工具 {tool_name} 执行结果]\n{result_str}"
        messages.append({"role": "user", "content": result_msg})

    return "达到最大迭代次数，任务未完成。已执行步骤: " + context.get_history_summary()


# ---------------------------------------------------------------------------
# 8. 教练对话模式（多轮对话型 skill）
# ---------------------------------------------------------------------------

COACH_SKILLS = {"soft-skills-coach", "academic-paper-writer", "article-writer", "book-review-writer"}


def _build_tools_help_text():
    """构建教练模式下给 LLM 看的工具说明。"""
    tools = []
    for name, info in TOOL_REGISTRY.items():
        if name == "activate_coach":
            continue
        params = ", ".join(
            f"{k}({v.get('description','')})" for k, v in info["parameters"]["properties"].items()
        )
        tools.append(f"- **{name}**: {info['description']}\n  参数: {params}")
    return "\n".join(tools)


def execute_coaching_session(skill_name, user_request, base_url, api_key, model):
    """教练模式：用 SKILL.md 正文作 system prompt，进行持续多轮对话。

    LLM 可以调用 read_file/write_file 工具读写文件。
    用户输入 /exit 或 /done 退出教练模式。"""
    skill_body = _get_skill_body(skill_name)
    if not skill_body:
        print(f"Error: 无法加载 skill {skill_name} 的内容")
        return

    messages = [
        {"role": "system", "content": skill_body},
    ]

    # 初始化：读取 skill 目录下已有的状态文件注入上下文
    skill_path = os.path.join(get_project_root(), ".agent", "skill", skill_name)
    if os.path.isdir(skill_path):
        for fname in sorted(os.listdir(skill_path)):
            if fname.endswith(".md") and fname != "SKILL.md":
                fpath = os.path.join(skill_path, fname)
                content = tool_read_file(
                    os.path.relpath(os.path.dirname(fpath), get_project_root()),
                    fname,
                )
                if content.get("content"):
                    messages.append({
                        "role": "system",
                        "content": f"[已有文件 {fname}]\n{content['content'][:2000]}",
                    })

    # 注入可用工具说明
    tools_help = _build_tools_help_text()
    messages.append({
        "role": "system",
        "content": f"""## 可用工具说明

你可以调用以下工具。在回复中，如果需要操作文件，将工具调用以 JSON 格式嵌在回复末尾：

{tools_help}

### 使用方式
当你需要写入文件时，在回复末尾添加（单独一行）：
```json
{{"name": "write_file", "arguments": {{"directory_path": "book-review-writer/wip", "file_name": "topic.md", "content": "文件内容..."}}}}
```

当你需要读取文件时：
```json
{{"name": "read_file", "arguments": {{"directory_path": ".agent/skill/book-review-writer/wip", "file_name": "topic.md"}}}}
```

注意：`directory_path` 必须是相对于项目根目录的路径。写文件时 `content` 字段包含完整的文件内容。""",
    })

    # 首轮用户消息
    messages.append({
        "role": "user",
        "content": f"用户当前说: {user_request}\n\n请按照你的 SKILL.md 流程回应。",
    })

    print(f"\n{'='*60}")
    print(f" 教练模式: {skill_name}")
    print(f" 输入 /exit 退出教练模式，/done 结束本次场景并复盘")
    print(f"{'='*60}")

    while True:
        t0 = time.time()
        response = call_openai(messages, base_url, api_key, model)
        elapsed = time.time() - t0

        if response.get("error"):
            print(f"LLM 错误: {response['error']}")
            break

        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {}) if choice else {}
        content = message.get("content", "")

        # 检查是否需要工具调用（优先检查 OpenAI tool_calls，再检查嵌入 JSON）
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            # 从文本内容中检测工具调用 JSON
            json_str = _extract_json(content)
            if json_str:
                try:
                    tool_data = json.loads(json_str)
                    if isinstance(tool_data, dict) and "name" in tool_data and "arguments" in tool_data:
                        tool_calls = [{
                            "id": "call_1",
                            "type": "function",
                            "function": tool_data,
                        }]
                    elif isinstance(tool_data, dict) and "tool_call" in tool_data:
                        tc = tool_data["tool_call"]
                        if isinstance(tc, dict) and "name" in tc:
                            tool_calls = [{
                                "id": "call_1",
                                "type": "function",
                                "function": tc,
                            }]
                except (json.JSONDecodeError, TypeError):
                    pass
        if tool_calls:
            tc = tool_calls[0]
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            try:
                tool_args = func.get("arguments", "{}")
                if isinstance(tool_args, str):
                    tool_args = json.loads(tool_args)
            except (json.JSONDecodeError, TypeError):
                tool_args = {}

            if tool_name in TOOL_REGISTRY and tool_name != "activate_coach":
                tool_result = execute_tool(tool_name, tool_args)
                if tool_name in ("write_file", "read_file"):
                    print(f"\n   [{tool_name}] {tool_args.get('file_name', '')} "
                          f"{'写入成功' if tool_result.get('success') or tool_result.get('content') else str(tool_result.get('error',''))}")
                else:
                    print(f"\n   [{tool_name}] 已执行")
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tc.get("id", "call_1"),
                        "type": "function",
                        "function": func,
                    }],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", "call_1"),
                    "content": json.dumps(tool_result, ensure_ascii=False),
                })
                debug_print(f"[coach] tool executed: {tool_name}")
                continue  # 不显示 content，等下一轮 LLM 响应

        if content:
            print(f"\nCoach: {content}")
            messages.append({"role": "assistant", "content": content})

        # 用户输入
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n退出教练模式。")
            break

        if not user_input:
            continue
        if user_input == "/exit":
            print("退出教练模式。")
            break
        if user_input == "/done":
            messages.append({
                "role": "user",
                "content": "场景结束了，请按照 SKILL.md 的 Step 2 进行复盘（包括写入 patterns.md）。",
            })
            continue

        messages.append({"role": "user", "content": user_input})


# ---------------------------------------------------------------------------
# 8. 交互式代理
# ---------------------------------------------------------------------------

def run_agent():
    root = get_project_root()
    local_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(local_env):
        load_env_file(local_env)
    load_env_file(os.path.join(root, ".env"))
    debug_init()

    base_url = os.environ.get("BASE_URL", "http://127.0.0.1:8080/v1")
    api_key = os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("MODEL") or os.environ.get("OPENAI_MODEL", "")
    if not model:
        model = "gpt-3.5-turbo"

    if not base_url:
        print("Missing BASE_URL in .env")
        return

    print("=" * 60)
    print("Chained Tool Client — 链式工具调用代理")
    print(f"可用工具: {', '.join(TOOL_REGISTRY.keys())}")
    print("输入 /exit 退出")
    print("=" * 60)

    while True:
        try:
            user_input = input("\nUser: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExit.")
            break
        if not user_input:
            continue
        if user_input == "/exit":
            print("Exit.")
            break

        print("[执行链式调用...]")
        answer = execute_chained_tool_call(user_input, base_url, api_key, model)
        if answer:
            print(f"\nAssistant: {answer}")


if __name__ == "__main__":
    run_agent()
