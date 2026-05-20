# AI智能体开发项目

这是一个基于Python的AI智能体开发学习项目。

## 环境要求

- Python 3.10
- Conda虚拟环境

## 安装依赖

```bash
conda activate ./venv
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

## LLM 练习脚本

项目提供 `practice/llm_practice.py`，用于调用本地或 OpenAI 兼容 LLM API。

### 配置

复制 `env.example` 为 `.env`，然后填写实际值：

```env
BASE_URL=http://127.0.0.1:8080/v1
MODEL=
API_KEY=
MAX_TOKENS=500
CONTEXT_LENGTH=64000
```

- `BASE_URL`: LLM API 根地址
- `MODEL`: 模型名称，可留空使用默认模型
- `API_KEY`: API 密钥（本地 llama.cpp server 通常可留空）
- `MAX_TOKENS`: 单次生成最大 token 数
- `CONTEXT_LENGTH`: 对话上下文最大长度，当前脚本默认支持 64000

### 运行脚本

```bash
python practice/llm_practice.py
```

脚本启动时会检查本地模型是否加载成功，退出时会清理对话历史并释放资源。

### 终端聊天客户端 (practice_02/chat_terminal.py)

支持流式输出和历史上下文自动续接的终端聊天客户端。

```bash
python practice_02/chat_terminal.py
```

功能特性：
- 终端界面输入聊天内容
- 流式输出 (streaming)
- 历史聊天记录自动添加到上下文
- Ctrl+C 退出终端

### 工具调用代理 (practice_02/tool_agent.py)

基于 Function Call 的文件操作工具代理，支持5个文件操作工具：
- list_files_with_info: 列出目录下文件及属性
- rename_file: 重命名文件
- delete_file: 删除文件
- create_file: 新建文件并写入内容
- read_file_content: 读取文件内容

```bash
python practice_02/tool_agent.py
```
