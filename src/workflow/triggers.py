"""
核心自动化工作流 — 6个触发点（测试题权重最高，30分）

触发点：
A. 商品确认 — 商品状态=已确认且佣金已填写 → 自动进入素材任务
B. 去重完成 — 视频去重通过 → 第1条前端发布，其余千川上传
C. 出单触发 — 视频订单从0变≥1 → 标记出单素材+创建AI精剪任务
D. 放量分级 — 商品累计订单达阈值 → 百单/千单阶段+放量任务
E. 无效素材 — 消耗达标无出单 → 停测/复盘任务
F. 日/批次复盘 — 汇总数据输出结构化复盘结果

术语讲解：
- 触发点：满足某个条件时自动执行一段逻辑
- 幂等性：同一个操作执行多次结果一样，不会重复处理
- 去重键：用来判断是否重复的唯一标识
- 事件驱动：发生了什么事就做什么反应，不是按顺序执行
"""

import logging
import uuid
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta

from ..database.db import Database
from ..database.crud import (
    ProductCRUD, VideoCRUD, CampaignCRUD, TaskCRUD,
    TriggerLogCRUD, ActionLogCRUD,
)
from ..database.models import TASK_TYPE, TASK_PRIORITY, TASK_STATUS
from .state_machine import ProductStateMachine
from ..config import get_config

logger = logging.getLogger(__name__)


class WorkflowTriggers:
    """
    工作流触发器 — 实现6个自动化触发点

    使用方法：
        triggers = WorkflowTriggers(db)
        triggers.trigger_a_product_confirm("P001")
        triggers.trigger_c_order_detected("V002", 1)
    """

    def __init__(self, db: Database):
        """
        初始化触发器

        Args:
            db: Database实例
        """
        self.db = db
        self.product_crud = ProductCRUD(db)
        self.video_crud = VideoCRUD(db)
        self.campaign_crud = CampaignCRUD(db)
        self.task_crud = TaskCRUD(db)
        self.trigger_log_crud = TriggerLogCRUD(db)
        self.action_log_crud = ActionLogCRUD(db)
        self.state_machine = ProductStateMachine()
        self.config = get_config()

    def _generate_task_id(self, prefix: str = "T") -> str:
        """生成任务ID（前缀+时间戳+短UUID）"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        short_uuid = uuid.uuid4().hex[:6].upper()
        return f"{prefix}{timestamp}{short_uuid}"

    def _check_idempotent(self, dedup_key: str) -> bool:
        """
        幂等检查：返回True表示是重复触发，应该跳过

        Args:
            dedup_key: 去重键

        Returns:
            True=重复触发应跳过，False=首次触发可执行
        """
        exists = self.trigger_log_crud.exists(dedup_key)
        if exists:
            logger.info(f"幂等检查：触发已存在，跳过执行 | dedup_key={dedup_key}")
        return exists

    def _record_trigger(self, trigger_type: str, dedup_key: str, target_id: str = "",
                        result: str = "成功", message: str = "") -> None:
        """记录触发日志"""
        self.trigger_log_crud.record(trigger_type, dedup_key, target_id, result, message)

    def _record_action(self, action_type: str, target_type: str = "", target_id: str = "",
                       details: str = "", result: str = "成功") -> None:
        """记录操作日志"""
        self.action_log_crud.record("workflow", action_type, target_type, target_id, details, result)

    # ============================================
    # 触发点A：商品确认自动化
    # ============================================
    def trigger_a_product_confirm(self, product_id: str) -> Dict[str, Any]:
        """
        触发点A：商品确认自动化

        规则：
        - 当商品状态="已确认"且佣金已填写 → 自动创建"素材搜集"任务
        - 当商品状态="已确认"但佣金为空 → 阻断，创建"佣金待填写"提醒任务

        Args:
            product_id: 商品ID

        Returns:
            执行结果字典
        """
        logger.info(f"[触发点A] 商品确认触发 | product_id={product_id}")

        # 幂等检查
        dedup_key = f"trigger:A:{product_id}:confirmed"
        if self._check_idempotent(dedup_key):
            return {"success": False, "skipped": True, "message": "重复触发，已跳过"}

        # 查询商品
        product = self.product_crud.get_by_id(product_id)
        if not product:
            msg = f"商品不存在: {product_id}"
            logger.error(msg)
            self._record_trigger("A", dedup_key, product_id, "失败", msg)
            return {"success": False, "message": msg}

        # 检查状态
        if product["status"] != ProductStateMachine.CONFIRMED:
            msg = f"商品状态不是'已确认'，当前状态: {product['status']}"
            logger.warning(msg)
            self._record_trigger("A", dedup_key, product_id, "失败", msg)
            return {"success": False, "message": msg}

        # 检查佣金
        commission = product.get("commission_rate", 0)
        if not commission or commission <= 0:
            # 佣金为空 → 阻断，创建佣金待填写提醒
            task_id = self._generate_task_id("COMM")
            self.task_crud.create(
                task_id=task_id,
                task_type=TASK_TYPE["COMMISSION_FILL"],
                trigger_source="触发点A-商品确认",
                product_id=product_id,
                owner=product.get("owner", ""),
                priority=TASK_PRIORITY["HIGH"],
                trigger_reason=f"商品 {product_id}({product['name']}) 已确认但佣金未填写，请补充佣金比例",
                need_confirm=0,
            )
            msg = f"佣金未填写，已阻断并创建佣金填写提醒任务: {task_id}"
            logger.warning(msg)
            self._record_trigger("A", dedup_key, product_id, "阻断", msg)
            self._record_action("create_commission_task", "task", task_id, msg)
            return {
                "success": True,
                "blocked": True,
                "message": msg,
                "task_id": task_id,
                "task_type": TASK_TYPE["COMMISSION_FILL"],
            }

        # 佣金已填写 → 创建素材搜集任务
        task_id = self._generate_task_id("MAT")
        self.task_crud.create(
            task_id=task_id,
            task_type=TASK_TYPE["MATERIAL_COLLECT"],
            trigger_source="触发点A-商品确认",
            product_id=product_id,
            owner=product.get("owner", ""),
            priority=TASK_PRIORITY["MEDIUM"],
            trigger_reason=f"商品 {product_id}({product['name']}) 已确认，佣金{commission}%，请开始搜集素材",
            need_confirm=0,
        )

        # 更新商品状态到"素材搜集"
        self.product_crud.update_status(product_id, ProductStateMachine.MATERIAL_COLLECTING)

        msg = f"商品确认成功，已创建素材搜集任务: {task_id}"
        logger.info(msg)
        self._record_trigger("A", dedup_key, product_id, "成功", msg)
        self._record_action("create_material_task", "task", task_id, msg)

        return {
            "success": True,
            "blocked": False,
            "message": msg,
            "task_id": task_id,
            "task_type": TASK_TYPE["MATERIAL_COLLECT"],
        }

    # ============================================
    # 触发点B：去重完成分流
    # ============================================
    def trigger_b_dedup_complete(self, video_id: str) -> Dict[str, Any]:
        """
        触发点B：去重完成分流

        规则：
        - 视频去重通过后：
          - 同一商品的第1条通过视频 → 创建"前端挂车发布"任务
          - 同一商品的第2条及以后 → 进入"千川上传/建计划"队列

        Args:
            video_id: 视频ID

        Returns:
            执行结果字典
        """
        logger.info(f"[触发点B] 去重完成触发 | video_id={video_id}")

        # 幂等检查
        dedup_key = f"trigger:B:{video_id}:dedup_passed"
        if self._check_idempotent(dedup_key):
            return {"success": False, "skipped": True, "message": "重复触发，已跳过"}

        # 查询视频
        video = self.video_crud.get_by_id(video_id)
        if not video:
            msg = f"视频不存在: {video_id}"
            logger.error(msg)
            self._record_trigger("B", dedup_key, video_id, "失败", msg)
            return {"success": False, "message": msg}

        # 检查去重状态
        if video["dedup_status"] != "去重通过":
            msg = f"视频去重状态不是'去重通过'，当前状态: {video['dedup_status']}"
            logger.warning(msg)
            self._record_trigger("B", dedup_key, video_id, "失败", msg)
            return {"success": False, "message": msg}

        product_id = video["product_id"]
        product = self.product_crud.get_by_id(product_id)

        # 判断这是该商品的第几条去重通过视频
        # 注意：要包含当前这条，所以查询时如果当前视频还没算进去，需要+1
        passed_count = self.video_crud.get_passed_dedup_count(product_id)
        frontend_count = self.video_crud.get_frontend_published_count(product_id)

        max_frontend = self.config.get("dedup_routing.frontend_videos_per_product", 1)

        if frontend_count < max_frontend:
            # 第1条（或前N条）→ 前端挂车发布
            task_id = self._generate_task_id("PUB")
            self.task_crud.create(
                task_id=task_id,
                task_type=TASK_TYPE["FRONTEND_PUBLISH"],
                trigger_source="触发点B-去重完成",
                product_id=product_id,
                video_id=video_id,
                owner=product.get("owner", "") if product else "",
                priority=TASK_PRIORITY["MEDIUM"],
                trigger_reason=f"视频 {video_id} 去重通过，为商品 {product_id} 的第{passed_count}条通过视频，分配前端挂车发布",
                need_confirm=0,
            )
            # 标记视频已前端发布
            self.db.execute_update(
                "UPDATE videos SET frontend_published = 1, updated_at = datetime('now', 'localtime') WHERE video_id = ?",
                params=(video_id,),
            )
            route = "前端挂车发布"
        else:
            # 其余 → 千川上传/建计划
            task_id = self._generate_task_id("QC")
            self.task_crud.create(
                task_id=task_id,
                task_type=TASK_TYPE["QIANCHUAN_UPLOAD"],
                trigger_source="触发点B-去重完成",
                product_id=product_id,
                video_id=video_id,
                owner=product.get("owner", "") if product else "",
                priority=TASK_PRIORITY["MEDIUM"],
                trigger_reason=f"视频 {video_id} 去重通过，为商品 {product_id} 的第{passed_count}条通过视频，分配千川上传/建计划",
                need_confirm=0,
            )
            # 标记视频已千川上传
            self.db.execute_update(
                "UPDATE videos SET qianchuan_uploaded = 1, updated_at = datetime('now', 'localtime') WHERE video_id = ?",
                params=(video_id,),
            )
            # 同时创建投流计划（模拟）
            campaign_id = f"C{video_id[1:]}"
            if not self.campaign_crud.get_by_id(campaign_id):
                self.campaign_crud.create(
                    campaign_id=campaign_id,
                    product_id=product_id,
                    video_id=video_id,
                    status="已创建",
                    start_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
            route = "千川上传/建计划"

        msg = f"视频 {video_id} 去重通过，分流至: {route}，任务ID: {task_id}"
        logger.info(msg)
        self._record_trigger("B", dedup_key, video_id, "成功", msg)
        self._record_action("dedup_routing", "video", video_id, msg)

        return {
            "success": True,
            "message": msg,
            "task_id": task_id,
            "route": route,
            "passed_count": passed_count,
        }

    # ============================================
    # 触发点C：出单触发AI精剪
    # ============================================
    def trigger_c_order_detected(self, video_id: str, new_order_count: int) -> Dict[str, Any]:
        """
        触发点C：出单触发AI精剪

        规则：
        - 任一视频订单数从0变为≥1：
          - 自动标记"出单素材"
          - 只创建1次"AI钩子重新剪辑"任务（幂等）
          - 写回触发原因和时间

        Args:
            video_id: 视频ID
            new_order_count: 新的订单数

        Returns:
            执行结果字典
        """
        logger.info(f"[触发点C] 出单触发 | video_id={video_id}, new_order_count={new_order_count}")

        # 幂等检查（用视频ID做去重键，一个视频只触发一次出单）
        dedup_key = f"trigger:C:{video_id}:order_detected"
        if self._check_idempotent(dedup_key):
            # 即使重复触发，也要更新订单数
            self.video_crud.update_order_count(video_id, new_order_count)
            return {"success": False, "skipped": True, "message": "重复触发，已跳过（订单数已更新）"}

        # 查询视频（获取旧订单数）
        video = self.video_crud.get_by_id(video_id)
        if not video:
            msg = f"视频不存在: {video_id}"
            logger.error(msg)
            self._record_trigger("C", dedup_key, video_id, "失败", msg)
            return {"success": False, "message": msg}

        old_order_count = video["order_count"]
        min_orders = self.config.get("order_trigger.min_orders", 1)

        # 变化检测：只有从0变到≥min_orders才触发
        if old_order_count >= min_orders:
            # 之前已经出单了，只更新订单数，不重复触发
            self.video_crud.update_order_count(video_id, new_order_count)
            msg = f"视频 {video_id} 之前已出单({old_order_count}单)，仅更新订单数为{new_order_count}，不重复触发"
            logger.info(msg)
            self._record_trigger("C", dedup_key, video_id, "跳过", msg)
            return {"success": True, "skipped": True, "message": msg}

        if new_order_count < min_orders:
            # 还没出单，只更新订单数
            self.video_crud.update_order_count(video_id, new_order_count)
            msg = f"视频 {video_id} 订单数从{old_order_count}变为{new_order_count}，未达到出单阈值({min_orders})"
            logger.info(msg)
            return {"success": True, "triggered": False, "message": msg}

        # === 出单了！从0变到≥1 ===
        # 1. 更新订单数
        self.video_crud.update_order_count(video_id, new_order_count)

        # 2. 标记为出单素材
        self.video_crud.mark_as_order_material(video_id)

        # 3. 创建AI钩子精剪任务（检查是否已创建）
        product_id = video["product_id"]
        product = self.product_crud.get_by_id(product_id)

        # 检查是否已经有AI精剪任务（双重幂等保护）
        existing_task = self.task_crud.exists_by_type_and_target(
            task_type=TASK_TYPE["AI_HOOK_EDIT"],
            video_id=video_id,
        )

        if existing_task:
            msg = f"视频 {video_id} 已存在AI精剪任务，不重复创建"
            logger.info(msg)
            self._record_trigger("C", dedup_key, video_id, "跳过", msg)
            return {"success": True, "skipped": True, "message": msg}

        task_id = self._generate_task_id("AI")
        self.task_crud.create(
            task_id=task_id,
            task_type=TASK_TYPE["AI_HOOK_EDIT"],
            trigger_source="触发点C-出单触发",
            product_id=product_id,
            video_id=video_id,
            owner=product.get("owner", "") if product else "",
            priority=TASK_PRIORITY["URGENT"],
            trigger_reason=f"视频 {video_id} 出单！订单数从{old_order_count}变为{new_order_count}，请进行AI钩子重新剪辑以提升转化率",
            need_confirm=0,
        )

        # 4. 标记AI精剪任务已创建
        self.video_crud.mark_ai_edit_task_created(video_id)

        # 5. 更新商品状态到"出单"
        if product and product["status"] not in [
            ProductStateMachine.ORDERED,
            ProductStateMachine.AI_HOOK_EDITING,
            ProductStateMachine.SCALING,
            ProductStateMachine.HUNDRED_ORDERS,
            ProductStateMachine.THOUSAND_ORDERS,
        ]:
            self.product_crud.update_status(product_id, ProductStateMachine.ORDERED)

        # 6. 增加商品累计订单
        self.product_crud.add_orders(product_id, new_order_count - old_order_count)

        msg = f"视频 {video_id} 出单！从{old_order_count}单变为{new_order_count}单，已标记出单素材并创建AI精剪任务: {task_id}"
        logger.info(msg)
        self._record_trigger("C", dedup_key, video_id, "成功", msg)
        self._record_action("order_detected", "video", video_id, msg)

        return {
            "success": True,
            "triggered": True,
            "message": msg,
            "task_id": task_id,
            "old_order_count": old_order_count,
            "new_order_count": new_order_count,
        }

    # ============================================
    # 触发点D：放量分级（百单/千单）
    # ============================================
    def trigger_d_scaling_tier(self, product_id: str) -> Dict[str, Any]:
        """
        触发点D：放量分级

        规则：
        - 商品累计订单达到百单阈值（默认100）→ 切换"百单"阶段+创建放量任务
        - 商品累计订单达到千单阈值（默认1000）→ 切换"千单"阶段+创建放量+复盘任务

        Args:
            product_id: 商品ID

        Returns:
            执行结果字典
        """
        logger.info(f"[触发点D] 放量分级触发 | product_id={product_id}")

        # 查询商品
        product = self.product_crud.get_by_id(product_id)
        if not product:
            msg = f"商品不存在: {product_id}"
            logger.error(msg)
            return {"success": False, "message": msg}

        total_orders = product["total_orders"]
        hundred_threshold = self.config.get("thresholds.hundred_orders", 100)
        thousand_threshold = self.config.get("thresholds.thousand_orders", 1000)

        current_stage = product.get("stage", "")
        triggered_tier = None
        task_ids = []

        # 判断千单（先判断高等级，因为千单也满足百单条件）
        if total_orders >= thousand_threshold and current_stage != "千单阶段":
            triggered_tier = "千单"
            dedup_key = f"trigger:D:{product_id}:thousand_orders"

            if not self._check_idempotent(dedup_key):
                # 更新商品阶段和状态
                self.product_crud.update_stage(product_id, "千单阶段")
                self.product_crud.update_status(product_id, ProductStateMachine.THOUSAND_ORDERS)

                # 创建千单放量任务
                task_id = self._generate_task_id("SCALE")
                self.task_crud.create(
                    task_id=task_id,
                    task_type=TASK_TYPE["SCALING"],
                    trigger_source="触发点D-千单放量",
                    product_id=product_id,
                    owner=product.get("owner", ""),
                    priority=TASK_PRIORITY["URGENT"],
                    trigger_reason=f"商品 {product_id}({product['name']}) 累计订单达到{total_orders}，超过千单阈值{thousand_threshold}，请进行千单级放量操作",
                    need_confirm=1,  # 放量是高风险动作，需要人工确认
                )
                task_ids.append(task_id)

                # 创建复盘任务
                review_task_id = self._generate_task_id("REV")
                self.task_crud.create(
                    task_id=review_task_id,
                    task_type=TASK_TYPE["DAILY_REVIEW"],
                    trigger_source="触发点D-千单复盘",
                    product_id=product_id,
                    owner=product.get("owner", ""),
                    priority=TASK_PRIORITY["HIGH"],
                    trigger_reason=f"商品 {product_id} 进入千单阶段，请进行数据复盘并制定后续策略",
                    need_confirm=0,
                )
                task_ids.append(review_task_id)

                msg = f"商品 {product_id} 累计订单{total_orders}，达到千单阈值，已进入千单阶段，创建任务: {', '.join(task_ids)}"
                self._record_trigger("D", dedup_key, product_id, "成功", msg)
                self._record_action("thousand_orders_tier", "product", product_id, msg)

                return {
                    "success": True,
                    "triggered": True,
                    "tier": "千单",
                    "message": msg,
                    "task_ids": task_ids,
                    "total_orders": total_orders,
                }

        # 判断百单
        elif total_orders >= hundred_threshold and current_stage not in ["百单阶段", "千单阶段"]:
            triggered_tier = "百单"
            dedup_key = f"trigger:D:{product_id}:hundred_orders"

            if not self._check_idempotent(dedup_key):
                # 更新商品阶段和状态
                self.product_crud.update_stage(product_id, "百单阶段")
                self.product_crud.update_status(product_id, ProductStateMachine.HUNDRED_ORDERS)

                # 创建百单放量任务
                task_id = self._generate_task_id("SCALE")
                self.task_crud.create(
                    task_id=task_id,
                    task_type=TASK_TYPE["SCALING"],
                    trigger_source="触发点D-百单放量",
                    product_id=product_id,
                    owner=product.get("owner", ""),
                    priority=TASK_PRIORITY["HIGH"],
                    trigger_reason=f"商品 {product_id}({product['name']}) 累计订单达到{total_orders}，超过百单阈值{hundred_threshold}，请进行百单级放量操作",
                    need_confirm=1,  # 放量需要人工确认
                )
                task_ids.append(task_id)

                msg = f"商品 {product_id} 累计订单{total_orders}，达到百单阈值，已进入百单阶段，创建任务: {task_id}"
                self._record_trigger("D", dedup_key, product_id, "成功", msg)
                self._record_action("hundred_orders_tier", "product", product_id, msg)

                return {
                    "success": True,
                    "triggered": True,
                    "tier": "百单",
                    "message": msg,
                    "task_ids": task_ids,
                    "total_orders": total_orders,
                }

        # 未触发：按实际情况返回准确原因（避免误报"未达到阈值"）
        if total_orders >= thousand_threshold and current_stage == "千单阶段":
            msg = f"商品 {product_id} 累计订单{total_orders}，已达千单阈值{thousand_threshold}，已处于千单阶段，不重复触发"
        elif total_orders >= hundred_threshold and current_stage in ["百单阶段", "千单阶段"]:
            msg = f"商品 {product_id} 累计订单{total_orders}，已达百单阈值{hundred_threshold}，已处于{current_stage}，不重复触发"
        elif triggered_tier:
            msg = f"商品 {product_id} 累计订单{total_orders}，{triggered_tier}放量已触发过（幂等跳过），不重复处理"
        else:
            msg = f"商品 {product_id} 累计订单{total_orders}，未达到百单({hundred_threshold})/千单({thousand_threshold})阈值"
        logger.info(msg)
        return {
            "success": True,
            "triggered": False,
            "message": msg,
            "total_orders": total_orders,
        }

    # ============================================
    # 触发点E：无效素材停测
    # ============================================
    def trigger_e_stop_test_check(self, campaign_id: str = None) -> List[Dict[str, Any]]:
        """
        触发点E：无效素材停测检查

        规则（可配置，满足任一即停测）：
        - 消耗≥X元 且 订单=0（默认X=300）
        - 测试时长≥Y小时 且 订单=0（默认Y=72）

        Args:
            campaign_id: 指定检查某个投流计划，None则检查所有投流中的计划

        Returns:
            检查结果列表
        """
        logger.info(f"[触发点E] 无效素材停测检查 | campaign_id={campaign_id or '全部投流中计划'}")

        # 获取要检查的投流计划
        if campaign_id:
            campaigns = [self.campaign_crud.get_by_id(campaign_id)]
            campaigns = [c for c in campaigns if c]
        else:
            campaigns = self.campaign_crud.get_running_campaigns()

        results = []
        now = datetime.now()

        # 读取停测规则配置
        by_cost_enabled = self.config.get("stop_test_rules.by_cost.enabled", True)
        max_cost = self.config.get("stop_test_rules.by_cost.max_cost", 300)
        min_orders_cost = self.config.get("stop_test_rules.by_cost.min_orders", 0)

        by_duration_enabled = self.config.get("stop_test_rules.by_duration.enabled", True)
        max_hours = self.config.get("stop_test_rules.by_duration.max_hours", 72)
        min_orders_duration = self.config.get("stop_test_rules.by_duration.min_orders", 0)

        for campaign in campaigns:
            cid = campaign["campaign_id"]
            video_id = campaign["video_id"]
            product_id = campaign["product_id"]
            cost = campaign.get("cost", 0)
            order_count = campaign.get("order_count", 0)
            start_time_str = campaign.get("start_time", "")

            # 幂等检查
            dedup_key = f"trigger:E:{cid}:stop_test"
            if self._check_idempotent(dedup_key):
                results.append({
                    "campaign_id": cid,
                    "video_id": video_id,
                    "triggered": False,
                    "skipped": True,
                    "message": "重复触发，已跳过",
                })
                continue

            hit_rules = []

            # 规则1：消耗达标且无订单
            if by_cost_enabled and cost >= max_cost and order_count <= min_orders_cost:
                hit_rules.append(f"消耗{cost}元≥阈值{max_cost}元且订单{order_count}={min_orders_cost}")

            # 规则2：测试时长达标且无订单
            if by_duration_enabled and start_time_str:
                try:
                    start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
                    duration_hours = (now - start_time).total_seconds() / 3600
                    if duration_hours >= max_hours and order_count <= min_orders_duration:
                        hit_rules.append(f"测试时长{duration_hours:.1f}小时≥阈值{max_hours}小时且订单{order_count}={min_orders_duration}")
                except (ValueError, TypeError):
                    pass

            if hit_rules:
                # 命中停测规则 → 创建停测/复盘任务
                product = self.product_crud.get_by_id(product_id)
                task_id = self._generate_task_id("STOP")
                self.task_crud.create(
                    task_id=task_id,
                    task_type=TASK_TYPE["STOP_TEST"],
                    trigger_source="触发点E-无效素材停测",
                    product_id=product_id,
                    video_id=video_id,
                    campaign_id=cid,
                    owner=product.get("owner", "") if product else "",
                    priority=TASK_PRIORITY["HIGH"],
                    trigger_reason=f"投流计划 {cid} 命中停测规则: {'; '.join(hit_rules)}。视频{video_id}，消耗{cost}元，订单{order_count}单",
                    need_confirm=1,  # 停测是高风险动作，需要人工确认
                )

                # 标记投流计划为待停测
                self.campaign_crud.update_status(cid, "已暂停")
                self.campaign_crud.mark_abnormal(cid, "命中停测规则")

                msg = f"投流计划 {cid} 命中停测规则: {'; '.join(hit_rules)}，已创建停测任务: {task_id}"
                logger.warning(msg)
                self._record_trigger("E", dedup_key, cid, "成功", msg)
                self._record_action("stop_test", "campaign", cid, msg)

                results.append({
                    "campaign_id": cid,
                    "video_id": video_id,
                    "product_id": product_id,
                    "triggered": True,
                    "hit_rules": hit_rules,
                    "task_id": task_id,
                    "message": msg,
                })
            else:
                results.append({
                    "campaign_id": cid,
                    "video_id": video_id,
                    "triggered": False,
                    "message": f"未命中停测规则（消耗{cost}元，订单{order_count}单）",
                })

        return results

    # ============================================
    # 触发点F：日/批次复盘
    # ============================================
    def trigger_f_daily_review(self) -> Dict[str, Any]:
        """
        触发点F：日/批次复盘

        汇总数据，输出结构化复盘结果：
        - 哪些商品继续测试（有出单、ROI达标）
        - 哪些视频进入AI精剪（刚出单的）
        - 哪些商品进入放量（百单/千单）
        - 哪些需停测/重新选品（消耗高无出单）

        Returns:
            结构化复盘结果
        """
        logger.info("[触发点F] 日/批次复盘开始")

        # 幂等检查（每天只复盘一次）
        today = datetime.now().strftime("%Y-%m-%d")
        dedup_key = f"trigger:F:review:{today}"
        if self._check_idempotent(dedup_key):
            return {"success": False, "skipped": True, "message": f"今日({today})已复盘，跳过"}

        # ===== 1. 汇总数据 =====
        all_products = self.product_crud.get_all(limit=1000)
        all_videos = self.db.execute_query("SELECT * FROM videos")
        all_campaigns = self.campaign_crud.get_running_campaigns()
        pending_tasks = self.task_crud.get_by_status("待处理")

        # 继续测试的商品：有出单素材且ROI>0，处于投流测试阶段
        continue_products = []
        for p in all_products:
            if p["status"] in ["投流测试", "出单"] and p["total_orders"] > 0:
                videos = self.video_crud.get_by_product(p["product_id"])
                ordered_videos = [v for v in videos if v["is_order_material"] == 1]
                if ordered_videos:
                    continue_products.append({
                        "product_id": p["product_id"],
                        "name": p["name"],
                        "total_orders": p["total_orders"],
                        "ordered_video_count": len(ordered_videos),
                        "reason": f"有{len(ordered_videos)}条出单素材，累计{p['total_orders']}单，建议继续测试",
                    })

        # 需要AI精剪的视频：出单素材但AI精剪任务未创建/未完成
        ai_edit_videos = []
        for v in all_videos:
            if v["is_order_material"] == 1 and v["ai_edit_task_created"] == 0:
                ai_edit_videos.append({
                    "video_id": v["video_id"],
                    "product_id": v["product_id"],
                    "order_count": v["order_count"],
                    "roi": v["roi"],
                    "reason": f"视频{v['video_id']}已出单({v['order_count']}单)但未创建AI精剪任务",
                })

        # 进入放量的商品：百单/千单阶段
        scaling_products = []
        for p in all_products:
            if p["stage"] in ["百单阶段", "千单阶段"]:
                scaling_products.append({
                    "product_id": p["product_id"],
                    "name": p["name"],
                    "stage": p["stage"],
                    "total_orders": p["total_orders"],
                    "reason": f"商品{p['product_id']}已进入{p['stage']}，累计{p['total_orders']}单，建议放量",
                })

        # 需停测/重新选品的商品/素材（阈值从配置读取，与触发点E保持一致）
        stop_max_cost = self.config.get("stop_test_rules.by_cost.max_cost", 300)
        stop_min_orders = self.config.get("stop_test_rules.by_cost.min_orders", 0)
        stop_test_items = []
        for c in all_campaigns:
            if c["cost"] >= stop_max_cost and c["order_count"] <= stop_min_orders:
                stop_test_items.append({
                    "campaign_id": c["campaign_id"],
                    "video_id": c["video_id"],
                    "product_id": c["product_id"],
                    "cost": c["cost"],
                    "order_count": c["order_count"],
                    "reason": f"投流计划{c['campaign_id']}消耗{c['cost']}元无出单，建议停测",
                })

        # ===== 2. 生成复盘结论 =====
        review_conclusion = (
            f"本次复盘共检查{len(all_products)}个商品、{len(all_videos)}条视频、"
            f"{len(all_campaigns)}个投流计划。"
            f"继续测试{len(continue_products)}个商品，"
            f"需AI精剪{len(ai_edit_videos)}条视频，"
            f"进入放量{len(scaling_products)}个商品，"
            f"建议停测{len(stop_test_items)}个素材。"
        )

        # 下一步动作
        next_actions = []
        if continue_products:
            next_actions.append(f"继续测试{len(continue_products)}个有出单的商品")
        if ai_edit_videos:
            next_actions.append(f"为{len(ai_edit_videos)}条出单视频创建AI精剪任务")
        if scaling_products:
            next_actions.append(f"对{len(scaling_products)}个百单/千单商品执行放量")
        if stop_test_items:
            next_actions.append(f"停测{len(stop_test_items)}个无效素材并重新选品")

        # ===== 3. 创建复盘任务 =====
        task_id = self._generate_task_id("REV")
        self.task_crud.create(
            task_id=task_id,
            task_type=TASK_TYPE["DAILY_REVIEW"],
            trigger_source="触发点F-日/批次复盘",
            priority=TASK_PRIORITY["HIGH"],
            trigger_reason=f"日/批次自动复盘 - {today}",
            need_confirm=0,
        )
        # 写回复盘结论
        self.task_crud.write_review(task_id, review_conclusion, "; ".join(next_actions))

        # ===== 4. 组装结果 =====
        result = {
            "success": True,
            "review_date": today,
            "task_id": task_id,
            "summary": {
                "total_products": len(all_products),
                "total_videos": len(all_videos),
                "total_campaigns": len(all_campaigns),
                "pending_tasks": len(pending_tasks),
            },
            "continue_testing": continue_products,
            "need_ai_edit": ai_edit_videos,
            "scaling_products": scaling_products,
            "stop_test_items": stop_test_items,
            "review_conclusion": review_conclusion,
            "next_actions": next_actions,
        }

        msg = f"复盘完成: {review_conclusion}"
        logger.info(msg)
        self._record_trigger("F", dedup_key, "", "成功", msg)
        self._record_action("daily_review", "task", task_id, msg)

        return result

    # ============================================
    # 全流程运行（用于演示和测试）
    # ============================================
    def run_full_workflow_demo(self) -> Dict[str, Any]:
        """
        运行全流程演示（从商品确认到复盘）

        用于演示和测试，按顺序触发所有触发点
        """
        logger.info("========== 全流程演示开始 ==========")
        results = {}

        # 用测试题中的数据验证3类结果
        # 1. 出单触发：V002(1单)
        results["order_trigger"] = self.trigger_c_order_detected("V002", 1)

        # 2. 百单/千单：P003(105单)、P004(1008单)
        results["hundred_tier"] = self.trigger_d_scaling_tier("P003")
        results["thousand_tier"] = self.trigger_d_scaling_tier("P004")

        # 3. 无效素材：V006/C006(消耗300, 0单)
        results["stop_test"] = self.trigger_e_stop_test_check("C006")

        # 4. 日复盘
        results["daily_review"] = self.trigger_f_daily_review()

        logger.info("========== 全流程演示完成 ==========")
        return results
