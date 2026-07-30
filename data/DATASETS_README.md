# NeuroViz 数据集说明

## 本地数据集

### PhysioNet EEG Motor Imagery ( physionet_s01_*.edf )

来源：PhysioNet EEG Motor Movement/Imagery Dataset (EEGMMIDB)
- 网址：https://physionet.org/content/eegmmidb/1.0.0/
- 受试者：S001
- 通道数：64ch（国际 10-10 系统）
- 采样率：160Hz
- 通道命名：Fc5/Fc3/Fc1/Fcz/Fc2/Fc4/Fc6/C5/C3/C1/Cz/C2/C4/C6/Pc5/Pc3/Pc1/Pcz/Pc2/Pc4/Pc6/...

| 文件 | 任务 | 时长 | 大小 |
|------|------|------|------|
| physionet_s01_baseline_eyes_open.edf | 睁眼基线 | 61s | 1.2 MB |
| physionet_s01_baseline_eyes_closed.edf | 闭眼基线 | 61s | 1.2 MB |
| physionet_s01_task_motor_imagery.edf | 运动想象任务 | 125s | 2.5 MB |
| physionet_s01_mi_left_hand.edf | 左手运动想象 | 125s | 2.5 MB |
| physionet_s01_mi_feet.edf | 双脚运动想象 | 125s | 2.5 MB |

**特点**：64 通道高密度 EEG，适合验证功能连接矩阵（64x64 相干性）、Topomap、频段分析。
闭眼基线数据可以看到明显的枕叶 Alpha 波（8-13Hz）。

### 原有测试数据

| 文件 | 通道 | 采样率 | 时长 | 说明 |
|------|------|--------|------|------|
| test_valid_8ch.edf | 8ch | 500Hz | 312s | 标准 8 通道测试 |
| test_10ch.edf | 10ch | 500Hz | 1s | 10 通道测试 |
| test_artifact.edf | 8ch | 500Hz | 1s | 伪迹检测测试 |
| sample_eeg_8ch_500hz_30s.csv | 8ch | 500Hz | 30s | CSV 格式样本 |
| sample_eeg_8ch_60s.csv | 9ch | 500Hz | ~8s | CSV 格式样本 |
| rawData(1).csv / rawData(2).csv | — | — | — | 真实采集数据 |

## 使用方法

1. **上传文件**：在 NeuroViz 网页中拖拽 .edf 文件到页面，或点击 File 按钮选择文件
2. **自动解析**：系统自动识别通道数、采样率、通道名、时长
3. **实时回放**：文件上传后自动切换到文件源，所有可视化功能基于文件数据工作
4. **功能连接**：64 通道数据可以看到 64×64 相干性矩阵，效果远比 8 通道震撼

## 支持的文件格式

- EDF (European Data Format) ✅
- BDF (BioSemi Data Format) ✅
- GDF (General Data Format) ✅
- BrainVision (.vhdr) ✅
- CSV (逗号分隔，每列一个通道) ✅