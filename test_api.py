#!/usr/bin/env python3
"""生产前 API 端点检查"""
import requests
import time

BASE = "http://localhost:8080"

print("=== NeuroViz 生产前检查 ===\n")

# 1. 检查后端是否运行
print("1. 后端运行状态:")
try:
    r = requests.get(f"{BASE}/docs", timeout=2)
    print(f"   ✅ 后端运行中 (HTTP {r.status_code})")
except Exception as e:
    print(f"   ❌ 后端未运行: {e}")
    exit(1)

# 2. 检查 LSL API
print("\n2. LSL API:")
try:
    r = requests.get(f"{BASE}/api/lsl/streams", timeout=5)
    print(f"   ✅ /api/lsl/streams: {r.status_code}")
    print(f"   响应: {r.json()}")
except Exception as e:
    print(f"   ❌ LSL API 错误: {e}")

# 3. 检查文件上传 API
print("\n3. 文件上传 API:")
try:
    r = requests.post(f"{BASE}/api/upload", timeout=2)
    print(f"   ✅ /api/upload: {r.status_code} (预期 422/415)")
except Exception as e:
    print(f"   ❌ 上传 API 错误: {e}")

# 4. 检查分析 API
print("\n4. 分析 API:")
try:
    r = requests.post(f"{BASE}/api/analysis/psd", json={"data": [0.1]*256}, timeout=2)
    print(f"   ✅ /api/analysis/psd: {r.status_code}")
except Exception as e:
    print(f"   ❌ PSD API 错误: {e}")

try:
    r = requests.post(f"{BASE}/api/analysis/band-stats", json={"data": [0.1]*256, "fs": 500}, timeout=2)
    print(f"   ✅ /api/analysis/band-stats: {r.status_code}")
except Exception as e:
    print(f"   ❌ Band-stats API 错误: {e}")

# 5. 检查导出 API
print("\n5. 导出 API:")
try:
    r = requests.post(f"{BASE}/api/export/csv", json={"data": [0.1]*256}, timeout=2)
    print(f"   ✅ /api/export/csv: {r.status_code}")
except Exception as e:
    print(f"   ❌ CSV 导出 API 错误: {e}")

try:
    r = requests.post(f"{BASE}/api/export/pdf", json={}, timeout=2)
    print(f"   ✅ /api/export/pdf: {r.status_code}")
except Exception as e:
    print(f"   ❌ PDF 导出 API 错误: {e}")

print("\n=== 检查完成 ===")
print("✅ = 正常, ❌ = 需要修复\n")
