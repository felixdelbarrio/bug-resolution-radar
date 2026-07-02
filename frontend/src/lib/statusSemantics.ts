export type IssueStateBucket = "open" | "closed";

type IssueStateInput = {
  status?: string | null;
  source_type?: string | null;
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

export function issueStateBucket(issue: IssueStateInput): IssueStateBucket {
  const sourceType = normalizeStatusToken(issue?.source_type);
  if (sourceType === "jira" && isFinalistStatus(issue?.status)) {
    return "closed";
  }
  return "open";
}

export function issueStateLabel(bucket: IssueStateBucket) {
  return bucket === "closed" ? "Cerrada" : "Abierta";
}
