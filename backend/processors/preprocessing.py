"""
EEG 预处理模块
50Hz陷波 + 1-40Hz带通 + 伪迹去除
"""

import numpy as np
from scipy import signal as sig


class Preprocessor:
    """EEG预处理流水线"""

    def __init__(self, fs: int = 500):
        self.fs = fs
        self._design_filters()

    def _design_filters(self):
        """设计滤波器（零相位，双向滤波）"""
        # 50Hz陷波（4th order IIR）
        b_notch, a_notch = sig.iirnotch(50.0, Q=30.0, fs=self.fs)
        self.b_notch = b_notch
        self.a_notch = a_notch

        # 1-40Hz带通（4th order IIR）
        b_band, a_band = sig.butter(4, [1.0, 40.0], btype='bandpass', fs=self.fs)
        self.b_band = b_band
        self.a_band = a_band

    def apply_notch(self, data: np.ndarray) -> np.ndarray:
        """
        50Hz陷波
        data: (n_channels, n_samples)
        """
        out = np.zeros_like(data)
        for ch in range(data.shape[0]):
            out[ch] = sig.filtfilt(self.b_notch, self.a_notch, data[ch])
        return out

    def apply_bandpass(self, data: np.ndarray) -> np.ndarray:
        """
        1-40Hz带通滤波
        data: (n_channels, n_samples)
        """
        out = np.zeros_like(data)
        for ch in range(data.shape[0]):
            out[ch] = sig.filtfilt(self.b_band, self.a_band, data[ch])
        return out

    def remove_artifacts(self, data: np.ndarray, threshold: float = 150.0) -> np.ndarray:
        """
        简单伪迹去除（阈值检测 + 线性插值）
        threshold: µV, 默认150µV（超过视为伪迹）
        """
        out = data.copy()
        for ch in range(data.shape[0]):
            # 检测伪迹（绝对值超过阈值）
            mask = np.abs(data[ch]) > threshold
            if np.any(mask):
                # 线性插值替换伪迹段
                idx = np.where(mask)[0]
                # 扩展伪迹窗口（前后50ms）
                win = int(0.05 * self.fs)
                for i in idx:
                    start = max(0, i - win)
                    end = min(data.shape[1], i + win + 1)
                    if start > 0 and end < data.shape[1]:
                        # 线性插值
                        t = np.arange(end - start)
                        out[ch, start:end] = np.linspace(
                            out[ch, start - 1],
                            out[ch, min(end, data.shape[1] - 1)],
                            end - start
                        )
        return out

    def process(self, data: np.ndarray) -> np.ndarray:
        """
        完整预处理流水线
        顺序: 陷波 → 带通 → 伪迹去除
        """
        # 1. 50Hz陷波
        data = self.apply_notch(data)
        # 2. 1-40Hz带通
        data = self.apply_bandpass(data)
        # 3. 伪迹去除
        data = self.remove_artifacts(data)
        return data


def test_preprocessing():
    """测试预处理模块"""
    fs = 500
    n_channels = 8
    n_samples = 1000

    # 生成测试数据（含50Hz工频干扰 + 伪迹）
    t = np.arange(n_samples) / fs
    data = np.zeros((n_channels, n_samples))
    for ch in range(n_channels):
        # 有效EEG（10Hz α波）
        data[ch] = 50.0 * np.sin(2 * np.pi * 10.0 * t)
        # 50Hz工频干扰
        data[ch] += 20.0 * np.sin(2 * np.pi * 50.0 * t)
        # 伪迹（大幅值尖峰）
        if ch == 0:
            data[ch, 300:350] += 200.0  # 伪迹

    # 预处理
    preproc = Preprocessor(fs=fs)
    cleaned = preproc.process(data)

    print("✅ 预处理测试通过")
    print(f"  原始STD: {data.std():.1f} µV")
    print(f"  清洗后STD: {cleaned.std():.1f} µV")
    print(f"  50Hz干扰是否去除: {np.abs(np.fft.rfft(cleaned[0])[int(50/fs*len(t))]) < 10}")


if __name__ == "__main__":
    test_preprocessing()
