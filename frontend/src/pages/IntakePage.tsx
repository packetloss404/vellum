import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import {
  useIntake,
  useStartIntake,
  useSendIntakeMessage,
} from "../api/hooks";
import { Header } from "../components/layout/Header";
import { IntakeThread } from "../components/intake/IntakeThread";
import { IntakeInput } from "../components/intake/IntakeInput";
import { IntakeStateSummary } from "../components/intake/IntakeStateSummary";
import { useDocumentTitle } from "../utils/useDocumentTitle";

/**
 * IntakePage — the conversational "open a new dossier" flow.
 *
 * Two modes, driven by URL:
 *   - /intake         → blank "What's the problem?" starter.
 *   - /intake/:id     → conversation view (thread + right-rail state).
 *
 * On commit we navigate to /dossiers/{id}. A short (~900ms) pause gives the
 * user time to register the "Dossier open" pill in the right rail before
 * the page switches, so the transition feels intentional rather than abrupt.
 */

const SERVER_ERROR = "I couldn't reach the server.";

export default function IntakePage() {
  useDocumentTitle("Intake · Vellum");
  const { id } = useParams<{ id: string }>();
  return id ? <IntakeConversation id={id} /> : <IntakeStart />;
}

// ---------- /intake (no id) ----------

function IntakeStart() {
  const navigate = useNavigate();
  const startIntake = useStartIntake();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  const trimmed = value.trim();
  const canSubmit = trimmed.length > 0 && !startIntake.isPending;

  async function handleSubmit(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!canSubmit) return;
    setError(null);
    try {
      const res = await startIntake.mutateAsync(trimmed);
      // onSuccess on the mutation seeds the intake cache with res.intake
      // (which already contains the first assistant reply), so the
      // /intake/:id view can render immediately without a refetch.
      navigate(`/intake/${res.intake.id}`);
    } catch {
      setError(SERVER_ERROR);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Cmd/Ctrl+Enter submits from the opener too — matches the composer
    // behavior on the conversation view so muscle memory carries over.
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      void handleSubmit();
    }
  }

  return (
    <div className="min-h-screen bg-paper">
      <Header />
      <main className="mx-auto max-w-narrow px-6 py-16">
        <h1 className="font-serif text-3xl text-ink tracking-tight">
          Open a dossier
        </h1>
        <p className="mt-2 font-serif text-ink-muted">
          Tell Vellum what problem you want to open a dossier on. A sentence
          or two is enough — the intake assistant will ask follow-ups.
        </p>

        <form onSubmit={handleSubmit} className="mt-8">
          <textarea
            autoFocus
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={6}
            placeholder="What's the problem?"
            className="w-full resize-none font-serif text-base bg-surface border border-rule focus:border-accent focus:outline-none rounded px-4 py-3 text-ink placeholder:text-ink-faint"
          />

          {error ? (
            <div className="mt-3 flex items-center gap-3">
              <div className="text-sm font-serif italic text-attention">
                {error}
              </div>
              <button
                type="button"
                onClick={() => void handleSubmit()}
                className="text-sm font-sans text-accent hover:text-accent-hover underline"
              >
                Retry
              </button>
            </div>
          ) : null}

          <div className="mt-4 flex items-center gap-4">
            <button
              type="submit"
              disabled={!canSubmit}
              className="bg-accent text-paper font-sans text-sm rounded px-4 py-2 hover:bg-accent-hover disabled:opacity-50"
            >
              {startIntake.isPending ? "Starting…" : "Start intake"}
            </button>
            <Link
              to="/"
              className="font-sans text-sm text-ink-faint hover:text-accent"
            >
              Cancel
            </Link>
          </div>
        </form>
      </main>
    </div>
  );
}

// ---------- /intake/:id ----------

function IntakeConversation({ id }: { id: string }) {
  const navigate = useNavigate();
  const query = useIntake(id);
  const { data, isLoading, isError } = query;
  const sendMessage = useSendIntakeMessage();
  const [sendError, setSendError] = useState<string | null>(null);
  // We stash the last user message so a send failure can be replayed via
  // the Retry button without the user having to retype.
  const lastUserMessageRef = useRef<string | null>(null);

  const status = data?.status;
  const dossierId = data?.dossier_id ?? null;

  // Auto-redirect on commit. The pause lets the user register the success
  // state — the "Dossier open" pill in the right rail — before we navigate.
  useEffect(() => {
    if (status === "committed" && dossierId) {
      const t = window.setTimeout(() => {
        navigate(`/dossiers/${dossierId}`);
      }, 900);
      return () => window.clearTimeout(t);
    }
    return undefined;
  }, [status, dossierId, navigate]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-paper">
        <Header />
        <div className="p-12 text-ink-faint font-serif italic">Loading…</div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="min-h-screen bg-paper">
        <Header />
        <div className="mx-auto max-w-narrow px-6 py-16">
          <div className="font-serif italic text-attention">
            {SERVER_ERROR}
          </div>
          <div className="mt-4 flex items-center gap-4">
            <button
              type="button"
              onClick={() => void query.refetch()}
              className="bg-accent text-paper font-sans text-sm rounded px-4 py-2 hover:bg-accent-hover"
            >
              Retry
            </button>
            <Link
              to="/intake"
              className="font-sans text-sm text-ink-faint hover:text-accent"
            >
              Start a new intake
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (data.status === "abandoned") {
    return (
      <div className="min-h-screen bg-paper">
        <Header />
        <div className="mx-auto max-w-narrow px-6 py-16">
          <div className="font-serif text-ink-muted italic">
            This intake was abandoned.
          </div>
          <div className="mt-4">
            <Link
              to="/intake"
              className="font-sans text-sm text-accent hover:text-accent-hover"
            >
              Start a new one →
            </Link>
          </div>
        </div>
      </div>
    );
  }

  async function doSend(text: string) {
    lastUserMessageRef.current = text;
    setSendError(null);
    try {
      const result = await sendMessage.mutateAsync({ intakeId: id, content: text });
      // The backend returns HTTP 200 even when the intake agent itself
      // raised an error mid-turn; surface it rather than silently dropping.
      if (result.error) {
        setSendError(SERVER_ERROR);
      } else {
        lastUserMessageRef.current = null;
      }
    } catch {
      setSendError(SERVER_ERROR);
      // Re-throw so IntakeInput restores the textarea content.
      throw new Error(SERVER_ERROR);
    }
  }

  async function handleSend(text: string) {
    await doSend(text);
  }

  function handleSendRetry() {
    const last = lastUserMessageRef.current;
    if (!last) return;
    void doSend(last);
  }

  // The composer disables while a turn is in flight. We also show the
  // thinking ellipsis in the thread while awaiting the assistant reply.
  const awaitingAssistant = sendMessage.isPending;
  const composerDisabled = awaitingAssistant || data.status !== "gathering";

  return (
    <div className="min-h-screen bg-paper">
      <Header />
      <main className="grid grid-cols-1 md:grid-cols-[1fr_280px] gap-8 max-w-wide mx-auto py-10 px-6">
        <div className="min-w-0 flex flex-col">
          <IntakeThread
            messages={data.messages}
            pending={awaitingAssistant}
          />

          {sendError ? (
            <div className="mt-4 flex items-center gap-3">
              <div className="text-sm font-serif italic text-attention">
                {sendError}
              </div>
              {lastUserMessageRef.current ? (
                <button
                  type="button"
                  onClick={handleSendRetry}
                  disabled={awaitingAssistant}
                  className="text-sm font-sans text-accent hover:text-accent-hover underline disabled:opacity-50"
                >
                  Retry
                </button>
              ) : null}
            </div>
          ) : null}

          <div className="mt-auto pt-6">
            <IntakeInput
              onSend={handleSend}
              disabled={composerDisabled}
              placeholder="Reply…"
            />
          </div>
        </div>

        <IntakeStateSummary
          state={data.state}
          status={data.status}
          dossierId={dossierId}
        />
      </main>
    </div>
  );
}
