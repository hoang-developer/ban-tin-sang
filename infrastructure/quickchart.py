"""Cổng ra QuickChart: vẽ biểu đồ Chart.js thành ảnh PNG. Chỉ gửi tên nhóm và số tiền."""
import json
import urllib.request

CHART_URL = "https://quickchart.io/chart"


def chart_png(chart, width=800, height=500):
    """Vẽ biểu đồ Chart.js thành ảnh PNG bằng QuickChart."""
    body = {"version": "4", "width": width, "height": height, "devicePixelRatio": 2, "backgroundColor": "white",
            "format": "png", "chart": chart}
    req = urllib.request.Request(CHART_URL, data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read()
    if not data.startswith(b"\x89PNG"):
        raise RuntimeError(f"QuickChart không trả ảnh: {data[:80]!r}")
    return data
