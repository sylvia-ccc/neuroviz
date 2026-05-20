"""
EDF/EDF+ 文件数据源
读取EDF文件，模拟实时播放（按帧读取）
"""

import numpy as np
import pyedflib


class EDFSource:
    """
    从EDF文件读取EEG数据，支持按帧播放（模拟实时）
    """

    def __init__(self, file_path: str, fs: int = 500):
        self.file_path = file_path
        self.target_fs = fs
        self._load_edf()
        print(f"[EDFSource] 加载: {file_path}")
        print(f"  通道数: {self.n_channels}")
        print(f"  采样率: {self.actual_fs} Hz")
        print(f"  时长: {self.total_samples / self.actual_fs:.1f} 秒")

    def _load_edf(self):
        """读取EDF文件头 + 全部数据到内存"""
        with pyedflib.EdfReader(self.file_path) as reader:
            self.n_channels = reader.n_sig
            # 取第一个信号的采样率（EDF通常所有信号同采样率）
            self.actual_fs = reader.get_sample_frequency(0)
            self.channel_names = [
                reader.get_signal_label(i) for i in range(self.n_channels)
            ]
            self.total_samples = reader.get_nsamples()[0]

            # 读取全部数据到内存 (n_channels, total_samples)
            self._data = np.zeros(
                (self.n_channels, self.total_samples),
                dtype=np.float32
            )
            for ch in range(self.n_channels):
                self._data[ch] = reader.read_signal(ch).astype(np.float32)

        self._playback_pos = 0  # 播放位置（样本数）

    def set_scene(self, scene: str):
        """EDF文件不支持场景切换（留空保持接口兼容）"""
        pass

    def read_frame(self, n_samples: int = 256) -> dict:
        """
        读取一帧（模拟实时播放）
        返回格式与 MockDataSource 一致
        """
        fs = self.actual_fs
        start = self._playback_pos
        end = min(start + n_samples, self.total_samples)

        if start >= self.total_samples:
            # 循环播放
            self._playback_pos = 0
            start = 0
            end = min(n_samples, self.total_samples)

        n = end - start
        if n < n_samples:
            # 末尾不够一帧，循环从头补
            chunk = np.zeros((self.n_channels, n_samples), dtype=np.float32)
            chunk[:, :n] = self._data[:, start:end]
            # 从头部补
            rem = n_samples - n
            chunk[:, n:] = self._data[:, :rem]
            self._playback_pos = rem
            raw = chunk
        else:
            raw = self._data[:, start:end].copy()
            self._playback_pos = end

        # 时间轴（相对时间，秒）
        t = (start / fs) + np.arange(n_samples) / fs

        return {
            "channels": self.channel_names,
            "raw": raw,
            "ch1": raw[0] if self.n_channels > 0 else np.zeros(n_samples),
            "ch2": raw[1] if self.n_channels > 1 else (raw[0] if self.n_channels > 0 else np.zeros(n_samples)),
            "scene": "file_playback",
            "t": t,
            "file_path": self.file_path,
            "playback_pos": self._playback_pos,
            "total_samples": self.total_samples,
        }

    def get_info(self) -> dict:
        """返回文件信息（供前端显示）"""
        return {
            "n_channels": self.n_channels,
            "channel_names": self.channel_names,
            "fs": self.actual_fs,
            "duration_sec": self.total_samples / self.actual_fs,
            "total_samples": self.total_samples,
        }
