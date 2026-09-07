(() => {
    "use strict";

    const root = document.getElementById("dashboard-root");
    if (!root || !window.WebSocket) return;

    const connection = document.getElementById("live-connection");
    const maxDelay = 30_000;
    const baseDelay = 1_000;
    let attempt = 0;
    let socket;
    let reconnectTimer;
    let stopped = false;

    const subscriptions = () => Array.from(new Set(
        Array.from(document.querySelectorAll("[data-market-symbol]"))
            .flatMap((node) => [node.dataset.instrumentKey, node.dataset.marketSymbol])
            .filter(Boolean)
    )).slice(0, 100);

    const setConnection = (text, state) => {
        if (!connection) return;
        connection.textContent = text;
        connection.dataset.state = state;
    };

    const reconnect = () => {
        if (stopped) return;
        const exponential = Math.min(baseDelay * (2 ** attempt), maxDelay);
        const jitter = exponential * ((Math.random() * 0.4) - 0.2);
        const delay = Math.min(maxDelay, Math.max(500, Math.round(exponential + jitter)));
        attempt += 1;
        window.clearTimeout(reconnectTimer);
        reconnectTimer = window.setTimeout(connect, delay);
    };

    const connect = () => {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        socket = new WebSocket(`${protocol}//${window.location.host}/ws/market/`);
        setConnection("Connecting…", "connecting");

        socket.addEventListener("open", () => {
            attempt = 0;
            setConnection("Stream connected", "connected");
            socket.send(JSON.stringify({ type: "market.subscribe", instruments: subscriptions() }));
        });

        socket.addEventListener("message", (event) => {
            let message;
            try {
                message = JSON.parse(event.data);
            } catch (_error) {
                return;
            }
            if (message.type === "market.tick" && message.version === 1) {
                window.QuantumDashboard?.applyTick(message.data);
            }
        });

        socket.addEventListener("close", () => {
            setConnection("REST fallback", "disconnected");
            window.QuantumDashboard?.refresh();
            reconnect();
        });

        socket.addEventListener("error", () => socket.close());
    };

    const markStaleTicks = () => {
        const threshold = Number(root.dataset.staleAfter || 300) * 1000;
        document.querySelectorAll("[data-last-tick]").forEach((node) => {
            if (Date.now() - Number(node.dataset.lastTick) <= threshold) return;
            const status = node.querySelector("[data-field='status']");
            if (status && status.textContent !== "MARKET_CLOSED") {
                status.textContent = "STALE";
                status.className = "status-dot status--stale";
            }
        });
    };

    window.setInterval(markStaleTicks, 15_000);
    window.addEventListener("beforeunload", () => {
        stopped = true;
        window.clearTimeout(reconnectTimer);
        socket?.close();
    });
    connect();
})();
