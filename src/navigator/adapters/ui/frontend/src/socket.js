const PREVIEW_HEADER_BYTES = 9;
const RECONNECT_MS = 400;

export function connect({ onEvent, onPreview, onLink }) {
  let closed = false;
  let socket = null;

  const open = () => {
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${scheme}//${location.host}/ws`);
    socket.binaryType = "arraybuffer";
    socket.onopen = () => onLink("live");
    socket.onclose = () => {
      onLink("offline");
      if (!closed) setTimeout(open, RECONNECT_MS);
    };
    socket.onmessage = (message) => {
      if (typeof message.data === "string") {
        try {
          onEvent(JSON.parse(message.data));
        } catch (error) {
          return;
        }
        return;
      }
      socket.send("ack");
      const bytes = new Uint8Array(message.data);
      if (bytes.length < PREVIEW_HEADER_BYTES) return;
      const frameId = new DataView(message.data).getBigUint64(1);
      onPreview(bytes[0], frameId, bytes.slice(PREVIEW_HEADER_BYTES));
    };
  };

  open();
  return () => {
    closed = true;
    if (socket) socket.close();
  };
}
