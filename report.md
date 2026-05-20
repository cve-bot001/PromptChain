# 基于 Prompt 驱动的本地模型链式工具调用 Agent 设计与实现

## 摘要

大型语言模型在云端 API 场景下通过 Function Calling 机制实现工具调用已较为成熟，但本地部署模型（如通过 llama.cpp 运行的 GGUF 量化模型）普遍不支持 OpenAI 标准 Function Calling 协议，且受限于上下文窗口小、推理能力弱等约束。本文设计并实现了一个基于纯文本 Prompt 工程驱动的链式工具调用 Agent，通过对 Qwen3.5-9B 本地模型的测试验证，证明该方案无需依赖云端 API 即可实现多轮工具链式调用、Skill 动态加载、对话式教练模式等能力。项目采用 Agent Skills 开放标准，以 SKILL.md 文件定义可复用的能力模块，通过运行时平台检测与模板变量替换实现跨平台兼容。

**关键词**：LLM Agent；提示工程；工具调用；Skill 系统；本地模型部署

---

## 一、引言

### 1.1 背景

当前主流的 LLM Agent 框架（如 LangChain[1]、AutoGPT[2]、OpenAI Agents SDK）在工具调用方面主要依赖两种机制：一是 OpenAI 标准 Function Calling API，通过 `tools` 字段发送 JSON Schema 定义，模型返回 `tool_calls` 结构化响应；二是基于代码层面的 Tool 抽象类，由框架层完成函数调度。然而，这两类方案对本地部署的开源模型存在显著局限：

1. **协议不兼容**：llama.cpp 等本地推理引擎对 Function Calling 的支持不稳定，许多 GGUF 格式模型在接收到 `tool_choice` 参数时产生格式混乱或空响应[3]；
2. **上下文成本高**：OpenAI 格式的 JSON Schema 定义平均每条工具消耗 150-300 tokens，当工具数量增多时迅速挤占本地模型有限的上下文窗口（本项目使用的 Qwen3.5-9B 模型上下文长度为 32768 tokens）；
3. **缺乏跨平台适配**：现有框架未对 Windows/Linux 系统命令差异做自动处理，导致 Agent 在跨平台部署时常产生语法错误的系统命令。

此外，当前市场上的 Agent Skills 生态尚处于早期阶段——agentskills.my 官方目录仅收录 20 个 Skill，且均为编程/DevOps 类别[4]。非编程领域的可复用 Skill（如沟通教练、学术写作）几乎为空白。

### 1.2 项目优势

本项目针对上述问题，提出了一种基于纯文本 Prompt 驱动的链式工具调用方案，具有以下优势：

1. **不依赖 Function Calling API**：通过精心设计的 System Prompt 和 build_analysis_prompt 函数，将工具描述、参数格式、输出规范以 Markdown 文本形式注入 Prompt，LLM 仅需返回 JSON 格式的决策文本，由 Python 代码解析后执行。这使得任何支持普通文本对话的本地模型均可使用；
2. **动态 Skill 注入**：采用 `_get_skill_body()` 函数按需读取 SKILL.md 正文，运行时替换 `{{PLATFORM}}`/`{{SHELL}}` 模板变量，避免了将大量命令对照表硬编码在 System Prompt 中，节省本地模型宝贵的上下文空间；
3. **链式工具调用**：通过 `ChainedCallContext` 类记录中间结果，`execute_chained_tool_call` 函数实现最多 10 轮的链式循环，支持前一步输出作为后一步输入的多步依赖场景；
4. **对话式教练模式**：针对软实力教练、学术论文写作、文章写作、读书心得等场景，实现了独立于工具链循环的 `execute_coaching_session` 函数，以完整 SKILL.md 正文替换 System Prompt，支持多轮教练对话。

### 1.3 实现思路

项目采用渐进式演进路径：从基础 LLM API 调用（practice/）到流式聊天（practice_02/），再到工具函数调用与自动摘要（practice_03/）、外部知识库集成（practice_04/）、Skill 发现与执行（practice_05/）、Prompt JSON 注入（practice_06/），最终在 practice_07/ 中整合为链式调用与教练模式双引擎架构。核心设计理念是"LLM 只负责输出 JSON 决策，所有实际执行由 Python 完成"。

---

## 二、文献综述

### 2.1 工具调用机制研究

Xu 等人[5]在综述中系统梳理了 LLM Agent 工具调用从单工具调用到多工具编排的演进历程，指出当前主要挑战在于工具检索与发现、Prompt 工程以及多步链式调用的鲁棒性。该文提出的"工具检索"概念与本项目的 `list_available_skills()` 函数设计思路一致，但本项目进一步通过 `_get_skill_body()` 实现了按需加载正文内容，而非一次性注入所有工具描述。

Cheng 等人[6]提出的 Prompt Sapper 系统采用 AI-chain 方法论实现了 Prompt 工程的系统化，通过 LLM 协同构建可组合的 AI 链。该研究验证了"用 Prompt 而非代码定义工具调用流程"的可行性，本项目的 `build_analysis_prompt` 函数在理念上与此一致，但实现更为轻量——不需要额外的图数据库或工程平台。

### 2.2 本地模型适配研究

在本地模型的工具调用方面，TSCG 工具模式编译器[7]的研究表明，对于 4B-14B 规模的小模型，JSON Schema 格式与模型理解能力之间存在协议不匹配，文本格式的工具描述比 JSON Schema 使 Phi-4 14B 的准确率从 0% 提升至 84.4%。这一发现直接支持了本项目选择纯文本 Prompt 注入而非 Function Calling API 的决策。

Lumer 等人[8]的生产环境 Agent 调研指出，工具的显式描述和可预测性是 Agent 可靠性的关键，Function Calling 的隐式语义可能导致选择偏差。本项目通过 `build_analysis_prompt` 在各轮循环中显式列出所有可用工具及其参数格式，确保 LLM 有充分的上下文做出决策。

### 2.3 Agent Skills 标准

Agent Skills 开放规范[4]定义了以 SKILL.md 为核心的渐进式三层加载模型：启动时扫描 YAML frontmatter（发现层）、按需加载正文（激活层）、惰性加载资源文件（资源层）。本项目完全遵循该规范：`COACH_SKILLS` 集合管理可用的教练型 Skill，`_get_skill_body()` 实现正文的按需加载与模板变量动态替换，`execute_coaching_session` 自动加载 Skill 目录下的已有 `.md` 状态文件。

---

## 三、项目实施过程

### 3.1 开发环境

| 项目 | 配置 |
|------|------|
| 推理引擎 | llama.cpp server (llama-server) |
| 模型 | Qwen3.5-9B Q4_K_M GGUF 量化 |
| 上下文长度 | 32768 tokens |
| 服务端口 | http://127.0.0.1:8080 |
| Python 环境 | Conda 虚拟环境 Python 3.10 |
| 核心依赖 | urllib（stdlib）、pyyaml、python-dotenv |
| 调试模式 | `DEBUG=1` 环境变量控制，stderr 输出 |

### 3.2 架构设计

项目由 8 个核心模块组成：

#### 3.2.1 工具注册表（TOOL_REGISTRY）

注册 7 个工具函数，每个工具包含 Python 实现函数、人类可读描述、JSON Schema 参数定义。其中 `run_command` 为唯一的系统命令执行入口（依赖 `subprocess`），`activate_coach` 为教练模式入口（无 Python 实现，由主循环特殊处理）。

#### 3.2.2 链式调用上下文（ChainedCallContext）

管理多轮工具调用间的状态传递，包含：
- `steps` 列表：记录每一步的工具名、参数和结果
- `variables` 字典：存储中间变量供后续步骤引用
- `max_iterations`：最大迭代次数（默认 10），防止无限循环
- `get_history_summary()`：将执行历史格式化为 LLM 可读文本

#### 3.2.3 分析提示词构建（build_analysis_prompt）

每轮循环动态构建提示词，包含：
- 用户原始请求
- 已执行步骤历史
- 当前操作系统信息（`platform.system()`）
- 可用工具列表及参数格式
- JSON 输出格式规范

#### 3.2.4 LLM 响应解析（parse_chained_response）

`_extract_json()` 函数支持从三种格式中提取 JSON：
1. Markdown 代码块包裹（` ```json ... ``` `）
2. 普通代码块包裹（` ``` ... ``` `）
3. 裸 JSON（通过括号配对算法 `_find_outer_json()` 提取）

#### 3.2.5 链式调用主循环（execute_chained_tool_call）

```
初始化 messages[system prompt] → while 未超限:
  → build_analysis_prompt() 注入历史
  → call_openai() HTTP POST
  → parse_chained_response() 解析决策
  → done=true → 返回最终回答
  → done=false + tool_name="run_command" → 注入 SKILL.md → LLM 纠正命令 → execute_tool()
  → done=false + tool_name="activate_coach" → execute_coaching_session()
```

#### 3.2.6 教练对话模式（execute_coaching_session）

针对 `soft-skills-coach`、`academic-paper-writer`、`article-writer`、`book-review-writer` 四个教练型 Skill，启动独立对话循环：
1. 以完整 SKILL.md 正文替换 System Prompt
2. 自动读取 Skill 目录下已有状态文件（如 `patterns.md`、`paper-outline.md`）
3. 注入可用工具说明（`write_file`、`read_file` 的调用格式）
4. 支持 `/done`（触发复盘）和 `/exit`（退出）命令

#### 3.2.7 调试系统（debug_print）

通过 `.env` 文件中的 `DEBUG=1` 控制开关，所有调试信息输出到 stderr，与正常 stdout 输出完全分离。每条调试信息包含轮次编号、响应时间、内容长度、决策结果等关键数据。

#### 3.2.8 安全机制

`DANGER_PATTERNS` 包含 16 条正则规则，覆盖格式化磁盘、系统关机、删除根目录、管道执行远程脚本等危险操作。`tool_run_command` 在每次执行前先逐条匹配检查。

### 3.3 项目目录结构

```
AI_Program/
├── report.md                     # 本报告
├── AGENTS.md                     # 代理说明
├── .agent/skill/                 # Skill 定义目录
│   ├── notice/                   # 通知撰写 Skill
│   ├── karpathy/                 # Karpathy 思维框架 Skill
│   ├── run_command/              # 系统命令执行 Skill
│   ├── soft-skills-coach/        # 软实力教练 Skill
│   ├── academic-paper-writer/    # 学术论文写作 Skill
│   ├── article-writer/           # 文章写作 Skill
│   └── book-review-writer/       # 读书心得写作 Skill
├── practice/                     # 基础 LLM API 调用
├── practice_02/                  # 流式聊天 + 工具代理
├── practice_03/                  # 自动摘要 + 上下文压缩
├── practice_04/                  # AnythingLLM 集成
├── practice_05/                  # Skill 发现与执行
├── practice_06/                  # Skill 列表 JSON 注入
└── practice_07/                  # 链式工具调用 (最终版本)
    ├── tool_client.py            # 主程序 (1000+ 行)
    ├── test_tool_client.py       # 测试脚本
    ├── .env                      # 环境配置
    └── README.md
```

---

## 四、测试与项目效果验证

### 4.1 测试方案设计

本项目采用"逻辑单元测试 + 集成场景测试"双层验证方案：

- **逻辑单元测试**：覆盖 `ChainedCallContext` 状态管理、`build_analysis_prompt` 提示词构建、`parse_chained_response` JSON 解析、`execute_tool` 工具执行、`DANGER_PATTERNS` 安全检测、`_get_skill_body` 动态加载等核心组件；
- **集成场景测试**：模拟真实用户请求，验证文件搜索链式调用、多文件操作、网页获取与保存等端到端场景。

### 4.2 测试数据收集

运行 `test_tool_client.py` 获得以下结果：

| 测试项目 | 测试内容 | 结果 |
|----------|----------|------|
| ChainedCallContext | 初始化、记录步骤、变量存取、历史摘要 | 通过 |
| build_analysis_prompt | 提示词结构完整性 | 通过 |
| execute_tool(list_files) | 列出 practice06 目录（5 个条目） | 通过 |
| execute_tool(unknown) | 未知工具错误处理 | 通过 |
| SYSTEM_PROMPT | 链式调用规则完整性 | 通过 |
| TOOL_REGISTRY | 7 个工具全部注册 | 通过 |
| DANGER_PATTERNS | 8 种危险命令检测 | 通过 |
| _get_skill_body(run_command) | 加载成功（1477 字符，平台注入正确） | 通过 |
| 测试1：文件搜索链 | search_files → read_file ×2 → 总结（3 步） | 通过 |
| 测试2：多文件操作 | read_file ×2 → 计算 → write_file（4 步，42+58=100） | 通过 |
| 测试3：网页获取 | web_fetch → 分析 → write_file（2 步，1637 字符） | 通过 |

### 4.3 交互实测数据

在 Qwen3.5-9B 本地模型上进行了多轮交互测试，记录关键指标：

| 场景 | 链式步骤 | LLM 调用次数 | 总耗时 | 工具执行耗时 |
|------|----------|-------------|--------|------------|
| 查看系统 IP 地址 | 1 步（skill 纠正为 `ipconfig`） | 2 次（含 refine） | ~6s | <1s |
| 列举前 10 个进程 | 1 步 | 2 次 | ~7s | <1s |
| 创建文件并写入 | 1 步（skill 纠正命令参数） | 2 次 | ~5s | <1s |
| 删除文件 | 1 步 | 2 次 | ~5s | <1s |
| 当前系统时间 | 1 步 | 2 次 | ~5s | <1s |
| 搜索文件含关键词 | 3 步（搜索 → 读取 ×2 → 总结） | 4 次 | ~15s | <2s |

**关键发现**：
1. Skill 纠正机制有效——LLM 最初输出的命令在 Windows 平台上语法错误（如 `hostname -I`、`ip addr show`），经 `tool_client.py:735` 注入 SKILL.md 正文后，第二轮均能纠正为正确的 PowerShell 命令（`ipconfig`、`Get-Date`）；
2. `build_analysis_prompt` 中注入 `platform.system()` 信息（第 505 行）后，LLM 在第一轮就能生成正确命令的概率显著提升；
3. JSON 解析的 `_extract_json()` 函数对三种格式（裸 JSON、markdown 代码块包裹、普通代码块包裹）均能正确提取，未出现解析失败。

---

## 五、结论

### 5.1 主要结论

1. **纯 Prompt 驱动的工具调用方案在本地 9B 级模型上可行**：通过精心设计的 System Prompt + 动态分析提示词 + JSON 输出格式约束，Qwen3.5-9B 能稳定生成符合规范的链式工具调用决策，无需依赖 OpenAI Function Calling API。

2. **按需加载的 Skill 机制有效节省上下文**：将命令对照表等平台特定知识从 System Prompt 中移除，改为 `_get_skill_body()` 运行时加载 + 模板变量替换，使 System Prompt 从含 300+ 字符速查表精简为仅含通用规则，为本地模型的有限上下文窗口留出更多空间。

3. **链式调用上下文管理器实现了可靠的多步依赖**：`ChainedCallContext` 的步骤记录与历史摘要机制，使 LLM 能够在每一步调用时完整了解前序执行结果，自主决定下一步操作。最多 10 次迭代的限制有效防止了无限循环。

4. **教练模式扩展了 Agent 的应用场景**：通过 `execute_coaching_session` 函数实现的对话式 Skill 执行模式，使 Agent 能够充当软实力教练、学术写作顾问、文章写作助手、读书心得教练等多种角色，超越了传统工具调用的范畴。

### 5.2 不足之处

1. **JSON 解析依赖非贪婪正则**：`_extract_json()` 中的正则表达式在嵌套极深或字符串内容包含大括号的极端情况下可能匹配失败，导致 LLM 响应被误判为 `done:true`；
2. **教练模式工具调用依赖文本解析**：教练对话循环中检测嵌入 JSON 工具调用的方式对 LLM 输出格式要求较高，部分本地模型可能无法在自然语言回复中正确嵌入 `write_file` 的 JSON 调用；
3. **缺乏向量化的 Skill 检索**：当前 Skill 触发仅依赖 `description` 字段的关键词匹配，未实现基于语义相似度的智能检索；
4. **单模型限制**：测试仅在 Qwen3.5-9B 单一模型上进行，未对比其他规模/系列的本地模型表现。

### 5.3 未来研究方向

1. **向量化 Skill 检索**：基于 Skill 的 `description` 字段生成 embedding，实现语义级触发匹配，提高非精确关键词场景下的召回率；
2. **工具调用可靠性量化**：设计标准化的工具调用基准测试，统计链式调用的成功率、平均步数、命令正确率等指标；
3. **多模型对比实验**：在 Qwen2.5、DeepSeek、Phi-4 等不同系列的本地模型上进行相同的工具调用测试，分析各模型在 Prompt 驱动工具调用场景下的差异；
4. **上下文窗口自适应压缩**：当消息历史超过一定阈值时，自动触发摘要压缩（参考 practice_03 的实现），使 Agent 能处理更长链的任务。

---

## 参考文献

[1] Chase H. LangChain: Building applications with LLMs through composability[EB/OL]. (2022-10-17)[2026-05-14]. https://github.com/langchain-ai/langchain.

[2] Significant Gravitas. AutoGPT: Build & use AI agents[EB/OL]. (2023-03-30)[2026-05-14]. https://github.com/Significant-Gravitas/AutoGPT.

[3] Sakizli F. TSCG: Deterministic Tool-Schema Compilation for Agentic LLM Deployments[J]. arXiv preprint arXiv:2605.04107, 2026.

[4] Agent Skills Community. Agent Skills Specification: Open standard for SKILL.md files[EB/OL]. (2026-04-01)[2026-05-14]. https://agentskills.my/specification.

[5] Xu H, Li C, Ma X, et al. The evolution of tool use in LLM agents: From single-tool call to multi-tool orchestration[J]. arXiv preprint arXiv:2603.22862, 2026.

[6] Cheng Y, Chen J, Huang Q, et al. Prompt sapper: A LLM-empowered production tool for building AI chains[C]//Proceedings of the 46th International Conference on Software Engineering. Lisbon: ACM, 2024: 1-5.

[7] Sakizli F. TSCG: Deterministic Tool-Schema Compilation for Agentic LLM Deployments[J]. arXiv preprint arXiv:2605.04107, 2026.

[8] Lumer E, Gulati A, Nizar F, et al. Tool and Agent Selection for Large Language Model Agents in Production: A Survey[EB/OL]. Preprints, 2025.

[9] Liang Y, Chen X, Ge Y, et al. UniToolCall: Unifying Tool-Use Representation, Data, and Evaluation for LLM Agents[J]. arXiv preprint arXiv:2604.11557, 2026.

[10] Törni M. Large Language Model Prompt Engineering for Software Development[D]. Turku: Turku University of Applied Sciences, 2025.
