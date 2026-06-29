import { useEffect } from "react";

export interface ToastMsg {
  text: string;
  kind?: "ok" | "error" | "info";
}

export function Toast({
  msg,
  onClose,
}: {
  msg: ToastMsg | null;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(onClose, msg.kind === "error" ? 5000 : 2500);
    return () => clearTimeout(t);
  }, [msg, onClose]);
  if (!msg) return null;
  return <div className={`toast toast-${msg.kind ?? "info"}`}>{msg.text}</div>;
}
