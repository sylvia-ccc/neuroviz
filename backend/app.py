"""
NeuroViz 后端主入口
FastAPI + WebSocket 实时数据推送
"""

import asyncio
import json
import os
import sys
import time
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

# 添加backend目录到路径
BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(BACKEND_DIR))

# 数据源
from data_sources.mock import MockDataSource
from data_sources.file_source import FileDataSource
from data_sources.serial_source import SerialDataSource

# 信号处理
from processors.emotion import EmotionEngine
from processors import topomap as topomap_module
from processors.spectrogram import SpectrogramProcessor
from processors.preprocessing import Preprocessor
from processors.report import export_csv, export_pdf
from processors.timefreq import TimeFreqProcessor

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

app = FastAPI(title="NeuroViz")

# 静态文件
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传EDF/CSV文件, 创建FileDataSource"""
    global file_source, data_source, current_source_type
    
    # 保存文件
    upload_dir = BASE_DIR.parent / "data"
    upload_dir.mkdir(exist_ok=True)
    file_path = upload_dir / file.filename
    
    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        print(f"[NeuroViz] 文件已保存: {file_path}")
    except Exception as e:
        return {"error": f"保存失败: {e}"}
    
    # 创建FileDataSource
    try:
        file_source = FileDataSource(str(file_path), fs_target=500)
        info = file_source.get_info()
        
        # 切换到文件源
        data_source = file_source
        current_source_type = "file"
        
        print(f"[NeuroViz] 已切换到文件源: {file.filename}")
        return {
            "status": "ok",
            "filename": file.filename,
            "info": info,
        }
    except Exception as e:
        return {"error": f"加载文件失败: {e}"}


@app.post("/api/source/switch")
async def switch_source(body: dict):
    """切换数据源: {"type": "mock"|"file"} """
    global data_source, mock_source, file_source, current_source_type, emotion_engine
    
    src_type = body.get("type", "mock")
    
    if src_type == "mock":
        if mock_source is None:
            mock_source = MockDataSource(n_channels=body.get("n_channels", 8), fs=500)
        data_source = mock_source
        current_source_type = "mock"
        print("[NeuroViz] 已切换到Mock数据源")
        return {"status": "ok", "source": "mock"}
    
    elif src_type == "file":
        if file_source is None:
            return {"error": "请先上传文件"}
        data_source = file_source
        current_source_type = "file"
        # 重置情绪引擎(通道数可能变化)
        emotion_engine = EmotionEngine(fs=file_source.fs)
        print("[NeuroViz] 已切换到文件数据源")
        return {"status": "ok", "source": "file"}
    
    return {"error": f"未知数据源: {src_type}"}


@app.get("/api/source/status")
async def get_source_status():
    """获取当前数据源状态"""
    global data_source, current_source_type, file_source
    info = {
        "type": current_source_type,
        "has_file": file_source is not None,
    }
    if file_source:
        info["file_info"] = file_source.get_info()
    return info


# ===== 串口数据源 API =====
serial_source = None  # 串口数据源

@app.get("/api/serial/ports")
async def list_serial_ports():
    """列出所有可用串口"""
    from data_sources.serial_source import SerialDataSource
    ports = SerialDataSource.list_ports()
    return {"ports": ports}

@app.post("/api/serial/connect")
async def connect_serial(body: dict):
    """连接串口: {"port": "/dev/ttyUSB0", "baudrate": 115200}"""
    global serial_source, data_source, current_source_type, emotion_engine
    
    port = body.get("port", "")
    baudrate = body.get("baudrate", 115200)
    
    if not port:
        return {"error": "未指定串口"}
    
    serial_source = SerialDataSource(port=port, baudrate=baudrate)
    if serial_source.connect():
        data_source = serial_source
        current_source_type = "serial"
        emotion_engine = EmotionEngine(fs=serial_source.fs_target)
        print(f"[NeuroViz] 已切换到串口源: {port}")
        return {"status": "ok", "port": port, "info": serial_source.get_info()}
    else:
        return {"error": f"连接失败: {port}"}

@app.post("/api/serial/disconnect")
async def disconnect_serial():
    """断开串口"""
    global serial_source, data_source, current_source_type, mock_source
    
    if serial_source:
        serial_source.disconnect()
        serial_source = None
    
    # 切换回mock
    if mock_source is None:
        mock_source = MockDataSource(n_channels=body.get("n_channels", 8), fs=500)
    data_source = mock_source
    current_source_type = "mock"
    
    return {"status": "ok", "message": "已断开串口, 切换回Mock"}


# 全局状态
connected_clients: list[WebSocket] = []
data_source = None  # 当前活跃数据源
mock_source = None   # Mock数据源(缓存)
file_source = None   # 文件数据源
serial_source = None  # 串口数据源
emotion_engine = None
preprocessor = None  # 预处理模块
timefreq_processor = None  # 时频分析模块
current_source_type = "mock"  # mock | file | serial


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global data_source, emotion_engine, mock_source, file_source, current_source_type
    
    await ws.accept()
    connected_clients.append(ws)
    print(f"[NeuroViz] 客户端连接, 当前{len(connected_clients)}个")
    
    try:
        # 初始化数据源(如果未初始化)
        if data_source is None:
            mock_source = MockDataSource(n_channels=8, fs=500)
            data_source = mock_source
            current_source_type = "mock"
        
        # 确保emotion_engine已初始化
        if emotion_engine is None:
            emotion_engine = EmotionEngine(fs=data_source.fs)
        
        # 确保preprocessor已初始化
        global preprocessor
        if preprocessor is None:
            preprocessor = Preprocessor(fs=data_source.fs)
        
        # 初始化时频分析器
        global timefreq_processor
        if timefreq_processor is None:
            timefreq_processor = TimeFreqProcessor(fs=data_source.fs)
        
        # 确保spectrogram_processor已初始化
        global spectrogram_processor
        if 'spectrogram_processor' not in globals() or spectrogram_processor is None:
            spectrogram_processor = SpectrogramProcessor(fs=data_source.fs)
        
        # 发送配置信息
        await ws.send_json({
            "type": "config",
            "n_channels": data_source.n_channels,
            "fs": data_source.fs,
            "channel_names": data_source.channel_names,
            "source_type": current_source_type,
        })
        
        # 持续推送数据
        send_counter = 0  # Topomap计数器
        timefreq_ch_idx = 0  # 时频图通道索引（可动态切换）
        while True:
            # 非阻塞接收客户端消息
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=0.01)
                data = json.loads(msg)
                if data.get("action") == "set_scene":
                    scene = data.get("scene")
                    if scene in ("relax", "focus", "blink"):
                        data_source.set_scene(scene)
                        print(f"[NeuroViz] 客户端切换场景 → {scene}")
                elif data.get("type") == "config":
                    if "timefreq_ch" in data:
                        timefreq_ch_idx = int(data["timefreq_ch"])
                        print(f"[NeuroViz] 时频图通道切换 → Ch{timefreq_ch_idx}")
            except asyncio.TimeoutError:
                pass
            except Exception:
                break

            # 读取一帧数据
            frame = data_source.read_frame()
            
            # 预处理（陷波 + 带通 + 伪迹去除）
            if preprocessor is not None:
                raw_clean = preprocessor.process(frame["raw"])
                frame["raw"] = raw_clean
                frame["ch1"] = raw_clean[0] if raw_clean.shape[0] > 0 else frame["ch1"]
                frame["ch2"] = raw_clean[1] if raw_clean.shape[0] > 1 else (raw_clean[0] if raw_clean.shape[0] > 0 else frame["ch2"])
            
            # 情绪分析
            features = emotion_engine.analyze(frame["ch1"], frame["ch2"])
            
            # 多通道频段功率（用于3D脑图）
            try:
                if hasattr(emotion_engine, 'compute_all_channels'):
                    ch_bands = emotion_engine.compute_all_channels(frame["raw"])
                    payload['channel_bands'] = [ {k: float(v) for k,v in ch.items()} for ch in ch_bands ]
            except Exception as e:
                print(f"[NeuroViz] compute_all_channels 失败: {e}")
            
            # 组装推送数据（波形只推64点降采样）
            raw = frame["raw"]
            step = max(1, raw.shape[1] // 64)
            raw_down = raw[:, ::step]
            
            payload = {
                "type": "eeg",
                "ts": time.time(),
                "channels": frame["channels"],
                "raw": raw_down.tolist(),
                "features": features,
                "scene": frame.get("scene", "relax"),
            }
            
            # 频谱瀑布图更新(添加spectrogram字段到payload)
            if 'spectrogram_processor' in globals() and spectrogram_processor:
                spectrogram_processor.update(frame["ch1"], frame["ch2"])
                spec_norm = spectrogram_processor.normalize(spectrogram_processor.get_latest())
                payload['spectrogram'] = spec_norm.tolist()
            
            # Topomap推送(每2秒=40帧×0.05秒)
            send_counter += 1
            if send_counter % 40 == 0:
                print(f'[NeuroViz] Topomap触发: send_counter={send_counter}, mod={send_counter%40}, topomap_module={topomap_module}')
            if send_counter % 40 == 0 and topomap_module:
                print(f'[NeuroViz] 进入40帧触发块: send_counter={send_counter}')
                try:
                    # 构造topomap数值(使用alpha频段)
                    values = {}
                    if 'bands_ch1' in features and 'bands_ch2' in features:
                        values['Fp1'] = features['bands_ch1'].get('alpha', 0.0)
                        values['Fp2'] = features['bands_ch2'].get('alpha', 0.0)
                        print(f'[NeuroViz] values={values}')
                    
                    if len(values) >= 2:
                        topomap_b64 = await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: topomap_module.generate_topomap_base64(
                                values,
                                title=f"Alpha Power ({data_source.fs}Hz)",
                            )
                        )
                        payload['topomap'] = topomap_b64
                        
                        # 时频分析（使用通道 0）
                        try:
                            timefreq_b64 = await asyncio.get_event_loop().run_in_executor(
                                None,
                                lambda: timefreq_processor.compute(frame["raw"], ch_idx=timefreq_ch_idx)
                            )
                            payload['timefreq'] = timefreq_b64
                            print(f'[NeuroViz] TimeFreq已生成: {len(timefreq_b64)} chars')
                        except Exception as e:
                            print(f"[NeuroViz] TimeFreq Error: {e}")
                        print(f"[NeuroViz] Topomap已生成: {len(topomap_b64)} chars")
                except Exception as e:
                    print(f"[NeuroViz] Topomap生成失败: {e}")
                    import traceback; traceback.print_exc()
            
            try:
                await ws.send_json(payload)
            except Exception:
                break
            await asyncio.sleep(0.05)  # 20fps推送
            
    except WebSocketDisconnect:
        connected_clients.remove(ws)
        print(f"[NeuroViz] 客户端断开, 当前{len(connected_clients)}个")
    except Exception as e:
        print(f"[NeuroViz] WebSocket错误: {type(e).__name__}: {e}")
        import traceback; traceback.print_exc()
        if ws in connected_clients:
            connected_clients.remove(ws)


# 导出端点
from fastapi.responses import FileResponse
import tempfile
from datetime import datetime

@app.post("/api/export/csv")
async def export_csv_endpoint(body: dict):
    """导出CSV"""
    raw = np.array(body["raw"], dtype=np.float32)
    channels = body.get("channels", [f"Ch{i}" for i in range(raw.shape[0])])
    fs = body.get("fs", 500)
    
    # 生成临时文件
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, dir="/tmp")
    path = tmp.name
    tmp.close()
    
    export_csv(raw, channels, fs, path)
    
    return FileResponse(
        path=path,
        filename=f"neuroviz_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        media_type="text/csv"
    )

@app.post("/api/export/pdf")
async def export_pdf_endpoint(body: dict):
    """导出PDF报告"""
    raw = np.array(body["raw"], dtype=np.float32)
    features = body.get("features", {})
    fs = body.get("fs", 500)
    
    # 生成临时文件
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".pdf", delete=False, dir="/tmp")
    path = tmp.name
    tmp.close()
    
    export_pdf(raw, features, path, fs)
    
    return FileResponse(
        path=path,
        filename=f"neuroviz_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        media_type="application/pdf"
    )


if __name__ == "__main__":
    import uvicorn
    print("=" * 40)
    print("  🧠 NeuroViz 启动中...")
    print("  http://localhost:8080")
    print("=" * 40)
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")
