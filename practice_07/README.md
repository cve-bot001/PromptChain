# Chained Tool Client — 链式工具调用代理

基于 `practice_06/tool_client.py` 扩展，实现链式工具调用：前一个工具的输出可作为后一个工具的输入参数，LLM 根据中间结果自主决定下一步工具调用。

## 核心组件

### ChainedCallContext (tool_client.py:199)
链式调用上下文管理器，记录调用历史和存储中间变量。

### build_analysis_prompt (tool_client.py:350)
构建分析提示词，含用户原始请求、已执行步骤历史、决策规则。

### execute_chained_tool_call (tool_client.py:470)
链式调用主循环：构建提示词→LLM决策→解析响应→执行工具→记录上下文，循环最多 10 次。

### parse_chained_response (tool_client.py:263)
解析 LLM 文本响应中的 JSON 决策，支持 markdown 代码块和裸 JSON。

## 可用工具 (6个)

| 工具 | 描述 |
|------|------|
| `list_files` | 列出目录下的文件 |
| `search_files` | 搜索包含关键词的文件 |
| `read_file` | 读取文件内容 |
| `write_file` | 写入文件内容 |
| `web_fetch` | 访问URL获取网页文本 |
| `run_command` | 执行系统命令（需用户确认） |

## 新增：系统命令执行

`run_command` 工具 (`tool_client.py:128`) 特性：

- **自动平台检测**：Windows → PowerShell，Linux → bash
- **每次确认**：执行前打印命令和用途，等待用户输入 `y` 确认
- **安全黑名单**：16 条危险模式（格式化磁盘、删除根目录、系统关机、管道下载执行等）
- **超时保护**：30 秒超时
- **输出截断**：stdout 上限 3000 字符，stderr 上限 1000 字符

用户确认流程：
```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
 工具: run_command (PowerShell)
 用途: 列出所有 .py 文件
 目录: .
 命令: Get-ChildItem -Filter *.py -Name
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
 确认执行? (y/n):
```

## 运行方式

```bash
cd practice_07
python tool_client.py
```

## 测试

```bash
cd practice_07
python test_tool_client.py
```

测试覆盖：6 个工具注册验证、16 条安全规则检测、3 个链式调用场景，全部通过。
