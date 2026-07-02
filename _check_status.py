"""检查书籍章节覆盖状态"""
import mysql.connector

conn = mysql.connector.connect(
    host='localhost', user='root', password='12345678',
    database='book_analyzer', charset='utf8mb4'
)
cur = conn.cursor(dictionary=True)

# 统计章节覆盖情况
cur.execute("""
    SELECT source,
           COUNT(*) AS total_books,
           SUM(CASE WHEN crawl_status=0 THEN 1 ELSE 0 END) AS pending,
           SUM(CASE WHEN crawl_status=2 THEN 1 ELSE 0 END) AS done,
           SUM(CASE WHEN crawl_status=3 THEN 1 ELSE 0 END) AS failed,
           SUM(chapter_count) AS total_chapters
    FROM books
    GROUP BY source
""")
print('=== 书籍爬取状态 ===')
for r in cur.fetchall():
    print(f'{r["source"]:>8s}  总{r["total_books"]:3d}本  '
          f'待爬{r["pending"]} 完成{r["done"]} 失败{r["failed"]}  '
          f'章节总数:{r["total_chapters"]}')

# 待爬取的书
cur.execute("""
    SELECT book_id, title, source, chapter_count, total_chapters
    FROM books WHERE crawl_status=0 LIMIT 10
""")
print('\n=== 待爬取书籍(前10) ===')
for r in cur.fetchall():
    print(f'  [{r["source"]}] {r["book_id"]}: {r["title"]} '
          f'(已有{r["chapter_count"]}/{r["total_chapters"]}章)')

# 已完成但章节数为0的异常
cur.execute("SELECT COUNT(*) AS cnt FROM books WHERE crawl_status=2 AND chapter_count=0")
r = cur.fetchone()
print(f'\n已完成但章节数为0的异常书籍: {r["cnt"]} 本')

cur.execute('SELECT COUNT(*) AS cnt FROM crawl_tasks')
print(f'crawl_tasks 剩余: {cur.fetchone()["cnt"]} 条')

# 按source统计异常书数量
cur.execute("""
    SELECT source, COUNT(*) AS cnt
    FROM books WHERE crawl_status=2 AND chapter_count=0
    GROUP BY source
""")
print('\n=== 各平台异常书籍(已完成但章节数为0) ===')
for r in cur.fetchall():
    print(f'  {r["source"]:>8s}: {r["cnt"]} 本')

# 查看chapters表覆盖
cur.execute("SELECT COUNT(DISTINCT book_id) FROM chapters")
cnt = cur.fetchone()["COUNT(DISTINCT book_id)"]
print(f'\nchapters 表覆盖了 {cnt} 本书')
cur.execute("SELECT COUNT(*) FROM chapters")
print(f'chapters 表总章节数: {cur.fetchone()["COUNT(*)"]}')

conn.close()
