import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { installDebugAssistant } from "./lib/debugAssistant";
import "./styles/global.css";

// 接入 debug-assistant：连不上时静默降级
installDebugAssistant({
  project: "PaperAssistant",
  module: "frontend",
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
