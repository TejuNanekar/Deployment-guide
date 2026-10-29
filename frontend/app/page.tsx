"use client";

import { useEffect, useRef, useState } from "react";
import { FormattedAnswer } from "./markdown";

type Choice = { id: string; label: string };

type Step = {
  where: string;
  command: string;
  purpose: string;
  expected: string;
  source_path: string;
  git_ref: string;
  status: string;
  heading: string;
};

type Citation = {
  source_path: string;
  heading: string;
  status: string;
};

type Answer = {
  answer_kind?: string;
  message: string;
  steps: Step[];
  notes: string[];
  citations: Citation[];
};

type ChatReply = {
  reply: string;
  choices: Choice[];
  choice_kind: string | null;
  question: string | null;
  environment: string | null;
  component: string | null;
  answer: Answer | null;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  choices: Choice[];
  choicesUsed: boolean;
  answer: Answer | null;
};

type Pending = {
  question: string | null;
  environment: string | null;
  component: string | null;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const STARTERS = [
  "How do I deploy the Spring Boot API on UAT?",
  "Where does the API live on the server?",
  "How do I check that a UAT deploy worked?",
];

function warningNotes(notes: string[]) {
  return notes.filter((note) => !/language model/i.test(note));
}

export default function HomePage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<Pending>({ question: null, environment: null, component: null });
  const [typing, setTyping] = useState(false);
  const [error, setError] = useState("");
  const threadRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const empty = messages.length === 0 && !typing;

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, typing]);

  useEffect(() => {
    const box = inputRef.current;
    if (!box) return;
    box.style.height = "24px";
    box.style.height = `${Math.min(box.scrollHeight, 140)}px`;
  }, [draft]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || typing) return;
    setDraft("");
    setError("");
    setMessages((current) => [
      ...current.map((item) => ({ ...item, choicesUsed: true })),
      { id: crypto.randomUUID(), role: "user", text: message, choices: [], choicesUsed: true, answer: null },
    ]);
    setTyping(true);
    try {
      const response = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          question: pending.question,
          environment: pending.environment,
          component: pending.component,
        }),
      });
      if (!response.ok) throw new Error(`The assistant returned ${response.status}.`);
      const body = (await response.json()) as ChatReply;
      setPending({
        question: body.question,
        environment: body.environment,
        component: body.component,
      });
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: body.reply,
          choices: body.choices ?? [],
          choicesUsed: false,
          answer: body.answer,
        },
      ]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The request failed.");
    } finally {
      setTyping(false);
      inputRef.current?.focus();
    }
  }

  function reset() {
    setPending({ question: null, environment: null, component: null });
    setDraft("");
    setError("");
    setMessages([]);
    inputRef.current?.focus();
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="mark" aria-hidden="true">
            M
          </span>
          <div>
            <h1>Deployment assistant</h1>
            <p className="eyebrow">Matrimony server</p>
          </div>
        </div>
        <button type="button" className="ghost" onClick={reset}>
          New chat
        </button>
      </header>

      <div className="thread" ref={threadRef}>
        {empty && (
          <div className="hero">
            <h2>How can I help with a deploy?</h2>
            <p>Say the environment and the app if you know them. If not, I’ll ask before I write the steps.</p>
            <div className="starters">
              {STARTERS.map((item) => (
                <button key={item} type="button" className="starter" onClick={() => void send(item)}>
                  {item}
                </button>
              ))}
            </div>
          </div>
        )}
        {!empty &&
          messages.map((message) => {
            const guide = message.answer?.answer_kind === "model";
            return (
              <article key={message.id} className={`turn ${message.role}`}>
                <p className="who">{message.role === "user" ? "You" : "Assistant"}</p>
                <div className={`bubble ${message.role}${guide ? " guide" : ""}`}>
                  {message.answer && warningNotes(message.answer.notes).length > 0 && (
                    <aside className="caution">
                      <p className="caution-title">Check this first</p>
                      <ul>
                        {warningNotes(message.answer.notes).map((note) => (
                          <li key={note}>{note}</li>
                        ))}
                      </ul>
                    </aside>
                  )}
                  {guide ? <FormattedAnswer text={message.text} /> : <p>{message.text}</p>}
                  {message.choices.length > 0 && (
                    <div className="choices">
                      {message.choices.map((choice) => (
                        <button
                          key={choice.id}
                          type="button"
                          className="choice"
                          disabled={message.choicesUsed || typing}
                          onClick={() => void send(choice.label)}
                        >
                          {choice.label}
                        </button>
                      ))}
                    </div>
                  )}
                  {message.answer?.steps.map((step, index) => (
                    <section className="step" key={`${step.source_path}-${index}`}>
                      <h2>{step.heading.startsWith("Step ") ? step.heading : `Step ${index + 1}${step.heading ? `: ${step.heading}` : ""}`}</h2>
                      <p className="meta">Where: {step.where}</p>
                      <pre>{step.command}</pre>
                      <button type="button" className="ghost" onClick={() => navigator.clipboard.writeText(step.command)}>
                        {step.where.includes("Do not paste") ? "Copy checklist" : "Copy command"}
                      </button>
                      <p className="meta">Purpose: {step.purpose}</p>
                      <p className="meta">Expected: {step.expected}</p>
                    </section>
                  ))}
                  {message.answer && message.answer.citations.length > 0 && (
                    <p className="meta sources">
                      Sources:{" "}
                      {message.answer.citations
                        .map((citation) => citation.source_path)
                        .filter((path, index, all) => all.indexOf(path) === index)
                        .join(", ")}
                    </p>
                  )}
                </div>
              </article>
            );
          })}
        {typing && (
          <article className="turn assistant">
            <p className="who">Assistant</p>
            <div className="bubble assistant typing" aria-label="Assistant is replying">
              <span />
              <span />
              <span />
            </div>
          </article>
        )}
      </div>

      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          void send(draft);
        }}
      >
        <textarea
          ref={inputRef}
          value={draft}
          placeholder="Ask a follow-up, or a new deploy question"
          rows={1}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send(draft);
            }
          }}
        />
        <button type="submit" disabled={typing || draft.trim().length === 0} aria-label="Send">
          ↑
        </button>
      </form>
      {error && <p className="error">{error}</p>}
    </main>
  );
}
