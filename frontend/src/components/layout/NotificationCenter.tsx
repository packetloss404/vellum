import { Link } from "react-router-dom";
import { useMarkNotificationRead, useNotifications } from "../../api/hooks";

export function NotificationCenter() {
  const notifications = useNotifications();
  const markRead = useMarkNotificationRead();
  const items = notifications.data ?? [];
  return (
    <details className="relative">
      <summary className="cursor-pointer list-none font-sans text-xs uppercase tracking-wide text-ink-faint hover:text-accent">
        Alerts{items.length ? ` (${items.length})` : ""}
      </summary>
      <div className="absolute right-0 z-40 mt-3 w-80 rounded border border-rule-strong bg-surface p-3 shadow-lg">
        {items.length === 0 ? (
          <p className="font-serif text-sm text-ink-faint">No unread research alerts.</p>
        ) : (
          <ul className="space-y-2">
            {items.map((item) => (
              <li key={item.id} className="rounded border border-rule bg-paper p-2">
                <div className="font-mono text-[10px] uppercase tracking-wide text-ink-muted">
                  {item.event_type.replace(/_/g, " ")}
                </div>
                <div className="mt-1 flex items-center justify-between gap-2">
                  <Link
                    to={`/dossiers/${item.dossier_id}`}
                    className="font-serif text-xs text-ink hover:text-accent"
                    onClick={() => markRead.mutate(item.id)}
                  >
                    Open dossier
                  </Link>
                  <button
                    type="button"
                    className="font-mono text-[10px] text-ink-faint hover:text-ink"
                    disabled={markRead.isPending}
                    onClick={() => markRead.mutate(item.id)}
                  >
                    Mark read
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}

