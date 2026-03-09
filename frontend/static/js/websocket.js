// WebSocket manager with auto-reconnect
const WS = (() => {
  let socket = null;
  let reconnectTimer = null;
  const handlers = {};
  let reconnectDelay = 2000;

  function connect() {
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const token = localStorage.getItem("dm_token") || "";
    const qs = token ? `?token=${encodeURIComponent(token)}` : "";
    socket = new WebSocket(`${protocol}://${location.host}/ws/downloads${qs}`);

    socket.onopen = () => {
      reconnectDelay = 2000;
      console.debug("[WS] connected");
      socket._pingInterval = setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) socket.send("ping");
      }, 25000);
    };

    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (handlers[msg.type]) handlers[msg.type](msg.data, msg);
      } catch (e) {
        // ignore non-JSON messages
      }
    };

    socket.onclose = () => {
      clearInterval(socket._pingInterval);
      console.debug(`[WS] closed, reconnecting in ${reconnectDelay}ms`);
      reconnectTimer = setTimeout(() => {
        reconnectDelay = Math.min(reconnectDelay * 1.5, 30000);
        connect();
      }, reconnectDelay);
    };

    socket.onerror = () => socket.close();
  }

  return {
    init: connect,
    on(type, fn) { handlers[type] = fn; },
  };
})();
