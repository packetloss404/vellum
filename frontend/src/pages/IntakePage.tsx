import React, { useEffect, useState } from "react";
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
 * On commit, we wait ~1s so the user registers the "Dossier open" success
 * state before we shove them into /dossiers/{id}. Long enough to feel
 * intentional; short enough that it doesn't feel like a bug.
 */
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

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setError(null);
    try {
      const res = await startIntake.mutateAsync(trimmed);
      // NOTE on `first_reply`: the server returns the assistant's first
      // reply alongside the new IntakeSession. The start mutation's
      // onSuccess seeds the intake cache with `res.intake`, and that
      // session already contains all messages (including the assistant
      // reply). So we don't need to forward first_reply separately —
      // the /intake/:id view reads the cached session and renders it.
      navigate(`/intake/${res.intake.id}`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Couldn't start intake.",
      );
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
            rows={6}
            placeholder="What's the problem?"
            className="w-full resize-none font-serif text-base bg-surface border border-rule focus:border-accent focus:outline-none rounded px-4 py-3 text-ink placeholder:text-ink-faint"
          />

          {error ? (
            <div className="mt-3 text-sm font-mono text-attention">
              {error}
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
  const { data, isLoading, isError, error } = useIntake(id);
  const sendMessage = useSendIntakeMessage();
  const [sendError, setSendError] = useState<string | null>(null);

  const status = data?.status;
  const dossierId = data?.dossier_id ?? null;

  // Auto-redirect on commit. 1s pause lets the user register the success
  // state — the "Dossier open" pill appears in the right rail — before we
  // navigate. Short enough that it feels like a transition, not a wait.
  useEffect(() => {
    if (status === "committed" && dossierId) {
      const t = window.setTimeout(() => {
        navigate(`/dossiers/${dossierId}`);
      }, 1000);
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
          <div className="font-serif text-ink-muted">
            Couldn't load this intake.{" "}
            {error instanceof Error ? error.message : ""}
          </div>
          <div className="mt-4">
            <Link
              to="/intake"
              className="font-sans text-sm text-accent hover:text-accent-hover"
            >
              Start a new intake →
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

  async function handleSend(text: string) {
    setSendError(null);
    try {
      const result = await sendMessage.mutateAsync({ intakeId: id, content: text });
      // The backend returns HTTP 200 even when the intake agent itself
      // raised an error mid-turn; surface it rather than silently dropping.
      if (result.error) {
        setSendError(result.error);
      }
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Couldn't send that message.";
      setSendError(msg);
      // Re-throw so IntakeInput restores the textarea content.
      throw err;
    }
  }

  return (
    <div className="min-h-screen bg-paper">
      <Header />
      <main className="grid grid-cols-1 md:grid-cols-[1fr_280px] gap-8 max-w-wide mx-auto py-10 px-6">
        <div className="min-w-0 flex flex-col">
          <IntakeThread messages={data.messages} />

          {sendError ? (
            <div className="mt-4 text-sm font-mono text-attention">
              {sendError}
            </div>
          ) : null}

          <div className="mt-auto pt-6">
            <IntakeInput
              onSend={handleSend}
              disabled={sendMessage.isPending || data.status !== "gathering"}
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
