/**
 * InsightFlow 产品工作台的 i18n 契约（Phase 4）。
 *
 * 为什么单独放一个文件而不是继续往 `types.ts` 里堆：
 *
 * 1. Phase 4 一次新增上百条词条，全部塞进既有文件会让审阅 diff 无法阅读；
 * 2. 新页面（数据源／指标／报告／历史／分析轨迹）与品牌文案属于同一个交付单元，
 *    合并成一个可被静态检查的接口，避免两套语言各写各的；
 * 3. 明文文案分别放在 `analytics.zh-CN.ts` / `analytics.en-US.ts`，通过展开合入
 *    既有的 `zhCN` / `enUS` 字典，`Translations` 仍然是唯一的类型来源。
 *
 * 中文是设计基准（见仓库级 AGENTS.md）；英文是等价的对照实现，不是逐字直译。
 */
export interface BrandingTranslations {
  /** 产品名。出现在页面 title、Landing、workspace header 与 about。 */
  productName: string;
  tagline: string;
  landingHeadline: string;
  landingDescription: string;
  landingEnter: string;
  landingSecurityTitle: string;
  landingSecurityBody: string;
  landingWorkflowTitle: string;
  landingWorkflowBody: string;
  aboutTitle: string;
  /** 上游派生说明。必须保留，不得删除。 */
  aboutDerivation: string;
  aboutLicense: string;
}

export interface AnalyticsTranslations {
  nav: {
    newAnalysis: string;
    analysis: string;
    datasources: string;
    metrics: string;
    reports: string;
    history: string;
    scheduledTasks: string;
    settings: string;
    more: string;
    compatibility: string;
  };
  common: {
    loading: string;
    loadFailed: string;
    empty: string;
    retry: string;
    refresh: string;
    cancel: string;
    save: string;
    saving: string;
    create: string;
    edit: string;
    close: string;
    copy: string;
    copied: string;
    notAvailable: string;
    adminOnly: string;
    readOnly: string;
    forbidden: string;
    unknownEvent: string;
    loadMore: string;
    noMore: string;
  };
  datasource: {
    title: string;
    description: string;
    name: string;
    engine: string;
    status: string;
    defaultSchema: string;
    secretRef: string;
    secretRefHint: string;
    createTitle: string;
    editTitle: string;
    engineImmutable: string;
    statusActive: string;
    statusDisabled: string;
    statusUnhealthy: string;
  };
  schema: {
    title: string;
    description: string;
    version: string;
    defaultSchema: string;
    relations: string;
    relationName: string;
    columnName: string;
    columnType: string;
    columnSensitivity: string;
    addRelation: string;
    addColumn: string;
    removeRelation: string;
    removeColumn: string;
    saved: string;
    staleTitle: string;
    staleBody: string;
    /** 关联自身的 schema 字段标签（与页面级的 defaultSchema 说明不同）。 */
    relationSchema: string;
    /** 受控 JSON 导入区的无障碍名。 */
    importLabel: string;
    /** 导入内容不是合法结构时的内联错误。 */
    importInvalidJson: string;
  };
  policy: {
    title: string;
    description: string;
    principalId: string;
    relations: string;
    allowedFunctions: string;
    accessAllowed: string;
    accessDenied: string;
    saveHint: string;
    remove: string;
    removed: string;
    confirmRemoveTitle: string;
    confirmRemoveBody: string;
  };
  metric: {
    title: string;
    description: string;
    key: string;
    name: string;
    expression: string;
    expressionHint: string;
    dimensions: string;
    version: string;
    status: string;
    statusDraft: string;
    statusActive: string;
    statusRetired: string;
    createTitle: string;
    editTitle: string;
    retire: string;
    confirmRetireTitle: string;
    confirmRetireBody: string;
    versionMustAdvance: string;
  };
  history: {
    title: string;
    description: string;
    phase: string;
    status: string;
    code: string;
    risk: string;
    rows: string;
    bytes: string;
    cost: string;
    latency: string;
    startedAt: string;
    finishedAt: string;
    queryHash: string;
    planDigest: string;
    principalId: string;
    adminHint: string;
  };
  report: {
    title: string;
    description: string;
    artifactPath: string;
    evidence: string;
    status: string;
    statusPublished: string;
    createdAt: string;
    openAnalysis: string;
    downloadReport: string;
    empty: string;
  };
  trace: {
    title: string;
    toggle: string;
    empty: string;
    unparsed: string;
    evidenceId: string;
    copyEvidence: string;
    risk: string;
    rows: string;
    bytes: string;
    estimatedRows: string;
    engineCost: string;
    truncated: string;
    truncatedYes: string;
    truncatedNo: string;
    schemaVersion: string;
    policyVersion: string;
    resultDigest: string;
    stepPlan: string;
    stepCatalog: string;
    stepQuery: string;
    stepDelegate: string;
    stepArtifact: string;
    stepPublish: string;
    reviewer: string;
    reviewerApproved: string;
    reviewerRejected: string;
    reviewerFailed: string;
    reviewerLimited: string;
    reviewReasonUnsupportedClaim: string;
    reviewReasonEvidenceMismatch: string;
    reviewReasonMissingCitation: string;
    reviewReasonInsufficientEvidence: string;
    statusRunning: string;
    statusCompleted: string;
    statusFailed: string;
    statusRejected: string;
  };
  analysis: {
    newTitle: string;
    newDescription: string;
    threadTitle: string;
    compatibilityNotice: string;
  };
  errors: {
    unavailable: string;
    invalidRequest: string;
    notFound: string;
    versionConflict: string;
    storageUnavailable: string;
  };
}
