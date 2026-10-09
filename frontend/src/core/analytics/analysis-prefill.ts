const MAX_ANALYSIS_PREFILL_LENGTH = 512;

export function newAnalysisPrefillHref(prompt: string): string {
  const value = prompt.trim().slice(0, MAX_ANALYSIS_PREFILL_LENGTH);
  const query = new URLSearchParams({ prompt: value });
  return `/workspace/analysis/new?${query.toString()}`;
}

export function readAnalysisPrefill(
  searchParams: Pick<URLSearchParams, "get">,
  isNewAnalysis: boolean,
): string | undefined {
  if (!isNewAnalysis) {
    return undefined;
  }
  const value = searchParams.get("prompt");
  if (!value || value.length > MAX_ANALYSIS_PREFILL_LENGTH) {
    return undefined;
  }
  const prompt = value.trim();
  if (!prompt || prompt.length > MAX_ANALYSIS_PREFILL_LENGTH) {
    return undefined;
  }
  return prompt;
}
