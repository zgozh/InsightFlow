import { useMDXComponents as getThemeComponents } from "nextra-theme-docs";

// Get the default MDX components
const themeComponents = getThemeComponents();

// Merge components. InsightFlow 已删除 nextra 文档站路由与本地化 MDX 组件
// （`components/docs/**`、`src/content/**`），这里只保留主题默认映射，让
// 仍被引用的 nextra 包装保持可编译。
export function useMDXComponents() {
  return {
    ...themeComponents,
  };
}
