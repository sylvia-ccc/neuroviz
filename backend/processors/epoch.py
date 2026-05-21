"""
分段分析（Epoching）
将长时间EEG记录按固定长度分段，逐段计算特征
"""
import numpy as np
from typing import List, Dict, Any, Optional


class Epocher:
    """EEG分段处理器"""
    
    def __init__(self, fs: int = 500, epoch_len: float = 5.0, overlap: float = 0.0):
        """
        fs: 采样率 Hz
        epoch_len: 每段时长 秒
        overlap: 段间重叠比例 0-1
        """
        self.fs = fs
        self.epoch_len = epoch_len
        self.overlap = overlap
        self.epoch_samples = int(epoch_len * fs)
        self.hop_samples = int(self.epoch_samples * (1 - overlap))
        
    def segment(self, raw: np.ndarray) -> List[np.ndarray]:
        """
        将原始数据分段
        raw: (n_channels, n_samples)
        returns: List of (n_channels, epoch_samples) arrays
        """
        n_samples = raw.shape[1]
        epochs = []
        start = 0
        while start + self.epoch_samples <= n_samples:
            epoch = raw[:, start:start + self.epoch_samples]
            epochs.append(epoch)
            start += self.hop_samples
        return epochs
    
    def segment_info(self, n_samples: int) -> List[Dict[str, Any]]:
        """获取分段信息（时间戳、索引）"""
        epochs_info = []
        start = 0
        epoch_idx = 0
        while start + self.epoch_samples <= n_samples:
            t_start = start / self.fs
            t_end = (start + self.epoch_samples) / self.fs
            epochs_info.append({
                "index": epoch_idx,
                "start_sample": start,
                "end_sample": start + self.epoch_samples,
                "start_time": round(t_start, 2),
                "end_time": round(t_end, 2),
            })
            start += self.hop_samples
            epoch_idx += 1
        return epochs_info
    
    def compute_epoch_features(self, epoch: np.ndarray) -> Dict[str, Any]:
        """
        计算单段特征：均值、标准差、峰值、频段功率
        epoch: (n_channels, epoch_samples)
        """
        n_ch = epoch.shape[0]
        features = {"channels": []}
        
        for ch in range(n_ch):
            ch_data = epoch[ch]
            # 时域特征
            mean = float(np.mean(ch_data))
            std = float(np.std(ch_data))
            peak = float(np.max(np.abs(ch_data)))
            rms = float(np.sqrt(np.mean(ch_data**2)))
            
            # 频段功率（简单FFT）
            fft = np.abs(np.fft.rfft(ch_data))
            freqs = np.fft.rfftfreq(len(ch_data), 1/self.fs)
            
            def band_power(lo, hi):
                mask = (freqs >= lo) & (freqs < hi)
                return float(np.sum(fft[mask]**2) / len(ch_data)) if np.any(mask) else 0.0
            
            bands = {
                "delta": band_power(1, 4),
                "theta": band_power(4, 8),
                "alpha": band_power(8, 13),
                "beta": band_power(13, 30),
                "gamma": band_power(30, 50),
            }
            
            features["channels"].append({
                "channel": ch,
                "mean_uv": round(mean, 2),
                "std_uv": round(std, 2),
                "peak_uv": round(peak, 2),
                "rms_uv": round(rms, 2),
                "bands": bands,
            })
        
        return features
    
    def analyze_all_epochs(self, raw: np.ndarray) -> Dict[str, Any]:
        """
        全部分段分析
        returns: {epoch_info: [...], features: [...]}
        """
        epochs = self.segment(raw)
        if not epochs:
            return {"error": "数据长度不足一个epoch"}
        
        info = self.segment_info(raw.shape[1])
        features = []
        
        for i, epoch in enumerate(epochs):
            feat = self.compute_epoch_features(epoch)
            feat["epoch_index"] = i
            features.append(feat)
        
        return {
            "epoch_len_sec": self.epoch_len,
            "overlap": self.overlap,
            "total_epochs": len(epochs),
            "epochs": info,
            "features": features,
        }


def compute_epoch_trend(features: List[Dict]) -> Dict[str, List]:
    """
    从分段特征提取时间趋势
    returns: {band_name: [values per epoch]}
    """
    bands = ["delta", "theta", "alpha", "beta", "gamma"]
    trends = {b: [] for b in bands}
    
    for epoch_feat in features:
        # 取第一个通道（或平均所有通道）
        if epoch_feat.get("channels"):
            ch_bands = epoch_feat["channels"][0]["bands"]
            for b in bands:
                trends[b].append(ch_bands.get(b, 0))
    
    return trends
