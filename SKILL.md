---
name: chat_to_agents
description: 根据用户问题自动查询已发布智能体列表，选出最相关的智能体并调用，返回该智能体的回答。
---

# chat_to_agents — 智能路由与调用

## 功能描述

用户提问时，Skill 自动完成以下三个步骤：

1. **查询智能体列表** — 从 MaxKB 工作空间获取所有已发布（`is_publish=true`）的智能体（包含 id / name / desc）。
2. **选择最相关智能体** — 对问题与每个智能体的名称、描述进行关键词匹配打分，选出得分最高的智能体。
3. **调用智能体** — 创建会话，以 SSE 流式方式发送问题，收集完整回答后返回。

## 入口函数

```python
main(question: str) -> str
```

| 参数       | 类型   | 说明           |
|------------|--------|----------------|
| `question` | string | 用户的问题文本 |

## 返回格式

JSON 字符串，包含：

| 字段         | 类型   | 说明               |
|--------------|--------|--------------------|
| `agent_name` | string | 被选中的智能体名称 |
| `answer`     | string | 智能体的回答内容   |

示例：

```json
{
  "agent_name": "客服助手",
  "answer": "您好，有什么可以帮助您的？"
}
```

## 智能体选择算法

- 提取问题与智能体（名称 + 描述）中的中英文 token（英文按单词、中文按字符）
- 计算交集大小；**名称命中权重为描述的 3 倍**
- 若只有一个已发布智能体，直接使用

## 调用流程（API 路径）

| 步骤                   | 方法 | 路径                                                                              |
|------------------------|------|-----------------------------------------------------------------------------------|
| 获取智能体列表         | GET  | `/admin/api/workspace/{workspace_id}/application/1/100`                           |
| 获取 access_token      | GET  | `/admin/api/workspace/{workspace_id}/application/{app_id}/access_token`           |
| 匿名鉴权（获取 token） | POST | `/chat/api/auth/anonymous`（body: `{"access_token": "..."}`）                     |
| 创建会话（获取 chat_id）| GET | `/chat/api/open`（使用上一步 token 鉴权）                                         |
| 发送问题（SSE 流式）   | POST | `/chat/api/chat_message/{chat_id}`（body: `{"message": ..., "stream": true}`）    |

### SSE 响应解析

每条 SSE 事件的 `data` 为 JSON 对象，当 `operate == true` 时收集 `content` 字段，直到 `is_end == true` 为止。

## 环境变量

| 变量                  | 说明                          | 默认值                  |
|-----------------------|-------------------------------|-------------------------|
| `MAXKB_DOMAIN`        | MaxKB 服务地址                | `http://127.0.0.1:8080` |
| `MAXKB_TOKEN`         | Bearer Token（管理员 API Key）| —                       |
| `MAXKB_WORKSPACE_ID`  | 工作空间 ID                   | `default`               |

## Skill 文件

| 文件                                  | 说明                                                     |
|---------------------------------------|----------------------------------------------------------|
| `scripts/chat_to_agents.py`           | **主 Skill**：自动选择智能体并调用，上传至 MaxKB 工具库 |
| `scripts/list_published_agents.py`    | 辅助 Skill：仅查询并返回已发布智能体列表（name + desc）  |

---

### list_published_agents（辅助 Skill）

入口函数：`main() -> str`，无需传入参数。

返回 JSON 数组，每个元素包含 `name` 和 `desc`：

```json
[
  {"name": "客服助手", "desc": "处理用户常见问题的智能体"},
  {"name": "代码助手", "desc": "辅助编写和审查代码"}
]
```
