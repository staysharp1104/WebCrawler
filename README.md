# 多平台小说榜单及章节爬取系统 — 项目架构分析

> 分析日期：2026-04-15

---

## 一、项目概述

面向**番茄（fanqie）**、**飞卢（feilu）**、**七猫（qimao）**、**起点（qidian）** 四大网文平台，实现：

- 各平台全部分类榜单数据自动化爬取（每类 10~20 本）
- 书籍基础信息的结构化入库
- 每本书前 10 章正文深度爬取（本地文件存储）
- 全流程任务调度与状态监控
- Web 可视化数据看板

---

## 二、整体分层架构

```
┌─────────────────────────────────────────────────────────┐
│                    命令行入口 (main.py)                    │
│           ┌───────────────────────────────┐              │
│           │   Web 可视化看板 (webapp.py)   │              │
│           │   Flask REST API + HTML 前端   │              │
│           └────────────┬──────────────────┘              │
├────────────────────────┼──────────────────────────────────┤
│         业务编排层 (main.py)                              │
│  step_crawl_rank → step_clean_garbled →                  │
│  step_init_books → step_crawl_books →                    │
│  step_crawl_chapters → step_download_covers               │
├────────────────────────┼──────────────────────────────────┤
│      ┌─────────────────┼─────────────────────┐           │
│ 任务管理服务            │             文件管理服务          │
│ (services/             │             (services/            │
│  task_manager.py)      │              file_manager.py)     │
├────────────────────────┼──────────────────────────────────┤
│        爬虫引擎层 (crawlers/)                             │
│  ┌────────┬────────┬────────┬────────┐                    │
│  │ fanqie │  feilu │ qidian │ qimao  │                    │
│  │ SSR/API│HTML/BS4│移动SSR │Nuxt SSR│                    │
│  └────┬───┴────┬───┴───┬────┴───┬────┘                    │
│       │        │       │        │                         │
│    ┌──┴────────┴───────┴────────┴──┐                      │
│    │       基类 BaseCrawler        │                      │
│    │   (crawlers/base.py)          │                      │
│    └───────────────────────────────┘                      │
├──────────────────────────────────────────────────────────┤
│      数据访问层                                           │
│  ┌────────────────┐  ┌────────────────────────────────┐   │
│  │  database.py   │  │        db_ops.py               │   │
│  │ MySQL 连接管理  │  │ rank_books/books/chapters/     │   │
│  └───────┬────────┘  │ crawl_tasks/chat_history CRUD  │   │
│          │           └────────────┬───────────────────┘   │
├──────────┼────────────────────────┼──────────────────────┤
│          ▼                        ▼                       │
│  ┌────────────────────────────────────────────────────┐   │
│  │               MySQL (book_analyzer)                │   │
│  │  rank_books  │  books  │  chapters  │  crawl_tasks │   │
│  │  chat_history                                     │   │
│  └────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────┤
│      本地文件系统                                           │
│  data/books/{book_id[:2]}/{book_id}/{idx:03d}.txt  ← 章节 │
│  data/covers/{source}/{source}_{book_id}.jpg       ← 封面 │
└──────────────────────────────────────────────────────────┘
```

---

## 三、模块详解

### 3.1 配置模块 (config.py)

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `RANK_PAGE_SIZE` | 10 | 每个子类目每页最多爬取书本数 |
| `MAX_RANK_PAGES` | 2 | 番茄类目分页深度（每类目最多2页） |
| `CHAPTER_MAX` | 10 | 每本书爬取前 N 章 |
| `MAX_RETRIES` | 3 | 任务最大重试次数 |
| `PLATFORM_LABELS` | 字典 | 四个平台的中文名称映射 |
| `TASK_PRIORITY` | 字典 | 四类任务优先级（榜单100 > 书籍80 > 章节60 > 封面40） |
| 状态码常量 | 0~3 | crawl_status 和 task_status 通用状态机 |

### 3.2 爬虫引擎层

#### 基类 (crawlers/base.py)

**接口定义（子类必须实现）：**

| 接口方法 | 输入 | 输出 | 职责 |
|----------|------|------|------|
| `crawl_rankings()` | 无 | `list[dict]` | 爬取平台榜单数据 |
| `crawl_book_info(book_url)` | `str` | `dict` | 爬取单本书籍详情 |
| `crawl_chapter_list(book_url)` | `str` | `list[tuple]` | 获取章节列表 |
| `crawl_chapter_content(chapter_url)` | `str` | `str` | 爬取单章正文 |

**公用能力：** Selenium 无头浏览器管理（`get_driver`/`close_driver`）、`safe_get`、`wait_element`、`delay`（随机延迟防反爬）

#### 番茄爬虫 (crawlers/fanqie.py) — 493 行

| 维度 | 说明 |
|------|------|
| **技术方案** | 纯 `requests` + SSR `__INITIAL_STATE__` JSON 解析 + API 混合 |
| **榜单策略** | 从 `rankCategoryTypeList` 提取 37 个子类目（男19+女18），逐类目分2页爬取 `/rank/{tab}_{page}_{catId}`，总计约 740 本 |
| **书籍详情** | 优先调用 `/api/book/info?bookId={id}` API 获取干净文本，SSR 补充章节总数 |
| **章节正文** | `/reader/{itemId}` SSR 提取 `reader.chapterData.content` |

#### 飞卢爬虫 (crawlers/feilu.py) — 262 行

| 维度 | 说明 |
|------|------|
| **技术方案** | `requests` + BeautifulSoup HTML 解析 |
| **榜单策略** | 8 个分类（玄幻/武侠/都市/军事/网游/科幻/女生/同人），每类各取 10 本 |
| **书籍详情** | 详情页 HTML 解析：h1 标题、`.C-Two` 作者、`.T-L-Two` 简介、字数正则提取 |
| **章节正文** | `.nr_center` 区域提取 `<p>` 段落文本 |

#### 起点爬虫 (crawlers/qidian.py) — 278 行

| 维度 | 说明 |
|------|------|
| **技术方案** | `requests` + 移动站 `m.qidian.com` SSR JSON |
| **榜单策略** | 10 个榜单类型（月票/热销/阅读指数/推荐/新书/更新/收藏/新人/签约/新粉丝），各 10 本 |
| **书籍详情** | `pageData.bookInfo` 提取 50+ 字段 |
| **章节正文** | 章节页 SSR `pageData.chapterInfo.content` |

#### 七猫爬虫 (crawlers/qimao.py) — 456 行

| 维度 | 说明 |
|------|------|
| **技术方案** | `requests` + Nuxt.js SSR `__NUXT__` JSON 提取 |
| **榜单策略** | 2 频道（boy+girl）× 5 排行类型（hot/new/over/collect/update）= 10 组合，各 10 本 |
| **书籍详情** | Nuxt SSR `fetch` 中提取 `bookInfo` |
| **章节正文** | 章节页 SSR 提取正文文本 |

### 3.3 业务编排层 (main.py) — 346 行

**命令行参数：**

| 参数 | 说明 |
|------|------|
| `-s / --source` | 目标平台（支持多选 `fanqie`/`feilu`/`qimao`/`qidian`/`all`） |
| `--rank-only` | 仅榜单爬取 |
| `--init-only` | 仅榜单→书籍初始化 |
| `--book-only` | 仅书籍详情爬取 |
| `--chapter-only` | 仅章节爬取 |
| `--cover-only` | 仅封面下载 |
| `--clean-garbled` | 清理乱码记录 |

**全流程 6 步骤：**

```
Step 1: 榜单爬取 ──→ crawl_rankings() → batch_insert_rank_books()
Step 2: 清理乱码 ──→ cleanup_garbled_rank_books()
Step 3: 书籍初始化 ──→ get_distinct_books_from_rank() → init_book_from_rank()
Step 4: 书籍详情 ──→ crawl_book_info() → insert_book()
Step 5: 章节爬取 ──→ crawl_chapter_list() → crawl_chapter_content() → save_chapter_content() → insert_chapter()
Step 6: 封面下载 ──→ download_cover() → update_book_cover_path()
```

---

## 四、服务层

### 4.1 任务管理器 (services/task_manager.py) — 74 行

| 方法 | 职责 |
|------|------|
| `create_rank_tasks()` | 创建榜单爬取任务 |
| `create_book_init_tasks()` | 为榜单书籍创建详情爬取任务 |
| `create_chapter_tasks()` | 为待爬书籍创建章节爬取任务 |
| `mark_task_running/success/failed/retry()` | 任务状态机转换 |

**任务状态机：**

```
Pending (0) ──→ Running (1) ──→ Success (2)
                  │
                  ├── retry < MAX_RETRIES → Pending (0)
                  └── retry >= MAX_RETRIES → Failed (3)
```

### 4.2 文件管理器 (services/file_manager.py) — 69 行

| 方法 | 职责 |
|------|------|
| `ensure_dirs()` | 创建 data/books/、data/covers/、data/logs/ 目录 |
| `save_chapter_content()` | 按 `{book_id[:2]}/{book_id}/{idx:03d}.txt` 结构保存章节正文 |
| `read_chapter_content()` | 读取已保存的章节文件 |
| `download_cover()` | 下载封面图片到 `data/covers/{source}/` |

**文件存储规范：**

```
data/
├── books/
│   ├── 72/                         # book_id 前2位建子目录
│   │   └── 7200738711116450877/    # 以 book_id 命名书籍目录
│   │       ├── 001.txt             # 第1章
│   │       ├── 002.txt
│   │       └── ...
│   └── ...
├── covers/
│   ├── fanqie/
│   │   └── fanqie_7200738711...jpg
│   ├── feilu/
│   └── ...
└── logs/
```

---

## 五、数据访问层

### 5.1 数据库连接 (database.py) — 48 行

| 配置 | 值 |
|------|-----|
| 数据库 | `book_analyzer` |
| 地址 | `localhost:3306` |
| 用户 | `root` |
| 密码 | `12345678` |
| 驱动 | `mysql-connector-python` |

`get_connection()` 提供统一连接入口，所有操作共享此函数。

### 5.2 CRUD 操作 (db_ops.py) — 398 行

覆盖 5 张表的全部读写操作：

| 分组 | 方法 | 说明 |
|------|------|------|
| **rank_books** | `insert_rank_book` / `batch_insert_rank_books` | `INSERT IGNORE` 去重 |
| | `get_distinct_books_from_rank` | 获取某平台去重书籍列表 |
| | `cleanup_garbled_rank_books` | 删除字体加密乱码记录及关联 books |
| **books** | `insert_book` | `REPLACE INTO` 更新，数值字段钳位防溢出 |
| | `init_book_from_rank` | 从榜单初始化书籍（crawl_status=0） |
| | `get_pending_crawl_books` | 待爬章节的书籍列表 |
| | `update_book_crawl_status` | 更新爬取状态和已爬章节数 |
| **chapters** | `insert_chapter` | `INSERT IGNORE` 去重 |
| | `count_chapters_by_book` | 统计已爬章节数 |
| **crawl_tasks** | `create_task` | 创建任务 |
| | `get_pending_tasks` | 获取待执行任务 |
| | `update_task_status` | 更新任务状态 |
| **chat_history** | `add_book_log` | 添加辅助日志 |

---

## 六、可视化层 (webapp.py) — 378 行

Flask 后端 + HTML 前端看板。

### API 接口清单

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 数据看板主页（HTML） |
| `/api/stats` | GET | 核心统计：总书籍数、各平台分布、完成/失败数、章节数、存储大小 |
| `/api/rank-books` | GET | 榜单数据分页列表（左连 books 表展示爬取状态） |
| `/api/books` | GET | 书籍分页列表（支持 source/keyword/crawl_status/book_status 筛选） |
| `/api/books/<book_id>` | GET | 书籍详情 + 章节统计 |
| `/api/chapters` | GET | 章节分页列表（左连 books 表展示书名作者） |
| `/api/chapters/<id>/content` | GET | 读取本地章节正文文件内容 |
| `/api/tasks` | GET | 任务分页列表（支持 task_type/source/status/priority 筛选） |
| `/api/tasks/<id>/retry` | POST | 重置任务为待执行状态 |

---

## 七、数据库表结构

### 7.1 rank_books（榜单数据）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT PK AUTO_INCREMENT | 主键 |
| book_id | VARCHAR(64) NOT NULL | 书籍ID |
| `rank` | VARCHAR(16) | 排名 |
| title | VARCHAR(255) | 书名 |
| author | VARCHAR(128) | 作者 |
| book_url | TEXT | 书籍链接 |
| description | TEXT | 简介 |
| status | VARCHAR(16) | 连载/完结 |
| reader_count | VARCHAR(64) | 阅读量 |
| category_label | VARCHAR(255) | 分类标签（如"科幻末世/男频新书榜"） |
| source | VARCHAR(32) NOT NULL | 平台标识 |
| cover_url | TEXT | 封面链接 |
| created_at | TIMESTAMP | 创建时间 |
| **唯一约束** | UNIQUE(source, book_id) | 去重 |

### 7.2 books（书籍信息）

| 字段 | 类型 | 说明 |
|------|------|------|
| book_id | VARCHAR(64) PK | 书籍ID（主键） |
| title | VARCHAR(255) | 书名 |
| author | VARCHAR(128) | 作者 |
| book_url | TEXT | 书籍链接 |
| intro | TEXT | 简介 |
| category | VARCHAR(128) | 分类 |
| word_count | INT DEFAULT 0 | 字数 |
| status | VARCHAR(16) | 连载/完结 |
| source | VARCHAR(32) | 平台标识 |
| chapter_count | INT DEFAULT 0 | 已爬取章节数 |
| total_chapters | INT DEFAULT 0 | 网站总章节数 |
| crawl_status | INT DEFAULT 0 | 0未爬 1中 2成功 3失败 |
| cover_url | TEXT | 封面链接 |
| cover_path | VARCHAR(255) | 封面本地路径 |
| created_at | TIMESTAMP | 创建时间 |

### 7.3 chapters（章节数据）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT PK AUTO_INCREMENT | 主键 |
| book_id | VARCHAR(64) NOT NULL | 所属书籍 |
| chapter_index | INT NOT NULL | 章节序号 |
| chapter_title | VARCHAR(255) | 章节标题 |
| chapter_url | TEXT | 章节链接 |
| content_path | VARCHAR(255) | 正文文件相对路径 |
| content_size | INT DEFAULT 0 | 文件字节数 |
| source | VARCHAR(32) | 平台标识 |
| created_at | TIMESTAMP | 创建时间 |
| **唯一约束** | UNIQUE(book_id, chapter_index) | 去重 |

### 7.4 crawl_tasks（爬取任务）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT PK AUTO_INCREMENT | 主键 |
| task_type | VARCHAR(32) | 任务类型（crawl_rank/book/chapter） |
| source | VARCHAR(32) | 平台标识 |
| target_id | VARCHAR(64) | 关联 book_id |
| status | INT DEFAULT 0 | 0待执行 1中 2成功 3失败 |
| priority | INT DEFAULT 0 | 优先级 |
| retry_count | INT DEFAULT 0 | 重试次数 |
| error_msg | TEXT | 错误信息 |
| created_at | TIMESTAMP | 创建时间 |

### 7.5 chat_history（辅助日志）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT PK AUTO_INCREMENT | 主键 |
| book_id | VARCHAR(64) | 关联书籍 |
| role | VARCHAR(16) DEFAULT 'system' | 角色 |
| content | TEXT | 日志内容 |
| source | VARCHAR(32) | 平台标识 |
| created_at | TIMESTAMP | 创建时间 |

---

## 八、核心业务流程图

```
用户执行 main.py
      │
      ▼
┌─────────────────────────────────────────────┐
│             创建 crawl_rank 任务              │
│  每个平台创建 1 条 crawl_tasks 记录           │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│     Step 1: 榜单爬取 (crawl_rankings)        │
│  fanqie → 37子类目×2页 → 740条              │
│  feilu  → 8分类×10本       → 80条            │
│  qidian → 10榜单×10本      → 100条           │
│  qimao  → 10组合×10本      → 100条           │
│     ↓ batch_insert_rank_books()              │
│  入库 rank_books 表 (INSERT IGNORE 去重)     │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│     Step 2: 清理乱码 (cleanup_garbled)       │
│  检测 title 中的 Unicode 私用区字体加密字符   │
│  删除乱码 rank_books 记录 + 关联 books 记录   │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│     Step 3: 书籍初始化 (init_book_from_rank) │
│  从 rank_books 提取去重 book_id 列表         │
│  创建 crawl_book 任务                        │
│  调用 init_book_from_rank() → books 表       │
│  crawl_status=0, chapter_count=0             │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│     Step 4: 书籍详情 (crawl_book_info)       │
│  遍历 pending 的 crawl_book 任务             │
│  各平台 crawl_book_info(book_url)            │
│  → insert_book() 入库 books 表               │
│  成功后创建 crawl_chapter 任务                │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│     Step 5: 章节爬取 (crawl_chapters)        │
│  遍历 crawl_status=0 的书籍                  │
│  crawl_chapter_list() → 前10章               │
│  逐章: crawl_chapter_content()               │
│   → save_chapter_content() 写文件            │
│   → insert_chapter() 入库 chapters 表        │
│  更新 books.crawl_status=2, chapter_count    │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│     Step 6: 封面下载 (download_covers)       │
│  遍历 cover_url 不为空且 cover_path 空的记录  │
│  download_cover() → data/covers/{source}/    │
│  update_book_cover_path()                    │
└──────────────────────────────────────────────┘
```

---

## 九、各平台爬虫对比总结

| 维度 | 番茄 fanqie | 飞卢 feilu | 起点 qidian | 七猫 qimao |
|------|-------------|-----------|------------|-----------|
| **技术栈** | requests + SSR/API | requests + BS4 | requests + 移动端 SSR | requests + Nuxt SSR |
| **页面类型** | React SPA | 传统 HTML | React SSR | Nuxt.js SSR |
| **数据提取方式** | `__INITIAL_STATE__` | DOM 选择器 | `<script type="application/json">` | `__NUXT__` JSON |
| **榜单结构** | 37子类目×2页 | 8分类 | 10榜单类型 | 2频道×5排行 |
| **每类数量** | 20本（×37 = 740） | 10本（×8 = 80） | 10本（×10 = 100） | 10本（×10 = 100） |
| **榜单URL** | `/rank/{tab}_{page}_{catId}` | `/l/{catId}/1.html` | `m.qidian.com/rank` | `/paihang?channelType=&rankType=` |
| **书籍详情** | API `/api/book/info` | 详情页 HTML | `pageData.bookInfo` | 详情页 SSR |
| **章节正文** | `/reader/{itemId}` SSR | `.nr_center` | `pageData.chapterInfo.content` | SSR 提取 |
| **反爬措施** | 字体加密（私用区字符） | 无 | 无 | 无 |

---

## 十、关键技术决策

| 决策 | 方案 | 原因 |
|------|------|------|
| **爬取引擎** | 纯 requests + SSR 解析为主 | 无需 Selenium，速度快 10 倍，避免浏览器兼容性问题 |
| **数据去重** | DB 层面 `INSERT IGNORE` | 简单可靠，避免多分类间同一书籍重复入库 |
| **章节存储** | 本地文本文件 + content_path 记录 | 正文大文本不适合存数据库，文件读写更快 |
| **目录散列** | `book_id[:2]` 两级子目录 | 避免单目录超大量文件导致文件系统性能下降 |
| **任务调度** | MySQL 表 + 状态机 | 无需额外消息队列，状态持久化，支持重试 |
| **防反爬** | 随机 UA 轮换 + 请求间隔 + 延迟抖动 | 降低被封概率，无需代理池 |
| **可视化** | Flask + 直写 SQL | 轻量级、无额外依赖、开发维护成本低 |

---

## 十一、项目文件清单

| 文件 | 行数 | 职责 |
|------|------|------|
| `main.py` | 346 | 主入口，CLI 参数解析，全流程编排 |
| `config.py` | 54 | 全局配置（路径/行为/优先级/状态码） |
| `database.py` | 48 | MySQL 连接管理 |
| `db_ops.py` | 398 | 5 张表的全部 CRUD 操作 |
| `webapp.py` | 378 | Flask 可视化看板（9 个 API + 1 个页面） |
| `crawlers/base.py` | 128 | 爬虫基类（Selenium 管理 + 接口定义） |
| `crawlers/fanqie.py` | 493 | 番茄爬虫（SSR+API 混合） |
| `crawlers/feilu.py` | 262 | 飞卢爬虫（HTML/BS4） |
| `crawlers/qidian.py` | 278 | 起点爬虫（移动站 SSR） |
| `crawlers/qimao.py` | 456 | 七猫爬虫（Nuxt SSR） |
| `services/task_manager.py` | 74 | 任务生命周期管理 |
| `services/file_manager.py` | 69 | 章节文件读写 + 封面下载 |
| `sql/schema.sql` | 121 | 数据库建表 DDL |
| `sql/data.sql` | 51 | 初始数据 |
| `sql/book_analyzer_full.sql` | 151 | 完整建库脚本 |

---

## 十二、扩展点

1. **新增平台**：继承 `BaseCrawler` 实现 4 个接口方法，在 `config.PLATFORM_LABELS` 注册，`main.py` 的 `CRAWLER_MAP` 中添加映射
2. **新增爬取步骤**：在 `main.run_full_pipeline()` 按需插入新 step
3. **API 扩展**：`webapp.py` 按 RESTful 风格新增 `@app.route`
4. **数据导出**：基于现有 5 张表可扩展 Excel/JSON 导出功能
5. **定时任务**：接入 cron 或 APScheduler，实现自动周期爬取
6. **封面 OSS**：封面存储可扩展为阿里云 OSS / 腾讯云 COS
