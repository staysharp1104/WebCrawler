"""
小说爬虫数据可视化看板 — 启动入口

启动方式:
    python webapp.py              # 默认 127.0.0.1:5000
    python webapp.py --port 8080  # 自定义端口
    python webapp.py --host 0.0.0.0  # 监听所有网络接口

访问:
    http://127.0.0.1:5000/        # 前端看板页面
"""
import argparse
from webapp import create_app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="爬虫数据看板")
    parser.add_argument("--port", "-p", type=int, default=5000, help="端口号")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="监听地址")
    args = parser.parse_args()

    app = create_app()
    print(f"📊 爬虫数据看板启动: http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=True)
