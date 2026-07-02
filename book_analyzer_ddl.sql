-- ============================================================
-- 数据库: book_analyzer
-- 导出时间: 2026-06-26
-- 共 9 张表
-- ============================================================

-- ------------------------------------------------------------
-- 表结构: books
-- 说明: 书籍信息表（核心业务表）
-- ------------------------------------------------------------
DROP TABLE IF EXISTS `books`;
CREATE TABLE `books` (
  `book_id`        varchar(64) NOT NULL               COMMENT '书籍ID（含平台前缀，如 qidian_123456）',
  `title`          varchar(512) NOT NULL               COMMENT '书名',
  `author`         varchar(256) DEFAULT ''              COMMENT '作者',
  `book_url`       varchar(1024) DEFAULT ''             COMMENT '书籍详情页URL',
  `intro`          text                                 COMMENT '书籍简介',
  `category`       varchar(128) DEFAULT ''              COMMENT '分类（如 玄幻/东方玄幻）',
  `word_count`     int DEFAULT '0'                      COMMENT '字数',
  `status`         varchar(32) DEFAULT ''               COMMENT '连载/完结',
  `source`         varchar(32) DEFAULT 'fanqie'         COMMENT '来源平台: fanqie/feilu/qimao/qidian',
  `chapter_count`  int DEFAULT '0'                      COMMENT '已爬取章节数',
  `total_chapters` int DEFAULT '0'                      COMMENT '网站上的总章节数',
  `crawl_status`   tinyint DEFAULT '0'                  COMMENT '爬取状态: 0=未爬,1=爬取中,2=已完成,3=失败',
  `created_at`     datetime DEFAULT CURRENT_TIMESTAMP   COMMENT '创建时间',
  `updated_at`     datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `cover_url`      varchar(512) DEFAULT ''              COMMENT '封面图片原网址',
  `cover_path`     varchar(256) DEFAULT ''              COMMENT '封面图片本地相对路径',
  PRIMARY KEY (`book_id`),
  KEY `idx_source`  (`source`),
  KEY `idx_created` (`created_at`),
  KEY `idx_status`  (`crawl_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='书籍信息表';

-- ------------------------------------------------------------
-- 表结构: chapters
-- 说明: 章节信息表（每本书前10章正文）
-- ------------------------------------------------------------
DROP TABLE IF EXISTS `chapters`;
CREATE TABLE `chapters` (
  `id`             bigint NOT NULL AUTO_INCREMENT       COMMENT '自增主键',
  `book_id`        varchar(64) NOT NULL                 COMMENT '书籍ID',
  `chapter_index`  int NOT NULL                         COMMENT '章节序号（从1开始）',
  `chapter_title`  varchar(512) DEFAULT ''              COMMENT '章节标题',
  `chapter_url`    varchar(1024) DEFAULT ''             COMMENT '章节原文URL',
  `content_path`   varchar(256) DEFAULT ''              COMMENT '正文文件相对路径(data/books/...)',
  `content_size`   int DEFAULT '0'                      COMMENT '正文文件大小(字节)',
  `source`         varchar(32) DEFAULT 'fanqie'         COMMENT '来源平台',
  `created_at`     datetime DEFAULT CURRENT_TIMESTAMP   COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_book_chapter` (`book_id`,`chapter_index`) COMMENT '每本书的章节序号唯一',
  KEY `idx_book_id` (`book_id`),
  KEY `idx_source`  (`source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='章节信息表';

-- ------------------------------------------------------------
-- 表结构: rank_books
-- 说明: 榜单原始快照表（历史排名数据）
-- ------------------------------------------------------------
DROP TABLE IF EXISTS `rank_books`;
CREATE TABLE `rank_books` (
  `id`              int NOT NULL AUTO_INCREMENT         COMMENT '自增主键',
  `book_id`         varchar(64) NOT NULL                COMMENT '书籍ID',
  `rank`            varchar(16) DEFAULT ''              COMMENT '榜单排名',
  `title`           varchar(512) DEFAULT ''             COMMENT '书名',
  `author`          varchar(256) DEFAULT ''             COMMENT '作者',
  `book_url`        varchar(1024) DEFAULT ''            COMMENT '书籍URL',
  `description`     text                                COMMENT '书籍简介',
  `status`          varchar(32) DEFAULT ''              COMMENT '连载/完结',
  `reader_count`    varchar(32) DEFAULT ''              COMMENT '阅读量/人气值',
  `category_label`  varchar(128) DEFAULT ''             COMMENT '榜单分类标签（如 综合榜单/月票榜/玄幻）',
  `source`          varchar(32) DEFAULT 'fanqie'        COMMENT '来源平台',
  `created_at`      datetime DEFAULT CURRENT_TIMESTAMP  COMMENT '创建时间(榜单快照时间)',
  `cover_url`       varchar(512) DEFAULT ''             COMMENT '封面图片原网址',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_source_book` (`source`,`book_id`)     COMMENT '同平台同本书只保留一条',
  KEY `idx_source` (`source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='榜单原始快照表';

-- ------------------------------------------------------------
-- 表结构: crawl_tasks
-- 说明: 爬取任务调度表
-- ------------------------------------------------------------
DROP TABLE IF EXISTS `crawl_tasks`;
CREATE TABLE `crawl_tasks` (
  `id`           bigint NOT NULL AUTO_INCREMENT        COMMENT '自增主键',
  `task_type`    varchar(32) NOT NULL                  COMMENT '任务类型: crawl_rank/crawl_book/crawl_chapter/download_cover/rank_weekly_refresh',
  `source`       varchar(32) DEFAULT 'fanqie'           COMMENT '来源平台',
  `target_id`    varchar(64) DEFAULT ''                COMMENT '目标ID(书籍ID或留空)',
  `status`       tinyint DEFAULT '0'                   COMMENT '状态: 0=待执行,1=执行中,2=成功,3=失败',
  `retry_count`  int DEFAULT '0'                       COMMENT '已重试次数',
  `error_msg`    text                                  COMMENT '错误信息',
  `priority`     int DEFAULT '0'                       COMMENT '优先级(越高越先执行)',
  `created_at`   datetime DEFAULT CURRENT_TIMESTAMP    COMMENT '创建时间',
  `updated_at`   datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_status` (`status`,`priority`),
  KEY `idx_type`   (`task_type`,`source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='爬取任务调度表';

-- ------------------------------------------------------------
-- 表结构: chat_history
-- 说明: 操作日志/辅助日志表
-- ------------------------------------------------------------
DROP TABLE IF EXISTS `chat_history`;
CREATE TABLE `chat_history` (
  `id`          bigint NOT NULL AUTO_INCREMENT         COMMENT '自增主键',
  `book_id`     varchar(64) DEFAULT NULL               COMMENT '关联书籍ID',
  `role`        varchar(16) DEFAULT NULL               COMMENT '角色(system/user)',
  `content`     text                                   COMMENT '日志内容',
  `source`      varchar(32) DEFAULT 'fanqie'           COMMENT '来源平台',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP     COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_book` (`book_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='操作日志/辅助日志表';

-- ------------------------------------------------------------
-- 表结构: scheduler_config
-- 说明: 定时任务配置（单行配置表）
-- ------------------------------------------------------------
DROP TABLE IF EXISTS `scheduler_config`;
CREATE TABLE `scheduler_config` (
  `id`               int NOT NULL AUTO_INCREMENT        COMMENT '主键(固定id=1)',
  `cron_expr`        varchar(64) NOT NULL DEFAULT '0 2 * * 0' COMMENT 'cron 表达式 (分 时 日 月 周)',
  `enabled`          tinyint(1) NOT NULL DEFAULT '1'   COMMENT '是否启用定时任务(1=启用)',
  `weekday`          int NOT NULL DEFAULT '0'           COMMENT '每周执行日 (0=周日,1=周一,...,6=周六)',
  `hour`             int NOT NULL DEFAULT '2'           COMMENT '执行小时 (0-23)',
  `minute`           int NOT NULL DEFAULT '0'           COMMENT '执行分钟 (0-59)',
  `last_run_at`      datetime DEFAULT NULL             COMMENT '上次执行时间',
  `next_run_at`      datetime DEFAULT NULL             COMMENT '下次执行时间',
  `last_run_status`  varchar(32) DEFAULT ''             COMMENT '上次执行结果 (success/failed)',
  `last_run_summary` varchar(512) DEFAULT ''            COMMENT '上次执行摘要',
  `created_at`       timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`       timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='定时任务配置表';

-- ------------------------------------------------------------
-- 表结构: prompt_templates
-- 说明: Prompt模板表（分析/聊天用）
-- ------------------------------------------------------------
DROP TABLE IF EXISTS `prompt_templates`;
CREATE TABLE `prompt_templates` (
  `id`           int NOT NULL AUTO_INCREMENT           COMMENT '自增主键',
  `name`         varchar(128) NOT NULL                 COMMENT '模板名称',
  `description`  varchar(512) DEFAULT ''               COMMENT '模板描述',
  `scene`        varchar(64) DEFAULT ''                COMMENT '使用场景(analysis/chat/custom)',
  `content`      text NOT NULL                         COMMENT 'Prompt正文',
  `is_quick_btn` tinyint(1) DEFAULT '0'               COMMENT '是否作为快捷分析按钮(1=是)',
  `is_system`    tinyint(1) DEFAULT '0'               COMMENT '系统内置保护模板(不可删除)',
  `enabled`      tinyint(1) DEFAULT '1'               COMMENT '启用状态(1=启用)',
  `sort_order`   int DEFAULT '0'                       COMMENT '排序序号',
  `created_at`   datetime DEFAULT CURRENT_TIMESTAMP    COMMENT '创建时间',
  `updated_at`   datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Prompt模板表';

-- ------------------------------------------------------------
-- 表结构: rag_index_info
-- 说明: RAG 索引元数据表
-- ------------------------------------------------------------
DROP TABLE IF EXISTS `rag_index_info`;
CREATE TABLE `rag_index_info` (
  `book_id`               varchar(64) NOT NULL          COMMENT '关联books.book_id',
  `status`                varchar(32) DEFAULT 'not_built' COMMENT '索引状态: not_built/built/rebuilding',
  `chunk_size`            int DEFAULT '500'             COMMENT '分块大小(字符数)',
  `overlap`               int DEFAULT '100'             COMMENT '重叠字数',
  `top_k`                 int DEFAULT '3'               COMMENT '召回Top数量',
  `short_book_full_text`  tinyint(1) DEFAULT '1'       COMMENT '短书籍全文注入策略开关(1=启用)',
  `chunk_count`           int DEFAULT '0'               COMMENT '文本总块数',
  `word_count`            int DEFAULT '0'               COMMENT '总字数',
  `built_at`              datetime DEFAULT NULL         COMMENT '索引构建时间',
  `cache_path`            varchar(256) DEFAULT ''       COMMENT 'pickle缓存文件路径',
  `updated_at`            datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`book_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='RAG索引元数据表';

-- ------------------------------------------------------------
-- 表结构: rag_source_records
-- 说明: AI回答溯源记录表
-- ------------------------------------------------------------
DROP TABLE IF EXISTS `rag_source_records`;
CREATE TABLE `rag_source_records` (
  `id`               bigint NOT NULL AUTO_INCREMENT    COMMENT '自增主键',
  `chat_message_id`  bigint NOT NULL                   COMMENT '关联chat_history.id',
  `book_id`          varchar(64) NOT NULL              COMMENT '书籍ID',
  `chapter_index`    int NOT NULL                      COMMENT '章节索引',
  `chapter_title`    varchar(512) DEFAULT ''           COMMENT '章节标题',
  `excerpt`          text                              COMMENT '引用的原文段落(前300字)',
  `rank`             tinyint DEFAULT '0'               COMMENT '相关性排名(1-3)',
  `created_at`       datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_chat_message` (`chat_message_id`),
  KEY `idx_book`         (`book_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='AI回答溯源记录表';
