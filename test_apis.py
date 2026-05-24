#!/usr/bin/env python3
"""测试所有 API 端点"""
import requests

BASE = "http://localhost:8080"

print("=== NeuroViz API 检查 ===\n")

# 1. LSL API
print("1. LSL API:")
try:
    r = requests.get(f"{BASE}/api/lsl/streams", timeout=5)
    print(f"   {r.status_code}: {r.text[:200]}")
except Exception as e:
    print(f"   ❌ {e}")

# 2. 文件上传 API
print("\n2. 文件上传 API:")
try:
    r = requests.post(f"{BASE}/api/upload", timeout=2)
    print(f"   {r.status_code} (预期 422)")
except Exception as e:
    print(f"   ❌ {e}")

# 3. 分析 API
print("\n3. 分析 API:")
try:
    r = requests.post(f"{BASE}/api/analysis/psd", json={"data": [0.1]*256}, timeout=2)
    print(f"   /api/analysis/psd: {r.status_code}")
except Exception as e:
    print(f"   ❌ PSD: {e}")

try:
    r = requests.post(f"{BASE}/api/analysis/band-stats", json={"data": [0.1]*256, "fs": 500}, timeout=2)
    print(f"   /api/analysis/band-stats: {r.status_code}")
except Exception as e:
    print(f"   ❌ Band-stats: {e}")

# 4. 导出 API
print("\n4. 导出 API:")
try:
    r = requests.post(f"{BASE}/api/export/csv", json={"data": [0.1]*256}, timeout=2)
    print(f"   /api/export/csv: {r.status_code} - {r.text[:100]}")
except Exception as e:
    print(f"   ❌ CSV: {e}")

try:
    r = requests.post(f"{BASE}/api/export/pdf", json={}, timeout=2)
    print(f"   /api/export/pdf: {r.status_code} - {r.text[:100]}")
except Exception as e:
    print(f"   ❌ PDF: {e}")

print("\n=== 检查完成 ===")
