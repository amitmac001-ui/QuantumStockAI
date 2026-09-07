(() => {
    "use strict";

    const root = document.getElementById("dashboard-root");
    if (!root) return;

    const matchingNodes = (symbol) => Array.from(
        document.querySelectorAll("[data-market-symbol]")
    ).filter((node) => node.dataset.marketSymbol?.toUpperCase() === String(symbol || "").toUpperCase());

    const numberText = (value, digits = 2) => {
        const numeric = Number(value);
        return Number.isFinite(numeric) ? numeric.toFixed(digits) : null;
    };

    const updateNode = (node, data) => {
        const mappings = [
            ["price", data.last_price ?? data.price],
            ["change", data.change],
            ["change-percent", data.change_percent],
            ["timestamp", data.provider_timestamp],
        ];
        mappings.forEach(([field, value]) => {
            const target = node.querySelector(`[data-field="${field}"]`);
            if (!target || value === null || value === undefined) return;
            target.textContent = field === "timestamp" ? String(value) : numberText(value);
        });
        const percent = Number(data.change_percent);
        if (Number.isFinite(percent)) {
            node.querySelectorAll(".market-change").forEach((target) => {
                target.classList.toggle("positive", percent >= 0);
                target.classList.toggle("negative", percent < 0);
            });
        }
        node.dataset.lastTick = String(Date.now());
    };

    const applyTick = (data) => {
        if (!data || !data.symbol) return;
        matchingNodes(data.symbol).forEach((node) => updateNode(node, data));
    };

    const refresh = async () => {
        try {
            const response = await fetch(root.dataset.homeApi, {
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            });
            if (!response.ok) return false;
            const payload = await response.json();
            payload.indices?.items?.forEach((item) => {
                if (item.symbol) matchingNodes(item.symbol).forEach((node) => updateNode(node, item));
            });
            const marketState = document.getElementById("market-state");
            if (marketState && payload.meta?.status) marketState.textContent = payload.meta.status;
            return true;
        } catch (_error) {
            return false;
        }
    };

    const drawChart = (container) => {
        const canvas = container.querySelector("canvas");
        const script = container.querySelector("script[type='application/json']");
        if (!canvas || !script) return;
        let candles;
        try {
            candles = JSON.parse(script.textContent);
        } catch (_error) {
            return;
        }
        if (!Array.isArray(candles) || candles.length < 2) return;
        const width = container.clientWidth || 320;
        const height = container.clientHeight || 122;
        const ratio = window.devicePixelRatio || 1;
        canvas.width = Math.round(width * ratio);
        canvas.height = Math.round(height * ratio);
        const context = canvas.getContext("2d");
        context.scale(ratio, ratio);
        context.clearRect(0, 0, width, height);

        const prices = candles.flatMap((candle) => [Number(candle.high), Number(candle.low)]).filter(Number.isFinite);
        const pivot = Number(canvas.dataset.pivot);
        if (Number.isFinite(pivot) && pivot > 0) prices.push(pivot);
        const minimum = Math.min(...prices);
        const maximum = Math.max(...prices);
        const span = maximum - minimum || 1;
        const pad = 9;
        const volumeHeight = 22;
        const priceBottom = height - volumeHeight - 5;
        const y = (price) => pad + ((maximum - price) / span) * (priceBottom - pad);
        const step = (width - pad * 2) / candles.length;
        const bodyWidth = Math.max(2, Math.min(6, step * 0.55));

        const volumes = candles.map((candle) => Number(candle.volume)).filter(Number.isFinite);
        const maxVolume = Math.max(...volumes, 0);
        if (maxVolume > 0) {
            candles.forEach((candle, index) => {
                const volume = Number(candle.volume);
                if (!Number.isFinite(volume) || volume < 0) return;
                const open = Number(candle.open);
                const close = Number(candle.close);
                const x = pad + step * (index + 0.5);
                const barHeight = Math.max(1, (volume / maxVolume) * volumeHeight);
                context.fillStyle = close >= open ? "#a9dac4" : "#e5b5b1";
                context.fillRect(x - bodyWidth / 2, height - barHeight - 2, bodyWidth, barHeight);
            });
        }

        if (Number.isFinite(pivot) && pivot > 0) {
            context.save();
            context.strokeStyle = "#175cd3";
            context.setLineDash([4, 3]);
            context.beginPath();
            context.moveTo(pad, y(pivot));
            context.lineTo(width - pad, y(pivot));
            context.stroke();
            context.restore();
        }

        candles.forEach((candle, index) => {
            const open = Number(candle.open);
            const high = Number(candle.high);
            const low = Number(candle.low);
            const close = Number(candle.close);
            if (![open, high, low, close].every(Number.isFinite)) return;
            const x = pad + step * (index + 0.5);
            const color = close >= open ? "#067647" : "#b42318";
            context.strokeStyle = color;
            context.fillStyle = color;
            context.beginPath();
            context.moveTo(x, y(high));
            context.lineTo(x, y(low));
            context.stroke();
            const top = Math.min(y(open), y(close));
            const bodyHeight = Math.max(1.5, Math.abs(y(open) - y(close)));
            context.fillRect(x - bodyWidth / 2, top, bodyWidth, bodyHeight);
        });
    };

    document.querySelectorAll(".mini-chart").forEach(drawChart);

    document.querySelectorAll(".stock-card[data-stock-url]").forEach((card) => {
        card.addEventListener("click", (event) => {
            if (event.target.closest("a, button, details, summary")) return;
            window.location.href = card.dataset.stockUrl;
        });
        card.addEventListener("keydown", (event) => {
            if (event.key !== "Enter" && event.key !== " ") return;
            if (event.target.closest("a, button, details, summary")) return;
            event.preventDefault();
            window.location.href = card.dataset.stockUrl;
        });
    });

    let debounceTimer;
    let selectionTimer;
    const searchInput = document.getElementById("dashboard-search");
    const searchResults = document.getElementById("search-results");
    const searchSelection = document.getElementById("search-selection");

    const clearSearchFocus = () => {
        document.querySelectorAll(".search-focus").forEach((node) => node.classList.remove("search-focus"));
        document.querySelectorAll(".is-filtered-out").forEach((node) => node.classList.remove("is-filtered-out"));
    };

    const showSelection = (message) => {
        if (!searchSelection) return;
        window.clearTimeout(selectionTimer);
        searchSelection.textContent = message;
        searchSelection.hidden = false;
        selectionTimer = window.setTimeout(() => {
            searchSelection.hidden = true;
        }, 5000);
    };

    const selectSearchResult = (result) => {
        clearSearchFocus();
        searchInput.value = result.label || result.symbol || "";
        searchResults.hidden = true;
        searchInput.setAttribute("aria-expanded", "false");

        if (result.type === "sector") {
            const cards = Array.from(document.querySelectorAll(".stock-card[data-sector]"));
            const matching = cards.filter((card) => card.dataset.sector?.toLowerCase() === String(result.label).toLowerCase());
            cards.filter((card) => !matching.includes(card)).forEach((card) => card.classList.add("is-filtered-out"));
            matching.forEach((card) => card.classList.add("search-focus"));
            if (matching[0]) matching[0].scrollIntoView({ behavior: "smooth", block: "center" });
            showSelection(matching.length ? `${result.label} sector · ${matching.length} scanner card${matching.length === 1 ? "" : "s"}` : `${result.label} sector selected · no current scanner cards`);
            return;
        }

        if (result.type === "stock" && result.url) {
            window.location.assign(result.url);
            return;
        }

        const matched = matchingNodes(result.symbol || result.label);
        matched.forEach((node) => node.classList.add("search-focus"));
        if (matched[0]) matched[0].scrollIntoView({ behavior: "smooth", block: "center" });
        showSelection(matched.length ? `${result.label} selected` : `${result.label} selected · no current market or scanner card`);
    };

    const renderSearch = (payload) => {
        searchResults.replaceChildren();
        const results = payload.results || [];
        if (!results.length) {
            const empty = document.createElement("div");
            empty.className = "search-result";
            empty.textContent = "No persisted match found.";
            searchResults.append(empty);
        } else {
            results.forEach((result) => {
                const row = document.createElement("button");
                row.type = "button";
                row.className = "search-result";
                const type = document.createElement("span");
                type.className = "search-result__type";
                type.textContent = result.type;
                const copy = document.createElement("div");
                const label = document.createElement("strong");
                label.textContent = result.label;
                const description = document.createElement("small");
                description.textContent = result.description || "";
                copy.append(label, description);
                row.append(type, copy);
                row.addEventListener("click", () => selectSearchResult(result));
                searchResults.append(row);
            });
        }
        searchResults.hidden = false;
        searchInput.setAttribute("aria-expanded", "true");
    };

    searchInput?.addEventListener("input", () => {
        window.clearTimeout(debounceTimer);
        clearSearchFocus();
        const query = searchInput.value.trim();
        if (query.length < 2) {
            searchResults.hidden = true;
            searchInput.setAttribute("aria-expanded", "false");
            return;
        }
        debounceTimer = window.setTimeout(async () => {
            const url = new URL(root.dataset.searchApi, window.location.origin);
            url.searchParams.set("q", query);
            try {
                const response = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
                if (response.ok) renderSearch(await response.json());
            } catch (_error) {
                searchResults.hidden = true;
            }
        }, 250);
    });

    searchInput?.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            searchResults.hidden = true;
            searchInput.setAttribute("aria-expanded", "false");
            clearSearchFocus();
        }
    });

    document.addEventListener("click", (event) => {
        if (searchResults && !event.target.closest(".search-box")) {
            searchResults.hidden = true;
            searchInput?.setAttribute("aria-expanded", "false");
        }
    });

    window.QuantumDashboard = { applyTick, refresh };
})();
