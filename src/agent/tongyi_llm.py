"""
通义千问LLM模块 — 接入阿里云百炼（DashScope）真实大模型

术语讲解：
- LLM（大语言模型）：像通义千问这样的AI，能理解和生成文字
- ChatTongyi：LangChain对阿里云通义千问的封装，走DashScope接口
- 意图识别：让大模型判断用户想干什么，决定调用哪个工具
- 函数调用：AI不直接回答，而是说"我要调用XX工具"，程序执行后把结果给AI
"""

import os
import json
import logging
from datetime import date
from typing import Dict, List, Optional, Any

from dotenv import load_dotenv
from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

logger = logging.getLogger(__name__)

# 加载项目根目录下的 .env 文件（里面存着 DASHSCOPE_API_KEY）
load_dotenv()


class TongyiLLM:
    """
    通义千问真实LLM — 用大模型做意图识别和回答生成

    工作原理：
    1. analyze_intent：把用户问题和工具清单交给大模型，让它判断调用哪个工具
    2. generate_response：把工具查到的数据交给大模型，生成自然语言回答
    """

    def __init__(self, config, tool_definitions: List[Dict] = None):
        """
        初始化通义千问LLM

        Args:
            config: Config实例，用于读取 agent.* 配置
            tool_definitions: 工具定义列表（来自 AgentTools.get_tool_definitions）
        """
        self.config = config
        self.tool_definitions = tool_definitions or []

        # 从环境变量读取API Key（.env 文件里配置）
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise ValueError(
                "未找到 DASHSCOPE_API_KEY，请在项目根目录的 .env 文件中配置"
            )

        # 从配置文件读取模型参数
        model_name = config.get("agent.model", "qwen3-max")
        temperature = config.get("agent.temperature", 0)
        max_tokens = config.get("agent.max_tokens", 2000)
        timeout = config.get("agent.timeout", 120)
        max_retries = config.get("agent.max_retries", 2)

        # 注意：ChatTongyi 的 temperature/超时等参数要通过 model_kwargs 传递才会生效
        self.model = ChatTongyi(
            model=model_name,
            api_key=api_key,
            max_retries=max_retries,
            model_kwargs={
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout": timeout,
            },
        )
        self.name = f"TongyiLLM({model_name})"
        logger.info(f"通义千问LLM初始化成功：模型={model_name}, 温度={temperature}")

    # ============================================
    # 意图识别 — 让大模型决定调用哪个工具
    # ============================================

    def analyze_intent(self, user_message: str) -> Dict[str, Any]:
        """
        分析用户意图，决定调用哪个工具

        Args:
            user_message: 用户消息

        Returns:
            意图分析结果，包含工具名和参数
        """
        tools_desc = self._format_tool_definitions()

        system_prompt = f"""你是一个电商投流业务的意图识别助手。根据用户的问题，判断他想要做什么，并决定调用哪个工具。

【当前日期】{date.today().isoformat()}

【可用工具清单】
{tools_desc}

【输出要求】
你必须且只能输出一个JSON对象（不要输出任何其他文字、不要用代码块包裹），格式如下：
{{
  "intent": "意图的简短英文标识，如 query_ordered_videos",
  "tool": "要调用的工具名，如果不需要调用工具则填 null",
  "params": {{}},
  "confidence": 0.9,
  "need_confirm": false
}}

【规则】
1. params 里的参数必须从用户问题中原文提取，比如用户说"给V002创建精剪任务"，则 params 应为 {{"video_id": "V002"}}
2. 严禁编造参数：用户没有明确提到的日期、ID等参数时，params 中不要包含该参数。可选参数（如日期范围）一律省略，不要填默认值或猜测值
3. 用户说"今天"时，不要添加日期参数（工具默认就查最新数据）；只有用户给出具体日期（如"9月1日"）时才添加日期参数
4. 商品ID形如 P001，视频ID形如 V002，投流计划ID形如 C003，任务ID形如 T001
5. 高风险操作（停测、更新商品阶段）需要把 need_confirm 设为 true
6. 如果是打招呼、问帮助等不需要查数据的对话，tool 填 null
7. 如果无法理解用户意图，tool 填 null，confidence 给低值，并在返回中加 "message" 字段说明
8. 只输出JSON，不要有任何额外解释"""

        try:
            response = self.model.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_message),
                ]
            )
            content = response.content.strip()
            result = self._parse_json(content)

            # 补全默认字段，保证返回结构完整
            result.setdefault("intent", "unknown")
            result.setdefault("tool", None)
            result.setdefault("params", {})
            result.setdefault("confidence", 0.5)
            result.setdefault("need_confirm", False)
            return result

        except Exception as e:
            logger.error(f"意图识别失败: {e}")
            return {
                "intent": "unknown",
                "tool": None,
                "params": {},
                "confidence": 0.0,
                "message": f"AI服务暂时不可用：{e}",
            }

    # ============================================
    # 回答生成 — 让大模型根据数据生成自然语言回答
    # ============================================

    def generate_response(self, intent: Dict, tool_result: Dict = None) -> str:
        """
        根据意图和工具结果生成自然语言回答

        Args:
            intent: 意图分析结果
            tool_result: 工具执行结果

        Returns:
            自然语言回答
        """
        # 工具执行失败时直接返回错误信息
        if tool_result and not tool_result.get("success", True):
            return f"查询失败：{tool_result.get('message', '未知错误')}"

        # 不需要工具的纯对话（打招呼/帮助/未知意图）
        if not intent.get("tool"):
            return self._chat_response(intent)

        system_prompt = """你是一个「素材与投流复盘数智员工」，服务于抖音电商投流团队。

【回答规则】
1. 必须引用具体数据：商品ID、视频ID、订单数、消耗、ROI等
2. 必须说明判断依据：为什么得出这个结论（如"消耗≥300元且订单=0"）
3. 不能凭空猜测：数据不存在就说不存在，不能编造
4. 回答先给结论，再列依据，最后给建议
5. 用清晰易读的排版（可用序号、换行），适当使用emoji增强可读性"""

        user_prompt = f"""用户的意图是：{intent.get('intent', '')}
调用的工具是：{intent.get('tool', '')}
工具返回的数据如下（JSON格式）：
{json.dumps(tool_result, ensure_ascii=False, indent=2) if tool_result else '无数据'}

请根据以上数据，用自然、专业、有条理的语言回答用户。"""

        try:
            response = self.model.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            )
            return response.content.strip()
        except Exception as e:
            logger.error(f"回答生成失败: {e}")
            return f"AI服务暂时不可用：{e}"

    # ============================================
    # 内部辅助方法
    # ============================================

    def _chat_response(self, intent: Dict) -> str:
        """处理不需要工具的纯对话（打招呼/帮助/未知意图）"""
        intent_type = intent.get("intent", "unknown")

        if intent_type == "greeting":
            return (
                "你好！我是素材与投流复盘数智员工。\n"
                "我可以帮你：\n"
                "1. 查询出单视频\n"
                "2. 查询需要AI精剪的视频\n"
                "3. 查询百单/千单商品\n"
                "4. 查询应停测的素材\n"
                "5. 执行创建任务、写回复盘等动作\n\n"
                "请问有什么可以帮你的？"
            )

        if intent_type == "help":
            return (
                "我可以回答以下问题：\n"
                "• 「今天哪些视频已出单？」— 查询出单素材\n"
                "• 「哪些需要立即进入AI钩子精剪？」— 查询待精剪视频\n"
                "• 「哪些商品已进入百单/千单阶段？」— 查询放量商品\n"
                "• 「哪些素材应停测？」— 查询无效素材\n"
                "• 「P001商品怎么样？」— 查询商品详情\n"
                "• 「给V002创建精剪任务」— 执行动作\n"
                "• 「C006停测」— 创建停测任务（需确认）\n\n"
                "所有回答都会引用具体的商品ID/视频ID和数据，不会凭空猜测。"
            )

        # 未知意图
        return intent.get(
            "message",
            "抱歉，我未能理解您的问题。请输入「帮助」查看我能做什么。",
        )

    def _format_tool_definitions(self) -> str:
        """把工具定义列表格式化成给大模型看的文本"""
        if not self.tool_definitions:
            return "（暂无可用工具）"

        lines = []
        for tool in self.tool_definitions:
            params = tool.get("parameters", {})
            params_desc = "、".join(
                f"{k}（{v}）" for k, v in params.items()
            ) if params else "无参数"
            risk = tool.get("risk", "")
            risk_desc = f"，风险等级：{risk}" if risk else ""
            lines.append(
                f"- 工具名：{tool['name']}\n"
                f"  功能：{tool['description']}\n"
                f"  参数：{params_desc}{risk_desc}"
            )
        return "\n".join(lines)

    def _parse_json(self, text: str) -> Dict[str, Any]:
        """
        从大模型返回的文本中解析JSON，容错处理

        支持：纯JSON、被```代码块包裹的JSON、JSON前后有多余文字
        """
        # 去掉可能的代码块标记
        cleaned = text.strip()
        if cleaned.startswith("```"):
            # 去掉首行的 ``` 或 ```json
            first_newline = cleaned.find("\n")
            if first_newline != -1:
                cleaned = cleaned[first_newline + 1:]
            # 去掉结尾的 ```
            if cleaned.rstrip().endswith("```"):
                cleaned = cleaned.rstrip()[:-3]
            cleaned = cleaned.strip()

        # 直接尝试解析
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # 尝试提取第一个 { 到最后一个 } 之间的内容
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                pass

        logger.warning(f"无法解析LLM返回的JSON: {text[:200]}")
        return {}
