# Practice 03 - 聊天记录自动摘要

## 功能说明

带聊天记录自动摘要功能的终端聊天客户端。

**核心功能：**
- 支持流式输出和历史上下文自动续接
- 对话超过5轮时自动触发摘要压缩
- 上下文超过3k tokens时自动触发摘要压缩
- 压缩策略：前75%内容进行摘要压缩，后30%内容保留原文

## 文件结构

```
practice_03/
├── .env              # 配置文件
├── chat_summary.py    # 主程序
└── README.md        # 本文件
```

## 配置项 (.env)

```env
BASE_URL=http://127.0.0.1:8080/v1
API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MODEL=qwen2.5-7b-instruct
MAX_TOKENS=2000
CONTEXT_LENGTH=3000
```

## 运行方式

```bash
cd practice_03
python chat_summary.py
```

## 使用说明

1. 配置 `.env` 文件中的 `BASE_URL`、`API_KEY`、`MODEL`
2. 启动本地LLM服务（如llama.cpp）
3. 运行 `python chat_summary.py`
4. 输入消息开始聊天

## 命令

- `/exit` - 退出聊天
- `/clear` - 清除对话历史

## 摘要策略

当满足触发条件时：
1. 取前75%的对话内容进行摘要压缩
2. 后30%的对话内容保留原文
3. 合并生成新的上下文继续对话