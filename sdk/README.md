# NeuroViz Python SDK

开发者接入工具包，用于自定义算法、实时数据获取、BCI控制。

## 安装

```bash
pip install neuroviz-sdk
```

或从源码安装：

```bash
cd sdk
pip install -e .
```

## 快速开始

### 连接

```python
from neuroviz import NeuroVizClient

client = NeuroVizClient()
client.connect()
```

### 实时数据流

```python
# 方式1: 生成器
for data in client.stream(timeout=10):
    raw = data['raw']  # np.ndarray, (n_channels, n_samples)
    features = data.get('features', {})
    print(f"Channels: {raw.shape[0]}")

# 方式2: 回调模式
def on_data(data):
    print(f"Got {data['raw'].shape[0]} channels")

client.on_data(on_data)
client.start_stream()
# ... 
client.stop_stream()
```

### Marker系统

```python
# Trial控制
trial_num = client.start_trial(trial_type='MI')

# 添加事件
client.add_marker('stimulus', value=1, metadata={'direction': 'left'})
client.add_marker('response', metadata={'rt_ms': 350})

# 结束Trial
client.end_trial(result='correct')

# 获取所有Trial
trials = client.get_trials()
```

### BCI分类器

```python
# 初始化
client.init_classifier(paradigm='mi')  # mi/p300/ssvep

# 训练
import numpy as np
epochs = [np.random.randn(8, 256) for _ in range(20)]
labels = ['left', 'right'] * 10
client.train_classifier(epochs, labels)

# 预测
test_epoch = np.random.randn(8, 256)
result = client.predict(test_epoch)
print(f"Prediction: {result['prediction']}, Confidence: {result['confidence']}")
```

### LSL集成

```python
# 列出可用流
streams = client.list_lsl_streams()
print(f"Found {len(streams)} LSL streams")

# 连接
client.connect_lsl(stream_name='OpenBCI_EEG')

# 断开
client.disconnect_lsl()
```

### 数据导出

```python
# 导出CSV
csv_data = client.export_csv()
with open('session.csv', 'wb') as f:
    f.write(csv_data)

# 导出PDF
pdf_data = client.export_pdf()
with open('report.pdf', 'wb') as f:
    f.write(pdf_data)
```

## API参考

### 连接管理

| 方法 | 说明 |
|------|------|
| `connect()` | 连接服务器 |
| `disconnect()` | 断开连接 |
| `is_connected()` | 检查连接状态 |

### 实时数据

| 方法 | 说明 |
|------|------|
| `stream(timeout)` | 生成器：实时数据流 |
| `on_data(callback)` | 注册回调 |
| `start_stream()` | 启动后台流 |
| `stop_stream()` | 停止后台流 |

### 数据源

| 方法 | 说明 |
|------|------|
| `switch_source(type)` | 切换数据源 |
| `upload_file(path)` | 上传EDF/CSV |

### Marker

| 方法 | 说明 |
|------|------|
| `add_marker(name, value)` | 添加Marker |
| `start_trial(trial_type)` | 开始Trial |
| `end_trial(result)` | 结束Trial |
| `mark_stimulus(type)` | 标记刺激 |
| `mark_response(response)` | 标记响应 |
| `get_markers(n)` | 获取Marker列表 |
| `get_trials()` | 获取Trial列表 |
| `export_markers()` | 导出JSON |

### BCI分类器

| 方法 | 说明 |
|------|------|
| `init_classifier(paradigm)` | 初始化分类器 |
| `train_classifier(epochs, labels)` | 训练模型 |
| `predict(epoch)` | 实时预测 |
| `add_training_sample(epoch, label)` | 添加训练样本 |
| `record_trial_result(correct)` | 记录结果 |
| `get_classifier_status()` | 获取状态 |
| `get_classifier_metrics()` | 获取性能指标 |
| `save_model(path)` | 保存模型 |
| `load_model(path)` | 加载模型 |

### LSL

| 方法 | 说明 |
|------|------|
| `list_lsl_streams()` | 列出LSL流 |
| `connect_lsl(stream_name)` | 连接LSL |
| `disconnect_lsl()` | 断开LSL |

### 导出

| 方法 | 说明 |
|------|------|
| `export_csv()` | 导出CSV |
| `export_pdf()` | 导出PDF |

## 示例：完整BCI实验

```python
from neuroviz import NeuroVizClient
import numpy as np
import time

client = NeuroVizClient()
client.connect()

# 初始化MI分类器
client.init_classifier(paradigm='mi')

# 训练阶段
print("Training phase - imagine left/right hand movement")

epochs = []
labels = []

def collect_training_data(direction: str, n_trials: int = 5):
    for i in range(n_trials):
        trial_num = client.start_trial(trial_type='MI')
        print(f"Trial {trial_num}: Imagine {direction}")
        
        time.sleep(4)  # 4秒想象
        
        # 获取最近epoch (实际应从数据缓冲提取)
        epoch = np.random.randn(8, 256)
        epochs.append(epoch)
        labels.append(direction)
        
        client.end_trial(result='completed')

collect_training_data('left', n_trials=10)
collect_training_data('right', n_trials=10)

# 训练模型
result = client.train_classifier(epochs, labels)
print(f"Training result: {result}")

# 测试阶段
print("\nTest phase")

correct = 0
for i in range(10):
    trial_num = client.start_trial(trial_type='MI_test')
    
    time.sleep(4)
    
    epoch = np.random.randn(8, 256)
    pred = client.predict(epoch)
    
    print(f"Trial {trial_num}: Prediction={pred['prediction']}, Conf={pred['confidence']:.2f}")
    
    # 用户反馈
    user_input = input("Correct? (y/n): ")
    is_correct = user_input.lower() == 'y'
    
    client.record_trial_result(is_correct)
    if is_correct:
        correct += 1
    
    client.end_trial(result='correct' if is_correct else 'incorrect')

metrics = client.get_classifier_metrics()
print(f"\nAccuracy: {metrics['accuracy']*100:.1f}%")

# 导出
markers = client.export_markers()
print(f"Total markers: {markers['total_markers']}")
```

## 配置

```python
from neuroviz import NeuroVizClient, NeuroVizConfig

config = NeuroVizConfig(
    host="192.168.1.100",  # 远程服务器
    port=8000,
    ws_reconnect=True,
    ws_reconnect_interval=2.0
)

client = NeuroVizClient(config)
```

## 依赖

- Python >= 3.9
- requests >= 2.28
- websocket-client >= 1.4
- numpy >= 1.21

## License

MIT
