"""
情绪分析引擎 — 简化版，用于NeuroViz MVP
只依赖numpy/scipy，无需mne
"""

import numpy as np
from scipy.signal import welch


class EmotionEngine:
    """情绪特征提取引擎"""
    
    def __init__(self, fs: int = 500):
        self.fs = fs
        self._calibrated = False
        self._baseline_vals = []
        self._baseline_median = 0.0
    
    def analyze(self, ch1: np.ndarray, ch2: np.ndarray) -> dict:
        """
        分析一帧数据，提取情绪特征
        ch1: 左前额(FP1)信号
        ch2: 右前额(FP2)信号
        """
        # 1. 频段功率
        bands1 = self._calc_bands(ch1)
        bands2 = self._calc_bands(ch2)
        
        # 2. Alpha不对称性（核心指标）
        alpha1 = bands1.get("alpha", 0.0)
        alpha2 = bands2.get("alpha", 0.0)
        asymmetry = np.log(alpha2 + 1e-10) - np.log(alpha1 + 1e-10)
        
        # 3. 个人校准
        valence = self._calibrate_valence(asymmetry)
        
        # 4. 唤醒度 (beta活跃度=高唤醒)
        total_power = sum(bands1.values()) + 1e-10
        beta_ratio = bands1.get("beta", 0.0) / total_power
        arousal = np.clip(beta_ratio * 10, 0.0, 5.0)  # 归一化0-5
        
        # 5. 专注度
        focus = bands1.get("beta", 0.0) / (bands1.get("alpha", 1.0) + 1e-10)
        focus = np.clip(focus * 20, 0, 100)  # 归一化到0-100
        
        # 6. 放松度 (alpha占比，beta高时自然降低)
        total = sum(bands1.values()) + 1e-10
        relaxation = (bands1.get("alpha", 0.0) / total) * 100
        
        return {
            "asymmetry": round(float(asymmetry), 4),
            "valence": valence,
            "arousal": round(float(arousal), 4),
            "focus": round(float(focus), 2),
            "relaxation": round(float(relaxation), 2),
            "bands_ch1": {k: round(float(v), 2) for k, v in bands1.items()},
            "bands_ch2": {k: round(float(v), 2) for k, v in bands2.items()},
            "calibrated": self._calibrated,
        }
    
    def _calc_bands(self, sig: np.ndarray) -> dict:
        """计算5个频段的功率"""
        fs = self.fs
        nperseg = min(len(sig), fs * 2)  # 2秒窗长
        freqs, psd = welch(sig, fs=fs, nperseg=nperseg)
        
        bands = {}
        bands["delta"] = self._band_power(freqs, psd, 1, 4)
        bands["theta"] = self._band_power(freqs, psd, 4, 8)
        bands["alpha"] = self._band_power(freqs, psd, 8, 13)
        bands["beta"]  = self._band_power(freqs, psd, 13, 30)
        bands["gamma"] = self._band_power(freqs, psd, 30, min(50, fs//2))
        return bands
    
    def _band_power(self, freqs, psd, low, high) -> float:
        """计算某频段的功率"""
        idx = (freqs >= low) & (freqs < high)
        return float(np.trapezoid(psd[idx], freqs[idx])) if np.any(idx) else 0.0
    
    
    def compute_bands(self, ch_data: np.ndarray) -> dict:
        """
        公开方法：计算单通道频段功率
        用于多通道场景（8电极）
        """
        return self._calc_bands(ch_data)
    
    def compute_all_channels(self, raw: np.ndarray) -> list:
        """
        计算所有通道的频段功率
        raw: shape (n_channels, n_samples)
        返回: [{'theta':v, 'alpha':v, ...}, ...] 每通道一个dict
        """
        result = []
        for i in range(raw.shape[0]):
            result.append(self._calc_bands(raw[i]))
        return result

    def _calibrate_valence(self, asymmetry: float) -> str:
        """
        基于不对称性的效价判断
        负值=左Alpha少=积极, 正值=右Alpha多=消极
        """
        self._baseline_vals.append(asymmetry)
        if len(self._baseline_vals) >= 120:  # 约2分钟@fs=500
            self._calibrated = True
            self._baseline_median = float(np.median(self._baseline_vals))
        
        if not self._calibrated:
            return "calibrating"
        
        diff = asymmetry - self._baseline_median
        if diff < -0.1:
            return "positive"
        elif diff > 0.1:
            return "negative"
        else:
            return "neutral"
