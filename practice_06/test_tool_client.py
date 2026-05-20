#!/usr/bin/env python3
"""测试 tool_client.py 的 notice 技能 — 不依赖 LLM 服务器"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tool_client import (
    get_project_root,
    list_available_skills,
    load_skill_content,
    parse_skill_request,
    SYSTEM_PROMPT,
)


def mock_llm_skill_request():
    """模拟 LLM 在第1轮返回的技能请求 JSON（不告知部门）"""
    return '{"skill": "notice", "task": "帮我写一个关于五一劳动节放假的通知"}'


def mock_llm_skill_request_dept():
    """模拟 LLM 在第1轮返回的技能请求 JSON（告知销售部）"""
    return '{"skill": "notice", "task": "我是销售部的，帮我写一个关于五一劳动节放假的通知"}'


def mock_llm_skill_execution_no_dept():
    """模拟 LLM 执行技能后生成的 XX部通知"""
    return """XX部通知

根据国家法定节假日安排，现将五一劳动节放假事宜通知如下：

一、放假时间：5月1日至5月5日，共5天。
二、4月27日（周日）正常上班。
三、请各部门做好节前工作安排和安全检查。
四、放假期间请保持通讯畅通。

XX部
2026年4月25日"""


def mock_llm_skill_execution_sales():
    """模拟 LLM 执行技能后生成的销售部通知"""
    return """销售部通知

根据国家法定节假日安排，现将五一劳动节放假事宜通知如下：

一、放假时间：5月1日至5月5日，共5天。
二、4月27日（周日）正常上班。
三、请各位同事做好节前客户对接和订单处理。
四、放假期间紧急事务请联系值班人员。

销售部
2026年4月25日"""


def test():
    root = get_project_root()
    skill_dir = os.path.join(root, ".agent", "skill")

    # ---- 技能发现测试 ----
    print("=" * 60)
    print("技能发现测试")
    print("=" * 60)
    skills = list_available_skills(skill_dir)
    skill_names = [s["name"] for s in skills]
    print(f"发现技能: {skill_names}")

    assert "notice" in skill_names, "notice 技能未发现"
    print("[PASS] notice 技能已发现")

    notice_skill = next(s for s in skills if s["name"] == "notice")
    assert notice_skill["description"], "notice 技能描述为空"
    print(f"   name: {notice_skill['name']}")
    print(f"   description: {notice_skill['description'][:80]}...")
    print(f"   dir_name: {notice_skill['dir_name']}")

    # ---- 技能列表 JSON 格式测试 ----
    print("\n" + "=" * 60)
    print("技能列表 JSON 格式测试")
    print("=" * 60)
    skill_list_json = json.dumps({"skills": skills}, ensure_ascii=False, indent=2)
    parsed = json.loads(skill_list_json)
    assert "skills" in parsed, "缺少 skills 字段"
    assert isinstance(parsed["skills"], list), "skills 应为数组"
    assert len(parsed["skills"]) >= 1, "技能列表为空"
    for s in parsed["skills"]:
        assert "name" in s, f"技能缺少 name 字段: {s}"
        assert "description" in s, f"技能缺少 description 字段: {s}"
    print("[PASS] JSON 格式正确")
    print(f"   skills 数量: {len(parsed['skills'])}")

    # ---- 技能正文加载测试 ----
    print("\n" + "=" * 60)
    print("技能正文加载测试")
    print("=" * 60)
    body = load_skill_content(skill_dir, notice_skill["dir_name"])
    assert body is not None, "技能正文加载失败"
    assert len(body) > 0, "技能正文为空"
    print(f"[PASS] 技能正文已加载，共 {len(body)} 字符")
    print(f"   正文前 100 字符: {body[:100]}...")

    # ---- 验证正文不含 front matter ----
    assert not body.startswith("---"), "正文不应包含 YAML front matter"
    print("[PASS] 正文不包含 YAML front matter")

    # ---- System prompt 格式测试 ----
    print("\n" + "=" * 60)
    print("System Prompt 格式测试")
    print("=" * 60)
    prompt = SYSTEM_PROMPT.format(skill_list=skill_list_json)
    assert "notice" in prompt, "system prompt 应包含 notice 技能"
    assert '"skills"' in prompt, "system prompt 应包含 skills JSON"
    print("[PASS] System prompt 包含技能列表 JSON")

    # ---- 技能请求解析测试 ----
    print("\n" + "=" * 60)
    print("技能请求解析测试")
    print("=" * 60)

    # 测试 1: 纯 JSON
    req = parse_skill_request('{"skill": "notice", "task": "写通知"}')
    assert req is not None, "解析纯 JSON 失败"
    assert req["skill"] == "notice"
    assert req["task"] == "写通知"
    print("[PASS] 纯 JSON 解析通过")

    # 测试 2: markdown 代码块
    req = parse_skill_request('```json\n{"skill": "notice", "task": "写通知"}\n```')
    assert req is not None, "解析 markdown JSON 代码块失败"
    assert req["skill"] == "notice"
    print("[PASS] Markdown JSON 代码块解析通过")

    # 测试 3: 普通代码块
    req = parse_skill_request('```\n{"skill": "notice", "task": "写通知"}\n```')
    assert req is not None, "解析普通代码块失败"
    assert req["skill"] == "notice"
    print("[PASS] 普通代码块解析通过")

    # 测试 4: JSON 嵌入文本中
    req = parse_skill_request('我认为应该使用 {"skill": "notice", "task": "写通知"} 这个技能')
    assert req is not None, "解析嵌入文本中的 JSON 失败"
    assert req["skill"] == "notice"
    print("[PASS] 嵌入文本 JSON 解析通过")

    # ---- 模拟完整流程测试 ----
    print("\n" + "=" * 60)
    print("测试 1: 用户不告知部门 → 应输出 XX部通知")
    print("=" * 60)

    user_input = "帮我写一个关于五一劳动节放假的通知"
    print(f"用户输入: {user_input}")

    # 第1轮：LLM 返回技能请求
    llm_response = mock_llm_skill_request()
    print(f"LLM 技能请求: {llm_response}")
    skill_request = parse_skill_request(llm_response)
    assert skill_request is not None, "解析技能请求失败"
    print(f"解析结果: skill={skill_request['skill']}, task={skill_request['task']}")

    # 加载技能正文
    body = load_skill_content(skill_dir, notice_skill["dir_name"])
    print(f"加载技能正文: {len(body)} 字符")

    # 第2轮：模拟 LLM 执行技能
    result = mock_llm_skill_execution_no_dept()
    print(f"\n技能执行结果:\n{result}")

    assert "XX部通知" in result[:20], f"结果应以 XX部通知 开头，实际: {result[:20]}"
    print("[PASS] 测试 1 通过：输出以「XX部通知」开头")

    # ---- 测试 2: 告知销售部 ----
    print("\n" + "=" * 60)
    print("测试 2: 用户告知销售部 → 应输出 销售部通知")
    print("=" * 60)

    user_input_2 = "我是销售部的，帮我写一个关于五一劳动节放假的通知"
    print(f"用户输入: {user_input_2}")

    llm_response_2 = mock_llm_skill_request_dept()
    print(f"LLM 技能请求: {llm_response_2}")
    skill_request_2 = parse_skill_request(llm_response_2)
    assert skill_request_2 is not None, "解析技能请求失败"
    print(f"解析结果: skill={skill_request_2['skill']}, task={skill_request_2['task']}")

    body = load_skill_content(skill_dir, notice_skill["dir_name"])
    result_2 = mock_llm_skill_execution_sales()
    print(f"\n技能执行结果:\n{result_2}")

    assert "销售部通知" in result_2[:20], f"结果应以 销售部通知 开头，实际: {result_2[:20]}"
    print("[PASS] 测试 2 通过：输出以「销售部通知」开头")

    # ---- 最终总结 ----
    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    test()
