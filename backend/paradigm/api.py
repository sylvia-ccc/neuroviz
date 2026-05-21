"""
范式设计器API端点
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import asyncio

from .controller import (
    ParadigmController, ParadigmConfig, TrialConfig,
    ParadigmType, TrialPhase, TrialState,
    create_mi_paradigm, create_p300_paradigm, 
    create_ssvep_paradigm, create_neurofeedback_paradigm
)


router = APIRouter(prefix="/api/paradigm", tags=["paradigm"])

# 全局范式控制器
paradigm_controller: Optional[ParadigmController] = None

# WebSocket客户端列表（由app.py设置）
ws_clients: List = []


def set_ws_clients(clients):
    """设置WebSocket客户端列表"""
    global ws_clients
    ws_clients = clients


class StartParadigmRequest(BaseModel):
    paradigm_type: str = "mi"  # mi/p300/ssvep/neurofeedback
    n_trials: int = 40
    classes: List[str] = ["left", "right"]
    
    # Trial配置
    cue_duration: float = 1.0
    wait_duration: float = 1.0
    stimulus_duration: float = 4.0
    response_window: float = 1.0
    rest_duration: float = 2.0
    randomize: bool = True


class RecordResponseRequest(BaseModel):
    response: str
    rt_ms: float = 0


class RecordPredictionRequest(BaseModel):
    prediction: str
    confidence: float


@router.get("/presets")
async def get_paradigm_presets():
    """获取预设范式"""
    return {
        "presets": [
            {
                "name": "MI - Motor Imagery",
                "type": "mi",
                "description": "运动想象范式，想象左/右手运动",
                "default_config": {
                    "n_trials": 40,
                    "classes": ["left", "right"],
                    "cue_duration": 1.0,
                    "stimulus_duration": 4.0,
                    "rest_duration": 2.0
                }
            },
            {
                "name": "P300 - Speller",
                "type": "p300",
                "description": "P300拼写器范式，行列闪烁",
                "default_config": {
                    "n_trials": 100,
                    "matrix_size": "6x6",
                    "flash_duration": 0.1
                }
            },
            {
                "name": "SSVEP - Frequency Target",
                "type": "ssvep",
                "description": "SSVEP范式，注视不同频率目标",
                "default_config": {
                    "frequencies": [8.0, 10.0, 12.0, 15.0],
                    "stimulus_duration": 5.0
                }
            },
            {
                "name": "Neurofeedback",
                "type": "neurofeedback",
                "description": "神经反馈训练，实时调节脑波",
                "default_config": {
                    "n_trials": 20,
                    "stimulus_duration": 30.0
                }
            }
        ]
    }


@router.post("/start")
async def start_paradigm(req: StartParadigmRequest):
    """启动范式"""
    global paradigm_controller
    
    # 创建范式配置
    if req.paradigm_type == "mi":
        config = create_mi_paradigm(req.n_trials, req.classes)
    elif req.paradigm_type == "p300":
        config = create_p300_paradigm(req.n_trials)
    elif req.paradigm_type == "ssvep":
        config = create_ssvep_paradigm()
    elif req.paradigm_type == "neurofeedback":
        config = create_neurofeedback_paradigm(req.n_trials)
    else:
        raise HTTPException(400, f"Unknown paradigm type: {req.paradigm_type}")
    
    # 应用自定义Trial配置
    config.trial_config = TrialConfig(
        cue_duration=req.cue_duration,
        wait_duration=req.wait_duration,
        stimulus_duration=req.stimulus_duration,
        response_window=req.response_window,
        rest_duration=req.rest_duration,
        randomize=req.randomize
    )
    
    # 创建控制器
    paradigm_controller = ParadigmController(config)
    
    # 注册回调（推送WebSocket事件）
    async def on_phase_change(state, event):
        # 推送给所有WebSocket客户端
        import json
        for ws in ws_clients:
            try:
                await ws.send_json({
                    "type": "paradigm_event",
                    "event": event
                })
            except:
                pass
    
    paradigm_controller.on_phase_change(on_phase_change)
    
    # 启动
    paradigm_controller.start()
    
    return {
        "status": "started",
        "paradigm": req.paradigm_type,
        "n_trials": req.n_trials,
        "classes": req.classes
    }


@router.post("/stop")
async def stop_paradigm():
    """停止范式"""
    global paradigm_controller
    
    if paradigm_controller:
        paradigm_controller.stop()
        paradigm_controller = None
        return {"status": "stopped"}
    
    return {"status": "not_running"}


@router.post("/pause")
async def pause_paradigm():
    """暂停范式"""
    if paradigm_controller:
        paradigm_controller.pause()
        return {"status": "paused"}
    return {"status": "not_running"}


@router.post("/resume")
async def resume_paradigm():
    """继续范式"""
    if paradigm_controller:
        paradigm_controller.resume()
        return {"status": "resumed"}
    return {"status": "not_running"}


@router.get("/status")
async def get_paradigm_status():
    """获取范式状态"""
    if not paradigm_controller:
        return {
            "running": False,
            "state": None
        }
    
    state = paradigm_controller.state
    return {
        "running": paradigm_controller._running,
        "paused": paradigm_controller._paused,
        "current_trial": paradigm_controller.current_trial,
        "total_trials": paradigm_controller.config.n_trials,
        "state": {
            "trial_num": state.trial_num if state else None,
            "phase": state.phase.value if state else None,
            "target_class": state.target_class if state else None,
            "response": state.response if state else None,
            "correct": state.correct if state else None,
            "prediction": state.prediction if state else None
        } if state else None
    }


@router.post("/response")
async def record_response(req: RecordResponseRequest):
    """记录响应"""
    if paradigm_controller and paradigm_controller.state:
        paradigm_controller.record_response(req.response, req.rt_ms)
        return {
            "status": "ok",
            "correct": paradigm_controller.state.correct
        }
    return {"error": "No active trial"}


@router.post("/prediction")
async def record_prediction(req: RecordPredictionRequest):
    """记录预测结果"""
    if paradigm_controller and paradigm_controller.state:
        paradigm_controller.record_prediction(req.prediction, req.confidence)
        return {"status": "ok"}
    return {"error": "No active trial"}


@router.get("/results")
async def get_paradigm_results():
    """获取实验结果"""
    if not paradigm_controller:
        return {"error": "No paradigm running"}
    
    # TODO: 收集所有Trial结果
    return {
        "n_completed": paradigm_controller.current_trial,
        "n_total": paradigm_controller.config.n_trials
    }
