"""
数据库连接管理模块

术语讲解：
- 连接（Connection）：程序和数据库之间的通道，像打电话建立了连接
- 游标（Cursor）：执行SQL语句的工具，像电话里的话筒，用来说话（执行SQL）
- 事务（Transaction）：一组操作要么全部成功，要么全部失败，像转账不能扣了钱没到账
- 提交（Commit）：把修改真正保存到数据库，像确认转账
- 回滚（Rollback）：出错了撤销所有修改，像转账失败退回来
"""

import sqlite3
import os
import logging
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class Database:
    """
    数据库连接管理类

    使用方法：
        db = Database("data/ecommerce.db")
        db.connect()
        results = db.execute_query("SELECT * FROM products")
        db.close()

    或者用with语句（推荐，自动关闭连接）：
        with Database("data/ecommerce.db") as db:
            results = db.execute_query("SELECT * FROM products")
    """

    def __init__(self, db_path: str = "data/ecommerce.db", echo_sql: bool = False):
        """
        初始化数据库连接管理器

        Args:
            db_path: 数据库文件路径
            echo_sql: 是否打印执行的SQL语句（调试用）
        """
        self.db_path = db_path
        self.echo_sql = echo_sql
        self._connection: Optional[sqlite3.Connection] = None
        self._ensure_directory()

    def _ensure_directory(self):
        """确保数据库文件所在目录存在"""
        dir_path = os.path.dirname(self.db_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            logger.info(f"创建数据库目录: {dir_path}")

    def connect(self) -> sqlite3.Connection:
        """
        建立数据库连接

        Returns:
            sqlite3.Connection: 数据库连接对象
        """
        if self._connection is None:
            self._connection = sqlite3.connect(
                self.db_path,
                detect_types=sqlite3.PARSE_DECLTYPES,
                check_same_thread=False,  # 允许多线程使用同一个连接
            )
            # 设置行工厂，让查询结果可以用列名访问（像字典一样）
            self._connection.row_factory = sqlite3.Row
            # 开启外键约束（SQLite默认关闭）
            self._connection.execute("PRAGMA foreign_keys = ON")
            logger.info(f"数据库连接已建立: {self.db_path}")
        return self._connection

    def close(self):
        """关闭数据库连接"""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            logger.info("数据库连接已关闭")

    def __enter__(self):
        """with语句入口：自动连接"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """with语句出口：自动关闭，如果有异常则回滚"""
        if exc_type is not None:
            self._connection.rollback()
            logger.error(f"数据库操作异常，已回滚: {exc_val}")
        self.close()
        return False  # 不吞掉异常，继续抛出

    def execute_query(
        self,
        sql: str,
        params: Optional[Tuple] = None,
        fetch_all: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        执行查询语句（SELECT）

        Args:
            sql: SQL查询语句，用?做占位符
            params: SQL参数，元组形式，如 (value1, value2)
            fetch_all: True返回所有行，False只返回第一行

        Returns:
            查询结果列表，每个元素是字典（列名->值）

        示例：
            # 查询所有商品
            products = db.execute_query("SELECT * FROM products")

            # 按ID查询
            product = db.execute_query(
                "SELECT * FROM products WHERE product_id = ?",
                params=("P001",),
                fetch_all=False
            )
        """
        if self.echo_sql:
            logger.debug(f"执行SQL: {sql} | 参数: {params}")

        conn = self.connect()
        cursor = conn.cursor()
        try:
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            rows = cursor.fetchall()
            # 把Row对象转成普通字典
            result = [dict(row) for row in rows] if fetch_all else (
                dict(rows[0]) if rows else None
            )
            return result if fetch_all else ([result] if result else [])
        except Exception as e:
            logger.error(f"查询失败: {sql} | 错误: {e}")
            raise
        finally:
            cursor.close()

    def execute_update(
        self,
        sql: str,
        params: Optional[Tuple] = None,
        commit: bool = True,
    ) -> int:
        """
        执行更新语句（INSERT/UPDATE/DELETE）

        Args:
            sql: SQL语句，用?做占位符
            params: SQL参数
            commit: 是否立即提交（False时需要手动调用commit，用于事务）

        Returns:
            受影响的行数

        示例：
            # 插入商品
            db.execute_update(
                "INSERT INTO products (product_id, name) VALUES (?, ?)",
                params=("P001", "测试商品")
            )
        """
        if self.echo_sql:
            logger.debug(f"执行SQL: {sql} | 参数: {params}")

        conn = self.connect()
        cursor = conn.cursor()
        try:
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            affected = cursor.rowcount
            if commit:
                conn.commit()
            return affected
        except Exception as e:
            if commit:
                conn.rollback()
            logger.error(f"更新失败: {sql} | 错误: {e}")
            raise
        finally:
            cursor.close()

    def execute_many(
        self,
        sql: str,
        params_list: List[Tuple],
        commit: bool = True,
    ) -> int:
        """
        批量执行更新语句（一次插入多条数据）

        Args:
            sql: SQL语句
            params_list: 参数列表，每个元素是一个参数元组
            commit: 是否提交

        Returns:
            受影响的总行数

        示例：
            db.execute_many(
                "INSERT INTO products (product_id, name) VALUES (?, ?)",
                params_list=[("P001", "商品1"), ("P002", "商品2")]
            )
        """
        conn = self.connect()
        cursor = conn.cursor()
        try:
            cursor.executemany(sql, params_list)
            affected = cursor.rowcount
            if commit:
                conn.commit()
            return affected
        except Exception as e:
            if commit:
                conn.rollback()
            logger.error(f"批量更新失败: {sql} | 错误: {e}")
            raise
        finally:
            cursor.close()

    def commit(self):
        """手动提交事务"""
        if self._connection:
            self._connection.commit()

    def rollback(self):
        """手动回滚事务"""
        if self._connection:
            self._connection.rollback()

    def get_last_insert_id(self) -> int:
        """获取最后插入的自增ID"""
        result = self.execute_query("SELECT last_insert_rowid() as id", fetch_all=False)
        return result[0]["id"] if result else 0


# 全局数据库实例（单例模式）
_db_instance: Optional[Database] = None


def get_db(db_path: str = "data/ecommerce.db", echo_sql: bool = False) -> Database:
    """
    获取全局数据库实例（单例模式）

    术语讲解：单例模式 — 整个程序只有一个数据库连接实例，避免重复创建连接

    Args:
        db_path: 数据库文件路径
        echo_sql: 是否打印SQL

    Returns:
        Database实例
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path, echo_sql)
    return _db_instance
1