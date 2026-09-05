"""
状态机模块 — 管理商品/视频/任务的状态流转

术语讲解：
- 状态机：管理状态流转的机制，规定了什么状态能变到什么状态
- 流转守卫：状态转换前的检查，条件不满足就不让转
- 流转动作：状态转换时自动执行的操作
- 幂等性：同一个操作执行多次结果一样
- 非法流转：不允许的状态转换，比如"待选品"直接跳到"出单"
"""

import logging
from typing import Dict, List, Optional, Set, Tuple, Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class StateMachine:
    """
    通用状态机

    使用方法：
        sm = StateMachine()
        sm.add_transition("待选品", "已确认")
        sm.add_transition("已确认", "素材搜集")
        sm.can_transition("待选品", "已确认")  # True
        sm.can_transition("待选品", "出单")      # False
    """

    def __init__(self, name: str = "状态机"):
        self.name = name
        # 状态流转图：{当前状态: {可以转到的状态集合}}
        self._transitions: Dict[str, Set[str]] = {}
        # 所有状态
        self._all_states: Set[str] = set()
        # 流转守卫：{(from, to): 检查函数}，检查函数返回True表示允许
        self._guards: Dict[Tuple[str, str], Callable] = {}
        # 流转动作：{(from, to): 动作函数}，状态转换成功后执行
        self._actions: Dict[Tuple[str, str], Callable] = {}

    def add_state(self, state: str) -> None:
        """添加一个状态"""
        self._all_states.add(state)
        if state not in self._transitions:
            self._transitions[state] = set()

    def add_transition(
        self,
        from_state: str,
        to_state: str,
        guard: Optional[Callable] = None,
        action: Optional[Callable] = None,
    ) -> None:
        """
        添加一条状态流转规则

        Args:
            from_state: 起始状态
            to_state: 目标状态
            guard: 守卫函数，返回True才允许转换（可选）
            action: 动作函数，转换成功后执行（可选）
        """
        self.add_state(from_state)
        self.add_state(to_state)
        self._transitions[from_state].add(to_state)

        if guard:
            self._guards[(from_state, to_state)] = guard
        if action:
            self._actions[(from_state, to_state)] = action

    def can_transition(self, from_state: str, to_state: str, **kwargs) -> Tuple[bool, str]:
        """
        检查是否允许从from_state转到to_state

        Args:
            from_state: 当前状态
            to_state: 目标状态
            **kwargs: 传给守卫函数的参数

        Returns:
            (是否允许, 原因说明)
        """
        # 检查起始状态是否存在
        if from_state not in self._all_states:
            return False, f"未知状态: {from_state}"

        # 检查目标状态是否存在
        if to_state not in self._all_states:
            return False, f"未知状态: {to_state}"

        # 检查是否有这条流转规则
        if to_state not in self._transitions.get(from_state, set()):
            return False, f"不允许从 [{from_state}] 转到 [{to_state}]"

        # 检查守卫条件
        guard = self._guards.get((from_state, to_state))
        if guard:
            try:
                allowed, reason = guard(**kwargs)
                if not allowed:
                    return False, f"守卫条件不满足: {reason}"
            except Exception as e:
                return False, f"守卫检查异常: {e}"

        return True, "允许流转"

    def transition(
        self,
        from_state: str,
        to_state: str,
        context: Optional[Dict] = None,
        **kwargs,
    ) -> Tuple[bool, str]:
        """
        执行状态转换

        Args:
            from_state: 当前状态
            to_state: 目标状态
            context: 上下文信息（传给动作函数）
            **kwargs: 传给守卫函数的参数

        Returns:
            (是否成功, 原因说明)
        """
        # 先检查是否允许
        allowed, reason = self.can_transition(from_state, to_state, **kwargs)
        if not allowed:
            logger.warning(f"[{self.name}] 状态流转被拒绝: {from_state} -> {to_state}, 原因: {reason}")
            return False, reason

        # 执行流转动作
        action = self._actions.get((from_state, to_state))
        if action:
            try:
                action(context=context, **kwargs)
            except Exception as e:
                logger.error(f"[{self.name}] 流转动作执行失败: {e}")
                return False, f"流转动作失败: {e}"

        logger.info(f"[{self.name}] 状态流转成功: {from_state} -> {to_state}")
        return True, "流转成功"

    def get_available_transitions(self, from_state: str) -> List[str]:
        """获取从当前状态可以转到哪些状态"""
        return sorted(list(self._transitions.get(from_state, set())))

    def get_all_states(self) -> List[str]:
        """获取所有状态"""
        return sorted(list(self._all_states))


class ProductStateMachine(StateMachine):
    """
    商品状态机 — 严格按测试题要求的状态流转

    状态流转：
    待选品 → 已确认 → 素材搜集 → 混剪 → 去重通过 → 前端已发布/千川待上传
    → 投流测试 → 出单 → AI钩子精剪 → 放量 → 百单/千单 → 复盘 → 再选品
    """

    # 状态常量
    PENDING = "待选品"
    CONFIRMED = "已确认"
    MATERIAL_COLLECTING = "素材搜集"
    EDITING = "混剪"
    DEDUP_PASSED = "去重通过"
    FRONTEND_PUBLISHED = "前端已发布"
    QIANCHUAN_PENDING = "千川待上传"
    AD_TESTING = "投流测试"
    ORDERED = "出单"
    AI_HOOK_EDITING = "AI钩子精剪"
    SCALING = "放量"
    HUNDRED_ORDERS = "百单"
    THOUSAND_ORDERS = "千单"
    REVIEW = "复盘"
    RESELECT = "再选品"
    STOPPED = "已停测"

    def __init__(self):
        super().__init__("商品状态机")
        self._build_transitions()

    def _build_transitions(self):
        """构建所有状态流转规则"""
        # 选品阶段
        self.add_transition(self.PENDING, self.CONFIRMED)
        self.add_transition(self.CONFIRMED, self.MATERIAL_COLLECTING)

        # 素材生产阶段
        self.add_transition(self.MATERIAL_COLLECTING, self.EDITING)
        self.add_transition(self.EDITING, self.DEDUP_PASSED)

        # 发布阶段（去重通过后可以走前端发布或千川上传）
        self.add_transition(self.DEDUP_PASSED, self.FRONTEND_PUBLISHED)
        self.add_transition(self.DEDUP_PASSED, self.QIANCHUAN_PENDING)
        self.add_transition(self.FRONTEND_PUBLISHED, self.AD_TESTING)
        self.add_transition(self.QIANCHUAN_PENDING, self.AD_TESTING)

        # 投流测试阶段
        self.add_transition(self.AD_TESTING, self.ORDERED)
        self.add_transition(self.AD_TESTING, self.STOPPED)  # 无效素材停测

        # 出单后
        self.add_transition(self.ORDERED, self.AI_HOOK_EDITING)
        self.add_transition(self.AI_HOOK_EDITING, self.SCALING)

        # 放量分级
        self.add_transition(self.SCALING, self.HUNDRED_ORDERS)
        self.add_transition(self.HUNDRED_ORDERS, self.THOUSAND_ORDERS)

        # 复盘闭环
        self.add_transition(self.HUNDRED_ORDERS, self.REVIEW)
        self.add_transition(self.THOUSAND_ORDERS, self.REVIEW)
        self.add_transition(self.STOPPED, self.REVIEW)
        self.add_transition(self.REVIEW, self.RESELECT)
        self.add_transition(self.RESELECT, self.PENDING)  # 循环回到选品

        # 一些允许的回退（实际业务中可能需要）
        self.add_transition(self.CONFIRMED, self.PENDING)  # 取消确认
        self.add_transition(self.AD_TESTING, self.MATERIAL_COLLECTING)  # 素材不够回退

    def get_stage_by_status(self, status: str) -> str:
        """根据状态判断所属阶段（用于商品stage字段）"""
        stage_map = {
            self.PENDING: "选品阶段",
            self.CONFIRMED: "选品阶段",
            self.MATERIAL_COLLECTING: "素材生产阶段",
            self.EDITING: "素材生产阶段",
            self.DEDUP_PASSED: "素材生产阶段",
            self.FRONTEND_PUBLISHED: "发布阶段",
            self.QIANCHUAN_PENDING: "发布阶段",
            self.AD_TESTING: "投流测试阶段",
            self.ORDERED: "投流测试阶段",
            self.AI_HOOK_EDITING: "精剪阶段",
            self.SCALING: "放量阶段",
            self.HUNDRED_ORDERS: "百单阶段",
            self.THOUSAND_ORDERS: "千单阶段",
            self.REVIEW: "复盘阶段",
            self.RESELECT: "复盘阶段",
            self.STOPPED: "复盘阶段",
        }
        return stage_map.get(status, "未知阶段")
