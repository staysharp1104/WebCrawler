"""重置已完成但章节数为0的书籍为待爬取状态，并创建章节爬取任务"""
import mysql.connector
import config

conn = mysql.connector.connect(
    host='localhost', user='root', password='12345678',
    database='book_analyzer', charset='utf8mb4'
)
cur = conn.cursor(dictionary=True)

# 1. 查出所有已完成但章节数为0的书
cur.execute("""
    SELECT book_id, title, source FROM books 
    WHERE crawl_status=2 AND chapter_count=0
""")
books = cur.fetchall()
print(f'待重置书籍: {len(books)} 本')

# 按source统计
by_source = {}
for b in books:
    by_source.setdefault(b['source'], []).append(b)
for src, lst in by_source.items():
    print(f'  {src}: {len(lst)} 本')

# 2. 重置 crawl_status=0，清空 chapter_count
cur.execute("""
    UPDATE books SET crawl_status=0, chapter_count=0 
    WHERE crawl_status=2 AND chapter_count=0
""")
updated = cur.rowcount
print(f'\n已重置 {updated} 本的状态')

# 3. 为这些书创建 crawl_chapter 任务
create_sql = """INSERT IGNORE INTO crawl_tasks 
    (task_type, source, target_id, status, priority)
    VALUES (%s, %s, %s, 0, %s)
"""
task_count = 0
for b in books:
    task_count += 1
    cur.execute(create_sql, (
        'crawl_chapter',
        b['source'],
        b['book_id'],
        config.TASK_PRIORITY["crawl_chapter"],
    ))

conn.commit()
print(f'已创建 {task_count} 个章节爬取任务')

# 验证
cur.execute('SELECT COUNT(*) AS cnt FROM crawl_tasks WHERE status=0')
print(f'当前待处理任务: {cur.fetchone()["cnt"]} 条')

conn.close()
