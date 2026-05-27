# NeuroViz v1.0 功能盘点与最小验证清单

更新时间：2026-05-27

## 状态定义

- 可用：已在本地代码或 API 层通过基础验证。
- 需验证：代码入口存在，但还没有完成浏览器端或完整用户链路验证。
- 有 bug：已发现明确问题，影响核心流程。
- 未实现：有入口或规划，但不能作为 v1.0 核心能力交付。

## 当前阶段

已完成：

- 本地代码状态检查：`main` 与 GitHub `main` 一致，工作区原本干净。
- 高优先级 bug 本地修复：上传错误处理、伪迹栏 DOM 崩溃、后端 `epoch` / `artifact` 阻塞接口。
- 基础验证：Python 编译、前端脚本语法、关键 API 请求、样本文件加载。
- 浏览器端完整链路验证通过：Mock、CSV、EDF、LSL 模拟流、CSV/PDF 导出。
- 核心链路阻塞 bug 已修复：PDF 导出 500、LSL WebSocket `NaN` 导致前端 JSON 解析异常、频段统计通道数错误。

未完成：

- Git push、服务器部署。

## 功能盘点

| 功能 | 状态 | 依据 | v1.0 处理 |
|---|---|---|---|
| 首页与静态前端 | 可用 | FastAPI `/` 返回 `frontend/index.html`，`/docs` 可访问 | 保留 |
| Mock 数据源 | 可用 | `MockDataSource` 本地可生成 8 通道 500Hz 帧 | 作为默认演示样本 |
| WebSocket 实时推送 | 可用 | 浏览器验证中 Mock/CSV/EDF/LSL 均保持连接并收到数据 | 保留 |
| 实时波形 Canvas | 可用 | 浏览器验证收到 8 通道实时帧 `rawShape=[8,64]` | 保留 |
| PSD 功率谱 API | 可用 | 浏览器验证 `psdData` 已生成，`psdLen=103` | 保留 |
| 频段统计 API | 可用 | 浏览器验证 `bandStatsChannels=8` 且表格有内容 | 保留 |
| 情绪四象限 | 可用 | 浏览器验证 `latestEmotion` 持续更新 | 保留 |
| 2D Topomap | 可用 | 浏览器验证 Topomap 图片已生成并加载 | 保留 |
| 3D Brain 视图 | 需验证 | 前端仍有 3D 入口，但交接文档说专业意义不足 | v1.0 不扩展 |
| 频谱瀑布图 | 可用 | 浏览器验证时频图图片已生成并加载 | 保留 |
| 文件上传 CSV/EDF | 可用 | 浏览器验证 CSV/EDF 上传后均切换文件源并回放 8 通道 | 保留 |
| 上传错误处理 | 可用 | 本地已修 `response.ok` 检查，JS 语法通过 | 回归测试 |
| 伪迹检测 API | 可用 | `/api/analysis/artifact` 本地返回 200 | 必测前端栏 |
| 伪迹栏 UI | 可用 | 浏览器验证伪迹栏正常显示且无 DOM 崩溃 | 保留 |
| 信号质量提示 | 可用 | 浏览器验证质量状态可显示“良好/一般/差” | 保留 |
| Epoch 分段分析 | 可用 | `/api/analysis/epoch` 本地返回 200 | 可作为研究模式能力 |
| CSV 导出 | 可用 | 浏览器验证导出返回 200，`text/csv`，3097 bytes | 保留 |
| PDF 导出 | 可用 | 浏览器验证导出返回 200，`application/pdf`，144736 bytes | 保留 |
| LSL 流发现 | 可用 | `/api/lsl/streams` 本地返回 200 | 必测模拟流 |
| LSL 连接 UI | 可用 | 浏览器验证模拟流可被扫描并连接 | 保留 |
| LSL 模拟流 | 可用 | 浏览器验证 `mock_lsl_stream.py` 发现并连接成功 | 保留 |
| Serial 串口 | 未实现 | 依赖真实硬件，交接文档标注待硬件 | v1.0 不阻塞 |
| Marker 标记 | 需验证 | API 与前端面板存在，非核心链路 | v1.0 可放后 |
| Classifier 在线分类器 | 需验证 | API 与前端面板存在，非核心链路 | v1.0 可放后 |
| Paradigm 范式 | 需验证 | API 与前端面板存在，非核心链路 | v1.0 可放后 |
| 授权系统 | 未实现 | Phase 4 待办 | v1.0 不做 |
| Tauri 桌面打包 | 未实现 | Phase 3 待办 | v1.0 不做 |
| API 认证 | 未实现 | 待办项 | v1.0 只记录风险 |
| 日志脱敏 | 未实现 | 待办项，涉及隐私风险 | v1.0 发布前评估 |

## 最小验证样本

| 类型 | 样本 | 选择理由 | 验证目标 |
|---|---|---|---|
| Mock | `MockDataSource(n_channels=8, fs=500)` | 默认数据源，已能生成 8 通道帧 | 页面默认打开、波形、频段、情绪、质量 |
| CSV | `data/sample_eeg_8ch_500hz_30s.csv` | 8 通道、500Hz、30 秒，加载结果稳定 | 上传、解析、回放、波形、频谱、导出 |
| EDF | `data/test_valid_8ch.edf` | 8 通道、500Hz、约 312 秒，加载结果稳定 | 上传、解析、回放、Topomap、导出 |
| LSL | `backend/mock_lsl_stream.py` | 本地 8 通道 500Hz 模拟 LSL 流 | 流发现、连接、实时波形 |

补充样本：

- `data/test_artifact.edf`：适合专门验证伪迹检测，时长只有 1 秒，不作为主链路样本。
- `data/test_10ch.edf`：适合后续验证多于 8 通道的兼容性，不作为 v1.0 主样本。
- `data/sample_eeg_8ch_60s.csv`：实际解析为 9 通道且时长约 7.68 秒，不作为主样本。

## v1.0 最小完整链路

1. 启动后端，打开首页。
2. 使用 Mock 默认数据源，确认 WebSocket 连接、波形、频段、情绪、质量正常更新。
3. 上传 `data/sample_eeg_8ch_500hz_30s.csv`，确认解析成功并切换到文件源。
4. 验证 CSV 回放：波形变化、PSD、频段统计、频谱瀑布图、伪迹栏、信号质量。
5. 上传 `data/test_valid_8ch.edf`，重复文件源验证。
6. 启动 `backend/mock_lsl_stream.py`，在前端 LSL 对话框发现并连接模拟流。
7. 导出 CSV，确认下载文件可打开且包含通道数据。
8. 导出 PDF，确认生成报告且无后端 500。
9. 记录发现的问题，只修核心链路阻塞项。

## 本地完整验证记录

验证时间：2026-05-27

验证工具：

- `browser-act-cli 0.1.19` 已安装。
- 使用本地后端临时端口 `8095`。
- 使用 headless Chrome 执行浏览器端链路验证。

验证结果：

| 验证项 | 结果 | 证据 |
|---|---|---|
| Mock / WebSocket / 波形 / 频段 / 情绪 / 质量 / 伪迹栏 | 通过 | `rawShape=[8,64]`，WebSocket `Connected`，`latestBands` / `latestEmotion` 存在 |
| PSD / 频段统计 / Topomap / 频谱 | 通过 | `psdLen=103`，`bandStatsChannels=8`，Topomap 与时频图图片已加载 |
| CSV 上传回放 | 通过 | `data/sample_eeg_8ch_500hz_30s.csv` 上传后文件源回放 8 通道 |
| EDF 上传回放 | 通过 | `data/test_valid_8ch.edf` 上传后文件源回放 8 通道 |
| LSL 模拟流 | 通过 | 发现 `Mock-EEG-8ch`，连接状态 `ok`，无 JSON 解析异常 |
| CSV 导出 | 通过 | 返回 200，`text/csv`，3097 bytes |
| PDF 导出 | 通过 | 返回 200，`application/pdf`，144736 bytes |
| 运行时异常 / 后端 5xx | 通过 | 0 条运行时异常或 5xx |

## 本地完整复测记录

验证时间：2026-05-28

验证工具：

- 使用项目虚拟环境 `backend/venv`。
- 使用本地后端临时端口 `8098`。
- 使用 headless Chrome DevTools Protocol 执行浏览器端链路验证。

验证结果：

| 验证项 | 结果 | 证据 |
|---|---|---|
| Mock / WebSocket / 波形 / 频段 / 情绪 / 质量 / 伪迹栏 | 通过 | `rawShape=[8,64]`，WebSocket `Connected`，`latestBands` / `latestEmotion` 存在，质量状态可显示 |
| PSD / 频段统计 / Topomap / 频谱 | 通过 | `psdLen=103`，`bandStatsChannels=8`，Topomap 与时频图已加载 |
| CSV 上传回放 | 通过 | `data/sample_eeg_8ch_500hz_30s.csv` 上传返回 200，回放 8 通道，频段统计 8 通道 |
| EDF 上传回放 | 通过 | `data/test_valid_8ch.edf` 上传返回 200，回放 8 通道，频段统计 8 通道 |
| LSL 模拟流 | 通过 | `backend/mock_lsl_stream.py` 发现 `Mock-EEG-8ch`，连接后 WebSocket 继续推送 8 通道 |
| CSV 导出 | 通过 | 返回 200，`text/csv`，3097 bytes |
| PDF 导出 | 通过 | 返回 200，`application/pdf`，144805 bytes |
| 运行时异常 / 后端 5xx | 通过 | 0 条 JavaScript 异常；干净上传回归中 0 条网络失败 |

本轮修复记录：

- 上传失败时先检查 `response.ok`，避免 HTML 错误页被当 JSON 解析。
- 伪迹栏 DOM 写入增加 null 防护，避免元素缺失时报错。
- `epoch` / `artifact` 两个后端分析接口使用 `asyncio.to_thread()`，避免阻塞事件循环。
- WebSocket payload 发送前清理 `NaN` / `Inf`，避免前端 `JSON.parse` 失败。
- PDF 报告导出兼容 `valence="calibrating"` 等非数值情绪状态。
- PSD / 频段统计修正 `raw_data` 拼接方向，避免把 64 个采样点误识别为 64 个通道。
- 频段统计表兼容后端 `channels` 返回结构，确保前端表格可显示。

## 服务器只读差异检查记录

检查时间：2026-05-27

检查范围：

- 服务器：`ubuntu@43.136.117.175`
- 线上目录：`/var/www/neuroviz`
- 关键文件：`backend/app.py`、`backend/processors/report.py`、`frontend/index.html`

检查结论：

- `/var/www/neuroviz` 是线上 Nginx 使用目录，但不是 Git 仓库。
- 线上首页内容与 `/var/www/neuroviz/frontend/index.html` 一致。
- 服务器三份关键文件整体落后于本地 v1.0 修复，不应整体反向覆盖本地。
- 已保留服务器中对 v1.0 有价值的线上改动：HTTPS 页面自动使用 `wss://`，上传文件解析放入后台线程。
- 未合并服务器调试 `print`、旧 PSD 转置逻辑、旧 PDF 情绪格式化逻辑、旧伪迹栏 DOM 写法。

## 下一轮建议

本地 v1.0 核心链路已在 2026-05-28 复测通过，服务器有效差异已小步合并到本地。下一阶段建议确认是否 push GitHub；push 后再制定服务器部署/回滚步骤。
