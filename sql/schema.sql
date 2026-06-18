
/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
DROP TABLE IF EXISTS `books`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `books` (
  `book_id` varchar(64) NOT NULL,
  `title` varchar(512) NOT NULL,
  `author` varchar(256) DEFAULT '',
  `book_url` varchar(1024) DEFAULT '',
  `intro` text,
  `category` varchar(128) DEFAULT '',
  `word_count` int DEFAULT '0',
  `status` varchar(32) DEFAULT '',
  `source` varchar(32) DEFAULT 'fanqie' COMMENT '来源: fanqie/feilu/qimao',
  `chapter_count` int DEFAULT '0' COMMENT '已爬取章节数',
  `total_chapters` int DEFAULT '0' COMMENT '网站上的总章节数',
  `crawl_status` tinyint DEFAULT '0' COMMENT '0=未爬,1=爬取中,2=已完成,3=失败',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `cover_url` varchar(512) DEFAULT '' COMMENT '封面图片原网址',
  `cover_path` varchar(256) DEFAULT '' COMMENT '封面图片本地路径',
  PRIMARY KEY (`book_id`),
  KEY `idx_source` (`source`),
  KEY `idx_created` (`created_at`),
  KEY `idx_status` (`crawl_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `chapters`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `chapters` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `book_id` varchar(64) NOT NULL,
  `chapter_index` int NOT NULL,
  `chapter_title` varchar(512) DEFAULT '',
  `chapter_url` varchar(1024) DEFAULT '',
  `content_path` varchar(256) DEFAULT '' COMMENT '正文文件相对路径(data/books/...)',
  `content_size` int DEFAULT '0' COMMENT '正文文件大小(字节)',
  `source` varchar(32) DEFAULT 'fanqie',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_book_chapter` (`book_id`,`chapter_index`),
  KEY `idx_book_id` (`book_id`),
  KEY `idx_source` (`source`)
) ENGINE=InnoDB AUTO_INCREMENT=4459 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `chat_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `chat_history` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `book_id` varchar(64) DEFAULT NULL,
  `role` varchar(16) DEFAULT NULL,
  `content` text,
  `source` varchar(32) DEFAULT 'fanqie',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_book` (`book_id`)
) ENGINE=InnoDB AUTO_INCREMENT=6077 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `crawl_tasks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `crawl_tasks` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_type` varchar(32) NOT NULL,
  `source` varchar(32) DEFAULT 'fanqie',
  `target_id` varchar(64) DEFAULT '',
  `status` tinyint DEFAULT '0',
  `retry_count` int DEFAULT '0',
  `error_msg` text,
  `priority` int DEFAULT '0',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_status` (`status`,`priority`),
  KEY `idx_type` (`task_type`,`source`)
) ENGINE=InnoDB AUTO_INCREMENT=6262 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `rank_books`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `rank_books` (
  `id` int NOT NULL AUTO_INCREMENT,
  `book_id` varchar(64) NOT NULL,
  `rank` varchar(16) DEFAULT '',
  `title` varchar(512) DEFAULT '',
  `author` varchar(256) DEFAULT '',
  `book_url` varchar(1024) DEFAULT '',
  `description` text,
  `status` varchar(32) DEFAULT '',
  `reader_count` varchar(32) DEFAULT '',
  `category_label` varchar(128) DEFAULT '',
  `source` varchar(32) DEFAULT 'fanqie',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `cover_url` varchar(512) DEFAULT '' COMMENT '封面图片原网址',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_source_book` (`source`,`book_id`),
  KEY `idx_source` (`source`)
) ENGINE=InnoDB AUTO_INCREMENT=4263 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- ----------------------------
-- 定时任务配置表 (scheduler_config)
-- 用于每周刷新任务的参数配置
-- ----------------------------
DROP TABLE IF EXISTS `scheduler_config`;
CREATE TABLE `scheduler_config` (
  `id` INT PRIMARY KEY AUTO_INCREMENT,
  `cron_expr` VARCHAR(64) NOT NULL DEFAULT '0 2 * * 0' COMMENT 'cron 表达式 (分 时 日 月 周)',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用定时任务',
  `weekday` INT NOT NULL DEFAULT 0 COMMENT '每周执行日 (0=周日, 1=周一, ..., 6=周六)',
  `hour` INT NOT NULL DEFAULT 2 COMMENT '执行小时 (0-23)',
  `minute` INT NOT NULL DEFAULT 0 COMMENT '执行分钟 (0-59)',
  `last_run_at` DATETIME DEFAULT NULL COMMENT '上次执行时间',
  `next_run_at` DATETIME DEFAULT NULL COMMENT '下次执行时间',
  `last_run_status` VARCHAR(32) DEFAULT '' COMMENT '上次执行结果 (success/failed)',
  `last_run_summary` VARCHAR(512) DEFAULT '' COMMENT '上次执行摘要',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务配置';

-- 插入默认配置 (每周日 02:00)
INSERT IGNORE INTO `scheduler_config` (`id`, `cron_expr`, `enabled`, `weekday`, `hour`, `minute`)
VALUES (1, '0 2 * * 0', 1, 0, 2, 0);

