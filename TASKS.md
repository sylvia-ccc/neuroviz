# NeuroViz 任务清单

> 每个任务 ≤ 20分钟，产出可验证
> ✅=已完成 🔄=进行中 ⬜=待做

---

## 已完成

- ✅ T0. 项目目录结构 + FastAPI后端骨架
- ✅ T0. MockDataSource(3场景: relax/focus/blink)
- ✅ T0. EmotionEngine(频段/效价/专注/放松)
- ✅ T0. WebSocket数据管道(后端→前端20fps)
- ✅ T0. 前端index.html(波形+频段柱状图+指标卡)
- ✅ T0. numpy 2.x trapz→trapezoid修复

---

## Phase 1: MVP投资人演示版 ✅ 完成

### Step 1 — 修复+补全基础Widget (4个任务)

- ✅ T1. 修复前端波形渲染
- ✅ T2. 修复频段柱状图渲染
- ✅ T3. 专注度/放松度进度条
- ✅ T4. 效价指示器

### Step 2 — 情绪四象限 (1个任务)

- ✅ T5. Russell情绪四象限Canvas

### Step 3 — 3D脑热力图 (5个任务)

- ✅ T6. Three.js场景初始化
- ✅ T7. 程序化3D脑模型
- ✅ T8. 电极标记点
- ✅ T9. 高斯插值+颜色映射
- ✅ T10. 频段切换按钮

### Step 4 — 场景控制+打磨 (3个任务)

- ✅ T11. 场景手动切换按钮
- ✅ T12. 暗色主题统一+布局优化
- ✅ T13. 投资人Demo模式

---

## Phase 2: 多通道产品化 (6 tasks)

- ✅ T14. 多通道波形(8ch)
  - drawWave()支持动态通道数(nCh = latestRawData.length)
  - 每通道高度自动分配(chH = h / nCh)
  - 颜色循环(12色)
  - 通道分隔线+零线+标签
  - 通道面板(点击"通道"按钮显示, 可隐藏/显示通道)
  - hiddenChannels Set控制显示/隐藏
  - 验证: 后端改为8通道Mock → 前端显示8条波形, 可切换隐藏

- ✅ T15. 2D脑地形图Topomap
  - 后端: `processors/topomap.py` (matplotlib+scipy插值)
  - 支持2电极(nearest)、≥3电极(cubic/linear自动选择)
  - 每2秒(40帧)生成一次, base64推送
  - 前端: `<img id="img-topomap">` 接收并显示
  - 验证: WebSocket消息40包含topomap(62156 chars)

- ✅ T16. 频谱瀑布图
  - 时间×频率×功率 伪彩色图
  - 后端: `processors/spectrogram.py` (FFT+历史矩阵)
  - 前端: Canvas绘制, 颜色映射蓝→红
  - 验证: ✅ 后端推送正常, 前端绘制代码完成

- ✅ T17. 文件回放(EDF/CSV)
  - POST /api/upload 上传EDF/CSV
  - FileDataSource类(支持EDF需mne, CSV纯文本)
  - POST /api/source/switch 切换mock/file
  - GET /api/source/status 查询状态
  - 前端加数据源控制条(上传/切换Mock/文件)
  - 验证: 上传CSV→切换文件源→看到文件数据回放

- 🔄 T18. 串口数据源(EEG102板子)
  - SerialDataSource类(框架完成, 等待板子到货)
  - pyserial读取USB串口
  - API: /api/serial/ports, /connect, /disconnect
  - 前端数据源控制条加串口按钮+端口选择+连接按钮
  - 验证(等待板子): 连接→看到真实脑波

- ⬜ T19. 多通道3D热力图(8电极)
  - 10-20系统电极坐标
  - 3D脑模型上标记8个电极位置
  - 高斯插值扩展到8通道
  - 验证: 8个电极小球, 插值着色平滑

---

## Phase 3: 商业化 (5 tasks)

- ⬜ T20. 功能连接矩阵
- 🔄 T21. 伪迹检测提示 (后端完成，前端集成完成，待验证)
- ⬜ T22. PDF报告导出
- ⬜ T23. Tauri桌面打包
- ⬜ T24. 授权系统(免费/Pro)

## Phase 4: 脑波解读 (4 tasks)

- ✅ T25. EDF自动解析+脑区映射
- ⬜ T26. CSV配置向导
- ⬜ T27. 设备模板选择器
- ⬜ T28. 信号质量实时提示

---

## 执行顺序

```
Phase 1 (13 tasks): T1→T2→T3→T4→T5→T6→T7→T8→T9→T10→T11→T12→T13
                                                              ↓
                                                    ✅ Phase 1 完成

Phase 2 (6 tasks):  T14→T15→T16→T17→T18→T19
                                                         ↓
                                            进行中: T18准备(串口框架)
```
