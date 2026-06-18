"""文件管理服务 —— 章节正文存储、封面下载"""
import os
from typing import Optional
import config


def ensure_dirs():
    """确保所有数据目录存在"""
    for d in [config.CHAPTERS_DIR, config.COVERS_DIR, config.LOGS_DIR]:
        os.makedirs(d, exist_ok=True)


def book_chapter_dir(book_id: str) -> str:
    """获取书籍章节存储目录（按 book_id 前2位建子目录避免单目录文件过多）"""
    sub = book_id[:2] if len(book_id) >= 2 else "00"
    path = os.path.join(config.CHAPTERS_DIR, sub, book_id)
    os.makedirs(path, exist_ok=True)
    return path


def save_chapter_content(book_id: str, chapter_index: int, content: str) -> dict:
    """保存章节正文到文件，返回 {content_path, content_size}"""
    chapter_dir = book_chapter_dir(book_id)
    filename = f"{chapter_index:03d}.txt"
    filepath = os.path.join(chapter_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content.strip())
    size = os.path.getsize(filepath)
    # 相对路径
    rel_path = os.path.relpath(filepath, config.DATA_DIR)
    return {
        "content_path": rel_path,
        "content_size": size,
    }


def read_chapter_content(rel_path: str) -> str:
    """读取章节正文内容"""
    full_path = os.path.join(config.DATA_DIR, rel_path)
    if not os.path.exists(full_path):
        return ""
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()


def download_cover(url: str, book_id: str, source: str) -> Optional[str]:
    """下载封面图片，返回本地相对路径；失败返回 None"""
    import requests
    if not url:
        return None
    ext = os.path.splitext(url.split("?")[0])[1] or ".jpg"
    filename = f"{source}_{book_id}{ext}"
    save_dir = os.path.join(config.DATA_DIR, config.COVERS_DIR.lstrip("data/"), source)
    os.makedirs(save_dir, exist_ok=True)
    filepath = os.path.join(save_dir, filename)
    if os.path.exists(filepath):
        rel = os.path.relpath(filepath, config.DATA_DIR)
        return rel
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": config.USER_AGENTS[0]})
        if r.status_code == 200:
            with open(filepath, "wb") as f:
                f.write(r.content)
            rel = os.path.relpath(filepath, config.DATA_DIR)
            return rel
    except Exception as e:
        print(f"  [COVER] 下载失败 {url}: {e}")
    return None
