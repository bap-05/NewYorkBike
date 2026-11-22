import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import "leaflet/dist/leaflet.css";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ErrorBoundary fallback={() => (
      <main className="fatal">
        <h1>Không thể hiển thị trang</h1>
        <p>Hãy tải lại trang để thử lại.</p>
        <button onClick={() => location.reload()}>Tải lại</button>
      </main>
    )}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ErrorBoundary>
  </React.StrictMode>,
);
