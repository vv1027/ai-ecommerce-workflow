"""
Agent工具封装 — 把数据库操作包装成Agent能调用的工具

术语讲解：
- 工具（Tool）：Agent能调用的功能，比如"查商品数据"、"创建任务"
- 工具描述：告诉Agent这个工具是干什么的、什么时候用、参数是什么
- 函数调用（Function Calling）：AI不直接回答，而是说"我要调用XX工具"
- 只读工具：只查询数据，不修改
- 写操作工具：会修改数据，需要谨慎，高风险操作需要人工确认
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from ..database.db import Database
from ..database.crud import (
    ProductCRUD, VideoCRUD, CampaignCRUD, TaskCRUD, ActionLogCRUD,
)
from ..database.models import TASK_TYPE, TASK_PRIORITY
from ..workflow.triggers import WorkflowTriggers
from ..config import get_config

logger = logging.getLogger(__name__)


class AgentTools:
    """
    Agent工具集 — 所有Agent能调用的工具都在这里

    工具分为两类：
    1. 只读查询工具（query_*）：安全，可随时调用
    2. 执行动作工具（action_*）：会修改数据，高风险需要人工确认
    """

    def __init__(self, db: Database):
        self.db = db
        self.product_crud = ProductCRUD(db)
        self.video_crud = VideoCRUD(db)
        self.campaign_crud = CampaignCRUD(db)
        self.task_crud = TaskCRUD(db)
        self.action_log_crud = ActionLogCRUD(db)
        self.workflow = WorkflowTriggers(db)
        self.config = get_config()

    # ============================================
    # 工具定义（名称、描述、参数说明）
    # Agent根据这些描述决定调用哪个工具
    # ============================================

    TOOL_DEFINITIONS = [
        {
            "name": "query_product_info",
            "description": "查询单个商品的详细信息，包括商品名、类目、佣金、状态、阶段、累计订单等",
            "parameters": {"product_id": "商品ID，如P001"},
            "category": "read",
        },
        {
            "name": "query_products_by_status",
            "description": "按状态查询商品列表，如查询所有'投流测试'状态的商品、所有'百单'阶段的商品",
            "parameters": {"status": "商品状态，如'投流测试'/'已确认'/'出单'/'百单'/'千单'"},
            "category": "read",
        },
        {
            "name": "query_video_info",
            "description": "查询单个视频的详细信息，包括所属商品、混剪状态、去重状态、订单数、消耗、ROI、是否出单素材",
            "parameters": {"video_id": "视频ID，如V001"},
            "category": "read",
        },
        {
            "name": "query_videos_by_product",
            "description": "查询某个商品下的所有视频，用于分析该商品的素材表现",
            "parameters": {"product_id": "商品ID，如P001"},
            "category": "read",
        },
        {
            "name": "query_ordered_videos",
            "description": "查询已出单的视频列表，可指定日期范围。用于回答'今天哪些视频已出单'",
            "parameters": {
                "date_from": "开始日期，格式YYYY-MM-DD，可选",
                "date_to": "结束日期，格式YYYY-MM-DD，可选",
            },
            "category": "read",
        },
        {
            "name": "query_need_ai_edit_videos",
            "description": "查询需要立即进入AI钩子精剪的视频（已出单但未创建精剪任务的）",
            "parameters": {},
            "category": "read",
        },
        {
            "name": "query_scaling_products",
            "description": "查询已进入百单或千单阶段的商品，用于回答'哪些商品已进入百单/千单阶段'",
            "parameters": {"tier": "可选，'百单'或'千单'，不填则返回全部"},
            "category": "read",
        },
        {
            "name": "query_stop_test_candidates",
            "description": "查询应该停测的素材（消耗高但无出单的投流计划），用于回答'哪些素材应停测'",
            "parameters": {},
            "category": "read",
        },
        {
            "name": "query_campaign_info",
            "description": "查询投流计划的详细信息，包括消耗、订单数、ROI、状态",
            "parameters": {"campaign_id": "投流计划ID，如C001"},
            "category": "read",
        },
        {
            "name": "query_tasks",
            "description": "查询任务列表，可按状态、类型、负责人筛选",
            "parameters": {
                "status": "可选，任务状态如'待处理'/'处理中'/'已完成'",
                "task_type": "可选，任务类型如'AI钩子精剪'/'停测/复盘'",
            },
            "category": "read",
        },
        {
            "name": "action_create_ai_edit_task",
            "description": "为出单视频创建AI钩子精剪任务（中风险，执行后告知用户）",
            "parameters": {
                "video_id": "视频ID，如V002",
                "reason": "创建原因，如'视频已出单，需要精剪提升转化率'",
            },
            "category": "write",
            "risk": "medium",
        },
        {
            "name": "action_create_stop_test_task",
            "description": "为无效素材创建停测/复盘任务（高风险，需要人工确认后执行）",
            "parameters": {
                "campaign_id": "投流计划ID，如C006",
                "reason": "停测原因，如'消耗300元无出单'",
            },
            "category": "write",
            "risk": "high",
        },
        {
            "name": "action_write_review_conclusion",
            "description": "写回复盘结论和下一步动作到任务（中风险）",
            "parameters": {
                "task_id": "任务ID",
                "conclusion": "复盘结论",
                "next_action": "下一步动作",
            },
            "category": "write",
            "risk": "medium",
        },
        {
            "name": "action_update_product_stage",
            "description": "更新商品阶段（高风险，需要人工确认）",
            "parameters": {
                "product_id": "商品ID",
                "stage": "新阶段，如'百单阶段'/'千单阶段'",
            },
            "category": "write",
            "risk": "high",
        },
    ]

    def get_tool_definitions(self) -> List[Dict]:
        """获取所有工具定义（供Agent使用）"""
        return self.TOOL_DEFINITIONS

    def get_read_tools(self) -> List[Dict]:
        """获取只读工具"""
        return [t for t in self.TOOL_DEFINITIONS if t["category"] == "read"]

    def get_write_tools(self) -> List[Dict]:
        """获取写操作工具"""
        return [t for t in self.TOOL_DEFINITIONS if t["category"] == "write"]

    # ============================================
    # 只读查询工具实现
    # ============================================

    def query_product_info(self, product_id: str) -> Dict[str, Any]:
        """查询商品详细信息"""
        product = self.product_crud.get_by_id(product_id)
        if not product:
            return {"success": False, "message": f"商品 {product_id} 不存在"}
        # 同时查该商品的视频统计
        videos = self.video_crud.get_by_product(product_id)
        ordered_count = sum(1 for v in videos if v["is_order_material"] == 1)
        total_video_orders = sum(v["order_count"] for v in videos)
        product["video_count"] = len(videos)
        product["ordered_video_count"] = ordered_count
        product["total_video_orders"] = total_video_orders
        return {"success": True, "data": product}

    def query_products_by_status(self, status: str) -> Dict[str, Any]:
        """按状态查询商品"""
        products = self.product_crud.get_by_status(status)
        # 也支持按阶段查询
        if not products:
            products = self.product_crud.get_by_stage(status)
        return {
            "success": True,
            "count": len(products),
            "data": products,
            "message": f"找到{len(products)}个状态为'{status}'的商品",
        }

    def query_video_info(self, video_id: str) -> Dict[str, Any]:
        """查询视频详细信息"""
        video = self.video_crud.get_by_id(video_id)
        if not video:
            return {"success": False, "message": f"视频 {video_id} 不存在"}
        return {"success": True, "data": video}

    def query_videos_by_product(self, product_id: str) -> Dict[str, Any]:
        """按商品查询视频"""
        videos = self.video_crud.get_by_product(product_id)
        return {
            "success": True,
            "count": len(videos),
            "data": videos,
            "message": f"商品 {product_id} 下有{len(videos)}条视频",
        }

    def query_ordered_videos(self, date_from: str = "", date_to: str = "") -> Dict[str, Any]:
        """查询已出单视频"""
        videos = self.video_crud.get_ordered_videos(date_from, date_to)
        return {
            "success": True,
            "count": len(videos),
            "data": videos,
            "message": f"找到{len(videos)}条出单视频",
        }

    def query_need_ai_edit_videos(self) -> Dict[str, Any]:
        """查询需要AI精剪的视频（出单但未创建精剪任务）"""
        videos = self.db.execute_query(
            "SELECT * FROM videos WHERE is_order_material = 1 AND ai_edit_task_created = 0"
        )
        return {
            "success": True,
            "count": len(videos),
            "data": videos,
            "message": f"找到{len(videos)}条需要AI精剪的视频",
        }

    def query_scaling_products(self, tier: str = "") -> Dict[str, Any]:
        """查询百单/千单阶段商品"""
        if tier == "百单":
            products = self.product_crud.get_by_stage("百单阶段")
        elif tier == "千单":
            products = self.product_crud.get_by_stage("千单阶段")
        else:
            products = self.product_crud.get_by_stage("百单阶段") + \
                       self.product_crud.get_by_stage("千单阶段")
        return {
            "success": True,
            "count": len(products),
            "data": products,
            "message": f"找到{len(products)}个进入放量阶段的商品",
        }

    def query_stop_test_candidates(self) -> Dict[str, Any]:
        """查询应该停测的素材"""
        max_cost = self.config.get("stop_test_rules.by_cost.max_cost", 300)
        campaigns = self.db.execute_query(
            f"SELECT * FROM campaigns WHERE status = '投流中' AND cost >= {max_cost} AND order_count = 0"
        )
        return {
            "success": True,
            "count": len(campaigns),
            "data": campaigns,
            "message": f"找到{len(campaigns)}个应停测的投流计划（消耗≥{max_cost}元且无出单）",
        }

    def query_campaign_info(self, campaign_id: str) -> Dict[str, Any]:
        """查询投流计划信息"""
        campaign = self.campaign_crud.get_by_id(campaign_id)
        if not campaign:
            return {"success": False, "message": f"投流计划 {campaign_id} 不存在"}
        return {"success": True, "data": campaign}

    def query_tasks(self, status: str = "", task_type: str = "") -> Dict[str, Any]:
        """查询任务列表"""
        if status:
            tasks = self.task_crud.get_by_status(status)
        elif task_type:
            tasks = self.task_crud.get_by_type(task_type)
        else:
            tasks = self.task_crud.get_all(limit=100)
        return {
            "success": True,
            "count": len(tasks),
            "data": tasks,
            "message": f"找到{len(tasks)}个任务",
        }

    # ============================================
    # 执行动作工具实现
    # ============================================

    def action_create_ai_edit_task(self, video_id: str, reason: str = "") -> Dict[str, Any]:
        """创建AI精剪任务"""
        video = self.video_crud.get_by_id(video_id)
        if not video:
            return {"success": False, "message": f"视频 {video_id} 不存在"}

        # 检查是否已创建
        if video["ai_edit_task_created"] == 1:
            return {"success": False, "message": f"视频 {video_id} 已创建过AI精剪任务，不重复创建"}

        product = self.product_crud.get_by_id(video["product_id"])
        task_id = f"AI{datetime.now().strftime('%Y%m%d%H%M%S')}{video_id}"

        self.task_crud.create(
            task_id=task_id,
            task_type=TASK_TYPE["AI_HOOK_EDIT"],
            trigger_source="Agent-数智员工",
            product_id=video["product_id"],
            video_id=video_id,
            owner=product.get("owner", "") if product else "",
            priority=TASK_PRIORITY["URGENT"],
            trigger_reason=reason or f"Agent根据出单数据，为视频 {video_id} 创建AI精剪任务",
        )
        self.video_crud.mark_ai_edit_task_created(video_id)

        self.action_log_crud.record(
            "agent", "create_ai_edit_task", "video", video_id,
            f"创建AI精剪任务 {task_id}: {reason}",
        )

        return {
            "success": True,
            "task_id": task_id,
            "message": f"已为视频 {video_id} 创建AI钩子精剪任务: {task_id}",
        }

    def action_create_stop_test_task(self, campaign_id: str, reason: str = "") -> Dict[str, Any]:
        """创建停测任务（高风险，调用前应已获得人工确认）"""
        campaign = self.campaign_crud.get_by_id(campaign_id)
        if not campaign:
            return {"success": False, "message": f"投流计划 {campaign_id} 不存在"}

        product = self.product_crud.get_by_id(campaign["product_id"])
        task_id = f"STOP{datetime.now().strftime('%Y%m%d%H%M%S')}{campaign_id}"

        self.task_crud.create(
            task_id=task_id,
            task_type=TASK_TYPE["STOP_TEST"],
            trigger_source="Agent-数智员工",
            product_id=campaign["product_id"],
            video_id=campaign["video_id"],
            campaign_id=campaign_id,
            owner=product.get("owner", "") if product else "",
            priority=TASK_PRIORITY["HIGH"],
            trigger_reason=reason or f"Agent根据停测规则，为投流计划 {campaign_id} 创建停测任务",
            need_confirm=1,
        )

        self.action_log_crud.record(
            "agent", "create_stop_test_task", "campaign", campaign_id,
            f"创建停测任务 {task_id}: {reason}",
        )

        return {
            "success": True,
            "task_id": task_id,
            "need_confirm": True,
            "message": f"已创建停测任务: {task_id}（高风险动作，需人工确认后执行）",
        }

    def action_write_review_conclusion(self, task_id: str, conclusion: str,
                                         next_action: str) -> Dict[str, Any]:
        """写回复盘结论"""
        task = self.task_crud.get_by_id(task_id)
        if not task:
            return {"success": False, "message": f"任务 {task_id} 不存在"}

        self.task_crud.write_review(task_id, conclusion, next_action)
        self.action_log_crud.record(
            "agent", "write_review", "task", task_id,
            f"写回复盘结论: {conclusion[:50]}...",
        )

        return {
            "success": True,
            "message": f"已为任务 {task_id} 写回复盘结论和下一步动作",
        }

    def action_update_product_stage(self, product_id: str, stage: str) -> Dict[str, Any]:
        """更新商品阶段（高风险）"""
        product = self.product_crud.get_by_id(product_id)
        if not product:
            return {"success": False, "message": f"商品 {product_id} 不存在"}

        self.product_crud.update_stage(product_id, stage)
        self.action_log_crud.record(
            "agent", "update_product_stage", "product", product_id,
            f"更新阶段为: {stage}",
        )

        return {
            "success": True,
            "message": f"商品 {product_id} 阶段已更新为: {stage}",
        }

    # ============================================
    # 工具调度器 — 根据工具名调用对应方法
    # ============================================

    def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """
        根据工具名调用对应方法

        Args:
            tool_name: 工具名称
            **kwargs: 工具参数

        Returns:
            工具执行结果
        """
        # 检查工具是否存在
        tool_names = [t["name"] for t in self.TOOL_DEFINITIONS]
        if tool_name not in tool_names:
            return {"success": False, "message": f"未知工具: {tool_name}，可用工具: {', '.join(tool_names)}"}

        # 调用对应方法
        method = getattr(self, tool_name, None)
        if not method:
            return {"success": False, "message": f"工具 {tool_name} 未实现"}

        try:
            result = method(**kwargs)
            logger.info(f"Agent工具调用: {tool_name} | 参数: {kwargs} | 结果: {result.get('message', '成功')}")
            return result
        except TypeError as e:
            return {"success": False, "message": f"工具参数错误: {e}"}
        except Exception as e:
            logger.error(f"Agent工具调用失败: {tool_name} | 错误: {e}")
            return {"success": False, "message": f"工具执行失败: {e}"}

    def get_tool_risk_level(self, tool_name: str) -> str:
        """获取工具风险等级"""
        for t in self.TOOL_DEFINITIONS:
            if t["name"] == tool_name:
                return t.get("risk", "low")
        return "unknown"
