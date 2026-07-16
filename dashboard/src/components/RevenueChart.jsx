import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import useThemeColors from "../hooks/useThemeColors.js";

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload) return null;
  return (
    <div className="custom-tooltip">
      <div className="label">{label}</div>
      {payload.map((entry) => (
        <div key={entry.dataKey} className="row">
          <span className="dot" style={{ background: entry.stroke }} />
          <span>
            {entry.name}: ${Number(entry.value).toLocaleString()}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function RevenueChart({ data }) {
  const c = useThemeColors();

  const chartData = data.map((d) => ({
    date: d.payment_date?.slice(5),
    Revenue: Number(d.revenue),
  }));

  return (
    <ResponsiveContainer width="100%" height={250}>
      <AreaChart data={chartData}>
        <defs>
          <linearGradient id="revenueGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={c.accent} stopOpacity={0.26} />
            <stop offset="100%" stopColor={c.accent} stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis
          dataKey="date"
          stroke={c.faint}
          fontSize={10}
          tickLine={false}
          axisLine={{ stroke: c.line }}
        />
        <YAxis
          stroke={c.faint}
          fontSize={10}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
        />
        <Tooltip content={<CustomTooltip />} />
        <Area
          type="monotone"
          dataKey="Revenue"
          stroke={c.accent}
          strokeWidth={2.6}
          fill="url(#revenueGrad)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
