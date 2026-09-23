import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export interface FeaturesResponse {
  mcp_tasks?: { enabled: boolean };
  conversation_references?: {
    enabled?: boolean;
    max_references?: number;
  };
}

export interface ConversationReferencesCapability {
  enabled: boolean;
  maxReferences: number;
}

export async function fetchFeatures(): Promise<FeaturesResponse> {
  const res = await fetch(`${getBackendBaseURL()}/api/features`);
  if (!res.ok) {
    throw new Error(`Failed to load features: ${res.statusText}`);
  }
  return (await res.json()) as FeaturesResponse;
}

export async function fetchMcpTasksEnabled(): Promise<boolean> {
  return (await fetchFeatures()).mcp_tasks?.enabled ?? false;
}

export async function fetchConversationReferencesCapability(): Promise<ConversationReferencesCapability> {
  const features = await fetchFeatures();
  const capability = features.conversation_references;
  const maxReferences = capability?.max_references;
  return {
    enabled: capability?.enabled === true,
    maxReferences:
      typeof maxReferences === "number" &&
      Number.isInteger(maxReferences) &&
      maxReferences > 0
        ? maxReferences
        : 0,
  };
}
