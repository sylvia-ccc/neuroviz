# NeuroViz 项目交接文档

> **给 Codex 机器人的完整项目说明** — 包含项目架构、当前状态、已知问题、待办任务

---

## 1. 项目概述

**NeuroViz** — 硬件无关的 EEG 脑电可视化平台

- **品牌**：Nowis NeuroViz
- **定位**：实时脑电数据可视化 + 情绪分析 + 信号质量评估
- **商业模式**：Core 免费（≤4通道）/ Pro ¥599 一次性
- **线上地址**：https://neuroviz.bigmonsterclaw.com
- **GitHub**：https://github.com/sylvia-ccc/neuroviz
- **ICP备案**：粤ICP备2026031333号-1

---

## 2. 技术架构

### 后端
- **框架**：FastAPI + Uvicorn（端口 8080）
- **实时通信**：WebSocket（20fps 推送，50ms 延迟）
- **数据处理**：NumPy + SciPy + MNE
- **文件支持**：EDF/BDF（pyedflib/mne）、GDF/BrainVision（mne）、CSV（内置）
- **信号处理**：
  - 预处理：50Hz 陷波（Q=30）+ 1-40Hz Butterworth 4阶带通 + ±150µV 伪迹线性插值
  - 情绪引擎：频段能量 + Alpha 不对称性 + 基线校准（120帧≈2分钟）
  - 伪迹检测：眼电/肌电/运动伪迹实时检测
  - 信号质量：8通道质量指示灯
  - Topomap：matplotlib + scipy griddata 插值
  - 时频分析：scipy.signal.stft
  - PSD：功率谱密度

### 前端
- **单文件 HTML**（~2885行）：`frontend/index.html`
- **Canvas 2D 渲染**：波形图、频段柱状图、情绪四象限、频谱瀑布图
- **UI 风格**："Neural Observatory" 概念 + glassmorphism + CSS 变量
- **库**：Three.js 0.159.0（本地）、OrbitControls.js（本地）
- **品牌色**：深空玄灰 #121826、神经紫 #7B61FF、鎏金 #C8B388、浅蓝 #8AA6C2

### 数据流
```
数据源(500Hz, 256点/帧) → 预处理(~5ms) → 情绪分析(~2ms) → WebSocket推送(64点降采样, 20fps) → 前端渲染
```

### 数据源
| 类型 | 文件 | 状态 |
|------|------|------|
| Mock | `data_sources/mock.py` | ✅ AR(2) + Cholesky 空间相关 |
| LSL | `data_sources/lsl_source.py` | ✅ pylsl |
| Serial | `data_sources/serial_source.py` | 🚧 等硬件到货 |
| File | `data_sources/file_source.py` | ✅ EDF/BDF/GDF/BrainVision/CSV |

---

## 3. 项目目录结构

```
neuroviz/
├── backend/
│   ├── app.py                    # FastAPI 主入口（1161行）
│   ├── requirements.txt          # 35 个依赖
│   ├── data_sources/
│   │   ├── __init__.py
│   │   ├── mock.py              # MockDataSource（AR(2)模拟数据）
│   │   ├── file_source.py       # FileDataSource（EDF/CSV回放）
│   │   ├── lsl_source.py        # LSLDataSource（Lab Streaming Layer）
│   │   ├── serial_source.py     # SerialDataSource（串口，待硬件）
│   │   └── edf_source.py        # EDF辅助
│   ├── processors/
│   │   ├── __init__.py
│   │   ├── emotion.py           # 情绪引擎（118行）
│   │   ├── topomap.py           # 2D脑地形图（250行）
│   │   ├── artifact.py          # 伪迹检测（296行）
│   │   ├── quality.py           # 信号质量评估（206行）
│   │   ├── spectrogram.py       # 频谱瀑布图
│   │   ├── preprocessing.py     # 预处理（陷波+带通+伪迹插值）
│   │   ├── psd.py               # 功率谱密度
│   │   ├── timefreq.py          # 时频分析
│   │   ├── epoch.py             # 分段分析
│   │   ├── report.py            # PDF报告导出（17890行，含STHeiti字体注册）
│   │   ├── markers.py           # 事件标记
│   │   └── classifier.py        # 在线分类器（9990行）
│   ├── paradigm/
│   │   ├── __init__.py
│   │   ├── api.py               # 范式API
│   │   └── controller.py        # 范式控制器
│   └── mock_lsl_stream.py       # LSL模拟流（测试用）
├── frontend/
│   ├── index.html               # 单文件前端（~2885行）
│   ├── css/neuroviz.css         # 玻璃态UI样式
│   └── lib/OrbitControls.js     # Three.js OrbitControls
├── data/                        # 测试数据（EDF/CSV样本）
├── sdk/                         # Python SDK
├── config.json                  # 配置文件
├── start.sh                     # 自动启动脚本
├── deploy.sh                    # 部署脚本
├── install.sh                   # 一键安装脚本
├── TASKS.md                     # 任务清单
├── DEPLOYMENT_CHECKLIST.md      # 上线检查清单
├── RELEASE_NOTES.md             # 发布说明
└── README.md                    # 项目文档
```

---

## 4. 部署配置

### 服务器
- **IP**：43.136.117.175（腾讯云）
- **域名**：neuroviz.bigmonsterclaw.com
- **代码路径**：`/var/www/neuroviz/`
- **后端虚拟环境**：`/opt/neuroviz-venv`
- **后端日志**：`/var/log/neuroviz.log`

### Nginx 配置（`/etc/nginx/sites-available/neuroviz`）
- **HTTPS**：Let's Encrypt，过期 2026-08-23，自动续期
- **WebSocket**：`wss://neuroviz.bigmonsterclaw.com/ws`，超时 3600s
- **文件上传**：`client_max_body_size 50M`
- **代理**：`/api/` → `http://localhost:8080`，`/ws` → `http://localhost:8080`

### 后端启动命令
```bash
cd /var/www/neuroviz/backend
nohup /opt/neuroviz-venv/bin/uvicorn app:app --host 0.0.0.0 --port 8080 > /var/log/neuroviz.log 2>&1 &
```

### 重要提醒
- 服务器上还有一个旧的 uvicorn 进程（端口 8000），需要清理：`kill -9 <PID>`
- 服务器代码可能比本地更新（之前的修复是在服务器上直接用 sed/python 修改的）

---

## 5. 已完成功能

### Phase 1 MVP ✅
- 实时波形（多通道动态缓冲）
- 频段能量柱（θ/α/β/γ/δ）
- 情绪四象限（Russell 模型，效价/唤醒度）
- 2D Topomap（matplotlib + scipy griddata 插值）
- 频谱瀑布图

### Phase 2 ✅（大部分完成）
- 多通道波形支持（2-8通道）
- 文件上传回放（EDF/BDF/GDF/BrainVision/CSV，拖拽上传）
- 通道选择器（下拉动态生成）
- 时频分析（scipy.signal.stft，base64 PNG 每2秒推送）
- PSD（功率谱密度）模块
- 频段统计 API
- 伪迹检测 + WebSocket 推送 + 前端状态栏
- 信号质量评估 + 8通道指示灯
- LSL 流连接
- PDF 报告导出（中文字体 STHeiti 4变体）
- CSV 导出

### 部署 ✅
- GitHub 仓库创建
- 腾讯云服务器部署
- Nginx 反向代理 + SSL 证书
- WebSocket 超时修复（3600s）
- 文件上传 413 错误修复（client_max_body_size 50M）
- asyncio.to_thread 修复（/api/analysis/artifact 和 /api/analysis/epoch）

---

## 6. 已知问题（需要修复）

### 🔴 高优先级

1. **前端 `updateArtifactBar` 缺少 null 检查**
   - 文件：`frontend/index.html` 第 2839 行
   - 问题：`document.getElementById('art-blink').textContent` 等 6 处调用，元素不存在时 TypeError
   - 修复：添加 `setSafe(id, text)` 辅助函数
   - **注意**：本地代码还没有修复，服务器上也还没修复

2. **前端 `uploadFile` 缺少 response.ok 检查**
   - 文件：`frontend/index.html`
   - 问题：上传失败（如413错误）时，`response.json()` 解析 HTML 错误页面导致崩溃
   - 修复：在 `return response.json()` 前添加 `if (!response.ok)` 检查

3. **服务器代码比本地更新**
   - 服务器上的 `app.py` 有本地没有的修改：
     - `asyncio.to_thread` 修复
     - WebSocket 调试输出
   - 服务器上的 `index.html` 是 5月25日下载的版本，但 Nginx 已修复
   - **需要从服务器同步最新代码到本地**

### 🟡 中优先级

4. **LSL 对话框可能不弹出**
   - 现象：点击 LSL 按钮，对话框可能不弹出
   - 之前的 commit（10eb4ae）已添加调试和加固代码，但未在服务器上验证

5. **CSV 上传后波形可能无变化**
   - 需要验证 `file_source.py` 的 CSV 处理逻辑
   - 可能是 CSV 格式不匹配或通道映射问题

6. **服务器有旧 uvicorn 进程（端口 8000）**
   - PID 1219913：`/usr/bin/python3 /usr/local/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`
   - 可能是旧版本或 n8n 的进程，需要清理

### 🟢 低优先级

7. **后端日志有大量重复输出**
   - WebSocket 循环每次迭代都打印 `[NeuroViz][DEBUG] WebSocket循环开始`
   - 应改为仅在切换数据源时打印，或完全移除调试输出

8. **Topomap 电极命名已修正**
   - T3/T4/T5/T6 → T7/T8/P7/P8（10-20 标准）✅
   - 确认已修正即可

---

## 7. 待办任务（Phase 3-4）

### Phase 3: 商业化
- ⬜ T20. 功能连接矩阵
- 🔄 T21. 伪迹检测提示（后端完成，前端集成完成，待验证）
- ⬜ T22. PDF 报告导出（基础版已完成，需增强）
- ⬜ T23. Tauri 桌面打包
- ⬜ T24. 授权系统（免费/Pro）

### Phase 4: 脑波解读
- ✅ T25. EDF 自动解析 + 脑区映射
- ⬜ T26. CSV 配置向导
- ⬜ T27. 设备模板选择器
- ⬜ T28. 信号质量实时提示（后端完成，待前端集成）

### 额外待办
- ⬜ 同步服务器最新代码到本地 Git 仓库
- ⬜ 清理服务器旧进程
- ⬜ 前端代码重构（2885行单文件太长，考虑拆分）
- ⬜ 添加 API 认证
- ⬜ 日志脱敏（EDF 文件头可能含患者姓名）

---

## 8. 关键技术细节

### WebSocket 消息格式
```json
{
  "type": "data",
  "channels": [...],
  "raw": [...],          // 64点降采样数据
  "bands": {...},        // 频段能量
  "emotion": {...},      // 情绪指标
  "topomap": "base64...", // 每40帧推送一次
  "spectrogram": "base64...", // 每2秒推送一次
  "quality": {...},      // 信号质量
  "channel_bands": {...} // 8通道频段能量
}
```

### Mock 数据模型
- AR(2) 自回归模型 + Cholesky 空间相关
- Alpha blocking 效应（专注场景下枕叶 α 消失）
- 3 场景：relax / focus / blink

### 伪迹检测阈值
- 预处理**前**检测（数据未被清理时）
- 眼电/肌电/运动伪迹分类

### PDF 中文字体
- 注册 STHeiti 4 变体（Regular/Bold/Light/Medium）

---

## 9. Git 信息

### 最近提交
```
10eb4ae fix(frontend): add debugging to LSL dialog, harden dialog creation with Object.assign
546722a fix(frontend): add debugging to exportPDF(), harden input validation
a494b5b Add one-click install.sh script
fb3f8db fix: 修复 3 个 API 500 错误，生产就绪
d027a51 feat: LSL connection + status badge + artifact detection UI
```

### 远程仓库
- `origin` → `https://github.com/sylvia-ccc/neuroviz.git`
- **注意**：URL 中包含 GitHub Personal Access Token

### 未跟踪文件
- `DEPLOYMENT_CHECKLIST.md`
- `README.md`
- `RELEASE_NOTES.md`
- `data/rawData(1).csv`
- `data/rawData(2).csv`
- `deploy.sh`
- `start.sh`

---

## 10. 环境依赖

### 后端 Python 依赖（requirements.txt）
- fastapi==0.136.1
- uvicorn==0.47.0
- numpy==2.4.6
- scipy==1.17.1
- matplotlib==3.10.9
- mne==1.12.1
- pyEDFlib==0.1.42
- pylsl==1.18.2
- reportlab==4.5.1
- pyserial==3.5
- python-multipart==0.0.29
- scikit-learn==1.8.0

### 前端库
- Three.js 0.159.0（本地 `frontend/lib/`，最后全局构建版本）
- OrbitControls.js（本地）

---

## 11. 部署命令速查

```bash
# 后端启动
cd /var/www/neuroviz/backend
/opt/neuroviz-venv/bin/uvicorn app:app --host 0.0.0.0 --port 8080

# 后端重启
killall -9 uvicorn
cd /var/www/neuroviz/backend
nohup /opt/neuroviz-venv/bin/uvicorn app:app --host 0.0.0.0 --port 8080 > /var/log/neuroviz.log 2>&1 &

# Nginx
nginx -t && nginx -s reload

# 查看日志
tail -f /var/log/neuroviz.log

# SSL 续期
certbot renew

# 回滚到稳定版本
cd /Users/sss/projects/neuroviz
git reset --hard fb3f8db
```

---

## 12. 安全提醒

- **不要泄露** `~/projects/second-brain-bci/` 目录内容
- **GitHub URL 含 PAT token**，不要公开分享
- **当前无 API 认证**，任何人可访问
- **日志可能含 EDF 患者信息**，需脱敏

---

**文档生成时间**：2026-05-27
**文档作者**：QClaw（基于项目文件和对话历史整理）
