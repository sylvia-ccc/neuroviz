# NeuroViz - EEG 实时可视化平台

硬件无关的脑电可视化软件，支持 Mock/LSL/Serial/EDF 文件多种数据源。

## 快速启动

```bash
# 1. 克隆项目
git clone <repo-url>
cd neuroviz

# 2. 启动（自动创建虚拟环境 + 安装依赖）
./start.sh

# 3. 打开前端
# 用浏览器打开 frontend/index.html
```

## 手动启动

```bash
# 后端
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 -m uvicorn app:app --host 0.0.0.0 --port 8080

# 前端
# 用浏览器打开 frontend/index.html
```

## API 文档

启动后访问: <a href="http://localhost:8080/docs">http://localhost:8080/docs</a>

## 功能列表

✅ 实时波形显示 (20fps)  
✅ 频段能量柱 (θ/α/β/γ/δ)  
✅ 情绪象限图 (效价/唤醒度)  
✅ 2D Topomap (电极空间插值)  
✅ 伪迹检测 (眼电/肌电/运动)  
✅ 信号质量评估 (8通道指示灯)  
✅ 频谱图 (瀑布图)  
✅ PSD/频段统计 API  
✅ EDF/BDF 文件上传回放  
✅ CSV/PDF 导出  
✅ LSL 流连接 (需 pylsl)  

## 数据源

| 类型 | 说明 | 状态 |
|------|------|------|
| Mock | AR(2) 模拟数据 + Cholesky 空间相关 | ✅ |
| LSL | Lab Streaming Layer (BCI2000/Muse/Emotiv) | ✅ |
| Serial | 串口 (EEG102/KS1092) | 🚧 待硬件到货 |
| File | EDF/BDF/BrainVision/CSV | ✅ |

## 依赖

后端: fastapi, uvicorn, numpy, scipy, matplotlib, mne, pyedflib, pylsl, reportlab  
前端: Three.js 0.159.0 (local), OrbitControls (local)  

## 项目结构

```
neuroviz/
├── backend/
│   ├── app.py              # FastAPI 主入口
│   ├── data_sources/       # 数据源 (mock/lsl/serial/file)
│   ├── processors/         # 信号处理 (PSD/topomap/spectrogram/artifact/quality)
│   └── paradigm/          # 范式设计器
├── frontend/
│   ├── index.html          # 单文件前端 (~2000行)
│   ├── css/neuroviz.css   # 玻璃态 UI
│   └── lib/OrbitControls.js
├── sdk/                    # Python SDK
└── start.sh                # 启动脚本
```

## 常见问题

**Q: LSL 按钮点了没反应？**  
A: 检查 F12 Console 是否有红字报错，执行 `document.getElementById('lsl-dialog')` 看元素是否存在。

**Q: PDF 导出失败？**  
A: 确保已采集数据 (raw_data 非空)，检查 `/tmp/neuroviz.log` 错误信息。

**Q: Topomap 不显示？**  
A: 检查电极命名是否为 10-20 标准 (F3/F4/C3/C4/P3/P4/O1/O2)，T7/T8 不是 T3/T4。

## 版本历史

- **v1.0** (2026-05-24): 生产就绪，所有 API 修复，提交 fb3f8db
- **v0.9** (2026-05-23): LSL 连接 + 伪迹检测 UI + 信号质量指示灯
- **v0.8** (2026-05-22): PDF 导出 + 中文字体修复
- **v0.7** (2026-05-21): 多通道 Topomap + UI 玻璃态 redesign
- **v0.6** (2026-05-20): 文件上传 + 预处理 + 时频分析
- **v0.5** (2026-05-19): Phase 1 MVP (波形/频段/情绪/Topomap)

## 授权

商业版: ¥599 一次性 (Base 版免费，≤4 通道)

---

**开发者**: QClaw  
**品牌**: Nowis NeuroViz  
**技术支持**: 检查 `/tmp/neuroviz.log` 或提 Issue
