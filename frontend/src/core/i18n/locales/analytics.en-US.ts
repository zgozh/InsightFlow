import type { AnalyticsTranslations, BrandingTranslations } from "./analytics";

/**
 * English copy for the InsightFlow brand and analytics workspace. This is an
 * independent equivalent of the Chinese baseline, not a literal translation:
 * the Chinese file is the design reference, this one carries the same intent
 * in idiomatic product English.
 */
export const analyticsEnUS: {
  branding: BrandingTranslations;
  analytics: AnalyticsTranslations;
} = {
  branding: {
    productName: "InsightFlow",
    tagline: "A governed workspace for enterprise analytics",
    landingHeadline: "Every number should be traceable to its evidence",
    landingDescription:
      "InsightFlow puts natural-language analysis on top of controlled SQL and semantic authorization. The model can only submit queries that pass policy validation, every execution leaves an audit record you can review, and each answer carries an evidence identifier. Trustworthy analysis, governed definitions, accountable results.",
    landingEnter: "Enter the workspace",
    landingSecurityTitle: "Governance before automation",
    landingSecurityBody:
      "Datasource credentials are registered as secret references and never reach the browser. Queries are parsed, rewritten, and validated row by row in the controlled SQL layer; functions, joins, and sensitive columns outside the grant are rejected outright. The policy version, schema version, and result digest are written into the audit record, so any extraction can be traced back to the authorization state in force at the time.",
    landingWorkflowTitle: "From question to reviewable answer",
    landingWorkflowBody:
      "You ask a question; the system plans its retrieval path, inspects the data catalog, then submits a governed query. Intermediate results can be delegated to parallel subtasks, and artifacts and reports bind an evidence identifier when they are published. The whole run is recorded as structured events — the model's thought process is neither shown nor required.",
    aboutTitle: "About InsightFlow",
    aboutSlogan: "Originated from Open Source, give back to Open Source.",
    aboutDerivation:
      "InsightFlow is a deep refactor derived from DeerFlow v2.1.0-rc0. It keeps the upstream MIT licence and copyright attribution and rebuilds the product around governed enterprise analytics. The upstream project is maintained by ByteDance and the DeerFlow community.",
    aboutLicense:
      "This project is distributed under the MIT License. Original copyright remains with the DeerFlow upstream authors; the full licence text ships in the LICENSE file at the repository root.",
  },

  analytics: {
    nav: {
      newAnalysis: "New analysis",
      analysis: "Analysis",
      datasources: "Data sources",
      metrics: "Metrics",
      reports: "Reports",
      history: "Audit history",
      scheduledTasks: "Scheduled tasks",
      settings: "Settings",
      more: "More",
      compatibility: "Compatibility",
    },
    common: {
      loading: "Loading…",
      loadFailed: "Could not load",
      empty: "Nothing here yet",
      retry: "Retry",
      refresh: "Refresh",
      cancel: "Cancel",
      save: "Save",
      saving: "Saving…",
      create: "Create",
      edit: "Edit",
      close: "Close",
      copy: "Copy",
      copied: "Copied",
      notAvailable: "Not available",
      adminOnly: "Administrator permission required",
      readOnly: "Read-only: your account cannot make changes",
      forbidden: "The server refused this action (403)",
      unknownEvent: "Unrecognized event type",
      loadMore: "Load more",
      noMore: "No more results",
    },
    datasource: {
      title: "Data sources",
      description:
        "Review the data sources available for governed analysis. Administrators register sources, schemas, and access policies; real credentials are resolved only on the server.",
      empty:
        "No data sources are currently available to your account. Ask an administrator to register a source and grant access.",
      adminEmpty:
        "No data sources are registered yet. Create a source, then configure its schema and access policy.",
      name: "Name",
      engine: "Engine",
      status: "Status",
      defaultSchema: "Default schema",
      secretRef: "Secret reference",
      secretRefHint:
        "Use the reference name from the server-side secret store. Never paste a plaintext password here.",
      createTitle: "New data source",
      editTitle: "Edit data source",
      engineImmutable:
        "The engine cannot be changed after creation. Create a new data source instead.",
      statusActive: "Active",
      statusDisabled: "Disabled",
      statusUnhealthy: "Connection failing",
    },
    schema: {
      title: "Data model",
      description:
        "Describe the tables, columns, and relations available for analysis. Saving produces a new schema version.",
      version: "Version",
      defaultSchema: "Default schema",
      relations: "Relations",
      relationName: "Relation name",
      columnName: "Column",
      columnType: "Type",
      columnSensitivity: "Sensitivity",
      addRelation: "Add relation",
      addColumn: "Add column",
      removeRelation: "Remove relation",
      removeColumn: "Remove column",
      saved: "Saved",
      staleTitle: "This schema has changed",
      staleBody:
        "A newer version was written on the server after you opened this model. Saving now would overwrite someone else's change — refresh and edit again.",
      relationSchema: "Schema",
      importLabel: "Controlled JSON import",
      importInvalidJson:
        "That is not a valid data-model document: it must be an object whose only key is a relations array, and every entry needs a name, a schema and columns. Fix it and try again.",
    },
    policy: {
      title: "Access policy",
      description:
        "Declare the relations and functions a principal may use. Anything not listed here stays invisible to that principal.",
      principalId: "Principal ID",
      relations: "Visible relations",
      allowedFunctions: "Allowed functions",
      accessAllowed: "Access allowed",
      accessDenied: "Access denied",
      saveHint:
        "A saved policy takes effect immediately; the next query is validated against it.",
      remove: "Remove policy",
      removed: "Policy removed",
      confirmRemoveTitle: "Remove this policy?",
      confirmRemoveBody:
        "The principal falls back to deny-by-default, and every query without an explicit grant will be blocked.",
    },
    metric: {
      title: "Metrics",
      description:
        "Review metric definitions used in analysis. Administrators create and activate metrics so reports use consistent definitions.",
      empty:
        "No active metrics are available to your account. Ask an administrator to define and activate one.",
      adminEmpty:
        "No metrics are defined yet. Create a metric and activate it before analyses can use it.",
      key: "Metric key",
      name: "Metric name",
      expression: "Expression",
      expressionHint:
        "Write the expression with granted columns and functions. Saving validates it once.",
      dimensions: "Available dimensions",
      version: "Version",
      status: "Status",
      statusDraft: "Draft",
      statusActive: "Active",
      statusRetired: "Retired",
      createTitle: "New metric",
      editTitle: "Edit metric",
      retire: "Retire metric",
      confirmRetireTitle: "Retire this metric?",
      confirmRetireBody:
        "New analyses can no longer reference it. Definitions already pinned in published reports are unaffected.",
      versionMustAdvance:
        "Editing an active metric requires advancing its version.",
    },
    history: {
      title: "Audit history",
      description:
        "An execution record for every governed query. Administrators see the full row; other roles see only their own entries.",
      empty:
        "No audit entries yet. A record appears after a governed query runs.",
      phase: "Phase",
      status: "Status",
      code: "Code",
      risk: "Risk",
      rows: "Rows",
      bytes: "Bytes",
      cost: "Cost",
      latency: "Latency",
      startedAt: "Started",
      finishedAt: "Finished",
      queryHash: "Query hash",
      planDigest: "Plan digest",
      principalId: "Principal ID",
      adminHint: "Only administrators can view the complete audit fields.",
    },
    report: {
      title: "Reports",
      description:
        "A published report pins the evidence identifiers and data definitions in force at publication.",
      artifactPath: "Artifact path",
      evidence: "Evidence",
      status: "Status",
      statusPublished: "Published",
      createdAt: "Created",
      openAnalysis: "Open the analysis",
      downloadReport: "Download report",
      empty:
        "No reports published yet. Reports appear here after an analysis writes and publishes one.",
    },
    trace: {
      title: "Tool event trace",
      toggle: "Expand or collapse the tool event trace",
      empty: "This run has no events to show yet.",
      unparsed: "Unparsed safe event; raw content is hidden",
      evidenceId: "Evidence ID",
      copyEvidence: "Copy evidence ID",
      risk: "Risk",
      rows: "Rows",
      bytes: "Bytes",
      estimatedRows: "Estimated rows",
      engineCost: "Engine cost",
      truncated: "Result truncated",
      truncatedYes: "Truncated",
      truncatedNo: "Complete",
      schemaVersion: "Schema version",
      policyVersion: "Policy version",
      resultDigest: "Result digest",
      stepPlan: "Retrieval plan",
      stepCatalog: "Catalog discovery",
      stepQuery: "Governed query",
      stepDelegate: "Subtask delegation",
      stepArtifact: "Artifact write",
      stepPublish: "Report publication",
      reviewer: "Reviewer",
      reviewerApproved: "Approved",
      reviewerRejected: "Rejected",
      reviewerFailed: "Could not complete",
      reviewerLimited: "Limited",
      reviewReasonUnsupportedClaim: "Unsupported claim",
      reviewReasonEvidenceMismatch: "Evidence mismatch",
      reviewReasonMissingCitation: "Missing evidence citation",
      reviewReasonInsufficientEvidence: "Insufficient evidence",
      statusRunning: "Running",
      statusCompleted: "Completed",
      statusFailed: "Failed",
      statusRejected: "Rejected",
    },
    analysis: {
      newTitle: "New analysis",
      newDescription:
        "Ask a question in plain language; the system plans a retrieval path and submits governed queries.",
      threadTitle: "Analysis",
      compatibilityNotice:
        "This conversation runs on the general chat runtime and has no governed SQL or audit trail.",
    },
    errors: {
      unavailable:
        "The analytics control plane is not mounted or is disabled. Ask an administrator to check the deployment configuration.",
      invalidRequest:
        "Request rejected: the parameters do not match the API contract.",
      notFound: "That resource no longer exists.",
      versionConflict:
        "This record was changed by someone else and your version is stale. Refresh and try again.",
      storageUnavailable:
        "Storage is temporarily unavailable, so your change was not saved.",
    },
  },
};
