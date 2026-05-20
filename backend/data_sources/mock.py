"""
模拟EEG数据源 - 逼真版 v6
正确空间相关：Cholesky分解生成相关噪声 + 共享振荡基底
"""

import numpy as np
from scipy.linalg import cholesky


CHANNEL_NAMES = ["Fp1", "Fp2", "F3", "F4", "C3", "C4", "O1", "O2"]

# 每通道 [α尺度, β尺度, θ尺度, 噪声µV]
CHANNEL_PARAMS = np.array([
    [0.5, 0.4, 1.0, 4.0],
    [0.5, 0.4, 1.0, 4.0],
    [0.8, 0.6, 0.6, 3.0],
    [0.8, 0.6, 0.6, 3.0],
    [0.9, 1.2, 0.3, 2.5],
    [0.9, 1.2, 0.3, 2.5],
    [1.2, 0.5, 0.2, 2.0],
    [1.2, 0.5, 0.2, 2.0],
], dtype=np.float32)


class MockDataSource:
    def __init__(self, n_channels: int = 8, fs: int = 500):
        self.n_channels = min(n_channels, 8)
        self.fs = fs
        self.channel_names = CHANNEL_NAMES[:self.n_channels]

        self.scene = "relax"
        self._target_scene = "relax"
        self._transition_samples = 0
        self._transition_duration = int(2.0 * fs)

        self._ar_state = [np.zeros(2, dtype=np.float32) for _ in range(self.n_channels)]
        self._osc_phase = np.zeros(self.n_channels, dtype=np.float32)

        self._osc_amp = np.zeros((self.n_channels, 3), dtype=np.float32)
        self._target_amp = np.zeros((self.n_channels, 3), dtype=np.float32)

        # 空间相关噪声（Cholesky分解生成）
        self._init_spatial_noise()

        # 共享振荡基底（各通道共用，产生空间相关）
        self._init_shared_osc()

        self._next_blink = np.random.uniform(3.0, 6.0)
        self._blink_timer = 0

        self._t = 0.0
        print(f"[MockDataSource] v6: {self.n_channels}ch {fs}Hz（Cholesky空间相关）")
        self._update_target(self.scene)

    # ----------------------------------------------------------------- #

    def set_scene(self, scene: str):
        if scene in ("relax", "focus", "blink"):
            self._target_scene = scene
            self._transition_samples = 0

    def read_frame(self, n_samples: int = 256) -> dict:
        fs = self.fs
        t = self._t + np.arange(n_samples) / fs
        self._t += n_samples / fs

        # 平滑过渡
        if self._transition_samples < self._transition_duration:
            frac = min(1.0, (self._transition_samples + n_samples) / self._transition_duration)
            frac = 3 * frac ** 2 - 2 * frac ** 3
            self._update_target(self._target_scene)
            for ch in range(self.n_channels):
                for k in range(3):
                    self._osc_amp[ch, k] = (
                        (1 - frac) * self._osc_amp[ch, k]
                        + frac * self._target_amp[ch, k]
                    )
            self._transition_samples += n_samples
        else:
            if self.scene != self._target_scene:
                self.scene = self._target_scene
                self._update_target(self.scene)

        raw = np.zeros((self.n_channels, n_samples), dtype=np.float32)

        # === 空间相关噪声 ===
        noise = self._next_spatial_noise(n_samples)
        for ch in range(self.n_channels):
            noise_uv = CHANNEL_PARAMS[ch][3]
            raw[ch] += noise[ch] * noise_uv

        # === 振荡信号（共享基底 + 独立调制） ===
        osc = self._next_shared_osc(n_samples)
        for ch in range(self.n_channels):
            raw[ch] += self._oscillations(ch, t, n_samples, osc)

        self._apply_blink(raw, n_samples)
        self._apply_ekg(raw, n_samples, t)

        return {
            "channels": self.channel_names,
            "raw": raw,
            "ch1": raw[0],
            "ch2": raw[1] if self.n_channels > 1 else raw[0],
            "scene": self.scene,
            "t": t,
        }

    # ----------------------------------------------------------------- #

    def _update_target(self, scene: str):
        for ch in range(self.n_channels):
            p = CHANNEL_PARAMS[ch]
            a_s, b_s, t_s = p[0], p[1], p[2]
            if scene == "relax":
                self._target_amp[ch] = [a_s * 50, b_s * 8, t_s * 20]
            elif scene == "focus":
                alpha_v = a_s * 5
                if ch >= 6:
                    alpha_v = 3.0
                self._target_amp[ch] = [alpha_v, b_s * 40, t_s * 8]
            elif scene == "blink":
                self._target_amp[ch] = [a_s * 20, b_s * 15, t_s * 12]

    def _init_spatial_noise(self):
        """
        用Cholesky分解生成空间相关噪声
        基于电极真实空间距离建立相关矩阵
        """
        # 8通道10-20系统近似距离矩阵 → 相关矩阵
        # 相邻电极相关~0.7~0.9，对侧~0.2~0.4
        R = np.array([
            [1.00, 0.75, 0.60, 0.30, 0.25, 0.15, 0.12, 0.08],
            [0.75, 1.00, 0.30, 0.60, 0.15, 0.25, 0.08, 0.12],
            [0.60, 0.30, 1.00, 0.75, 0.65, 0.35, 0.20, 0.12],
            [0.30, 0.60, 0.75, 1.00, 0.35, 0.65, 0.12, 0.20],
            [0.25, 0.15, 0.65, 0.35, 1.00, 0.75, 0.45, 0.25],
            [0.15, 0.25, 0.35, 0.65, 0.75, 1.00, 0.25, 0.45],
            [0.12, 0.08, 0.20, 0.12, 0.45, 0.25, 1.00, 0.75],
            [0.08, 0.12, 0.12, 0.20, 0.25, 0.45, 0.75, 1.00],
        ], dtype=np.float32)

        # Cholesky分解：R = L @ L.T
        try:
            L = cholesky(R, lower=True)
        except Exception:
            # 若R非正定，用最近正定矩阵
            eigvals, eigvecs = np.linalg.eigh(R)
            eigvals = np.maximum(eigvals, 1e-6)
            R_pd = eigvecs @ np.diag(eigvals) @ eigvecs.T
            L = cholesky(R_pd, lower=True)

        self._chol_L = L.astype(np.float32)
        self._noise_buffer = np.random.randn(8, self.fs * 60).astype(np.float32)
        self._noise_idx = 0
        print("[MockDataSource] 空间相关噪声已初始化（Cholesky）")

    def _next_spatial_noise(self, n: int) -> np.ndarray:
        """取出n个时间点的空间相关噪声（8×n）"""
        total = self._noise_buffer.shape[1]
        if self._noise_idx + n > total:
            # 重新生成
            self._noise_buffer = np.random.randn(8, total).astype(np.float32)
            self._noise_idx = 0

        # 独立噪声 → 空间相关噪声
        idx = self._noise_idx
        independent = self._noise_buffer[:, idx:idx + n]
        correlated = self._chol_L @ independent  # (8, n)
        self._noise_idx += n
        return correlated.astype(np.float32)

    def _init_shared_osc(self):
        total = self.fs * 60
        t = np.arange(total) / self.fs
        self._sha = (40.0 * np.sin(2 * np.pi * 10.0 * t)).astype(np.float32)
        self._shb = (25.0 * np.sin(2 * np.pi * 20.0 * t)).astype(np.float32)
        self._sht = (15.0 * np.sin(2 * np.pi *  6.0 * t)).astype(np.float32)
        self._sh_idx = 0

    def _next_shared_osc(self, n: int) -> dict:
        total = len(self._sha)
        if self._sh_idx + n > total:
            self._sh_idx = 0
        a = self._sha[self._sh_idx:self._sh_idx + n]
        b = self._shb[self._sh_idx:self._sh_idx + n]
        t = self._sht[self._sh_idx:self._sh_idx + n]
        self._sh_idx += n
        return {"alpha": a, "beta": b, "theta": t}

    def _oscillations(self, ch: int, t: np.ndarray, n: int, shared: dict) -> np.ndarray:
        """
        振荡 = 共享基底(60%) + 通道独立调制(40%)
        共享基底使相邻通道空间相关
        """
        alpha_amp = self._osc_amp[ch, 0]
        beta_amp = self._osc_amp[ch, 1]
        theta_amp = self._osc_amp[ch, 2]

        sig = np.zeros(n, dtype=np.float32)

        # 共享基底（空间相关的主要来源）
        sig += (alpha_amp / 50.0) * 0.6 * shared["alpha"].astype(np.float32)
        sig += (beta_amp  / 40.0) * 0.6 * shared["beta"].astype(np.float32)
        sig += (theta_amp / 20.0) * 0.6 * shared["theta"].astype(np.float32)

        # 通道独立调制（频率微差 + 相位差）
        f_a = 10.0 + ch * 0.5
        f_b = 20.0 + ch * 1.0
        f_t =  6.0 + ch * 0.2

        sig += alpha_amp * 0.4 * np.sin(2 * np.pi * f_a * t + self._osc_phase[ch])
        sig += beta_amp  * 0.4 * np.sin(2 * np.pi * f_b * t + self._osc_phase[ch] + 1.0)
        sig += theta_amp * 0.4 * np.sin(2 * np.pi * f_t * t + self._osc_phase[ch] + 2.0)

        # 更新相位
        mean_f = (f_a + f_b + f_t) / 3.0
        self._osc_phase[ch] += 2 * np.pi * mean_f * (n / self.fs)
        return sig

    def _apply_blink(self, raw, n_samples):
        if self.scene == "blink":
            self._blink_active = True
            self._blink_timer = int(0.25 * self.fs)
            self._next_blink = np.random.uniform(4.0, 8.0)
        if getattr(self, '_blink_active', False) and self._blink_timer > 0:
            blink_n = min(n_samples, self._blink_timer)
            t_blink = np.arange(blink_n) / self.fs
            env = 80.0 * np.exp(-0.5 * ((t_blink - 0.125) / 0.04) ** 2)
            for ch in range(self.n_channels):
                if ch < 2:      w = 1.0
                elif ch < 4:    w = 0.4
                elif ch < 6:    w = 0.05
                else:            w = 0.02
                raw[ch, :blink_n] += (w * env).astype(np.float32)
            self._blink_timer -= n_samples
            if self._blink_timer <= 0:
                self._blink_active = False
        else:
            self._next_blink -= n_samples / self.fs

    def _apply_ekg(self, raw, n, t):
        ekg = np.sin(2 * np.pi * 1.2 * t)
        ekg = ekg * np.exp(-((ekg - 0.8) ** 2) * 5)
        w = [1.0, 1.0, 0.6, 0.6, 0.3, 0.3, 0.1, 0.1]
        for ch in range(self.n_channels):
            raw[ch] += w[ch] * 1.5 * ekg.astype(np.float32)
