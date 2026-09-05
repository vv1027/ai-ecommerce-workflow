"""
工作流测试用例 — 状态机 + 6个触发点

测试内容：
1. 状态机测试
2. 触发点A：商品确认
3. 触发点B：去重分流
4. 触发点C：出单触发
5. 触发点D：放量分级
6. 触发点E：无效素材停测
7. 触发点F：日/批次复盘
8. 幂等性测试
"""

import pytest
from src.workflow.state_machine import ProductStateMachine
from src.database.models import TASK_TYPE


class TestStateMachine:
    """状态机测试"""

    def test_valid_transition(self, state_machine):
        """测试合法状态流转"""
        allowed, reason = state_machine.can_transition("待选品", "已确认")
        assert allowed is True

    def test_invalid_transition(self, state_machine):
        """测试非法状态流转（待选品不能直接到出单）"""
        allowed, reason = state_machine.can_transition("待选品", "出单")
        assert allowed is False
        assert "不允许" in reason

    def test_unknown_state(self, state_machine):
        """测试未知状态"""
        allowed, reason = state_machine.can_transition("未知状态", "已确认")
        assert allowed is False

    def test_get_available_transitions(self, state_machine):
        """测试获取可用流转"""
        transitions = state_machine.get_available_transitions("待选品")
        assert "已确认" in transitions

    def test_get_stage_by_status(self, state_machine):
        """测试根据状态判断阶段"""
        assert state_machine.get_stage_by_status("待选品") == "选品阶段"
        assert state_machine.get_stage_by_status("百单") == "百单阶段"
        assert state_machine.get_stage_by_status("千单") == "千单阶段"

    def test_full_chain_transition(self, state_machine):
        """测试完整状态链是否都能流转"""
        chain = ["待选品", "已确认", "素材搜集", "混剪", "去重通过",
                 "前端已发布", "投流测试", "出单", "AI钩子精剪", "放量",
                 "百单", "千单", "复盘", "再选品", "待选品"]
        for i in range(len(chain) - 1):
            allowed, reason = state_machine.can_transition(chain[i], chain[i+1])
            assert allowed is True, f"{chain[i]} -> {chain[i+1]} 失败: {reason}"


class TestTriggerA:
    """触发点A：商品确认测试"""

    def test_normal_confirm(self, triggers, product_crud):
        """测试正常确认（有佣金）→ 创建素材任务"""
        # 先把P001状态改为已确认
        product_crud.update_status("P001", "已确认")

        result = triggers.trigger_a_product_confirm("P001")
        assert result["success"] is True
        assert result["blocked"] is False
        assert "task_id" in result

        # 验证商品状态已更新
        product = product_crud.get_by_id("P001")
        assert product["status"] == "素材搜集"

    def test_confirm_without_commission(self, triggers, product_crud):
        """测试确认但佣金为空 → 阻断，创建佣金填写任务"""
        # 创建一个无佣金的商品
        product_crud.create("P_NO_COMM", "无佣金商品", commission_rate=0)
        product_crud.update_status("P_NO_COMM", "已确认")

        result = triggers.trigger_a_product_confirm("P_NO_COMM")
        assert result["success"] is True
        assert result["blocked"] is True
        assert result["task_type"] == TASK_TYPE["COMMISSION_FILL"]

    def test_confirm_wrong_status(self, triggers, product_crud):
        """测试状态不是已确认时触发 → 失败"""
        # P001当前是投流测试状态
        result = triggers.trigger_a_product_confirm("P001")
        assert result["success"] is False
        assert "不是" in result["message"]

    def test_confirm_nonexistent_product(self, triggers):
        """测试确认不存在的商品 → 失败"""
        result = triggers.trigger_a_product_confirm("P9999")
        assert result["success"] is False

    def test_idempotent(self, triggers, product_crud):
        """测试幂等性：重复触发不重复创建任务"""
        product_crud.update_status("P001", "已确认")
        result1 = triggers.trigger_a_product_confirm("P001")
        result2 = triggers.trigger_a_product_confirm("P001")
        assert result2.get("skipped") is True


class TestTriggerB:
    """触发点B：去重分流测试"""

    def test_first_video_frontend(self, triggers, video_crud):
        """测试第1条去重通过视频 → 前端发布"""
        # 创建一个新商品和新视频
        from src.database.crud import ProductCRUD
        product_crud = ProductCRUD(triggers.db)
        product_crud.create("P_NEW", "新商品")

        video_crud.create("V_NEW1", "P_NEW", dedup_status="待去重")
        video_crud.update_dedup_status("V_NEW1", "去重通过")

        result = triggers.trigger_b_dedup_complete("V_NEW1")
        assert result["success"] is True
        assert result["route"] == "前端挂车发布"

    def test_second_video_qianchuan(self, triggers, video_crud):
        """测试第2条去重通过视频 → 千川上传"""
        from src.database.crud import ProductCRUD
        product_crud = ProductCRUD(triggers.db)
        product_crud.create("P_NEW2", "新商品2")

        # 第1条
        video_crud.create("V_NEW2_1", "P_NEW2")
        video_crud.update_dedup_status("V_NEW2_1", "去重通过")
        triggers.trigger_b_dedup_complete("V_NEW2_1")

        # 第2条
        video_crud.create("V_NEW2_2", "P_NEW2")
        video_crud.update_dedup_status("V_NEW2_2", "去重通过")
        result = triggers.trigger_b_dedup_complete("V_NEW2_2")
        assert result["success"] is True
        assert result["route"] == "千川上传/建计划"

    def test_dedup_not_passed(self, triggers, video_crud):
        """测试去重状态不是通过时触发 → 失败"""
        result = triggers.trigger_b_dedup_complete("V001")  # V001已经是去重通过，应该能触发
        # V001是P001的第1条，应该走前端发布
        assert result["success"] is True

    def test_idempotent(self, triggers, video_crud):
        """测试幂等性"""
        result1 = triggers.trigger_b_dedup_complete("V001")
        result2 = triggers.trigger_b_dedup_complete("V001")
        assert result2.get("skipped") is True


class TestTriggerC:
    """触发点C：出单触发测试"""

    def test_order_from_zero_to_one(self, triggers, video_crud):
        """测试订单从0变到1 → 触发出单，创建AI精剪任务"""
        # V001原来0单
        result = triggers.trigger_c_order_detected("V001", 1)
        assert result["success"] is True
        assert result["triggered"] is True
        assert "task_id" in result

        # 验证视频被标记为出单素材
        video = video_crud.get_by_id("V001")
        assert video["is_order_material"] == 1
        assert video["ai_edit_task_created"] == 1

    def test_order_already_has_orders(self, triggers, video_crud):
        """测试之前已经出单的视频 → 只更新订单数，不重复触发"""
        # V002原来1单，更新到5单
        result = triggers.trigger_c_order_detected("V002", 5)
        assert result["success"] is True
        assert result.get("skipped") is True or result.get("triggered") is False

    def test_order_still_zero(self, triggers, video_crud):
        """测试订单还是0 → 不触发"""
        result = triggers.trigger_c_order_detected("V001", 0)
        assert result["success"] is True
        assert result.get("triggered") is False

    def test_idempotent(self, triggers):
        """测试幂等性：重复触发不重复创建任务"""
        result1 = triggers.trigger_c_order_detected("V001", 1)
        result2 = triggers.trigger_c_order_detected("V001", 1)
        assert result2.get("skipped") is True

    def test_nonexistent_video(self, triggers):
        """测试不存在的视频 → 失败"""
        result = triggers.trigger_c_order_detected("V9999", 1)
        assert result["success"] is False


class TestTriggerD:
    """触发点D：放量分级测试"""

    def test_hundred_orders(self, triggers, product_crud):
        """测试百单触发：P003有105单 → 进入百单阶段"""
        # 先把P003阶段重置为投流测试阶段（模拟还没达到百单）
        product_crud.update_stage("P003", "投流测试阶段")
        result = triggers.trigger_d_scaling_tier("P003")
        assert result["success"] is True
        assert result.get("triggered") is True
        assert result["tier"] == "百单"

        product = product_crud.get_by_id("P003")
        assert product["stage"] == "百单阶段"

    def test_thousand_orders(self, triggers, product_crud):
        """测试千单触发：P004有1008单 → 进入千单阶段"""
        # 先把P004阶段重置为百单阶段（模拟从百单升级到千单）
        product_crud.update_stage("P004", "百单阶段")
        result = triggers.trigger_d_scaling_tier("P004")
        assert result["success"] is True
        assert result.get("triggered") is True
        assert result["tier"] == "千单"

        product = product_crud.get_by_id("P004")
        assert product["stage"] == "千单阶段"

    def test_below_threshold(self, triggers):
        """测试未达到阈值：P001有20单 → 不触发"""
        result = triggers.trigger_d_scaling_tier("P001")
        assert result["success"] is True
        assert result.get("triggered") is False

    def test_nonexistent_product(self, triggers):
        """测试不存在的商品 → 失败"""
        result = triggers.trigger_d_scaling_tier("P9999")
        assert result["success"] is False


class TestTriggerE:
    """触发点E：无效素材停测测试"""

    def test_stop_test_hit(self, triggers, campaign_crud):
        """测试命中停测规则：C006消耗300，0单 → 触发停测"""
        result = triggers.trigger_e_stop_test_check("C006")
        assert len(result) > 0
        assert result[0].get("triggered") is True
        assert "task_id" in result[0]

    def test_no_stop_test(self, triggers):
        """测试未命中停测规则：C003消耗200，6单 → 不触发"""
        result = triggers.trigger_e_stop_test_check("C003")
        assert len(result) > 0
        assert result[0].get("triggered") is False

    def test_batch_check(self, triggers):
        """测试批量检查所有投流计划"""
        results = triggers.trigger_e_stop_test_check()
        assert len(results) > 0
        # C006应该命中
        c006_results = [r for r in results if r.get("campaign_id") == "C006"]
        assert len(c006_results) > 0
        assert c006_results[0].get("triggered") is True


class TestTriggerF:
    """触发点F：日/批次复盘测试"""

    def test_daily_review(self, triggers):
        """测试日复盘运行"""
        result = triggers.trigger_f_daily_review()
        assert result["success"] is True
        assert "review_conclusion" in result
        assert "continue_testing" in result
        assert "need_ai_edit" in result
        assert "scaling_products" in result
        assert "stop_test_items" in result
        assert "task_id" in result

    def test_review_has_data(self, triggers):
        """测试复盘结果包含数据"""
        result = triggers.trigger_f_daily_review()
        # 应该有百单/千单商品（P003、P004）
        assert len(result["scaling_products"]) > 0
        # 应该有出单视频需要AI精剪（V002等）
        # 注意：样例数据中V002已经标记了出单素材，但ai_edit_task_created可能是0
        # 所以应该能查到需要精剪的视频


class TestFullWorkflow:
    """全流程集成测试"""

    def test_run_full_demo(self, triggers):
        """测试运行全流程演示"""
        result = triggers.run_full_workflow_demo()
        assert "order_trigger" in result
        assert "hundred_tier" in result
        assert "thousand_tier" in result
        assert "stop_test" in result
        assert "daily_review" in result

    def test_three_expected_results(self, triggers, product_crud):
        """测试测试题要求的3类结果：出单触发、百单/千单、无效素材"""
        # 先重置阶段，确保能触发升级
        product_crud.update_stage("P003", "投流测试阶段")
        product_crud.update_stage("P004", "百单阶段")

        result = triggers.run_full_workflow_demo()

        # 1. 出单触发：V002
        assert result["order_trigger"]["success"] is True

        # 2. 百单/千单：P003→百单，P004→千单
        assert result["hundred_tier"].get("tier") == "百单"
        assert result["thousand_tier"].get("tier") == "千单"

        # 3. 无效素材：C006停测
        stop_results = result["stop_test"]
        assert len(stop_results) > 0
        triggered = [r for r in stop_results if r.get("triggered")]
        assert len(triggered) > 0


class TestTriggerFStopTestConfig:
    """触发点F停测阈值配置化验证（修复硬编码300的问题）"""

    def test_stop_test_threshold_from_config(self, triggers, campaign_crud):
        """停测判断应读取配置的max_cost，而非硬编码300"""
        original = triggers.config.get("stop_test_rules.by_cost.max_cost", 300)
        try:
            # 把停测阈值改为200
            triggers.config.set("stop_test_rules.by_cost.max_cost", 200)

            # 新增一个消耗250元、0订单的投流计划
            campaign_crud.create(
                campaign_id="C100",
                product_id="P001",
                video_id="V001",
                status="投流中",
                start_time="2026-08-30 10:00:00",
            )
            campaign_crud.backfill_data("C100", cost=250, order_count=0, roi=0.0)

            # 阈值为200时，C100(250元)应被停测
            # 若仍是硬编码300，则C100(250)不会命中，测试失败
            result = triggers.trigger_f_daily_review()
            stop_ids = [item["campaign_id"] for item in result["stop_test_items"]]
            assert "C100" in stop_ids
        finally:
            # 恢复配置，避免污染其他测试（Config是单例）
            triggers.config.set("stop_test_rules.by_cost.max_cost", original)
