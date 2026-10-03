import { useEffect, useState, useSyncExternalStore } from "react";
import { createRoot } from "react-dom/client";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import { Separator } from "@/components/ui/separator";
import { createBridge } from "./bridge";
import {
  describe,
  noteName,
  excerpt,
  changeExcerpts,
  changeCounts,
  type Entry,
} from "./model";
const theme = JSON.parse(
  document.getElementById("kajamite-theme")!.textContent!,
);
const bridge = createBridge(theme);

// Legacy receipts retain broad-span highlighting. New ranges address code points.
function changedSpan(
  value: string,
  other: string,
  ranges?: [number, number][],
) {
  if (ranges) {
    const points = Array.from(value);
    let offset = 0;
    const parts = ranges.flatMap(([start, end]) => {
      const unchanged = points.slice(offset, start).join("");
      offset = end;
      return [
        unchanged,
        <mark key={start}>{points.slice(start, end).join("")}</mark>,
      ];
    });
    return (
      <>
        {parts}
        {points.slice(offset).join("")}
      </>
    );
  }
  if (value === other) return value;
  let start = 0,
    end = 0;
  while (
    start < Math.min(value.length, other.length) &&
    value[start] === other[start]
  )
    start++;
  while (start > 0 && /\S/.test(value[start - 1])) start--;
  while (
    end < Math.min(value.length, other.length) - start &&
    value[value.length - end - 1] === other[other.length - end - 1]
  )
    end++;
  while (end > 0 && /\S/.test(value[value.length - end])) end--;
  return (
    <>
      {value.slice(0, start)}
      <mark>{value.slice(start, value.length - end)}</mark>
      {end ? value.slice(-end) : ""}
    </>
  );
}
function Comparison({ item }: { item: Entry }) {
  const [full, setFull] = useState(false);
  const before = item.before ?? "None",
    after = item.after ?? "None";
  const long =
    (item.message !== undefined
      ? item.message.length
      : Math.max(before.length, after.length)) > 600;
  const oldPoints = Array.from(before),
    newPoints = Array.from(after);
  let common = 0;
  while (
    common < Math.min(oldPoints.length, newPoints.length) &&
    oldPoints[common] === newPoints[common]
  )
    common++;
  const offset =
    item.kind === "text" && !item.message ? Math.max(0, common - 180) : 0;
  const shown = (s: string) =>
    full || !long
      ? s
      : (offset ? "…" : "") +
        Array.from(s)
          .slice(offset, offset + 600)
          .join("") +
        (Array.from(s).length > offset + 600 ? "…" : "");
  const visibleRanges = (
    value: string,
    ranges: unknown,
  ): [number, number][] | undefined => {
    const length = Array.from(value).length;
    let previous = 0;
    if (
      !Array.isArray(ranges) ||
      ranges.length > 1000 ||
      !ranges.every((range) => {
        if (!Array.isArray(range) || range.length !== 2) return false;
        const [start, end] = range;
        const valid =
          Number.isInteger(start) &&
          Number.isInteger(end) &&
          start >= previous &&
          end > start &&
          end <= length;
        previous = end;
        return valid;
      })
    )
      return undefined;
    const start = full || !long ? 0 : offset;
    const end = full || !long ? length : offset + 600;
    const prefix = start ? 1 : 0;
    return ranges
      .filter(([a, b]) => b > start && a < end)
      .map(([a, b]) => [
        Math.max(a, start) - start + prefix,
        Math.min(b, end) - start + prefix,
      ]);
  };
  return (
    <div className="flex flex-col gap-2">
      {item.message !== undefined ? (
        <p className="whitespace-pre-wrap break-anywhere">
          {shown(item.message)}
        </p>
      ) : item.title === "Added content" || item.title === "Removed content" ? (
        <p className="whitespace-pre-wrap break-anywhere">
          {shown(item.title === "Added content" ? after : before)}
        </p>
      ) : item.kind === "field" ? (
        <p className="field-change break-anywhere">
          <span className="text-muted-foreground">{shown(before)}</span>
          <span aria-label="changed to"> → </span>
          <strong>{shown(after)}</strong>
        </p>
      ) : (
        <div className="diff">
          <div className="diff-line">
            <span className="diff-label">Before</span>
            <p>
              {changedSpan(
                shown(before),
                shown(after),
                visibleRanges(before, item.beforeRanges),
              )}
            </p>
          </div>
          <div className="diff-line diff-after">
            <span className="diff-label">After</span>
            <p>
              {changedSpan(
                shown(after),
                shown(before),
                visibleRanges(after, item.afterRanges),
              )}
            </p>
          </div>
        </div>
      )}
      {long && (
        <Button size="sm" variant="ghost" onClick={() => setFull(!full)}>
          {full ? "Shorten excerpt" : "Show full excerpt"}
        </Button>
      )}
      {item.truncated && (
        <p className="text-xs text-muted-foreground">
          The receipt contains an excerpt, not the full note.
        </p>
      )}
    </div>
  );
}
function SummaryEntry({ item, showNote }: { item: Entry; showNote: boolean }) {
  const [before, after] = changeExcerpts(
    item.before,
    item.after,
    item.kind === "text" ? 300 : 110,
  );
  return (
    <li className="summary-line">
      {showNote && item.note && (
        <span className="font-medium">
          {item.noteTitle || noteName(item.note)}
          <span className="text-muted-foreground"> · </span>
        </span>
      )}
      <span className="text-muted-foreground">{item.title}: </span>
      {item.message !== undefined ? (
        excerpt(item.message)
      ) : item.title === "Added content" || item.title === "Removed content" ? (
        excerpt(item.title === "Added content" ? item.after : item.before, 300)
      ) : (
        <>
          <span>{before}</span>
          <span aria-label="changed to"> → </span>
          <strong>{after}</strong>
        </>
      )}
    </li>
  );
}
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
  const waiting = state.stage === "waiting",
    working = state.stage === "working",
    cancelled = state.stage === "cancelled",
    active = waiting || working;
  const headline = waiting
    ? "Waiting for result"
    : working
      ? "Working"
      : cancelled
        ? "Operation cancelled"
        : view.headline;
  const batch = Array.isArray(state.result?.completed);
  const created =
    !state.error &&
    state.result?.knowledge_change?.body_change?.kind === "created";
  const fields = created
    ? view.entries.filter((item) => item.kind === "field")
    : [];
  const primary = view.entries.filter((item) => !fields.includes(item));
  const overview = primary
    .filter((item) => item.kind !== "message")
    .slice(0, batch ? 3 : 2);
  const errors = view.entries.filter((item) => item.kind === "message");
  const remaining = view.entries.filter(
    (item) => item.kind !== "message" && !overview.includes(item),
  );
  useEffect(() => {
    const observer = new ResizeObserver(bridge.resize);
    observer.observe(document.body);
    return () => observer.disconnect();
  }, []);
  useEffect(() => bridge.resize(), [state]);
  return (
    <main aria-label="Knowledge operation result">
      <Card className="gap-3 py-3">
        <CardHeader className="gap-1 px-4">
          <div className="result-heading">
            <CardTitle>
              <h1 id="headline" role="status">
                {headline}
              </h1>
            </CardTitle>
            <span id="counts" className="text-xs text-muted-foreground">
              {active || cancelled ? "" : view.counts}
            </span>
          </div>
          {view.subject && !active && (
            <CardDescription id="subject" className="break-anywhere">
              <strong className="text-card-foreground">
                {view.subjectTitle || noteName(view.subject)}
              </strong>
              <span className="note-path">{view.subject}</span>
            </CardDescription>
          )}
        </CardHeader>
        <Collapsible open={state.expanded} onOpenChange={bridge.toggle}>
          <CardContent className="px-4 flex flex-col gap-3">
            {!active && !state.expanded && (
              <div id="overview" className="flex flex-col gap-1">
                {cancelled ? (
                  <p>
                    The operation stopped. No completed change is confirmed
                    here.
                  </p>
                ) : (
                  <>
                    {view.summary && <p>{view.summary}</p>}
                    {!state.error && (
                      <ul className="flex flex-col gap-1">
                        {overview.map((item, i) => (
                          <SummaryEntry key={i} item={item} showNote={batch} />
                        ))}
                      </ul>
                    )}
                    {remaining.length > 0 && !state.error && (
                      <p className="text-xs text-muted-foreground">
                        {changeCounts(remaining)} in details
                      </p>
                    )}
                  </>
                )}
              </div>
            )}
            {!active && !cancelled && errors.length > 0 && (
              <div className="flex flex-col gap-1" role="status">
                {errors.slice(0, 2).map((item, i) => (
                  <p key={i} className="break-anywhere">
                    <strong>
                      {item.note ? noteName(item.note) : "Update failed"}:
                    </strong>{" "}
                    {excerpt(item.message, 180)}
                  </p>
                ))}
              </div>
            )}
            <p
              id="status"
              hidden={
                !state.disconnected && (active || cancelled || !view.attention)
              }
              className="text-sm text-muted-foreground"
            >
              {state.disconnected
                ? "Waiting for the host. The tool result remains available in chat."
                : view.attention}
            </p>
            <div id="actions" hidden={active}>
              <CollapsibleTrigger asChild>
                <Button variant="default" size="sm" id="toggle">
                  {state.expanded ? "Hide details" : view.action}
                </Button>
              </CollapsibleTrigger>
            </div>
            <CollapsibleContent id="review">
              <div id="changes" className="flex flex-col gap-3">
                {primary.slice(0, state.visible).map((item, index) => (
                  <section
                    key={`${state.generation}-${index}`}
                    className="flex flex-col gap-2"
                  >
                    <Separator />
                    {batch && item.note !== primary[index - 1]?.note && (
                      <div>
                        <h2 className="break-anywhere font-medium">
                          {item.noteTitle || noteName(item.note ?? "")}
                        </h2>
                        <p className="note-path break-anywhere">{item.note}</p>
                      </div>
                    )}
                    <h3 className="text-xs font-medium text-muted-foreground">
                      {item.title}
                    </h3>
                    <Comparison item={item} />
                  </section>
                ))}
              </div>
              <div className="flex flex-col items-start gap-2 pt-3">
                <Button
                  id="more"
                  variant="secondary"
                  size="sm"
                  hidden={state.visible >= primary.length}
                  onClick={bridge.showMore}
                >
                  Show more ({Math.max(0, primary.length - state.visible)}{" "}
                  remaining)
                </Button>
                {fields.length > 0 && (
                  <Collapsible key={`fields-${state.generation}`}>
                    <CollapsibleTrigger asChild>
                      <Button id="fields-toggle" variant="secondary" size="sm">
                        Note fields ({fields.length})
                      </Button>
                    </CollapsibleTrigger>
                    <CollapsibleContent
                      id="note-fields"
                      className="flex flex-col gap-3 pt-3"
                    >
                      {fields.map((item, index) => (
                        <section key={index} className="flex flex-col gap-2">
                          <h3 className="text-xs font-medium text-muted-foreground">
                            {item.title}
                          </h3>
                          <Comparison item={item} />
                        </section>
                      ))}
                    </CollapsibleContent>
                  </Collapsible>
                )}
                <Evidence
                  key={state.generation}
                  result={state.result}
                  status={view.status}
                  scope={view.scope}
                />
              </div>
            </CollapsibleContent>
          </CardContent>
        </Collapsible>
      </Card>
    </main>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
