import { applyTheme, type HostContext, type Theme } from "./theme";
import { reviewResult } from "./model";
export type Snapshot = {
  result: any;
  error: boolean;
  stage: "waiting" | "working" | "result" | "cancelled";
  expanded: boolean;
  visible: number;
  generation: number;
  host: HostContext;
  ready: boolean;
  disconnected: boolean;
};
export function createBridge(theme: Theme) {
  let state: Snapshot = {
    result: {},
    error: false,
    stage: "waiting",
    expanded: false,
    visible: 3,
    generation: 0,
    host: {},
    ready: false,
    disconnected: false,
  };
  let nextId = 1;
  let resultRequest = 0;
  const subscribers = new Set<() => void>();
  const pending = new Map<
    number,
    {
      resolve: (v: any) => void;
      reject: (e: any) => void;
      timer: ReturnType<typeof setTimeout>;
    }
  >();
  const update = (patch: Partial<Snapshot>) => {
    state = { ...state, ...patch };
    subscribers.forEach((fn) => fn());
  };
  const send = (method: string, params: any) =>
    parent.postMessage({ jsonrpc: "2.0", method, params }, "*");
  const request = (method: string, params: any, timeout = 1500): Promise<any> =>
    new Promise((resolve, reject) => {
      const id = nextId++;
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(Error("Host did not respond"));
      }, timeout);
      pending.set(id, { resolve, reject, timer });
      parent.postMessage({ jsonrpc: "2.0", id, method, params }, "*");
    });
  const context = (patch: HostContext) => {
    const previous = state.host.displayMode;
    const host = { ...state.host, ...patch };
    const expanded =
      host.displayMode === "fullscreen"
        ? true
        : previous === "fullscreen"
          ? false
          : state.expanded;
    applyTheme(theme, host);
    update({ host, expanded });
  };
  const result = (
    value: any,
    error = false,
    stage: Snapshot["stage"] = "result",
  ) =>
    update({
      result: value ?? {},
      error,
      stage,
      expanded: false,
      visible: 3,
      generation: state.generation + 1,
    });
  window.addEventListener("message", (event) => {
    if (event.source !== parent || event.data?.jsonrpc !== "2.0") return;
    const m = event.data;
    if (pending.has(m.id)) {
      const p = pending.get(m.id)!;
      pending.delete(m.id);
      clearTimeout(p.timer);
      m.error ? p.reject(m.error) : p.resolve(m.result ?? {});
      return;
    }
    if (m.method === "ui/notifications/host-context-changed")
      context(m.params ?? {});
    if (m.method === "ui/notifications/tool-result") {
      const request = ++resultRequest;
      reviewResult(m.params).then((value) => {
        if (request === resultRequest) result(value, m.params?.isError);
      });
    }
    if (m.method === "ui/notifications/tool-input") {
      resultRequest++;
      result({}, false, "working");
    }
    if (m.method === "ui/notifications/tool-cancelled") {
      resultRequest++;
      result(
        {
          content: [
            { type: "text", text: m.params?.reason ?? "Operation cancelled" },
          ],
        },
        true,
        "cancelled",
      );
    }
  });
  applyTheme(theme, {});
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () =>
    applyTheme(theme, state.host),
  );
  request(
    "ui/initialize",
    {
      protocolVersion: "2026-01-26",
      appInfo: { name: "kajamite-knowledge-change", version: "4.0.0" },
      appCapabilities: { availableDisplayModes: ["inline", "fullscreen"] },
    },
    10000,
  )
    .then((value) => {
      update({ ready: true });
      send("ui/notifications/initialized", {});
      context(value.hostContext ?? {});
    })
    .catch(() => update({ disconnected: true }));
  return {
    subscribe: (fn: () => void) => {
      subscribers.add(fn);
      return () => {
        subscribers.delete(fn);
      };
    },
    snapshot: () => state,
    resize: () => {
      if (state.ready && state.host.displayMode !== "fullscreen")
        send("ui/notifications/size-changed", {
          width: document.documentElement.clientWidth,
          height: Math.ceil(document.body.getBoundingClientRect().height),
        });
    },
    showMore: () => update({ visible: state.visible + 3 }),
    toggle: async (expanded: boolean) => {
      const generation = state.generation;
      update({ expanded });
      if (expanded && !state.host.availableDisplayModes?.includes("fullscreen"))
        return;
      if (!expanded && state.host.displayMode !== "fullscreen") return;
      try {
        const reply = await request("ui/request-display-mode", {
          mode: expanded ? "fullscreen" : "inline",
        });
        if (state.generation === generation && state.expanded === expanded)
          context({ displayMode: reply.mode });
      } catch (_) {
        /* Local disclosure remains usable when the host refuses. */
      }
    },
  };
}
