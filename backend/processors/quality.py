"""
信号质量实时检测模块
检测：阻抗/接触不良、饱和、噪声过大、信号过弱
"""

import numpy as np
from collections import deque


class QualityDetector:
    """实时信号质量评估"""

    # 质量等级
    GOOD = "good"        # 绿 - 信号良好
    WARNING = "warning"   # 黄 - 信号一般，建议调整
    BAD = "bad"           # 红 - 信号差，无法分析

    def __init__(self, fs: int = 500, n_channels: int = 8):
        self.fs = fs
        self.n_channels = n_channels

        # 滑动窗口（1秒数据用于质量评估）
        self.window_sec = 1.0
        self.window_samples = int(fs * self.window_sec)
        self.buffers = [deque(maxlen=self.window_samples) for _ in range(n_channels)]

        # 阈值配置
        self.thresholds = {
            "saturation": 0.95,      # 信号幅度 > 95% 量程 → 饱和
            "flatline": 0.01,        # 方差 < 0.01 →  flatline（接触不良）
            "noise_hf_ratio": 0.40,  # 高频噪声比 > 40% → 干扰大
            "amplitude_max": 200,     # µV，超过可能接触不良
            "amplitude_min": 5,       # µV，低于可能接触不良
        }

    def push(self, data: np.ndarray):
        """
        推入新数据帧
        data: shape (n_channels, n_samples)
        """
        for ch in range(self.n_channels):
            self.buffers[ch].extend(data[ch, :])

    def assess_channel(self, ch_idx: int) -> dict:
        """
        评估单个通道信号质量
        返回: {status, issues, suggestion}
        """
        buf = np.array(self.buffers[ch_idx])
        if len(buf) < self.fs * 0.5:  # 不足0.5秒数据
            return {
                "status": self.WARNING,
                "issues": ["数据不足"],
                "suggestion": "等待数据..."
            }

        issues = []
        status = self.GOOD

        # 1. 检查饱和（信号幅度过大）
        amp_max = np.max(np.abs(buf))
        if amp_max > self.thresholds["amplitude_max"]:
            issues.append("信号饱和")
            status = self.BAD

        # 2. 检查 flatline（接触不良）
        variance = np.var(buf)
        if variance < self.thresholds["flatline"]:
            issues.append("信号平坦（可能接触不良）")
            status = self.BAD

        # 3. 检查幅度过小（接触不良）
        amp_rms = np.sqrt(np.mean(buf ** 2))
        if amp_rms < self.thresholds["amplitude_min"]:
            issues.append("信号过弱（可能接触不良）")
            if status != self.BAD:
                status = self.WARNING

        # 4. 检查高频噪声（肌电/工频干扰）
        if len(buf) >= 256:
            from scipy import signal as sig
            f, Pxx = sig.welch(buf, fs=self.fs, nperseg=min(256, len(buf)))
            hf_mask = (f >= 30) & (f <= 100)
            if np.any(hf_mask):
                hf_power = np.sum(Pxx[hf_mask])
                total_power = np.sum(Pxx)
                if total_power > 0:
                    hf_ratio = hf_power / total_power
                    if hf_ratio > self.thresholds["noise_hf_ratio"]:
                        issues.append("高频噪声过大（肌电干扰）")
                        if status == self.GOOD:
                            status = self.WARNING

        # 5. 检查工频干扰（50/60Hz）
        if len(buf) >= 500:
            from scipy import signal as sig
            f, Pxx = sig.welch(buf, fs=self.fs, nperseg=min(500, len(buf)))
            # 50Hz (中国) 或 60Hz (美国)
            powerline_freq = 50  # 中国工频
            pf_mask = (f >= powerline_freq - 2) & (f <= powerline_freq + 2)
            if np.any(pf_mask):
                pf_power = np.sum(Pxx[pf_mask])
                total_power = np.sum(Pxx[f < 40])  # 信号频段总功率
                if total_power > 0 and pf_power / total_power > 0.3:
                    issues.append("工频干扰（请检查接地）")
                    if status == self.GOOD:
                        status = self.WARNING

        # 生成建议
        suggestion = self._generate_suggestion(issues)

        return {
            "status": status,
            "issues": issues,
            "suggestion": suggestion,
            "rms": round(float(amp_rms), 2),
            "variance": round(float(variance), 2),
        }

    def assess_all(self) -> dict:
        """
        评估所有通道，返回汇总结果
        """
        channel_results = []
        for ch in range(self.n_channels):
            result = self.assess_channel(ch)
            channel_results.append(result)

        # 汇总
        bad_count = sum(1 for r in channel_results if r["status"] == self.BAD)
        warning_count = sum(1 for r in channel_results if r["status"] == self.WARNING)
        good_count = sum(1 for r in channel_results if r["status"] == self.GOOD)

        if bad_count >= 2:
            overall = self.BAD
        elif bad_count >= 1 or warning_count >= 2:
            overall = self.WARNING
        else:
            overall = self.GOOD

        return {
            "overall": overall,
            "channels": channel_results,
            "summary": {
                "good": good_count,
                "warning": warning_count,
                "bad": bad_count,
            }
        }

    def _generate_suggestion(self, issues: list) -> str:
        """根据问题生成调整建议"""
        if not issues:
            return "信号质量良好，可继续采集"

        if "信号平坦（可能接触不良）" in issues or "信号过弱（可能接触不良）" in issues:
            return "⚠️ 请调整电极位置或湿润导电胶"

        if "信号饱和" in issues:
            return "⚠️ 信号过强，请降低增益或检查电极"

        if "高频噪声过大（肌电干扰）" in issues:
            return "⚠️ 请放松肌肉，减少咬合和皱眉"

        if "工频干扰（请检查接地）" in issues:
            return "⚠️ 请远离电源，检查设备接地"

        return "⚠️ 信号质量一般，建议调整电极"


# 便捷函数：快速评估（不维护状态）
def quick_assess(data: np.ndarray, fs: int = 500) -> dict:
    """
    快速评估一段数据的信号质量
    data: shape (n_channels, n_samples)
    """
    n_channels = data.shape[0]
    detector = QualityDetector(fs=fs, n_channels=n_channels)
    detector.push(data)
    return detector.assess_all()


if __name__ == "__main__":
    # 测试
    import time

    fs = 500
    detector = QualityDetector(fs=fs, n_channels=2)

    # 模拟好信号
    good_data = np.random.randn(2, 500) * 50  # 50µV 噪声
    detector.push(good_data)
    result = detector.assess_all()
    print("好信号:", result["overall"], result["summary"])

    # 模拟接触不良（flatline）
    bad_data = np.zeros((2, 500))
    detector.push(bad_data)
    result = detector.assess_all()
    print("接触不良:", result["overall"], result["channels"][0]["issues"])

    # 模拟饱和
    sat_data = np.ones((2, 500)) * 300  # 300µV 超量程
    detector.push(sat_data)
    result = detector.assess_all()
    print("饱和:", result["overall"], result["channels"][0]["issues"])
