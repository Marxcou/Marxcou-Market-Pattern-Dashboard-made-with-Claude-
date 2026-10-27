import { useEffect, useRef } from "react";

export interface LiveEvent { id: number; type: "quote" | "news" | "detection" | "source_status"; payload: Record<string, unknown>; created_at: string }

// WebSocket /ws with simple reconnecting. If the connection drops, the polling of the pages stays active.
export function useLiveEvents(onEvent: (e: LiveEvent) => void) {
  const cb = useRef(onEvent);
  cb.current = onEvent;
  useEffect(() => {
    if (typeof WebSocket === "undefined") return;
    let ws: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout>;
    let closed = false;
    const connect = () => {
      try {
        ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
      } catch {
        return;
      }
      ws.onmessage = (m) => { try { cb.current(JSON.parse(m.data as string) as LiveEvent); } catch { /* ignore invalid event */ } };
      ws.onclose = () => { if (!closed) timer = setTimeout(connect, 5000); };
    };
    connect();
    return () => { closed = true; clearTimeout(timer); ws?.close(); };
  }, []);
}
