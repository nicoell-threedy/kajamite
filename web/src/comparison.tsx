import { useId, useMemo, useState, type ReactNode } from "react";
import { flushSync } from "react-dom";
import type { Entry } from "./model";

type Op = {
  type: "same" | "remove" | "add";
  text: string;
  ai?: number;
  bi?: number;
};
export type DiffRow = Op & { parts: { text: string; changed: boolean }[] };
const LIMIT = 250_000;
/** Bounded sequence comparison. The fallback preserves each supplied string. */
export function sequenceDiff(a: string[], b: string[]): Op[] {
  if (a.length * b.length > LIMIT || a.length + b.length > 4000) {
    let first = 0,
      last = 0;
    while (first < Math.min(a.length, b.length) && a[first] === b[first])
      first++;
    while (
      last < Math.min(a.length, b.length) - first &&
      a[a.length - last - 1] === b[b.length - last - 1]
    )
      last++;
    return [
      ...a
        .slice(0, first)
        .map((text, i) => ({ type: "same" as const, text, ai: i, bi: i })),
      ...a
        .slice(first, a.length - last)
        .map((text, i) => ({ type: "remove" as const, text, ai: first + i })),
      ...b
        .slice(first, b.length - last)
        .map((text, i) => ({ type: "add" as const, text, bi: first + i })),
      ...a.slice(a.length - last).map((text, i) => ({
        type: "same" as const,
        text,
        ai: a.length - last + i,
        bi: b.length - last + i,
      })),
    ];
  }
  const table = Array.from(
    { length: a.length + 1 },
    () => new Uint32Array(b.length + 1),
  );
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--)
      table[i][j] =
        a[i] === b[j]
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1]);
  const result: Op[] = [];
  let i = 0,
    j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j])
      result.push({ type: "same", text: a[i], ai: i++, bi: j++ });
    else if (
      i < a.length &&
      (j === b.length || table[i + 1][j] >= table[i][j + 1])
    )
      result.push({ type: "remove", text: a[i], ai: i++ });
    else result.push({ type: "add", text: b[j], bi: j++ });
  }
  return result;
}
function tokenLines(before: string, after: string) {
  const tokens = (s: string) =>
    s.match(/\s+|[\p{L}\p{N}_]+|[^\s\p{L}\p{N}_]/gu) ?? [];
  const a = tokens(before),
    b = tokens(after);
  const result: DiffRow["parts"][][] = [[[]], [[]]];
  const ops = sequenceDiff(a, b);
  for (const op of ops)
    for (const side of [0, 1]) {
      if (
        (side === 0 && op.type === "add") ||
        (side === 1 && op.type === "remove")
      )
        continue;
      op.text.split("\n").forEach((text, i) => {
        if (i) result[side].push([]);
        if (text)
          result[side].at(-1)!.push({ text, changed: op.type !== "same" });
      });
    }
  return result;
}
export function lineDiff(before: string, after: string): DiffRow[] {
  const lines = (s: string) => (s === "" ? [] : s.split("\n"));
  const rows: DiffRow[] = sequenceDiff(lines(before), lines(after)).map(
    (op) => ({ ...op, parts: [{ text: op.text, changed: false }] }),
  );
  for (let start = 0; start < rows.length;) {
    if (rows[start].type === "same") {
      start++;
      continue;
    }
    let end = start + 1;
    while (end < rows.length && rows[end].type !== "same") end++;
    const old = rows.slice(start, end).filter((x) => x.type === "remove"),
      fresh = rows.slice(start, end).filter((x) => x.type === "add");
    const parts = tokenLines(
      old.map((x) => x.text).join("\n"),
      fresh.map((x) => x.text).join("\n"),
    );
    old.forEach((x, i) => (x.parts = parts[0][i] ?? x.parts));
    fresh.forEach((x, i) => (x.parts = parts[1][i] ?? x.parts));
    start = end;
  }
  return rows;
}
function keepPosition(button: HTMLButtonElement, update: () => void) {
  const top = button.getBoundingClientRect().top;
  const scrollers: HTMLElement[] = [];
  for (let node = button.parentElement; node; node = node.parentElement) {
    if (/auto|scroll/.test(getComputedStyle(node).overflowY))
      scrollers.push(node);
  }
  const root = document.scrollingElement as HTMLElement | null;
  if (root && !scrollers.includes(root)) scrollers.push(root);
  flushSync(update);
  button.focus({ preventScroll: true });
  const correct = () => {
    if (!button.isConnected) return;
    for (const node of scrollers) {
      const delta = button.getBoundingClientRect().top - top;
      if (Math.abs(delta) > 0.5) node.scrollTop += delta;
    }
  };
  correct();
  requestAnimationFrame(() => {
    correct();
    requestAnimationFrame(correct);
  });
}
function Fold({
  label,
  tone = "context",
  children,
}: {
  label: string;
  tone?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const action = `${open ? "Collapse" : "Expand"} ${label.replace(/ folded$/, "")}`;
  return (
    <div className={`diff-disclosure ${tone} ${open ? "is-open" : ""}`}>
      <button
        className="fold-seam"
        aria-expanded={open}
        aria-controls={id}
        aria-label={action}
        title={action}
        onClick={(e) => keepPosition(e.currentTarget, () => setOpen(!open))}
      >
        <span className="fold-icon" aria-hidden="true">
          {open ? "−" : "↕"}
        </span>
        <span className="fold-label">{label}</span>
      </button>
      <div id={id} className="fold-content" hidden={!open}>
        {children}
      </div>
    </div>
  );
}
function Text({ row }: { row: DiffRow }) {
  return (
    <span className="diff-text">
      {row.parts.map((p, i) =>
        p.changed ? (
          row.type === "remove" ? (
            <del key={i}>{p.text}</del>
          ) : (
            <ins key={i}>{p.text}</ins>
          )
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </span>
  );
}
const tone = (row: DiffRow) =>
  row.type === "remove" ? "removed" : row.type === "add" ? "added" : "context";
const sign = (row: DiffRow) =>
  row.type === "remove" ? "−" : row.type === "add" ? "+" : " ";
function Rows({ rows, split }: { rows: DiffRow[]; split: boolean }) {
  if (!split)
    return (
      <>
        {rows.map((row, i) => (
          <div className={`diff-row ${tone(row)}`} key={i}>
            <span
              className="number"
              aria-hidden="true"
              title="Before: line in supplied passage"
            >
              {row.ai === undefined ? "" : row.ai + 1}
            </span>
            <span
              className="number"
              aria-hidden="true"
              title="After: line in supplied passage"
            >
              {row.bi === undefined ? "" : row.bi + 1}
            </span>
            <span
              className="diff-sign"
              aria-label={
                row.type === "same"
                  ? "Unchanged"
                  : row.type === "add"
                    ? "Added"
                    : "Removed"
              }
            >
              {sign(row)}
            </span>
            <Text row={row} />
          </div>
        ))}
      </>
    );
  const pairs: [DiffRow | undefined, DiffRow | undefined][] = [];
  for (let start = 0; start < rows.length;) {
    if (rows[start].type === "same") {
      pairs.push([rows[start], rows[start]]);
      start++;
      continue;
    }
    let end = start + 1;
    while (end < rows.length && rows[end].type !== "same") end++;
    const old = rows.slice(start, end).filter((x) => x.type === "remove"),
      fresh = rows.slice(start, end).filter((x) => x.type === "add");
    for (let i = 0; i < Math.max(old.length, fresh.length); i++)
      pairs.push([old[i], fresh[i]]);
    start = end;
  }
  return (
    <>
      {pairs.map((pair, i) => (
        <div className="split-row" key={i}>
          {pair.map((row, side) =>
            row ? (
              <div key={side} className={`split-cell ${tone(row)}`}>
                <span className="number" aria-hidden="true">
                  {(side === 0 ? row.ai : row.bi)! + 1}
                </span>
                <span
                  className="diff-sign"
                  aria-label={
                    row.type === "same"
                      ? "Unchanged"
                      : row.type === "add"
                        ? "Added"
                        : "Removed"
                  }
                >
                  {sign(row)}
                </span>
                <Text row={row} />
              </div>
            ) : (
              <div
                key={side}
                className="split-cell split-empty"
                aria-hidden="true"
              />
            ),
          )}
        </div>
      ))}
    </>
  );
}
function Changed({ rows, split }: { rows: DiffRow[]; split: boolean }) {
  const old = rows.filter((x) => x.type === "remove"),
    fresh = rows.filter((x) => x.type === "add");
  if (Math.max(old.length, fresh.length) <= 8)
    return <Rows rows={rows} split={split} />;
  const preview = (items: DiffRow[], last: boolean) =>
    items.length <= 4
      ? last
        ? []
        : items
      : last
        ? items.slice(-2)
        : items.slice(0, 2);
  const middle = [
    ...(old.length > 4 ? old.slice(2, -2) : []),
    ...(fresh.length > 4 ? fresh.slice(2, -2) : []),
  ];
  const label = `${middle.length} ${!old.length ? "added" : !fresh.length ? "removed" : "changed"} lines folded`;
  return (
    <>
      <Rows
        rows={[...preview(old, false), ...preview(fresh, false)]}
        split={split}
      />
      <Fold
        label={label}
        tone={!old.length ? "added" : !fresh.length ? "removed" : "context"}
      >
        <Rows rows={middle} split={split} />
      </Fold>
      <Rows
        rows={[...preview(old, true), ...preview(fresh, true)]}
        split={split}
      />
    </>
  );
}
export function ComparisonSurface({
  item,
  split,
}: {
  item: Entry;
  split: boolean;
}) {
  const before = item.title === "Added content" ? "" : (item.before ?? "");
  const after = item.title === "Removed content" ? "" : (item.after ?? "");
  const rows = useMemo(() => lineDiff(before, after), [before, after]);
  const runs = useMemo(() => {
    const groups: { edit: boolean; rows: DiffRow[] }[] = [];
    for (const row of rows) {
      const edit = row.type !== "same";
      if (groups.at(-1)?.edit === edit) groups.at(-1)!.rows.push(row);
      else groups.push({ edit, rows: [row] });
    }
    return groups;
  }, [rows]);
  if (item.message !== undefined)
    return <p className="source-message">{item.message}</p>;
  if (item.kind === "location")
    return (
      <div className="location-change">
        <span>From</span>
        <strong>{before}</strong>
        <span>To</span>
        <strong>{after}</strong>
      </div>
    );
  const edits = runs.map((r, i) => (r.edit ? i : -1)).filter((i) => i >= 0);
  const middle = edits.length > 2 ? [edits[1], edits[edits.length - 2]] : null;
  const render = (run: (typeof runs)[number], index: number): ReactNode => {
    if (run.edit) return <Changed rows={run.rows} split={split} />;
    const keepStart = index === 0 ? 0 : 2,
      keepEnd = index === runs.length - 1 ? 0 : 2;
    if (run.rows.length <= 4) return <Rows rows={run.rows} split={split} />;
    const hidden = run.rows.slice(keepStart, run.rows.length - keepEnd);
    return (
      <>
        <Rows rows={run.rows.slice(0, keepStart)} split={split} />
        <Fold label={`${hidden.length} unchanged lines folded`}>
          <Rows rows={hidden} split={split} />
        </Fold>
        <Rows rows={keepEnd ? run.rows.slice(-keepEnd) : []} split={split} />
      </>
    );
  };
  return (
    <div
      className={`comparison-surface diff ${split ? "diff-split" : ""} ${item.kind === "field" ? "field-diff" : ""}`}
    >
      {split && (
        <div className="split-labels">
          <span>Before</span>
          <span>After</span>
        </div>
      )}
      {runs.map((run, i) => {
        if (middle && i >= middle[0] && i <= middle[1])
          return i === middle[0] ? (
            <Fold key={`run-${i}`} label={`${edits.length - 2} edits folded`}>
              {runs.slice(middle[0], middle[1] + 1).map((r, j) => (
                <div key={j}>{render(r, middle[0] + j)}</div>
              ))}
            </Fold>
          ) : null;
        return <div key={`run-${i}`}>{render(run, i)}</div>;
      })}
      {item.truncated && (
        <p className="unavailable-text">
          Further text was not supplied. Line numbers refer to this excerpt.
        </p>
      )}
    </div>
  );
}
