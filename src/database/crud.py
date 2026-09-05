"""
CRUD操作模块 — 对4张表的增删改查封装

术语讲解：
- CRUD：Create(增)、Read(查)、Update(改)、Delete(删)
- 封装：把复杂的SQL语句藏起来，对外提供简单的方法调用
- 数据访问层：专门负责和数据库打交道的代码层，业务逻辑不直接写SQL
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class BaseCRUD:
    """CRUD基类 — 通用的增删改查方法"""

    def __init__(self, db, table_name: str, primary_key: str):
        """
        初始化CRUD对象

        Args:
            db: Database实例
            table_name: 表名
            primary_key: 主键字段名
        """
        self.db = db
        self.table_name = table_name
        self.primary_key = primary_key

    def get_by_id(self, id_value: str) -> Optional[Dict[str, Any]]:
        """按主键ID查询单条记录"""
        results = self.db.execute_query(
            f"SELECT * FROM {self.table_name} WHERE {self.primary_key} = ?",
            params=(id_value,),
            fetch_all=False,
        )
        return results[0] if results else None

    def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """查询所有记录（分页）"""
        return self.db.execute_query(
            f"SELECT * FROM {self.table_name} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params=(limit, offset),
        )

    def count(self) -> int:
        """统计记录总数"""
        result = self.db.execute_query(
            f"SELECT COUNT(*) as cnt FROM {self.table_name}",
            fetch_all=False,
        )
        return result[0]["cnt"] if result else 0

    def delete(self, id_value: str) -> bool:
        """
        按ID删除记录（软删除建议用update标记，这里是硬删除）

        注意：实际项目中建议用软删除（加个is_deleted字段），
        这里为了简单用硬删除
        """
        affected = self.db.execute_update(
            f"DELETE FROM {self.table_name} WHERE {self.primary_key} = ?",
            params=(id_value,),
        )
        return affected > 0

    def _update_updated_at(self, id_value: str):
        """更新updated_at字段"""
        self.db.execute_update(
            f"UPDATE {self.table_name} SET updated_at = datetime('now', 'localtime') WHERE {self.primary_key} = ?",
            params=(id_value,),
        )


class ProductCRUD(BaseCRUD):
    """商品表CRUD"""

    def __init__(self, db):
        super().__init__(db, "products", "product_id")

    def create(self, product_id: str, name: str, category: str = "",
               commission_rate: float = 0, owner: str = "",
               status: str = "待选品", stage: str = "选品阶段") -> bool:
        """创建商品"""
        try:
            self.db.execute_update(
                """INSERT INTO products (product_id, name, category, commission_rate, owner, status, stage)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                params=(product_id, name, category, commission_rate, owner, status, stage),
            )
            logger.info(f"创建商品成功: {product_id} - {name}")
            return True
        except Exception as e:
            logger.error(f"创建商品失败: {e}")
            return False

    def update_status(self, product_id: str, status: str) -> bool:
        """更新商品状态"""
        affected = self.db.execute_update(
            "UPDATE products SET status = ?, updated_at = datetime('now', 'localtime') WHERE product_id = ?",
            params=(status, product_id),
        )
        if affected > 0:
            logger.info(f"商品 {product_id} 状态更新为: {status}")
        return affected > 0

    def update_stage(self, product_id: str, stage: str) -> bool:
        """更新商品阶段"""
        affected = self.db.execute_update(
            "UPDATE products SET stage = ?, updated_at = datetime('now', 'localtime') WHERE product_id = ?",
            params=(stage, product_id),
        )
        return affected > 0

    def update_commission(self, product_id: str, commission_rate: float) -> bool:
        """更新佣金比例"""
        affected = self.db.execute_update(
            "UPDATE products SET commission_rate = ?, updated_at = datetime('now', 'localtime') WHERE product_id = ?",
            params=(commission_rate, product_id),
        )
        return affected > 0

    def add_orders(self, product_id: str, order_count: int) -> bool:
        """增加商品累计订单数"""
        affected = self.db.execute_update(
            "UPDATE products SET total_orders = total_orders + ?, updated_at = datetime('now', 'localtime') WHERE product_id = ?",
            params=(order_count, product_id),
        )
        return affected > 0

    def get_by_status(self, status: str) -> List[Dict[str, Any]]:
        """按状态查询商品"""
        return self.db.execute_query(
            "SELECT * FROM products WHERE status = ? ORDER BY updated_at DESC",
            params=(status,),
        )

    def get_by_stage(self, stage: str) -> List[Dict[str, Any]]:
        """按阶段查询商品"""
        return self.db.execute_query(
            "SELECT * FROM products WHERE stage = ? ORDER BY total_orders DESC",
            params=(stage,),
        )

    def get_products_with_orders_above(self, min_orders: int) -> List[Dict[str, Any]]:
        """查询累计订单超过指定值的商品"""
        return self.db.execute_query(
            "SELECT * FROM products WHERE total_orders >= ? ORDER BY total_orders DESC",
            params=(min_orders,),
        )


class VideoCRUD(BaseCRUD):
    """视频表CRUD"""

    def __init__(self, db):
        super().__init__(db, "videos", "video_id")

    def create(self, video_id: str, product_id: str, source: str = "",
               file_path: str = "", edit_status: str = "待混剪",
               dedup_status: str = "待去重") -> bool:
        """创建视频"""
        try:
            self.db.execute_update(
                """INSERT INTO videos (video_id, product_id, source, file_path, edit_status, dedup_status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                params=(video_id, product_id, source, file_path, edit_status, dedup_status),
            )
            logger.info(f"创建视频成功: {video_id} (商品: {product_id})")
            return True
        except Exception as e:
            logger.error(f"创建视频失败: {e}")
            return False

    def get_by_product(self, product_id: str) -> List[Dict[str, Any]]:
        """按商品ID查询所有视频"""
        return self.db.execute_query(
            "SELECT * FROM videos WHERE product_id = ? ORDER BY created_at",
            params=(product_id,),
        )

    def update_dedup_status(self, video_id: str, dedup_status: str) -> bool:
        """更新去重状态"""
        affected = self.db.execute_update(
            "UPDATE videos SET dedup_status = ?, updated_at = datetime('now', 'localtime') WHERE video_id = ?",
            params=(dedup_status, video_id),
        )
        return affected > 0

    def update_order_count(self, video_id: str, order_count: int) -> Optional[Dict[str, Any]]:
        """
        更新视频订单数，返回更新前的记录（用于变化检测）

        Returns:
            更新前的视频记录（用于对比订单数变化），如果视频不存在返回None
        """
        old = self.get_by_id(video_id)
        if old is None:
            return None
        self.db.execute_update(
            "UPDATE videos SET order_count = ?, updated_at = datetime('now', 'localtime') WHERE video_id = ?",
            params=(order_count, video_id),
        )
        return old

    def update_cost_and_roi(self, video_id: str, cost: float, roi: float) -> bool:
        """更新消耗和ROI"""
        affected = self.db.execute_update(
            "UPDATE videos SET cost = ?, roi = ?, updated_at = datetime('now', 'localtime') WHERE video_id = ?",
            params=(cost, roi, video_id),
        )
        return affected > 0

    def mark_as_order_material(self, video_id: str) -> bool:
        """标记为出单素材"""
        affected = self.db.execute_update(
            "UPDATE videos SET is_order_material = 1, updated_at = datetime('now', 'localtime') WHERE video_id = ?",
            params=(video_id,),
        )
        return affected > 0

    def mark_ai_edit_task_created(self, video_id: str) -> bool:
        """标记AI精剪任务已创建（幂等用）"""
        affected = self.db.execute_update(
            "UPDATE videos SET ai_edit_task_created = 1, updated_at = datetime('now', 'localtime') WHERE video_id = ?",
            params=(video_id,),
        )
        return affected > 0

    def get_ordered_videos(self, date_from: str = "", date_to: str = "") -> List[Dict[str, Any]]:
        """查询出单视频（可按日期范围）"""
        sql = "SELECT * FROM videos WHERE is_order_material = 1"
        params = []
        if date_from:
            sql += " AND updated_at >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND updated_at <= ?"
            params.append(date_to)
        sql += " ORDER BY updated_at DESC"
        return self.db.execute_query(sql, params=tuple(params) if params else None)

    def get_passed_dedup_count(self, product_id: str) -> int:
        """查询某商品去重通过的视频数量"""
        result = self.db.execute_query(
            "SELECT COUNT(*) as cnt FROM videos WHERE product_id = ? AND dedup_status = '去重通过'",
            params=(product_id,),
            fetch_all=False,
        )
        return result[0]["cnt"] if result else 0

    def get_frontend_published_count(self, product_id: str) -> int:
        """查询某商品已前端发布的视频数量"""
        result = self.db.execute_query(
            "SELECT COUNT(*) as cnt FROM videos WHERE product_id = ? AND frontend_published = 1",
            params=(product_id,),
            fetch_all=False,
        )
        return result[0]["cnt"] if result else 0


class CampaignCRUD(BaseCRUD):
    """投流计划表CRUD"""

    def __init__(self, db):
        super().__init__(db, "campaigns", "campaign_id")

    def create(self, campaign_id: str, product_id: str, video_id: str,
               status: str = "待创建", start_time: str = "") -> bool:
        """创建投流计划"""
        try:
            self.db.execute_update(
                """INSERT INTO campaigns (campaign_id, product_id, video_id, status, start_time)
                   VALUES (?, ?, ?, ?, ?)""",
                params=(campaign_id, product_id, video_id, status, start_time),
            )
            logger.info(f"创建投流计划成功: {campaign_id}")
            return True
        except Exception as e:
            logger.error(f"创建投流计划失败: {e}")
            return False

    def get_by_product(self, product_id: str) -> List[Dict[str, Any]]:
        """按商品ID查询投流计划"""
        return self.db.execute_query(
            "SELECT * FROM campaigns WHERE product_id = ? ORDER BY created_at DESC",
            params=(product_id,),
        )

    def get_by_video(self, video_id: str) -> List[Dict[str, Any]]:
        """按视频ID查询投流计划"""
        return self.db.execute_query(
            "SELECT * FROM campaigns WHERE video_id = ? ORDER BY created_at DESC",
            params=(video_id,),
        )

    def get_by_status(self, status: str) -> List[Dict[str, Any]]:
        """按状态查询投流计划"""
        return self.db.execute_query(
            "SELECT * FROM campaigns WHERE status = ? ORDER BY created_at DESC",
            params=(status,),
        )

    def backfill_data(self, campaign_id: str, cost: float, order_count: int, roi: float) -> bool:
        """
        回填投流数据（消耗、订单数、ROI）

        模拟从千川后台拉取数据更新到本地
        """
        affected = self.db.execute_update(
            """UPDATE campaigns SET cost = ?, order_count = ?, roi = ?,
               last_backfill = datetime('now', 'localtime'),
               updated_at = datetime('now', 'localtime')
               WHERE campaign_id = ?""",
            params=(cost, order_count, roi, campaign_id),
        )
        return affected > 0

    def update_status(self, campaign_id: str, status: str) -> bool:
        """更新投流计划状态"""
        affected = self.db.execute_update(
            "UPDATE campaigns SET status = ?, updated_at = datetime('now', 'localtime') WHERE campaign_id = ?",
            params=(status, campaign_id),
        )
        return affected > 0

    def mark_abnormal(self, campaign_id: str, reason: str = "") -> bool:
        """标记为异常"""
        affected = self.db.execute_update(
            "UPDATE campaigns SET is_abnormal = 1, updated_at = datetime('now', 'localtime') WHERE campaign_id = ?",
            params=(campaign_id,),
        )
        return affected > 0

    def get_running_campaigns(self) -> List[Dict[str, Any]]:
        """获取所有投流中的计划（用于停测检查）"""
        return self.db.execute_query(
            "SELECT * FROM campaigns WHERE status = '投流中' ORDER BY created_at",
        )


class TaskCRUD(BaseCRUD):
    """任务/复盘表CRUD"""

    def __init__(self, db):
        super().__init__(db, "tasks", "task_id")

    def create(self, task_id: str, task_type: str, trigger_source: str = "",
               product_id: str = "", video_id: str = "", campaign_id: str = "",
               owner: str = "", priority: str = "中", trigger_reason: str = "",
               need_confirm: int = 0) -> bool:
        """创建任务"""
        try:
            self.db.execute_update(
                """INSERT INTO tasks (task_id, task_type, trigger_source, product_id,
                   video_id, campaign_id, owner, priority, trigger_reason, need_confirm)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                params=(task_id, task_type, trigger_source, product_id, video_id,
                        campaign_id, owner, priority, trigger_reason, need_confirm),
            )
            logger.info(f"创建任务成功: {task_id} [{task_type}] 原因: {trigger_reason}")
            return True
        except Exception as e:
            logger.error(f"创建任务失败: {e}")
            return False

    def get_by_status(self, status: str) -> List[Dict[str, Any]]:
        """按状态查询任务"""
        return self.db.execute_query(
            "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC",
            params=(status,),
        )

    def get_by_type(self, task_type: str) -> List[Dict[str, Any]]:
        """按类型查询任务"""
        return self.db.execute_query(
            "SELECT * FROM tasks WHERE task_type = ? ORDER BY created_at DESC",
            params=(task_type,),
        )

    def get_by_product(self, product_id: str) -> List[Dict[str, Any]]:
        """按商品ID查询任务"""
        return self.db.execute_query(
            "SELECT * FROM tasks WHERE product_id = ? ORDER BY created_at DESC",
            params=(product_id,),
        )

    def get_pending_tasks(self, owner: str = "") -> List[Dict[str, Any]]:
        """获取待处理任务（可按负责人筛选）"""
        if owner:
            return self.db.execute_query(
                "SELECT * FROM tasks WHERE status = '待处理' AND owner = ? ORDER BY priority DESC, created_at",
                params=(owner,),
            )
        return self.db.execute_query(
            "SELECT * FROM tasks WHERE status = '待处理' ORDER BY priority DESC, created_at",
        )

    def update_status(self, task_id: str, status: str) -> bool:
        """更新任务状态"""
        affected = self.db.execute_update(
            "UPDATE tasks SET status = ?, updated_at = datetime('now', 'localtime') WHERE task_id = ?",
            params=(status, task_id),
        )
        return affected > 0

    def write_review(self, task_id: str, conclusion: str, next_action: str) -> bool:
        """写回复盘结论和下一步动作"""
        affected = self.db.execute_update(
            """UPDATE tasks SET review_conclusion = ?, next_action = ?,
               status = '已完成', updated_at = datetime('now', 'localtime')
               WHERE task_id = ?""",
            params=(conclusion, next_action, task_id),
        )
        return affected > 0

    def confirm_task(self, task_id: str) -> bool:
        """确认任务（人工确认后执行）"""
        affected = self.db.execute_update(
            "UPDATE tasks SET confirmed = 1, status = '处理中', updated_at = datetime('now', 'localtime') WHERE task_id = ?",
            params=(task_id,),
        )
        return affected > 0

    def exists_by_type_and_target(self, task_type: str, product_id: str = "",
                                    video_id: str = "", status_list: List[str] = None) -> bool:
        """
        检查是否已存在同类型同目标的任务（用于防重复）

        Args:
            task_type: 任务类型
            product_id: 商品ID
            video_id: 视频ID
            status_list: 要检查的状态列表，默认检查待处理和处理中
        """
        if status_list is None:
            status_list = ["待处理", "处理中"]

        placeholders = ",".join(["?"] * len(status_list))
        sql = f"SELECT COUNT(*) as cnt FROM tasks WHERE task_type = ? AND status IN ({placeholders})"
        params = [task_type] + status_list

        if product_id:
            sql += " AND product_id = ?"
            params.append(product_id)
        if video_id:
            sql += " AND video_id = ?"
            params.append(video_id)

        result = self.db.execute_query(sql, params=tuple(params), fetch_all=False)
        return result[0]["cnt"] > 0 if result else False


class TriggerLogCRUD(BaseCRUD):
    """触发记录CRUD（用于幂等）"""

    def __init__(self, db):
        super().__init__(db, "trigger_logs", "id")

    def exists(self, dedup_key: str) -> bool:
        """检查去重键是否已存在（幂等检查）"""
        result = self.db.execute_query(
            "SELECT COUNT(*) as cnt FROM trigger_logs WHERE dedup_key = ?",
            params=(dedup_key,),
            fetch_all=False,
        )
        return result[0]["cnt"] > 0 if result else False

    def record(self, trigger_type: str, dedup_key: str, target_id: str = "",
               result: str = "成功", message: str = "") -> bool:
        """记录触发日志"""
        try:
            self.db.execute_update(
                """INSERT INTO trigger_logs (trigger_type, dedup_key, target_id, result, message)
                   VALUES (?, ?, ?, ?, ?)""",
                params=(trigger_type, dedup_key, target_id, result, message),
            )
            return True
        except Exception as e:
            # 如果是重复键冲突，说明已经触发过了，不算错误
            if "UNIQUE constraint failed" in str(e):
                logger.info(f"触发记录已存在（幂等跳过）: {dedup_key}")
                return False
            logger.error(f"记录触发日志失败: {e}")
            raise

    def get_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近的触发记录"""
        return self.db.execute_query(
            "SELECT * FROM trigger_logs ORDER BY created_at DESC LIMIT ?",
            params=(limit,),
        )


class ActionLogCRUD(BaseCRUD):
    """操作日志CRUD"""

    def __init__(self, db):
        super().__init__(db, "action_logs", "id")

    def record(self, actor: str, action_type: str, target_type: str = "",
               target_id: str = "", details: str = "", result: str = "成功") -> bool:
        """记录操作日志"""
        try:
            self.db.execute_update(
                """INSERT INTO action_logs (actor, action_type, target_type, target_id, details, result)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                params=(actor, action_type, target_type, target_id, details, result),
            )
            return True
        except Exception as e:
            logger.error(f"记录操作日志失败: {e}")
            return False

    def get_by_actor(self, actor: str, limit: int = 50) -> List[Dict[str, Any]]:
        """按操作者查询日志"""
        return self.db.execute_query(
            "SELECT * FROM action_logs WHERE actor = ? ORDER BY created_at DESC LIMIT ?",
            params=(actor, limit),
        )
