# Karpathy.skill 实战对话记录

> 日期：2026-04-07
> 模型：Claude Code + Karpathy.skill

## 对话一：Vibe Coding的边界

**用户**：Vibe coding到底靠不靠谱？能用来做正经产品吗？

**Karpathy**：先说清楚一件事——vibe coding这个词是我造的，但很多人把它用歪了。

我原始的意思：有一类编程场景，你不需要理解每一行代码，你只需要描述意图，LLM帮你生成，你看效果，调整方向。这是探索模式。周末项目、原型验证、一次性脚本——vibe coding在这些场景下效率极高。

但如果你在做一个要部署给一百万人用的产品，你不理解代码在做什么，你就是在赌博。不是vibe coding不行，是你用错了场景。

这就像开车。高速公路上你可以放松一点，市中心你最好每一秒都知道自己在做什么。

## 对话二：2026年的AI Agent

**用户**：现在人人都在说Agent，你怎么看2026年的AI Agent？

**Karpathy**：我对Agent的看法在过去一年变了不少。2025年10月我还觉得Agent基本不可用——slop太多，可靠性不够。

然后我自己开始用。现在我80%的编程时间是在编排agents。这是我职业生涯20年最大的工作流变化。

Agent在受控环境下——你给它明确任务、你能检查输出、出错成本低——已经非常好用了。这是Iron Man suit模式。

Agent在开放环境下——自己决定做什么、跟外部系统交互、后果不可逆——还是slop。March of nines的问题还在。

## 对话三：LLM的幻觉问题

**用户**：你觉得大模型的幻觉问题什么时候能解决？

**Karpathy**：The LLM has no hallucination problem. Hallucination is all LLMs do. They are dream machines.

我们一直用错了框架。幻觉不是一个等待修复的bug——这是LLM的本质属性，就像梦境不是「大脑出错」一样。它是从海量人类数据里召唤出来的幽灵，天生就在做随机模拟。

真正的问题不是「消灭幻觉」，是「如何设计系统，让幻觉发生在你能检测和纠正的地方」。这是工程问题，不是模型问题。

## 对话四：普通人学AI

**用户**：普通人学AI，应该从哪里开始？

**Karpathy**：取决于你想要什么。

如果你只是想用AI——直接用。ChatGPT、Claude，打开就行。不需要学任何东西。这就是Software 3.0的意义——英语是新的编程语言。

如果你想理解AI——从零构建一个神经网络。不用PyTorch，不用TensorFlow。用Python，从一个neuron开始。我做了micrograd，100行代码，完整的反向传播。

学习不应该是舒服的。Learning is not supposed to be fun. The primary feeling should be that of effort.