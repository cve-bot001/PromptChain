# PromptChain

> Prompt-driven chained tool calling agent for local LLMs

基于纯文本 Prompt 工程驱动的链式工具调用 Agent，专为本地部署的大语言模型设计。无需 OpenAI Function Calling API，任何支持文本对话的模型均可使用。

## 快速开始

```bash
# 1. 环境
conda activate ./venv
pip install -r requirements.txt

# 2. 配置
cp env.example .env   # 编辑 BASE_URL / MODEL
# 模型启动示例: llama-server -m Qwen3.5-9B.Q4_K_M.gguf -ngl 999 -c 32768 --host 127.0.0.1 --port 8080

# 3. 运行
python practice_07/tool_client.py
```

## 核心能力

| 能力 | 说明 |
|------|------|
| 链式工具调用 | 前一步输出作为后一步输入，LLM 自主决策多步编排 |
| Skill 动态注入 | SKILL.md 按需加载，`{{PLATFORM}}`/`{{SHELL}}` 运行时替换 |
| 教练对话模式 | 软实力教练、论文写作、文章写作、读书心得 4 个对话式 Skill |
| 系统命令执行 | Windows/Linux 自动适配，执行前确认，16 条安全规则 |
| 纯 Prompt 驱动 | 不依赖 Function Calling API，JSON 格式决策 + Python 执行 |
| 调试系统 | stderr 分离输出，实时展示每轮耗时、Token 量、决策结果 |

## 架构

```
用户输入 → execute_chained_tool_call()
  ├─ build_analysis_prompt()   # 注入历史 + 工具列表 + 平台信息
  ├─ call_openai()             # HTTP POST 纯文本请求
  ├─ parse_chained_response()  # 提取 JSON 决策
  ├─ _get_skill_body()         # 按需加载 SKILL.md
  ├─ execute_tool()            # 执行 Python 工具函数
  └─ execute_coaching_session()# 对话式教练模式
```

## 可用工具 (7个)

| 工具 | 功能 |
|------|------|
| `list_files` | 列出目录内容 |
| `search_files` | 全文搜索文件关键词 |
| `read_file` | 读取文件内容 |
| `write_file` | 写入文件 |
| `web_fetch` | 抓取网页文本 |
| `run_command` | 执行系统命令 |
| `activate_coach` | 激活教练模式 |

## 可用 Skill (7个)

| Skill | 触发场景 |
|-------|----------|
| `soft-skills-coach` | 沟通困难、活动焦虑、表达紧张 |
| `academic-paper-writer` | 论文/文献综述/引用格式(APA/MLA/GB-T7714) |
| `article-writer` | 博客/公众号/评论/科普文章 |
| `book-review-writer` | 读书心得/书评（先生成4份引导文档） |
| `run_command` | 系统命令执行（平台自适应） |
| `notice` | 通知/公告撰写 |
| `karpathy` | Andrej Karpathy 思维框架 |

## 项目结构

```
PromptChain/
├── .agent/skill/           # Skill 定义 (SKILL.md + 资源文件)
├── practice/               # 基础 LLM API 调用
├── practice_02/            # 流式聊天 + 工具函数调用
├── practice_03/            # 自动摘要 + 上下文压缩
├── practice_04/            # AnythingLLM 集成
├── practice_05/            # Skill 发现与执行
├── practice_06/            # Skill 列表 JSON 注入
├── practice_07/            # ★ 最终版本：链式调用 + 教练模式
│   ├── tool_client.py      #   主程序 (1000+ 行)
│   └── test_tool_client.py #   测试脚本
├── report.md               # 课程报告
└── env.example             # 配置模板
```

## 配置

```env
BASE_URL=http://127.0.0.1:8080/v1
MODEL=                       # 留空使用默认
API_KEY=                     # 本地可留空
DEBUG=1                      # 调试模式 (stderr 输出)
```

## License

MIT
