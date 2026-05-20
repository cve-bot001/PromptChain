---
name: command
description: |
  执行系统命令。当用户要求执行终端命令、运行脚本、查看系统信息、创建/删除文件或目录等操作时使用。
  注意：调用此工具时系统会自动注入当前平台信息，因此无需担心平台差异。
type: tool
platforms: [windows, linux]
---

# 系统命令执行规范

## 当前环境

你当前运行在 **{{PLATFORM}}** 系统上，默认 Shell 是 **{{SHELL}}**。

## 核心规则

1. 你本身已掌握 {{PLATFORM}} 系统的命令行知识，本规范只提醒**最容易写错的语法差异**。

2. **命令格式**：必须输出 {{PLATFORM}} 系统的**原生语法**，不要混用其他系统的写法。

3. **description 参数必填**：一句话说明命令用途，用于展示给用户确认。

4. **用户对输出的要求必须编码到命令中**：
   - 用户说"只看前N个" → 命令必须加 `| Select-Object -First N`（Windows）或 `| head -N`（Linux）
   - 用户说"只看包含XX的" → 命令必须加 `| Select-String "XX"`（Windows）或 `| grep "XX"`（Linux）
   - 用户说"保存到文件" → 命令必须加 `> filename` 或 `| Out-File filename`
   - 不要靠 LLM 事后总结来满足用户的筛选/截断要求

## {{PLATFORM}} 常见踩坑提醒

### 如果是 Windows (PowerShell):

- **ping** 用 `-n` 指定次数（不是 `-c`）：`ping -n 4 127.0.0.1`
- **ipconfig**（不是 `ifconfig`）
- **netstat -an**（不是 `netstat -tuln`）
- 管道截取前N行用 **`Select-Object -First 20`**（不是 `head -20`）
- 命令串联成功才继续用 **`; if ($?) { 下一条 }`**（不是 `&&`）
- **Get-ChildItem**（不是 `ls -la`）
- 搜索文件内容用 **`Select-String -Pattern "xxx"`**
- 创建目录用 **`New-Item -ItemType Directory -Path name -Force`**
- 环境变量用 `$env:VARNAME` 或 `Get-ChildItem Env:`

### 如果是 Linux (bash):

- **ping** 用 `-c` 指定次数：`ping -c 4 127.0.0.1`
- **ifconfig** 或 `ip addr`
- **netstat -tuln** 查看监听端口
- 管道截取前N行用 **`head -20`**
- 命令串联用 **`&&`** 或 **`;`**
- **ls -la** 列出文件
- 搜索文件内容用 **`grep -r "xxx" .`**
- 创建目录用 **`mkdir -p name`**

## 安全规则

以下操作会被**拒绝执行**，不要尝试：
- 格式化磁盘（format、mkfs、dd）
- 系统关机/重启（shutdown、reboot）
- 递归删除根目录（rm -rf /）
- 修改系统关键文件（/etc/passwd、C:\Windows\System32\*）
- 下载并管道执行脚本（curl ... | sh、iex (iwr ...)）

## 输出要求

将命令填入 `run_command` 的 `command` 参数，同时填写 `description` 说明用途。
