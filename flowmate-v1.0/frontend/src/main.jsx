import React from "react"; import { createRoot } from "react-dom/client"; import App from "./App.jsx"; import "./style.css";
createRoot(document.getElementById("root")).render(<App />);

if ("serviceWorker" in navigator && !window.Capacitor?.isNativePlatform?.()) window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
