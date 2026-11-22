import { AlertCircle, ArrowUpRight, LoaderCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { labels, number, time } from "../lib/data.js";

export function Badge({ value, children }) {
  return (
    <span className={`badge badge-${value || "missing"}`}>
      <span className="status-dot" />
      {children || labels[value] || "Chưa có dữ liệu"}
    </span>
  );
}
export function Empty({ title = "Chưa có dữ liệu", children }) {
  return (
    <div className="empty">
      <span className="empty-icon">—</span>
      <h3>{title}</h3>
      <p>
        {children ||
          "Kết quả sẽ xuất hiện khi dịch vụ công bố dữ liệu phù hợp."}
      </p>
    </div>
  );
}
export function Feedback({ resource, retry, children }) {
  if (resource.error && !resource.data)
    return (
      <div className="notice error" role="alert">
        <AlertCircle size={20} />
        <div>
          <strong>Không tải được dữ liệu</strong>
          <p>{resource.error}</p>
          <button className="text-button" onClick={retry}>
            Thử lại
          </button>
        </div>
      </div>
    );
  if (!resource.data)
    return (
      <div className="loading" role="status">
        <LoaderCircle className="spin" size={22} /> Đang đọc dữ liệu…
      </div>
    );
  return (
    <>
      {resource.error && (
        <div className="notice" role="status">
          <span>Chưa cập nhật được. Đang hiển thị dữ liệu tải thành công gần nhất.</span>
          <button className="text-button" onClick={retry}>Thử lại</button>
        </div>
      )}
      {resource.loading && (
        <p className="subtle" role="status">
          Đang cập nhật…
        </p>
      )}
      {children(resource.data)}
    </>
  );
}
export function PageTitle({ eyebrow, title, description, children }) {
  return (
    <div className="page-title">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children}
    </div>
  );
}
export function Panel({ title, subtitle, action, children, className = "" }) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Stat({ icon: Icon, label, value, detail, accent }) {
  return (
    <div className={`stat ${accent ? "stat-accent" : ""}`}>
      <div className="stat-top">
        <span>{label}</span>
        <Icon size={20} />
      </div>
      <strong>{value}</strong>
      <p>{detail}</p>
    </div>
  );
}
export function Table({ headers, children }) {
  return (
    <div className="table-wrap" role="region" aria-label="Bảng dữ liệu có thể cuộn ngang" tabIndex={0}>
      <table>
        <thead>
          <tr>
            {headers.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
export function DetailLink({ to, children = "Chi tiết" }) {
  return (
    <Link className="detail-link" to={to}>
      {children}
      <ArrowUpRight size={15} />
    </Link>
  );
}
export function Time({ value }) {
  return <span className="time-value">{time(value)}</span>;
}
export function Value({ value, unit = "" }) {
  return (
    <>
      {number(value, 1)}
      {value != null && unit ? ` ${unit}` : ""}
    </>
  );
}
