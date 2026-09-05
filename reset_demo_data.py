"""
演示数据一键重置脚本 — 录屏前运行，确保所有触发点都能顺利演示

使用方法：
    python reset_demo_data.py

作用：
    1. 重置P001状态为"已确认"（方便演示触发点A）
    2. 重置V001去重状态为"待去重"（方便演示触发点B）
    3. 重置V002订单数为0（方便演示触发点C出单）
    4. 重置P003阶段为"投流测试阶段"（方便演示触发点D百单）
    5. 重置P004阶段为"百单阶段"（方便演示触发点D千单）
    6. 重置C006状态为"投流中"（方便演示触发点E停测）
    7. 清空任务表和触发记录表（干净的演示环境）
"""

import sys
import os

# 把项目根目录加入Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database.db import get_db
from src.database.crud import ProductCRUD, VideoCRUD, CampaignCRUD, TaskCRUD
from src.logger import setup_logging

setup_logging()


def reset_demo_data():
    """重置演示数据"""
    db = get_db("data/ecommerce.db")
    db.connect()

    product_crud = ProductCRUD(db)
    video_crud = VideoCRUD(db)
    campaign_crud = CampaignCRUD(db)
    task_crud = TaskCRUD(db)

    print("=" * 50)
    print("正在重置演示数据...")
    print("=" * 50)

    # 1. 重置P001：状态改为"已确认"，佣金25%
    product_crud.update_status("P001", "已确认")
    product_crud.update_commission("P001", 25.0)
    product_crud.update_stage("P001", "选品阶段")
    print("✅ P001 已重置为'已确认'状态（触发点A就绪）")

    # 2. 重置V001：去重状态改为"待去重"，前端发布标记0
    db.execute_update(
        "UPDATE videos SET dedup_status='待去重', frontend_published=0, qianchuan_uploaded=0, updated_at=datetime('now','localtime') WHERE video_id='V001'"
    )
    print("✅ V001 已重置为'待去重'状态（触发点B就绪）")

    # 3. 重置V002：订单数改为0，出单素材标记0，AI精剪任务标记0
    db.execute_update(
        "UPDATE videos SET order_count=0, is_order_material=0, ai_edit_task_created=0, updated_at=datetime('now','localtime') WHERE video_id='V002'"
    )
    print("✅ V002 已重置为0订单（触发点C出单就绪）")

    # 4. 重置P003：阶段改为"投流测试阶段"
    product_crud.update_stage("P003", "投流测试阶段")
    product_crud.update_status("P003", "投流测试")
    print("✅ P003 已重置为'投流测试阶段'（触发点D百单就绪）")

    # 5. 重置P004：阶段改为"百单阶段"
    product_crud.update_stage("P004", "百单阶段")
    product_crud.update_status("P004", "放量")
    print("✅ P004 已重置为'百单阶段'（触发点D千单就绪）")

    # 6. 重置C006：状态改为"投流中"，异常标记0
    db.execute_update(
        "UPDATE campaigns SET status='投流中', is_abnormal=0, updated_at=datetime('now','localtime') WHERE campaign_id='C006'"
    )
    print("✅ C006 已重置为'投流中'状态（触发点E停测就绪）")

    # 7. 清空任务表和触发记录表（干净的演示环境）
    db.execute_update("DELETE FROM tasks")
    db.execute_update("DELETE FROM trigger_logs")
    db.execute_update("DELETE FROM action_logs")
    print("✅ 任务表和触发记录表已清空（干净的演示环境）")

    print("=" * 50)
    print("演示数据重置完成！")
    print("=" * 50)
    print()
    print("现在可以启动前端开始录屏了：")
    print("  python run.py ui")
    print()
    print("录屏流程参考 docs/录屏操作详细指南.md")
    print("=" * 50)


if __name__ == "__main__":
    reset_demo_data()
