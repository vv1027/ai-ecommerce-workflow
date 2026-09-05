"""
Agent主体模块 — 素材与投流复盘数智员工

术语讲解：
- Agent（智能体）：不只是聊天，还能自己查数据、自己做决定、自己动手的AI
- 数智员工：一个虚拟的AI员工，能读业务数据、做判断、生成动作并回写
- 系统提示词：给AI设定角色和规则
- 工具调用：AI调用外部工具获取数据或执行操作
- 人工确认：高风险操作前，先问人确认再执行
- 对话历史：记住之前说过的话，让对话有上下文
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from ..database.db import Database
from .tools import AgentTools
from .tongyi_llm import TongyiLLM
from ..config import get_config

logger = logging.getLogger(__name__)


class ReviewAgent:
    """
    素材与投流复盘数智员工

    能力：
    1. 能读数据 — 从商品/视频/投流/任务表中实时查询
    2. 回答4类问题 — 出单视频、AI精剪、百单/千单、停测素材
    3. 给依据 — 回答中引用商品ID/视频ID、关键数据和触发规则
    4. 执行动作 — 创建任务、修改状态、写回复盘
    5. 人工确认 — 高风险动作需要人确认
    6. 边界控制 — 不猜测、不删除、不越权

    使用方法：
        agent = ReviewAgent(db)
        response = agent.chat("今天哪些视频已出单？")
        print(response)
    """

    # 系统提示词 — 定义Agent的角色、规则、回答格式
    SYSTEM_PROMPT = """你是一个「素材与投流复盘数智员工」，服务于抖音电商投流团队。

【你的职责】
1. 查询业务数据（商品、视频、投流计划、任务）
2. 回答团队日常问题（出单情况、精剪需求、放量商品、停测建议）
3. 根据数据做判断，给出有依据的建议
4. 经确认后执行操作（创建任务、写回复盘等）

【回答规则】
1. 必须引用具体数据：商品ID、视频ID、订单数、消耗、ROI等
2. 必须说明触发规则：为什么得出这个结论（如"消耗≥300元且订单=0"）
3. 不能凭空猜测：数据不存在就说不存在，不能编造
4. 高风险操作（停测、批量改状态）必须先确认
5. 回答先给结论，再列依据，最后给建议

【你能回答的问题】
- 今天哪些视频已出单？
- 哪些需要立即进入AI钩子精剪？
- 哪些商品已进入百单/千单阶段？
- 哪些商品/素材应停测、重测或继续放量？
- 某个商品/视频/投流计划的详情
- 待处理任务列表

【你能执行的操作】
- 为出单视频创建AI精剪任务
- 为无效素材创建停测任务（需确认）
- 写回复盘结论
- 更新商品阶段（需确认）
"""

    def __init__(self, db: Database):
        """
        初始化数智员工

        Args:
            db: Database实例
        """
        self.db = db
        self.tools = AgentTools(db)
        self.config = get_config()

        # 接入通义千问真实大模型（需在 .env 中配置 DASHSCOPE_API_KEY）
        self.llm = TongyiLLM(self.config, self.tools.get_tool_definitions())
        logger.info(f"Agent使用真实LLM：{self.llm.name}")

        # 对话历史（短期记忆）
        self.conversation_history: List[Dict[str, str]] = []
        self.max_history = self.config.get("agent.conversation_history", 10)

        # 待确认的动作（高风险操作需要用户确认）
        self.pending_confirmation: Optional[Dict] = None

        logger.info("素材与投流复盘数智员工已初始化")

    def chat(self, user_message: str) -> str:
        """
        和Agent对话（主入口）

        Args:
            user_message: 用户消息

        Returns:
            Agent的回答
        """
        logger.info(f"Agent收到消息: {user_message}")

        # 检查是否是确认/取消操作
        if self.pending_confirmation:
            return self._handle_confirmation(user_message)

        # 1. 分析意图
        intent = self.llm.analyze_intent(user_message)
        logger.info(f"意图识别: {intent.get('intent')} (置信度: {intent.get('confidence', 0)})")

        # 2. 如果需要调用工具
        tool_name = intent.get("tool")
        tool_result = None

        if tool_name:
            # 检查是否需要人工确认
            need_confirm = intent.get("need_confirm", False)
            risk_level = self.tools.get_tool_risk_level(tool_name)

            if risk_level == "high" or need_confirm:
                # 高风险操作，先存起来等确认
                self.pending_confirmation = {
                    "tool": tool_name,
                    "params": intent.get("params", {}),
                    "intent": intent,
                    "message": user_message,
                    "created_at": datetime.now().isoformat(),
                }
                return self._build_confirmation_message(tool_name, intent.get("params", {}))

            # 低/中风险操作，直接执行
            tool_result = self.tools.execute_tool(tool_name, **intent.get("params", {}))

        # 3. 生成回答
        response = self.llm.generate_response(intent, tool_result)

        # 4. 记录对话历史
        self._add_to_history("user", user_message)
        self._add_to_history("assistant", response)

        return response

    def _handle_confirmation(self, user_message: str) -> str:
        """
        处理用户的确认/取消

        Args:
            user_message: 用户消息（确认/取消）

        Returns:
            处理结果
        """
        msg = user_message.lower()

        # 用户确认
        if any(kw in msg for kw in ["确认", "确定", "是", "好的", "执行", "同意", "yes", "y"]):
            pending = self.pending_confirmation
            self.pending_confirmation = None

            tool_result = self.tools.execute_tool(
                pending["tool"],
                **pending["params"],
            )

            response = self.llm.generate_response(pending["intent"], tool_result)
            self._add_to_history("user", user_message)
            self._add_to_history("assistant", response)
            return response

        # 用户取消
        if any(kw in msg for kw in ["取消", "不", "算了", "不要", "no", "n"]):
            self.pending_confirmation = None
            response = "已取消该操作。有其他需要帮助的吗？"
            self._add_to_history("user", user_message)
            self._add_to_history("assistant", response)
            return response

        # 不是明确的确认/取消，提示
        return (
            f"请明确回复「确认」或「取消」。\n"
            f"待确认操作：{self.pending_confirmation['tool']}\n"
            f"参数：{self.pending_confirmation['params']}"
        )

    def _build_confirmation_message(self, tool_name: str, params: Dict) -> str:
        """
        构建确认提示消息

        Args:
            tool_name: 工具名
            params: 参数

        Returns:
            确认消息
        """
        tool_descriptions = {
            "action_create_stop_test_task": "创建停测任务",
            "action_update_product_stage": "更新商品阶段",
        }
        desc = tool_descriptions.get(tool_name, tool_name)

        return (
            f"⚠️ 这是一个高风险操作，需要您确认：\n\n"
            f"操作：{desc}\n"
            f"参数：{params}\n\n"
            f"请回复「确认」执行，或「取消」放弃。"
        )

    def _add_to_history(self, role: str, content: str):
        """
        添加到对话历史

        Args:
            role: 角色（user/assistant）
            content: 内容
        """
        self.conversation_history.append({"role": role, "content": content})
        # 保留最近N轮
        if len(self.conversation_history) > self.max_history * 2:
            self.conversation_history = self.conversation_history[-self.max_history * 2:]

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """获取对话历史"""
        return self.conversation_history.copy()

    def clear_history(self):
        """清空对话历史"""
        self.conversation_history.clear()
        self.pending_confirmation = None
        logger.info("Agent对话历史已清空")

    def get_available_tools(self) -> List[Dict]:
        """获取可用工具列表"""
        return self.tools.get_tool_definitions()

    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return self.SYSTEM_PROMPT
