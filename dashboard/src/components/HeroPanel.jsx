import DotGrid from "./DotGrid.jsx";

const usd = (n) =>
  "$" + Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });

export default function HeroPanel({ summary, revenue }) {
  const totalRevenue = revenue.reduce(
    (sum, r) => sum + Number(r.revenue || 0),
    0
  );

  return (
    <div className="hero-panel">
      <DotGrid />
      <div className="hero-top">
        <span className="hero-wm">Reckon</span>
        <span className="live">
          <span className="live-dot" />
          Live
        </span>
      </div>
      <div>
        <div className="hero-big num">{usd(totalRevenue)}</div>
        <div className="hero-cap">Revenue, last 30 days</div>
      </div>
      <div className="hero-mini">
        <div>
          <b className="num">{Number(summary.total_calls).toLocaleString()}</b>
          calls
        </div>
        <div>
          <b className="num">
            {Number(summary.total_booked).toLocaleString()}
          </b>
          booked
        </div>
        <div>
          <b className="num">
            {Number(summary.total_completed || 0).toLocaleString()}
          </b>
          completed
        </div>
        <div>
          <b className="num">{summary.avg_sentiment}</b>sentiment
        </div>
      </div>
    </div>
  );
}
