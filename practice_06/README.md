# Tool Client — 技能列表读取与正文加载代理

基于 `practice_05/skill_agent.py` 重构的技能调用代理，核心区别：

1. **技能列表通过 system prompt JSON 发送**（而非 OpenAI function calling tools）
2. **技能正文通过 system prompt 动态加载**（而非 `read_skill_content` 读取整个目录）

## 核心函数

### `list_available_skills(skill_dir)`
- 每次用户输入时自动扫描 `.agent/skill/` 下所有一级子目录
- 读取 `SKILL.md` 的 YAML front matter
- 提取 `name` 和 `description` 字段
- 返回技能列表

### `load_skill_content(skill_dir, dir_name)`
- 当 LLM 判断需要使用某技能时调用
- 加载 `SKILL.md` 正文内容（YAML front matter 之后的部分）
- 通过 system prompt 发送给 LLM 遵照执行

## 工作流程

1. 用户输入 → 扫描技能列表，以 JSON 格式 `{"skills": [...]}` 通过 system prompt 发送给 LLM
2. LLM 判断是否匹配技能：
   - 匹配 → 返回 JSON `{"skill": "...", "task": "..."}`
   - 不匹配 → 直接回应用户
3. 加载技能正文 → 作为 system prompt 发送 → LLM 遵照执行

## 运行方式

```bash
cd practice_06
python tool_client.py
```

## 测试

```bash
cd practice_06
python test_tool_client.py
```

## Notice 技能测试结果

| 测试场景 | 用户输入 | 预期开头 | 实际结果 |
|----------|----------|----------|----------|
| 不告知部门 | "帮我写一个关于五一劳动节放假的通知" | `XX部通知` | `XX部通知` 通过 |
| 告知销售部 | "我是销售部的，帮我写一个关于五一劳动节放假的通知" | `销售部通知` | `销售部通知` 通过 |

技能正文加载：759 字符，不含 YAML front matter，JSON 解析支持纯 JSON、markdown 代码块、普通代码块、嵌入文本等格式。
