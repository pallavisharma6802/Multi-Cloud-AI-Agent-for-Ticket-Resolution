import Link from "next/link";
import { TicketSummary } from "@/lib/api";
export function Status({ status }: { status: string }) {
  const label: Record<string, string> = {
    resolved: "Resolved",
    in_progress: "Needs review",
    open: "Open",
    closed: "Closed",
  };
  return (
    <span
      className={`badge ${status === "resolved" ? "green" : status === "in_progress" ? "amber" : "blue"}`}
    >
      <span
        className="dot"
        style={{ background: "currentColor", width: 4, height: 4 }}
      />
      {label[status] || status.replaceAll("_", " ")}
    </span>
  );
}
export function Priority({ priority }: { priority: string }) {
  return (
    <span
      className={`badge ${priority === "urgent" ? "red" : priority === "high" ? "amber" : ""}`}
    >
      <span style={{ fontSize: 11 }}>
        {priority === "urgent" ? "↑↑" : priority === "high" ? "↑" : "−"}
      </span>
      {priority.charAt(0).toUpperCase() + priority.slice(1)}
    </span>
  );
}
export default function TicketTable({
  tickets,
  loading = false,
}: {
  tickets: TicketSummary[];
  loading?: boolean;
}) {
  return (
    <div className="table-scroll">
      <table className="tickets-table">
        <thead>
          <tr>
            <th>SUBJECT</th>
            <th>REQUESTER</th>
            <th>PRIORITY</th>
            <th>STATUS</th>
            <th>CREATED</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={t.ticket_id}>
              <td>
                <Link
                  className="ticket-subject"
                  href={`/tickets/${t.ticket_id}`}
                >
                  {t.title}
                </Link>
                <span className="ticket-id">
                  {t.ticket_id} ·{" "}
                  {t.intent?.replaceAll("_", " ") || "Awaiting classification"}
                </span>
              </td>
              <td>
                <div className="requester">
                  <span className="mini-avatar">
                    {t.user_email.slice(0, 2).toUpperCase()}
                  </span>
                  <span>{t.user_email.split("@")[0]}</span>
                </div>
              </td>
              <td>
                <Priority priority={t.priority} />
              </td>
              <td>
                <Status status={t.status} />
              </td>
              <td
                style={{ color: "#929f87", fontSize: 10, whiteSpace: "nowrap" }}
              >
                {new Date(
                  t.created_at +
                    (/Z|[+-]\d\d:\d\d$/.test(t.created_at) ? "" : "Z"),
                ).toLocaleDateString(undefined, {
                  month: "short",
                  day: "numeric",
                })}
              </td>
              <td>
                <Link
                  aria-label={`Open ${t.ticket_id}`}
                  href={`/tickets/${t.ticket_id}`}
                  style={{ color: "#99ab8b" }}
                >
                  ↗
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!tickets.length && (
        <div className="empty-state">
          {loading ? (
            "Loading tickets…"
          ) : (
            <>
              <h3>Your inbox is clear</h3>
              <p>Create a ticket to start building your support history.</p>
              <Link href="/submit" className="btn" style={{ marginTop: 10 }}>
                Create ticket →
              </Link>
            </>
          )}
        </div>
      )}
    </div>
  );
}
