"""
数据库CRUD测试用例

测试内容：
1. 商品表CRUD
2. 视频表CRUD
3. 投流计划表CRUD
4. 任务表CRUD
5. 异常情况测试
"""

import pytest
from src.database.models import TASK_TYPE


class TestProductCRUD:
    """商品表CRUD测试"""

    def test_create_product(self, product_crud):
        """测试创建商品"""
        success = product_crud.create(
            product_id="P999",
            name="测试商品",
            category="测试类目",
            commission_rate=20.0,
            owner="测试员",
        )
        assert success is True

        product = product_crud.get_by_id("P999")
        assert product is not None
        assert product["name"] == "测试商品"
        assert product["commission_rate"] == 20.0

    def test_get_product_by_id(self, product_crud):
        """测试按ID查询商品（样例数据P001）"""
        product = product_crud.get_by_id("P001")
        assert product is not None
        assert product["product_id"] == "P001"
        assert product["name"] == "保湿口红"

    def test_get_nonexistent_product(self, product_crud):
        """测试查询不存在的商品"""
        product = product_crud.get_by_id("P9999")
        assert product is None

    def test_update_product_status(self, product_crud):
        """测试更新商品状态"""
        success = product_crud.update_status("P001", "已确认")
        assert success is True

        product = product_crud.get_by_id("P001")
        assert product["status"] == "已确认"

    def test_update_product_stage(self, product_crud):
        """测试更新商品阶段"""
        success = product_crud.update_stage("P001", "百单阶段")
        assert success is True

        product = product_crud.get_by_id("P001")
        assert product["stage"] == "百单阶段"

    def test_update_commission(self, product_crud):
        """测试更新佣金"""
        success = product_crud.update_commission("P001", 35.0)
        assert success is True

        product = product_crud.get_by_id("P001")
        assert product["commission_rate"] == 35.0

    def test_add_orders(self, product_crud):
        """测试增加累计订单"""
        old = product_crud.get_by_id("P001")
        old_orders = old["total_orders"]

        success = product_crud.add_orders("P001", 5)
        assert success is True

        new = product_crud.get_by_id("P001")
        assert new["total_orders"] == old_orders + 5

    def test_get_by_status(self, product_crud):
        """测试按状态查询"""
        products = product_crud.get_by_status("投流测试")
        assert len(products) > 0
        for p in products:
            assert p["status"] == "投流测试"

    def test_get_by_stage(self, product_crud):
        """测试按阶段查询"""
        products = product_crud.get_by_stage("百单阶段")
        assert len(products) > 0
        for p in products:
            assert p["stage"] == "百单阶段"

    def test_count(self, product_crud):
        """测试统计数量"""
        count = product_crud.count()
        assert count >= 5  # 样例数据有5个

    def test_delete_product(self, product_crud):
        """测试删除商品"""
        product_crud.create("P_DEL", "待删除商品")
        success = product_crud.delete("P_DEL")
        assert success is True

        product = product_crud.get_by_id("P_DEL")
        assert product is None


class TestVideoCRUD:
    """视频表CRUD测试"""

    def test_create_video(self, video_crud):
        """测试创建视频"""
        success = video_crud.create(
            video_id="V999",
            product_id="P001",
            source="测试来源",
            file_path="test.mp4",
        )
        assert success is True

        video = video_crud.get_by_id("V999")
        assert video is not None
        assert video["product_id"] == "P001"

    def test_get_video_by_id(self, video_crud):
        """测试按ID查询视频"""
        video = video_crud.get_by_id("V001")
        assert video is not None
        assert video["video_id"] == "V001"
        assert video["product_id"] == "P001"

    def test_get_videos_by_product(self, video_crud):
        """测试按商品查询视频"""
        videos = video_crud.get_by_product("P001")
        assert len(videos) == 2  # P001有V001和V002
        for v in videos:
            assert v["product_id"] == "P001"

    def test_update_dedup_status(self, video_crud):
        """测试更新去重状态"""
        success = video_crud.update_dedup_status("V001", "去重通过")
        assert success is True

        video = video_crud.get_by_id("V001")
        assert video["dedup_status"] == "去重通过"

    def test_update_order_count(self, video_crud):
        """测试更新订单数（返回旧记录）"""
        old = video_crud.update_order_count("V001", 5)
        assert old is not None
        assert old["order_count"] == 0  # 原来V001是0单

        new = video_crud.get_by_id("V001")
        assert new["order_count"] == 5

    def test_mark_as_order_material(self, video_crud):
        """测试标记出单素材"""
        success = video_crud.mark_as_order_material("V001")
        assert success is True

        video = video_crud.get_by_id("V001")
        assert video["is_order_material"] == 1

    def test_get_ordered_videos(self, video_crud):
        """测试查询出单视频"""
        videos = video_crud.get_ordered_videos()
        assert len(videos) > 0
        for v in videos:
            assert v["is_order_material"] == 1

    def test_get_passed_dedup_count(self, video_crud):
        """测试查询去重通过数量"""
        count = video_crud.get_passed_dedup_count("P001")
        assert count == 2  # P001的V001和V002都去重通过

    def test_get_frontend_published_count(self, video_crud):
        """测试查询前端发布数量"""
        count = video_crud.get_frontend_published_count("P001")
        assert count == 1  # V001已前端发布


class TestCampaignCRUD:
    """投流计划表CRUD测试"""

    def test_create_campaign(self, campaign_crud):
        """测试创建投流计划"""
        success = campaign_crud.create(
            campaign_id="C999",
            product_id="P001",
            video_id="V001",
            status="已创建",
        )
        assert success is True

        campaign = campaign_crud.get_by_id("C999")
        assert campaign is not None

    def test_get_by_product(self, campaign_crud):
        """测试按商品查询投流计划"""
        campaigns = campaign_crud.get_by_product("P001")
        assert len(campaigns) == 2  # C001和C002

    def test_get_by_video(self, campaign_crud):
        """测试按视频查询投流计划"""
        campaigns = campaign_crud.get_by_video("V001")
        assert len(campaigns) == 1

    def test_backfill_data(self, campaign_crud):
        """测试回填数据"""
        success = campaign_crud.backfill_data("C001", 100.0, 3, 1.5)
        assert success is True

        campaign = campaign_crud.get_by_id("C001")
        assert campaign["cost"] == 100.0
        assert campaign["order_count"] == 3
        assert campaign["roi"] == 1.5

    def test_update_status(self, campaign_crud):
        """测试更新状态"""
        success = campaign_crud.update_status("C001", "已暂停")
        assert success is True

        campaign = campaign_crud.get_by_id("C001")
        assert campaign["status"] == "已暂停"

    def test_get_running_campaigns(self, campaign_crud):
        """测试获取投流中的计划"""
        campaigns = campaign_crud.get_running_campaigns()
        assert len(campaigns) > 0
        for c in campaigns:
            assert c["status"] == "投流中"


class TestTaskCRUD:
    """任务表CRUD测试"""

    def test_create_task(self, task_crud):
        """测试创建任务"""
        success = task_crud.create(
            task_id="T999",
            task_type="素材搜集",
            trigger_source="测试",
            product_id="P001",
            owner="测试员",
            priority="高",
            trigger_reason="测试任务",
        )
        assert success is True

        task = task_crud.get_by_id("T999")
        assert task is not None
        assert task["task_type"] == "素材搜集"

    def test_get_by_status(self, task_crud):
        """测试按状态查询任务"""
        task_crud.create("T_STATUS", "测试任务")  # create默认状态就是"待处理"
        tasks = task_crud.get_by_status("待处理")
        assert len(tasks) > 0

    def test_get_pending_tasks(self, task_crud):
        """测试获取待处理任务"""
        tasks = task_crud.get_pending_tasks()
        for t in tasks:
            assert t["status"] == "待处理"

    def test_update_status(self, task_crud):
        """测试更新任务状态"""
        task_crud.create("T_UPD", "测试任务")
        success = task_crud.update_status("T_UPD", "处理中")
        assert success is True

        task = task_crud.get_by_id("T_UPD")
        assert task["status"] == "处理中"

    def test_write_review(self, task_crud):
        """测试写回复盘结论"""
        task_crud.create("T_REV", "日/批次复盘")
        success = task_crud.write_review("T_REV", "测试复盘结论", "测试下一步")
        assert success is True

        task = task_crud.get_by_id("T_REV")
        assert task["review_conclusion"] == "测试复盘结论"
        assert task["next_action"] == "测试下一步"
        assert task["status"] == "已完成"

    def test_exists_by_type_and_target(self, task_crud):
        """测试检查任务是否已存在（防重复）"""
        task_crud.create("T_DUP", "AI钩子精剪", video_id="V001")
        exists = task_crud.exists_by_type_and_target("AI钩子精剪", video_id="V001")
        assert exists is True

        not_exists = task_crud.exists_by_type_and_target("AI钩子精剪", video_id="V999")
        assert not_exists is False
