#!/usr/bin/env python3
"""AnythingLLM 查询模块 - 通过API查询工作区文档。

功能：
- 使用 subprocess 调用 curl 访问 AnythingLLM 的聊天API
- 支持中文编码
- 从 .env 读取 API_KEY 和 WORKSPACE_SLUG
"""

import os
import json
import subprocess


def get_project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env_file(env_path):
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def anythingllm_query(message, workspace_slug=None, api_key=None):
    """调用 AnythingLLM API 查询工作区文档。

    Args:
        message: 查询消息
        workspace_slug: 工作区Slug ID（可选，从环境变量读取）
        api_key: API密钥（可选，从环境变量读取）

    Returns:
        dict: API响应结果
    """
    project_root = get_project_root()
    load_env_file(os.path.join(project_root, ".env"))

    if not api_key:
        api_key = os.environ.get("ANYTHINGLLM_API_KEY")
    if not workspace_slug:
        workspace_slug = os.environ.get("ANYTHINGLLM_WORKSPACE_SLUG")

    if not api_key or api_key == "your_anythingllm_api_key_here":
        return {"error": "请在 .env 文件中配置 ANYTHINGLLM_API_KEY"}
    if not workspace_slug or workspace_slug == "your_workspace_slug_here":
        return {"error": "请在 .env 文件中配置 ANYTHINGLLM_WORKSPACE_SLUG"}

    api_url = f"http://localhost:3001/api/v1/workspace/{workspace_slug}/chat"

curl_cmd = [
        "curl",
        "-s",
        "-X", "POST",
        api_url,
        "-H", "Content-Type: application/json; charset=utf-8",
        "-H", f"Authorization: Bearer {api_key}",
        "--data-binary", json.dumps({"message": message}, ensure_ascii=False)
    ]

    try:
        result = subprocess.run(
            curl_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )

        if result.returncode != 0:
            return {"error": f"Curl错误: {result.stderr}"}

        try:
            response = json.loads(result.stdout)
            return response
        except json.JSONDecodeError:
            return {"raw_response": result.stdout, "error": "JSON解析失败"}

    except subprocess.TimeoutExpired:
        return {"error": "请求超时"}
    except Exception as e:
        return {"error": str(e)}


def query_workspace(query):
    """简化的查询接口，用于 function calling。

    Args:
        query: 查询内容

    Returns:
        str: 格式化后的响应结果
    """
    result = anythingllm_query(query)

    if "error" in result:
        return f"查询失败: {result['error']}"

    if "response" in result:
        return result["response"]

    if "text" in result:
        return result["text"]

    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    test_query = "你好"
    print(f"测试查询: {test_query}")
    result = anythingllm_query(test_query)
    print(f"结果: {result}")
