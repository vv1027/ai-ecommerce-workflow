"""
FastAPI接口层 — 提供RESTful API供前端和外部系统调用

术语讲解：
- RESTful API：一种接口设计风格，用GET查、POST增、PUT改、DELETE删
- 路由（Route）：接口的URL路径
- 请求体（Request Body）：POST/PUT请求时传的数据
- 响应模型：接口返回数据的格式
- Swagger文档：FastAPI自动生成的接口文档，能在线测试
- CORS：跨域资源共享，允许前端页面调用后端接口
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..database.db import get_db
from ..database.crud import (
    ProductCRUD, VideoCRUD, CampaignCRUD, TaskCRUD, TriggerLogCRUD, ActionLogCRUD,
)
from ..workflow.triggers import WorkflowTriggers
from ..agent.agent import ReviewAgent
from ..config import get_config
from ..logger import setup_logging

# 初始化日志和配置
setup_logging()
config = get_config()
logger = logging.getLogger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title="AI电商自动化工作流系统",
    description="抖音电商选品→素材→投流→出单→复盘全流程自动化原型",
    version="1.0.0",
)

# 配置CORS（允许前端跨域调用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境允许所有来源，生产环境应限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局数据库实例
db = get_db(config.get("database.path", "data/ecommerce.db"))


# ============================================
# 请求/响应模型（Pydantic）
# ============================================

class ProductCreate(BaseModel):
    product_id: str = Field(..., description="商品ID")
    name: str = Field(..., description="商品名")
    category: str = Field("", description="类目")
    commission_rate: float = Field(0, description="佣金比例")
    owner: str = Field("", description="负责人")

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    commission_rate: Optional[float] = None
    status: Optional[str] = None
    stage: Optional[str] = None

class VideoCreate(BaseModel):
    video_id: str
    product_id: str
    source: str = ""
    file_path: str = ""

class OrderBackfill(BaseModel):
    video_id: str
    order_count: int
    cost: Optional[float] = None
    roi: Optional[float] = None

class CampaignBackfill(BaseModel):
    campaign_id: str
    cost: float
    order_count: int
    roi: float

class AgentMessage(BaseModel):
    message: str = Field(..., description="用户消息")

class ReviewWrite(BaseModel):
    task_id: str
    conclusion: str
    next_action: str

class APIResponse(BaseModel):
    success: bool = True
    message: str = ""
    data: Any = None


# ============================================
# 启动事件
# ============================================

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库"""
    from ..database.models import create_tables, insert_sample_data
    create_tables(db)
    insert_sample_data(db)
    logger.info("API服务启动，数据库已初始化")


# ============================================
# 商品接口
# ============================================

@app.get("/api/products", summary="获取商品列表")
async def get_products(status: Optional[str] = None, stage: Optional[str] = None,
                        limit: int = 100, offset: int = 0):
    product_crud = ProductCRUD(db)
    if status:
        data = product_crud.get_by_status(status)
    elif stage:
        data = product_crud.get_by_stage(stage)
    else:
        data = product_crud.get_all(limit, offset)
    return APIResponse(data=data, message=f"共{len(data)}条")

@app.get("/api/products/{product_id}", summary="获取商品详情")
async def get_product(product_id: str):
    product = ProductCRUD(db).get_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    return APIResponse(data=product)

@app.post("/api/products", summary="创建商品")
async def create_product(product: ProductCreate):
    crud = ProductCRUD(db)
    if crud.get_by_id(product.product_id):
        raise HTTPException(status_code=400, detail="商品ID已存在")
    success = crud.create(**product.dict())
    if not success:
        raise HTTPException(status_code=500, detail="创建失败")
    return APIResponse(message="创建成功", data=product.dict())

@app.put("/api/products/{product_id}", summary="更新商品")
async def update_product(product_id: str, update: ProductUpdate):
    crud = ProductCRUD(db)
    if not crud.get_by_id(product_id):
        raise HTTPException(status_code=404, detail="商品不存在")
    if update.status:
        crud.update_status(product_id, update.status)
    if update.stage:
        crud.update_stage(product_id, update.stage)
    if update.commission_rate is not None:
        crud.update_commission(product_id, update.commission_rate)
    return APIResponse(message="更新成功")

@app.post("/api/products/{product_id}/confirm", summary="确认商品（触发点A）")
async def confirm_product(product_id: str):
    """确认商品，触发点A：自动创建素材任务"""
    triggers = WorkflowTriggers(db)
    result = triggers.trigger_a_product_confirm(product_id)
    return APIResponse(success=result.get("success", False),
                       message=result.get("message", ""),
                       data=result)


# ============================================
# 视频接口
# ============================================

@app.get("/api/videos", summary="获取视频列表")
async def get_videos(product_id: Optional[str] = None, limit: int = 100):
    crud = VideoCRUD(db)
    if product_id:
        data = crud.get_by_product(product_id)
    else:
        data = crud.get_all(limit)
    return APIResponse(data=data, message=f"共{len(data)}条")

@app.get("/api/videos/{video_id}", summary="获取视频详情")
async def get_video(video_id: str):
    video = VideoCRUD(db).get_by_id(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")
    return APIResponse(data=video)

@app.post("/api/videos", summary="创建视频")
async def create_video(video: VideoCreate):
    crud = VideoCRUD(db)
    if crud.get_by_id(video.video_id):
        raise HTTPException(status_code=400, detail="视频ID已存在")
    success = crud.create(**video.dict())
    if not success:
        raise HTTPException(status_code=500, detail="创建失败")
    return APIResponse(message="创建成功")

@app.post("/api/videos/{video_id}/dedup-pass", summary="标记去重通过（触发点B）")
async def video_dedup_pass(video_id: str):
    """视频去重通过，触发点B：分流到前端发布或千川上传"""
    crud = VideoCRUD(db)
    video = crud.get_by_id(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")
    crud.update_dedup_status(video_id, "去重通过")
    triggers = WorkflowTriggers(db)
    result = triggers.trigger_b_dedup_complete(video_id)
    return APIResponse(success=result.get("success", False),
                       message=result.get("message", ""),
                       data=result)

@app.post("/api/videos/backfill-order", summary="回填视频订单（触发点C）")
async def backfill_video_order(backfill: OrderBackfill):
    """回填视频订单数，触发点C：出单时创建AI精剪任务"""
    crud = VideoCRUD(db)
    if not crud.get_by_id(backfill.video_id):
        raise HTTPException(status_code=404, detail="视频不存在")
    if backfill.cost is not None and backfill.roi is not None:
        crud.update_cost_and_roi(backfill.video_id, backfill.cost, backfill.roi)
    triggers = WorkflowTriggers(db)
    result = triggers.trigger_c_order_detected(backfill.video_id, backfill.order_count)
    return APIResponse(success=result.get("success", False),
                       message=result.get("message", ""),
                       data=result)


# ============================================
# 投流计划接口
# ============================================

@app.get("/api/campaigns", summary="获取投流计划列表")
async def get_campaigns(status: Optional[str] = None, product_id: Optional[str] = None):
    crud = CampaignCRUD(db)
    if status:
        data = crud.get_by_status(status)
    elif product_id:
        data = crud.get_by_product(product_id)
    else:
        data = crud.get_all()
    return APIResponse(data=data, message=f"共{len(data)}条")

@app.post("/api/campaigns/backfill", summary="回填投流数据")
async def backfill_campaign(backfill: CampaignBackfill):
    crud = CampaignCRUD(db)
    if not crud.get_by_id(backfill.campaign_id):
        raise HTTPException(status_code=404, detail="投流计划不存在")
    success = crud.backfill_data(backfill.campaign_id, backfill.cost,
                                  backfill.order_count, backfill.roi)
    return APIResponse(success=success, message="回填成功")

@app.post("/api/campaigns/check-stop-test", summary="停测检查（触发点E）")
async def check_stop_test(campaign_id: Optional[str] = None):
    """检查无效素材，触发点E：命中停测规则则创建停测任务"""
    triggers = WorkflowTriggers(db)
    result = triggers.trigger_e_stop_test_check(campaign_id)
    return APIResponse(data=result, message=f"检查了{len(result)}个计划")


# ============================================
# 任务接口
# ============================================

@app.get("/api/tasks", summary="获取任务列表")
async def get_tasks(status: Optional[str] = None, task_type: Optional[str] = None):
    crud = TaskCRUD(db)
    if status:
        data = crud.get_by_status(status)
    elif task_type:
        data = crud.get_by_type(task_type)
    else:
        data = crud.get_all()
    return APIResponse(data=data, message=f"共{len(data)}条")

@app.put("/api/tasks/{task_id}/status", summary="更新任务状态")
async def update_task_status(task_id: str, status: str):
    crud = TaskCRUD(db)
    if not crud.get_by_id(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    success = crud.update_status(task_id, status)
    return APIResponse(success=success, message="更新成功")

@app.post("/api/tasks/write-review", summary="写回复盘结论")
async def write_review(review: ReviewWrite):
    crud = TaskCRUD(db)
    if not crud.get_by_id(review.task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    success = crud.write_review(review.task_id, review.conclusion, review.next_action)
    return APIResponse(success=success, message="复盘结论已写回")


# ============================================
# 工作流接口
# ============================================

@app.post("/api/workflow/run-full-demo", summary="运行全流程演示")
async def run_full_demo():
    """运行全流程演示，验证3类结果：出单触发、百单/千单、无效素材"""
    triggers = WorkflowTriggers(db)
    result = triggers.run_full_workflow_demo()
    return APIResponse(data=result, message="全流程演示完成")

@app.post("/api/workflow/daily-review", summary="运行日/批次复盘（触发点F）")
async def daily_review():
    """触发点F：日/批次复盘"""
    triggers = WorkflowTriggers(db)
    result = triggers.trigger_f_daily_review()
    return APIResponse(success=result.get("success", False),
                       message=result.get("review_conclusion", ""),
                       data=result)

@app.post("/api/workflow/scaling-check/{product_id}", summary="放量分级检查（触发点D）")
async def scaling_check(product_id: str):
    """触发点D：检查商品是否达到百单/千单阈值"""
    triggers = WorkflowTriggers(db)
    result = triggers.trigger_d_scaling_tier(product_id)
    return APIResponse(success=result.get("success", False),
                       message=result.get("message", ""),
                       data=result)

@app.get("/api/workflow/trigger-logs", summary="获取触发记录")
async def get_trigger_logs(limit: int = 20):
    logs = TriggerLogCRUD(db).get_recent(limit)
    return APIResponse(data=logs)


# ============================================
# Agent接口
# ============================================

# 全局Agent实例
agent_instance = None

def get_agent():
    global agent_instance
    if agent_instance is None:
        agent_instance = ReviewAgent(db)
    return agent_instance

@app.post("/api/agent/chat", summary="和数智员工对话")
async def agent_chat(msg: AgentMessage):
    """和素材与投流复盘数智员工对话"""
    agent = get_agent()
    response = agent.chat(msg.message)
    return APIResponse(data={"response": response, "history": agent.get_conversation_history()})

@app.get("/api/agent/tools", summary="获取Agent可用工具")
async def agent_tools():
    agent = get_agent()
    return APIResponse(data=agent.get_available_tools())

@app.get("/api/agent/system-prompt", summary="获取Agent系统提示词")
async def agent_system_prompt():
    agent = get_agent()
    return APIResponse(data={"system_prompt": agent.get_system_prompt()})

@app.post("/api/agent/clear-history", summary="清空Agent对话历史")
async def agent_clear_history():
    agent = get_agent()
    agent.clear_history()
    return APIResponse(message="对话历史已清空")


# ============================================
# 系统接口
# ============================================

@app.get("/api/stats", summary="获取系统统计数据")
async def get_stats():
    """获取数据看板需要的统计数据"""
    product_crud = ProductCRUD(db)
    video_crud = VideoCRUD(db)
    campaign_crud = CampaignCRUD(db)
    task_crud = TaskCRUD(db)

    stats = {
        "total_products": product_crud.count(),
        "total_videos": video_crud.count(),
        "total_campaigns": campaign_crud.count(),
        "total_tasks": task_crud.count(),
        "pending_tasks": len(task_crud.get_by_status("待处理")),
        "ordered_videos": len(video_crud.get_ordered_videos()),
        "hundred_products": len(product_crud.get_by_stage("百单阶段")),
        "thousand_products": len(product_crud.get_by_stage("千单阶段")),
    }
    return APIResponse(data=stats)

@app.get("/", summary="健康检查")
async def root():
    return {"status": "running", "message": "AI电商自动化工作流系统", "docs": "/docs"}
