"""
数据库模块 — 负责数据库连接、建表、CRUD操作
"""
from .db import Database, get_db
from .models import create_tables, insert_sample_data
from .crud import ProductCRUD, VideoCRUD, CampaignCRUD, TaskCRUD

__all__ = [
    "Database",
    "get_db",
    "create_tables",
    "insert_sample_data",
    "ProductCRUD",
    "VideoCRUD",
    "CampaignCRUD",
    "TaskCRUD",
]
