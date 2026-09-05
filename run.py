"""
项目启动脚本 — 一键初始化数据库并启动服务

使用方法：
    python run.py init    # 初始化数据库（创建表+插入样例数据）
    python run.py api     # 启动FastAPI后端服务
    python run.py ui      # 启动Streamlit前端界面
    python run.py test    # 运行所有测试
    python run.py demo    # 运行全流程演示
    python run.py agent   # 启动Agent命令行对话
"""

import sys
import os

# 把项目根目录加入Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.logger import setup_logging
from src.config import get_config

# 初始化日志和配置
setup_logging()
config = get_config()


def init_database():
    """初始化数据库"""
    from src.database.db import get_db
    from src.database.models import create_tables, insert_sample_data

    print("=" * 50)
    print("正在初始化数据库...")
    print("=" * 50)

    db_path = config.get("database.path", "data/ecommerce.db")
    db = get_db(db_path)
    db.connect()
    create_tables(db)
    insert_sample_data(db)

    print(f"数据库初始化完成: {db_path}")
    print("已创建表: products, videos, campaigns, tasks, trigger_logs, action_logs")
    print("已插入样例数据: 5个商品, 6条视频, 6个投流计划")
    print("=" * 50)


def run_api():
    """启动FastAPI后端服务"""
    import uvicorn

    host = config.get("api.host", "0.0.0.0")
    port = config.get("api.port", 8000)

    print("=" * 50)
    print(f"启动API服务: http://{host}:{port}")
    print(f"接口文档: http://{host}:{port}/docs")
    print("=" * 50)

    uvicorn.run("src.api.main:app", host=host, port=port, reload=True)


def run_ui():
    """启动Streamlit前端界面"""
    port = config.get("ui.port", 8501)

    print("=" * 50)
    print(f"启动前端界面: http://localhost:{port}")
    print("=" * 50)

    os.system(f"streamlit run src/ui/app.py --server.port {port}")


def run_tests():
    """运行所有测试"""
    import pytest

    print("=" * 50)
    print("运行测试用例...")
    print("=" * 50)

    exit_code = pytest.main(["-v", "--tb=short", "tests/"])
    sys.exit(exit_code)


def run_demo():
    """运行全流程演示"""
    from src.database.db import get_db
    from src.workflow.triggers import WorkflowTriggers
    import json

    print("=" * 50)
    print("运行全流程演示...")
    print("=" * 50)

    db = get_db(config.get("database.path", "data/ecommerce.db"))
    triggers = WorkflowTriggers(db)
    result = triggers.run_full_workflow_demo()

    print("\n【演示结果】")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print("\n" + "=" * 50)
    print("全流程演示完成！")
    print("=" * 50)


def run_agent_chat():
    """启动Agent命令行对话"""
    from src.database.db import get_db
    from src.agent.agent import ReviewAgent

    print("=" * 50)
    print("素材与投流复盘数智员工")
    print("输入 'quit' 或 'exit' 退出")
    print("=" * 50)

    db = get_db(config.get("database.path", "data/ecommerce.db"))
    agent = ReviewAgent(db)

    print("\n你好！我是素材与投流复盘数智员工。")
    print("可以问我：出单视频、AI精剪、百单/千单商品、停测建议等。\n")

    while True:
        try:
            user_input = input("你: ").strip()
            if user_input.lower() in ["quit", "exit", "退出"]:
                print("再见！")
                break
            if not user_input:
                continue

            response = agent.chat(user_input)
            print(f"\n数智员工: {response}\n")
        except KeyboardInterrupt:
            print("\n再见！")
            break


def main():
    """主入口"""
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1].lower()

    if command == "init":
        init_database()
    elif command == "api":
        init_database()
        run_api()
    elif command == "ui":
        init_database()
        run_ui()
    elif command == "test":
        run_tests()
    elif command == "demo":
        init_database()
        run_demo()
    elif command == "agent":
        init_database()
        run_agent_chat()
    else:
        print(f"未知命令: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
