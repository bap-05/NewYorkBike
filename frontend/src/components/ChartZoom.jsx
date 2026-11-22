import { useLayoutEffect, useRef, useState } from "react";

export default function ChartZoom({ children, min = 100, step = 50, centerWidth }) {
  const [scale, setScale] = useState(100);
  const drag = useRef(null);
  const scroll = useRef(null);
  useLayoutEffect(() => {
    if (!centerWidth) return;
    const viewport = scroll.current;
    const center = () => {
      viewport.scrollLeft = (viewport.scrollWidth - viewport.clientWidth) / 2;
    };
    center();
    const observer = new ResizeObserver(center);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [centerWidth, scale]);
  function startDrag(event) {
    const viewport = event.currentTarget;
    if (event.pointerType !== "mouse" || event.button !== 0 ||
        viewport.scrollWidth <= viewport.clientWidth) return;
    drag.current = { id: event.pointerId, x: event.clientX, left: viewport.scrollLeft };
  }
  function moveDrag(event) {
    const viewport = event.currentTarget;
    if (drag.current?.id !== event.pointerId) return;
    const offset = drag.current.x - event.clientX;
    if (!viewport.hasPointerCapture(event.pointerId)) {
      if (Math.abs(offset) < 4) return;
      viewport.setPointerCapture(event.pointerId);
      viewport.classList.add("is-dragging");
    }
    viewport.scrollLeft = drag.current.left + offset;
  }
  function finishDrag(event) {
    if (drag.current?.id !== event.pointerId) return;
    drag.current = null;
    event.currentTarget.classList.remove("is-dragging");
  }
  return <div className="chart-zoom">
    <div className="chart-zoom-controls" aria-label="Zoom">
      <button type="button" aria-label="Thu nhỏ biểu đồ" disabled={scale === min} onClick={() => setScale(Math.max(min, scale - step))}>-</button>
      <span>{scale}%</span>
      <button type="button" aria-label="Phóng to biểu đồ" disabled={scale === 400} onClick={() => setScale(Math.min(400, scale + step))}>+</button>
      <button type="button" disabled={scale === 100} onClick={() => setScale(100)}>100%</button>
      {!centerWidth && scale > 100 && <span className="subtle">Kéo ngang để xem</span>}
    </div>
    <div ref={scroll} className="chart-zoom-scroll" role="region" aria-label="Biểu đồ có thể cuộn" tabIndex={0}
      onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={finishDrag}
      onPointerCancel={finishDrag} onLostPointerCapture={finishDrag} onPointerLeave={finishDrag}>
      <div style={centerWidth ? {
        width: `min(${scale}%, ${centerWidth * scale / 100}px)`,
        marginInline: "auto",
      } : { width: `${scale}%` }}>{children}</div>
    </div>
  </div>;
}
