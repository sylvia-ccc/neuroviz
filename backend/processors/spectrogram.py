"""
频谱瀑布图(Spectrogram)生成
计算FFT, 维护时间×频率的功率矩阵, 生成热图
"""

import numpy as np
from collections import deque
import time


class SpectrogramProcessor:
    """实时频谱瀑布图处理器"""
    
    def __init__(self, fs: int = 500, nfft: int = 256, nperseg: int = 256,
                 history_sec: float = 10.0):
        """
        Args:
            fs: 采样率 (Hz)
            nfft: FFT点数
            nperseg: 每段长度(用于Welch)
            history_sec: 保留的历史时长(秒)
        """
        self.fs = fs
        self.nfft = nfft
        self.nperseg = nperseg
        self.history_sec = history_sec
        
        # 频率轴 (只保留0-50Hz)
        self.freqs = np.fft.rfftfreq(nfft, 1.0 / fs)
        self.mask = (self.freqs >= 0) & (self.freqs <= 50)
        self.freqs_plot = self.freqs[self.mask]
        self.nf = len(self.freqs_plot)
        
        # 时间轴 (保留最近N个FFT)
        self.max_history = int(history_sec * fs / (nperseg // 2))  # ~ overlap 50%
        self.spectrogram = deque(maxlen=self.max_history)  # 存储(log)功率谱
        
        # 功率范围(用于颜色映射)
        self.pmin = -10  # dB
        self.pmax = 30   # dB
        
        print(f"[Spectrogram] 初始化: fs={fs}Hz, nfft={nfft}, "
              f"freq=0-50Hz ({self.nf}点), history={self.max_history}帧")
    
    def compute_psd(self, data: np.ndarray) -> np.ndarray:
        """
        计算功率谱密度(PSD) using Welch方法(简化版)
        
        Args:
            data: 时域信号 (n_samples,)
        
        Returns:
            psd: 功率谱 (nf,) 单位: dB
        """
        # 加窗(Hamming)
        window = np.hamming(len(data))
        data_win = data * window
        
        # FFT
        fft = np.fft.rfft(data_win, n=self.nfft)
        psd = np.abs(fft) ** 2 / (self.fs * np.sum(window ** 2))
        
        # 转换为dB
        psd_db = 10 * np.log10(psd + 1e-10)
        
        # 只保留0-50Hz
        return psd_db[self.mask]
    
    def update(self, data_ch1: np.ndarray, data_ch2: np.ndarray) -> np.ndarray:
        """
        更新瀑布图(计算两个通道的PSD, 取平均)
        
        Args:
            data_ch1: 通道1数据 (n_samples,)
            data_ch2: 通道2数据 (n_samples,)
        
        Returns:
            spectrogram: 当前瀑布图矩阵 (nt, nf) 单位: dB (最新在最后)
        """
        # 计算PSD
        psd1 = self.compute_psd(data_ch1)
        psd2 = self.compute_psd(data_ch2)
        
        # 取平均
        psd_avg = (psd1 + psd2) / 2.0
        
        # 添加到历史
        self.spectrogram.append(psd_avg)
        
        # 返回完整矩阵 (nt, nf)
        return np.array(self.spectrogram)
    
    def get_latest(self) -> np.ndarray:
        """返回最新的PSD (nf,)"""
        if len(self.spectrogram) > 0:
            return self.spectrogram[-1]
        return np.zeros(self.nf)
    
    def normalize(self, spec: np.ndarray) -> np.ndarray:
        """
        归一化到0-1范围(用于颜色映射)
        
        Args:
            spec: 频谱矩阵 (nt, nf) 或 (nf,)
        
        Returns:
            spec_norm: 归一化后的矩阵 (0-1)
        """
        if spec.ndim == 1:
            spec = spec.reshape(1, -1)
        
        # Clip到[pmin, pmax]
        spec_clip = np.clip(spec, self.pmin, self.pmax)
        
        # 归一化到0-1
        spec_norm = (spec_clip - self.pmin) / (self.pmax - self.pmin)
        
        return spec_norm


# 测试
if __name__ == '__main__':
    import sys
    sys.path.insert(0, '.')
    
    # 创建处理器
    proc = SpectrogramProcessor(fs=500, nfft=256, history_sec=5.0)
    
    # 模拟数据 (Alpha振荡 + 噪声)
    t = np.arange(256) / 500.0
    alpha = 30 * np.sin(2 * np.pi * 10 * t)  # 10Hz Alpha
    noise = np.random.randn(256) * 5
    data = alpha + noise
    
    # 更新10次
    for i in range(10):
        spec = proc.update(data, data + np.random.randn(256) * 2)
        print(f"Frame {i+1}: spec shape={spec.shape}")
    
    print(f"\n✅ 瀑布图矩阵: {spec.shape}")
    print(f"   频率轴: 0-50Hz, {proc.nf}点")
    print(f"   时间轴: 最近{proc.max_history}帧")
    
    # 归一化测试
    spec_norm = proc.normalize(spec)
    print(f"   归一化: min={spec_norm.min():.3f}, max={spec_norm.max():.3f}")
