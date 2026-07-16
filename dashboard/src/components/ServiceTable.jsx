const usd = (n) =>
  "$" +
  Number(n).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

export default function ServiceTable({ data }) {
  const maxRevenue = data.length ? Math.max(...data.map((r) => Number(r.revenue))) : 1;

  return (
    <table className="svc-table">
      <thead>
        <tr>
          <th>Service</th>
          <th className="col-right">Revenue</th>
          <th className="col-right">Jobs</th>
          <th className="col-right">Avg ticket</th>
        </tr>
      </thead>
      <tbody>
        {data.map((row) => (
          <tr key={row.service_description}>
            <td>
              <div className="svc-cell">
                <span className="svc-bar">
                  <span
                    className="svc-bar-fill"
                    style={{
                      width: `${((Number(row.revenue) / maxRevenue) * 100).toFixed(0)}%`,
                    }}
                  />
                </span>
                <span className="svc-name">{row.service_description}</span>
              </div>
            </td>
            <td className="col-right col-money">{usd(row.revenue)}</td>
            <td className="col-right col-dim">{row.transactions}</td>
            <td className="col-right col-dim">{usd(row.avg_ticket)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
