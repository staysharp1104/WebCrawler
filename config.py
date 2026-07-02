"""全局配置"""

# ==================== 路径配置 ====================
DATA_DIR = "data"
CHAPTERS_DIR = f"{DATA_DIR}/books"     # 章节正文存放目录
COVERS_DIR = f"{DATA_DIR}/covers"      # 封面图片存放目录
LOGS_DIR = f"{DATA_DIR}/logs"          # 运行日志目录

# ==================== 爬取行为配置 ====================
RANK_PAGE_SIZE = 10         # 每个类目/榜单每页爬取前 N 本
CHAPTER_MAX = 10            # 每本书爬取前 N 章
MAX_RANK_PAGES = 2          # 每个子类目最大爬取页数（番茄类目分页深度）
REQUEST_TIMEOUT = 30        # 请求超时(秒)
SELENIUM_TIMEOUT = 30       # Selenium 等待超时
PAGE_LOAD_DELAY = 2         # 页面加载后等待(秒)
BETWEEN_BOOK_DELAY = 1      # 每本书请求间隔(秒)
BETWEEN_CHAPTER_DELAY = 0.5 # 每章请求间隔(秒)
MAX_RETRIES = 3             # 任务最大重试次数

# ==================== 第三方 API 代理配置 ====================
# 绕过 fanqie BDTuring 验证码的第三方代理 API
# 来源：addallno/fqdt 项目默认配置
FANQIE_PROXY_API = "http://101.35.133.34:5000/api/raw_full?item_id={}"
FANQIE_PROXY_API_FALLBACKS = [
    "http://101.35.133.34:5000/api/raw_full?item_id={}",
    "https://tt.sjmyzq.cn/api/raw_full?item_id={}",
]

# ==================== 任务优先级 ====================
TASK_PRIORITY = {
    "crawl_rank": 100,      # 榜单爬取 - 最高
    "crawl_book": 80,       # 书籍信息 - 次高
    "crawl_chapter": 60,    # 章节爬取 - 中等
    "download_cover": 40,   # 封面下载 - 较低
    "rank_weekly_refresh": 90, # 每周刷新 - 次高
}

# ==================== 平台配置 ====================
PLATFORM_LABELS = {
    "fanqie": "番茄小说",
    "feilu": "飞卢小说",
    "qimao": "七猫小说",
    "qidian": "起点中文网",
}

# 爬虫 UA 列表（轮换使用）
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]

# ==================== 爬虫状态码 ====================
CRAWL_STATUS_PENDING = 0       # 未爬取
CRAWL_STATUS_RUNNING = 1       # 爬取中
CRAWL_STATUS_DONE = 2          # 已完成
CRAWL_STATUS_FAILED = 3        # 失败

TASK_STATUS_PENDING = 0        # 待执行
TASK_STATUS_RUNNING = 1        # 执行中
TASK_STATUS_SUCCESS = 2        # 成功
TASK_STATUS_FAILED = 3         # 失败
