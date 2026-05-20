"""
时频分析处理器 - STFT 短时傅里叶变换
使用 scipy.signal.stft，生成时频热力图
"""

import numpy as np
from scipy.signal import stft
import base64
from io import BytesIO
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


class TimeFreqProcessor:
    """
    STFT 时频分析
    - 输入: (n_channels, n_samples) EEG 数据
    - 输出: base64 PNG 图像（时频热力图）
    """

    def __init__(self, fs: int = 500, freq_max: int = 50, nperseg: int = 128):
        self.fs = fs
        self.freq_max = freq_max
        self.nperseg = nperseg

    def compute(self, data: np.ndarray, ch_idx: int = 0) -> str:
        """
        计算指定通道的时频表示（STFT）
        返回: base64 PNG 图像字符串
        """
        if ch_idx >= data.shape[0]:
            ch_idx = 0
        sig = data[ch_idx].astype(np.float64)

        # STFT
        f, t, Zxx = stft(sig, fs=self.fs, nperseg=self.nperseg)
        
        # 只保留 0-freq_max Hz
        freq_mask = f <= self.freq_max
        f = f[freq_mask]
        Zxx = Zxx[freq_mask, :]

        # 功率谱 (dB)
        power = 10 * np.log10(np.abs(Zxx) ** 2 + 1e-10)

        # 生成热力图
        fig, ax = plt.subplots(figsize=(4, 3), dpi=80)
        im = ax.imshow(
            power,
            aspect='auto',
            origin='lower',
            extent=[t[0], t[-1], f[0], f[-1]],
            cmap='jet',
            vmin=np.percentile(power, 5),
            vmax=np.percentile(power, 95)
        )
        ax.set_ylabel('Frequency (Hz)')
        ax.set_xlabel('Time (s)')
        ax.set_title(f'Time-Frequency Ch{ch_idx}')
        plt.colorbar(im, ax=ax, label='Power (dB)')
        plt.tight_layout()

        # 保存为 base64
        buf = BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode('utf-8')
        return img_b64


if __name__ == '__main__':
    # 测试
    fs = 500
    n_samples = 256
    t = np.arange(n_samples) / fs

    # 模拟 10Hz 正弦波 + 20Hz 正弦波
    data = np.zeros((2, n_samples))
    data[0] = np.sin(2 * np.pi * 10.0 * t) + 0.5 * np.sin(2 * np.pi * 20.0 * t)
    data[1] = np.sin(2 * np.pi * 8.0 * t)
    data += 0.3 * np.random.randn(2, n_samples)

    proc = TimeFreqProcessor(fs=fs)
    img_b64 = proc.compute(data, ch_idx=0)
    print(f'✅ 时频图生成成功，base64 长度: {len(img_b64)}')
    
    # 保存测试图像
    with open('/tmp/test_timefreq.png', 'wb') as f:
        import base64
        f.write(base64.b64decode(img_b64))
    print('✅ 测试图像已保存: /tmp/test_timefreq.png')
