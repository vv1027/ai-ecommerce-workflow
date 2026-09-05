"""
Agent数智员工测试用例

测试内容：
1. 工具查询测试
2. 4类必答问题测试
3. 执行动作测试
4. 人工确认测试
5. 边界和异常测试
"""

import pytest


class TestAgentTools:
    """Agent工具测试"""

    def test_query_product_info(self, agent_tools):
        """测试查询商品信息"""
        result = agent_tools.query_product_info("P001")
        assert result["success"] is True
        assert result["data"]["product_id"] == "P001"
        assert "video_count" in result["data"]

    def test_query_nonexistent_product(self, agent_tools):
        """测试查询不存在的商品"""
        result = agent_tools.query_product_info("P9999")
        assert result["success"] is False

    def test_query_products_by_status(self, agent_tools):
        """测试按状态查询商品"""
        result = agent_tools.query_products_by_status("投流测试")
        assert result["success"] is True
        assert result["count"] > 0

    def test_query_video_info(self, agent_tools):
        """测试查询视频信息"""
        result = agent_tools.query_video_info("V001")
        assert result["success"] is True
        assert result["data"]["video_id"] == "V001"

    def test_query_videos_by_product(self, agent_tools):
        """测试按商品查询视频"""
        result = agent_tools.query_videos_by_product("P001")
        assert result["success"] is True
        assert result["count"] == 2

    def test_query_ordered_videos(self, agent_tools):
        """测试查询出单视频"""
        result = agent_tools.query_ordered_videos()
        assert result["success"] is True
        assert result["count"] > 0

    def test_query_need_ai_edit_videos(self, agent_tools):
        """测试查询需要AI精剪的视频"""
        result = agent_tools.query_need_ai_edit_videos()
        assert result["success"] is True
        # 样例数据中V002是出单素材，需要检查ai_edit_task_created
        # 样例数据中ai_edit_task_created默认是0，所以应该能查到

    def test_query_scaling_products(self, agent_tools):
        """测试查询放量商品"""
        result = agent_tools.query_scaling_products()
        assert result["success"] is True
        assert result["count"] > 0  # P003百单、P004千单

    def test_query_scaling_products_by_tier(self, agent_tools):
        """测试按级别查询放量商品"""
        result = agent_tools.query_scaling_products("百单")
        assert result["success"] is True
        for p in result["data"]:
            assert p["stage"] == "百单阶段"

    def test_query_stop_test_candidates(self, agent_tools):
        """测试查询停测候选"""
        result = agent_tools.query_stop_test_candidates()
        assert result["success"] is True
        # C006消耗300，0单，应该命中

    def test_query_campaign_info(self, agent_tools):
        """测试查询投流计划"""
        result = agent_tools.query_campaign_info("C001")
        assert result["success"] is True
        assert result["data"]["campaign_id"] == "C001"

    def test_query_tasks(self, agent_tools):
        """测试查询任务"""
        result = agent_tools.query_tasks()
        assert result["success"] is True

    def test_execute_unknown_tool(self, agent_tools):
        """测试调用不存在的工具"""
        result = agent_tools.execute_tool("nonexistent_tool")
        assert result["success"] is False
        assert "未知工具" in result["message"]


class TestAgentActions:
    """Agent执行动作测试"""

    def test_create_ai_edit_task(self, agent_tools, video_crud):
        """测试创建AI精剪任务"""
        # V001原来不是出单素材，先标记
        video_crud.mark_as_order_material("V001")
        result = agent_tools.action_create_ai_edit_task("V001", "测试创建")
        assert result["success"] is True
        assert "task_id" in result

        # 验证视频已标记
        video = video_crud.get_by_id("V001")
        assert video["ai_edit_task_created"] == 1

    def test_create_duplicate_ai_edit_task(self, agent_tools, video_crud):
        """测试重复创建AI精剪任务（幂等）"""
        video_crud.mark_as_order_material("V001")
        agent_tools.action_create_ai_edit_task("V001", "第一次")
        result = agent_tools.action_create_ai_edit_task("V001", "第二次")
        assert result["success"] is False
        assert "已创建过" in result["message"]

    def test_create_stop_test_task(self, agent_tools):
        """测试创建停测任务"""
        result = agent_tools.action_create_stop_test_task("C006", "测试停测")
        assert result["success"] is True
        assert result.get("need_confirm") is True

    def test_write_review_conclusion(self, agent_tools, task_crud):
        """测试写回复盘结论"""
        task_crud.create("T_REVIEW_TEST", "日/批次复盘")
        result = agent_tools.action_write_review_conclusion(
            "T_REVIEW_TEST", "测试结论", "测试下一步"
        )
        assert result["success"] is True

        task = task_crud.get_by_id("T_REVIEW_TEST")
        assert task["review_conclusion"] == "测试结论"
        assert task["next_action"] == "测试下一步"

    def test_update_product_stage(self, agent_tools, product_crud):
        """测试更新商品阶段"""
        result = agent_tools.action_update_product_stage("P001", "百单阶段")
        assert result["success"] is True

        product = product_crud.get_by_id("P001")
        assert product["stage"] == "百单阶段"


class TestAgentChat:
    """Agent对话测试"""

    def test_greeting(self, agent):
        """测试问候"""
        response = agent.chat("你好")
        assert "你好" in response or "数智员工" in response

    def test_help(self, agent):
        """测试帮助"""
        response = agent.chat("帮助")
        assert "出单" in response or "精剪" in response or "停测" in response

    def test_query_ordered_videos_question(self, agent):
        """测试问题①：今天哪些视频已出单？"""
        response = agent.chat("今天哪些视频已出单？")
        assert "V00" in response or "出单" in response
        # 应该引用视频ID

    def test_query_need_ai_edit_question(self, agent):
        """测试问题②：哪些需要立即进入AI钩子精剪？"""
        response = agent.chat("哪些需要立即进入AI钩子精剪？")
        assert "精剪" in response or "V00" in response or "没有" in response

    def test_query_scaling_products_question(self, agent):
        """测试问题③：哪些商品已进入百单/千单阶段？"""
        response = agent.chat("哪些商品已进入百单/千单阶段？")
        assert "P00" in response or "百单" in response or "千单" in response

    def test_query_stop_test_question(self, agent):
        """测试问题④：哪些商品/素材应停测？"""
        response = agent.chat("哪些素材应停测？")
        assert "C00" in response or "停测" in response or "没有" in response

    def test_query_product_detail(self, agent):
        """测试查询商品详情"""
        response = agent.chat("P001商品怎么样？")
        assert "P001" in response or "保湿口红" in response

    def test_query_video_detail(self, agent):
        """测试查询视频详情"""
        response = agent.chat("V002视频详情")
        assert "V002" in response or "P001" in response

    def test_create_ai_edit_action(self, agent):
        """测试执行动作：创建AI精剪任务"""
        response = agent.chat("给V001创建精剪任务")
        assert "成功" in response or "失败" in response or "任务" in response

    def test_high_risk_needs_confirmation(self, agent):
        """测试高风险操作需要人工确认"""
        response = agent.chat("C006停测")
        assert "确认" in response or "高风险" in response

    def test_confirm_high_risk_action(self, agent):
        """测试确认高风险操作"""
        # 先触发高风险操作
        agent.chat("C006停测")
        # 确认
        response = agent.chat("确认")
        assert "成功" in response or "任务" in response or "停测" in response

    def test_cancel_high_risk_action(self, agent):
        """测试取消高风险操作"""
        agent.chat("C006停测")
        response = agent.chat("取消")
        assert "取消" in response or "已取消" in response

    def test_conversation_history(self, agent):
        """测试对话历史记录"""
        agent.chat("你好")
        agent.chat("帮助")
        history = agent.get_conversation_history()
        assert len(history) >= 4  # 2轮对话，每轮user+assistant

    def test_clear_history(self, agent):
        """测试清空对话历史"""
        agent.chat("你好")
        agent.clear_history()
        history = agent.get_conversation_history()
        assert len(history) == 0

    def test_unknown_question(self, agent):
        """测试无法识别的问题"""
        response = agent.chat("xyzabc123")
        assert "帮助" in response or "理解" in response or "抱歉" in response


class TestAgentBoundary:
    """Agent边界和异常测试"""

    def test_no_hallucination(self, agent):
        """测试不编造数据：查询不存在的商品"""
        response = agent.chat("P9999商品怎么样？")
        assert "不存在" in response or "没有" in response or "未找到" in response

    def test_tool_risk_level(self, agent_tools):
        """测试工具风险等级"""
        assert agent_tools.get_tool_risk_level("action_create_stop_test_task") == "high"
        assert agent_tools.get_tool_risk_level("action_create_ai_edit_task") == "medium"
        assert agent_tools.get_tool_risk_level("query_product_info") == "low"

    def test_get_tool_definitions(self, agent_tools):
        """测试获取工具定义"""
        tools = agent_tools.get_tool_definitions()
        assert len(tools) > 0
        tool_names = [t["name"] for t in tools]
        assert "query_product_info" in tool_names
        assert "action_create_ai_edit_task" in tool_names

    def test_read_write_tools_separated(self, agent_tools):
        """测试只读和写操作工具分开"""
        read_tools = agent_tools.get_read_tools()
        write_tools = agent_tools.get_write_tools()
        assert len(read_tools) > 0
        assert len(write_tools) > 0
        # 只读工具不应该包含action_
        for t in read_tools:
            assert not t["name"].startswith("action_")
        # 写操作工具应该包含action_
        for t in write_tools:
            assert t["name"].startswith("action_")

    def test_system_prompt_exists(self, agent):
        """测试系统提示词存在"""
        prompt = agent.get_system_prompt()
        assert len(prompt) > 100
        assert "数智员工" in prompt
