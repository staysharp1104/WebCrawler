# book_analyzer 数据库导出文档

## 数据库概览

| 项目 | 值 |
|------|-----|
| 数据库名 | `book_analyzer` |
| MySQL 版本 | 8.0+ |
| 字符集 | utf8mb4 |
| 表数量 | 5 |
| 导出时间 | 2026-06-19 |

## 文件说明

```
sql/
├── schema.sql                 # 建表语句（仅 DDL，无数据）
├── data.sql                   # 数据导出（仅 INSERT，无建表）
├── book_analyzer_full.sql     # 完整备份（DDL + 数据）
└── README.md                  # 本文档
```

| 文件 | 用途 |
|------|------|
| `schema.sql` | 仅需建表结构时使用，不含任何数据 |
| `data.sql` | 已有表结构，仅需导入数据时使用 |
| `book_analyzer_full.sql` | **一键还原**，含建表 + 全量数据，推荐使用 |

---

## 导入方法

### 方法一：完整还原（推荐）

```bash
# 先创建数据库（如不存在）
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS book_analyzer DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"

# 一键导入完整备份
mysql -u root -p book_analyzer < book_analyzer_full.sql
```

### 方法二：分步导入

```bash
# 1. 先导入表结构
mysql -u root -p book_analyzer < schema.sql

# 2. 再导入数据
mysql -u root -p book_analyzer < data.sql
```

---

## 表结构说明

### 1. `rank_books` — 榜单原始数据

存储各平台新书榜爬取的原始排名快照，每条记录对应某平台某分类下的一本书。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INT AUTO_INCREMENT | 主键 |
| `book_id` | VARCHAR(64) | 平台侧书籍唯一 ID |
| `rank` | VARCHAR(16) | 榜单排名 |
| `title` | VARCHAR(512) | 书名 |
| `author` | VARCHAR(256) | 作者 |
| `book_url` | VARCHAR(1024) | 书籍详情页 URL |
| `description` | TEXT | 书籍简介 |
| `status` | VARCHAR(32) | 连载状态（连载中/完结） |
| `reader_count` | VARCHAR(32) | 读者数/人气值 |
| `category_label` | VARCHAR(128) | 所属分类（如玄幻、都市） |
| `source` | VARCHAR(32) | 来源平台：`fanqie` / `feilu` / `qimao` / `qidian` |
| `cover_url` | VARCHAR(512) | 封面图片原网址 |
| `created_at` | DATETIME | 入库时间 |

**唯一约束：** `source` + `book_id`（同平台同书仅存一条）

---

### 2. `books` — 书籍主数据

从榜单数据中提炼的书籍主体信息，用于追踪章节爬取进度。

| 字段 | 类型 | 说明 |
|------|------|------|
| `book_id` | VARCHAR(64) | 主键，平台侧书籍 ID |
| `title` | VARCHAR(512) | 书名 |
| `author` | VARCHAR(256) | 作者 |
| `book_url` | VARCHAR(1024) | 书籍详情页 URL |
| `intro` | TEXT | 书籍简介 |
| `category` | VARCHAR(128) | 所属分类 |
| `word_count` | INT | 总字数 |
| `status` | VARCHAR(32) | 连载状态 |
| `source` | VARCHAR(32) | 来源平台 |
| `chapter_count` | INT | **已爬取**章节数 |
| `total_chapters` | INT | 网站上显示的总章节数 |
| `crawl_status` | TINYINT | 爬取状态：`0`=未爬 / `1`=爬取中 / `2`=已完成 / `3`=失败 |
| `cover_url` | VARCHAR(512) | 封面图片原网址 |
| `cover_path` | VARCHAR(256) | 封面图片本地存储路径 |
| `created_at` | DATETIME | 入库时间 |
| `updated_at` | DATETIME | 最后更新时间 |

**主键：** `book_id`（使用 REPLACE INTO 实现去重更新）

---

### 3. `chapters` — 章节数据

每本书已爬取的章节元信息，正文以 `.txt` 文件形式存储在 `data/books/` 目录下。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT AUTO_INCREMENT | 主键 |
| `book_id` | VARCHAR(64) | 关联书籍 ID |
| `chapter_index` | INT | 章节序号（从 1 开始） |
| `chapter_title` | VARCHAR(512) | 章节标题 |
| `chapter_url` | VARCHAR(1024) | 章节页面 URL |
| `content_path` | VARCHAR(256) | 正文 `.txt` 文件相对路径（如 `data/books/10/1039126/001.txt`） |
| `content_size` | INT | 正文文件大小（字节） |
| `source` | VARCHAR(32) | 来源平台 |
| `created_at` | DATETIME | 入库时间 |

**唯一约束：** `book_id` + `chapter_index`（同书同章仅存一条）

---

### 4. `crawl_tasks` — 爬取任务队列

任务调度表，管理榜单爬取、章节爬取等任务的执行状态。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT AUTO_INCREMENT | 主键 |
| `task_type` | VARCHAR(32) | 任务类型（如 `rank` / `chapter`） |
| `source` | VARCHAR(32) | 目标平台 |
| `target_id` | VARCHAR(64) | 目标 ID（book_id 或分类 ID） |
| `status` | TINYINT | 状态：`0`=待执行 / `1`=执行中 / `2`=成功 / `3`=失败 |
| `retry_count` | INT | 已重试次数 |
| `error_msg` | TEXT | 最后错误信息 |
| `priority` | INT | 优先级（越大越先执行） |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 最后更新时间 |

---

### 5. `chat_history` — 辅助日志

记录爬取过程中的操作日志，便于问题追踪和数据分析。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT AUTO_INCREMENT | 主键 |
| `book_id` | VARCHAR(64) | 关联书籍 ID |
| `role` | VARCHAR(16) | 日志角色（system / user） |
| `content` | TEXT | 日志内容 |
| `source` | VARCHAR(32) | 来源平台 |
| `create_time` | DATETIME | 记录时间 |

---

## 表关系

```
rank_books (榜单快照)
     │
     │  book_id + source（去重后初始化）
     ▼
books (书籍主数据)
     │
     │  book_id（1:N）
     ▼
chapters (章节数据)  ←── 正文文件存储于 data/books/{source_prefix}/{book_id}/{NNN}.txt

crawl_tasks (任务队列)  ── 驱动整个爬取流程
chat_history (操作日志)  ── 记录爬取过程
```

## 常用查询示例

```sql
-- 查看各平台书籍数量
SELECT source, COUNT(*) AS cnt FROM books GROUP BY source;

-- 查看各平台爬取完成情况
SELECT source, crawl_status, COUNT(*) AS cnt
FROM books GROUP BY source, crawl_status;

-- 查看某本书已爬取的章节
SELECT chapter_index, chapter_title, content_path
FROM chapters WHERE book_id = '1039126' ORDER BY chapter_index;

-- 查看待执行的任务
SELECT * FROM crawl_tasks WHERE status = 0 ORDER BY priority DESC, created_at ASC;
```
