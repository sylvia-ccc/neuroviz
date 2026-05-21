"""
事件Marker系统 — Trial同步与事件标注
支持手动/自动/LSL事件，用于BCI实验和数据分析
"""

import time
from typing import Optional, List, Dict
from dataclasses import dataclass, field, asdict
from datetime import datetime
import json


@dataclass
class Marker:
    """单个事件Marker"""
    timestamp: float  # Unix时间戳（秒）
    name: str         # 事件名称（如 "trial_start", "stimulus", "response"）
    value: int = 0    # 数值（如trial编号）
    duration: float = 0.0  # 事件持续时间（秒）
    metadata: dict = field(default_factory=dict)  # 额外元数据
    
    def to_dict(self):
        return asdict(self)


class MarkerManager:
    """Marker管理器 — 收集/存储/导出事件标记"""
    
    def __init__(self, max_markers: int = 10000):
        self.max_markers = max_markers
        self.markers: List[Marker] = []
        self._session_start = time.time()
        self._trial_counter = 0
        self._current_trial: Optional[dict] = None
    
    def add_marker(self, name: str, value: int = 0, duration: float = 0.0, 
                   metadata: Optional[dict] = None) -> Marker:
        """添加Marker"""
        marker = Marker(
            timestamp=time.time(),
            name=name,
            value=value,
            duration=duration,
            metadata=metadata or {}
        )
        self.markers.append(marker)
        
        # 限制数量
        if len(self.markers) > self.max_markers:
            self.markers = self.markers[-self.max_markers:]
        
        return marker
    
    def start_trial(self, trial_type: str = "", metadata: Optional[dict] = None) -> int:
        """开始新Trial"""
        self._trial_counter += 1
        self._current_trial = {
            "trial_num": self._trial_counter,
            "trial_type": trial_type,
            "start_time": time.time()
        }
        
        self.add_marker(
            name="trial_start",
            value=self._trial_counter,
            metadata={"trial_type": trial_type, **(metadata or {})}
        )
        
        return self._trial_counter
    
    def end_trial(self, result: str = "", metadata: Optional[dict] = None) -> Optional[dict]:
        """结束当前Trial"""
        if not self._current_trial:
            return None
        
        duration = time.time() - self._current_trial["start_time"]
        
        self.add_marker(
            name="trial_end",
            value=self._current_trial["trial_num"],
            duration=duration,
            metadata={"result": result, **(metadata or {})}
        )
        
        trial_info = {
            **self._current_trial,
            "duration": duration,
            "result": result
        }
        self._current_trial = None
        
        return trial_info
    
    def mark_stimulus(self, stimulus_type: str, value: int = 0) -> Marker:
        """标记刺激呈现"""
        return self.add_marker(
            name="stimulus",
            value=value,
            metadata={"stimulus_type": stimulus_type}
        )
    
    def mark_response(self, response: str, correct: bool = False, rt_ms: float = 0) -> Marker:
        """标记被试响应"""
        return self.add_marker(
            name="response",
            metadata={"response": response, "correct": correct, "rt_ms": rt_ms}
        )
    
    def get_markers_since(self, timestamp: float) -> List[dict]:
        """获取指定时间后的所有Marker"""
        return [m.to_dict() for m in self.markers if m.timestamp > timestamp]
    
    def get_recent_markers(self, n: int = 50) -> List[dict]:
        """获取最近n个Marker"""
        return [m.to_dict() for m in self.markers[-n:]]
    
    def get_trials(self) -> List[dict]:
        """提取所有Trial信息"""
        trials = []
        current_trial = None
        
        for m in self.markers:
            if m.name == "trial_start":
                current_trial = {
                    "trial_num": m.value,
                    "trial_type": m.metadata.get("trial_type", ""),
                    "start_time": m.timestamp,
                    "stimuli": [],
                    "responses": []
                }
            elif m.name == "stimulus" and current_trial:
                current_trial["stimuli"].append({
                    "type": m.metadata.get("stimulus_type", ""),
                    "value": m.value,
                    "time": m.timestamp
                })
            elif m.name == "response" and current_trial:
                current_trial["responses"].append({
                    "response": m.metadata.get("response", ""),
                    "correct": m.metadata.get("correct", False),
                    "rt_ms": m.metadata.get("rt_ms", 0),
                    "time": m.timestamp
                })
            elif m.name == "trial_end" and current_trial:
                current_trial["end_time"] = m.timestamp
                current_trial["duration"] = m.duration
                current_trial["result"] = m.metadata.get("result", "")
                trials.append(current_trial)
                current_trial = None
        
        return trials
    
    def export_to_dict(self) -> dict:
        """导出所有Marker数据"""
        return {
            "session_start": self._session_start,
            "total_markers": len(self.markers),
            "total_trials": self._trial_counter,
            "markers": [m.to_dict() for m in self.markers],
            "trials": self.get_trials()
        }
    
    def export_to_json(self) -> str:
        """导出为JSON字符串"""
        return json.dumps(self.export_to_dict(), indent=2)
    
    def export_to_csv_rows(self) -> List[str]:
        """导出为CSV行（用于BIDS events.tsv格式）"""
        rows = ["onset\tduration\ttrial_type\tvalue\tstim_file"]
        
        session_start = self._session_start
        for m in self.markers:
            onset = m.timestamp - session_start
            row = f"{onset:.3f}\t{m.duration}\t{m.name}\t{m.value}\t"
            rows.append(row)
        
        return rows
    
    def clear(self):
        """清空所有Marker"""
        self.markers = []
        self._trial_counter = 0
        self._current_trial = None
        self._session_start = time.time()


# 全局Marker管理器
marker_manager = MarkerManager()


# ===== LSL Marker支持 =====

class LSLMarkerReceiver:
    """从LSL Marker流接收事件"""
    
    def __init__(self, marker_manager: MarkerManager):
        self.marker_manager = marker_manager
        self._inlet = None
        self._running = False
        
    def connect(self, stream_name: str = None, timeout: float = 2.0):
        """连接LSL Marker流"""
        try:
            from pylsl import resolve_stream, StreamInlet
            
            streams = resolve_stream("type", "Markers", timeout=timeout)
            if not streams:
                return False
            
            self._inlet = StreamInlet(streams[0])
            self._running = True
            print(f"[LSLMarker] Connected to {streams[0].name()}")
            return True
        except Exception as e:
            print(f"[LSLMarker] Connection failed: {e}")
            return False
    
    def poll(self) -> List[dict]:
        """轮询新Marker"""
        if not self._inlet or not self._running:
            return []
        
        markers = []
        try:
            chunk, timestamps = self._inlet.pull_chunk(timeout=0.0)
            for sample, ts in zip(chunk or [], timestamps or []):
                marker_name = str(sample[0]) if sample else "unknown"
                marker = self.marker_manager.add_marker(name=marker_name)
                markers.append(marker.to_dict())
        except Exception as e:
            print(f"[LSLMarker] Poll error: {e}")
        
        return markers
    
    def disconnect(self):
        """断开连接"""
        self._running = False
        if self._inlet:
            self._inlet.close_stream()
            self._inlet = None
