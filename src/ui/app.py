"""
Streamlit前端界面 — 数据看板、工作流监控、Agent对话

术语讲解：
- Streamlit：用Python写网页的框架，不用学HTML/CSS/JS
- 数据看板：一眼看到关键数据的页面，有图表有表格
- 侧边栏：左边的导航栏
- 会话状态：页面刷新后还能保留的数据
"""

import sys
import os

# 把项目根目录加入Python路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

from src.database.db import get_db
from src.database.crud import (
    ProductCRUD, VideoCRUD, CampaignCRUD, TaskCRUD, TriggerLogCRUD,
)
from src.database.models import create_tables, insert_sample_data
from src.workflow.triggers import WorkflowTriggers
from src.agent.agent import ReviewAgent
from src.config import get_config
from src.logger import setup_logging

# 页面配置
st.set_page_config(
    page_title="AI电商自动化工作流系统",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 初始化
setup_logging()
config = get_config()

# 初始化数据库（只执行一次）
if "db_initialized" not in st.session_state:
    db = get_db(config.get("database.path", "data/ecommerce.db"))
    create_tables(db)
    insert_sample_data(db)
    st.session_state.db_initialized = True
    st.session_state.db = db

db = st.session_state.db

# 初始化Agent
if "agent" not in st.session_state:
    st.session_state.agent = ReviewAgent(db)

agent = st.session_state.agent


def flash(level: str, message: str) -> None:
    """暂存操作提示，供 rerun 后显示（st.success 在 rerun 后会丢失）"""
    st.session_state.flash_message = (level, message)


def render_flash() -> None:
    """显示并清除上一次操作暂存的提示消息"""
    flash_msg = st.session_state.pop("flash_message", None)
    if flash_msg:
        level, message = flash_msg
        getattr(st, level)(message)


# ============================================
# 侧边栏导航
# ============================================

st.sidebar.title("🚀 AI电商工作流")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "导航",
    [
        "📊 数据看板",
        "📦 商品管理",
        "🎬 视频管理",
        "📈 投流管理",
        "📋 任务管理",
        "⚙️ 工作流监控",
        "🤖 数智员工",
        "📖 使用说明",
    ],
)

st.sidebar.markdown("---")

# 显示上一次操作的提示消息（在 rerun 后仍可见）
render_flash()



# ============================================
# 页面1：数据看板
# ============================================

if page == "📊 数据看板":
    st.title("📊 数据看板")
    st.markdown("系统核心指标一览")

    product_crud = ProductCRUD(db)
    video_crud = VideoCRUD(db)
    campaign_crud = CampaignCRUD(db)
    task_crud = TaskCRUD(db)

    # 关键指标卡片
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("商品总数", product_crud.count())
    with col2:
        st.metric("视频总数", video_crud.count())
    with col3:
        st.metric("投流计划", campaign_crud.count())
    with col4:
        st.metric("待处理任务", len(task_crud.get_by_status("待处理")))

    col5, col6, col7, col8 = st.columns(4)
    with col5:
        ordered = video_crud.get_ordered_videos()
        st.metric("出单视频", len(ordered))
    with col6:
        hundred = product_crud.get_by_stage("百单阶段")
        st.metric("百单商品", len(hundred))
    with col7:
        thousand = product_crud.get_by_stage("千单阶段")
        st.metric("千单商品", len(thousand))
    with col8:
        total_orders = sum(p["total_orders"] for p in product_crud.get_all(limit=1000))
        st.metric("累计订单", total_orders)

    st.markdown("---")

    # 商品阶段分布
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("商品阶段分布")
        products = product_crud.get_all(limit=1000)
        if products:
            df = pd.DataFrame(products)
            stage_counts = df["stage"].value_counts().reset_index()
            stage_counts.columns = ["阶段", "数量"]
            fig = px.pie(stage_counts, values="数量", names="阶段", title="商品阶段占比")
            st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.subheader("视频出单情况")
        videos = video_crud.get_all(limit=1000)
        if videos:
            df_v = pd.DataFrame(videos)
            df_v["是否出单"] = df_v["is_order_material"].map({1: "已出单", 0: "未出单"})
            order_counts = df_v["是否出单"].value_counts().reset_index()
            order_counts.columns = ["状态", "数量"]
            fig2 = px.bar(order_counts, x="状态", y="数量", title="视频出单情况", color="状态")
            st.plotly_chart(fig2, use_container_width=True)

    # 最近触发记录
    st.subheader("最近触发记录")
    trigger_logs = TriggerLogCRUD(db).get_recent(10)
    if trigger_logs:
        df_logs = pd.DataFrame(trigger_logs)
        st.dataframe(df_logs[["created_at", "trigger_type", "target_id", "result", "message"]],
                     use_container_width=True)
    else:
        st.info("暂无触发记录")


# ============================================
# 页面2：商品管理
# ============================================

elif page == "📦 商品管理":
    st.title("📦 商品管理")

    product_crud = ProductCRUD(db)
    video_crud = VideoCRUD(db)

    # 筛选
    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.selectbox("按状态筛选", ["全部", "待选品", "已确认", "素材搜集", "投流测试", "出单", "百单", "千单", "已停测"])
    with col2:
        stage_filter = st.selectbox("按阶段筛选", ["全部", "选品阶段", "投流测试阶段", "百单阶段", "千单阶段", "复盘阶段"])

    # 查询
    if status_filter != "全部":
        products = product_crud.get_by_status(status_filter)
    elif stage_filter != "全部":
        products = product_crud.get_by_stage(stage_filter)
    else:
        products = product_crud.get_all(limit=1000)

    st.write(f"共 {len(products)} 个商品")

    if products:
        df = pd.DataFrame(products)
        st.dataframe(df[["product_id", "name", "category", "commission_rate", "owner",
                         "status", "stage", "total_orders", "updated_at"]],
                     use_container_width=True)

    # 商品详情展开
    st.markdown("---")
    st.subheader("商品详情")
    selected_product = st.selectbox("选择商品查看详情",
                                     [p["product_id"] + " - " + p["name"] for p in products] if products else ["无"])

    if selected_product != "无":
        pid = selected_product.split(" - ")[0]
        product = product_crud.get_by_id(pid)
        videos = video_crud.get_by_product(pid)

        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**商品ID**: {product['product_id']}")
            st.write(f"**商品名**: {product['name']}")
            st.write(f"**类目**: {product['category']}")
            st.write(f"**佣金**: {product['commission_rate']}%")
            st.write(f"**负责人**: {product['owner']}")
        with col2:
            st.write(f"**状态**: {product['status']}")
            st.write(f"**阶段**: {product['stage']}")
            st.write(f"**累计订单**: {product['total_orders']}")
            st.write(f"**创建时间**: {product['created_at']}")
            st.write(f"**更新时间**: {product['updated_at']}")

        st.markdown("**该商品下的视频:**")
        if videos:
            df_v = pd.DataFrame(videos)
            st.dataframe(df_v[["video_id", "edit_status", "dedup_status", "order_count",
                               "cost", "roi", "is_order_material"]],
                         use_container_width=True)
        else:
            st.info("暂无视频")

        # 操作按钮
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("✅ 确认商品（触发点A）"):
                triggers = WorkflowTriggers(db)
                result = triggers.trigger_a_product_confirm(pid)
                flash("success", result.get("message", "完成"))
                st.rerun()
        with col2:
            if st.button("📈 放量分级检查（触发点D）"):
                triggers = WorkflowTriggers(db)
                result = triggers.trigger_d_scaling_tier(pid)
                flash("success", result.get("message", "完成"))
                st.rerun()


# ============================================
# 页面3：视频管理
# ============================================

elif page == "🎬 视频管理":
    st.title("🎬 视频管理")

    video_crud = VideoCRUD(db)
    product_crud = ProductCRUD(db)

    # 筛选
    col1, col2 = st.columns(2)
    with col1:
        product_filter = st.selectbox("按商品筛选", ["全部"] + [p["product_id"] for p in product_crud.get_all(limit=100)])
    with col2:
        dedup_filter = st.selectbox("按去重状态筛选", ["全部", "待去重", "去重通过", "去重失败"])

    if product_filter != "全部":
        videos = video_crud.get_by_product(product_filter)
    else:
        videos = video_crud.get_all(limit=1000)

    if dedup_filter != "全部":
        videos = [v for v in videos if v["dedup_status"] == dedup_filter]

    st.write(f"共 {len(videos)} 条视频")

    if videos:
        df = pd.DataFrame(videos)
        st.dataframe(df[["video_id", "product_id", "edit_status", "dedup_status",
                         "frontend_published", "qianchuan_uploaded", "order_count",
                         "cost", "roi", "is_order_material"]],
                     use_container_width=True)

    # 操作区
    st.markdown("---")
    st.subheader("视频操作")

    selected_video = st.selectbox("选择视频",
                                    [v["video_id"] + " (商品" + v["product_id"] + ")" for v in videos] if videos else ["无"])

    if selected_video != "无":
        vid = selected_video.split(" ")[0]

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("✅ 标记去重通过（触发点B）"):
                video_crud.update_dedup_status(vid, "去重通过")
                triggers = WorkflowTriggers(db)
                result = triggers.trigger_b_dedup_complete(vid)
                flash("success", result.get("message", "完成"))
                st.rerun()

        with col2:
            new_orders = st.number_input("回填订单数", min_value=0, value=1)
            if st.button("📝 回填订单（触发点C）"):
                triggers = WorkflowTriggers(db)
                result = triggers.trigger_c_order_detected(vid, new_orders)
                flash("success", result.get("message", "完成"))
                st.rerun()

        with col3:
            if st.button("🔍 查看详情"):
                video = video_crud.get_by_id(vid)
                st.json(video)


# ============================================
# 页面4：投流管理
# ============================================

elif page == "📈 投流管理":
    st.title("📈 投流管理")

    campaign_crud = CampaignCRUD(db)

    status_filter = st.selectbox("按状态筛选", ["全部", "投流中", "已暂停", "已停投", "已完成", "异常"])
    if status_filter != "全部":
        campaigns = campaign_crud.get_by_status(status_filter)
    else:
        campaigns = campaign_crud.get_all(limit=1000)

    st.write(f"共 {len(campaigns)} 个投流计划")

    if campaigns:
        df = pd.DataFrame(campaigns)
        st.dataframe(df[["campaign_id", "product_id", "video_id", "status",
                         "start_time", "cost", "order_count", "roi", "is_abnormal"]],
                     use_container_width=True)

    # 操作区
    st.markdown("---")
    st.subheader("投流操作")

    col1, col2 = st.columns(2)
    with col1:
        selected_campaign = st.selectbox("选择投流计划",
                                           [c["campaign_id"] for c in campaigns] if campaigns else ["无"])
    with col2:
        if selected_campaign != "无":
            if st.button("🛑 停测检查（触发点E）"):
                triggers = WorkflowTriggers(db)
                result = triggers.trigger_e_stop_test_check(selected_campaign)
                if result:
                    flash("success", result[0].get("message", "完成"))
                else:
                    flash("warning", "该投流计划未命中停测规则")
                st.rerun()

    # 批量停测检查
    st.markdown("---")
    if st.button("🔍 批量检查所有投流计划（触发点E）"):
        triggers = WorkflowTriggers(db)
        results = triggers.trigger_e_stop_test_check()
        triggered = [r for r in results if r.get("triggered")]
        st.write(f"检查了 {len(results)} 个计划，命中停测规则 {len(triggered)} 个")
        if triggered:
            df_t = pd.DataFrame(triggered)
            st.dataframe(df_t[["campaign_id", "video_id", "hit_rules", "task_id"]],
                         use_container_width=True)


# ============================================
# 页面5：任务管理
# ============================================

elif page == "📋 任务管理":
    st.title("📋 任务管理")

    task_crud = TaskCRUD(db)

    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.selectbox("按状态筛选", ["全部", "待处理", "处理中", "已完成", "已取消", "已阻断"])
    with col2:
        type_filter = st.selectbox("按类型筛选", ["全部", "素材搜集", "前端挂车发布", "千川上传",
                                                    "AI钩子精剪", "放量操作", "停测/复盘", "日/批次复盘", "佣金待填写"])

    if status_filter != "全部":
        tasks = task_crud.get_by_status(status_filter)
    elif type_filter != "全部":
        tasks = task_crud.get_by_type(type_filter)
    else:
        tasks = task_crud.get_all(limit=1000)

    st.write(f"共 {len(tasks)} 个任务")

    if tasks:
        df = pd.DataFrame(tasks)
        st.dataframe(df[["task_id", "task_type", "trigger_source", "product_id",
                         "video_id", "priority", "status", "trigger_reason", "created_at"]],
                     use_container_width=True)

    # 任务详情和操作
    st.markdown("---")
    st.subheader("任务操作")
    selected_task = st.selectbox("选择任务",
                                   [t["task_id"] + " - " + t["task_type"] for t in tasks] if tasks else ["无"])

    if selected_task != "无":
        tid = selected_task.split(" - ")[0]
        task = task_crud.get_by_id(tid)

        st.write(f"**任务ID**: {task['task_id']}")
        st.write(f"**类型**: {task['task_type']}")
        st.write(f"**状态**: {task['status']}")
        st.write(f"**优先级**: {task['priority']}")
        st.write(f"**触发原因**: {task['trigger_reason']}")
        st.write(f"**复盘结论**: {task.get('review_conclusion', '无')}")
        st.write(f"**下一步动作**: {task.get('next_action', '无')}")

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("✅ 标记完成"):
                task_crud.update_status(tid, "已完成")
                flash("success", f"任务 {tid} 已标记完成")
                st.rerun()
        with col2:
            if st.button("🔄 重新处理"):
                task_crud.update_status(tid, "待处理")
                flash("success", f"任务 {tid} 已重置为待处理")
                st.rerun()
        with col3:
            if st.button("❌ 取消"):
                task_crud.update_status(tid, "已取消")
                flash("success", f"任务 {tid} 已取消")
                st.rerun()


# ============================================
# 页面6：工作流监控
# ============================================

elif page == "⚙️ 工作流监控":
    st.title("⚙️ 工作流监控")
    st.markdown("6个自动化触发点的执行状态和手动触发")

    # 触发点状态卡片
    st.subheader("触发点状态")
    trigger_log_crud = TriggerLogCRUD(db)
    recent_logs = trigger_log_crud.get_recent(100)

    col1, col2, col3 = st.columns(3)
    with col1:
        a_count = len([l for l in recent_logs if l["trigger_type"] == "A"])
        st.metric("A. 商品确认", f"{a_count}次")
    with col2:
        b_count = len([l for l in recent_logs if l["trigger_type"] == "B"])
        st.metric("B. 去重分流", f"{b_count}次")
    with col3:
        c_count = len([l for l in recent_logs if l["trigger_type"] == "C"])
        st.metric("C. 出单触发", f"{c_count}次")

    col4, col5, col6 = st.columns(3)
    with col4:
        d_count = len([l for l in recent_logs if l["trigger_type"] == "D"])
        st.metric("D. 放量分级", f"{d_count}次")
    with col5:
        e_count = len([l for l in recent_logs if l["trigger_type"] == "E"])
        st.metric("E. 无效素材停测", f"{e_count}次")
    with col6:
        f_count = len([l for l in recent_logs if l["trigger_type"] == "F"])
        st.metric("F. 日/批次复盘", f"{f_count}次")

    # 手动触发区
    st.markdown("---")
    st.subheader("手动触发")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**触发点F：日/批次复盘**")
        if st.button("🔄 运行复盘"):
            triggers = WorkflowTriggers(db)
            result = triggers.trigger_f_daily_review()
            flash("success", result.get("review_conclusion", "复盘完成"))
            st.session_state.last_review_result = result
            st.rerun()

    with col2:
        st.markdown("**全流程演示**")
        if st.button("🚀 运行全流程演示"):
            triggers = WorkflowTriggers(db)
            result = triggers.run_full_workflow_demo()
            flash("success", "全流程演示完成！")
            st.session_state.last_demo_result = result
            st.rerun()

    # 显示上一次复盘/演示的详细结果（rerun 后仍可见）
    if "last_review_result" in st.session_state:
        with st.expander("查看最近一次复盘结果"):
            st.json(st.session_state.last_review_result)
    if "last_demo_result" in st.session_state:
        with st.expander("查看最近一次演示结果"):
            st.json(st.session_state.last_demo_result)

    # 触发记录时间线
    st.markdown("---")
    st.subheader("触发记录时间线")
    if recent_logs:
        df = pd.DataFrame(recent_logs[:30])
        st.dataframe(df[["created_at", "trigger_type", "target_id", "result", "message"]],
                     use_container_width=True)
    else:
        st.info("暂无触发记录")


# ============================================
# 页面7：数智员工（Agent对话）
# ============================================

elif page == "🤖 数智员工":
    st.title("🤖 素材与投流复盘数智员工")
    st.markdown("能读业务数据、做判断、生成动作并回写的AI员工")

    # 快捷问题
    st.markdown("**快捷提问：**")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("📊 哪些视频已出单？"):
            st.session_state.quick_question = "今天哪些视频已出单？"
    with col2:
        if st.button("✂️ 哪些需要AI精剪？"):
            st.session_state.quick_question = "哪些需要立即进入AI钩子精剪？"
    with col3:
        if st.button("🚀 百单/千单商品？"):
            st.session_state.quick_question = "哪些商品已进入百单/千单阶段？"
    with col4:
        if st.button("🛑 哪些应停测？"):
            st.session_state.quick_question = "哪些商品/素材应停测？"

    st.markdown("---")

    # 对话界面
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "你好！我是素材与投流复盘数智员工。我可以帮你查询出单视频、AI精剪需求、百单/千单商品、停测建议，也可以经确认后执行操作。请问有什么可以帮你的？"}
        ]

    # 显示对话历史
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 用户输入
    user_input = st.chat_input("输入你的问题...")

    # 快捷问题填充
    if "quick_question" in st.session_state and st.session_state.quick_question:
        user_input = st.session_state.quick_question
        st.session_state.quick_question = ""

    if user_input:
        # 显示用户消息
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Agent回复
        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                response = agent.chat(user_input)
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

    # 清空对话
    st.markdown("---")
    if st.button("🗑️ 清空对话历史"):
        st.session_state.messages = []
        agent.clear_history()
        flash("success", "对话历史已清空")
        st.rerun()


# ============================================
# 页面8：使用说明
# ============================================

elif page == "📖 使用说明":
    st.title("📖 使用说明")

    st.markdown("""
    ## 项目简介

    这是一个**抖音电商选品→素材→投流→出单→复盘**全流程自动化原型，
    包含数据结构设计、6个自动化触发点、AI数智员工、工程可靠性保障。

    ## 快速开始

    ### 1. 查看数据
    - 「数据看板」查看系统核心指标
    - 「商品管理」「视频管理」「投流管理」「任务管理」查看详细数据

    ### 2. 触发自动化流程
    - 在「商品管理」点击"确认商品" → 触发点A，自动创建素材任务
    - 在「视频管理」点击"标记去重通过" → 触发点B，自动分流
    - 在「视频管理」回填订单数 → 触发点C，出单自动创建AI精剪任务
    - 在「商品管理」点击"放量分级检查" → 触发点D，百单/千单自动切换
    - 在「投流管理」点击"停测检查" → 触发点E，无效素材自动停测
    - 在「工作流监控」点击"运行复盘" → 触发点F，自动生成复盘报告

    ### 3. 使用数智员工
    - 「数智员工」页面和AI对话
    - 可以问：出单视频、AI精剪、百单/千单、停测建议
    - 可以执行：创建精剪任务、创建停测任务（需确认）、写回复盘

    ### 4. 运行全流程演示
    - 「工作流监控」页面点击"运行全流程演示"
    - 自动验证3类结果：出单触发、百单/千单、无效素材停测

    ## 技术架构

    | 层级 | 技术 |
    |------|------|
    | 后端 | Python + FastAPI |
    | 数据库 | SQLite |
    | 工作流 | 自研状态机 + 6个触发点 |
    | Agent | LangChain + 通义千问真实大模型 |
    | 前端 | Streamlit |
    | 测试 | pytest |

    ## 配置修改

    所有阈值和参数都在 `config/settings.yaml` 中配置：
    - 百单/千单阈值
    - 停测规则（消耗阈值、时长阈值）
    - 出单判定阈值
    - 日志级别
    - Agent模型配置

    ## 已知限制

    1. 外部平台（抖音、千川）接口为模拟，实际接入需要替换为真实API
    2. 定时任务需要手动触发，可接入APScheduler实现自动定时
    3. 单用户系统，未实现多用户权限管理

    ## 下一步

    1. 接入抖音/千川真实API
    2. 添加定时任务（APScheduler）
    3. 添加用户权限管理
    4. 部署到服务器（Docker + Nginx）
    """)
