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
    new: "#E85D63",
    ready: "#E85D63",
    analysing: "#E85D63",
    blocked: "#E85D63",
    "en progreso": "#F59E0B",
    "in progress": "#F59E0B",
    "to rework": "#F59E0B",
    rework: "#F59E0B",
    test: "#F59E0B",
    "ready to verify": "#F59E0B",
    accepted: "#4CAF50",
    "ready to deploy": "#4CAF50",
    deployed: "#5B3FD0",
    closed: "#15803D",
    resolved: "#15803D",
    done: "#15803D",
    open: "#FBBF24",
    created: "#E85D63"
  },
  priorityByKey: {
    "supone un impedimento": "#B4232A",
    highest: "#B4232A",
    high: "#D64550",
    medium: "#F59E0B",
    low: "#22A447",
    lowest: "#15803D"
  },
  neutral: "#E2E6EE",
  goalAccent: "#5B3FD0",
  goalSurface: "#ECE6FF"
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

function hexToRgba(hexColor: string, alpha: number) {
  const token = String(hexColor || "")
    .trim()
    .replace(/^#/, "");
  if (!/^[0-9a-fA-F]{6}$/.test(token)) {
    const fallback = runtimeSemanticConfig.neutral
      .replace(/^#/, "")
      .match(/^[0-9a-fA-F]{6}$/)
      ? runtimeSemanticConfig.neutral
      : "#E2E6EE";
    const normalizedFallback = fallback.replace(/^#/, "");
    const r = Number.parseInt(normalizedFallback.slice(0, 2), 16);
    const g = Number.parseInt(normalizedFallback.slice(2, 4), 16);
    const b = Number.parseInt(normalizedFallback.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  const r = Number.parseInt(token.slice(0, 2), 16);
  const g = Number.parseInt(token.slice(2, 4), 16);
  const b = Number.parseInt(token.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function chipPalette(color: string) {
  const normalized = String(color || "").trim().toUpperCase();
  const goalAccent = runtimeSemanticConfig.goalAccent.toUpperCase();
  if (normalized === goalAccent) {
    return {
      color: runtimeSemanticConfig.goalAccent,
      borderColor: hexToRgba(runtimeSemanticConfig.goalAccent, 0.64),
      backgroundColor: runtimeSemanticConfig.goalSurface
    };
  }
  return {
    color,
    borderColor: hexToRgba(color, 0.62),
    backgroundColor: hexToRgba(color, 0.16)
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
    borderColor: hexToRgba(color, active ? 0.72 : 0.45),
    backgroundColor: hexToRgba(color, active ? 0.2 : 0.12),
    boxShadow: active ? `0 0 0 3px ${hexToRgba(color, 0.18)}` : "none"
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
    borderColor: hexToRgba(color, active ? 0.72 : 0.45),
    backgroundColor: hexToRgba(color, active ? 0.2 : 0.12),
    boxShadow: active ? `0 0 0 3px ${hexToRgba(color, 0.16)}` : "none"
  };
}
