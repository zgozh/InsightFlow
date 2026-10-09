"use client";

import { useId, useRef, useState, type FormEvent } from "react";

import {
  AnalyticsInlineAlert,
  isAnalyticsForbidden,
} from "@/components/analytics/analytics-catalog-views";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  useAdminMetricGrants,
  useGrantMetric,
  useRevokeMetric,
} from "@/core/analytics/hooks";
import { metricPrincipalIdSchema } from "@/core/analytics/schemas";
import { useI18n } from "@/core/i18n/hooks";

export function MetricGrantPanel({
  metricKey,
  metricName,
  onClose,
}: {
  metricKey: string;
  metricName: string;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const m = t.analytics.metric;
  const g = m.grants;
  const grants = useAdminMetricGrants(metricKey, true);
  const grant = useGrantMetric();
  const revoke = useRevokeMetric();
  const principalFieldId = useId();
  const principalHintId = useId();
  const submissionLock = useRef(false);
  const [principalInput, setPrincipalInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<"granted" | "revoked" | null>(null);
  const [operationError, setOperationError] = useState<
    "forbidden" | "failed" | null
  >(null);

  const principalResult = metricPrincipalIdSchema.safeParse(principalInput);
  const startSubmission = () => {
    if (submissionLock.current) return false;
    submissionLock.current = true;
    setSubmitting(true);
    setFeedback(null);
    setOperationError(null);
    grant.reset();
    revoke.reset();
    return true;
  };
  const finishSubmission = () => {
    submissionLock.current = false;
    setSubmitting(false);
  };
  const recordOperationError = (error: unknown) => {
    setOperationError(isAnalyticsForbidden(error) ? "forbidden" : "failed");
  };

  const submitGrant = (event: FormEvent) => {
    event.preventDefault();
    if (!principalResult.success || !startSubmission()) return;
    const principalId = principalResult.data;
    grant.mutate(
      { metricKey, principalId },
      {
        onSuccess: () => {
          setPrincipalInput("");
          setFeedback("granted");
        },
        onError: recordOperationError,
        onSettled: finishSubmission,
      },
    );
  };

  const revokePrincipal = (principalId: string) => {
    if (!startSubmission()) return;
    revoke.mutate(
      { metricKey, principalId },
      {
        onSuccess: () => setFeedback("revoked"),
        onError: recordOperationError,
        onSettled: finishSubmission,
      },
    );
  };

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !submissionLock.current) onClose();
      }}
    >
      <DialogContent
        showCloseButton={false}
        className="max-h-[calc(100vh-2rem)] gap-4 overflow-y-auto sm:max-w-xl"
        data-testid="metric-grant-panel"
      >
        <DialogHeader>
          <DialogTitle>{g.title}</DialogTitle>
          <DialogDescription>{g.description}</DialogDescription>
        </DialogHeader>

        <div className="border-border flex min-w-0 flex-col gap-1 rounded-md border p-3 text-sm">
          <span className="font-medium">{metricName}</span>
          <code className="text-muted-foreground break-all">{metricKey}</code>
        </div>

        <form
          className="flex min-w-0 flex-col gap-3"
          data-testid="metric-grant-form"
          onSubmit={submitGrant}
          noValidate
        >
          <div className="flex min-w-0 flex-col gap-1.5">
            <label htmlFor={principalFieldId} className="text-sm font-medium">
              {g.principalId}
            </label>
            <Input
              id={principalFieldId}
              value={principalInput}
              maxLength={64}
              autoComplete="off"
              aria-describedby={principalHintId}
              className="min-h-11"
              onChange={(event) => {
                setPrincipalInput(event.target.value);
                setOperationError(null);
                setFeedback(null);
              }}
            />
            <p id={principalHintId} className="text-muted-foreground text-xs">
              {g.principalHint}
            </p>
          </div>
          {principalInput.length > 0 && !principalResult.success && (
            <AnalyticsInlineAlert>{g.invalidPrincipal}</AnalyticsInlineAlert>
          )}
          <Button
            type="submit"
            className="min-h-11 min-w-11 self-start"
            disabled={
              submitting ||
              !principalResult.success ||
              principalInput.length === 0
            }
          >
            {submitting && grant.isPending ? g.submitting : g.submit}
          </Button>
        </form>

        <section
          aria-label={g.listTitle}
          className="flex min-w-0 flex-col gap-2"
        >
          <h3 className="text-sm font-semibold">{g.listTitle}</h3>
          {grants.isLoading && (
            <p role="status" className="text-muted-foreground text-sm">
              {t.analytics.common.loading}
            </p>
          )}
          {grants.isError && (
            <div className="flex flex-wrap items-center gap-2">
              <AnalyticsInlineAlert>
                {isAnalyticsForbidden(grants.error)
                  ? t.analytics.common.forbidden
                  : t.analytics.common.loadFailed}
              </AnalyticsInlineAlert>
              <Button
                type="button"
                variant="outline"
                className="min-h-11 min-w-11"
                disabled={grants.isFetching}
                onClick={() => void grants.refetch()}
              >
                {t.analytics.common.retry}
              </Button>
            </div>
          )}
          {!grants.isLoading &&
            !grants.isError &&
            grants.principalIds.length === 0 && (
              <p role="status" className="text-muted-foreground text-sm">
                {g.empty}
              </p>
            )}
          {!grants.isLoading &&
            !grants.isError &&
            grants.principalIds.length > 0 && (
              <ul className="flex min-w-0 flex-col gap-2">
                {grants.principalIds.map((principalId) => (
                  <li
                    key={principalId}
                    className="border-border flex min-w-0 flex-wrap items-center justify-between gap-2 rounded-md border p-2"
                  >
                    <code className="min-w-0 text-sm break-all">
                      {principalId}
                    </code>
                    <Button
                      type="button"
                      variant="outline"
                      className="min-h-11 min-w-11"
                      aria-label={g.revoke + " " + principalId}
                      disabled={submitting}
                      onClick={() => revokePrincipal(principalId)}
                    >
                      {submitting && revoke.isPending ? g.revoking : g.revoke}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
        </section>

        {operationError !== null && (
          <AnalyticsInlineAlert>
            {operationError === "forbidden"
              ? t.analytics.common.forbidden
              : g.operationFailed}
          </AnalyticsInlineAlert>
        )}
        {feedback !== null && (
          <p
            role="status"
            className="text-sm text-emerald-700 dark:text-emerald-400"
          >
            {feedback === "granted" ? g.granted : g.revoked}
          </p>
        )}

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            className="min-h-11 min-w-11"
            disabled={submitting}
            onClick={onClose}
          >
            {t.analytics.common.close}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
