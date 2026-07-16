import { useEffect, useState } from "react";
import "./styles/tokens.css";
import "./styles/dashboard.css";
import HeroPanel from "./components/HeroPanel.jsx";
import KpiCards from "./components/KpiCards.jsx";
import FunnelChart from "./components/FunnelChart.jsx";
import RevenueChart from "./components/RevenueChart.jsx";
import ServiceTable from "./components/ServiceTable.jsx";
import ThemeToggle, {
  getInitialTheme,
  applyTheme,
} from "./components/ThemeToggle.jsx";

const API = "/api";

export default function App() {
  const [theme, setTheme] = useState(getInitialTheme);
  const [summary, setSummary] = useState(null);
  const [funnel, setFunnel] = useState([]);
  const [revenue, setRevenue] = useState([]);
  const [services, setServices] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  useEffect(() => {
    Promise.all([
      fetch(`${API}/call-funnel/summary`).then((r) => r.json()),
      fetch(`${API}/call-funnel`).then((r) => r.json()),
      fetch(`${API}/revenue`).then((r) => r.json()),
      fetch(`${API}/revenue/by-service`).then((r) => r.json()),
    ])
      .then(([s, f, r, sv]) => {
        setSummary(s[0]);
        setFunnel(f);
        setRevenue(r);
        setServices(sv);
      })
      .catch((e) => setError(e.message));
  }, []);

  function toggleTheme() {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }

  if (error) return <div className="state-msg error">API error: {error}</div>;
  if (!summary) return <div className="state-msg">Loading dashboard...</div>;

  return (
    <div className="wrap">
      <div className="top-bar">
        <div className="brand">
          <div className="brand-logo">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="#fff"
              strokeWidth="2.3"
              strokeLinecap="round"
            >
              <path d="M4 15l4-5 4 3 4-7 4 5" />
            </svg>
          </div>
          <div>
            <span className="brand-name">Reckon</span>{" "}
            <span className="brand-sub">Business intelligence</span>
          </div>
        </div>
        <ThemeToggle theme={theme} onToggle={toggleTheme} />
      </div>

      <div className="bento">
        <HeroPanel summary={summary} revenue={revenue} />
        <KpiCards summary={summary} />

        <div className="box wide">
          <div className="box-header">
            <h3 className="box-title">Call funnel</h3>
            <span className="box-note">daily</span>
          </div>
          <FunnelChart data={funnel} />
        </div>

        <div className="box wide">
          <div className="box-header">
            <h3 className="box-title">Revenue trend</h3>
            <span className="box-note">daily</span>
          </div>
          <RevenueChart data={revenue} />
        </div>

        <div className="box full">
          <div className="box-header">
            <h3 className="box-title">Revenue by service</h3>
            <span className="box-note">30 days</span>
          </div>
          <ServiceTable data={services} />
        </div>
      </div>
    </div>
  );
}
