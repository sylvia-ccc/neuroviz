"""
文件数据源 — EDF/BDF/GDF/BrainVision/CSV回放
支持EDF/BDF(优先pyedflib)、GDF、BrainVision(.vhdr)、CSV格式
"""

import asyncio
import numpy as np
import os
from pathlib import Path

try:
    import pyedflib
    HAS_PYEDFLIB = True
except ImportError:
    HAS_PYEDFLIB = False

try:
    import mne
    HAS_MNE = True
except ImportError:
    HAS_MNE = False


class FileDataSource:
    """从EDF/CSV文件读取数据，模拟实时流"""

    def __init__(self, filepath: str, fs_target: int = 500, buffer_sec: float = 1.0):
        self.filepath = filepath
        self.fs_target = fs_target
        self.buffer_samples = int(fs_target * buffer_sec)
        self._ptr = 0
        self._data = None  # (n_channels, n_samples)
        self._fs_original = fs_target
        self.n_channels = 0
        self.channel_names = []
        self._scene = "relax"
        self._total_samples = 0

        self._load_file(filepath)
        print(f"[FileDataSource] 加载: {Path(filepath).name}")
        print(f"  通道数: {self.n_channels}, 原始fs={self._fs_original}Hz, 总时长={self._total_samples/self._fs_original:.1f}s")

    def _load_file(self, filepath: str):
        ext = os.path.splitext(filepath)[1].lower()
        if ext in (".edf", ".bdf"):
            self._load_edf(filepath)  # EDF/BDF统一处理
        elif ext == ".gdf":
            self._load_gdf(filepath)
        elif ext == ".vhdr":
            self._load_brainvision(filepath)
        elif ext == ".csv":
            self._load_csv(filepath)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")

    def _load_edf(self, filepath: str):
        """读取EDF文件，优先pyedflib，失败则尝试mne"""
        if HAS_PYEDFLIB:
            try:
                self._load_edf_pyedflib(filepath)
                return
            except Exception as e:
                print(f"[FileDataSource] pyedflib读取失败，尝试mne: {e}")
        
        if HAS_MNE:
            self._load_edf_mne(filepath)
        else:
            raise RuntimeError("需要pyedflib或mne才能读取EDF。请运行: pip install pyedflib")

    def _load_edf_pyedflib(self, filepath: str):
        """使用pyedflib读取EDF（轻量、兼容性好）"""
        with pyedflib.EdfReader(filepath) as reader:
            self.n_channels = reader.n_sig
            # 取第一个信号的采样率（EDF通常所有信号同采样率）
            self._fs_original = reader.get_sample_frequency(0)
            self.channel_names = [
                reader.get_signal_label(i) for i in range(self.n_channels)
            ]
            # 读取全部数据到内存
            n_samples = reader.get_nsamples()[0]
            self._data = np.zeros((self.n_channels, n_samples), dtype=np.float32)
            for ch in range(self.n_channels):
                self._data[ch] = reader.read_signal(ch).astype(np.float32)
            self._total_samples = n_samples
        
        # 重采样到fs_target
        if self._fs_original != self.fs_target:
            print(f"[FileDataSource] 重采样: {self._fs_original}Hz → {self.fs_target}Hz")
            self._data = self._resample(self._data, self._fs_original, self.fs_target)
            self._total_samples = self._data.shape[1]
        
        print(f"[FileDataSource] pyedflib读取成功: {self.n_channels}通道, {self._total_samples}样本")

    def _load_edf_mne(self, filepath: str):
        """使用mne读取EDF（后备方案）"""
        raw = mne.io.read_raw_edf(filepath, preload=True, verbose=False)
        self._fs_original = int(raw.info["sfreq"])
        self._data = raw.get_data()  # (n_channels, n_samples)
        self.n_channels = self._data.shape[0]
        self.channel_names = raw.ch_names[:self.n_channels]
        self._total_samples = self._data.shape[1]
        
        # 重采样到fs_target
        if self._fs_original != self.fs_target:
            print(f"[FileDataSource] 重采样: {self._fs_original}Hz → {self.fs_target}Hz")
            self._data = self._resample(self._data, self._fs_original, self.fs_target)
            self._total_samples = self._data.shape[1]

    def _load_gdf(self, filepath: str):
        """读取GDF文件 (使用mne)"""
        if not HAS_MNE:
            raise RuntimeError("需要mne才能读取GDF。请运行: pip install mne")
        
        raw = mne.io.read_raw_gdf(filepath, preload=True, verbose=False)
        self._fs_original = int(raw.info["sfreq"])
        self._data = raw.get_data()
        self.n_channels = self._data.shape[0]
        self.channel_names = raw.ch_names[:self.n_channels]
        self._total_samples = self._data.shape[1]
        
        if self._fs_original != self.fs_target:
            print(f"[FileDataSource] 重采样: {self._fs_original}Hz → {self.fs_target}Hz")
            self._data = self._resample(self._data, self._fs_original, self.fs_target)
            self._total_samples = self._data.shape[1]
        
        print(f"[FileDataSource] GDF读取成功: {self.n_channels}通道, {self._total_samples}样本")

    def _load_brainvision(self, filepath: str):
        """读取BrainVision文件 (.vhdr + .vmrk + .eeg)"""
        if not HAS_MNE:
            raise RuntimeError("需要mne才能读取BrainVision。请运行: pip install mne")
        
        # BrainVision主文件是.vhdr，mne会自动关联.vmrk和.eeg
        raw = mne.io.read_raw_brainvision(filepath, preload=True, verbose=False)
        self._fs_original = int(raw.info["sfreq"])
        self._data = raw.get_data()
        self.n_channels = self._data.shape[0]
        self.channel_names = raw.ch_names[:self.n_channels]
        self._total_samples = self._data.shape[1]
        
        if self._fs_original != self.fs_target:
            print(f"[FileDataSource] 重采样: {self._fs_original}Hz → {self.fs_target}Hz")
            self._data = self._resample(self._data, self._fs_original, self.fs_target)
            self._total_samples = self._data.shape[1]
        
        print(f"[FileDataSource] BrainVision读取成功: {self.n_channels}通道, {self._total_samples}样本")

    def _load_csv(self, filepath: str):
        # CSV格式: 每行=一个时间点, 每列=一个通道
        data = []
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    row = [float(x) for x in line.split(",")]
                    data.append(row)
                except ValueError:
                    continue
        if not data:
            raise ValueError("CSV文件为空或格式错误")
        self._data = np.array(data).T  # (n_channels, n_samples)
        self.n_channels = self._data.shape[0]
        self._fs_original = self.fs_target  # CSV假定已采样好
        self._total_samples = self._data.shape[1]
        # 自动生成通道名
        self.channel_names = [f"Ch{i}" for i in range(self.n_channels)]

    def _resample(self, data: np.ndarray, fs_from: int, fs_to: int) -> np.ndarray:
        from scipy import signal
        n_target = int(data.shape[1] * fs_to / fs_from)
        resampled = np.zeros((data.shape[0], n_target))
        for ch in range(data.shape[0]):
            resampled[ch] = signal.resample(data[ch], n_target)
        return resampled

    @property
    def fs(self):
        return self.fs_target

    def set_scene(self, scene: str):
        self._scene = scene

    def read_frame(self, n_samples: int = 256) -> dict:
        if self._data is None:
            raise RuntimeError("数据未加载")

        start = self._ptr
        end = min(start + n_samples, self._total_samples)

        # 如果数据不够一帧，循环播放
        if end - start < n_samples:
            chunk = np.zeros((self.n_channels, n_samples), dtype=np.float32)
            chunk[:, :end-start] = self._data[:, start:end]
            # 从头补
            remain = n_samples - (end - start)
            chunk[:, end-start:] = self._data[:, :remain]
            self._ptr = remain
            raw = chunk
        else:
            raw = self._data[:, start:end].copy()
            self._ptr = end

        # 时间轴
        t = (start / self.fs_target) + np.arange(n_samples) / self.fs_target

        return {
            "channels": self.channel_names,
            "raw": raw,
            "ch1": raw[0] if self.n_channels > 0 else np.zeros(n_samples),
            "ch2": raw[1] if self.n_channels > 1 else (raw[0] if self.n_channels > 0 else np.zeros(n_samples)),
            "scene": "file_playback",
            "t": t,
            "file_path": self.filepath,
            "playback_pos": self._ptr,
            "total_samples": self._total_samples,
        }

    def get_info(self) -> dict:
        return {
            "n_channels": self.n_channels,
            "channel_names": self.channel_names,
            "fs": self.fs_target,
            "duration_sec": self._total_samples / self.fs_target,
            "total_samples": self._total_samples,
        }
