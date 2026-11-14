const RECONNECT_MS = 400;

export function connect({ onEvent, onLink }) {
  let closed = false;
  let socket = null;

  const open = () => {
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${scheme}//${location.host}/ws`);
    socket.onopen = () => onLink("live");
    socket.onclose = () => {
      onLink("offline");
      if (!closed) setTimeout(open, RECONNECT_MS);
    };
    socket.onmessage = (message) => {
      if (typeof message.data !== "string") return;
      try {
        onEvent(JSON.parse(message.data));
      } catch (error) {
        return;
      }
    };
  };

  open();
  return () => {
    closed = true;
    if (socket) socket.close();
  };
}
