import { useState } from "react";

export default function ChartZoom({ children }) {
  const [scale, setScale] = useState(1);
  return <div className="chart-zoom">
    <div className="chart-zoom-controls" aria-label="Zoom">
      <button type="button" aria-label="Thu nhỏ biểu đồ" disabled={scale === 1} onClick={() => setScale(Math.max(1, scale - 0.5))}>-</button>
      <span>{scale * 100}%</span>
      <button type="button" aria-label="Phóng to biểu đồ" disabled={scale === 4} onClick={() => setScale(Math.min(4, scale + 0.5))}>+</button>
      <button type="button" disabled={scale === 1} onClick={() => setScale(1)}>100%</button>
    </div>
    <div className="chart-zoom-scroll" role="region" aria-label="Biểu đồ có thể cuộn" tabIndex={0}>
      <div style={{ width: `${scale * 100}%` }}>{children}</div>
    </div>
  </div>;
}
