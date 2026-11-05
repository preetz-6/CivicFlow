import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { get } from "../../api/client";
import { Breadcrumbs } from "../../frame/Breadcrumbs";
import s from "./agentflow.module.css";

/** GET /public/agent-flow: one case as a chain of boxes, in time order. */
interface Step {
  n: number;
  kind: "lookup" | "rule" | "action";
  label: string;
  summary: string;
}
interface Box {
  key: string;
  kind: "agent" | "person" | "trigger";
  at: string;
  title: string;
  line: string;
  running?: boolean;
  sent_back?: boolean;
  detail?: {
    started_by: string | null;
    how: string | null;
    steps: Step[];
    reasoning: string[];
    guardrails: string[];
    result: string;
  };
}
interface Flow {
  sr_id: string | null;
  found: boolean;
  recent: string[];
  title?: string;
  status?: string;
  boxes: Box[];
}

const time = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export function AgentFlow() {
  const [params] = useSearchParams();
  const initial = (params.get("sr") ?? "").trim().toUpperCase();
  const [follow, setFollow] = useState(!initial);
  const [sr, setSr] = useState(initial);
  const [typed, setTyped] = useState("");
  const [flow, setFlow] = useState<Flow | null>(null);
  const [error, setError] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const seen = useRef<Set<string>>(new Set());
  const lastSr = useRef<string | null>(null);

  useEffect(() => {
    document.title = "How the agents work | CivicFlow";
  }, []);

  useEffect(() => {
    let alive = true;
    const load = () =>
      get<Flow>(`/public/agent-flow${!follow && sr ? `?sr=${encodeURIComponent(sr)}` : ""}`)
        .then((f) => {
          if (!alive) return;
          setError(false);
          setFlow(f);
          if (f.sr_id !== lastSr.current) {
            lastSr.current = f.sr_id;
            seen.current = new Set();
            setSelected(null);
          }
          // open the newest agent box automatically, so the presenter never has to click
          const fresh = f.boxes.filter((b) => !seen.current.has(b.key));
          f.boxes.forEach((b) => seen.current.add(b.key));
          const newestAgent = [...fresh].reverse().find((b) => b.kind === "agent");
          if (newestAgent) setSelected(newestAgent.key);
          else setSelected((cur) => cur ?? [...f.boxes].reverse().find((b) => b.detail)?.key ?? null);
        })
        .catch(() => alive && setError(true));
    load();
    const id = window.setInterval(load, 2000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [follow, sr]);

  const open = (id: string) => {
    setSr(id.trim().toUpperCase());
    setFollow(false);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (typed.trim()) open(typed);
  };

  const box = flow?.boxes.find((b) => b.key === selected);
  const d = box?.detail;

  return (
    <>
      <Breadcrumbs items={[{ label: "How the agents work" }]} />
      <h1>How the agents work</h1>
      <p>
        Every complaint is handled by a chain of AI agents and people. Each box below is one step. Click an agent box to
        see what it looked up, what it decided and what it did.
      </p>

      <div className={s.controls}>
        <label className={s.check}>
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
          Follow the latest case live
        </label>
        <form onSubmit={submit} className={s.find}>
          <label htmlFor="sr-no">Grievance No.</label>
          <input
            id="sr-no"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder="SR-2026-001270"
          />
          <button type="submit">Show</button>
        </form>
      </div>
      {flow && flow.recent.length > 0 ? (
        <p className={s.recent}>
          Recent cases:{" "}
          {flow.recent.map((id) => (
            <button key={id} type="button" className={s.linkBtn} onClick={() => open(id)}>
              {id}
            </button>
          ))}
        </p>
      ) : null}

      {error ? <p className={s.note}>Could not load. Retrying…</p> : null}
      {flow && !flow.found ? (
        <p className={s.note}>{flow.sr_id ? `No case ${flow.sr_id} found.` : "No activity yet. Lodge a grievance to start."}</p>
      ) : null}

      {flow?.found ? (
        <section aria-labelledby="case-h">
          <h2 id="case-h" className={s.caseH}>
            {flow.sr_id}: {flow.title} <span className={s.status}>({flow.status})</span>
          </h2>

          <ol className={s.chain} aria-live="polite">
            {flow.boxes.map((b, i) => (
              <li key={b.key} className={s.item}>
                {i > 0 ? (
                  <span className={s.arrow} aria-hidden="true">
                    →
                  </span>
                ) : null}
                <button
                  type="button"
                  title={b.line}
                  disabled={!b.detail}
                  onClick={() => setSelected(b.key)}
                  aria-pressed={selected === b.key}
                  className={[
                    s.box,
                    s[b.kind],
                    b.sent_back ? s.sentBack : "",
                    b.running ? s.running : "",
                    selected === b.key ? s.selected : "",
                  ].join(" ")}
                >
                  <span className={s.kindTag}>
                    {b.kind === "agent" ? "AI agent" : b.kind === "person" ? "Person" : "Trigger"}
                  </span>
                  <strong>{b.title}</strong>
                  <span className={s.line}>{b.running ? "Working…" : b.line}</span>
                  <span className={s.time}>{time(b.at)}</span>
                </button>
              </li>
            ))}
          </ol>
          <p className={s.legend}>
            Dark box: AI agent. Dashed box: a person. Grey box: what started it on its own (timer, vehicles, weather). Red
            border: the agent sent the work back.
          </p>

          {box && d ? (
            <section className={s.panel} aria-labelledby="detail-h">
              <h3 id="detail-h">
                {box.title} <span className={s.time}>at {time(box.at)}</span>
              </h3>
              <dl className={s.facts}>
                {d.started_by ? (
                  <>
                    <dt>Started by</dt>
                    <dd>{d.started_by}</dd>
                  </>
                ) : null}
                {d.how ? (
                  <>
                    <dt>How it decided</dt>
                    <dd>{d.how}</dd>
                  </>
                ) : null}
              </dl>

              {d.steps.length ? (
                <>
                  <h4>What it did, step by step</h4>
                  <ol className={s.steps}>
                    {d.steps.map((st) => (
                      <li key={st.n} className={st.kind === "action" ? s.action : undefined}>
                        <span className={s.stepLabel}>
                          {st.kind === "rule" ? "Check: " : st.kind === "action" ? "Action: " : "Looked up "}
                          {st.label}
                        </span>{" "}
                        – {st.summary}
                      </li>
                    ))}
                  </ol>
                </>
              ) : null}

              {d.reasoning.length ? (
                <>
                  <h4>Why</h4>
                  <ul>
                    {d.reasoning.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </>
              ) : null}

              {d.guardrails.length ? (
                <div className={s.guard}>
                  <strong>Safety rule applied:</strong>
                  <ul>
                    {d.guardrails.map((g) => (
                      <li key={g}>{g}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <p className={s.result}>
                <strong>Result:</strong> {d.result || "-"}
              </p>
            </section>
          ) : null}
        </section>
      ) : null}
    </>
  );
}
