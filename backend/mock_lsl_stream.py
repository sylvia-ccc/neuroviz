"""
LSL 模拟EEG流发射器 — 用于测试 NeuroViz LSL 连接
模拟 8 通道 EEG 数据（500Hz，使用 AR(2) 模型生成逼真信号）
"""

import numpy as np
import time

# ========== 检查 pylsl ==========
try:
    import pylsl as lsl
    HAS_PYLSL = True
except ImportError:
    HAS_PYLSL = False
    print("❌ 需要 pylsl: pip install pylsl")
    exit(1)

# ========== 参数 ==========
N_CHANNELS = 8
FS = 500  # 采样率
SCENE = "relax"  # relax / focus / blink

# 10-20 系统电极位置（8通道）
CHANNEL_NAMES = ["Fp1", "Fp2", "F7", "F3", "F4", "F8", "T7", "T8"]

# AR(2) 模型参数（模拟Alpha波 8-12Hz）
AR_A1 = 1.6   # 主频 10Hz
AR_A2 = -0.8  # 阻尼
NOISE_STD = 5.0  # 微伏


def generate_eeg_sample(n_channels: int, scene: str, prev_x: list) -> tuple:
    """
    生成单个采样点（使用 AR(2) 模型）
    返回: (samples, new_prev_x)
    """
    samples = []
    new_x = [prev_x[1], 0.0]
    
    for ch in range(n_channels):
        noise = np.random.randn() * NOISE_STD
        x_new = AR_A1 * new_x[0] + AR_A2 * prev_x[0] + noise
        
        # 根据场景调整 Alpha 能量
        if scene == "focus":
            x_new *= 0.4  # Alpha blocking
        elif scene == "relax":
            x_new *= 1.5  # Alpha 增强
        
        samples.append(x_new)
        if ch == 0:  # 只更新一次
            new_x[1] = x_new
    
    return samples, new_x


def main():
    # ========== 创建 LSL 流信息（使用正确的 API） ==========
    info = lsl.StreamInfo(
        name="Mock-EEG-8ch",
        type="EEG",
        channel_count=N_CHANNELS,
        nominal_srate=FS,
        channel_format=lsl.cf_float32,
        source_id="mock_eeg_001"
    )

    # 添加通道元数据（可选，但专业）
    desc = info.desc()
    channels = desc.append_child("channels")
    for name in CHANNEL_NAMES:
        ch = channels.append_child("channel")
        ch.append_child_value("label", name)
        ch.append_child_value("unit", "microvolts")
        ch.append_child_value("type", "EEG")

    # 创建 outlet（使用正确的 API）
    outlet = lsl.StreamOutlet(info, max_buffered=360)
    print(f"[MockLSL] ✅ LSL 流已创建")
    print(f"  名称: {info.name()}")
    print(f"  类型: {info.type()}")
    print(f"  通道数: {info.channel_count()}")
    print(f"  采样率: {info.nominal_srate()}Hz")
    print(f"  格式: float32")
    print(f"\n正在推送数据... (Ctrl+C 停止)\n")

    # ========== 主循环 ==========
    prev_x = [[0.0, 0.0] for _ in range(N_CHANNELS)]  # 每个通道的 AR(2) 历史
    
    try:
        while True:
            # 生成单个采样点
            sample = []
            for ch in range(N_CHANNELS):
                noise = np.random.randn() * NOISE_STD
                x_new = AR_A1 * prev_x[ch][1] + AR_A2 * prev_x[ch][0] + noise
                
                # 根据场景调整
                if SCENE == "focus":
                    x_new *= 0.4
                elif SCENE == "relax":
                    x_new *= 1.5
                
                sample.append(x_new)
                prev_x[ch] = [prev_x[ch][1], x_new]
            
            # 随机眨眼伪迹（前2通道 Fp1/Fp2）
            if np.random.rand() < 0.001:  # 约每1秒一次
                sample[0] += np.random.uniform(200, 500)
                sample[1] += np.random.uniform(200, 500)
            
            # 推送采样（使用正确的 API）
            outlet.push_sample(sample)
            
            # 500Hz → 休眠 2ms
            time.sleep(1.0 / FS)
            
    except KeyboardInterrupt:
        print("\n[MockLSL] 流已停止")


if __name__ == "__main__":
    main()
