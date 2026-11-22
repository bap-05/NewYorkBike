import { useEffect, useRef, useState } from "react";
import ChartZoom from "./ChartZoom.jsx";

export default function ChartDialog({ title, onClose, children }) {
  const dialog = useRef(null);
  useEffect(() => {
    if (!dialog.current.open) dialog.current.showModal();
  }, []);
  return (
    <dialog ref={dialog} className="calendar-chart-dialog" aria-label={title} onClose={onClose}>
      <header>
        <h3>{title}</h3>
        <form method="dialog"><button type="submit">Đóng</button></form>
      </header>
      {children}
    </dialog>
  );
}

export function ExpandableChart({ title, renderChart, reading, onClose }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="calendar-chart-preview" type="button" onClick={() => setOpen(true)}
        aria-label={`Mở lớn biểu đồ ${title}`}>
        {renderChart(false)}
        <span>Mở lớn</span>
      </button>
      {open && (
        <ChartDialog title={title} onClose={() => {
          setOpen(false);
          onClose?.();
        }}>
          <ChartZoom min={60} step={20}>{renderChart(true)}</ChartZoom>
          {reading}
        </ChartDialog>
      )}
    </>
  );
}
