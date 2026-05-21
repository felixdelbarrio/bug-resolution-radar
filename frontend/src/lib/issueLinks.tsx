import type { ReactNode } from "react";

const JIRA_KEY_PATTERN = /^[A-Z][A-Z0-9]+-\d+(?:[A-Z0-9-]*)?$/i;
const HELIX_ID_PATTERN = /^INC\d{8,}$/i;
const ISSUE_REFERENCE_PATTERN = /\b(INC\d{8,}|[A-Z][A-Z0-9]+-\d+(?:[A-Z0-9-]*)?)\b/gi;
const DEFAULT_JIRA_BROWSE_ROOT = "https://jira.globaldevtools.bbva.com/browse";
const DEFAULT_HELIX_DASHBOARD_URL =
  "https://itsmhelixbbva-smartit.onbmc.com/smartit/app/#/ticket-console";

function normalizeJiraKey(value: string): string {
  const key = value.trim().toUpperCase();
  return JIRA_KEY_PATTERN.test(key) ? key : "";
}

function normalizeHelixId(value: string): string {
  const id = value.trim().toUpperCase();
  return HELIX_ID_PATTERN.test(id) ? id : "";
}

function normalizeHttpUrl(value?: string): string {
  const raw = (value ?? "").trim();
  if (!raw) return "";
  try {
    const parsed = new URL(raw);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? raw : "";
  } catch {
    return "";
  }
}

export function buildJiraIssueUrl(jiraKey: string, existingUrl = ""): string {
  const key = normalizeJiraKey(jiraKey);
  if (!key) return "";
  return normalizeHttpUrl(existingUrl) || `${DEFAULT_JIRA_BROWSE_ROOT}/${encodeURIComponent(key)}`;
}

export function buildHelixIssueUrl(helixId: string, existingUrl = ""): string {
  const id = normalizeHelixId(helixId);
  if (!id) return "";
  return normalizeHttpUrl(existingUrl) || DEFAULT_HELIX_DASHBOARD_URL;
}

export function isValidIssueReference(value: string): boolean {
  return Boolean(normalizeJiraKey(value) || normalizeHelixId(value));
}

type LinkifyOptions = {
  jiraUrls?: Record<string, string>;
  helixUrls?: Record<string, string>;
  className?: string;
};

export function linkifyIssueReferences(text: string, options: LinkifyOptions = {}): ReactNode[] {
  const raw = text || "";
  if (!raw) return [];

  const nodes: ReactNode[] = [];
  let cursor = 0;
  raw.replace(ISSUE_REFERENCE_PATTERN, (match, _token, offset: number) => {
    if (offset > cursor) {
      nodes.push(raw.slice(cursor, offset));
    }
    const helixId = normalizeHelixId(match);
    const jiraKey = helixId ? "" : normalizeJiraKey(match);
    const url = helixId
      ? buildHelixIssueUrl(helixId, options.helixUrls?.[helixId] ?? "")
      : buildJiraIssueUrl(jiraKey, options.jiraUrls?.[jiraKey] ?? "");
    nodes.push(
      url ? (
        <a
          className={options.className}
          href={url}
          key={`${match}-${offset}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          {helixId || jiraKey}
        </a>
      ) : (
        match
      )
    );
    cursor = offset + match.length;
    return match;
  });
  if (cursor < raw.length) {
    nodes.push(raw.slice(cursor));
  }
  return nodes;
}
