"""
信号质量实时检测模块
检测：阻抗/接触不良、饱和、噪声过大、信号过弱

使用自适应统计阈值，适配不同数据源（Mock/EDF/CSV/LSL）的幅度范围。
前 30 帧自动校准基线，之后用 z-score 相对判断。
"""

import numpy as np
from collections import deque


class QualityDetector:
    """实时信号质量评估（自适应阈值）"""

    GOOD = "good"
    WARNING = "warning"
    BAD = "bad"

    def __init__(self, fs: int = 500, n_channels: int = 8):
        self.fs = fs
        self.n_channels = n_channels
        self.set_n_channels(n_channels)

        # 校准状态
        self._calibration_frames = 0
        self._calibration_target = 30  # 30 帧 ≈ 1.5s @ 20fps
        self._calibrated = False
        # 校准期间的 RMS 统计
        self._rms_history = {ch: [] for ch in range(n_channels)}

        # 自适应基线（校准后填充）
        self._baseline_rms = [None] * n_channels  # 每通道 RMS 基线
        self._baseline_std = [None] * n_channels  # 每通道标准差基线

        # 固定阈值（用于检测绝对异常，不依赖数据范围）
        self._flatline_var = 1e-8      # 方差几乎为零 = flatline
        self._saturation_ratio = 0.99   # 99% 样本相同 = 饱和
        self._hf_noise_ratio = 0.45     # 高频功率占比 > 45% = 肌电
        self._powerline_ratio = 0.35    # 工频功率占比 > 35% = 工频干扰

    def set_n_channels(self, n: int):
        """更新通道数（数据源切换时）"""
        self.n_channels = n
        self.window_sec = 1.0
        self.window_samples = int(self.fs * self.window_sec)
        self.buffers = [deque(maxlen=self.window_samples) for _ in range(n)]
        self._rms_history = {ch: [] for ch in range(n)}
        self._baseline_rms = [None] * n
        self._baseline_std = [None] * n
        self._calibration_frames = 0
        self._calibrated = False

    def push(self, data: np.ndarray):
        """推入新数据帧 data: (n_channels, n_samples)"""
        n_ch = min(self.n_channels, data.shape[0])
        for ch in range(n_ch):
            self.buffers[ch].extend(data[ch, :])
            # 校准期间记录 RMS
            if not self._calibrated:
                buf_arr = np.array(data[ch, :])
                rms = np.sqrt(np.mean(buf_arr ** 2))
                if rms > 0:  # 忽略全零帧
                    self._rms_history.setdefault(ch, []).append(rms)

        # 检查是否校准完成（需要至少 5 个有效帧）
        if not self._calibrated:
            self._calibration_frames += 1
            valid_count = min(len(v) for v in self._rms_history.values()) if self._rms_history else 0
            if self._calibration_frames >= self._calibration_target and valid_count >= 3:
                self._finish_calibration()

    def _finish_calibration(self):
        """根据前 30 帧数据计算自适应基线"""
        for ch in range(self.n_channels):
            rms_values = self._rms_history.get(ch, [])
            if len(rms_values) >= 5:
                self._baseline_rms[ch] = float(np.median(rms_values))
                self._baseline_std[ch] = float(np.std(rms_values))
            else:
                # 数据不足，用默认值
                self._baseline_rms[ch] = 50.0
                self._baseline_std[ch] = 10.0
        self._calibrated = True
        # 清理校准历史
        self._rms_history.clear()

    def assess_channel(self, ch_idx: int) -> dict:
        """评估单个通道信号质量"""
        buf = np.array(self.buffers[ch_idx])
        if len(buf) < self.fs * 0.3:
            return {"status": self.WARNING, "issues": ["数据不足"], "suggestion": "等待���据..."}

        issues = []
        status = self.GOOD

        # 基本统计
        amp_max = float(np.max(np.abs(buf)))
        variance = float(np.var(buf))
        amp_rms = float(np.sqrt(np.mean(buf ** 2)))

        # === 绝对检测（不依赖数据范围）===

        # 1. Flatline / 饱和 检测
        signal_std = float(np.std(buf))
        signal_mean_abs = float(np.abs(np.mean(buf))) + 1e-12
        relative_std = signal_std / signal_mean_abs

        # 绝对 flatline：std 几乎为零
        if signal_std < 1e-12:
            issues.append("信号平坦（可能接触不良）")
            status = self.BAD
            return self._make_result(status, issues, amp_rms, variance)

        # 饱和检测：信号值变化极少（相对精度），且有显著幅度
        # 用四舍五入后的唯一值比例，但根据信号量级调整精度
        if amp_rms > 1e-9:
            # 动态精度：根据信号幅度选择小数位数
            scale = max(0, int(-np.log10(amp_rms + 1e-15)) + 3)
            scale = min(scale, 12)
            unique_ratio = len(np.unique(np.round(buf, scale))) / len(buf)
            if unique_ratio < 0.005:
                issues.append("信号饱和（ADC 限幅）")
                status = self.BAD
                return self._make_result(status, issues, amp_rms, variance)

        # 相对 flatline：std 相对于信号偏移极小
        if abs(np.mean(buf)) > 1e-8 and relative_std < 0.0001:
            issues.append("信号平坦（仅有直流偏置）")
            status = self.BAD
            return self._make_result(status, issues, amp_rms, variance)

        # === 自适应检测（基于校准基线）===

        if self._calibrated and self._baseline_rms[ch_idx] is not None:
            baseline = self._baseline_rms[ch_idx]
            std = max(self._baseline_std[ch_idx], 1e-6)

            # 3. 幅度突变（z-score > 5 表示信号突变，可能接触不良或电极脱落）
            if baseline > 0:
                z_score = abs(amp_rms - baseline) / std
                if z_score > 8:
                    issues.append("信号突变（可能电极松动）")
                    status = self.BAD
                elif z_score > 4:
                    issues.append("信号波动异常")
                    if status == self.GOOD:
                        status = self.WARNING

            # 4. 信号骤降（RMS 降至基线的 1/10 以下）
            if baseline > 0 and amp_rms < baseline * 0.1:
                issues.append("信号骤降（可能接触不良）")
                if status != self.BAD:
                    status = self.WARNING

            # 5. 信号骤升（RMS 超过基线 10 倍）
            if baseline > 0 and amp_rms > baseline * 10:
                issues.append("信号骤升（可能伪迹或电极移动）")
                if status == self.GOOD:
                    status = self.WARNING
        else:
            # 未校准时仅检查相对异常，不做绝对幅度判断
            # 用信号自身的 std 作为参考
            if signal_std < 1e-10:
                issues.append("信号无变化")
                if status == self.GOOD:
                    status = self.WARNING

        # === 频域检测 ===

        # 6. 高频噪声（肌电干扰）
        if len(buf) >= 256:
            from scipy import signal as sig
            f, Pxx = sig.welch(buf, fs=self.fs, nperseg=min(256, len(buf)))
            hf_mask = (f >= 30) & (f <= 100)
            if np.any(hf_mask) and np.sum(Pxx) > 0:
                hf_ratio = float(np.sum(Pxx[hf_mask]) / np.sum(Pxx))
                if hf_ratio > self._hf_noise_ratio:
                    issues.append("高频噪声过大（肌电干扰）")
                    if status == self.GOOD:
                        status = self.WARNING

        # 7. 工频干扰（50Hz）
        if len(buf) >= 500:
            from scipy import signal as sig
            f, Pxx = sig.welch(buf, fs=self.fs, nperseg=min(500, len(buf)))
            pf_mask = (f >= 48) & (f <= 52)
            sig_mask = f < 40
            if np.any(pf_mask) and np.any(sig_mask) and np.sum(Pxx[sig_mask]) > 0:
                pf_ratio = float(np.sum(Pxx[pf_mask]) / np.sum(Pxx[sig_mask]))
                if pf_ratio > self._powerline_ratio:
                    issues.append("工频干扰（请检查接地）")
                    if status == self.GOOD:
                        status = self.WARNING

        suggestion = self._generate_suggestion(issues)
        return self._make_result(status, issues, amp_rms, variance, suggestion)

    def _make_result(self, status, issues, rms, variance, suggestion=None):
        if suggestion is None:
            suggestion = self._generate_suggestion(issues)
        return {
            "status": status,
            "issues": issues,
            "suggestion": suggestion,
            "rms": round(rms, 4),
            "variance": round(variance, 6),
        }

    def assess_all(self) -> dict:
        """评估所有通道"""
        channel_results = [self.assess_channel(ch) for ch in range(self.n_channels)]
        bad_count = sum(1 for r in channel_results if r["status"] == self.BAD)
        warning_count = sum(1 for r in channel_results if r["status"] == self.WARNING)
        good_count = sum(1 for r in channel_results if r["status"] == self.GOOD)

        if bad_count >= max(2, self.n_channels // 4):
            overall = self.BAD
        elif bad_count >= 1 or warning_count >= max(2, self.n_channels // 3):
            overall = self.WARNING
        else:
            overall = self.GOOD

        return {
            "overall": overall,
            "channels": channel_results,
            "summary": {"good": good_count, "warning": warning_count, "bad": bad_count},
            "calibrated": self._calibrated,
            "calibration_frames": self._calibration_frames,
            "calibration_target": self._calibration_target,
        }

    def _generate_suggestion(self, issues: list) -> str:
        if not issues:
            return "信号质量良好，可继续采集"
        if "信号平坦（可能接触不良）" in issues:
            return "请检查电极接触，重新佩戴"
        if "信号饱和（ADC 限幅）" in issues:
            return "信号超量程，请降低增益"
        if "信号突变（可能电极松动）" in issues:
            return "电极可能松动，请重新固定"
        if "高频噪声过大（肌电干扰）" in issues:
            return "请放松面部和颈部肌肉"
        if "工频干扰（请检查接地）" in issues:
            return "请远离电源，检查设备接地"
        if "信号骤降（可能接触不良）" in issues:
            return "信号变弱，请检查电极"
        if "信号骤升（可能伪迹或电极移动）" in issues:
            return "检测到信号突变，请注意保持静止"
        if "信号波动异常" in issues:
            return "信号波动较大，建议保持安静"
        return "信号质量一般，建议调整电极"


def quick_assess(data: np.ndarray, fs: int = 500) -> dict:
    """快速评估一段数据（无状态）"""
    n = data.shape[0]
    det = QualityDetector(fs=fs, n_channels=n)
    det.push(data)
    det._calibration_frames = det._calibration_target
    det._finish_calibration()
    det.push(data)
    return det.assess_all()