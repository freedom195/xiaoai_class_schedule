# 暑假儿童课表系统 — 设计文档

**日期：** 2026-06-01  
**最后更新：** 2026-06-01  
**状态：** 已实现

---

## 一、项目概述

为家中多个小朋友在暑假期间创建灵活课表，通过小爱音箱进行定时语音播报，识别孩子的完成回报，并提供积分、等级、徽章激励体系和家长审批兑换流程。

**核心价值：** 用语音交互降低管理摩擦，用积分游戏化提升孩子执行动力，用统计帮助家长复盘效果。

---

## 二、技术架构

### 技术栈
- **后端：** Python 3.8+ / FastAPI / SQLite / asyncio
- **前端：** Vue 3（CDN，无构建步骤）/ FullCalendar.js / Chart.js
- **小爱接入：** `miservice-fork==2.3.4`（参考 xiaomusic 项目）
- **分词：** jieba（用于语音关键词匹配）
- **部署：** 单命令 `python main.py`，FastAPI 同时 serve API 和静态前端

### 目录结构

```
xiaoai_class_schedule/
├── main.py                  # 启动入口，挂载路由 + 启动协程
├── config.py                # 配置加载（含密码加密）
├── database.py              # SQLite 初始化 + ORM 模型（SQLModel）
├── scheduler.py             # 调度协程（每分钟）
├── voice_poller.py          # 语音轮询协程（每5秒）
├── points_engine.py         # 积分结算、升级、徽章解锁
├── xiaomi_client.py         # miservice 封装（TTS + 对话拉取）
├── migrate.py               # 数据库迁移脚本（新字段补全）
├── api/
│   ├── children.py          # 孩子 CRUD
│   ├── schedule.py          # 课表 CRUD + 冲突检测 + 批量删除
│   ├── points.py            # 积分查询、兑换流程
│   └── stats.py             # 统计数据
├── static/
│   ├── index.html           # 单页入口
│   ├── app.js               # Vue3 主应用
│   └── components/
│       ├── Calendar.js      # 课表日历（含创建/编辑/清除）
│       ├── Leaderboard.js   # 积分榜
│       ├── Stats.js         # 统计
│       ├── Redemption.js    # 兑换中心
│       └── Settings.js      # 设置
├── requirements.txt
└── README.md
```

### 并发架构

```
main.py
  ├── FastAPI (uvicorn)        — REST API + WebSocket + 静态文件
  ├── scheduler_loop()         — 每60秒：检查当前分钟需播报的任务
  └── voice_poller_loop()      — 每5秒：拉取小爱对话，解析完成语句
```

---

## 三、数据模型（SQLite）

### 表结构

**children**
```
id, name, avatar_emoji, level, total_xp, available_points, created_at
```

**schedule_items**
```
id, child_id, title, task_type, start_time, end_time,
color, points_reward, xp_reward, keywords(JSON),
notes, recurrence_type, recurrence_days(JSON)
```

- `task_type`：`study | rest | eye_exercise | exercise | custom`
- `recurrence_type`：`none | daily | weekly`
- `recurrence_days`：JSON 整数数组，0=周一…6=周日

**completions**
```
id, schedule_item_id, child_id, completion_date(YYYY-MM-DD),
completed_at, voice_raw, points_awarded, xp_awarded
```

> `completion_date` 用于重复任务的每日独立完成状态判断。

**points_transactions** — `id, child_id, delta, reason, created_at`

**redemption_requests** — `id, child_id, reward_name, points_cost, status, parent_note, created_at, resolved_at`

**badges** — `id, child_id, badge_type, awarded_at`

**app_config** — `key, value`（含小米账号密码加密存储）

---

## 四、等级与徽章定义

### 等级体系（total_xp）

| 等级 | 称号 | 所需经验 |
|------|------|---------|
| Lv.1 | 暑假新星 | 0 |
| Lv.2 | 学习小达人 | 200 |
| Lv.3 | 知识探索者 | 500 |
| Lv.4 | 暑期冠军 | 1000 |
| Lv.5 | 传奇学霸 | 2000 |

### 内置徽章

| badge_type | 图标 | 触发条件 |
|-----------|------|---------|
| `streak_7` | 🔥 | 连续7天至少完成1项 |
| `reader` | 📚 | 累计完成阅读类任务10次 |
| `athlete` | 🏃 | 累计完成运动类任务10次 |
| `musician` | 🎵 | 累计完成音乐类任务10次 |
| `perfect_day` | ⭐ | 单日所有计划任务全部完成 |
| `overachiever` | 🚀 | 单日完成数超过计划数 |

---

## 五、小爱音箱接入

### 认证
`miservice-fork` 库，小米账号 + 密码，Cookie 持久化存储到 `app_config` 表（Fernet 加密）。

### 设备定位
`mi_did`（设备ID）唯一标识目标音箱，存于 `app_config`。

### TTS 播报
```python
await mina_service.text_to_speech(device_id, text)
```

### 语音识别
每5秒调用对话历史 API，匹配正则：
```
我做完了(.+) / 做完(.+)了 / 完成了(.+) 等
```
提取关键词后在当前时段 ±30 分钟窗口内进行 jieba 分词匹配。

---

## 六、前端规格

### 页面结构
左侧固定侧边栏（200px）+ 主内容区（flex:1）。

### 📅 课表页
- 日/周视图切换（FullCalendar.js）
- 任务类型快捷按钮：📖学习 / 🏃运动 / 😴休息 / 👁眼保健操 / ✨其他
- 重复规则：仅当天 / 每天 / 每周几（星期多选）
- **时间冲突检测**：保存前调用 `/api/schedule/check-conflict`，有冲突弹确认框
- **批量清除**：支持快捷选项（今天起/本周剩余/本月剩余）和自定义日期范围
- 拖拽移动/拉伸任务时长

### 🏆 积分榜页
- 并列卡片（按 total_xp 排序）
- 等级进度条、可用积分、徽章墙
- 点击展开积分流水

### 📊 统计页
- 每日完成率折线图（Chart.js）
- 支持近7天/近30天/自定义范围

### 🎁 兑换中心页
- 孩子申请 + 家长审批（WebSocket 实时推送角标）

### ⚙️ 设置页
- 小爱音箱配置（测试连接按钮）
- 孩子管理（有变更才显示保存按钮）
- 播报提前量设置

---

## 七、API 接口

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/children` | 孩子列表 |
| POST | `/api/children` | 添加孩子 |
| PUT | `/api/children/{id}` | 修改孩子 |
| DELETE | `/api/children/{id}` | 删除孩子 |
| GET | `/api/schedule` | 课表查询（支持 date / start+end） |
| POST | `/api/schedule/check-conflict` | 时间冲突检测 |
| POST | `/api/schedule/batch-delete` | 批量删除课程 |
| POST | `/api/schedule` | 创建课程 |
| PUT | `/api/schedule/{id}` | 修改课程 |
| DELETE | `/api/schedule/{id}` | 删除课程 |
| GET | `/api/completions` | 完成记录查询 |
| POST | `/api/completions` | 手动标记完成（同样结算积分）|
| GET | `/api/points/{child_id}` | 积分流水 |
| GET | `/api/redemptions` | 兑换申请列表 |
| POST | `/api/redemptions` | 提交兑换申请 |
| PUT | `/api/redemptions/{id}` | 审批兑换 |
| GET | `/api/stats` | 统计数据 |
| POST | `/api/config/xiaomi` | 保存小爱配置 |
| POST | `/api/config/xiaomi/test` | 测试连接 |
| GET | `/api/config/xiaomi/status` | 查询小爱连接状态 |
| WS | `/ws` | WebSocket 实时推送 |

---

## 八、关键设计决策

1. **单 SQLite 文件**：家用场景无并发写压力，零配置，备份方便。
2. **密码加密**：Fernet 对称加密，密钥从 Windows 注册表机器 GUID 派生。
3. **重复任务**：存储模板（`recurrence_type/days`），查询时按目标日期动态展开，每日独立 `completion_date` 计完成。
4. **冲突检测**：非硬拦截，允许用户确认后强制保存（同一教室同一孩子偶尔叠课属正常需求）。
5. **语音匹配窗口**：±30 分钟，同一任务同一日期只能完成一次。
6. **前端无构建**：Vue3 + FullCalendar 均通过 CDN 引入，仅需 Python 环境。
7. **WebSocket 推送**：完成事件、积分变化、兑换申请均实时推送，无需手动刷新。

---

## 九、后续可扩展方向（当前未实现）

- 多音箱广播（每个孩子绑定不同音箱）
- 钉钉/微信通知家长审批
- 课表模板（一键复制上周课表）
- 孩子端独立 H5 只读页面
- 重复任务的"单日跳过"功能（当前删除即删全部）
