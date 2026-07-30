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
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path

# 添加backend目录到路径
BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(BACKEND_DIR))

# 数据源
from data_sources.mock import MockDataSource
from data_sources.file_source import FileDataSource
from data_sources.serial_source import SerialDataSource
from data_sources.lsl_source import LSLDataSource, list_lsl_streams

# 信号处理
from processors.emotion import EmotionEngine
from processors import topomap as topomap_module
from processors.spectrogram import SpectrogramProcessor
from processors.preprocessing import Preprocessor
from processors.report import export_csv, export_pdf
from processors.timefreq import TimeFreqProcessor
from processors.quality import QualityDetector
from processors.psd import compute_psd_multi, compute_stats_multi, BANDS, REF_RANGES
from processors.epoch import Epocher, compute_epoch_trend
from processors.artifact import ArtifactDetector
from processors.topomap import generate_topomap_base64, generate_topomap_base64_from_array
from processors.markers import marker_manager, MarkerManager, LSLMarkerReceiver
from processors.classifier import OnlineClassifier, BCIManager
from processors.connectivity import ConnectivityProcessor

# 范式设计器
from paradigm import router as paradigm_router

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"


def _json_safe(value):
    """Convert numpy values and non-finite floats into strict JSON-safe data."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float):
        return value if np.isfinite(value) else 0.0
    return value

async def _send_topomap_now(ws, current_payload, frame, features, data_source, topomap_module, timefreq_ch_idx=0):
    """立即生成并推送Topomap（不受40帧间隔限制）"""
    try:
        electrode_names = ['Fp1','Fp2','F7','F3','F4','F8','T7','T8','C3','C4','P7','P3','P4','P8','O1','O2']
        ch_bands = current_payload.get('channel_bands', [])
        values = {}
        if ch_bands:
            for i, ch_data in enumerate(ch_bands):
                if i < len(electrode_names):
                    values[electrode_names[i]] = ch_data.get('alpha', 0.0)
        elif 'bands_ch1' in features and 'bands_ch2' in features:
            values['Fp1'] = features['bands_ch1'].get('alpha', 0.0)
            values['Fp2'] = features['bands_ch2'].get('alpha', 0.0)
        
        if len(values) >= 2:
            loop = asyncio.get_event_loop()
            topomap_b64 = await loop.run_in_executor(
                None,
                lambda: topomap_module.generate_topomap_base64(values, title="Alpha Power")
            )
            msg = json.dumps({**current_payload, 'type': 'eeg', 'topomap': topomap_b64})
            await ws.send_text(msg)
            print(f"[NeuroViz] Topomap立即推送: {len(topomap_b64)} chars")
    except Exception as e:
        print(f"[NeuroViz] _send_topomap_now失败: {e}")


def _generate_artifact_tips(artifact_result: dict) -> list:
    """根据伪迹检测结果生成用户提示"""
    tips = []
    summary = artifact_result.get("summary", {})
    
    # 眨眼伪迹
    blink_count = summary.get("blink", 0)
    if blink_count > 3:
        tips.append("👁️ 检测到频繁眨眼，建议放松眼部或闭眼采集")
    elif blink_count > 0:
        tips.append(f"👁️ 检测到{blink_count}次眨眼伪迹，数据基本可用")
    
    # 眼动伪迹
    eog_count = summary.get("eog", 0)
    if eog_count > 2:
        tips.append("👀 检测到眼动伪迹，建议减少眼球转动")
    
    # 肌电伪迹
    emg_count = summary.get("emg", 0)
    if emg_count > 5:
        tips.append("💪 检测到大量肌电干扰，建议放松面部和颈部肌肉")
    elif emg_count > 0:
        tips.append(f"💪 检测到{emg_count}处肌电干扰，注意放松")
    
    # 移动伪迹
    move_count = summary.get("movement", 0)
    if move_count > 0:
        tips.append("🚶 检测到移动伪迹，采集时请保持静止")
    
    # 信号质量评估
    total = artifact_result.get("total_artifacts", 0)
    if total == 0:
        tips.append("✅ 信号质量良好，无显著伪迹")
    elif total > 10:
        tips.append("⚠️ 信号质量较差，建议检查电极接触或重新采集")
    
    return tips


app = FastAPI(title="NeuroViz")

# 注册范式设计器路由
app.include_router(paradigm_router)

# 静态文件
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传EDF/CSV文件, 创建FileDataSource，返回详细解析结果"""
    global file_source, data_source, current_source_type, emotion_engine
    
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
        file_source = await asyncio.to_thread(FileDataSource, str(file_path), fs_target=500)
        info = file_source.get_info()
        
        # 增强返回信息：脑区映射 + 信号质量评估
        enhanced_info = _enhance_file_info(info)
        
        # 切换到文件源
        data_source = file_source
        current_source_type = "file"
        # 重置情绪引擎
        emotion_engine = EmotionEngine(fs=file_source.fs)
        
        print(f"[NeuroViz] 已切换到文件源: {file.filename}")
        return {
            "status": "ok",
            "filename": file.filename,
            "info": enhanced_info,
        }
    except Exception as e:
        return {"error": f"加载文件失败: {e}"}


def _map_brain_region(ch_name: str) -> dict:
    """通道名→脑区映射，返回脑区信息"""
    ch = ch_name.strip().upper()
    # 标准10-20系统映射
    brain_regions = {
        # 前额叶
        "FP1": {"region": "Frontal Pole", "zone": "前额叶", "function": "执行功能、决策", "color": "#FF6B6B"},
        "FP2": {"region": "Frontal Pole", "zone": "前额叶", "function": "执行功能、决策", "color": "#FF6B6B"},
        "FPZ": {"region": "Frontal Pole", "zone": "前额叶", "function": "执行功能、决策", "color": "#FF6B6B"},
        # 额叶
        "F7": {"region": "Frontal", "zone": "左额叶", "function": "语言处理、情绪", "color": "#FFA07A"},
        "F8": {"region": "Frontal", "zone": "右额叶", "function": "语言处理、情绪", "color": "#FFA07A"},
        "F3": {"region": "Frontal", "zone": "左额叶", "function": "运动规划", "color": "#FFA07A"},
        "F4": {"region": "Frontal", "zone": "右额叶", "function": "运动规划", "color": "#FFA07A"},
        "FZ": {"region": "Frontal", "zone": "额叶中线", "function": "运动准备", "color": "#FFA07A"},
        # 中央
        "C3": {"region": "Central", "zone": "左中央", "function": "感觉运动", "color": "#98D8C8"},
        "C4": {"region": "Central", "zone": "右中央", "function": "感觉运动", "color": "#98D8C8"},
        "CZ": {"region": "Central", "zone": "中央中线", "function": "感觉运动", "color": "#98D8C8"},
        # 颞叶
        "T7": {"region": "Temporal", "zone": "左颞叶", "function": "听觉、记忆", "color": "#87CEEB"},
        "T8": {"region": "Temporal", "zone": "右颞叶", "function": "听觉、记忆", "color": "#87CEEB"},
        "T3": {"region": "Temporal", "zone": "左颞叶", "function": "听觉、记忆", "color": "#87CEEB"},
        "T4": {"region": "Temporal", "zone": "右颞叶", "function": "听觉、记忆", "color": "#87CEEB"},
        "T5": {"region": "Temporal", "zone": "左颞叶", "function": "视觉记忆", "color": "#87CEEB"},
        "T6": {"region": "Temporal", "zone": "右颞叶", "function": "视觉记忆", "color": "#87CEEB"},
        # 顶叶
        "P7": {"region": "Parietal", "zone": "左顶叶", "function": "空间感知", "color": "#DDA0DD"},
        "P8": {"region": "Parietal", "zone": "右顶叶", "function": "空间感知", "color": "#DDA0DD"},
        "P3": {"region": "Parietal", "zone": "左顶叶", "function": "感觉整合", "color": "#DDA0DD"},
        "P4": {"region": "Parietal", "zone": "右顶叶", "function": "感觉整合", "color": "#DDA0DD"},
        "PZ": {"region": "Parietal", "zone": "顶叶中线", "function": "感觉整合", "color": "#DDA0DD"},
        # 枕叶
        "O1": {"region": "Occipital", "zone": "左枕叶", "function": "视觉处理", "color": "#9370DB"},
        "O2": {"region": "Occipital", "zone": "右枕叶", "function": "视觉处理", "color": "#9370DB"},
        "OZ": {"region": "Occipital", "zone": "枕叶中线", "function": "视觉处理", "color": "#9370DB"},
        "PO3": {"region": "Parieto-Occipital", "zone": "左顶枕", "function": "视觉空间", "color": "#9370DB"},
        "PO4": {"region": "Parieto-Occipital", "zone": "右顶枕", "function": "视觉空间", "color": "#9370DB"},
    }
    return brain_regions.get(ch, None)


def _enhance_file_info(info: dict) -> dict:
    """增强文件信息：添加脑区映射和信号质量评估"""
    channels = []
    region_stats = {}
    
    for ch_name in info.get("channel_names", []):
        ch_info = {
            "name": ch_name,
            "type": _detect_channel_type(ch_name),
        }
        # 脑区映射
        brain = _map_brain_region(ch_name)
        if brain:
            ch_info["brain_region"] = brain["zone"]
            ch_info["function"] = brain["function"]
            ch_info["color"] = brain["color"]
            # 统计各脑区通道数
            region = brain["zone"]
            region_stats[region] = region_stats.get(region, 0) + 1
        else:
            ch_info["brain_region"] = "未知"
            ch_info["function"] = "未识别"
            ch_info["color"] = "#808080"
        channels.append(ch_info)
    
    # 信号质量评估（基于已知通道）
    known_channels = sum(1 for c in channels if c["brain_region"] != "未知")
    total_channels = len(channels)
    quality = "excellent" if known_channels == total_channels else ("good" if known_channels > total_channels // 2 else "unknown")
    
    # 生成解读建议
    suggestion = _generate_suggestion(info, channels, region_stats)
    
    return {
        **info,
        "channels": channels,
        "region_stats": region_stats,
        "quality": quality,
        "suggestion": suggestion,
    }


def _detect_channel_type(ch_name: str) -> str:
    """检测通道类型：EEG、EOG、EMG、ECG等"""
    ch = ch_name.upper()
    if ch.startswith("EOG"): return "EOG (眼电)"
    if ch.startswith("EMG"): return "EMG (肌电)"
    if ch.startswith("ECG") or ch.startswith("EKG"): return "ECG (心电)"
    if ch.startswith("REF") or ch.startswith("REF"): return "参考电极"
    if any(x in ch for x in ["EOG", "EMG", "ECG", "EKG", "TRIG", "MARK"]): return "其他"
    # 10-20系统默认是EEG
    if len(ch) <= 4 and any(c.isalpha() for c in ch): return "EEG"
    return "EEG"


def _generate_suggestion(info: dict, channels: list, region_stats: dict) -> dict:
    """基于文件分析生成解读建议"""
    n_ch = len(channels)
    duration = info.get("duration_sec", 0)
    fs = info.get("fs", 500)
    
    suggestion = {
        "summary": "",
        "features": [],
        "tips": [],
    }
    
    # 通道数分析
    if n_ch <= 2:
        suggestion["summary"] = "检测到前额叶脑电数据，适合基础放松/专注度分析"
        suggestion["features"].append("⚡ 通道数较少，建议配合引导式校准获取更准确解读")
    elif n_ch <= 8:
        suggestion["summary"] = "检测到多通道脑电数据，可分析脑区活跃模式和区域间协调性"
        suggestion["features"].append("🎯 可分析前额叶、额叶、颞叶等多个脑区的活跃状态")
    else:
        suggestion["summary"] = "检测到专业级多通道脑电数据，支持完整的脑区分析和连接性研究"
        suggestion["features"].append("🧠 建议进行功能连接分析和ICA伪迹去除")
    
    # 脑区覆盖分析
    regions_coverage = list(region_stats.keys())
    if "前额叶" in regions_coverage:
        suggestion["tips"].append("✅ 前额叶覆盖完整，适合专注度和情绪分析")
    if "枕叶" in regions_coverage or "左枕叶" in regions_coverage:
        suggestion["tips"].append("✅ 枕叶覆盖，可检测Alpha波（闭眼休息状态）")
    if "左中央" in regions_coverage or "右中央" in regions_coverage:
        suggestion["tips"].append("✅ 中央区覆盖，可分析感觉运动节律(Mu波)")
    
    # 时长分析
    if duration < 60:
        suggestion["tips"].append("📊 记录时长较短(<1分钟)，建议至少采集5分钟以获得稳定基线")
    elif duration < 300:
        suggestion["tips"].append("📊 记录时长适中(1-5分钟)，适合快速分析")
    else:
        suggestion["tips"].append("📊 记录时长充足(>5分钟)，建议进行完整的时序分析")
    
    # 采样率分析
    if fs < 250:
        suggestion["tips"].append("⚠️ 采样率偏低({}Hz)，低频分析可能受限，建议250Hz以上".format(fs))
    elif fs < 500:
        suggestion["tips"].append("📈 采样率{}Hz，满足基础分析需求".format(fs))
    else:
        suggestion["tips"].append("✅ 采样率{}Hz充足，支持高质量频谱分析".format(fs))
    
    return suggestion


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


@app.get("/api/datasets")
async def list_datasets():
    """列出 data/ 目录下所有可用数据集"""
    data_dir = BASE_DIR.parent / "data"
    datasets = []

    if data_dir.exists():
        for f in sorted(data_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in ('.edf', '.bdf', '.gdf', '.vhdr', '.csv'):
                size_mb = f.stat().st_size / (1024 * 1024)
                # 快速探测文件信息（不加载全部数据）
                info = {"filename": f.name, "path": str(f), "size_mb": round(size_mb, 1), "format": f.suffix.lower()}

                if f.suffix.lower() == '.edf':
                    try:
                        import mne as _mne
                        raw = _mne.io.read_raw_edf(str(f), preload=False, verbose="ERROR")
                        info["n_channels"] = raw.info['nchan']
                        info["fs"] = int(raw.info['sfreq'])
                        info["duration_sec"] = round(raw.n_times / raw.info['sfreq'], 1)
                        info["channel_names"] = raw.ch_names[:8]
                        info["channel_type"] = "EEG"
                    except Exception:
                        info["error"] = "无法解析"
                elif f.suffix.lower() == '.csv':
                    try:
                        import csv as _csv
                        with open(f, 'r') as fh:
                            reader = _csv.reader(fh)
                            first_row = next(reader)
                            info["n_columns"] = len(first_row)
                            info["format_detail"] = "CSV"
                    except Exception:
                        info["error"] = "无法解析"

                datasets.append(info)

    return {"datasets": datasets, "count": len(datasets)}


@app.post("/api/datasets/load")
async def load_dataset(body: dict):
    """加载 data/ 目录下的已有数据集文件"""
    global file_source, data_source, current_source_type, emotion_engine

    filename = body.get("filename")
    if not filename:
        return {"error": "未指定文件名"}

    file_path = BASE_DIR.parent / "data" / filename
    if not file_path.exists():
        return {"error": f"文件不存在: {filename}"}

    try:
        file_source = await asyncio.to_thread(FileDataSource, str(file_path), fs_target=500)
        info = file_source.get_info()
        enhanced_info = _enhance_file_info(info)

        data_source = file_source
        current_source_type = "file"
        emotion_engine = EmotionEngine(fs=file_source.fs)

        print(f"[NeuroViz] 加载数据集: {filename}")
        return {"status": "ok", "filename": filename, "info": enhanced_info}
    except Exception as e:
        return {"error": f"加载失败: {e}"}


# ===== 串口数据源 API =====
serial_source = None  # 串口数据源
lsl_source = None  # LSL数据源

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
        mock_source = MockDataSource(n_channels=8, fs=500)
    data_source = mock_source
    current_source_type = "mock"
    
    return {"status": "ok", "message": "已断开串口, 切换回Mock"}


# ===== LSL数据源 API =====

@app.get("/api/lsl/streams")
async def api_list_lsl_streams():
    """列出当前网络上可用的LSL流"""
    streams = list_lsl_streams(wait_time=2.0)
    return {"streams": streams, "count": len(streams)}

@app.post("/api/lsl/connect")
async def connect_lsl(body: dict):
    """连接LSL流: {"stream_name": "Muse-EEG", "stream_type": "EEG"}"""
    global lsl_source, data_source, current_source_type, emotion_engine
    
    stream_name = body.get("stream_name")  # None则自动发现
    stream_type = body.get("stream_type", "EEG")
    
    try:
        lsl_source = LSLDataSource(
            fs_target=500,
            stream_name=stream_name,
            stream_type=stream_type,
            timeout=5.0
        )
        data_source = lsl_source
        current_source_type = "lsl"
        emotion_engine = EmotionEngine(fs=500)
        print(f"[NeuroViz] 已切换到LSL源: {stream_name or 'auto'}")
        return {"status": "ok", "info": lsl_source.get_info()}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/lsl/disconnect")
async def disconnect_lsl():
    """断开LSL流"""
    global lsl_source, data_source, current_source_type, mock_source
    
    if lsl_source:
        lsl_source.close()
        lsl_source = None
    
    # 切换回mock
    if mock_source is None:
        mock_source = MockDataSource(n_channels=8, fs=500)
    data_source = mock_source
    current_source_type = "mock"
    
    return {"status": "ok", "message": "已断开LSL, 切换回Mock"}


# ===== Marker API =====

@app.get("/api/markers")
async def get_markers(n: int = 50):
    """获取最近n个Marker"""
    return {"markers": marker_manager.get_recent_markers(n)}

@app.post("/api/markers/add")
async def add_marker(body: dict):
    """添加Marker"""
    marker = marker_manager.add_marker(
        name=body.get("name", "event"),
        value=body.get("value", 0),
        duration=body.get("duration", 0.0),
        metadata=body.get("metadata")
    )
    return {"status": "ok", "marker": marker.to_dict()}

@app.post("/api/markers/trial/start")
async def start_trial(body: dict):
    """开始Trial"""
    trial_num = marker_manager.start_trial(
        trial_type=body.get("trial_type", ""),
        metadata=body.get("metadata")
    )
    return {"status": "ok", "trial_num": trial_num}

@app.post("/api/markers/trial/end")
async def end_trial(body: dict):
    """结束Trial"""
    trial_info = marker_manager.end_trial(
        result=body.get("result", ""),
        metadata=body.get("metadata")
    )
    if trial_info:
        return {"status": "ok", "trial": trial_info}
    return {"error": "No active trial"}

@app.post("/api/markers/stimulus")
async def mark_stimulus(body: dict):
    """标记刺激"""
    marker = marker_manager.mark_stimulus(
        stimulus_type=body.get("stimulus_type", ""),
        value=body.get("value", 0)
    )
    return {"status": "ok", "marker": marker.to_dict()}

@app.post("/api/markers/response")
async def mark_response(body: dict):
    """标记响应"""
    marker = marker_manager.mark_response(
        response=body.get("response", ""),
        correct=body.get("correct", False),
        rt_ms=body.get("rt_ms", 0)
    )
    return {"status": "ok", "marker": marker.to_dict()}

@app.get("/api/markers/trials")
async def get_trials():
    """获取所有Trial信息"""
    return {"trials": marker_manager.get_trials()}

@app.get("/api/markers/export")
async def export_markers():
    """导出所有Marker数据"""
    return marker_manager.export_to_dict()

@app.post("/api/markers/clear")
async def clear_markers():
    """清空所有Marker"""
    marker_manager.clear()
    return {"status": "ok"}


# ===== BCI Classifier API =====

bci_manager = None  # 全局BCI管理器

def get_bci_manager(paradigm: str = 'mi'):
    """获取或创建BCI管理器"""
    global bci_manager
    if bci_manager is None or bci_manager.paradigm != paradigm:
        bci_manager = BCIManager(paradigm=paradigm)
    return bci_manager

@app.post("/api/classifier/init")
async def init_classifier(body: dict):
    """初始化分类器: {"paradigm": "mi"}"""
    paradigm = body.get("paradigm", "mi")
    manager = get_bci_manager(paradigm)
    return {"status": "ok", "paradigm": paradigm}

@app.get("/api/classifier/status")
async def classifier_status():
    """获取分类器状态"""
    if bci_manager is None:
        return {"initialized": False}
    
    return {
        "initialized": True,
        "paradigm": bci_manager.paradigm,
        "trained": bci_manager.classifier.is_trained,
        "trial_count": bci_manager.session.trial_count,
        "accuracy": bci_manager.get_accuracy()
    }

@app.post("/api/classifier/train")
async def train_classifier(body: dict):
    """
    训练分类器
    body: {"paradigm": "mi", "data": [[epoch1], [epoch2], ...], "labels": ["left", "right", ...]}
    epoch shape: (n_channels, n_samples)
    """
    paradigm = body.get("paradigm", "mi")
    epochs = body.get("data", [])
    labels = body.get("labels", [])
    
    if len(epochs) == 0 or len(labels) == 0:
        return {"error": "No training data provided"}
    
    manager = get_bci_manager(paradigm)
    fs = 500  # 假设采样率
    
    # 提取特征并训练
    X = []
    for epoch in epochs:
        epoch_arr = np.array(epoch)
        features = manager.classifier.extract_features(epoch_arr, fs)
        X.append(features)
    
    X = np.array(X)
    y = np.array(labels)
    
    try:
        manager.classifier.train(X, y)
        return {
            "status": "ok",
            "n_samples": len(X),
            "classes": manager.classifier.classes
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/classifier/predict")
async def predict_classifier(body: dict):
    """
    实时预测
    body: {"epoch": [[ch1_data], [ch2_data], ...]}
    """
    if bci_manager is None or not bci_manager.classifier.is_trained:
        return {"error": "Classifier not trained"}
    
    epoch = np.array(body.get("epoch", []))
    fs = body.get("fs", 500)
    
    if epoch.size == 0:
        return {"error": "No epoch data"}
    
    pred_class, confidence = bci_manager.classifier.predict(epoch, fs)
    
    return {
        "prediction": pred_class,
        "confidence": confidence,
        "paradigm": bci_manager.paradigm
    }

@app.post("/api/classifier/update")
async def update_classifier(body: dict):
    """
    在线更新分类器
    body: {"epoch": [[...]], "label": "left"}
    """
    if bci_manager is None:
        return {"error": "BCI manager not initialized"}
    
    epoch = np.array(body.get("epoch", []))
    label = body.get("label", "")
    fs = body.get("fs", 500)
    
    if epoch.size == 0 or not label:
        return {"error": "Missing epoch or label"}
    
    bci_manager.classifier.update(epoch, fs, label)
    
    return {"status": "ok", "buffer_size": len(bci_manager.classifier.feature_buffer)}

@app.post("/api/classifier/trial/result")
async def record_trial_result(body: dict):
    """记录Trial结果"""
    if bci_manager is None:
        return {"error": "BCI manager not initialized"}
    
    correct = body.get("correct", False)
    bci_manager.record_trial_result(correct)
    
    return {
        "status": "ok",
        "trial_count": bci_manager.session.trial_count,
        "accuracy": bci_manager.get_accuracy()
    }

@app.get("/api/classifier/metrics")
async def classifier_metrics():
    """获取分类器性能指标"""
    if bci_manager is None:
        return {"error": "BCI manager not initialized"}
    
    return {
        "paradigm": bci_manager.paradigm,
        "trial_count": bci_manager.session.trial_count,
        "correct_count": bci_manager.session.correct_count,
        "accuracy": bci_manager.get_accuracy(),
        "recent_predictions": bci_manager.session.predictions[-10:]
    }

@app.post("/api/classifier/save")
async def save_classifier_model(body: dict):
    """保存模型"""
    if bci_manager is None or not bci_manager.classifier.is_trained:
        return {"error": "No trained model to save"}
    
    path = body.get("path", "model.pkl")
    bci_manager.save_model(path)
    
    return {"status": "ok", "path": path}

@app.post("/api/classifier/load")
async def load_classifier_model(body: dict):
    """加载模型"""
    paradigm = body.get("paradigm", "mi")
    path = body.get("path", "model.pkl")
    
    manager = get_bci_manager(paradigm)
    
    if not os.path.exists(path):
        return {"error": f"Model file not found: {path}"}
    
    try:
        manager.classifier.load(path)
        return {"status": "ok", "classes": manager.classifier.classes}
    except Exception as e:
        return {"error": str(e)}


# 全局状态
connected_clients: list[WebSocket] = []

# 设置范式设计器的WebSocket引用
from paradigm.api import set_ws_clients
set_ws_clients(connected_clients)

data_source = None  # 当前活跃数据源
artifact_detector = None  # 全局伪迹检测器
last_artifact_check = 0  # 上次伪迹检测时间戳
mock_source = None   # Mock数据源(缓存)
file_source = None   # 文件数据源
serial_source = None  # 串口数据源
emotion_engine = None
preprocessor = None  # 预处理模块
timefreq_processor = None  # 时频分析模块
current_source_type = "mock"  # mock | file | serial | lsl
connectivity_processor = None  # 功能连接矩阵处理器
last_connectivity_check = 0  # 上次连接矩阵更新时间
connectivity_band = "alpha"  # 当前连接分析频段


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global data_source, emotion_engine, mock_source, file_source, current_source_type
    global preprocessor, timefreq_processor, spectrogram_processor
    global artifact_detector, last_artifact_check, artifact_buffer
    global quality_detector, last_quality_check
    
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
        
        # 初始化伪迹检测器
        artifact_detector = ArtifactDetector(fs=data_source.fs, threshold_uv=150.0)
        last_artifact_check = time.time()
        artifact_buffer = []  # 缓存帧用于伪迹检测
        
        # 初始化信号质量检测器
        quality_detector = QualityDetector(fs=data_source.fs, n_channels=data_source.n_channels)

        # 初始化功能连接矩阵处理器
        global connectivity_processor, last_connectivity_check, connectivity_band
        if connectivity_processor is None or connectivity_processor.n_channels != data_source.n_channels:
            connectivity_processor = ConnectivityProcessor(
                fs=data_source.fs, n_channels=data_source.n_channels,
                band=connectivity_band, update_interval_sec=2.0, window_sec=4.0
            )
        last_connectivity_check = time.time()
        
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
                elif data.get("action") == "set_connectivity_band":
                    band = data.get("band", "alpha")
                    if connectivity_processor:
                        connectivity_processor.set_band(band)
                        connectivity_band = band
                        print(f"[NeuroViz] 连接矩阵频段切换 → {band}")
                elif data.get("action") == "request_topomap":
                    # 客户端切换到2D视图时立即请求生成Topomap
                    await _send_topomap_now(ws, payload, frame, features, data_source, topomap_module, timefreq_ch_idx)
                    continue  # 本帧已发送，跳过常规payload
            except asyncio.TimeoutError:
                pass
            except Exception:
                break

            # 读取一帧数据
            frame = data_source.read_frame()
            
            # ===== 实时伪迹检测（预处理之前，用原始数据）=====
            artifact_buffer.append(frame["raw"].copy())
            
            # 伪迹检测（每2秒）
            if time.time() - last_artifact_check >= 2.0 and len(artifact_buffer) >= 10:
                artifact_raw = np.concatenate(artifact_buffer[-20:], axis=1)
                artifact_result = artifact_detector.detect_all(artifact_raw)
                
                # 始终推送结果（包括0伪迹=信号良好）
                artifact_alert = {
                    "type": "artifact_alert",
                    "timestamp": time.time(),
                    "total": artifact_result["total_artifacts"],
                    "summary": artifact_result.get("summary", {}),
                    "bad_ratio": artifact_result.get("bad_ratio_percent", 0),
                    "tips": _generate_artifact_tips(artifact_result),
                }
                await ws.send_json(artifact_alert)
                if artifact_result['total_artifacts'] > 0:
                    print(f"[NeuroViz] 伪迹检测: {artifact_result['total_artifacts']}个 ({artifact_result.get('summary', {})})")
                
                artifact_buffer = artifact_buffer[-10:]
                last_artifact_check = time.time()
            
            # 信号质量评估（独立定时器，每2秒）
            if not hasattr(globals(), 'last_quality_check') or time.time() - last_quality_check >= 2.0:
                quality_detector.push(frame["raw"])
                quality_result = quality_detector.assess_all()
                quality_payload = {
                    "type": "quality",
                    "timestamp": time.time(),
                    "overall": quality_result["overall"],
                    "channels": [{"ch": i, "status": ch["status"], "issues": ch["issues"], "suggestion": ch["suggestion"]} for i, ch in enumerate(quality_result["channels"])],
                    "summary": quality_result["summary"],
                    "calibrated": quality_result.get("calibrated", True),
                    "calibration_frames": quality_result.get("calibration_frames", 30),
                    "calibration_target": quality_result.get("calibration_target", 30),
                    "channel_names": data_source.channel_names,
                }
                await ws.send_json(quality_payload)
                if quality_result["overall"] != "good":
                    bad_chs = [i for i, ch in enumerate(quality_result["channels"]) if ch["status"] != "good"]
                    if len(bad_chs) <= 8:
                        print(f"[NeuroViz] 信号质量: {quality_result['overall']}, 问题通道: {bad_chs}")
                    else:
                        print(f"[NeuroViz] 信号质量: {quality_result['overall']}, {len(bad_chs)}/{quality_detector.n_channels} 通道异常")
                last_quality_check = time.time()

            # 功能连接矩阵（每2秒，推入缓冲并计算）
            connectivity_processor.push(frame["raw"])
            if time.time() - last_connectivity_check >= connectivity_processor.update_interval_sec:
                if len(connectivity_processor.buffer) >= connectivity_processor.nperseg:
                    conn_payload = connectivity_processor.get_matrix_payload(
                        channel_names=data_source.channel_names
                    )
                    conn_msg = {
                        "type": "connectivity",
                        "timestamp": time.time(),
                        "matrix": conn_payload["matrix"],
                        "channel_names": conn_payload["channel_names"],
                        "band": conn_payload["band"],
                        "freq_range": conn_payload["freq_range"],
                        "top_connections": conn_payload["top_connections"],
                        "mean_connectivity": conn_payload["mean_connectivity"],
                    }
                    await ws.send_json(_json_safe(conn_msg))
                last_connectivity_check = time.time()

            # 预处理（陷波 + 带通 + 伪迹去除）
            if preprocessor is not None:
                raw_clean = preprocessor.process(frame["raw"])
                frame["raw"] = raw_clean
                frame["ch1"] = raw_clean[0] if raw_clean.shape[0] > 0 else frame["ch1"]
                frame["ch2"] = raw_clean[1] if raw_clean.shape[0] > 1 else (raw_clean[0] if raw_clean.shape[0] > 0 else frame["ch2"])
            
            # 情绪分析（使用预处理后数据）
            features = emotion_engine.analyze(frame["ch1"], frame["ch2"])
            
            # 伪迹检测已移到预处理之前
            
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
            
            # 多通道频段功率（用于3D脑图）- 必须在payload定义之后
            try:
                if hasattr(emotion_engine, 'compute_all_channels'):
                    ch_bands = emotion_engine.compute_all_channels(frame["raw"])
                    payload['channel_bands'] = [ {k: float(v) for k,v in ch.items()} for ch in ch_bands ]
            except Exception as e:
                print(f"[NeuroViz] compute_all_channels 失败: {e}")
                payload["channel_bands"] = []
            
            # 频谱瀑布图更新(添加spectrogram字段到payload)
            if 'spectrogram_processor' in globals() and spectrogram_processor:
                spectrogram_processor.update(frame["ch1"], frame["ch2"])
                spec_norm = spectrogram_processor.normalize(spectrogram_processor.get_latest())
                payload['spectrogram'] = spec_norm.tolist()
            
            # Topomap推送(每2秒=40帧×0.05秒)
            send_counter += 1
            if send_counter % 40 == 0 and topomap_module:
                try:
                    # 使用channel_bands构建Topomap（全部8通道）
                    values = {}
                    electrode_names = ['Fp1','Fp2','F7','F3','F4','F8','T7','T8','C3','C4','P7','P3','P4','P8','O1','O2']
                    if 'channel_bands' in payload and payload['channel_bands']:
                        for i, ch_data in enumerate(payload['channel_bands']):
                            if i < len(electrode_names):
                                values[electrode_names[i]] = ch_data.get('alpha', 0.0)
                    
                    # 兜底：只有2通道时用features
                    elif 'bands_ch1' in features and 'bands_ch2' in features:
                        values['Fp1'] = features['bands_ch1'].get('alpha', 0.0)
                        values['Fp2'] = features['bands_ch2'].get('alpha', 0.0)
                    
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
                await ws.send_json(_json_safe(payload))
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

@app.get("/api/preprocessing/status")
async def preprocessing_status():
    """获取当前预处理参数"""
    return {
        "notch_freq": 50.0,
        "notch_Q": 30.0,
        "bandpass_low": 1.0,
        "bandpass_high": 40.0,
        "bandpass_order": 4,
        "artifact_threshold": 150.0,
        "fs": data_source.fs if data_source else 500,
    }


@app.post("/api/analysis/psd")
async def analyze_psd(body: dict):
    """计算PSD（接收raw数组或帧数组）"""
    fs = body.get("fs", 500)
    if "raw" in body:
        raw = np.array(body["raw"], dtype=np.float64)
    elif "raw_data" in body:
        frames = body["raw_data"]
        all_raw = [f["raw"] if isinstance(f, dict) else f for f in frames]
        raw = np.concatenate([np.array(r, dtype=np.float64) for r in all_raw], axis=1)
    else:
        return {"error": "no raw data provided"}
    
    # 返回格式: {freqs, powers, bands}
    from processors.psd import compute_psd, band_power_from_psd, BANDS
    result = {"freqs": [], "powers": [], "bands": {}}
    if raw.ndim == 1:
        raw = raw.reshape(1, -1)
    
    # 取第一通道作为代表
    freqs, psd = compute_psd(raw[0], fs=fs)
    result["freqs"] = freqs.tolist()
    result["powers"] = psd.tolist()
    result["bands"] = band_power_from_psd(freqs, psd, BANDS)
    
    return result


@app.post("/api/analysis/band-stats")
async def analyze_band_stats(body: dict):
    """计算频段统计（绝对功率/相对功率/参考范围）"""
    fs = body.get("fs", 500)
    if "raw" in body:
        raw = np.array(body["raw"], dtype=np.float64)
    elif "raw_data" in body:
        frames = body["raw_data"]
        all_raw = [f["raw"] if isinstance(f, dict) else f for f in frames]
        raw = np.concatenate([np.array(r, dtype=np.float64) for r in all_raw], axis=1)
    else:
        return {"error": "no raw data provided"}
    
    from processors.psd import compute_stats_multi
    if raw.ndim == 1:
        raw = raw.reshape(1, -1)
    stats = compute_stats_multi(raw, fs=fs)
    
    # 返回格式: {channels: [{name, bands: {band: {abs, rel, status}}}]}
    channels = []
    for ch_name, bands in stats.items():
        channels.append({"name": ch_name, "bands": bands})
    return {"channels": channels}


@app.post("/api/analysis/epoch")
async def analyze_epochs(body: dict):
    """分段分析（Epoching）"""
    fs = body.get("fs", 500)
    epoch_len = body.get("epoch_len", 5.0)  # 秒
    overlap = body.get("overlap", 0.0)  # 重叠比例
    
    if "raw" in body:
        raw = np.array(body["raw"], dtype=np.float64)
    elif "raw_data" in body:
        frames = body["raw_data"]
        all_raw = [f["raw"] if isinstance(f, dict) else f for f in frames]
        raw = np.concatenate([np.array(r, dtype=np.float64) for r in all_raw], axis=1)
    else:
        return {"error": "no raw data provided"}
    
    epocher = Epocher(fs=fs, epoch_len=epoch_len, overlap=overlap)
    return await asyncio.to_thread(epocher.analyze_all_epochs, raw)


@app.post("/api/analysis/artifact")
async def detect_artifacts(body: dict):
    """伪迹自动检测"""
    fs = body.get("fs", 500)
    threshold = body.get("threshold_uv", 150.0)
    
    if "raw" in body:
        raw = np.array(body["raw"], dtype=np.float64)
    elif "raw_data" in body:
        frames = body["raw_data"]
        all_raw = [f["raw"] if isinstance(f, dict) else f for f in frames]
        raw = np.concatenate([np.array(r, dtype=np.float64) for r in all_raw], axis=1)
    else:
        return {"error": "no raw data provided"}
    
    detector = ArtifactDetector(fs=fs, threshold_uv=threshold)
    return await asyncio.to_thread(detector.detect_all, raw)


@app.post("/api/analysis/topomap")
async def generate_topomap_endpoint(body: dict):
    """生成2D脑地形图"""
    values = body.get("values")  # {'Fp1': 5.2, ...}
    channel_values = body.get("channel_values")  # [v0, v1, ...]
    channel_names = body.get("channel_names")
    method = body.get("method", "auto")  # 'auto', 'rbf', 'cubic', 'linear', 'nearest'
    
    if channel_values:
        b64 = generate_topomap_base64_from_array(
            channel_values, 
            channel_names=channel_names,
            method=method
        )
    elif values:
        b64 = generate_topomap_base64(values, method=method)
    else:
        return {"error": "需要 values 或 channel_values"}
    
    return {"topomap_base64": b64}


@app.post("/api/analysis/connectivity")
async def analyze_connectivity(body: dict):
    """计算功能连接矩阵（相干性）

    body: {
        "raw": [[ch0_data], [ch1_data], ...],  # (n_channels, n_samples)
        "fs": 500,
        "band": "alpha"  # delta/theta/alpha/beta/gamma/broadband
    }

    Returns:
        {
            "matrix": [[...]],          # NxN 相干性矩阵 (0~1)
            "channel_names": [...],
            "band": "alpha",
            "freq_range": [lo, hi],
            "top_connections": [...],
            "mean_connectivity": float,
        }
    """
    fs = body.get("fs", 500)
    band = body.get("band", "alpha")
    channel_names = body.get("channel_names")

    if "raw" in body:
        raw = np.array(body["raw"], dtype=np.float64)
    elif "raw_data" in body:
        frames = body["raw_data"]
        all_raw = [f["raw"] if isinstance(f, dict) else f for f in frames]
        raw = np.concatenate([np.array(r, dtype=np.float64) for r in all_raw], axis=1)
    else:
        return {"error": "no raw data provided"}

    if raw.ndim == 1:
        raw = raw.reshape(1, -1)

    n_channels = raw.shape[0]

    def _compute():
        proc = ConnectivityProcessor(fs=fs, n_channels=n_channels, band=band,
                                      window_sec=4.0, update_interval_sec=1.0)
        proc.push(raw)
        names = channel_names or [f"Ch{i}" for i in range(n_channels)]
        return proc.get_matrix_payload(channel_names=names)

    result = await asyncio.to_thread(_compute)
    return result


@app.get("/api/connectivity/bands")
async def list_connectivity_bands():
    """获取可用的连接分析频段列表"""
    from processors.connectivity import BANDS
    bands = [
        {"name": "delta", "range": BANDS["delta"], "label": "δ (1-4Hz) 慢波睡眠"},
        {"name": "theta", "range": BANDS["theta"], "label": "θ (4-8Hz) 记忆/冥想"},
        {"name": "alpha", "range": BANDS["alpha"], "label": "α (8-13Hz) 放松同步"},
        {"name": "beta", "range": BANDS["beta"], "label": "β (13-30Hz) 专注/运动"},
        {"name": "gamma", "range": BANDS["gamma"], "label": "γ (30-50Hz) 高级认知"},
        {"name": "broadband", "range": (1, 50), "label": "全频段 (1-50Hz)"},
    ]
    return {"bands": bands, "current": connectivity_band}


@app.post("/api/export/csv")
async def export_csv_endpoint(body: dict):
    """导出CSV"""
    try:
        raw_data = body.get("raw")
        if not raw_data or len(raw_data) == 0:
            return JSONResponse({"error": "无数据可导出"}, status_code=400)
        raw = np.array(raw_data, dtype=np.float32)
        if raw.ndim == 1:
            raw = raw.reshape(1, -1)
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
    except Exception as e:
        print(f"[NeuroViz] CSV导出失败: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/export/pdf")
async def export_pdf_endpoint(body: dict):
    """导出专业PDF分析报告"""
    try:
        raw_data = body.get("raw")
        if not raw_data or len(raw_data) == 0:
            return JSONResponse({"error": "无数据可导出，请先采集数据"}, status_code=400)
        raw = np.array(raw_data, dtype=np.float32)
        if raw.ndim == 1:
            raw = raw.reshape(1, -1)
        print(f"[NeuroViz] PDF导出: shape={raw.shape}, fs={body.get('fs',500)}")
    except Exception as e:
        print(f"[NeuroViz] PDF导出数据解析失败: {e}")
        return JSONResponse({"error": f"数据格式错误: {e}"}, status_code=400)
    
    features = body.get("features", {})
    fs = body.get("fs", 500)
    channel_names = body.get("channel_names")
    channel_bands = body.get("channel_bands")
    artifact_summary = body.get("artifact_summary")
    session_duration = body.get("session_duration_sec")
    topomap_b64 = body.get("topomap")
    spectrogram_b64 = body.get("spectrogram")
    
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".pdf", delete=False, dir="/tmp")
    path = tmp.name
    tmp.close()
    
    try:
        export_pdf(
            raw, features, path, fs,
            channel_names=channel_names,
            channel_bands=channel_bands,
            artifact_summary=artifact_summary,
            session_duration_sec=session_duration,
            topomap_b64=topomap_b64,
            spectrogram_b64=spectrogram_b64,
        )
    except Exception as e:
        print(f"[NeuroViz] PDF生成失败: {e}")
        import traceback; traceback.print_exc()
        return JSONResponse({"error": f"PDF生成失败: {e}"}, status_code=500)
    
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
