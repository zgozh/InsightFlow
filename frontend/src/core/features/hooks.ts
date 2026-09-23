import { useQuery } from "@tanstack/react-query";

import {
  fetchConversationReferencesCapability,
  fetchMcpTasksEnabled,
} from "./api";

export function useMcpTasksEnabled() {
  const { data, isPending } = useQuery({
    queryKey: ["features", "mcp_tasks"],
    queryFn: () => fetchMcpTasksEnabled(),
    staleTime: 0,
    refetchOnMount: true,
    retry: false,
  });

  return {
    enabled: data ?? false,
    isLoading: isPending,
  };
}

export function useConversationReferencesCapability() {
  const { data, isPending } = useQuery({
    queryKey: ["features", "conversation_references"],
    queryFn: () => fetchConversationReferencesCapability(),
    staleTime: 0,
    refetchOnMount: true,
    retry: false,
  });
  return {
    enabled: data?.enabled ?? false,
    maxReferences: data?.maxReferences ?? 0,
    isLoading: isPending,
  };
}
