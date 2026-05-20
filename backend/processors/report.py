"""
报告导出模块
CSV原始数据 + PDF分析报告
"""

import numpy as np
import json
from pathlib import Path
from datetime import datetime


def export_csv(data: np.ndarray, channels: list, fs: int, output_path: str):
    """
    导出CSV文件
    data: (n_channels, n_samples)
    channels: 通道名列表
    fs: 采样率
    output_path: 输出文件路径
    """
    n_ch, n_samp = data.shape
    t = np.arange(n_samp) / fs
    
    with open(output_path, "w") as f:
        # 头部
        f.write(f"# NeuroViz EEG Export\n")
        f.write(f"# Time: {datetime.now().isoformat()}\n")
        f.write(f"# Sampling Rate: {fs} Hz\n")
        f.write(f"# Channels: {n_ch}\n")
        f.write(f"# Duration: {n_samp/fs:.1f} s\n")
        f.write("Time(s)," + ",".join(channels) + "\n")
        
        # 数据行
        for i in range(n_samp):
            row = [f"{t[i]:.3f}"]
            row += [f"{data[ch, i]:.2f}" for ch in range(n_ch)]
            f.write(",".join(row) + "\n")
    
    print(f"[Report] CSV导出成功: {output_path}")
    return output_path


def export_pdf(data: np.ndarray, features: dict, output_path: str, fs: int = 500):
    """
    导出PDF分析报告
    data: (n_channels, n_samples) 原始数据
    features: 特征字典（emotion_engine输出）
    output_path: 输出文件路径
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
    except ImportError:
        raise RuntimeError("需要reportlab，请运行: pip install reportlab")
    
    doc = SimpleDocTemplate(output_path, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    # 标题
    title = Paragraph("<b>NeuroViz EEG Analysis Report</b>", styles["Title"])
    story.append(title)
    story.append(Spacer(1, 0.5 * cm))
    
    # 基本信息
    info = [
        ["Time", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ["Channels", str(data.shape[0])],
        ["Sampling Rate", f"{fs} Hz"],
        ["Duration", f"{data.shape[1]/fs:.1f} s"],
    ]
    tbl_info = Table(info, colWidths=[4*cm, 6*cm])
    tbl_info.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(tbl_info)
    story.append(Spacer(1, 1 * cm))
    
    # 情绪分析（如果有）
    if features:
        emotion_title = Paragraph("<b>Emotion Analysis</b>", styles["Heading2"])
        story.append(emotion_title)
        story.append(Spacer(1, 0.3 * cm))
        
        emotion_data = [
            ["Metric", "Value"],
            ["Arousal", f"{features.get('arousal', 0):.2f}"],
            ["Valence", f"{features.get('valence', 0):.2f}"],
            ["Focus Level", f"{features.get('focus', 0):.2f}"],
            ["Relaxation", f"{features.get('relaxation', 0):.2f}"],
        ]
        tbl_emotion = Table(emotion_data, colWidths=[4*cm, 4*cm])
        tbl_emotion.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(tbl_emotion)
        story.append(Spacer(1, 1 * cm))
    
    # 频段能量（如果有）
    if "bands_ch1" in features:
        bands_title = Paragraph("<b>Band Power (Ch1)</b>", styles["Heading2"])
        story.append(bands_title)
        story.append(Spacer(1, 0.3 * cm))
        
        bands = features["bands_ch1"]
        bands_data = [
            ["Band", "Power (µV²)"],
            ["Delta (0.5-4 Hz)", f"{bands.get('delta', 0):.2f}"],
            ["Theta (4-8 Hz)", f"{bands.get('theta', 0):.2f}"],
            ["Alpha (8-13 Hz)", f"{bands.get('alpha', 0):.2f}"],
            ["Beta (13-30 Hz)", f"{bands.get('beta', 0):.2f}"],
            ["Gamma (30-50 Hz)", f"{bands.get('gamma', 0):.2f}"],
        ]
        tbl_bands = Table(bands_data, colWidths=[4*cm, 4*cm])
        tbl_bands.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(tbl_bands)
    
    # 生成PDF
    doc.build(story)
    print(f"[Report] PDF导出成功: {output_path}")
    return output_path


def test_report():
    """测试报告导出"""
    fs = 500
    n_channels = 8
    n_samples = fs * 10  # 10秒
    
    # 生成测试数据
    data = np.random.randn(n_channels, n_samples).astype(np.float32) * 50.0
    
    # 测试CSV导出
    csv_path = "/tmp/test_export.csv"
    export_csv(data, [f"Ch{i}" for i in range(n_channels)], fs, csv_path)
    
    # 测试PDF导出（需要reportlab）
    try:
        pdf_path = "/tmp/test_report.pdf"
        features = {
            "arousal": 0.65,
            "valence": 0.42,
            "focus": 0.78,
            "relaxation": 0.35,
            "bands_ch1": {
                "delta": 120.5,
                "theta": 85.2,
                "alpha": 150.8,
                "beta": 95.3,
                "gamma": 45.6,
            },
        }
        export_pdf(data, features, pdf_path, fs)
    except RuntimeError as e:
        print(f"PDF导出跳过: {e}")


if __name__ == "__main__":
    test_report()
