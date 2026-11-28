import React, { useMemo } from 'react';
import { PieChart as PieIcon, BarChart3, TrendingUp, Users } from 'lucide-react';

const PALETTE = [
  '#10b981', // emerald
  '#8b5cf6', // violet
  '#f59e0b', // amber
  '#06b6d4', // cyan
  '#ec4899', // pink
  '#3b82f6', // blue
  '#f97316', // orange
  '#14b8a6', // teal
];

function formatINR(val) {
  return `₹${Number(val || 0).toLocaleString('en-IN', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })}`;
}

export default function FinanceCharts({ monthlyReport }) {
  const categoryData = useMemo(() => {
    const raw = monthlyReport?.category_breakdown || [];
    const total = raw.reduce((acc, c) => acc + Number(c.total || c.amount || 0), 0);
    return raw.map((c, idx) => {
      const value = Number(c.total || c.amount || 0);
      return {
        label: c.name || c.category || 'General',
        value,
        pct: total > 0 ? (value / total) * 100 : 0,
        color: PALETTE[idx % PALETTE.length],
      };
    });
  }, [monthlyReport]);

  const projectData = useMemo(() => {
    const raw = monthlyReport?.project_breakdown || [];
    const maxVal = Math.max(...raw.map((p) => Number(p.total || p.amount || 0)), 1);
    return raw.slice(0, 8).map((p, idx) => {
      const value = Number(p.total || p.amount || 0);
      return {
        label: p.name || p.project || 'General',
        value,
        widthPct: Math.max(4, (value / maxVal) * 100),
        color: PALETTE[idx % PALETTE.length],
      };
    });
  }, [monthlyReport]);

  const dailyMovement = useMemo(() => {
    const raw = monthlyReport?.daily_movement || [];
    const maxVal = Math.max(
      ...raw.map((d) => Math.max(Number(d.payments || 0), Number(d.receipts || 0))),
      1
    );
    return raw.slice(-14).map((d) => ({
      date: (d.date || '').slice(5),
      payments: Number(d.payments || 0),
      receipts: Number(d.receipts || 0),
      payH: Math.max(2, (Number(d.payments || 0) / maxVal) * 100),
      recH: Math.max(2, (Number(d.receipts || 0) / maxVal) * 100),
    }));
  }, [monthlyReport]);

  const spenderData = useMemo(() => {
    const txns = monthlyReport?.transactions || monthlyReport?.posted_entries || [];
    const map = {};
    txns.forEach((t) => {
      const pay = Number(t.payment || 0);
      if (pay > 0) {
        const who = t.requested_by || 'Finance Direct';
        map[who] = (map[who] || 0) + pay;
      }
    });
    const list = Object.entries(map)
      .map(([name, total]) => ({ name, total }))
      .sort((a, b) => b.total - a.total)
      .slice(0, 6);
    const maxVal = Math.max(...list.map((s) => s.total), 1);
    return list.map((s, idx) => ({
      ...s,
      widthPct: Math.max(4, (s.total / maxVal) * 100),
      color: PALETTE[(idx + 2) % PALETTE.length],
    }));
  }, [monthlyReport]);

  // SVG Donut math
  const donutSegments = useMemo(() => {
    const radius = 42;
    const circumference = 2 * Math.PI * radius;
    let offset = 0;
    return categoryData.map((seg) => {
      const dash = (seg.pct / 100) * circumference;
      const item = {
        ...seg,
        dasharray: `${dash} ${circumference - dash}`,
        dashoffset: -offset,
      };
      offset += dash;
      return item;
    });
  }, [categoryData]);

  const totalSpent = categoryData.reduce((a, b) => a + b.value, 0);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* 1. Category Spend Donut Chart */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-2">
            <PieIcon className="w-4 h-4 text-emerald-400" /> Spend by Category
          </h3>
          <span className="text-[11px] font-mono text-slate-400">
            Total: {formatINR(totalSpent)}
          </span>
        </div>
        {categoryData.length === 0 ? (
          <div className="h-44 flex items-center justify-center text-xs text-slate-500">
            No category expenditure data for this period.
          </div>
        ) : (
          <div className="flex flex-col sm:flex-row items-center gap-6">
            <div className="relative w-36 h-36 shrink-0">
              <svg viewBox="0 0 110 110" className="w-full h-full -rotate-90">
                <circle
                  cx="55"
                  cy="55"
                  r="42"
                  fill="none"
                  stroke="#1e293b"
                  strokeWidth="14"
                />
                {donutSegments.map((seg, i) => (
                  <circle
                    key={i}
                    cx="55"
                    cy="55"
                    r="42"
                    fill="none"
                    stroke={seg.color}
                    strokeWidth="14"
                    strokeDasharray={seg.dasharray}
                    strokeDashoffset={seg.dashoffset}
                  />
                ))}
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center text-center pointer-events-none">
                <span className="text-[10px] text-slate-400 uppercase">Spent</span>
                <span className="text-xs font-bold text-slate-100">{formatINR(totalSpent)}</span>
              </div>
            </div>
            <div className="flex-1 w-full space-y-2 max-h-40 overflow-y-auto pr-1">
              {categoryData.map((c, idx) => (
                <div key={idx} className="flex items-center justify-between text-xs gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className="w-2.5 h-2.5 rounded-sm shrink-0"
                      style={{ backgroundColor: c.color }}
                    />
                    <span className="text-slate-300 truncate">{c.label}</span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0 font-mono">
                    <span className="text-slate-400 text-[10px]">{c.pct.toFixed(1)}%</span>
                    <span className="text-slate-100 font-semibold">{formatINR(c.value)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 2. Project Spend Bar Chart */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-purple-400" /> Project Expenditure Breakdown
          </h3>
          <span className="text-[11px] text-slate-400">Top Projects</span>
        </div>
        {projectData.length === 0 ? (
          <div className="h-44 flex items-center justify-center text-xs text-slate-500">
            No project expenditure data for this period.
          </div>
        ) : (
          <div className="space-y-3">
            {projectData.map((p, idx) => (
              <div key={idx} className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-300 truncate max-w-[60%]">{p.label}</span>
                  <span className="font-mono text-slate-100 font-semibold">{formatINR(p.value)}</span>
                </div>
                <div className="w-full h-2.5 bg-slate-950 rounded-full overflow-hidden border border-slate-800/80">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${p.widthPct}%`, backgroundColor: p.color }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 3. Daily Cash Flow (Payments vs Receipts) Bar Chart */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-cyan-400" /> Cash Flow Activity (Recent Days)
          </h3>
          <div className="flex items-center gap-3 text-[10px] text-slate-400">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-xs bg-emerald-500" /> Receipts
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-xs bg-rose-500" /> Payments
            </span>
          </div>
        </div>
        {dailyMovement.length === 0 ? (
          <div className="h-44 flex items-center justify-center text-xs text-slate-500">
            No daily movement recorded in this period.
          </div>
        ) : (
          <div className="h-44 flex items-end gap-2 pt-4 pb-1 border-b border-slate-800">
            {dailyMovement.map((d, idx) => (
              <div key={idx} className="flex-1 flex flex-col items-center gap-1 h-full justify-end group">
                <div className="w-full flex items-end justify-center gap-0.5 h-32">
                  {d.receipts > 0 && (
                    <div
                      title={`Receipt: ${formatINR(d.receipts)}`}
                      className="w-2.5 sm:w-3 bg-emerald-500/90 hover:bg-emerald-400 rounded-t transition-all"
                      style={{ height: `${d.recH}%` }}
                    />
                  )}
                  {d.payments > 0 && (
                    <div
                      title={`Payment: ${formatINR(d.payments)}`}
                      className="w-2.5 sm:w-3 bg-rose-500/90 hover:bg-rose-400 rounded-t transition-all"
                      style={{ height: `${d.payH}%` }}
                    />
                  )}
                </div>
                <span className="text-[9px] font-mono text-slate-500 rotate-0 truncate">
                  {d.date}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 4. Top Spenders / Requesters Breakdown */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-2">
            <Users className="w-4 h-4 text-amber-400" /> Spend by Team Member
          </h3>
          <span className="text-[11px] text-slate-400">Posted Amounts</span>
        </div>
        {spenderData.length === 0 ? (
          <div className="h-44 flex items-center justify-center text-xs text-slate-500">
            No posted team member spend in this period.
          </div>
        ) : (
          <div className="space-y-3">
            {spenderData.map((s, idx) => (
              <div key={idx} className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-300 truncate max-w-[60%] font-medium">{s.name}</span>
                  <span className="font-mono text-slate-100 font-semibold">{formatINR(s.total)}</span>
                </div>
                <div className="w-full h-2.5 bg-slate-950 rounded-full overflow-hidden border border-slate-800/80">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${s.widthPct}%`, backgroundColor: s.color }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
