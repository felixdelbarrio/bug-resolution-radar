import type { CSSProperties } from "react";

const BBVA_SIGNAL_RED_1 = "#B4232A";
const BBVA_SIGNAL_RED_2 = "#D64550";
const BBVA_SIGNAL_RED_3 = "#E85D63";
const BBVA_SIGNAL_ORANGE_2 = "#F59E0B";
const BBVA_SIGNAL_YELLOW_1 = "#FBBF24";
const BBVA_SIGNAL_GREEN_1 = "#15803D";
const BBVA_SIGNAL_GREEN_2 = "#22A447";
const BBVA_SIGNAL_GREEN_3 = "#4CAF50";
const BBVA_GOAL_ACCENT_7 = "#5B3FD0";
const BBVA_GOAL_SURFACE_8 = "#ECE6FF";
const BBVA_NEUTRAL_SOFT = "#E2E6EE";

function normalizeSemanticToken(value: string) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\s+/g, " ");
}

const STATUS_COLOR_BY_KEY: Record<string, string> = {
  new: BBVA_SIGNAL_RED_3,
  ready: BBVA_SIGNAL_RED_3,
  analysing: BBVA_SIGNAL_RED_3,
  blocked: BBVA_SIGNAL_RED_3,
  "en progreso": BBVA_SIGNAL_ORANGE_2,
  "in progress": BBVA_SIGNAL_ORANGE_2,
  "to rework": BBVA_SIGNAL_ORANGE_2,
  rework: BBVA_SIGNAL_ORANGE_2,
  test: BBVA_SIGNAL_ORANGE_2,
  "ready to verify": BBVA_SIGNAL_ORANGE_2,
  accepted: BBVA_SIGNAL_GREEN_3,
  "ready to deploy": BBVA_SIGNAL_GREEN_3,
  deployed: BBVA_GOAL_ACCENT_7,
  closed: BBVA_SIGNAL_GREEN_1,
  resolved: BBVA_SIGNAL_GREEN_1,
  done: BBVA_SIGNAL_GREEN_1,
  open: BBVA_SIGNAL_YELLOW_1,
  created: BBVA_SIGNAL_RED_3
};

const PRIORITY_COLOR_BY_KEY: Record<string, string> = {
  "supone un impedimento": BBVA_SIGNAL_RED_1,
  highest: BBVA_SIGNAL_RED_1,
  high: BBVA_SIGNAL_RED_2,
  medium: BBVA_SIGNAL_ORANGE_2,
  low: BBVA_SIGNAL_GREEN_2,
  lowest: BBVA_SIGNAL_GREEN_1
};

function hexToRgba(hexColor: string, alpha: number) {
  const token = String(hexColor || "")
    .trim()
    .replace(/^#/, "");
  if (!/^[0-9a-fA-F]{6}$/.test(token)) {
    return `rgba(226,230,238,${alpha})`;
  }
  const r = Number.parseInt(token.slice(0, 2), 16);
  const g = Number.parseInt(token.slice(2, 4), 16);
  const b = Number.parseInt(token.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function chipPalette(color: string) {
  const normalized = String(color || "").trim().toUpperCase();
  if (normalized === BBVA_GOAL_ACCENT_7) {
    return {
      color: BBVA_GOAL_ACCENT_7,
      borderColor: hexToRgba(BBVA_GOAL_ACCENT_7, 0.64),
      backgroundColor: BBVA_GOAL_SURFACE_8
    };
  }
  return {
    color,
    borderColor: hexToRgba(color, 0.62),
    backgroundColor: hexToRgba(color, 0.16)
  };
}

export function statusColor(status: string) {
  return STATUS_COLOR_BY_KEY[normalizeSemanticToken(status)] ?? BBVA_NEUTRAL_SOFT;
}

export function priorityColor(priority: string) {
  return PRIORITY_COLOR_BY_KEY[normalizeSemanticToken(priority)] ?? BBVA_NEUTRAL_SOFT;
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
