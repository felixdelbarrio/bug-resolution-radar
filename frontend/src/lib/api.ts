export type WorkspaceSource = {
  source_id: string;
  source_type: string;
  country: string;
  alias: string;
  jql?: string;
  service_origin_buug?: string;
  service_origin_n1?: string;
  service_origin_n2?: string;
};

export type WorkspaceData = {
  countries: Array<{ country: string; sourceCount: number }>;
  sources: WorkspaceSource[];
  selectedCountry: string;
  selectedSourceId: string;
  scopeMode: string;
  hasCountryRollup: boolean;
  countryRollupSourceIds: string[];
  hasData: boolean;
  filterOptions: {
    status: string[];
    priority: string[];
    assignee: string[];
    quincenal: string[];
  };
};

export type BootstrapPayload = {
  appTitle: string;
  theme: string;
  defaultFilters: {
    status: string[];
    priority: string[];
    assignee: string[];
  };
  dashboardDefaults: {
    summaryChartIds: string[];
    defaultTrendChartId: string;
  };
  workspace: WorkspaceData;
  chartsCatalog: Array<{ id: string; label: string }>;
  permissionsPolicy: Record<string, string>;
};

export type DashboardPayload = {
  stats: Record<string, string | number>;
  overviewKpis: Array<{
    label: string;
    value: string;
    hint: string;
  }>;
  focusCards: Array<{
    cardId: string;
    title: string;
    metric: string;
    detail: string;
    panel: string;
    target: string;
    kicker: string;
    tone: string;
  }>;
  statusPriorityMatrix: {
    title: string;
    total: number;
    priorities: Array<{ priority: string; count: number }>;
    rows: Array<{
      status: string;
      count: number;
      cells: Array<{ priority: string; count: number }>;
    }>;
    selected: {
      status: string[];
      priority: string[];
    };
  };
  open_priority_breakdown: Array<{ priority: string; count: number }>;
  top_open: Array<Record<string, unknown>>;
  charts: Array<{
    id: string;
    title: string;
    subtitle: string;
    group: string;
    figure: Record<string, unknown> | null;
    insights: string[];
  }>;
  row_count: number;
  open_row_count: number;
  workspace: WorkspaceData;
};

export type IssuesPayload = {
  total: number;
  rows: Array<Record<string, string>>;
};

export type IssueKeysPayload = {
  total: number;
  keys: string[];
};

export type IssueRecord = {
  key: string;
  summary: string;
  description: string;
  status: string;
  priority: string;
  assignee: string;
  created: string;
  updated: string;
  resolved: string;
  url: string;
  source_alias: string;
  source_type: string;
  ageDays: number;
};

export type KanbanItem = {
  key: string;
  summary: string;
  status: string;
  priority: string;
  assignee: string;
  updated: string;
  url: string;
  source_alias: string;
  source_type: string;
  ageDays: number;
};

export type KanbanPayload = Array<{
  status: string;
  count: number;
  items: KanbanItem[];
}>;

export type TrendDetailPayload = {
  chart: {
    id: string;
    title: string;
    subtitle: string;
    group: string;
    figure: Record<string, unknown> | null;
  } | null;
  metrics: Array<{ label: string; value: string }>;
  cards: Array<{
    title: string;
    body: string;
    score: number;
    statusFilters: string[];
    priorityFilters: string[];
    assigneeFilters: string[];
  }>;
  executiveTip: string | null;
  adaptedForTerminal: boolean;
};

export type IntelligencePayload = {
  tabs: Array<{ id: string; label: string }>;
  periodSummary: {
    caption: string;
    cards: Array<{
      cardId: string;
      kicker: string;
      metric: string;
      detail: string;
      label: string;
      quincenalScopeLabel: string;
      issueKeys: string[];
    }>;
    groups: Array<{
      label: string;
      count: number;
      helpText: string;
      quincenalScopeLabel: string;
      issueKeys: string[];
      items: IssueRecord[];
    }>;
    showOpenSplit: boolean;
    sourceBreakdown: Array<{
      source: string;
      abiertas: number;
      focus: { label: string; value: number };
      other: { label: string; value: number };
      nuevasAhora: number;
      cerradasAhora: number;
      resolucionAhora: string;
    }>;
  };
  functionality: {
    combo: {
      viewMode: string;
      viewModeOptions: Array<{ value: string; label: string }>;
      statusOptions: string[];
      priorityOptions: string[];
      functionalityOptions: string[];
      selectedStatuses: string[];
      selectedPriorities: string[];
      selectedFunctionalities: string[];
    };
    chart: {
      title: string;
      subtitle: string;
      figure: Record<string, unknown> | null;
    } | null;
    topics: Array<{
      topic: string;
      count: number;
      pct: number;
      dominantStatus: string;
      dominantPriority: string;
      brief: string;
      flow: {
        createdCount: number;
        resolvedCount: number;
        pctDelta: number;
        direction: string;
        windowDays: number;
      } | null;
      rootCauses: Array<{ label: string; count: number }>;
      issues: IssueRecord[];
    }>;
    tip: string;
  };
  duplicates: {
    brief: string;
    titleGroups: Array<{
      summary: string;
      count: number;
      issues: IssueRecord[];
    }>;
    heuristicGroups: Array<{
      summary: string;
      count: number;
      dominantStatus: string;
      dominantPriority: string;
      issues: IssueRecord[];
    }>;
  };
  people: {
    cards: Array<{
      assignee: string;
      openCount: number;
      sharePct: number;
      statusBreakdown: Array<{ status: string; count: number }>;
      risk: {
        label: string;
        flowRiskPct: number;
        criticalRiskPct: number;
      };
      pushPct: number;
      blockedCount: number;
      aging: {
        value: string;
        caption: string;
      };
      recommendations: string[];
      oldestIssues: IssueRecord[];
    }>;
  };
  opsHealth: {
    kpis: Array<{ label: string; value: string; detail: string }>;
    brief: string[];
    oldestIssues: IssueRecord[];
  };
};

export type SettingsPayload = {
  values: Record<string, string | number>;
  supportedCountries: string[];
  jiraSources: WorkspaceSource[];
  helixSources: WorkspaceSource[];
  countryRollupSources: Record<string, string[]>;
  jiraDisabledSourceIds: string[];
  helixDisabledSourceIds: string[];
};

export function normalizeSettingsPayload(
  payload: Partial<SettingsPayload> | null | undefined
): SettingsPayload {
  return {
    values: payload?.values ?? {},
    supportedCountries: payload?.supportedCountries ?? [],
    jiraSources: payload?.jiraSources ?? [],
    helixSources: payload?.helixSources ?? [],
    countryRollupSources: payload?.countryRollupSources ?? {},
    jiraDisabledSourceIds: payload?.jiraDisabledSourceIds ?? [],
    helixDisabledSourceIds: payload?.helixDisabledSourceIds ?? []
  };
}

export type IngestLastRunPayload = {
  schema_version: string;
  ingested_at: string;
  jira_base_url?: string;
  helix_base_url?: string;
  query: string;
  jira_source_count?: number;
  helix_source_count?: number;
  issues_count?: number;
  items_count?: number;
  data_path?: string;
};

export type IngestConnectorOverview = {
  configuredCount: number;
  selectedSourceIds: string[];
  lastIngest: IngestLastRunPayload;
};

export type IngestOverviewPayload = {
  jira: IngestConnectorOverview;
  helix: IngestConnectorOverview;
};

export type CacheInventoryRow = {
  cache_id: string;
  label: string;
  records: number;
  path: string;
};

export type IngestResult = {
  state: string;
  summary: string;
  success_count: number;
  total_sources: number;
  messages: Array<{ ok: boolean; message: string }>;
};

export type SavedReportPayload = {
  fileName: string;
  savedPath: string;
  savedDir: string;
  slideCount: number;
  totalIssues: number;
  openIssues: number;
  closedIssues: number;
};

type QueryValue = string | number | boolean | null | undefined | string[];

function toQueryString(params: Record<string, QueryValue>) {
  const query = new URLSearchParams();
  for (const [key, raw] of Object.entries(params)) {
    if (raw === undefined || raw === null || raw === "") {
      continue;
    }
    if (Array.isArray(raw)) {
      if (raw.length === 0) continue;
      query.set(key, raw.join(","));
      continue;
    }
    query.set(key, String(raw));
  }
  const serialized = query.toString();
  return serialized ? `?${serialized}` : "";
}

async function parseError(response: Response): Promise<never> {
  let detail = `${response.status} ${response.statusText}`;
  const text = await response.text();
  if (text) {
    try {
      const payload = JSON.parse(text) as { detail?: string };
      if (payload.detail) {
        detail = payload.detail;
      } else {
        detail = text;
      }
    } catch {
      detail = text;
    }
  }
  throw new Error(detail);
}

export async function fetchJson<T>(
  path: string,
  params?: Record<string, QueryValue>
): Promise<T> {
  const response = await fetch(`${path}${toQueryString(params ?? {})}`, {
    credentials: "same-origin"
  });
  if (!response.ok) {
    await parseError(response);
  }
  return (await response.json()) as T;
}

export async function putJson<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json"
    },
    credentials: "same-origin",
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    await parseError(response);
  }
  return (await response.json()) as T;
}

export async function postJson<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    credentials: "same-origin",
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    await parseError(response);
  }
  return (await response.json()) as T;
}

export async function downloadFromApi(
  path: string,
  payload: unknown,
  suggestedName: string
) {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    credentials: "same-origin",
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    await parseError(response);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filenameMatch = disposition.match(/filename="([^"]+)"/);
  const filename = filenameMatch?.[1] ?? suggestedName;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export async function downloadGet(
  path: string,
  params: Record<string, QueryValue>,
  suggestedName: string
) {
  const response = await fetch(`${path}${toQueryString(params)}`, {
    credentials: "same-origin"
  });
  if (!response.ok) {
    await parseError(response);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filenameMatch = disposition.match(/filename="([^"]+)"/);
  const filename = filenameMatch?.[1] ?? suggestedName;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
