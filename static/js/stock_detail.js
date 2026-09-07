(() => {
    "use strict";

    const root = document.getElementById("stock-xray-root");
    const payloadNode = document.getElementById("stock-xray-data");
    if (!root || !payloadNode) return;

    let payload;
    try {
        payload = JSON.parse(payloadNode.textContent);
    } catch (_error) {
        return;
    }

    const canvas = document.getElementById("xray-canvas");
    const chart = document.getElementById("xray-chart");
    const tooltip = document.getElementById("xray-tooltip");
    const countNode = document.getElementById("xray-candle-count");
    const overlays = { ma50: true, ma200: true, pivot: true, support: true, markers: true };
    let candles = payload.chart?.candles || [];
    let markers = payload.markers || [];
    let viewStart = 0;
    let viewEnd = candles.length;
    let dragOrigin = null;

    const finite = (value) => Number.isFinite(Number(value));
    const money = (value) => finite(value) ? Number(value).toFixed(2) : "DATA UNAVAILABLE";
    const compact = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });

    const color = {
        text: "#344054",
        muted: "#98a2b3",
        grid: "#eaecf0",
        up: "#067647",
        down: "#b42318",
        volumeUp: "rgba(6, 118, 71, .28)",
        volumeDown: "rgba(180, 35, 24, .25)",
        ma50: "#7f56d9",
        ma200: "#f79009",
        pivot: "#175cd3",
        support: "#039855",
        marker: "#6941c6",
    };

    const resetViewport = () => {
        viewStart = 0;
        viewEnd = candles.length;
    };

    const line = (context, points, stroke, width = 1.5) => {
        if (points.length < 2) return;
        context.save();
        context.strokeStyle = stroke;
        context.lineWidth = width;
        context.beginPath();
        points.forEach(([x, y], index) => index ? context.lineTo(x, y) : context.moveTo(x, y));
        context.stroke();
        context.restore();
    };

    const drawLevel = (context, value, label, stroke, y, left, right) => {
        if (!finite(value)) return;
        const levelY = y(Number(value));
        context.save();
        context.strokeStyle = stroke;
        context.fillStyle = stroke;
        context.lineWidth = 1;
        context.setLineDash([5, 4]);
        context.beginPath();
        context.moveTo(left, levelY);
        context.lineTo(right, levelY);
        context.stroke();
        context.setLineDash([]);
        context.font = "10px system-ui";
        context.fillText(`${label} ${Number(value).toFixed(2)}`, left + 5, Math.max(12, levelY - 4));
        context.restore();
    };

    const chartGeometry = () => {
        if (!canvas || !candles.length) return null;
        const visible = candles.slice(viewStart, viewEnd);
        if (!visible.length) return null;
        const rect = canvas.getBoundingClientRect();
        const width = Math.max(Math.round(rect.width), 320);
        const height = Math.max(Math.round(rect.height), 360);
        const ratio = window.devicePixelRatio || 1;
        canvas.width = Math.round(width * ratio);
        canvas.height = Math.round(height * ratio);
        const context = canvas.getContext("2d");
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        context.clearRect(0, 0, width, height);

        const left = 58;
        const right = width - 72;
        const top = 18;
        const priceBottom = Math.round(height * 0.76);
        const volumeTop = priceBottom + 28;
        const volumeBottom = height - 30;
        const values = visible.flatMap((item) => [item.low, item.high]).filter(finite).map(Number);
        if (overlays.ma50) values.push(...visible.map((item) => item.ma50).filter(finite).map(Number));
        if (overlays.ma200) values.push(...visible.map((item) => item.ma200).filter(finite).map(Number));
        const levels = payload.scanner?.levels || {};
        if (overlays.pivot) values.push(...[levels.pivot, levels.resistance, levels.breakout_level].filter(finite).map(Number));
        if (overlays.support) values.push(...[levels.support, levels.base_high, levels.base_low].filter(finite).map(Number));
        const minimum = Math.min(...values);
        const maximum = Math.max(...values);
        const padding = Math.max((maximum - minimum) * 0.08, maximum * 0.005, 0.01);
        const low = minimum - padding;
        const high = maximum + padding;
        const span = high - low || 1;
        const y = (price) => top + ((high - price) / span) * (priceBottom - top);
        const xStep = (right - left) / visible.length;
        const x = (index) => left + xStep * (index + 0.5);
        return { context, visible, width, height, left, right, top, priceBottom, volumeTop, volumeBottom, low, high, y, x, xStep };
    };

    const draw = () => {
        const geometry = chartGeometry();
        if (!geometry) return;
        const { context, visible, width, left, right, top, priceBottom, volumeTop, volumeBottom, low, high, y, x, xStep } = geometry;
        context.font = "10px system-ui";
        context.fillStyle = color.muted;
        context.textBaseline = "middle";

        for (let index = 0; index <= 5; index += 1) {
            const price = high - ((high - low) * index / 5);
            const gridY = top + ((priceBottom - top) * index / 5);
            context.strokeStyle = color.grid;
            context.beginPath();
            context.moveTo(left, gridY);
            context.lineTo(right, gridY);
            context.stroke();
            context.fillStyle = color.text;
            context.fillText(price.toFixed(2), right + 8, gridY);
        }

        const maxVolume = Math.max(...visible.map((item) => Number(item.volume) || 0), 1);
        const bodyWidth = Math.max(1.5, Math.min(9, xStep * 0.62));
        visible.forEach((candle, index) => {
            const open = Number(candle.open);
            const highPrice = Number(candle.high);
            const lowPrice = Number(candle.low);
            const close = Number(candle.close);
            if (![open, highPrice, lowPrice, close].every(Number.isFinite)) return;
            const center = x(index);
            const rising = close >= open;
            context.strokeStyle = rising ? color.up : color.down;
            context.fillStyle = rising ? color.up : color.down;
            context.lineWidth = 1;
            context.beginPath();
            context.moveTo(center, y(highPrice));
            context.lineTo(center, y(lowPrice));
            context.stroke();
            const bodyTop = Math.min(y(open), y(close));
            const bodyHeight = Math.max(1.5, Math.abs(y(open) - y(close)));
            context.fillRect(center - bodyWidth / 2, bodyTop, bodyWidth, bodyHeight);

            const volume = Number(candle.volume) || 0;
            const volumeHeight = (volume / maxVolume) * (volumeBottom - volumeTop);
            context.fillStyle = rising ? color.volumeUp : color.volumeDown;
            context.fillRect(center - bodyWidth / 2, volumeBottom - volumeHeight, bodyWidth, volumeHeight);
        });

        if (overlays.ma50) {
            line(context, visible.map((item, index) => finite(item.ma50) ? [x(index), y(Number(item.ma50))] : null).filter(Boolean), color.ma50);
        }
        if (overlays.ma200) {
            line(context, visible.map((item, index) => finite(item.ma200) ? [x(index), y(Number(item.ma200))] : null).filter(Boolean), color.ma200);
        }

        const levels = payload.scanner?.levels || {};
        if (overlays.pivot) {
            drawLevel(context, levels.pivot, "Pivot", color.pivot, y, left, right);
            if (finite(levels.resistance) && Number(levels.resistance) !== Number(levels.pivot)) {
                drawLevel(context, levels.resistance, "Resistance", "#2e90fa", y, left, right);
            }
        }
        if (overlays.support) {
            drawLevel(context, levels.support, "Support", color.support, y, left, right);
            if (finite(levels.base_high) && finite(levels.base_low)) {
                const zoneTop = y(Number(levels.base_high));
                const zoneBottom = y(Number(levels.base_low));
                context.fillStyle = "rgba(23, 92, 211, .07)";
                context.fillRect(left, zoneTop, right - left, zoneBottom - zoneTop);
            }
        }

        if (overlays.markers && markers.length) {
            const markerMap = new Map(markers.map((item) => [item.date, item.state]));
            visible.forEach((candle, index) => {
                const state = markerMap.get(candle.date);
                if (!state) return;
                const center = x(index);
                const markerY = y(Number(candle.low)) + 10;
                context.fillStyle = color.marker;
                context.beginPath();
                context.moveTo(center, markerY);
                context.lineTo(center - 5, markerY + 8);
                context.lineTo(center + 5, markerY + 8);
                context.closePath();
                context.fill();
                context.save();
                context.translate(center + 7, markerY + 4);
                context.rotate(-Math.PI / 4);
                context.font = "9px system-ui";
                context.fillText(state, 0, 0);
                context.restore();
            });
        }

        const tickCount = Math.min(6, visible.length);
        for (let index = 0; index < tickCount; index += 1) {
            const candleIndex = Math.round(index * (visible.length - 1) / Math.max(tickCount - 1, 1));
            const candle = visible[candleIndex];
            const tickX = x(candleIndex);
            context.fillStyle = color.muted;
            context.textAlign = index === 0 ? "left" : index === tickCount - 1 ? "right" : "center";
            context.fillText(candle.date, tickX, volumeBottom + 17);
        }
        context.textAlign = "left";
        context.fillStyle = color.muted;
        context.fillText(`Volume · max ${compact.format(maxVolume)}`, left, priceBottom + 15);
        canvas._geometry = { visible, left, right, xStep };
    };

    const showTooltip = (event) => {
        const geometry = canvas?._geometry;
        if (!geometry || !tooltip) return;
        const rect = canvas.getBoundingClientRect();
        const relativeX = event.clientX - rect.left;
        const index = Math.max(0, Math.min(
            geometry.visible.length - 1,
            Math.floor((relativeX - geometry.left) / geometry.xStep),
        ));
        const candle = geometry.visible[index];
        if (!candle) return;
        const rows = [
            candle.date,
            `O ${money(candle.open)}  H ${money(candle.high)}`,
            `L ${money(candle.low)}  C ${money(candle.close)}`,
            `Volume ${Number(candle.volume || 0).toLocaleString("en-IN")}`,
            `MA50 ${money(candle.ma50)}  MA200 ${money(candle.ma200)}`,
        ];
        tooltip.replaceChildren(...rows.map((text, rowIndex) => {
            const node = document.createElement(rowIndex === 0 ? "strong" : "span");
            node.textContent = text;
            return node;
        }));
        tooltip.hidden = false;
        tooltip.style.left = `${Math.min(Math.max(relativeX + 14, 8), rect.width - 190)}px`;
        tooltip.style.top = `${Math.max(event.clientY - rect.top - 90, 8)}px`;
    };

    canvas?.addEventListener("mousemove", showTooltip);
    canvas?.addEventListener("mouseleave", () => { if (tooltip) tooltip.hidden = true; });
    canvas?.addEventListener("wheel", (event) => {
        if (candles.length < 20) return;
        event.preventDefault();
        const span = viewEnd - viewStart;
        const nextSpan = Math.max(20, Math.min(candles.length, Math.round(span * (event.deltaY > 0 ? 1.18 : 0.82))));
        const rect = canvas.getBoundingClientRect();
        const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
        const focus = viewStart + span * ratio;
        viewStart = Math.max(0, Math.min(candles.length - nextSpan, Math.round(focus - nextSpan * ratio)));
        viewEnd = viewStart + nextSpan;
        draw();
    }, { passive: false });
    canvas?.addEventListener("pointerdown", (event) => {
        dragOrigin = { x: event.clientX, start: viewStart, end: viewEnd };
        canvas.setPointerCapture(event.pointerId);
    });
    canvas?.addEventListener("pointermove", (event) => {
        if (!dragOrigin || candles.length <= dragOrigin.end - dragOrigin.start) return;
        const span = dragOrigin.end - dragOrigin.start;
        const shift = Math.round((dragOrigin.x - event.clientX) / canvas.clientWidth * span);
        viewStart = Math.max(0, Math.min(candles.length - span, dragOrigin.start + shift));
        viewEnd = viewStart + span;
        draw();
    });
    canvas?.addEventListener("pointerup", () => { dragOrigin = null; });

    document.querySelectorAll("[data-overlay]").forEach((input) => {
        input.addEventListener("change", () => {
            overlays[input.dataset.overlay] = input.checked;
            draw();
        });
    });

    document.querySelectorAll("[data-range]").forEach((button) => {
        button.addEventListener("click", async () => {
            if (button.classList.contains("is-active")) return;
            const url = new URL(root.dataset.detailApi, window.location.origin);
            url.searchParams.set("range", button.dataset.range);
            button.disabled = true;
            try {
                const response = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
                if (!response.ok) return;
                const next = await response.json();
                payload = next;
                candles = next.chart?.candles || [];
                markers = next.markers || [];
                resetViewport();
                document.querySelectorAll("[data-range]").forEach((item) => {
                    const active = item === button;
                    item.classList.toggle("is-active", active);
                    item.setAttribute("aria-pressed", String(active));
                });
                if (countNode) countNode.textContent = String(candles.length);
                draw();
            } finally {
                button.disabled = false;
            }
        });
    });

    const updateQuote = (data) => {
        if (String(data.symbol || "").toUpperCase() !== root.dataset.symbol.toUpperCase()) return;
        [["price", data.last_price], ["change", data.change], ["change-percent", data.change_percent]].forEach(([field, value]) => {
            const node = root.querySelector(`[data-field="${field}"]`);
            if (node && finite(value)) node.textContent = Number(value).toFixed(2);
        });
        const timestamp = root.querySelector("[data-field='timestamp']");
        if (timestamp && data.provider_timestamp) timestamp.textContent = data.provider_timestamp;
        const change = Number(data.change_percent);
        root.querySelectorAll(".xray-live-quote .market-change").forEach((node) => {
            node.classList.toggle("positive", change >= 0);
            node.classList.toggle("negative", change < 0);
        });
        const allowed = ["LIVE", "STALE", "MARKET_CLOSED", "DATA_UNAVAILABLE"];
        const nextStatus = allowed.includes(data.provider_state) ? data.provider_state : null;
        const status = document.getElementById("xray-market-status");
        if (status && nextStatus) {
            status.textContent = nextStatus;
            status.className = `status-pill status--${nextStatus.toLowerCase()}`;
        }
    };

    const connection = document.getElementById("xray-connection");
    let socket;
    let retry = 0;
    let reconnectTimer;
    let stopped = false;
    const setConnection = (text, state) => {
        if (!connection) return;
        connection.textContent = text;
        connection.dataset.state = state;
    };
    const connect = () => {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        socket = new WebSocket(`${protocol}//${window.location.host}/ws/market/`);
        setConnection("Connecting…", "connecting");
        socket.addEventListener("open", () => {
            retry = 0;
            setConnection("Stream connected", "connected");
            socket.send(JSON.stringify({
                type: "market.subscribe",
                instruments: [root.dataset.instrumentKey, root.dataset.symbol].filter(Boolean),
            }));
        });
        socket.addEventListener("message", (event) => {
            try {
                const message = JSON.parse(event.data);
                if (message.type === "market.tick" && message.version === 1) updateQuote(message.data || {});
            } catch (_error) {
                return;
            }
        });
        socket.addEventListener("close", () => {
            if (stopped) return;
            setConnection("REST fallback", "disconnected");
            const delay = Math.min(30_000, 1_000 * (2 ** retry));
            retry += 1;
            reconnectTimer = window.setTimeout(connect, delay);
        });
        socket.addEventListener("error", () => socket.close());
    };
    connect();
    window.addEventListener("beforeunload", () => {
        stopped = true;
        window.clearTimeout(reconnectTimer);
        socket?.close();
    });

    const searchInput = document.getElementById("dashboard-search");
    const searchResults = document.getElementById("search-results");
    let searchTimer;
    searchInput?.addEventListener("input", () => {
        window.clearTimeout(searchTimer);
        const query = searchInput.value.trim();
        if (query.length < 2) {
            searchResults.hidden = true;
            return;
        }
        searchTimer = window.setTimeout(async () => {
            const url = new URL(root.dataset.searchApi, window.location.origin);
            url.searchParams.set("q", query);
            const response = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
            if (!response.ok) return;
            const resultPayload = await response.json();
            searchResults.replaceChildren();
            (resultPayload.results || []).forEach((result) => {
                const row = document.createElement("button");
                row.type = "button";
                row.className = "search-result";
                row.textContent = `${result.label} · ${result.description || result.type}`;
                if (result.type === "stock" && result.symbol) {
                    row.addEventListener("click", () => {
                        window.location.href = `/stock/${encodeURIComponent(result.symbol)}/`;
                    });
                } else {
                    row.disabled = true;
                }
                searchResults.append(row);
            });
            searchResults.hidden = false;
        }, 250);
    });

    if (canvas) {
        new ResizeObserver(draw).observe(chart);
        draw();
    }
})();
