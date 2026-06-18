# 多平台小说榜单爬取与可视化系统

面向**番茄小说**、**飞卢小说**、**七猫小说**、**起点中文网**四大网文平台，实现新书榜全分类数据爬取、书籍基础信息入库、前十章深度爬取、本地文件存储、全流程任务调度、Web 可视化看板，并支持**每周自动定时刷新**。

---

## 快速开始

### 环境要求

- Python 3.12+
- MySQL 8.0+
- Chrome / Chromedriver（用于 Selenium 回退方案）

### 安装

```bash
# 进入项目目录
cd /Users/qianxuyang/PycharmProjects/pythonProject1

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt 2>/dev/null || pip install \
  mysql-connector-python \
  requests beautifulsoup4 lxml \
  flask \
  apscheduler
```

### 数据库初始化

```bash
# 确保 MySQL 运行中，导入表结构
mysql -u root -p12345678 book_analyzer < sql/schema.sql
mysql -u root -p12345678 book_analyzer < sql/data.sql
```

### 基础爬取

```bash
# 番茄全流程（榜单+书籍+章节+封面）
python main.py -s fanqie

# 所有平台全流程
python main.py -s all

# 仅爬取榜单（不爬章节）
python main.py -s fanqie --rank-only

# 每周刷新（增量更新旧书信息 + 自动爬新书章节）
python main.py -s all --weekly-refresh
```

### 启动数据看板

```bash
python webapp.py --port 5001
# 访问 http://127.0.0.1:5001
# 定时任务配置页: http://127.0.0.1:5001/scheduler
```

---

## 功能特性

### 核心爬取

| 平台 | 类目数 | 每类本数 | 总榜单数 | 技术方案 |
|------|--------|---------|---------|---------|
| **番茄** fanqie | 37 个子类目 | 20 本/类（2页×10） | **~740** | requests + SSR `__INITIAL_STATE__` + API 混合 |
| **飞卢** feilu | 8 个分类 | 10 本/类 | **~80** | requests + BeautifulSoup HTML 解析 |
| **起点** qidian | 10 个榜单类型 | 10 本/类 | **~100** | requests + 移动站 m.qidian.com SSR |
| **七猫** qimao | 10 个组合 | 10 本/类 | **~100** | requests + Nuxt.js SSR `__NUXT__` |
| **合计** | | | **~1020** | |

### 章节爬取

- 每本书固定爬取 **第 1–10 章**
- 正文存为本地 `txt` 文件，路径记录在 `chapters` 表
- 已爬取的书籍（`crawl_status=2`）**不重复爬取**
- 付费/加密章节自动跳过，不阻塞整体任务

### 每周定时刷新

- **APScheduler 进程内调度**，随 Flask 启动自动注册
- 默认每周日 02:00 自动执行全平台刷新
- 支持后台页面自定义：**开关 / 星期 / 时分**
- 支持**手动一键刷新**

**数据更新策略：**

| 表 | 策略 | 说明 |
|----|------|------|
| `rank_books` | 增量留存 | 每周保留独立快照，不覆盖历史 |
| `books` | 动态更新 | 旧书更新信息，不重置 `crawl_status` |
| `chapters` | 只增不改 | 仅新书爬取章节 |
| `crawl_tasks` | 全量记录 | `task_type=rank_weekly_refresh` 区分任务类型 |

**容错策略：**
- 单平台失败**不影响其他平台**
- 失败自动重试 3 次
- 错误信息精准记录于 `error_msg`

---

## 命令行参考

```bash
python main.py [OPTIONS]

# 平台选择
-s, --source    # 目标平台: fanqie/feilu/qimao/qidian/all（支持多选，默认 all）

# 执行模式（互斥）
--rank-only     # 仅爬取榜单数据
--init-only     # 仅榜单→书籍初始化
--book-only     # 仅爬取书籍详情
--chapter-only  # 仅爬取章节
--cover-only    # 仅下载封面
--clean-garbled # 清理字体加密乱码记录
--weekly-refresh # 每周刷新（增量更新+新书自动爬章节）
                 # 不传任何模式则执行全流程（6步）
```

---

## 项目文件

```
.
├── main.py                   # 主入口，CLI 解析，6步流程编排 + 每周刷新
├── config.py                 # 全局配置（路径/爬取行为/优先级）
├── database.py               # MySQL 连接管理
├── db_ops.py                 # 6张表的 CRUD 操作（含 scheduler_config）
├── webapp.py                 # Flask 看板后端（12个API + APScheduler 集成）
│
├── crawlers/
│   ├── base.py               # 爬虫基类（Selenium管理 + 4个接口定义）
│   ├── fanqie.py             # 番茄爬虫（SSR+API，37子类目×2页）
│   ├── feilu.py              # 飞卢爬虫（HTML/BS4，8分类）
│   ├── qidian.py             # 起点爬虫（移动站SSR，10榜单）
│   └── qimao.py              # 七猫爬虫（Nuxt SSR，10组合）
│
├── services/
│   ├── task_manager.py       # 任务生命周期管理（含每周刷新）
│   └── file_manager.py       # 章节文件读写 + 封面下载
│
├── templates/
│   ├── dashboard.html        # 数据看板主页
│   └── scheduler.html        # 定时任务配置页
│
├── sql/
│   ├── schema.sql            # 6张表 DDL（含 scheduler_config）
│   ├── data.sql              # 初始数据
│   └── book_analyzer_full.sql # 完整建库脚本
│
└── data/
    ├── books/{id[:2]}/{book_id}/{idx:03d}.txt  # 章节正文
    ├── covers/{source}/{source}_{book_id}.jpg   # 封面图片
    └── logs/                                     # 运行日志
```

---

## API 接口

### 数据看板（webapp.py — Flask）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 数据看板主页 |
| `/scheduler` | GET | 定时任务配置页 |
| `/api/stats` | GET | 核心统计（含本周新增、成功率、调度器状态） |
| `/api/rank-books` | GET | 榜单分页列表 |
| `/api/books` | GET | 书籍分页列表 |
| `/api/books/<book_id>` | GET | 书籍详情 |
| `/api/chapters` | GET | 章节分页列表 |
| `/api/chapters/<id>/content` | GET | 读取章节正文文件 |
| `/api/tasks` | GET | 任务分页列表 |
| `/api/tasks/<id>/retry` | POST | 重置任务为待执行 |
| `/api/scheduler/config` | GET/POST | 定时任务配置读写 |
| `/api/scheduler/trigger` | POST | 手动触发每周刷新 |
| `/api/scheduler/history` | GET | 最近 10 次刷新记录 |

---

## 数据库

### 数据库连接

| 配置 | 值 |
|------|-----|
| 数据库 | `book_analyzer` |
| 地址 | `localhost:3306` |
| 用户 | `root` |
| 密码 | `12345678` |
| 驱动 | `mysql-connector-python` |

### 表结构（6张）

| 表 | 用途 | 关键约束 |
|----|------|---------|
| `rank_books` | 榜单数据快照 | UNIQUE(source, book_id) |
| `books` | 书籍信息 | book_id 主键，crawl_status 状态机 |
| `chapters` | 章节数据 | UNIQUE(book_id, chapter_index) |
| `crawl_tasks` | 爬取任务 | task_type + status + retry_count |
| `chat_history` | 辅助日志 | 扩展能力 |
| `scheduler_config` | 定时任务配置 | 单行配置（id=1） |

---

## 各平台爬虫技术对比

| 维度 | 番茄 | 飞卢 | 起点 | 七猫 |
|------|------|------|------|------|
| 技术栈 | SSR+API | HTML/BS4 | 移动SSR | Nuxt SSR |
| 数据源 | `__INITIAL_STATE__` | DOM解析 | `<script type="application/json">` | `__NUXT__` |
| 榜单量 | ~740本 | ~80本 | ~100本 | ~100本 |
| 反爬 | 字体加密（私用区字符） | 无 | 无 | 无 |

---

## 技术架构

```
┌──────────────┐    ┌──────────────────────┐
│   CLI入口     │    │  Flask 可视化看板     │
│  (main.py)   │    │  (webapp.py)          │
└──────┬───────┘    └──────────┬───────────┘
       │                       │
       └───────┬───────────────┘
               │
       ┌───────┴───────┐
       │  业务编排层    │
       │ 6步 + 每周刷新 │
       └───────┬───────┘
               │
       ┌───────┴───────┐
       │  爬虫引擎层    │
       │ 4个平台实现类  │
       └───────┬───────┘
               │
       ┌───────┴───────┐
       │  数据访问层    │
       │ db_ops / MySQL │
       └───────────────┘
```

---

## 扩展方向

1. **新增平台**：继承 `BaseCrawler` 实现 4 个接口，注册 `PLATFORM_LABELS` + `CRAWLER_MAP`
2. **数据导出**：基于现有 6 张表可扩展 Excel/JSON 导出
3. **封面 OSS**：存储可扩展为阿里云 OSS / 腾讯云 COS
4. **通知告警**：刷新失败时可接入飞书/钉钉/邮件通知
