"""
数据模型模块 — 建表语句、状态常量、样例数据

术语讲解：
- 主键（Primary Key）：每行数据的唯一身份证，不能重复
- 外键（Foreign Key）：引用另一张表的主键，建立表之间的关系
- 索引（Index）：给字段加目录，加快查询速度
- NOT NULL：该字段不能为空
- DEFAULT：字段的默认值
- CHECK：字段值的约束条件
"""

import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# ============================================
# 状态常量定义（用字符串常量，避免拼写错误）
# ============================================

# 商品选品状态
PRODUCT_STATUS = {
    "PENDING": "待选品",
    "CONFIRMED": "已确认",
    "MATERIAL_COLLECTING": "素材搜集",
    "EDITING": "混剪",
    "DEDUP_PASSED": "去重通过",
    "PUBLISHED": "前端已发布",
    "QIANCHUAN_PENDING": "千川待上传",
    "AD_TESTING": "投流测试",
    "ORDERED": "出单",
    "AI_HOOK_EDITING": "AI钩子精剪",
    "SCALING": "放量",
    "HUNDRED_ORDERS": "百单",
    "THOUSAND_ORDERS": "千单",
    "REVIEW": "复盘",
    "RESELECT": "再选品",
    "STOPPED": "已停测",
}

# 视频混剪状态
VIDEO_EDIT_STATUS = {
    "PENDING": "待混剪",
    "EDITING": "混剪中",
    "COMPLETED": "混剪完成",
}

# 视频去重状态
VIDEO_DEDUP_STATUS = {
    "PENDING": "待去重",
    "PROCESSING": "去重中",
    "PASSED": "去重通过",
    "FAILED": "去重失败",
}

# 投流计划状态
CAMPAIGN_STATUS = {
    "PENDING": "待创建",
    "CREATED": "已创建",
    "RUNNING": "投流中",
    "PAUSED": "已暂停",
    "STOPPED": "已停投",
    "COMPLETED": "已完成",
    "ERROR": "异常",
}

# 任务状态
TASK_STATUS = {
    "PENDING": "待处理",
    "IN_PROGRESS": "处理中",
    "COMPLETED": "已完成",
    "CANCELLED": "已取消",
    "BLOCKED": "已阻断",
}

# 任务类型
TASK_TYPE = {
    "MATERIAL_COLLECT": "素材搜集",
    "VIDEO_EDIT": "视频混剪",
    "FRONTEND_PUBLISH": "前端挂车发布",
    "QIANCHUAN_UPLOAD": "千川上传",
    "CAMPAIGN_CREATE": "创建投流计划",
    "AI_HOOK_EDIT": "AI钩子精剪",
    "SCALING": "放量操作",
    "STOP_TEST": "停测/复盘",
    "DAILY_REVIEW": "日/批次复盘",
    "COMMISSION_FILL": "佣金待填写",
    "RESELECT": "重新选品",
}

# 任务优先级
TASK_PRIORITY = {
    "LOW": "低",
    "MEDIUM": "中",
    "HIGH": "高",
    "URGENT": "紧急",
}


# ============================================
# 建表SQL语句
# ============================================

CREATE_TABLES_SQL = [
    # ===== 商品表 =====
    """
    CREATE TABLE IF NOT EXISTS products (
        product_id      TEXT PRIMARY KEY,                          -- 商品ID（主键）
        name            TEXT NOT NULL,                              -- 商品名
        category        TEXT DEFAULT '',                            -- 类目
        commission_rate REAL DEFAULT 0,                             -- 佣金比例（如25表示25%）
        owner           TEXT DEFAULT '',                            -- 负责人
        status          TEXT DEFAULT '待选品',                      -- 选品状态
        stage           TEXT DEFAULT '选品阶段',                    -- 阶段（选品/投流测试/放量/百单/千单/复盘）
        total_orders    INTEGER DEFAULT 0,                          -- 累计订单
        total_cost      REAL DEFAULT 0,                             -- 累计消耗
        total_roi       REAL DEFAULT 0,                             -- 累计ROI
        created_at      TEXT DEFAULT (datetime('now', 'localtime')),  -- 创建时间
        updated_at      TEXT DEFAULT (datetime('now', 'localtime'))   -- 更新时间
    )
    """,

    # ===== 素材/视频表 =====
    """
    CREATE TABLE IF NOT EXISTS videos (
        video_id            TEXT PRIMARY KEY,                       -- 视频ID（主键）
        product_id          TEXT NOT NULL,                           -- 商品ID（外键，关联商品表）
        source              TEXT DEFAULT '',                         -- 素材来源
        file_path           TEXT DEFAULT '',                         -- 文件/链接
        edit_status         TEXT DEFAULT '待混剪',                   -- 混剪状态
        dedup_status        TEXT DEFAULT '待去重',                   -- 去重状态
        frontend_published  INTEGER DEFAULT 0,                       -- 前端发布标记（0=未发布，1=已发布）
        qianchuan_uploaded  INTEGER DEFAULT 0,                       -- 千川上传标记（0=未上传，1=已上传）
        order_count         INTEGER DEFAULT 0,                       -- 订单数
        cost                REAL DEFAULT 0,                          -- 消耗
        roi                 REAL DEFAULT 0,                          -- ROI
        is_order_material   INTEGER DEFAULT 0,                       -- 是否出单素材（0=否，1=是）
        ai_edit_task_created INTEGER DEFAULT 0,                      -- AI精剪任务是否已创建（幂等用）
        created_at          TEXT DEFAULT (datetime('now', 'localtime')),
        updated_at          TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (product_id) REFERENCES products(product_id)
    )
    """,

    # ===== 投流计划表 =====
    """
    CREATE TABLE IF NOT EXISTS campaigns (
        campaign_id     TEXT PRIMARY KEY,                            -- 计划ID（主键）
        product_id      TEXT NOT NULL,                                -- 商品ID（外键）
        video_id        TEXT NOT NULL,                                -- 视频ID（外键）
        status          TEXT DEFAULT '待创建',                        -- 计划状态
        start_time      TEXT DEFAULT '',                              -- 开始时间
        cost            REAL DEFAULT 0,                               -- 消耗
        order_count     INTEGER DEFAULT 0,                            -- 订单数
        roi             REAL DEFAULT 0,                               -- ROI
        is_abnormal     INTEGER DEFAULT 0,                            -- 异常标记（0=正常，1=异常）
        last_backfill   TEXT DEFAULT '',                              -- 最近回填时间
        created_at      TEXT DEFAULT (datetime('now', 'localtime')),
        updated_at      TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (product_id) REFERENCES products(product_id),
        FOREIGN KEY (video_id) REFERENCES videos(video_id)
    )
    """,

    # ===== 任务/复盘表 =====
    """
    CREATE TABLE IF NOT EXISTS tasks (
        task_id         TEXT PRIMARY KEY,                             -- 任务ID（主键）
        trigger_source  TEXT DEFAULT '',                              -- 触发来源（哪个触发点/人工）
        task_type       TEXT NOT NULL,                                -- 任务类型
        product_id      TEXT DEFAULT '',                              -- 关联商品ID
        video_id        TEXT DEFAULT '',                              -- 关联视频ID
        campaign_id     TEXT DEFAULT '',                              -- 关联投流计划ID
        owner           TEXT DEFAULT '',                              -- 负责人
        priority        TEXT DEFAULT '中',                            -- 优先级
        status          TEXT DEFAULT '待处理',                        -- 状态
        deadline        TEXT DEFAULT '',                              -- 截止时间
        trigger_reason  TEXT DEFAULT '',                              -- 触发原因
        review_conclusion TEXT DEFAULT '',                            -- 复盘结论
        next_action     TEXT DEFAULT '',                              -- 下一步动作
        need_confirm    INTEGER DEFAULT 0,                            -- 是否需要人工确认（0=否，1=是）
        confirmed       INTEGER DEFAULT 0,                            -- 是否已确认（0=否，1=是）
        created_at      TEXT DEFAULT (datetime('now', 'localtime')),
        updated_at      TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """,

    # ===== 触发记录表（用于幂等和审计）=====
    """
    CREATE TABLE IF NOT EXISTS trigger_logs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,           -- 自增ID
        trigger_type    TEXT NOT NULL,                                -- 触发类型（A/B/C/D/E/F）
        dedup_key       TEXT NOT NULL UNIQUE,                         -- 去重键（唯一，防重复）
        target_id       TEXT DEFAULT '',                              -- 目标对象ID（商品/视频/计划）
        result          TEXT DEFAULT '',                              -- 执行结果（成功/失败/跳过）
        message         TEXT DEFAULT '',                              -- 详细信息
        created_at      TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """,

    # ===== 操作日志表（Agent执行动作记录）=====
    """
    CREATE TABLE IF NOT EXISTS action_logs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        actor           TEXT DEFAULT 'system',                        -- 操作者（system/agent/user）
        action_type     TEXT NOT NULL,                                -- 动作类型
        target_type     TEXT DEFAULT '',                              -- 目标类型（product/video/campaign/task）
        target_id       TEXT DEFAULT '',                              -- 目标ID
        details         TEXT DEFAULT '',                              -- 动作详情
        result          TEXT DEFAULT '',                              -- 结果
        created_at      TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """,
]

# 索引创建SQL（加快常用查询）
CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_videos_product ON videos(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_videos_dedup ON videos(dedup_status)",
    "CREATE INDEX IF NOT EXISTS idx_campaigns_product ON campaigns(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_campaigns_video ON campaigns(video_id)",
    "CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(task_type)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_product ON tasks(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_products_status ON products(status)",
    "CREATE INDEX IF NOT EXISTS idx_trigger_logs_dedup ON trigger_logs(dedup_key)",
]


def create_tables(db) -> None:
    """
    创建所有数据表和索引

    Args:
        db: Database实例
    """
    logger.info("开始创建数据表...")
    for sql in CREATE_TABLES_SQL:
        db.execute_update(sql)
    for sql in CREATE_INDEXES_SQL:
        db.execute_update(sql)
    logger.info("数据表和索引创建完成")


# ============================================
# 测试题给出的样例数据
# ============================================

SAMPLE_PRODUCTS: List[Tuple] = [
    # product_id, name, category, commission_rate, owner, status, stage, total_orders
    ("P001", "保湿口红", "美妆", 25.0, "张三", "投流测试", "投流测试阶段", 20),
    ("P002", "控油粉底液", "美妆", 30.0, "李四", "投流测试", "投流测试阶段", 98),
    ("P003", "美白精华", "美妆", 20.0, "王五", "放量", "百单阶段", 105),
    ("P004", "抗皱面霜", "美妆", 28.0, "赵六", "放量", "千单阶段", 1008),
    ("P005", "卸妆水", "美妆", 18.0, "孙七", "投流测试", "投流测试阶段", 0),
]

SAMPLE_VIDEOS: List[Tuple] = [
    # video_id, product_id, source, file_path, edit_status, dedup_status,
    # frontend_published, qianchuan_uploaded, order_count, cost, roi, is_order_material
    ("V001", "P001", "抖音搜索", "files/V001.mp4", "混剪完成", "去重通过", 1, 0, 0, 80, 0.0, 0),
    ("V002", "P001", "抖音搜索", "files/V002.mp4", "混剪完成", "去重通过", 0, 1, 1, 120, 1.6, 1),
    ("V003", "P002", "抖音搜索", "files/V003.mp4", "混剪完成", "去重通过", 1, 1, 6, 200, 2.2, 1),
    ("V004", "P003", "抖音搜索", "files/V004.mp4", "混剪完成", "去重通过", 1, 1, 8, 450, 1.9, 1),
    ("V005", "P004", "抖音搜索", "files/V005.mp4", "混剪完成", "去重通过", 1, 1, 35, 1600, 2.5, 1),
    ("V006", "P005", "抖音搜索", "files/V006.mp4", "混剪完成", "去重通过", 0, 1, 0, 300, 0.0, 0),
]

SAMPLE_CAMPAIGNS: List[Tuple] = [
    # campaign_id, product_id, video_id, status, start_time, cost, order_count, roi
    ("C001", "P001", "V001", "投流中", "2026-08-30 10:00:00", 80, 0, 0.0),
    ("C002", "P001", "V002", "投流中", "2026-08-30 10:00:00", 120, 1, 1.6),
    ("C003", "P002", "V003", "投流中", "2026-08-29 14:00:00", 200, 6, 2.2),
    ("C004", "P003", "V004", "投流中", "2026-08-28 09:00:00", 450, 8, 1.9),
    ("C005", "P004", "V005", "投流中", "2026-08-25 11:00:00", 1600, 35, 2.5),
    ("C006", "P005", "V006", "投流中", "2026-08-29 16:00:00", 300, 0, 0.0),
]


def insert_sample_data(db) -> None:
    """
    插入测试题给出的样例数据

    Args:
        db: Database实例
    """
    logger.info("开始插入样例数据...")

    # 插入商品
    db.execute_many(
        """INSERT OR IGNORE INTO products
           (product_id, name, category, commission_rate, owner, status, stage, total_orders)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        SAMPLE_PRODUCTS,
    )

    # 插入视频
    db.execute_many(
        """INSERT OR IGNORE INTO videos
           (video_id, product_id, source, file_path, edit_status, dedup_status,
            frontend_published, qianchuan_uploaded, order_count, cost, roi, is_order_material)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        SAMPLE_VIDEOS,
    )

    # 插入投流计划
    db.execute_many(
        """INSERT OR IGNORE INTO campaigns
           (campaign_id, product_id, video_id, status, start_time, cost, order_count, roi)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        SAMPLE_CAMPAIGNS,
    )

    logger.info("样例数据插入完成")


def init_database(db_path: str = "data/ecommerce.db"):
    """
    初始化数据库：创建表 + 插入样例数据

    Args:
        db_path: 数据库文件路径

    Returns:
        Database实例
    """
    from .db import Database

    db = Database(db_path)
    db.connect()
    create_tables(db)
    insert_sample_data(db)
    return db
