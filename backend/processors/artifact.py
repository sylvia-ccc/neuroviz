"""
伪迹自动检测
检测眨眼、眼动、肌电、移动伪迹，标记坏段
"""
import numpy as np
from typing import Dict, List, Any, Tuple


class ArtifactDetector:
    """伪迹检测器"""
    
    def __init__(self, fs: int = 500, threshold_uv: float = 150.0):
        """
        fs: 采样率
        threshold_uv: 幅度阈值 µV
        """
        self.fs = fs
        self.threshold = threshold_uv
        
    def detect_blink(self, data: np.ndarray, ch_idx: int = 0) -> List[Dict]:
        """
        检测眨眼伪迹（前额电极高幅度尖峰）
        data: (n_channels, n_samples)
        returns: [{start, end, peak, type:'blink'}]
        """
        signal = data[ch_idx]
        n_samples = len(signal)
        
        # 眨眼特征: >100µV 尖峰, 持续 50-200ms
        blink_threshold = 100  # µV
        min_duration_ms = 50
        max_duration_ms = 300
        
        above = np.abs(signal) > blink_threshold
        artifacts = []
        
        i = 0
        while i < n_samples:
            if above[i]:
                start = i
                while i < n_samples and above[i]:
                    i += 1
                end = i
                duration_ms = (end - start) / self.fs * 1000
                
                if min_duration_ms <= duration_ms <= max_duration_ms:
                    peak = float(np.max(np.abs(signal[start:end])))
                    artifacts.append({
                        "type": "blink",
                        "start_sample": int(start),
                        "end_sample": int(end),
                        "start_time": round(start / self.fs, 3),
                        "end_time": round(end / self.fs, 3),
                        "duration_ms": round(duration_ms, 1),
                        "peak_uv": round(peak, 1),
                        "channel": ch_idx,
                    })
            else:
                i += 1
                
        return artifacts
    
    def detect_eog(self, data: np.ndarray, ch_indices: Tuple[int, int] = (0, 1)) -> List[Dict]:
        """
        检测眼动（EOG）：左右电极反向变化
        适用于 Fp1/Fp2 或水平眼电
        """
        ch1, ch2 = ch_indices
        if max(ch1, ch2) >= data.shape[0]:
            return []
            
        diff = data[ch1] - data[ch2]
        threshold = 50  # µV 差异
        
        above = np.abs(diff) > threshold
        artifacts = []
        
        i = 0
        n_samples = len(diff)
        while i < n_samples:
            if above[i]:
                start = i
                while i < n_samples and above[i]:
                    i += 1
                end = i
                duration_ms = (end - start) / self.fs * 1000
                
                # 眼动持续 200-500ms
                if 100 <= duration_ms <= 800:
                    peak = float(np.max(np.abs(diff[start:end])))
                    artifacts.append({
                        "type": "eog",
                        "start_sample": int(start),
                        "end_sample": int(end),
                        "start_time": round(start / self.fs, 3),
                        "end_time": round(end / self.fs, 3),
                        "duration_ms": round(duration_ms, 1),
                        "peak_uv": round(peak, 1),
                        "channels": [ch1, ch2],
                    })
            else:
                i += 1
                
        return artifacts
    
    def detect_emg(self, data: np.ndarray, ch_idx: int = 0) -> List[Dict]:
        """
        检测肌电伪迹（高频能量突增）
        EMG: 20-100Hz 能量突然升高
        """
        signal = data[ch_idx]
        n_samples = len(signal)
        
        # 计算20-100Hz能量（滑动窗口）
        window_ms = 100
        window_samples = int(window_ms / 1000 * self.fs)
        hop = window_samples // 2
        
        emg_energy = []
        for i in range(0, n_samples - window_samples, hop):
            segment = signal[i:i + window_samples]
            # 高通20Hz滤波
            from scipy.signal import butter, filtfilt
            b, a = butter(2, 20 / (self.fs / 2), btype='high')
            filtered = filtfilt(b, a, segment)
            energy = np.sqrt(np.mean(filtered ** 2))
            emg_energy.append((i + window_samples // 2, energy))
        
        if not emg_energy:
            return []
            
        # 检测能量突增（>均值+2*标准差）
        energies = [e[1] for e in emg_energy]
        mean_e = np.mean(energies)
        std_e = np.std(energies)
        threshold = mean_e + 2 * std_e
        
        artifacts = []
        for sample, energy in emg_energy:
            if energy > threshold and energy > 20:  # >20µV
                artifacts.append({
                    "type": "emg",
                    "sample": int(sample),
                    "time": round(sample / self.fs, 3),
                    "energy_uv": round(energy, 1),
                    "channel": ch_idx,
                })
        
        # 合并相邻检测点
        merged = self._merge_artifacts(artifacts, gap_ms=200)
        return merged
    
    def detect_movement(self, data: np.ndarray) -> List[Dict]:
        """
        检测移动伪迹（全通道大幅度偏移）
        """
        n_ch = data.shape[0]
        n_samples = data.shape[1]
        
        # 所有通道同时超阈值
        all_above = np.all(np.abs(data) > self.threshold, axis=0)
        
        artifacts = []
        i = 0
        while i < n_samples:
            if all_above[i]:
                start = i
                while i < n_samples and all_above[i]:
                    i += 1
                end = i
                duration_ms = (end - start) / self.fs * 1000
                artifacts.append({
                    "type": "movement",
                    "start_sample": int(start),
                    "end_sample": int(end),
                    "start_time": round(start / self.fs, 3),
                    "end_time": round(end / self.fs, 3),
                    "duration_ms": round(duration_ms, 1),
                    "channels": list(range(n_ch)),
                })
            else:
                i += 1
                
        return artifacts
    
    def _merge_artifacts(self, artifacts: List[Dict], gap_ms: float = 200) -> List[Dict]:
        """合并相邻伪迹点"""
        if not artifacts:
            return []
        
        gap_samples = int(gap_ms / 1000 * self.fs)
        merged = [artifacts[0]]
        
        for art in artifacts[1:]:
            last = merged[-1]
            if art.get('sample', 0) - last.get('sample', 0) < gap_samples:
                # 扩展上一个
                merged[-1]['end_sample'] = art.get('sample', 0) + 50
                merged[-1]['end_time'] = round(merged[-1]['end_sample'] / self.fs, 3)
            else:
                merged.append(art)
        
        return merged
    
    def detect_all(self, data: np.ndarray) -> Dict[str, Any]:
        """
        综合检测所有类型伪迹
        returns: {artifacts: [...], summary: {blink: n, eog: n, ...}, bad_ratio: %}
        """
        all_artifacts = []
        
        # 眨眼（前额通道）
        if data.shape[0] >= 1:
            blinks = self.detect_blink(data, ch_idx=0)
            all_artifacts.extend(blinks)
        
        # 眼动（需要2+通道）
        if data.shape[0] >= 2:
            eogs = self.detect_eog(data, ch_indices=(0, 1))
            all_artifacts.extend(eogs)
        
        # 肌电（检查所有通道）
        for ch in range(min(data.shape[0], 4)):  # 最多检查4通道
            emgs = self.detect_emg(data, ch_idx=ch)
            all_artifacts.extend(emgs)
        
        # 移动伪迹
        movements = self.detect_movement(data)
        all_artifacts.extend(movements)
        
        # 按时间排序
        all_artifacts.sort(key=lambda x: x.get('start_time', x.get('time', 0)))
        
        # 统计
        summary = {}
        for art in all_artifacts:
            t = art['type']
            summary[t] = summary.get(t, 0) + 1
        
        # 计算坏段比例
        n_samples = data.shape[1]
        bad_samples = 0
        for art in all_artifacts:
            if 'start_sample' in art and 'end_sample' in art:
                bad_samples += art['end_sample'] - art['start_sample']
            elif 'sample' in art:
                bad_samples += 50  # 假设每个点影响50个样本
        
        bad_ratio = min(bad_samples / n_samples * 100, 100) if n_samples > 0 else 0
        
        return {
            "artifacts": all_artifacts[:50],  # 最多返回50个
            "summary": summary,
            "total_artifacts": len(all_artifacts),
            "bad_ratio_percent": round(bad_ratio, 1),
        }
    
    def mark_bad_segments(self, data: np.ndarray, artifacts: List[Dict]) -> np.ndarray:
        """
        标记坏段（用NaN填充）
        """
        marked = data.copy()
        for art in artifacts:
            if 'start_sample' in art and 'end_sample' in art:
                start, end = art['start_sample'], art['end_sample']
                if art.get('channels'):
                    for ch in art['channels']:
                        if ch < marked.shape[0]:
                            marked[ch, start:end] = np.nan
                elif 'channel' in art:
                    ch = art['channel']
                    if ch < marked.shape[0]:
                        marked[ch, start:end] = np.nan
        return marked
