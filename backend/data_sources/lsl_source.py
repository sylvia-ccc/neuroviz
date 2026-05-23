"""
LSL (Lab Streaming Layer) 数据源 — 行业标准实时数据流
支持从任意LSL发射器接收EEG数据（OpenBCI, G.Tec, Muse等）
"""

import numpy as np
import time
from typing import Optional, List

try:
    import pylsl as lsl
    HAS_PYLSL = True
except ImportError:
    HAS_PYLSL = False


class LSLDataSource:
    """从LSL网络流接收EEG数据"""

    def __init__(self, fs_target: int = 500, stream_name: Optional[str] = None, 
                 stream_type: str = "EEG", timeout: float = 5.0):
        """
        Args:
            fs_target: 目标采样率（重采样用）
            stream_name: 流名称（None则自动发现第一个EEG流）
            stream_type: 流类型（默认"EEG"）
            timeout: 发现超时（秒）
        """
        if not HAS_PYLSL:
            raise RuntimeError("需要pylsl。请运行: pip install pylsl")

        self.fs_target = fs_target
        self.stream_name = stream_name
        self.stream_type = stream_type
        self.timeout = timeout

        self._inlet: Optional[lsl.StreamInlet] = None
        self._fs_original = fs_target
        self.n_channels = 0
        self.channel_names = []
        self._scene = "relax"
        self._connected = False

        self._connect()

    def _connect(self):
        """连接LSL流"""
        print(f"[LSLSource] 搜索{'"' + self.stream_name + '"' if self.stream_name else '任意'} {self.stream_type}流...")

        # 发现流（使用正确的API）
        streams = lsl.resolve_streams(wait_time=self.timeout)
        
        # 过滤类型和名称
        filtered = []
        for s in streams:
            if s.type() == self.stream_type:
                if self.stream_name is None or s.name() == self.stream_name:
                    filtered.append(s)
        
        if not filtered:
            available = [f"{s.name()} ({s.type()})" for s in streams]
            raise RuntimeError(f"未找到类型为'{self.stream_type}'的LSL流，可用: {available}")

        # 选择流
        target_stream = filtered[0]

        # 创建inlet（使用正确的API）
        self._inlet = lsl.StreamInlet(target_stream)
        self._fs_original = int(target_stream.nominal_srate())
        self.n_channels = target_stream.channel_count()
        self.channel_names = [f"Ch{i}" for i in range(self.n_channels)]
        self._connected = True

        print(f"[LSLSource] 已连接: {target_stream.name()}")
        print(f"  通道数: {self.n_channels}, 采样率: {self._fs_original}Hz")

    @property
    def fs(self):
        return self.fs_target

    def set_scene(self, scene: str):
        self._scene = scene

    def read_frame(self, n_samples: int = 256) -> dict:
        """读取一帧数据（阻塞直到足够数据）"""
        if not self._connected or self._inlet is None:
            raise RuntimeError("LSL流未连接")

        # 拉取数据
        samples_needed = n_samples
        raw_chunks = []

        while len(raw_chunks) < samples_needed:
            chunk, timestamps = self._inlet.pull_chunk(
                max_samples=samples_needed - len(raw_chunks),
                timeout=1.0
            )
            if chunk:
                raw_chunks.extend(chunk)

        # 转换为numpy
        raw = np.array(raw_chunks[:n_samples], dtype=np.float32).T  # (n_channels, n_samples)

        # 重采样（如果需要）
        if self._fs_original != self.fs_target:
            raw = self._resample(raw, self._fs_original, self.fs_target)

        # 时间轴
        t = np.arange(n_samples) / self.fs_target

        return {
            "channels": self.channel_names,
            "raw": raw,
            "ch1": raw[0] if self.n_channels > 0 else np.zeros(n_samples),
            "ch2": raw[1] if self.n_channels > 1 else (raw[0] if self.n_channels > 0 else np.zeros(n_samples)),
            "scene": self._scene,
            "t": t,
            "lsl_source": self.stream_name or "auto",
        }

    def _resample(self, data: np.ndarray, fs_from: int, fs_to: int) -> np.ndarray:
        from scipy import signal
        n_target = int(data.shape[1] * fs_to / fs_from)
        resampled = np.zeros((data.shape[0], n_target))
        for ch in range(data.shape[0]):
            resampled[ch] = signal.resample(data[ch], n_target)
        return resampled

    def get_info(self) -> dict:
        return {
            "n_channels": self.n_channels,
            "channel_names": self.channel_names,
            "fs": self.fs_target,
            "connected": self._connected,
            "stream_name": self.stream_name,
            "stream_type": self.stream_type,
        }

    def close(self):
        """关闭LSL连接"""
        if self._inlet:
            self._inlet.close_stream()
            self._connected = False
            print("[LSLSource] 连接已关闭")


def list_lsl_streams(wait_time: float = 2.0) -> List[dict]:
    """列出当前网络上可用的LSL流（使用正确的API）"""
    if not HAS_PYLSL:
        print("需要pylsl: pip install pylsl")
        return []

    streams = lsl.resolve_streams(wait_time=wait_time)
    result = []
    for s in streams:
        result.append({
            "name": s.name(),
            "type": s.type(),
            "channel_count": s.channel_count(),
            "nominal_srate": s.nominal_srate(),
            "source_id": s.source_id(),
        })
    return result
