#!/usr/bin/env python3
"""Skill Agent - 基于SKILL.md的技能调用代理"""

import json
import os
import re
import yaml
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


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


def discover_skills(skill_dir):
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
                body = content[frontmatter_match.end():].strip()
            else:
                frontmatter = {}
                body = content

            skills.append({
                "name": frontmatter.get("name", item),
                "description": frontmatter.get("description", ""),
                "path": skill_path,
                "body": body,
                "dir_name": item
            })
        except Exception as e:
            print(f"Warning: Failed to parse skill {item}: {e}")

    return skills


def build_skill_functions(skills):
    functions = []
    for skill in skills:
        functions.append({
            "type": "function",
            "function": {
                "name": f"use_skill_{skill['dir_name']}",
                "description": skill["description"],
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "用户想要执行的具体任务描述"
                        }
                    },
                    "required": ["task"]
                },
                "strict": True
            }
        })
    return functions


def read_skill_content(skill_path):
    content_parts = []
    for root, dirs, files in os.walk(skill_path):
        rel_root = os.path.relpath(root, skill_path)
        for file in sorted(files):
            file_path = os.path.join(root, file)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    file_content = f.read()
                content_parts.append(f"## File: {rel_root}/{file}\n\n{file_content}\n")
            except Exception as e:
                content_parts.append(f"## File: {rel_root}/{file}\n[Error reading: {e}]\n")
    return "\n\n".join(content_parts)


SYSTEM_PROMPT = """你是一个技能助手。你的任务是根据用户的需求，从已知的技能列表中选择合适的技能来完成任务。

## 可用技能
{skill_list}

## 重要规则
1. 仔细理解用户的需求
2. 选择最匹配用户需求的技能
3. 直接调用技能函数，不要询问用户确认
4. 如果不确定用户需求，可以直接猜测最可能的意图并执行

## 调用格式
当需要使用某个技能时，调用对应的函数，task参数描述用户想要完成的具体任务。"""


def call_openai(messages, base_url, api_key, model, functions=None):
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    data = {
        "model": model,
        "messages": messages,
    }
    if functions:
        data["tools"] = functions
        data["tool_choice"] = "auto"

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

    for pattern in [
        r'<\|tool_call>call:(\w+)\{([^}]+)\}<tool_call\|>',
        r'<\|tool_call>call:\s*(\w+)\(([^)]+)\)',
        r'"function_call"\s*:\s*\{\s*"name"\s*:\s*"([^"]+)"[^}]*"arguments"\s*:\s*\{([^}]+)\}',
    ]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                if "function_call" in pattern:
                    name = match.group(1)
                    args_str = match.group(2)
                else:
                    name = match.group(1)
                    args_str = match.group(2)

                if name.startswith("use_skill_"):
                    skill_name = name.replace("use_skill_", "")
                    args = {}
                    for arg in args_str.split(","):
                        if ":" in arg:
                            key, val = arg.split(":", 1)
                            key = key.strip().strip('"')
                            val = re.sub(r'<\|\"\|>', '', val).strip().strip('"')
                            args[key] = val
                    return {"name": name, "arguments": json.dumps(args)}
            except:
                pass

    json_match = re.search(r'\{[^{}]*"name"\s*:\s*"use_skill_[^"]+"[^{}]*"arguments"\s*:\s*\{[^}]+\}[^}]*\}', text)
    if json_match:
        try:
            data = json.loads(json_match.group())
            name = data.get("name", "")
            args = data.get("arguments", {})
            if name.startswith("use_skill_"):
                if isinstance(args, str):
                    args = json.loads(args)
                return {"name": name, "arguments": json.dumps(args)}
        except:
            pass

    return None


def execute_skill(skill_dir_name, task, skill_dir, skills):
    skill = next((s for s in skills if s["dir_name"] == skill_dir_name), None)
    if not skill:
        return {"error": f"Skill not found: {skill_dir_name}"}

    skill_content = read_skill_content(skill["path"])

    messages = [
        {
            "role": "system",
            "content": f"""你是一个技能执行器。技能目录位于: {skill['path']}
技能内容:
{skill_content}

你的任务是根据用户的要求 {task} 执行相应的操作。"""
        },
        {"role": "user", "content": f"请执行任务: {task}"}
    ]

    base_url = os.environ.get("BASE_URL", "http://127.0.0.1:8080/v1")
    api_key = os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("MODEL") or os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")

    response = call_openai(messages, base_url, api_key, model, functions=None)
    if response.get("error"):
        return {"error": response["error"], "skill_content": skill_content}

    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    return {
        "skill": skill["name"],
        "task": task,
        "result": content,
        "skill_content": skill_content
    }


def run_agent():
    root = get_project_root()
    load_env_file(os.path.join(root, ".env"))

    base_url = os.environ.get("BASE_URL", "http://127.0.0.1:8080/v1")
    api_key = os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("MODEL") or os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")

    if not base_url:
        print("Missing BASE_URL in .env")
        return

    skill_dir = os.path.join(root, ".agent", "skill")
    skills = discover_skills(skill_dir)

    if not skills:
        print(f"No skills found in {skill_dir}")
        print("Please create skills in .agent/skill/ directory")
        return

    print(f"Discovered {len(skills)} skills:")
    for s in skills:
        print(f"  - {s['name']}: {s['description']}")
    print("\nSkill agent started. Input /exit to quit.")
    print("Available skills: " + ", ".join(s["name"] for s in skills))

    functions = build_skill_functions(skills)

    while True:
        user_input = input("\nUser: ").strip()
        if not user_input:
            continue
        if user_input == "/exit":
            print("Exit.")
            break

        skill_list = "\n".join([f"- {s['name']}: {s['description']}" for s in skills])
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.format(skill_list=skill_list)},
            {"role": "user", "content": user_input},
        ]

        response = call_openai(messages, base_url, api_key, model, functions=functions)

        if response.get("error"):
            print(f"Error: {response['error']}")
            continue

        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})

        function_call = message.get("tool_calls", [{}])[0] if message.get("tool_calls") else None
        if function_call:
            function_call = {
                "name": function_call.get("function", {}).get("name"),
                "arguments": function_call.get("function", {}).get("arguments", "{}")
            }

        if not function_call:
            function_call = parse_tool_call(message.get("content", ""))

        if function_call:
            name = function_call.get("name", "")
            try:
                args = json.loads(function_call.get("arguments") or "{}")
            except:
                args = {}

            if name.startswith("use_skill_"):
                skill_dir_name = name.replace("use_skill_", "")
                task = args.get("task", "")

                print(f"Calling skill: {skill_dir_name}")
                result = execute_skill(skill_dir_name, task, skill_dir, skills)
                print(f"Result: {json.dumps(result, ensure_ascii=False, indent=2)}")
            else:
                print(f"Unknown function: {name}")
        else:
            print(f"Assistant: {message.get('content', 'No response.')}")


if __name__ == "__main__":
    run_agent()