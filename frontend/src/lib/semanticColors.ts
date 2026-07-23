import type { CSSProperties } from "react";

type SemanticContractPayload = {
  statusByKey?: Record<string, string>;
  priorityByKey?: Record<string, string>;
  neutral?: string;
  goalAccent?: string;
  goalSurface?: string;
} | null;

type SemanticConfig = {
  statusByKey: Record<string, string>;
  priorityByKey: Record<string, string>;
  neutral: string;
  goalAccent: string;
  goalSurface: string;
};

const DEFAULT_SEMANTIC_CONFIG: SemanticConfig = {
  statusByKey: {
    new: "var(--bbva-status-intake)",
    ready: "var(--bbva-status-intake)",
    analysing: "var(--bbva-status-intake)",
    blocked: "var(--bbva-status-intake)",
    "en progreso": "var(--bbva-status-progress)",
    "in progress": "var(--bbva-status-progress)",
    "to rework": "var(--bbva-status-progress)",
    rework: "var(--bbva-status-progress)",
    test: "var(--bbva-status-progress)",
    "ready to verify": "var(--bbva-status-progress)",
    accepted: "var(--bbva-status-accepted)",
    "ready to deploy": "var(--bbva-status-accepted)",
    deployed: "var(--bbva-status-deployed)",
    closed: "var(--bbva-priority-lowest)",
    resolved: "var(--bbva-priority-lowest)",
    done: "var(--bbva-priority-lowest)",
    open: "var(--bbva-status-open)",
    created: "var(--bbva-status-intake)"
  },
  priorityByKey: {
    "supone un impedimento": "var(--bbva-priority-highest)",
    highest: "var(--bbva-priority-highest)",
    high: "var(--bbva-priority-high)",
    medium: "var(--bbva-priority-medium)",
    low: "var(--bbva-priority-low)",
    lowest: "var(--bbva-priority-lowest)"
  },
  neutral: "var(--bbva-neutral)",
  goalAccent: "var(--bbva-goal-accent)",
  goalSurface: "var(--bbva-goal-surface)"
};

let runtimeSemanticConfig: SemanticConfig = {
  statusByKey: { ...DEFAULT_SEMANTIC_CONFIG.statusByKey },
  priorityByKey: { ...DEFAULT_SEMANTIC_CONFIG.priorityByKey },
  neutral: DEFAULT_SEMANTIC_CONFIG.neutral,
  goalAccent: DEFAULT_SEMANTIC_CONFIG.goalAccent,
  goalSurface: DEFAULT_SEMANTIC_CONFIG.goalSurface
};

function normalizeSemanticToken(value: string) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\s+/g, " ");
}

function normalizeColorMap(
  input: Record<string, string> | undefined,
  fallback: Record<string, string>
) {
  const mapped: Record<string, string> = {};
  for (const [key, value] of Object.entries(input ?? {})) {
    const token = normalizeSemanticToken(key);
    const color = String(value || "").trim();
    if (!token || !color) {
      continue;
    }
    mapped[token] = color;
  }
  if (Object.keys(mapped).length > 0) {
    return mapped;
  }
  return { ...fallback };
}

export function configureSemanticColors(payload: SemanticContractPayload) {
  if (!payload) {
    runtimeSemanticConfig = {
      statusByKey: { ...DEFAULT_SEMANTIC_CONFIG.statusByKey },
      priorityByKey: { ...DEFAULT_SEMANTIC_CONFIG.priorityByKey },
      neutral: DEFAULT_SEMANTIC_CONFIG.neutral,
      goalAccent: DEFAULT_SEMANTIC_CONFIG.goalAccent,
      goalSurface: DEFAULT_SEMANTIC_CONFIG.goalSurface
    };
    return;
  }
  runtimeSemanticConfig = {
    statusByKey: normalizeColorMap(payload.statusByKey, DEFAULT_SEMANTIC_CONFIG.statusByKey),
    priorityByKey: normalizeColorMap(
      payload.priorityByKey,
      DEFAULT_SEMANTIC_CONFIG.priorityByKey
    ),
    neutral: String(payload.neutral || "").trim() || DEFAULT_SEMANTIC_CONFIG.neutral,
    goalAccent: String(payload.goalAccent || "").trim() || DEFAULT_SEMANTIC_CONFIG.goalAccent,
    goalSurface: String(payload.goalSurface || "").trim() || DEFAULT_SEMANTIC_CONFIG.goalSurface
  };
}

function colorWithAlpha(color: string, alpha: number) {
  const source = String(color || "").trim() || runtimeSemanticConfig.neutral;
  const token = source.replace(/^#/, "");
  const boundedAlpha = Math.min(1, Math.max(0, alpha));
  if (/^[0-9a-fA-F]{6}$/.test(token)) {
    const r = Number.parseInt(token.slice(0, 2), 16);
    const g = Number.parseInt(token.slice(2, 4), 16);
    const b = Number.parseInt(token.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${boundedAlpha})`;
  }
  return `color-mix(in srgb, ${source} ${boundedAlpha * 100}%, transparent)`;
}

function chipPalette(color: string) {
  const normalized = String(color || "").trim().toUpperCase();
  const goalAccent = runtimeSemanticConfig.goalAccent.toUpperCase();
  if (normalized === goalAccent) {
    return {
      color: runtimeSemanticConfig.goalAccent,
      borderColor: colorWithAlpha(runtimeSemanticConfig.goalAccent, 0.64),
      backgroundColor: runtimeSemanticConfig.goalSurface
    };
  }
  return {
    color,
    borderColor: colorWithAlpha(color, 0.62),
    backgroundColor: colorWithAlpha(color, 0.16)
  };
}

export function statusColor(status: string) {
  return (
    runtimeSemanticConfig.statusByKey[normalizeSemanticToken(status)] ??
    runtimeSemanticConfig.neutral
  );
}

export function priorityColor(priority: string) {
  return (
    runtimeSemanticConfig.priorityByKey[normalizeSemanticToken(priority)] ??
    runtimeSemanticConfig.neutral
  );
}

export function semanticChipStyle(
  value: string,
  kind: "status" | "priority"
): CSSProperties {
  const color = kind === "priority" ? priorityColor(value) : statusColor(value);
  const palette = chipPalette(color);
  return {
    color: palette.color,
    borderColor: palette.borderColor,
    backgroundColor: palette.backgroundColor
  };
}

export function neutralChipStyle(fontSize = "0.8rem"): CSSProperties {
  return {
    color: "var(--bbva-text-muted)",
    borderColor: "var(--bbva-border-strong)",
    background:
      "color-mix(in srgb, var(--bbva-surface) 86%, var(--bbva-surface-2))",
    fontSize
  };
}

export function kanbanHeaderStyle(status: string, active: boolean): CSSProperties {
  const color = statusColor(status);
  return {
    color,
    borderColor: colorWithAlpha(color, active ? 0.72 : 0.45),
    backgroundColor: colorWithAlpha(color, active ? 0.2 : 0.12),
    boxShadow: active ? `0 0 0 3px ${colorWithAlpha(color, 0.18)}` : "none"
  };
}

export function semanticButtonStyle(
  value: string,
  kind: "status" | "priority",
  active: boolean
): CSSProperties {
  const color = kind === "priority" ? priorityColor(value) : statusColor(value);
  return {
    color,
    borderColor: colorWithAlpha(color, active ? 0.72 : 0.45),
    backgroundColor: colorWithAlpha(color, active ? 0.2 : 0.12),
    boxShadow: active ? `0 0 0 3px ${colorWithAlpha(color, 0.16)}` : "none"
  };
}
