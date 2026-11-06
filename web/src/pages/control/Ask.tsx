import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { get, post } from "../../api/client";
import { useConsoleBase } from "../consoleBase";
import s from "./ask.module.css";

/** POST /ask, GET /ask/history */
interface Answer {
  run_id: number | null;
  question: string;
  answer: string;
  points: string[];
  cases: string[];
  sources: string[];
  confidence: number | null;
  how: string | null;
  latency_ms?: number | null;
  steps: { n: number; kind: string; label: string; summary: string }[];
}

const EXAMPLES = [
  "Which ward is worst this week and why?",
  "Why is SR-2026-001257 late?",
  "How many potholes did vehicles find that no citizen reported?",
  "Which crews are overloaded?",
  "How many streetlight complaints are breached in W12?",
  "What does the charter say about reopening a grievance?",
];

const SR = /SR-\d{4}-\d{6}/g;

/** Ask CivicFlow: plain-English questions answered by an agent over the live data. */
export function Ask() {
  const base = useConsoleBase();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [current, setCurrent] = useState<Answer | null>(null);
  const [history, setHistory] = useState<Answer[]>([]);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    document.title = "Ask CivicFlow | CivicFlow";
    get<Answer[]>("/ask/history")
      .then(setHistory)
      .catch(() => undefined);
  }, []);

  async function ask(question: string) {
    const text = question.trim();
    if (text.length < 3) {
      setError("Type a question first.");
      input.current?.focus();
      return;
    }
    setQ(text);
    setBusy(true);
    setError(null);
    setCurrent(null);
    try {
      const a = await post<Answer>("/ask", { question: text });
      setCurrent(a);
      setHistory((h) => [a, ...h.filter((x) => x.run_id !== a.run_id)].slice(0, 5));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not get an answer. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void ask(q);
  };

  /** grievance numbers inside text become links */
  const linkify = (text: string) => {
    const parts = text.split(SR);
    const ids = text.match(SR) ?? [];
    return parts.flatMap((p, i) =>
      i < ids.length
        ? [p, <Link key={i} to={`${base}/complaints/${ids[i]}`}>{ids[i]}</Link>]
        : [p],
    );
  };

  return (
    <>
      <div className={s.hero}>
        <h1 className={s.title}>Ask CivicFlow</h1>
        <p className={s.sub}>
          Ask a question in plain English. An AI agent looks up the live case data and the Citizen Charter, then answers
          with the numbers and the cases behind them.
        </p>
        <form onSubmit={submit} className={s.form}>
          <label htmlFor="ask-q" className="visually-hidden">
            Your question
          </label>
          <input
            id="ask-q"
            ref={input}
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setError(null);
            }}
            placeholder="Which ward is worst this week and why?"
            maxLength={400}
            className={s.input}
            autoComplete="off"
          />
          <button type="submit" className={`btn btn-accent ${s.go}`} disabled={busy}>
            {busy ? "Thinking…" : "Ask"}
          </button>
        </form>
        {error ? (
          <p className={s.error} role="alert">
            {error}
          </p>
        ) : null}
        <div className={s.examples}>
          <span>Try:</span>
          {EXAMPLES.map((e) => (
            <button key={e} type="button" className={s.chip} onClick={() => void ask(e)} disabled={busy}>
              {e}
            </button>
          ))}
        </div>
      </div>

      <div aria-live="polite">
        {busy ? (
          <div className={s.thinking}>
            <span className={s.dots} aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            Looking things up…
          </div>
        ) : null}
        {current ? <AnswerCard a={current} linkify={linkify} base={base} /> : null}
      </div>

      {history.length > 0 ? (
        <section className={s.history}>
          <h2>Recent questions</h2>
          <ul>
            {history.map((h) => (
              <li key={h.run_id ?? h.question}>
                <button type="button" className={s.histBtn} onClick={() => setCurrent(h)}>
                  <strong>{h.question}</strong>
                  <span>{h.answer}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}

function AnswerCard({ a, linkify, base }: { a: Answer; linkify: (t: string) => ReactNode[]; base: string }) {
  const [open, setOpen] = useState(true);
  return (
    <article className={s.card}>
      <p className={s.q}>“{a.question}”</p>
      <p className={s.answer}>{linkify(a.answer)}</p>
      {a.points.length ? (
        <ul className={s.points}>
          {a.points.map((p, i) => (
            <li key={i} style={{ animationDelay: `${i * 70}ms` }}>
              {linkify(p)}
            </li>
          ))}
        </ul>
      ) : null}
      {a.cases.length ? (
        <p className={s.cases}>
          Cases:{" "}
          {a.cases.map((c) => (
            <Link key={c} to={`${base}/complaints/${c}`} className={s.caseChip}>
              {c}
            </Link>
          ))}
        </p>
      ) : null}
      {a.sources.length ? (
        <p className={s.sources}>
          From:{" "}
          {a.sources.map((src) => (
            <span key={src} className={s.srcChip}>
              {src}
            </span>
          ))}
        </p>
      ) : null}

      <div className={s.meta}>
        <span>{a.how}</span>
        {a.confidence !== null ? <span>Confidence {a.confidence.toFixed(2)}</span> : null}
        <button type="button" className={s.toggle} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          {open ? "Hide" : "Show"} how it found this ({a.steps.length} steps)
        </button>
      </div>
      {open ? (
        <ol className={s.steps}>
          {a.steps.map((st) => (
            <li key={st.n} style={{ animationDelay: `${st.n * 120}ms` }}>
              <span className={s.stepLabel}>Looked up {st.label}</span>
              <span>{st.summary}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </article>
  );
}
