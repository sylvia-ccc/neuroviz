"""
NeuroViz 范式设计器
支持MI/P300/SSVEP等BCI实验范式的自动控制

功能:
- Trial时序控制（提示→等待→刺激→响应→休息）
- 刺激呈现事件推送
- 自动Marker标记
- 实时反馈接口
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Callable, Any
from enum import Enum
import json


class ParadigmType(Enum):
    """范式类型"""
    MI = "motor_imagery"       # 运动想象
    P300 = "p300"              # P300
    SSVEP = "ssvep"            # SSVEP
    NEUROFEEDBACK = "neurofeedback"  # 神经反馈
    CUSTOM = "custom"          # 自定义


class TrialPhase(Enum):
    """Trial阶段"""
    IDLE = "idle"
    CUE = "cue"                # 提示
    WAIT = "wait"              # 等待
    STIMULUS = "stimulus"      # 刺激/想象
    RESPONSE = "response"      # 响应窗口
    REST = "rest"              # 休息
    ENDED = "ended"


@dataclass
class TrialConfig:
    """Trial配置"""
    cue_duration: float = 1.0          # 提示时长（秒）
    wait_duration: float = 1.0         # 等待时长
    stimulus_duration: float = 4.0     # 刺激/想象时长
    response_window: float = 1.0       # 响应窗口
    rest_duration: float = 2.0         # 休息时长
    isi: float = 0.5                   # 刺激间隔
    randomize: bool = True             # 随机化Trial顺序


@dataclass
class ParadigmConfig:
    """范式配置"""
    paradigm_type: ParadigmType
    trial_config: TrialConfig
    n_trials: int = 40
    n_blocks: int = 4
    classes: List[str] = field(default_factory=lambda: ["left", "right"])
    instructions: str = ""
    
    # SSVEP特有参数
    ssvep_frequencies: List[float] = field(default_factory=lambda: [8.0, 10.0, 12.0, 15.0])
    
    # P300特有参数
    p300_matrix_rows: int = 6
    p300_matrix_cols: int = 6
    p300_flash_duration: float = 0.1
    p300_n_repetitions: int = 10


@dataclass
class TrialState:
    """Trial状态"""
    trial_num: int
    phase: TrialPhase
    target_class: str
    start_time: float
    phase_start_time: float
    response: Optional[str] = None
    correct: Optional[bool] = None
    rt_ms: Optional[float] = None
    prediction: Optional[str] = None
    confidence: Optional[float] = None


class ParadigmController:
    """
    范式控制器
    
    示例:
        config = ParadigmConfig(
            paradigm_type=ParadigmType.MI,
            classes=["left", "right"],
            n_trials=40
        )
        
        controller = ParadigmController(config)
        controller.on_phase_change(callback)
        controller.start()
    """
    
    def __init__(self, config: ParadigmConfig):
        self.config = config
        self.state: Optional[TrialState] = None
        self.current_trial = 0
        self.current_block = 0
        
        self._running = False
        self._paused = False
        self._task: Optional[asyncio.Task] = None
        
        self._phase_callbacks: List[Callable] = []
        self._trial_callbacks: List[Callable] = []
        self._end_callbacks: List[Callable] = []
        
        # Trial序列
        self._trial_sequence: List[str] = []
        self._generate_trial_sequence()
    
    def _generate_trial_sequence(self):
        """生成Trial序列"""
        import random
        
        trials_per_class = self.config.n_trials // len(self.config.classes)
        sequence = []
        
        for cls in self.config.classes:
            sequence.extend([cls] * trials_per_class)
        
        # 补齐
        while len(sequence) < self.config.n_trials:
            sequence.append(random.choice(self.config.classes))
        
        if self.config.trial_config.randomize:
            random.shuffle(sequence)
        
        self._trial_sequence = sequence
    
    def on_phase_change(self, callback: Callable[[TrialState], None]):
        """注册阶段变化回调"""
        self._phase_callbacks.append(callback)
    
    def on_trial_end(self, callback: Callable[[TrialState], None]):
        """注册Trial结束回调"""
        self._trial_callbacks.append(callback)
    
    def on_paradigm_end(self, callback: Callable[[Dict], None]):
        """注册范式结束回调"""
        self._end_callbacks.append(callback)
    
    async def _emit_phase_change(self, state: TrialState):
        """触发阶段变化事件"""
        event = {
            "type": "phase_change",
            "trial_num": state.trial_num,
            "phase": state.phase.value,
            "target_class": state.target_class,
            "timestamp": time.time(),
            "phase_start_time": state.phase_start_time
        }
        
        for callback in self._phase_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(state, event)
                else:
                    callback(state, event)
            except Exception as e:
                print(f"[Paradigm] Callback error: {e}")
    
    async def _run_trial(self, trial_num: int, target_class: str):
        """运行单个Trial"""
        config = self.config.trial_config
        
        # 初始化Trial状态
        self.state = TrialState(
            trial_num=trial_num,
            phase=TrialPhase.CUE,
            target_class=target_class,
            start_time=time.time(),
            phase_start_time=time.time()
        )
        
        # Phase 1: CUE (提示)
        await self._emit_phase_change(self.state)
        await asyncio.sleep(config.cue_duration)
        
        # Phase 2: WAIT (等待)
        self.state.phase = TrialPhase.WAIT
        self.state.phase_start_time = time.time()
        await self._emit_phase_change(self.state)
        await asyncio.sleep(config.wait_duration)
        
        # Phase 3: STIMULUS (刺激/想象)
        self.state.phase = TrialPhase.STIMULUS
        self.state.phase_start_time = time.time()
        await self._emit_phase_change(self.state)
        await asyncio.sleep(config.stimulus_duration)
        
        # Phase 4: RESPONSE (响应窗口)
        self.state.phase = TrialPhase.RESPONSE
        self.state.phase_start_time = time.time()
        await self._emit_phase_change(self.state)
        await asyncio.sleep(config.response_window)
        
        # Phase 5: REST (休息)
        self.state.phase = TrialPhase.REST
        self.state.phase_start_time = time.time()
        await self._emit_phase_change(self.state)
        await asyncio.sleep(config.rest_duration)
        
        # Trial结束
        self.state.phase = TrialPhase.ENDED
        
        for callback in self._trial_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(self.state)
                else:
                    callback(self.state)
            except Exception as e:
                print(f"[Paradigm] Trial callback error: {e}")
    
    async def run(self):
        """运行范式"""
        self._running = True
        self.current_trial = 0
        
        # 范式开始事件
        start_event = {
            "type": "paradigm_start",
            "paradigm": self.config.paradigm_type.value,
            "n_trials": self.config.n_trials,
            "classes": self.config.classes,
            "timestamp": time.time()
        }
        
        for callback in self._phase_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(None, start_event)
                else:
                    callback(None, start_event)
            except:
                pass
        
        # 运行所有Trial
        for i, target_class in enumerate(self._trial_sequence):
            if not self._running:
                break
            
            while self._paused:
                await asyncio.sleep(0.1)
            
            self.current_trial = i + 1
            await self._run_trial(self.current_trial, target_class)
        
        # 范式结束
        end_event = {
            "type": "paradigm_end",
            "n_completed": self.current_trial,
            "timestamp": time.time()
        }
        
        for callback in self._end_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(end_event)
                else:
                    callback(end_event)
            except:
                pass
        
        self._running = False
    
    def start(self):
        """启动范式（异步）"""
        if self._running:
            return
        
        self._task = asyncio.create_task(self.run())
    
    def stop(self):
        """停止范式"""
        self._running = False
        if self._task:
            self._task.cancel()
    
    def pause(self):
        """暂停"""
        self._paused = True
    
    def resume(self):
        """继续"""
        self._paused = False
    
    def record_response(self, response: str, rt_ms: float = 0):
        """记录响应"""
        if self.state:
            self.state.response = response
            self.state.rt_ms = rt_ms
            self.state.correct = (response == self.state.target_class)
    
    def record_prediction(self, prediction: str, confidence: float):
        """记录预测结果"""
        if self.state:
            self.state.prediction = prediction
            self.state.confidence = confidence


# ===== 预设范式 =====

def create_mi_paradigm(n_trials: int = 40, classes: List[str] = None) -> ParadigmConfig:
    """创建MI范式配置"""
    classes = classes or ["left", "right"]
    
    return ParadigmConfig(
        paradigm_type=ParadigmType.MI,
        trial_config=TrialConfig(
            cue_duration=1.0,
            wait_duration=1.0,
            stimulus_duration=4.0,  # 4秒想象
            response_window=1.0,
            rest_duration=2.0,
            randomize=True
        ),
        n_trials=n_trials,
        n_blocks=4,
        classes=classes,
        instructions="想象左/右手运动"
    )


def create_p300_paradigm(n_trials: int = 100) -> ParadigmConfig:
    """创建P300范式配置"""
    return ParadigmConfig(
        paradigm_type=ParadigmType.P300,
        trial_config=TrialConfig(
            cue_duration=0.5,
            wait_duration=0.0,
            stimulus_duration=0.1,  # 100ms闪烁
            response_window=2.0,
            rest_duration=0.5,
            randomize=False
        ),
        n_trials=n_trials,
        classes=["target", "non-target"],
        p300_matrix_rows=6,
        p300_matrix_cols=6,
        p300_flash_duration=0.1,
        p300_n_repetitions=10
    )


def create_ssvep_paradigm(frequencies: List[float] = None) -> ParadigmConfig:
    """创建SSVEP范式配置"""
    frequencies = frequencies or [8.0, 10.0, 12.0, 15.0]
    
    return ParadigmConfig(
        paradigm_type=ParadigmType.SSVEP,
        trial_config=TrialConfig(
            cue_duration=1.0,
            wait_duration=0.5,
            stimulus_duration=5.0,  # 5秒注视
            response_window=0.0,
            rest_duration=2.0,
            randomize=True
        ),
        n_trials=len(frequencies) * 10,
        classes=[f"{f}Hz" for f in frequencies],
        ssvep_frequencies=frequencies
    )


def create_neurofeedback_paradigm(n_trials: int = 20) -> ParadigmConfig:
    """创建神经反馈范式配置"""
    return ParadigmConfig(
        paradigm_type=ParadigmType.NEUROFEEDBACK,
        trial_config=TrialConfig(
            cue_duration=1.0,
            wait_duration=0.0,
            stimulus_duration=30.0,  # 30秒训练
            response_window=0.0,
            rest_duration=5.0,
            randomize=False
        ),
        n_trials=n_trials,
        classes=["train"],
        instructions="调节脑波达到目标状态"
    )
