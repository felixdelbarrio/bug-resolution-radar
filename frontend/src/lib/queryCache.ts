import type { QueryClient } from "@tanstack/react-query";

export function invalidateDashboardQueries(queryClient: QueryClient) {
  return queryClient.invalidateQueries({
    predicate: ({ queryKey }) =>
      queryKey[0] === "bootstrap-shell" ||
      (typeof queryKey[0] === "string" && queryKey[0].startsWith("dashboard-"))
  });
}
