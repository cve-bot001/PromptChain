# Skill Agent - 基于SKILL.md的技能调用代理

本目录实现了一个能够自动发现并调用技能的LLM代理。

## Skill格式规范

遵循 [Agent Skills Specification](https://agentskills.my/specification)：

```markdown
---
name: skill-name
description: 技能描述，当用户请求与此描述匹配的任务时触发
---

技能详细说明（仅在技能被调用时加载）
```

可选文件：
- `agents/openai.yaml` - UI元数据
- 脚本文件 (`*.py`, `*.js`)
- `references/` - 参考文档
- `assets/` - 资源文件

## 技能目录

技能应放在项目根目录的 `.agent/skill/` 目录下：

```
.agent/skill/
├── docx/
│   ├── SKILL.md
│   └── ...
├── pdf/
│   ├── SKILL.md
│   └── ...
└── xlsx/
    ├── SKILL.md
    └── ...
```

## 运行方式

```bash
cd practice_05
python skill_agent.py
```

## 技能发现机制

1. 启动时扫描 `.agent/skill/` 下所有子目录
2. 读取每个子目录中的 `SKILL.md`
3. 解析YAML frontmatter获取 `name` 和 `description`
4. 将技能转换为LLM函数调用格式
5. 模型根据用户请求决定调用哪个技能