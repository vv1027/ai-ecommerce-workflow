"""
conftest.py — pytest测试配置和共享fixture

术语讲解：
- fixture：测试前的准备工作，比如创建测试数据库、插入测试数据
- conftest.py：pytest的配置文件，里面的fixture所有测试文件都能用
- 临时数据库：测试用的数据库，测试完可以删掉，不影响正式数据
"""

import os
import sys
import pytest
import tempfile

# 把项目根目录加入Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database.db import Database
from src.database.models import create_tables, insert_sample_data
from src.database.crud import (
    ProductCRUD, VideoCRUD, CampaignCRUD, TaskCRUD, TriggerLogCRUD,
)
from src.workflow.state_machine import ProductStateMachine
from src.workflow.triggers import WorkflowTriggers
from src.agent.agent import ReviewAgent
from src.agent.tools import AgentTools
from src.config import get_config


@pytest.fixture
def test_db():
    """
    创建临时测试数据库（每个测试函数独立使用，测试完自动删除）

    使用方法：
        def test_something(test_db):
            # test_db就是一个干净的、有样例数据的数据库
            product = ProductCRUD(test_db).get_by_id("P001")
    """
    # 创建临时文件
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name

    # 初始化数据库
    db = Database(db_path)
    db.connect()
    create_tables(db)
    insert_sample_data(db)

    yield db  # 把数据库交给测试用例

    # 测试完清理
    db.close()
    os.unlink(db_path)


@pytest.fixture
def product_crud(test_db):
    """商品CRUD fixture"""
    return ProductCRUD(test_db)


@pytest.fixture
def video_crud(test_db):
    """视频CRUD fixture"""
    return VideoCRUD(test_db)


@pytest.fixture
def campaign_crud(test_db):
    """投流计划CRUD fixture"""
    return CampaignCRUD(test_db)


@pytest.fixture
def task_crud(test_db):
    """任务CRUD fixture"""
    return TaskCRUD(test_db)


@pytest.fixture
def state_machine():
    """状态机fixture"""
    return ProductStateMachine()


@pytest.fixture
def triggers(test_db):
    """工作流触发器fixture"""
    return WorkflowTriggers(test_db)


@pytest.fixture
def agent_tools(test_db):
    """Agent工具fixture"""
    return AgentTools(test_db)


@pytest.fixture
def agent(test_db):
    """Agent数智员工fixture"""
    return ReviewAgent(test_db)


@pytest.fixture
def config():
    """配置fixture"""
    return get_config()
