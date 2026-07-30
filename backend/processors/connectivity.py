"""
功能连接矩阵 (Functional Connectivity Matrix)
计算通道间相干性 (Coherence)，生成 NxN 连接强度矩阵

支持频段特异性分析：可指定 alpha/beta 等频段计算该频段内的平均相干性
"""

import numpy as np
from scipy import signal as sig
from collections import deque


# 标准频段定义（与 psd.py 一致）
BANDS = {
    "delta": (1, 4),
    "theta": (4, 8),
    "alpha": (8, 13),
    "beta": (13, 30),
    "gamma": (30, 50),
}


class ConnectivityProcessor:
    """实时功能连接矩阵处理器

    计算 N 通道之间的相干性矩阵 (Coherence Matrix)。
    相干性衡量两个通道在某频段内的线性相关程度，取值 0~1。
    1 = 完全相关，0 = 完全无关。

    用途：
    - 识别脑区间的功能连接模式
    - Alpha 频段相干性反映丘脑皮层同步
    - Beta 频段相干性反映运动网络协调
    """

    def __init__(self, fs: int = 500, n_channels: int = 8,
                 band: str = "alpha", update_interval_sec: float = 2.0,
                 window_sec: float = 4.0, nperseg: int = 256):
        """
        Args:
            fs: 采样率 (Hz)
            n_channels: 通道数
            band: 目标频段名 ("delta"/"theta"/"alpha"/"beta"/"gamma"/"broadband")
            update_interval_sec: 更新间隔（秒）
            window_sec: 计算窗口长度（秒），越长越稳定但延迟越高
            nperseg: Welch 分段长度
        """
        self.fs = fs
        self.n_channels = n_channels
        self.band = band
        self.update_interval_sec = update_interval_sec
        self.window_sec = window_sec
        self.nperseg = min(nperseg, int(fs * window_sec))

        # 滑动窗口缓冲
        self.window_samples = int(fs * window_sec)
        self.buffer = deque(maxlen=self.window_samples)

        # 频段范围
        if band == "broadband":
            self.freq_range = (1, 50)
        else:
            self.freq_range = BANDS.get(band, (8, 13))

        # 最新结果缓存
        self.last_matrix = np.eye(n_channels)
        self.last_top_connections = []

        print(f"[Connectivity] 初始化: fs={fs}Hz, n_ch={n_channels}, "
              f"band={band}({self.freq_range[0]}-{self.freq_range[1]}Hz), "
              f"window={window_sec}s, update={update_interval_sec}s")

    def set_band(self, band: str):
        """切换分析频段"""
        if band == "broadband":
            self.freq_range = (1, 50)
        elif band in BANDS:
            self.freq_range = BANDS[band]
        else:
            return False
        self.band = band
        return True

    def set_n_channels(self, n: int):
        """更新通道数（数据源切换时）"""
        self.n_channels = n
        self.last_matrix = np.eye(n)

    def push(self, frame_raw: np.ndarray):
        """推入一帧数据

        Args:
            frame_raw: (n_channels, n_samples_per_frame)
        """
        # 转置后按通道存入缓冲 (n_samples, n_channels)
        self.buffer.extend(frame_raw.T)

    def _compute_coherence_pair(self, ch_a: np.ndarray, ch_b: np.ndarray) -> float:
        """计算两个通道在目标频段内的平均相干性

        Returns:
            coherence: 0~1 的标量值
        """
        nperseg = min(self.nperseg, len(ch_a) // 2)
        if nperseg < 4:
            return 0.0

        noverlap = nperseg // 2
        freqs, coh = sig.coherence(
            ch_a, ch_b, fs=self.fs, nperseg=nperseg, noverlap=noverlap
        )

        # 提取目标频段
        lo, hi = self.freq_range
        mask = (freqs >= lo) & (freqs <= hi)
        if not np.any(mask):
            return 0.0

        return float(np.mean(coh[mask]))

    def compute_matrix(self) -> np.ndarray:
        """计算完整的 NxN 相干性矩阵

        Returns:
            matrix: (n_channels, n_channels) 对称矩阵，对角线=1
        """
        if len(self.buffer) < self.nperseg:
            return self.last_matrix

        data = np.array(self.buffer)  # (n_samples, n_channels)
        n_ch = min(self.n_channels, data.shape[1])

        matrix = np.zeros((n_ch, n_ch))
        for i in range(n_ch):
            matrix[i, i] = 1.0
            for j in range(i + 1, n_ch):
                coh = self._compute_coherence_pair(data[:, i], data[:, j])
                matrix[i, j] = coh
                matrix[j, i] = coh

        self.last_matrix = matrix
        return matrix

    def get_top_connections(self, matrix: np.ndarray, top_n: int = 5,
                             channel_names: list = None) -> list:
        """提取连接最强的通道对

        Returns:
            [{ "ch_a": name, "ch_b": name, "strength": float, "ch_a_idx": int, "ch_b_idx": int }, ...]
        """
        n = matrix.shape[0]
        if channel_names is None:
            channel_names = [f"Ch{i}" for i in range(n)]

        pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                pairs.append({
                    "ch_a": channel_names[i] if i < len(channel_names) else f"Ch{i}",
                    "ch_b": channel_names[j] if j < len(channel_names) else f"Ch{j}",
                    "ch_a_idx": i,
                    "ch_b_idx": j,
                    "strength": float(matrix[i, j]),
                })

        pairs.sort(key=lambda x: x["strength"], reverse=True)
        self.last_top_connections = pairs[:top_n]
        return self.last_top_connections

    def get_matrix_payload(self, channel_names: list = None) -> dict:
        """计算并返回适合 WebSocket 推送的 payload

        Returns:
            {
                "matrix": [[...]],         # NxN 相干性矩阵 (0~1)
                "channel_names": [...],     # 通道名
                "band": "alpha",            # 当前频段
                "freq_range": [lo, hi],     # 频段范围
                "top_connections": [...],   # 连接最强的 Top-5 通道对
                "mean_connectivity": float, # 全局平均连接强度
            }
        """
        matrix = self.compute_matrix()
        top = self.get_top_connections(matrix, top_n=5, channel_names=channel_names)

        # 全局平均（排除对角线）
        n = matrix.shape[0]
        if n > 1:
            off_diag = matrix[np.triu_indices(n, k=1)]
            mean_conn = float(np.mean(off_diag))
        else:
            mean_conn = 0.0

        if channel_names is None:
            channel_names = [f"Ch{i}" for i in range(n)]

        return {
            "matrix": matrix.tolist(),
            "channel_names": channel_names[:n],
            "band": self.band,
            "freq_range": list(self.freq_range),
            "top_connections": top,
            "mean_connectivity": round(mean_conn, 4),
        }


# 测试
if __name__ == "__main__":
    proc = ConnectivityProcessor(fs=500, n_channels=8, band="alpha")

    # 模拟数据：通道间有不同程度的耦合
    np.random.seed(42)
    t = np.arange(512) / 500.0
    base = np.sin(2 * np.pi * 10 * t)  # 10Hz alpha
    channels = []
    for i in range(8):
        noise = np.random.randn(512) * 0.5
        coupling = base * (1.0 - i * 0.1)  # 前几个通道耦合更强
        channels.append(coupling + noise)

    raw = np.array(channels)  # (8, 512)
    proc.push(raw)

    result = proc.get_matrix_payload(channel_names=["Fp1","Fp2","F3","F4","C3","C4","P3","P4"])
    print(f"\n矩阵形状: {np.array(result['matrix']).shape}")
    print(f"平均连接强度: {result['mean_connectivity']}")
    print(f"Top-3 连接:")
    for c in result["top_connections"][:3]:
        print(f"  {c['ch_a']} <-> {c['ch_b']}: {c['strength']:.4f}")
    print("\n✅ 功能连接矩阵计算正常")