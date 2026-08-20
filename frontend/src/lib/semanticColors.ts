import type { CSSProperties } from "react";

type SemanticConfig = {
  statusByKey: Record<string, string>;
  priorityByKey: Record<string, string>;
  neutral: string;
  goalAccent: string;
  goalSurface: string;
};

const SEMANTIC_CONFIG: SemanticConfig = {
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

function normalizeSemanticToken(value: string) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\s+/g, " ");
}

function colorWithAlpha(color: string, alpha: number) {
  const source = String(color || "").trim() || SEMANTIC_CONFIG.neutral;
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
  const goalAccent = SEMANTIC_CONFIG.goalAccent.toUpperCase();
  if (normalized === goalAccent) {
    return {
      color: SEMANTIC_CONFIG.goalAccent,
      borderColor: colorWithAlpha(SEMANTIC_CONFIG.goalAccent, 0.64),
      backgroundColor: SEMANTIC_CONFIG.goalSurface
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
    SEMANTIC_CONFIG.statusByKey[normalizeSemanticToken(status)] ?? SEMANTIC_CONFIG.neutral
  );
}

export function priorityColor(priority: string) {
  return (
    SEMANTIC_CONFIG.priorityByKey[normalizeSemanticToken(priority)] ?? SEMANTIC_CONFIG.neutral
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
