export function drawDetailedGraph(containerElement, data, config = {}) {
  const defaultMargin = { top: 20, right: 20, bottom: 40, left: 68 };
  const margin = { ...defaultMargin, ...(config.margin || {}) };
  const valueKey = config.yKey || "value";
  const clipId = `clip-${Math.random().toString(36).slice(2)}`;
  const liveWindowMs = config.liveWindowMs || 60_000;

  // Keep mutable values in closure so update() can append one sample at a time.
  let width = config.width || containerElement.clientWidth || 600;
  let height = config.height || 300;
  let sortedData = normalizeData(data);
  let lastSamplePrice = sortedData.length
    ? sortedData[sortedData.length - 1].price
    : null;
  let lastSampleTimeMs = sortedData.length
    ? sortedData[sortedData.length - 1].date.getTime()
    : null;
  let lastTradeTimestampMs = null;

  let d3svg, xAxisGroup, yAxisGroup, lineGroup, gridGroup, emptyStateText;
  let currentXScale, globalYScale, lineGenerator;
  let firstBuild = true;
  const xTickFormat = d3.timeFormat("%H:%M:%S");

  function render() {
    width = config.width || containerElement.clientWidth || 600;
    height = config.height || 300;

    if (firstBuild) {
      containerElement.innerHTML = "";

      const svgEl = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svgEl.classList.add("portfolio-graph");
      containerElement.appendChild(svgEl);

      d3svg = d3.select(svgEl).attr("width", width).attr("height", height);

      xAxisGroup = d3svg
        .append("g")
        .attr("class", "x-axis")
        .attr("transform", `translate(0,${height - margin.bottom})`);

      yAxisGroup = d3svg
        .append("g")
        .attr("class", "y-axis")
        .attr("transform", `translate(${margin.left},0)`);

      gridGroup = d3svg.append("g").attr("class", "y-grid");
      lineGroup = d3svg.append("g").attr("class", "line-group");
      emptyStateText = d3svg.append("text").attr("class", "graph-empty-text");

      d3svg
        .append("clipPath")
        .attr("id", clipId)
        .append("rect")
        .attr("x", margin.left)
        .attr("y", margin.top)
        .attr("width", width - margin.left - margin.right)
        .attr("height", height - margin.top - margin.bottom);

      lineGroup.attr("clip-path", `url(#${clipId})`);

      if (config.resizeOnWindow) {
        window.addEventListener("resize", render);
      }

      firstBuild = false;
    } else {
      d3svg.attr("width", width).attr("height", height);
      xAxisGroup.attr("transform", `translate(0,${height - margin.bottom})`);
      yAxisGroup.attr("transform", `translate(${margin.left},0)`);
      d3svg
        .select(`clipPath#${clipId} rect`)
        .attr("width", width - margin.left - margin.right)
        .attr("height", height - margin.top - margin.bottom);
    }

    refreshLiveChart(new Date());
  }

  function refreshLiveChart(now) {
    const xDomain = getRollingDomain(now);
    trimOlderThan(xDomain[0]);

    currentXScale = d3
      .scaleTime()
      .domain(xDomain)
      .range([margin.left, width - margin.right]);

    emptyStateText
      .attr("x", width / 2)
      .attr("y", height / 2)
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "middle");

    const numTicks = width < 400 ? 4 : 6;
    xAxisGroup.call(
      d3.axisBottom(currentXScale).ticks(numTicks).tickFormat(xTickFormat)
    );

    if (!sortedData.length) {
      lineGroup.selectAll("path").remove();
      yAxisGroup.selectAll("*").remove();
      gridGroup.selectAll("*").remove();
      emptyStateText.text(config.emptyText || "No data yet").attr("display", null);
      return;
    }

    emptyStateText.attr("display", "none");

    const visibleData = sortedData.filter(
      (point) => point.date >= xDomain[0] && point.date <= xDomain[1]
    );
    const lineData = visibleData.length
      ? visibleData
      : [
          { date: xDomain[0], price: sortedData[sortedData.length - 1].price },
          { date: xDomain[1], price: sortedData[sortedData.length - 1].price },
        ];
    const yData = lineData;

    const yMin = d3.min(yData, (point) => point.price);
    const yMax = d3.max(yData, (point) => point.price);
    const yPad = calculateYPadding(yMin, yMax);

    globalYScale = d3
      .scaleLinear()
      .domain([yMin - yPad, yMax + yPad])
      .range([height - margin.bottom, margin.top]);

    const isGain =
      lineData[lineData.length - 1].price >= lineData[0].price;

    lineGenerator = d3
      .line()
      .x((point) => currentXScale(point.date))
      .y((point) => globalYScale(point.price));

    lineGroup
      .selectAll("path")
      .data([lineData])
      .join("path")
      .attr("fill", "none")
      .attr("stroke", isGain ? "#28a745" : "#dc3545")
      .attr("stroke-width", 3)
      .attr("d", lineGenerator);

    const yAxisFormatter = getYAxisFormatter();
    yAxisGroup.call(
      d3
        .axisLeft(globalYScale)
        .ticks(6)
        .tickFormat(yAxisFormatter)
        .tickPadding(10)
    );
    yAxisGroup.select(".domain").remove();

    gridGroup
      .attr("transform", `translate(${margin.left},0)`)
      .call(
        d3
          .axisLeft(globalYScale)
          .ticks(6)
          .tickSize(-(width - margin.left - margin.right))
          .tickFormat("")
      );
    gridGroup.selectAll("line").attr("stroke", "grey").attr("stroke-opacity", 0.2);
    gridGroup.select("path").remove();
  }

  // Rolling window: x-axis always represents "now - window" to "now".
  function getRollingDomain(now) {
    return [new Date(now.getTime() - liveWindowMs), now];
  }

  function trimOlderThan(cutoff) {
    while (sortedData.length && sortedData[0].date < cutoff) {
      sortedData.shift();
    }
  }

  // We sample every tick instead of only trades so time is continuous:
  // no-trade periods still produce a flat line, and trade changes appear as jumps.
  function resolveSnapshotPrice(snapshot, previousPrice, hasNewTrade) {
    if (Array.isArray(snapshot)) {
      const normalized = normalizeData(snapshot);
      const lastPoint = normalized[normalized.length - 1];
      return lastPoint ? lastPoint.price : previousPrice;
    }

    if (snapshot?.force_price) {
      const forcedPrice = firstFinite(snapshot?.price);
      if (forcedPrice !== null) {
        return forcedPrice;
      }
    }

    if (hasNewTrade) {
      const tradePrice = firstFinite(
        snapshot?.price,
        snapshot?.last_trade_price,
        snapshot?.last_price,
        snapshot?.trade_price
      );
      if (tradePrice !== null) {
        return tradePrice;
      }
    }

    const bestBid = toFiniteNumber(snapshot?.best_bid);
    const bestAsk = toFiniteNumber(snapshot?.best_ask);
    if (bestBid !== null && bestAsk !== null && bestBid > 0 && bestAsk > 0) {
      return (bestBid + bestAsk) / 2;
    }

    return previousPrice;
  }

  function appendSample(snapshot) {
    // Sample time represents the websocket tick time (chart x-axis), not last trade time.
    let now = resolveSampleTime(snapshot?.server_time);
    if (lastSampleTimeMs !== null && now.getTime() <= lastSampleTimeMs) {
      now = new Date(lastSampleTimeMs + 1);
    }
    const hasNewTrade = didReceiveNewTrade(snapshot);
    const nextPrice = resolveSnapshotPrice(snapshot, lastSamplePrice, hasNewTrade);

    if (nextPrice !== null) {
      sortedData.push({ date: now, price: nextPrice });
      lastSamplePrice = nextPrice;
      lastSampleTimeMs = now.getTime();
    }

    trimOlderThan(new Date(now.getTime() - liveWindowMs));
    return now;
  }

  function didReceiveNewTrade(snapshot) {
    const tradeTimestampMs = resolveTradeTimestampMs(snapshot);
    if (tradeTimestampMs === null) {
      return false;
    }
    if (
      lastTradeTimestampMs === null ||
      tradeTimestampMs > lastTradeTimestampMs
    ) {
      lastTradeTimestampMs = tradeTimestampMs;
      return true;
    }
    return false;
  }

  function resolveTradeTimestampMs(snapshot) {
    const rawTradeTimestamp =
      snapshot?.timestamp ??
      snapshot?.last_timestamp ??
      snapshot?.last_trade_timestamp ??
      null;
    if (rawTradeTimestamp == null) {
      return null;
    }
    const parsedDate = new Date(rawTradeTimestamp);
    if (Number.isFinite(parsedDate.getTime())) {
      return parsedDate.getTime();
    }
    const numeric = toFiniteNumber(rawTradeTimestamp);
    return numeric === null ? null : numeric;
  }

  function getYAxisFormatter() {
    if (typeof config.yTickFormat === "function") {
      return config.yTickFormat;
    }
    return d3.format(config.yTickFormat || ".2f");
  }

  function normalizeData(inputData = []) {
    return [...inputData]
      .map((point) => {
        const date = point.date instanceof Date ? point.date : new Date(point.date);
        const price = firstFinite(
          point?.price,
          point?.[valueKey],
          point?.last_trade_price,
          point?.last_price
        );
        return { date, price };
      })
      .filter(
        (point) =>
          Number.isFinite(point.date.getTime()) && Number.isFinite(point.price)
      )
      .sort((a, b) => a.date - b.date);
  }

  function firstFinite(...values) {
    for (const value of values) {
      const numeric = toFiniteNumber(value);
      if (numeric !== null) {
        return numeric;
      }
    }
    return null;
  }

  function toFiniteNumber(value) {
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === "string" && value.trim() !== "") {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
    return null;
  }

  function resolveSampleTime(rawServerTime) {
    if (rawServerTime == null) {
      return new Date();
    }
    const parsed = new Date(rawServerTime);
    if (Number.isFinite(parsed.getTime())) {
      return parsed;
    }
    return new Date();
  }

  function calculateYPadding(minValue, maxValue) {
    const span = maxValue - minValue;
    if (span === 0) {
      return Math.max(Math.abs(maxValue) * 0.02, 1);
    }
    return span * 0.02;
  }

  render();

  return {
    update(snapshot = {}) {
      const now = appendSample(snapshot);
      refreshLiveChart(now);
    }
  };
}
