#!/usr/bin/env python3
"""Tool Client — 技能列表读取与技能正文加载代理"""

import json
import os
import re
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import yaml


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


def list_available_skills(skill_dir):
    """扫描 skill_dir 下所有一级子目录，读取 SKILL.md YAML front matter，
    提取 name 和 description 字段，返回技能列表。"""
    skills = []
    if not os.path.isdir(skill_dir):
        return skills

    for item in os.listdir(skill_dir):
        skill_path = os.path.join(skill_dir, item)
        if not os.path.isdir(skill_path):
            continue

        skill_md = None
        for md_name in ["SKILL.md", "skill.md"]:
            md_path = os.path.join(skill_path, md_name)
            if os.path.isfile(md_path):
                skill_md = md_path
                break

        if not skill_md:
            continue

        try:
            with open(skill_md, "r", encoding="utf-8") as f:
                content = f.read()

            frontmatter_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
            if frontmatter_match:
                frontmatter = yaml.safe_load(frontmatter_match.group(1))
                skills.append({
                    "name": frontmatter.get("name", item),
                    "description": frontmatter.get("description", "").strip(),
                    "dir_name": item,
                })
            else:
                skills.append({
                    "name": item,
                    "description": "",
                    "dir_name": item,
                })
        except Exception as e:
            print(f"Warning: Failed to parse skill {item}: {e}")

    return skills


def load_skill_content(skill_dir, dir_name):
    """加载指定技能的 SKILL.md 正文内容（YAML front matter 之后的部分）。"""
    skill_path = os.path.join(skill_dir, dir_name)
    if not os.path.isdir(skill_path):
        return None

    for md_name in ["SKILL.md", "skill.md"]:
        md_path = os.path.join(skill_path, md_name)
        if os.path.isfile(md_path):
            break
    else:
        return None

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    frontmatter_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if frontmatter_match:
        body = content[frontmatter_match.end():].strip()
    else:
        body = content.strip()

    return body


SYSTEM_PROMPT = """你是一个智能工具客户端助手。你可以根据用户的需求，从可用技能列表中选择合适的技能来回答。

## 可用技能列表 (JSON)
```json
{skill_list}
```

## 工作规则
1. 首先阅读「可用技能列表」，理解每个技能的用途
2. 判断用户的需求是否匹配某个技能：
   - 如果匹配：**仅输出**以下格式的 JSON 请求，不要输出任何其他内容：
     ```json
     {{"skill": "技能的name字段", "task": "用户想要完成的具体任务描述"}}
     ```
   - 如果不匹配：以普通对话方式直接回应用户
3. 判断匹配时，对照技能的 description 字段，只要用户意图与技能描述相关即可触发
4. task 字段要用中文详细描述用户想完成的具体任务"""


def call_openai(messages, base_url, api_key, model):
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    data = {
        "model": model,
        "messages": messages,
    }

    try:
        req = Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError) as e:
        return {"error": str(e)}


def parse_skill_request(text):
    """从 LLM 返回文本中解析技能请求 JSON。"""
    if not text:
        return None

    patterns = [
        r'```json\s*(\{[^{]*"skill"\s*:\s*"[^"]+"[^{]*"task"\s*:\s*"[^"]+"[^{}]*\})\s*```',
        r'```\s*(\{[^{]*"skill"\s*:\s*"[^"]+"[^{]*"task"\s*:\s*"[^"]+"[^{}]*\})\s*```',
        r'\{[^{}]*"skill"\s*:\s*"[^"]+"[^{}]*"task"\s*:\s*"[^"]+"[^{}]*\}',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1) if match.lastindex else match.group())
                if "skill" in data and "task" in data:
                    return data
            except (json.JSONDecodeError, IndexError):
                continue

    return None


def run_agent():
    root = get_project_root()

    local_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(local_env):
        load_env_file(local_env)
    load_env_file(os.path.join(root, ".env"))

    base_url = os.environ.get("BASE_URL", "http://127.0.0.1:8080/v1")
    api_key = os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("MODEL") or os.environ.get("OPENAI_MODEL", "")
    if not model:
        model = "gpt-3.5-turbo"

    if not base_url:
        print("Missing BASE_URL in .env")
        return

    skill_dir = os.path.join(root, ".agent", "skill")

    print("=" * 50)
    print("Tool Client — 技能列表读取与正文加载代理")
    print("输入 /exit 退出")
    print("每次输入时自动扫描 .agent/skill/ 下的可用技能")
    print("=" * 50)

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

        # —— 第1轮：发送技能列表，让 LLM 决定是否需要技能 ——

        skills = list_available_skills(skill_dir)
        skill_list_json = json.dumps({"skills": skills}, ensure_ascii=False, indent=2)

        if skills:
            print(f"[skills] 发现 {len(skills)} 个可用技能")

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(skill_list=skill_list_json),
            },
            {"role": "user", "content": user_input},
        ]

        response = call_openai(messages, base_url, api_key, model)

        if response.get("error"):
            print(f"Error: {response['error']}")
            continue

        choice = response.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")

        skill_request = parse_skill_request(content)

        if skill_request:
            skill_name = skill_request["skill"]
            task = skill_request["task"]

            matched = None
            for s in skills:
                if s["name"] == skill_name:
                    matched = s
                    break

            if matched:
                print(f"[skill] 加载技能: {skill_name}")

                skill_body = load_skill_content(skill_dir, matched["dir_name"])
                if skill_body is None:
                    print(f"Error: 无法加载技能 {skill_name} 的内容")
                    continue

                # —— 第2轮：将技能正文作为 system prompt 发送给 LLM 执行 ——
                exec_messages = [
                    {
                        "role": "system",
                        "content": f"""你是一个技能执行器。以下是技能「{skill_name}」的详细操作指南，请严格按照技能内容来执行用户的任务。

## 技能描述
{matched['description']}

## 技能详细内容
{skill_body}

## 执行规则
- 严格按照上述技能内容中的指示操作
- 如果技能定义了角色扮演规则，请以对应的身份回应
- 如果技能有使用说明/限制，务必遵守""",
                    },
                    {"role": "user", "content": task},
                ]

                exec_response = call_openai(exec_messages, base_url, api_key, model)
                if exec_response.get("error"):
                    print(f"Error: {exec_response['error']}")
                else:
                    exec_content = (
                        exec_response.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                    print(f"\nAssistant: {exec_content}")
            else:
                print(f"Error: 未找到技能 '{skill_name}'")
        else:
            print(f"\nAssistant: {content}")


if __name__ == "__main__":
    run_agent()
