import { afterEach, expect, test, rs } from "@rstest/core";

async function captureThreadStreamOptions(
  streamCallbacks: Record<string, unknown> = {},
) {
  let capturedOptions: Record<string, unknown> | undefined;

  rs.resetModules();
  rs.doMock("react", () => ({
    useCallback: <T extends (...args: never[]) => unknown>(callback: T) =>
      callback,
    useEffect: () => undefined,
    useMemo: <T>(factory: () => T) => factory(),
    useRef: <T>(initialValue: T) => ({ current: initialValue }),
    useState: <T>(initialValue: T | (() => T)) => [
      typeof initialValue === "function"
        ? (initialValue as () => T)()
        : initialValue,
      rs.fn(),
    ],
  }));
  rs.doMock("@tanstack/react-query", () => ({
    useInfiniteQuery: () => ({
      data: { pages: [] },
      error: null,
      fetchNextPage: rs.fn(),
      hasNextPage: false,
      isFetchingNextPage: false,
      isLoading: false,
    }),
    useMutation: rs.fn(),
    useQuery: rs.fn(),
    useQueryClient: () => ({
      invalidateQueries: rs.fn(),
      setQueriesData: rs.fn(),
    }),
  }));
  rs.doMock("@langchain/langgraph-sdk/react", () => ({
    useStream: (options: Record<string, unknown>) => {
      capturedOptions = options;
      return {
        isLoading: false,
        messages: [],
        stop: rs.fn(),
        submit: rs.fn(),
        values: { title: "", messages: [] },
      };
    },
  }));
  rs.doMock("@/core/api", () => ({
    getAPIClient: () => ({}),
  }));
  rs.doMock("@/core/i18n/hooks", () => ({
    useI18n: () => ({
      t: {
        pages: { newChat: "New chat" },
        uploads: { uploadingFiles: "Uploading files" },
      },
    }),
  }));
  rs.doMock("@/core/tasks/context", () => ({
    useSubtaskContext: () => ({
      tasksRef: { current: {} },
      setTasks: rs.fn(),
    }),
    useUpdateSubtask: () => rs.fn(),
  }));

  const { useThreadStream } = await import("@/core/threads/hooks");
  function ThreadStreamCapture() {
    useThreadStream({
      context: {
        mode: "flash",
      },
      isMock: true,
      ...streamCallbacks,
    } as never);
    return null;
  }
  ThreadStreamCapture();

  return capturedOptions;
}

afterEach(() => {
  rs.doUnmock("react");
  rs.doUnmock("@tanstack/react-query");
  rs.doUnmock("@langchain/langgraph-sdk/react");
  rs.doUnmock("@/core/api");
  rs.doUnmock("@/core/i18n/hooks");
  rs.doUnmock("@/core/tasks/context");
  rs.resetModules();
});

test("does not subscribe to unsupported LangGraph events mode", async () => {
  const options = await captureThreadStreamOptions();

  expect(options).toBeDefined();
  expect(options).not.toHaveProperty("onLangChainEvent");
  expect(options).toHaveProperty("onUpdateEvent");
  expect(options).toHaveProperty("onCustomEvent");
});

test("binds custom events to the stream metadata callback", async () => {
  const metadataEvents: unknown[] = [];
  const customEvents: Array<{ event: unknown; metadata: unknown }> = [];
  const options = await captureThreadStreamOptions({
    onStreamMetadata: (metadata: unknown) => metadataEvents.push(metadata),
    onCustomEvent: (event: unknown, metadata: unknown) =>
      customEvents.push({ event, metadata }),
  });
  const metadata = { thread_id: "thread-1", run_id: "run-1" };
  const event = { type: "analysis_stage", run_id: "run-1", seq: 1 };

  (
    options?.onMetadataEvent as ((value: typeof metadata) => void) | undefined
  )?.(metadata);
  (
    options?.onCustomEvent as
      | ((
          value: typeof event,
          options: { namespace: undefined; mutate: () => void },
        ) => void)
      | undefined
  )?.(event, { namespace: undefined, mutate: () => undefined });

  expect(metadataEvents).toEqual([metadata]);
  expect(customEvents).toEqual([{ event, metadata }]);
});
