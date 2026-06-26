export type IssueLifecycleBucket = "active" | "finalist";

type IssueLifecycleInput = {
  status?: string | null;
  resolved?: string | null;
} | null | undefined;

const FINALIST_STATUS_TOKENS = [
  "accepted",
  "acepted",
  "ready to deploy",
  "deployed",
  "closed",
  "resolved",
  "done",
  "cancelled",
  "canceled"
] as const;

export function normalizeStatusToken(value: unknown) {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\s+/g, " ");
}

export function isFinalistStatus(value: unknown) {
  const token = normalizeStatusToken(value);
  if (!token) {
    return false;
  }
  return FINALIST_STATUS_TOKENS.some((finalistToken) => token.includes(finalistToken));
}

function hasResolvedTimestamp(value: unknown) {
  const token = normalizeStatusToken(value);
  return Boolean(token && token !== "nat" && token !== "none" && token !== "null");
}

export function issueLifecycleBucket(issue: IssueLifecycleInput): IssueLifecycleBucket {
  if (hasResolvedTimestamp(issue?.resolved) || isFinalistStatus(issue?.status)) {
    return "finalist";
  }
  return "active";
}

export function issueLifecycleLabel(bucket: IssueLifecycleBucket) {
  return bucket === "finalist" ? "Finalizada" : "En seguimiento";
}
