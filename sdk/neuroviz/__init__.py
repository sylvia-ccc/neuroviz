"""
NeuroViz Python SDK — 开发者接入
提供简洁的API用于自定义算法、数据获取、BCI控制

安装: pip install neuroviz-sdk (或本地安装)
使用: from neuroviz import NeuroVizClient
"""

import requests
import websocket
import json
import numpy as np
from typing import Optional, List, Dict, Callable, Any
from dataclasses import dataclass
import threading
import time


@dataclass
class NeuroVizConfig:
    """配置"""
    host: str = "127.0.0.1"
    port: int = 8000
    ws_reconnect: bool = True
    ws_reconnect_interval: float = 2.0
    

class NeuroVizClient:
    """
    NeuroViz Python客户端
    
    示例:
        client = NeuroVizClient()
        client.connect()
        
        # 获取实时数据
        for data in client.stream():
            print(data['raw'].shape)  # (n_channels, n_samples)
        
        # 添加自定义处理
        client.on_data(my_callback)
        
        # BCI控制
        client.start_trial('MI')
        client.add_marker('stimulus', value=1)
        client.end_trial('correct')
    """
    
    def __init__(self, config: Optional[NeuroVizConfig] = None):
        self.config = config or NeuroVizConfig()
        self.base_url = f"http://{self.config.host}:{self.config.port}"
        self.ws_url = f"ws://{self.config.host}:{self.config.port}/ws"
        
        self._ws = None
        self._connected = False
        self._running = False
        self._callbacks: List[Callable] = []
        self._ws_thread = None
        
    # ===== 连接管理 =====
    
    def connect(self) -> bool:
        """连接到NeuroViz服务器"""
        try:
            # 测试HTTP连接
            resp = requests.get(f"{self.base_url}/api/markers?n=1", timeout=2)
            if resp.status_code == 200:
                self._connected = True
                print(f"[NeuroViz] Connected to {self.base_url}")
                return True
        except Exception as e:
            print(f"[NeuroViz] Connection failed: {e}")
            return False
        
    def disconnect(self):
        """断开连接"""
        self._running = False
        if self._ws:
            self._ws.close()
        self._connected = False
        
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._connected
    
    # ===== 实时数据流 =====
    
    def stream(self, timeout: Optional[float] = None) -> Dict:
        """
        生成器：实时数据流
        
        for data in client.stream():
            raw = data['raw']           # np.ndarray, (n_channels, n_samples)
            features = data['features'] # 情绪/频段等特征
            markers = data.get('markers', [])
        """
        start_time = time.time()
        
        def on_message(ws, message):
            pass
        
        ws = websocket.create_connection(self.ws_url)
        
        try:
            while True:
                if timeout and (time.time() - start_time) > timeout:
                    break
                    
                result = ws.recv()
                if result:
                    data = json.loads(result)
                    # 转换numpy数组
                    if 'raw' in data:
                        data['raw'] = np.array(data['raw'])
                    yield data
        finally:
            ws.close()
    
    def on_data(self, callback: Callable[[Dict], None]):
        """
        注册数据回调
        
        def my_callback(data):
            print(f"Got {data['raw'].shape[0]} channels")
            
        client.on_data(my_callback)
        client.start_stream()
        """
        self._callbacks.append(callback)
        
    def start_stream(self):
        """启动后台数据流（回调模式）"""
        if self._running:
            return
            
        self._running = True
        
        def _ws_thread():
            while self._running:
                try:
                    ws = websocket.create_connection(self.ws_url)
                    while self._running:
                        result = ws.recv()
                        if result:
                            data = json.loads(result)
                            if 'raw' in data:
                                data['raw'] = np.array(data['raw'])
                            for cb in self._callbacks:
                                cb(data)
                except Exception as e:
                    if self.config.ws_reconnect and self._running:
                        print(f"[NeuroViz] WS disconnected, reconnecting... ({e})")
                        time.sleep(self.config.ws_reconnect_interval)
                    else:
                        break
                        
        self._ws_thread = threading.Thread(target=_ws_thread, daemon=True)
        self._ws_thread.start()
        
    def stop_stream(self):
        """停止后台数据流"""
        self._running = False
        
    # ===== 数据源控制 =====
    
    def switch_source(self, source_type: str, **kwargs) -> Dict:
        """
        切换数据源
        
        client.switch_source('mock')
        client.switch_source('file', path='/path/to/data.edf')
        client.switch_source('serial', port='/dev/ttyUSB0')
        client.switch_source('lsl', stream_name='EEG')
        """
        resp = requests.post(
            f"{self.base_url}/api/source/switch",
            json={"type": source_type, **kwargs}
        )
        return resp.json()
    
    def upload_file(self, file_path: str) -> Dict:
        """上传EDF/CSV文件"""
        with open(file_path, 'rb') as f:
            resp = requests.post(
                f"{self.base_url}/api/upload",
                files={'file': f}
            )
        return resp.json()
    
    # ===== Marker系统 =====
    
    def add_marker(self, name: str, value: int = 0, 
                   duration: float = 0.0, metadata: Optional[dict] = None) -> Dict:
        """添加Marker"""
        resp = requests.post(
            f"{self.base_url}/api/markers/add",
            json={"name": name, "value": value, "duration": duration, "metadata": metadata}
        )
        return resp.json()
    
    def start_trial(self, trial_type: str = "", metadata: Optional[dict] = None) -> int:
        """开始Trial"""
        resp = requests.post(
            f"{self.base_url}/api/markers/trial/start",
            json={"trial_type": trial_type, "metadata": metadata}
        )
        data = resp.json()
        return data.get('trial_num', 0)
    
    def end_trial(self, result: str = "", metadata: Optional[dict] = None) -> Dict:
        """结束Trial"""
        resp = requests.post(
            f"{self.base_url}/api/markers/trial/end",
            json={"result": result, "metadata": metadata}
        )
        return resp.json()
    
    def mark_stimulus(self, stimulus_type: str, value: int = 0) -> Dict:
        """标记刺激"""
        resp = requests.post(
            f"{self.base_url}/api/markers/stimulus",
            json={"stimulus_type": stimulus_type, "value": value}
        )
        return resp.json()
    
    def mark_response(self, response: str, correct: bool = False, 
                      rt_ms: float = 0) -> Dict:
        """标记响应"""
        resp = requests.post(
            f"{self.base_url}/api/markers/response",
            json={"response": response, "correct": correct, "rt_ms": rt_ms}
        )
        return resp.json()
    
    def get_markers(self, n: int = 50) -> List[Dict]:
        """获取最近Marker"""
        resp = requests.get(f"{self.base_url}/api/markers?n={n}")
        return resp.json().get('markers', [])
    
    def get_trials(self) -> List[Dict]:
        """获取所有Trial"""
        resp = requests.get(f"{self.base_url}/api/markers/trials")
        return resp.json().get('trials', [])
    
    def export_markers(self) -> Dict:
        """导出所有Marker数据"""
        resp = requests.get(f"{self.base_url}/api/markers/export")
        return resp.json()
    
    def clear_markers(self) -> Dict:
        """清空所有Marker"""
        resp = requests.post(f"{self.base_url}/api/markers/clear")
        return resp.json()
    
    # ===== BCI分类器 =====
    
    def init_classifier(self, paradigm: str = 'mi') -> Dict:
        """初始化分类器 (mi/p300/ssvep)"""
        resp = requests.post(
            f"{self.base_url}/api/classifier/init",
            json={"paradigm": paradigm}
        )
        return resp.json()
    
    def train_classifier(self, epochs: List[np.ndarray], labels: List[str],
                        paradigm: str = 'mi') -> Dict:
        """
        训练分类器
        
        epochs = [epoch1, epoch2, ...]  # 每个epoch: (n_channels, n_samples)
        labels = ['left', 'right', 'left', ...]
        
        client.train_classifier(epochs, labels, paradigm='mi')
        """
        # 转换numpy为list
        epochs_list = [e.tolist() for e in epochs]
        
        resp = requests.post(
            f"{self.base_url}/api/classifier/train",
            json={"paradigm": paradigm, "data": epochs_list, "labels": labels}
        )
        return resp.json()
    
    def predict(self, epoch: np.ndarray, fs: int = 500) -> Dict:
        """
        实时预测
        
        pred = client.predict(epoch)
        print(pred['prediction'], pred['confidence'])
        """
        resp = requests.post(
            f"{self.base_url}/api/classifier/predict",
            json={"epoch": epoch.tolist(), "fs": fs}
        )
        return resp.json()
    
    def add_training_sample(self, epoch: np.ndarray, label: str, fs: int = 500) -> Dict:
        """添加训练样本（在线学习）"""
        resp = requests.post(
            f"{self.base_url}/api/classifier/update",
            json={"epoch": epoch.tolist(), "label": label, "fs": fs}
        )
        return resp.json()
    
    def record_trial_result(self, correct: bool) -> Dict:
        """记录Trial结果"""
        resp = requests.post(
            f"{self.base_url}/api/classifier/trial/result",
            json={"correct": correct}
        )
        return resp.json()
    
    def get_classifier_status(self) -> Dict:
        """获取分类器状态"""
        resp = requests.get(f"{self.base_url}/api/classifier/status")
        return resp.json()
    
    def get_classifier_metrics(self) -> Dict:
        """获取分类器性能指标"""
        resp = requests.get(f"{self.base_url}/api/classifier/metrics")
        return resp.json()
    
    def save_model(self, path: str) -> Dict:
        """保存模型"""
        resp = requests.post(
            f"{self.base_url}/api/classifier/save",
            json={"path": path}
        )
        return resp.json()
    
    def load_model(self, path: str, paradigm: str = 'mi') -> Dict:
        """加载模型"""
        resp = requests.post(
            f"{self.base_url}/api/classifier/load",
            json={"path": path, "paradigm": paradigm}
        )
        return resp.json()
    
    # ===== LSL集成 =====
    
    def list_lsl_streams(self) -> List[Dict]:
        """列出可用LSL流"""
        resp = requests.get(f"{self.base_url}/api/lsl/streams")
        return resp.json().get('streams', [])
    
    def connect_lsl(self, stream_name: Optional[str] = None,
                   stream_type: str = 'EEG') -> Dict:
        """连接LSL流"""
        resp = requests.post(
            f"{self.base_url}/api/lsl/connect",
            json={"stream_name": stream_name, "stream_type": stream_type}
        )
        return resp.json()
    
    def disconnect_lsl(self) -> Dict:
        """断开LSL"""
        resp = requests.post(f"{self.base_url}/api/lsl/disconnect")
        return resp.json()
    
    # ===== 数据导出 =====
    
    def export_csv(self, session_data: Optional[dict] = None) -> bytes:
        """导出CSV"""
        resp = requests.post(
            f"{self.base_url}/api/export/csv",
            json={"session_data": session_data or {}}
        )
        return resp.content
    
    def export_pdf(self, session_data: Optional[dict] = None) -> bytes:
        """导出PDF"""
        resp = requests.post(
            f"{self.base_url}/api/export/pdf",
            json={"session_data": session_data or {}}
        )
        return resp.content
    
    # ===== 预处理与PSD =====
    
    def get_psd(self, data: np.ndarray, fs: int = 500) -> Dict:
        """计算PSD"""
        resp = requests.post(
            f"{self.base_url}/api/psd",
            json={"data": data.tolist(), "fs": fs}
        )
        return resp.json()
    
    def get_band_stats(self, data: np.ndarray, fs: int = 500) -> Dict:
        """计算频段统计"""
        resp = requests.post(
            f"{self.base_url}/api/band-stats",
            json={"data": data.tolist(), "fs": fs}
        )
        return resp.json()


# ===== 便捷函数 =====

def connect(host: str = "127.0.0.1", port: int = 8000) -> NeuroVizClient:
    """快速连接"""
    client = NeuroVizClient(NeuroVizConfig(host=host, port=port))
    if client.connect():
        return client
    raise ConnectionError(f"Cannot connect to NeuroViz at {host}:{port}")


def stream(host: str = "127.0.0.1", port: int = 8000, timeout: Optional[float] = None):
    """快速数据流"""
    client = connect(host, port)
    yield from client.stream(timeout=timeout)


# ===== 示例脚本 =====

if __name__ == "__main__":
    # 示例1: 实时数据流
    print("=== Example 1: Real-time Stream ===")
    client = NeuroVizClient()
    
    if client.connect():
        for i, data in enumerate(client.stream(timeout=5)):
            if 'raw' in data:
                print(f"[{i}] Channels: {data['raw'].shape[0]}, Samples: {data['raw'].shape[1]}")
                if i >= 3:
                    break
    
    # 示例2: Marker系统
    print("\n=== Example 2: Markers ===")
    trial_num = client.start_trial(trial_type='MI')
    print(f"Started trial #{trial_num}")
    
    client.add_marker('stimulus', value=1, metadata={'direction': 'left'})
    client.add_marker('response', metadata={'key': 'A', 'rt_ms': 350})
    
    result = client.end_trial(result='correct')
    print(f"Trial ended: {result}")
    
    # 示例3: BCI分类器
    print("\n=== Example 3: BCI Classifier ===")
    client.init_classifier(paradigm='mi')
    
    # 模拟训练数据
    epochs = [np.random.randn(8, 256) for _ in range(10)]
    labels = ['left', 'right'] * 5
    
    train_result = client.train_classifier(epochs, labels)
    print(f"Training: {train_result}")
    
    # 预测
    test_epoch = np.random.randn(8, 256)
    pred = client.predict(test_epoch)
    print(f"Prediction: {pred['prediction']} (confidence: {pred['confidence']:.2f})")
    
    print("\n[NeuroViz SDK] Examples completed!")
