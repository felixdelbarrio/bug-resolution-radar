import { startTransition, useDeferredValue } from "react";
import { useSearchParams } from "react-router-dom";

type DashboardParams = {
  panel: string;
  country: string;
  sourceId: string;
  scopeMode: string;
  status: string[];
  priority: string[];
  assignee: string[];
  quincenalScope: string;
  issueLikeQuery: string;
  issueSortCol: string;
  issueSortDir: string;
  issuesView: string;
  issuePage: string;
  trendChart: string;
  notesIssueKey: string;
  insightsTab: string;
  insightsViewMode: string;
  insightsStatus: string[];
  insightsPriority: string[];
  insightsFunctionality: string[];
  insightsStatusManual: string;
  settingsTab: string;
};

function splitValue(raw: string | null) {
  return (raw ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function useDashboardParams(defaultPanel = "overview") {
  const [searchParams, setSearchParams] = useSearchParams();

  const params: DashboardParams = {
    panel: searchParams.get("panel") ?? defaultPanel,
    country: searchParams.get("country") ?? "",
    sourceId: searchParams.get("sourceId") ?? "",
    scopeMode: searchParams.get("scopeMode") ?? "source",
    status: splitValue(searchParams.get("status")),
    priority: splitValue(searchParams.get("priority")),
    assignee: splitValue(searchParams.get("assignee")),
    quincenalScope: searchParams.get("quincenalScope") ?? "Todas",
    issueLikeQuery: searchParams.get("issueLikeQuery") ?? "",
    issueSortCol: searchParams.get("issueSortCol") ?? "updated",
    issueSortDir: searchParams.get("issueSortDir") ?? "desc",
    issuesView: searchParams.get("issuesView") ?? "Cards",
    issuePage: searchParams.get("issuePage") ?? "1",
    trendChart: searchParams.get("trendChart") ?? "",
    notesIssueKey: searchParams.get("notesIssueKey") ?? "",
    insightsTab: searchParams.get("insightsTab") ?? "summary",
    insightsViewMode: searchParams.get("insightsViewMode") ?? "quincenal",
    insightsStatus: splitValue(searchParams.get("insightsStatus")),
    insightsPriority: splitValue(searchParams.get("insightsPriority")),
    insightsFunctionality: splitValue(searchParams.get("insightsFunctionality")),
    insightsStatusManual: searchParams.get("insightsStatusManual") ?? "",
    settingsTab: searchParams.get("settingsTab") ?? "preferences"
  };

  const deferredIssueLikeQuery = useDeferredValue(params.issueLikeQuery);

  function buildNextSearch(values: Partial<DashboardParams>) {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(values)) {
      if (Array.isArray(value)) {
        if (value.length === 0) next.delete(key);
        else next.set(key, value.join(","));
        continue;
      }
      if (!value) next.delete(key);
      else next.set(key, String(value));
    }
    return next;
  }

  function update(values: Partial<DashboardParams>) {
    startTransition(() => {
      setSearchParams(buildNextSearch(values), { replace: true });
    });
  }

  return {
    params,
    deferredIssueLikeQuery,
    update,
    buildNextSearch
  };
}
