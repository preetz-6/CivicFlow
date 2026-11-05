import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../../api/client";
import type { OpsCause, OpsItem, OpsRun, OpsSummary } from "../../api/types";
import { ErrorBox } from "../../ui/ErrorBox";
import s from "./operations.module.css";

const FEED_MS = 2000;
const SUMMARY_MS = 10_000;

type CauseType = OpsCause["type"];
type IconName = CauseType | "feed";

/** Runs that no person started: vehicle feed, SLA clock, another agent, weather. */
function isAutonomous(r: OpsRun): boolean {
  return r.cause.type !== "human" && r.cause.type !== "citizen";
}

const CAUSE_NAME: Record<CauseType, string> = {
  citizen: "Citizen",
  vehicle_feed: "Vehicle feed",
  clock: "Timer",
  agent: "Agent hand-off",
  human: "Staff action",
  weather: "Weather",
};

const STATUS_TEXT: Record<OpsRun["status"], string> = {
  RUNNING: "Running",
  OK: "Done",
  FALLBACK: "Done (rule-based fallback)",
  ERROR: "Error",
};

function modelText(model: string | null): string | null {
  if (!model) return null;
  if (model === "rules") return "Rule-based";
  if (model.startsWith("replay:")) return `Recorded (${model.slice(7)})`;
  return model;
}

function fmtTime(at: string): string {
  return new Date(at).toLocaleTimeString("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function pct(c: number | null): string | null {
  if (c === null || c === undefined) return null;
  return `${Math.round(c <= 1 ? c * 100 : c)}%`;
}

/** Small monochrome line icons, one per cause type. Decorative: the text next to them says the same. */
export function OpsIcon({ name }: { name: IconName }) {
  const common = {
    width: 18,
    height: 18,
    viewBox: "0 0 20 20",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.6,
    "aria-hidden": true,
    focusable: false,
    className: s.icon,
  } as const;
  switch (name) {
    case "citizen":
      return (
        <svg {...common}>
          <circle cx="10" cy="6" r="3.2" />
          <path d="M3.5 18c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6" />
        </svg>
      );
    case "human":
      return (
        <svg {...common}>
          <rect x="3" y="2.5" width="14" height="15" rx="1" />
          <circle cx="10" cy="8" r="2.4" />
          <path d="M6 15c0-2.2 1.8-3.6 4-3.6s4 1.4 4 3.6" />
        </svg>
      );
    case "vehicle_feed":
    case "feed":
      return (
        <svg {...common}>
          <path d="M2.5 13.5V10l2-4.5h11l2 4.5v3.5z" />
          <path d="M2.5 10h15" />
          <circle cx="6" cy="15" r="1.6" />
          <circle cx="14" cy="15" r="1.6" />
        </svg>
      );
    case "clock":
      return (
        <svg {...common}>
          <circle cx="10" cy="10" r="7.5" />
          <path d="M10 5.5V10l3 2" />
        </svg>
      );
    case "agent":
      return (
        <svg {...common}>
          <rect x="4.5" y="4.5" width="11" height="11" />
          <rect x="8" y="8" width="4" height="4" />
          <path d="M8 2v2.5M12 2v2.5M8 15.5V18M12 15.5V18M2 8h2.5M2 12h2.5M15.5 8H18M15.5 12H18" />
        </svg>
      );
    case "weather":
      return (
        <svg {...common}>
          <path d="M5.5 12h9a3.2 3.2 0 0 0 0-6.4 4.5 4.5 0 0 0-8.6.9A2.8 2.8 0 0 0 5.5 12z" />
          <path d="M7 14.5l-1 2.5M10.5 14.5l-1 2.5M14 14.5l-1 2.5" />
        </svg>
      );
  }
}

function SubjectLink({ id }: { id: string | null }) {
  if (!id) return null;
  if (id.startsWith("SR-")) return <Link to={`/control/complaints/${encodeURIComponent(id)}`}>{id}</Link>;
  return <span>{id}</span>;
}

function Counters({ summary }: { summary: OpsSummary | null }) {
  if (!summary) return null;
  const agents = Object.entries(summary.by_agent).sort((a, b) => b[1] - a[1]);
  return (
    <div className={s.counters} aria-label="Totals">
      <span>
        <strong>{summary.runs}</strong> agent runs
        {agents.length ? (
          <span className="muted">
            {" "}
            ({agents.map(([name, n]) => `${name} ${n}`).join(", ")})
          </span>
        ) : null}
      </span>
      <span>
        <strong>{summary.actions}</strong> actions taken
      </span>
      <span>
        <strong>{summary.human_decisions}</strong> human decisions
      </span>
      <span className={s.nobody}>
        <strong>{summary.autonomous_runs}</strong> runs nobody clicked
      </span>
    </div>
  );
}

interface RunPanelProps {
  run: OpsRun;
  selected: boolean;
  highlighted: boolean;
  animate: boolean;
  onSelect: (id: number) => void;
  onJump: (id: number) => void;
}

function RunPanel({ run, selected, highlighted, animate, onSelect, onJump }: RunPanelProps) {
  const model = modelText(run.model);
  const conf = pct(run.confidence);
  const running = run.status === "RUNNING";
  const cls = [s.run, selected ? s.selected : "", highlighted ? s.highlight : "", animate ? s.enter : ""]
    .filter(Boolean)
    .join(" ");
  return (
    <article id={`run-${run.id}`} className={cls} aria-labelledby={`run-${run.id}-h`} aria-busy={running}>
      <header className={s.runHead}>
        <h2 id={`run-${run.id}-h`} className={s.runTitle} tabIndex={-1}>
          {run.agent_label}
        </h2>
        <span className={`${s.status} ${s[`st${run.status}`] ?? ""}`}>{STATUS_TEXT[run.status] ?? run.status}</span>
        {model ? <span className="muted">{model}</span> : null}
        <span className={s.time}>
          <time dateTime={run.at}>{fmtTime(run.at)}</time>
        </span>
      </header>

      <p className={s.cause}>
        <OpsIcon name={run.cause.type} />
        <strong>Started by:</strong>{" "}
        {run.cause.label.startsWith(CAUSE_NAME[run.cause.type]) ? null : (
          <span className="visually-hidden">{CAUSE_NAME[run.cause.type]}: </span>
        )}
        {run.cause.type === "agent" ? (
          <a
            href={`#run-${run.cause.run_id}`}
            onClick={(e) => {
              e.preventDefault();
              onJump(run.cause.type === "agent" ? run.cause.run_id : run.id);
            }}
          >
            {run.cause.label}
          </a>
        ) : (
          <span>{run.cause.label}</span>
        )}
      </p>

      {run.subject_id ? (
        <p className={s.subject}>
          On: <SubjectLink id={run.subject_id} />
        </p>
      ) : null}

      {run.steps.length ? (
        <ol className={s.steps} aria-label="Steps taken">
          {run.steps.map((st) => (
            <li key={st.idx} className={`${s.step} ${s[`k${st.kind}`] ?? ""}`}>
              {st.kind === "rule" ? <span className={s.check}>check</span> : null}
              {st.kind === "action" ? <strong>{st.label}</strong> : <span>{st.label}</span>}
              {st.summary ? <span className={s.stepSummary}> - {st.summary}</span> : null}
            </li>
          ))}
          {running ? <li className={`${s.step} ${s.working}`}>working...</li> : null}
        </ol>
      ) : running ? (
        <p className={`${s.step} ${s.working}`}>working...</p>
      ) : null}

      {run.decision ? (
        <p className={s.decision}>
          <strong>Decision:</strong> {run.decision}
          {conf ? <span className="muted"> (confidence {conf})</span> : null}
          {run.latency_ms !== null ? <span className="muted"> - {(run.latency_ms / 1000).toFixed(1)} s</span> : null}
        </p>
      ) : null}

      {run.guardrails.length ? (
        <div className={s.guardrail}>
          {run.guardrails.map((g) => (
            <p key={g}>
              <strong>Guardrail:</strong> {g}
            </p>
          ))}
        </div>
      ) : null}

      {run.human.accepted_by ? <p className={s.human}>Accepted by {run.human.accepted_by}</p> : null}
      {run.human.overridden_by ? (
        <p className={s.human}>
          Overridden by {run.human.overridden_by}
          {run.human.override_reason ? `: ${run.human.override_reason}` : ""}
        </p>
      ) : null}

      <div className={s.runFoot}>
        <button type="button" className={`btn btn-secondary ${s.small}`} aria-pressed={selected} onClick={() => onSelect(run.id)}>
          Show chain
        </button>
        <Link to={`/control/activity/${run.id}`}>Full log (run {run.id})</Link>
      </div>
    </article>
  );
}

function ThinRow({ item, animate }: { item: Exclude<OpsItem, OpsRun>; animate: boolean }) {
  const icon: IconName = item.kind === "human" ? "human" : item.kind === "citizen" ? "citizen" : "feed";
  return (
    <div className={`${s.thin} ${animate ? s.enter : ""}`}>
      <OpsIcon name={icon} />
      <span className={s.thinText}>
        {item.text}
        {item.kind === "human" && item.role ? <span className="muted"> ({item.role.replace(/_/g, " ").toLowerCase()})</span> : null}
      </span>
      <time className={s.time} dateTime={item.at}>
        {fmtTime(item.at)}
      </time>
    </div>
  );
}

interface ChainNode {
  key: string;
  icon: IconName;
  title: string;
  detail?: string;
  runId?: number;
  current?: boolean;
}

/** Walk `cause` back to the root, then list the runs this one handed off to. */
function buildChain(run: OpsRun, byId: Map<number, OpsRun>, runs: OpsRun[]): { up: ChainNode[]; down: OpsRun[] } {
  const up: ChainNode[] = [];
  const seen = new Set<number>();
  let cur: OpsRun | undefined = run;
  while (cur && !seen.has(cur.id)) {
    seen.add(cur.id);
    const outcome = cur.human.overridden_by
      ? `Overridden by ${cur.human.overridden_by}`
      : cur.human.accepted_by
        ? `Accepted by ${cur.human.accepted_by}`
        : undefined;
    up.unshift({
      key: `r${cur.id}`,
      icon: "agent",
      title: cur.agent_label,
      detail: [cur.subject_id, cur.decision, outcome].filter(Boolean).join(" - ") || undefined,
      runId: cur.id,
      current: cur.id === run.id,
    });
    const c: OpsCause = cur.cause;
    if (c.type === "agent") {
      const parent = byId.get(c.run_id);
      if (!parent) {
        up.unshift({ key: `x${c.run_id}`, icon: "agent", title: c.label, detail: `run ${c.run_id} (older than this view)` });
        break;
      }
      cur = parent;
    } else {
      up.unshift({ key: `root-${cur.id}`, icon: c.type, title: CAUSE_NAME[c.type], detail: c.label });
      break;
    }
  }
  const down = runs.filter((r) => r.cause.type === "agent" && r.cause.run_id === run.id);
  return { up, down };
}

function ChainView({
  run,
  byId,
  runs,
  onJump,
}: {
  run: OpsRun | null;
  byId: Map<number, OpsRun>;
  runs: OpsRun[];
  onJump: (id: number) => void;
}) {
  return (
    <section className={s.rail} aria-labelledby="chain-h">
      <h2 id="chain-h" className={s.railTitle}>
        Chain of events
      </h2>
      {!run ? (
        <p className="muted">Select "Show chain" on a run.</p>
      ) : (
        (() => {
          const { up, down } = buildChain(run, byId, runs);
          return (
            <>
              <ol className={s.chain}>
                {up.map((n) => (
                  <li key={n.key} className={n.current ? s.chainCurrent : undefined}>
                    <OpsIcon name={n.icon} />
                    <div>
                      {n.runId !== undefined && !n.current ? (
                        <a
                          href={`#run-${n.runId}`}
                          onClick={(e) => {
                            e.preventDefault();
                            onJump(n.runId!);
                          }}
                        >
                          {n.title}
                        </a>
                      ) : (
                        <strong>{n.title}</strong>
                      )}
                      {n.detail ? <div className={s.chainDetail}>{n.detail}</div> : null}
                    </div>
                  </li>
                ))}
                {down.map((d) => (
                  <li key={`d${d.id}`}>
                    <OpsIcon name="agent" />
                    <div>
                      <a
                        href={`#run-${d.id}`}
                        onClick={(e) => {
                          e.preventDefault();
                          onJump(d.id);
                        }}
                      >
                        {d.agent_label}
                      </a>
                      <div className={s.chainDetail}>{[d.subject_id, d.decision].filter(Boolean).join(" - ") || "handed off"}</div>
                    </div>
                  </li>
                ))}
              </ol>
            </>
          );
        })()
      )}
    </section>
  );
}

/**
 * Agent Operations: a live timeline of what the agents are doing and what started each run.
 * Polls the feed every 2 s; items are keyed so new ones animate in and RUNNING runs update in place.
 */
export function Operations() {
  const [items, setItems] = useState<OpsItem[] | null>(null);
  const [summary, setSummary] = useState<OpsSummary | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [announce, setAnnounce] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [highlightId, setHighlightId] = useState<number | null>(null);
  const [agent, setAgent] = useState("");
  const [onlyAuto, setOnlyAuto] = useState(false);
  const [onlyActions, setOnlyActions] = useState(false);
  const [paused, setPaused] = useState(false);
  const known = useRef<Set<string> | null>(null);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  const loadFeed = useCallback(async () => {
    try {
      const next = await get<OpsItem[]>("/agent-ops/feed?limit=80");
      setError(null);
      const prev = known.current;
      const keys = new Set(next.map((i) => i.key));
      if (prev) {
        const added = next.filter((i) => !prev.has(i.key));
        setFresh(new Set(added.map((i) => i.key)));
        const newRuns = added.filter((i): i is OpsRun => i.kind === "agent_run");
        if (newRuns.length) {
          setAnnounce(
            newRuns
              .map((r) => `${r.agent_label} started${r.subject_id ? ` on ${r.subject_id}` : ""}: ${r.cause.label}`)
              .join(". "),
          );
        }
      }
      known.current = keys;
      setItems(next);
    } catch (e) {
      setError(e);
    }
  }, []);

  const loadSummary = useCallback(async () => {
    try {
      setSummary(await get<OpsSummary>("/agent-ops/summary"));
    } catch {
      setSummary(null);
    }
  }, []);

  useEffect(() => {
    document.title = "Agent Operations | Control Room";
    let alive = true;
    let timer = 0;
    const tick = async () => {
      if (!pausedRef.current && document.visibilityState === "visible") await loadFeed();
      if (alive) timer = window.setTimeout(() => void tick(), FEED_MS);
    };
    void tick();
    void loadSummary();
    const sTimer = window.setInterval(() => void loadSummary(), SUMMARY_MS);
    return () => {
      alive = false;
      window.clearTimeout(timer);
      window.clearInterval(sTimer);
    };
  }, [loadFeed, loadSummary]);

  const runs = useMemo(() => (items ?? []).filter((i): i is OpsRun => i.kind === "agent_run"), [items]);
  const byId = useMemo(() => new Map(runs.map((r) => [r.id, r])), [runs]);
  const agents = useMemo(() => [...new Set(runs.map((r) => r.agent_label))].sort(), [runs]);

  // Default the chain view to the newest run until the user picks one.
  const selected = (selectedId !== null ? byId.get(selectedId) : undefined) ?? runs[0] ?? null;

  const visible = useMemo(() => {
    const filtering = agent !== "" || onlyAuto || onlyActions;
    return (items ?? []).filter((i) => {
      if (i.kind !== "agent_run") {
        if (!filtering) return true;
        // Vehicle-feed batches are autonomous input; people and citizens are not.
        return i.kind === "feed" && onlyAuto && agent === "" && !onlyActions;
      }
      if (agent && i.agent_label !== agent) return false;
      if (onlyAuto && !isAutonomous(i)) return false;
      if (onlyActions && !i.steps.some((st) => st.kind === "action")) return false;
      return true;
    });
  }, [items, agent, onlyAuto, onlyActions]);

  const jump = useCallback(
    (id: number) => {
      setSelectedId(id);
      const el = document.getElementById(`run-${id}`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        (el.querySelector("h2") as HTMLElement | null)?.focus?.();
        setHighlightId(id);
        window.setTimeout(() => setHighlightId((h) => (h === id ? null : h)), 2500);
      }
    },
    [],
  );

  return (
    <>
      <h1>Agent Operations</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        Everything the agents do, as it happens, and what started each run. Updates every 2 seconds.
      </p>
      <Counters summary={summary} />

      <div className={s.filters} role="group" aria-label="Filters">
        <label htmlFor="ops-agent">
          Agent
          <select id="ops-agent" value={agent} onChange={(e) => setAgent(e.target.value)}>
            <option value="">All agents</option>
            {agents.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor="ops-auto" className={s.check2}>
          <input id="ops-auto" type="checkbox" checked={onlyAuto} onChange={(e) => setOnlyAuto(e.target.checked)} />
          Only autonomous (nobody clicked)
        </label>
        <label htmlFor="ops-actions" className={s.check2}>
          <input
            id="ops-actions"
            type="checkbox"
            checked={onlyActions}
            onChange={(e) => setOnlyActions(e.target.checked)}
          />
          Only runs that took an action
        </label>
        <button type="button" className={`btn btn-secondary ${s.small}`} aria-pressed={paused} onClick={() => setPaused(!paused)}>
          {paused ? "Resume updates" : "Pause updates"}
        </button>
      </div>

      <ErrorBox error={error} />
      <div className="visually-hidden" aria-live="polite" aria-atomic="true">
        {announce}
      </div>

      <div className={s.layout}>
        <div className={s.timeline}>
          {items && visible.length === 0 ? <p className="notice">No agent activity matches these filters yet.</p> : null}
          {visible.map((i) =>
            i.kind === "agent_run" ? (
              <RunPanel
                key={i.key}
                run={i}
                selected={selected?.id === i.id}
                highlighted={highlightId === i.id}
                animate={fresh.has(i.key)}
                onSelect={setSelectedId}
                onJump={jump}
              />
            ) : (
              <ThinRow key={i.key} item={i} animate={fresh.has(i.key)} />
            ),
          )}
        </div>
        <ChainView run={selected} byId={byId} runs={runs} onJump={jump} />
      </div>
    </>
  );
}
