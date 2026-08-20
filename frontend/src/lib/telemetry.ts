export type TelemetrySummary = {
  days: number;
  eventCount: number;
  errorCount: number;
  averageDurationMs: number;
  p95DurationMs: number;
  byLayer: Record<string, number>;
  latestTimestamp: string;
  operations: Array<{
    layer: string;
    name: string;
    route: string;
    count: number;
    averageDurationMs: number;
    p95DurationMs: number;
    errorCount: number;
  }>;
};

type TelemetryDetails = Record<string, string | number | boolean>;

type TelemetryEvent = {
  layer: "frontend";
  name: string;
  status: "success" | "error";
  durationMs: number;
  route?: string;
  method?: string;
  statusCode?: number;
  details?: TelemetryDetails;
};

const queue: TelemetryEvent[] = [];
const MAX_QUEUE = 100;
const BATCH_SIZE = 20;
const FLUSH_DELAY_MS = 5_000;
let flushTimer: number | undefined;
let flushPromise: Promise<void> | null = null;
let retryDelayMs = FLUSH_DELAY_MS;
let initialized = false;

function normalizedRoute(input: RequestInfo | URL) {
  try {
    const url = new URL(String(input), window.location.origin);
    return url.pathname
      .split("/")
      .map((segment) =>
        /^(?:[A-Z]{2,10}-\d+|INC\d+|[0-9a-f]{8,}|[0-9a-f-]{32,})$/i.test(segment)
          ? ":id"
          : segment
      )
      .join("/")
      .slice(0, 160);
  } catch {
    return "/api/unknown";
  }
}

function scheduleFlush() {
  if (flushTimer !== undefined) return;
  flushTimer = window.setTimeout(() => {
    flushTimer = undefined;
    void flushTelemetry();
  }, retryDelayMs);
}

export function trackTelemetry(
  name: string,
  options: Omit<Partial<TelemetryEvent>, "layer" | "name"> = {}
) {
  queue.push({
    layer: "frontend",
    name: String(name || "unknown").slice(0, 80),
    status: options.status === "error" ? "error" : "success",
    durationMs: Math.max(0, Math.round(Number(options.durationMs || 0) * 100) / 100),
    ...(options.route ? { route: options.route } : {}),
    ...(options.method ? { method: options.method } : {}),
    ...(options.statusCode ? { statusCode: options.statusCode } : {}),
    ...(options.details ? { details: options.details } : {})
  });
  if (queue.length > MAX_QUEUE) queue.splice(0, queue.length - MAX_QUEUE);
  if (queue.length >= BATCH_SIZE) void flushTelemetry();
  else scheduleFlush();
}

async function performFlush() {
  if (flushTimer !== undefined) {
    window.clearTimeout(flushTimer);
    flushTimer = undefined;
  }
  if (queue.length === 0) return;
  const events = queue.splice(0, BATCH_SIZE);
  try {
    const response = await fetch("/api/telemetry/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ events }),
      keepalive: true
    });
    if (!response.ok) throw new Error("telemetry rejected");
    retryDelayMs = FLUSH_DELAY_MS;
  } catch {
    queue.unshift(...events);
    if (queue.length > MAX_QUEUE) queue.length = MAX_QUEUE;
    retryDelayMs = Math.min(retryDelayMs * 2, 60_000);
  }
  if (queue.length > 0) scheduleFlush();
}

export function flushTelemetry() {
  if (flushPromise) return flushPromise;
  flushPromise = performFlush().finally(() => {
    flushPromise = null;
  });
  return flushPromise;
}

export async function telemetryFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const started = performance.now();
  const route = normalizedRoute(input);
  const method = String(init.method || "GET").toUpperCase();
  try {
    const response = await fetch(input, init);
    trackTelemetry("api_request", {
      route,
      method,
      status: response.ok ? "success" : "error",
      statusCode: response.status,
      durationMs: performance.now() - started
    });
    return response;
  } catch (error) {
    trackTelemetry("api_request", {
      route,
      method,
      status: "error",
      durationMs: performance.now() - started
    });
    throw error;
  }
}

function initializeTelemetry() {
  if (initialized || typeof window === "undefined") return;
  initialized = true;
  trackTelemetry("app_open", {
    durationMs: performance.now(),
    details: {
      navigationType:
        (performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined)
          ?.type ?? "navigate"
    }
  });
  window.addEventListener("error", () => trackTelemetry("client_error", { status: "error" }));
  window.addEventListener("unhandledrejection", () =>
    trackTelemetry("unhandled_rejection", { status: "error" })
  );
  window.addEventListener("pagehide", () => void flushTelemetry());

  if ("PerformanceObserver" in window) {
    let count = 0;
    let totalMs = 0;
    let maxMs = 0;
    try {
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          count += 1;
          totalMs += entry.duration;
          maxMs = Math.max(maxMs, entry.duration);
        }
      });
      observer.observe({ type: "longtask", buffered: true });
      window.addEventListener("pagehide", () => {
        observer.disconnect();
        if (count > 0) {
          trackTelemetry("long_tasks", {
            durationMs: totalMs,
            details: { count, totalMs, maxMs }
          });
          void flushTelemetry();
        }
      });
    } catch {
      // Older browsers simply omit long-task telemetry.
    }
  }
}

initializeTelemetry();
