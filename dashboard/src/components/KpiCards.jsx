const fmt = (n) => (n != null ? Number(n).toLocaleString() : "-");
const pct = (n) => (n != null ? `${Number(n).toFixed(1)}%` : "-");

export default function KpiCards({ summary }) {
  return (
    <>
      {/* Booking rate - accent */}
      <div className="box stat stat-accent">
        <div className="stat-label">Booking rate</div>
        <div className="stat-value num">{pct(summary.booking_rate_pct)}</div>
        <div className="mbar">
          <span
            className="mbar-fill"
            style={{
              width: `${Math.min(Number(summary.booking_rate_pct) || 0, 100)}%`,
              background: "var(--accent)",
            }}
          />
        </div>
      </div>

      {/* Booked - green */}
      <div className="box stat stat-good">
        <div className="stat-label">Booked jobs</div>
        <div className="stat-value num">{fmt(summary.total_booked)}</div>
        <div className="stat-sub">
          <span className="chip chip-good">
            {pct(summary.booking_rate_pct)} of calls
          </span>
        </div>
      </div>

      {/* Escalated - amber */}
      <div className="box stat stat-warn">
        <div className="stat-label">Escalated</div>
        <div className="stat-value num">{fmt(summary.total_escalated)}</div>
        <div className="stat-sub">
          <span className="chip chip-warn">
            {pct(summary.escalation_rate_pct)} of calls
          </span>
        </div>
      </div>

      {/* Missed - red */}
      <div className="box stat stat-bad">
        <div className="stat-label">Missed</div>
        <div className="stat-value num">{fmt(summary.total_missed)}</div>
        <div className="stat-sub">
          <span className="chip chip-bad">
            {pct(
              summary.total_calls
                ? (100 * summary.total_missed) / summary.total_calls
                : 0
            )}{" "}
            of calls
          </span>
        </div>
      </div>
    </>
  );
}
