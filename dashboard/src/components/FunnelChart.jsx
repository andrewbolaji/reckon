import {
  BarChart,
  Bar,
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
          <span className="dot" style={{ background: entry.fill }} />
          <span>
            {entry.name}: {entry.value}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function FunnelChart({ data }) {
  const c = useThemeColors();

  const chartData = data.map((d) => ({
    date: d.call_date?.slice(5),
    Booked: d.booked,
    Qualified: d.qualified,
    Escalated: d.escalated,
    Missed: d.missed,
  }));

  return (
    <>
      <ResponsiveContainer width="100%" height={230}>
        <BarChart data={chartData} barCategoryGap="20%">
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
          />
          <Tooltip content={<CustomTooltip />} cursor={false} />
          <Bar dataKey="Booked" stackId="a" fill={c.good} radius={[0, 0, 0, 0]} />
          <Bar dataKey="Qualified" stackId="a" fill={c.accent} />
          <Bar dataKey="Escalated" stackId="a" fill={c.warn} />
          <Bar
            dataKey="Missed"
            stackId="a"
            fill={c.bad}
            radius={[2, 2, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
      <div className="chart-legend">
        <span>
          <i style={{ background: c.good }} />
          Booked
        </span>
        <span>
          <i style={{ background: c.accent }} />
          Qualified
        </span>
        <span>
          <i style={{ background: c.warn }} />
          Escalated
        </span>
        <span>
          <i style={{ background: c.bad }} />
          Missed
        </span>
      </div>
    </>
  );
}
