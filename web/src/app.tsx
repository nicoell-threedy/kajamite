import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { createRoot } from "react-dom/client";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import { createBridge } from "./bridge";
import { describe, creationClaim, noteName } from "./model";
import { ComparisonSurface } from "./comparison";
const theme = JSON.parse(
  document.getElementById("kajamite-theme")!.textContent!,
);
const bridge = createBridge(theme);
function Evidence({
  result,
  status,
  scope,
}: {
  result: any;
  status: string;
  scope: string;
}) {
  return (
    <Collapsible>
      <CollapsibleTrigger asChild>
        <Button variant="ghost" size="sm" id="about-toggle">
          About this result
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="flex flex-col gap-2 pt-2">
        <p className="text-xs text-muted-foreground">{status}</p>
        <p id="scope" className="text-xs text-muted-foreground">
          {scope}
        </p>
        <Collapsible>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" id="evidence-toggle">
              Raw receipt
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent id="evidence">
            <pre
              id="raw"
              className="break-anywhere whitespace-pre-wrap font-mono text-xs"
            >
              {JSON.stringify(result, null, 2)}
            </pre>
          </CollapsibleContent>
        </Collapsible>
      </CollapsibleContent>
    </Collapsible>
  );
}
function App() {
  const state = useSyncExternalStore(bridge.subscribe, bridge.snapshot);
  const view = describe(state.result, state.error);
  const [snapshot, setSnapshot] = useState<{
    generation: number;
    claim: string;
  } | null>(null);
  const [layout, setLayout] = useState("unified");
  const [reading, setReading] = useState(false);
  const [wide, setWide] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let current = true;
    if (!state.error)
      creationClaim(state.result).then((claim) => {
        if (current)
          setSnapshot(
            claim === null ? null : { generation: state.generation, claim },
          );
      });
    return () => {
      current = false;
    };
  }, [state.result, state.generation, state.error]);
  if (!state.error && snapshot?.generation === state.generation)
    view.entries = view.entries.map((item) =>
      item.title === "Added content"
        ? { ...item, after: snapshot.claim, truncated: false, complete: true }
        : item,
    );
  useEffect(() => {
    const observer = new ResizeObserver(() => {
      bridge.resize();
      if (container.current) setWide(container.current.clientWidth >= 560);
    });
    observer.observe(document.body);
    if (container.current) observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    setLayout("unified");
    setReading(false);
    bridge.resize();
  }, [state.generation]);
  useEffect(() => bridge.resize(), [state.expanded]);
  const active = state.stage === "waiting" || state.stage === "working",
    cancelled = state.stage === "cancelled";
  const headline =
    state.stage === "waiting"
      ? "Waiting for result"
      : state.stage === "working"
        ? "Working"
        : cancelled
          ? "Operation cancelled"
          : view.headline;
  const batch = Array.isArray(state.result?.completed);
  const subject = view.subjectTitle || noteName(view.subject);
  const readable = view.entries.filter(
    (item) =>
      item.kind === "text" &&
      item.title !== "Removed content" &&
      item.after !== undefined &&
      item.after !== "None" &&
      item.message === undefined,
  );
  const split = state.expanded && layout === "split" && wide;
  const outcome = state.disconnected
    ? "Waiting for the host. The tool result remains available in chat."
    : view.attention || (state.error ? view.status : "");
  return (
    <main
      aria-label="Knowledge operation result"
      data-expanded={state.expanded}
      ref={container}
    >
      <Card className="result-card gap-3 py-3">
        <CardHeader className="gap-1 px-4">
          <CardTitle>
            <h1
              id="headline"
              className={subject && !active ? "result-outcome" : ""}
              role="status"
            >
              {headline}
            </h1>
          </CardTitle>
          {subject && !active && (
            <div id="subject" className="note-subject">
              <h2>{subject}</h2>
              <span className="note-path" hidden={!state.expanded}>
                {view.subject}
              </span>
            </div>
          )}
          {
            <p id="counts" className="result-counts" hidden={!batch}>
              {view.counts}
            </p>
          }
        </CardHeader>
        <CardContent className="px-4 flex flex-col gap-3">
          {!active && cancelled && (
            <p>The operation stopped. No completed change is confirmed here.</p>
          )}
          {!active && !cancelled && (
            <div id="overview">
              {view.summary && <p className="result-summary">{view.summary}</p>}
              {state.expanded && readable.length > 0 && (
                <div
                  className="content-switch"
                  role="tablist"
                  aria-label="Note content"
                  onKeyDown={(event) => {
                    if (
                      !["ArrowLeft", "ArrowRight", "Home", "End"].includes(
                        event.key,
                      )
                    )
                      return;
                    event.preventDefault();
                    const next =
                      event.key === "Home"
                        ? false
                        : event.key === "End"
                          ? true
                          : !reading;
                    setReading(next);
                    document
                      .getElementById(next ? "reading-tab" : "edits-tab")
                      ?.focus();
                  }}
                >
                  <Button
                    variant="ghost"
                    size="sm"
                    id="edits-tab"
                    role="tab"
                    tabIndex={reading ? -1 : 0}
                    aria-selected={!reading}
                    aria-controls="changes"
                    onClick={() => setReading(false)}
                  >
                    Edits
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    id="reading-tab"
                    role="tab"
                    tabIndex={reading ? 0 : -1}
                    aria-selected={reading}
                    aria-controls="reading"
                    onClick={() => setReading(true)}
                  >
                    {readable.every((item) => item.complete)
                      ? "Read note"
                      : "Read text"}
                  </Button>
                </div>
              )}
              <div
                className="diff-toolbar"
                hidden={
                  !state.expanded ||
                  reading ||
                  !view.entries.some(
                    (item) => item.kind === "text" || item.kind === "field",
                  )
                }
              >
                <div className="diff-switch" aria-label="Diff layout">
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-pressed={!split}
                    onClick={() => setLayout("unified")}
                  >
                    Unified
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-pressed={split}
                    disabled={!wide}
                    title={
                      !wide ? "Split view needs at least 560 px" : undefined
                    }
                    onClick={() => setLayout("split")}
                  >
                    Split
                  </Button>
                </div>
              </div>
              <div
                id="changes"
                hidden={state.expanded && reading}
                className="comparison-frame"
                tabIndex={view.entries.length ? 0 : undefined}
                role="region"
                aria-label="Note changes"
              >
                {view.entries.map((item, index) => (
                  <section
                    className="change-entry"
                    key={`${state.generation}-${index}`}
                  >
                    {batch &&
                      item.note &&
                      item.note !== view.entries[index - 1]?.note && (
                        <header className="entry-note">
                          <h2>{item.noteTitle || noteName(item.note)}</h2>
                          <p className="note-path" hidden={!state.expanded}>
                            {item.note}
                          </p>
                        </header>
                      )}
                    {(item.kind === "field" ||
                      item.kind === "location" ||
                      item.kind === "message") && (
                      <h3 className="entry-label">{item.title}</h3>
                    )}
                    <ComparisonSurface item={item} split={split} />
                  </section>
                ))}
              </div>
              {state.expanded && reading && (
                <div
                  id="reading"
                  className="reading-passages"
                  role="tabpanel"
                  aria-labelledby="reading-tab"
                >
                  {readable.map((item, index) => (
                    <section key={index}>
                      {readable.length > 1 && (
                        <h3 className="entry-label">{item.title}</h3>
                      )}
                      <p className="source-message">{item.after}</p>
                      {item.truncated && (
                        <p className="unavailable-text">
                          Further text was not supplied.
                        </p>
                      )}
                    </section>
                  ))}
                </div>
              )}
            </div>
          )}
          <p
            id="status"
            hidden={!outcome || active || cancelled}
            className="result-attention"
          >
            {outcome}
          </p>
          <footer id="actions" className="result-actions" hidden={active}>
            <span className="save-state" aria-hidden="true">
              {cancelled
                ? "□"
                : state.error ||
                    state.result?.partial ||
                    state.result?.errors?.length
                  ? "!"
                  : state.result?.preview
                    ? "◌"
                    : state.result?.replayed
                      ? "↶"
                      : [
                            "No change receipt returned",
                            "Result could not be displayed",
                          ].includes(view.headline)
                        ? "?"
                        : "✓"}
            </span>
            <span>
              {state.result?.preview
                ? "Nothing saved"
                : state.result?.replayed
                  ? "No new write"
                  : state.error
                    ? "Check before retrying"
                    : cancelled
                      ? "Stopped"
                      : view.status || headline}
            </span>
            <Button
              variant="ghost"
              size="sm"
              id="toggle"
              aria-expanded={state.expanded}
              onClick={() => bridge.toggle(!state.expanded)}
            >
              {state.expanded ? "Close details" : view.action}
              <span aria-hidden="true">{state.expanded ? "×" : "↗"}</span>
            </Button>
          </footer>
          <div id="review" hidden={!state.expanded}>
            <Evidence
              key={state.generation}
              result={state.result}
              status={view.status}
              scope={view.scope}
            />
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
