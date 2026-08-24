import React, { useState, useEffect, useRef, useCallback } from 'react';
import { API_BASE } from './config';

export default function App() {
  // Global Metadata & Quality
  const [meta, setMeta] = useState(null);
  const [quality, setQuality] = useState(null);
  const [streams, setStreams] = useState([]);
  
  // Slider Controls
  const [thresholdYears, setThresholdYears] = useState(3);
  const [horizonMonths, setHorizonMonths] = useState(12);
  const [throughputMult, setThroughputMult] = useState(1.0);
  const [reserved, setReserved] = useState(0);

  // Optimization & Override State
  const [plan, setPlan] = useState(null);
  const [overrides, setOverrides] = useState({});
  const [overrideNotice, setOverrideNotice] = useState(null);

  // UI Status
  const [loading, setLoading] = useState(true);
  const [optimizing, setOptimizing] = useState(false);
  const [error, setError] = useState(null);
  const [showExclusions, setShowExclusions] = useState(false);

  // Initial Boot Fetch (/meta & /quality)
  const fetchInitialData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [metaRes, qualRes] = await Promise.all([
        fetch(`${API_BASE}/meta`),
        fetch(`${API_BASE}/quality`)
      ]);

      if (!metaRes.ok || !qualRes.ok) {
        throw new Error(`API Connection Failed: Server returned status ${metaRes.status}`);
      }

      const metaData = await metaRes.json();
      const qualData = await qualRes.json();

      setMeta(metaData);
      setQuality(qualData);
    } catch (err) {
      console.error(err);
      setError(`Backend API unavailable at ${API_BASE}. Please ensure the server is running.`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInitialData();
  }, []);

  // Debounced /streams fetch when controls change
  const fetchStreams = useCallback(async (tYears, hMonths) => {
    setError(null);
    try {
      const tDays = tYears * 365;
      const hDays = Math.round(hMonths * 30.416);

      const res = await fetch(`${API_BASE}/streams?threshold_days=${tDays}&horizon_days=${hDays}`);
      if (!res.ok) {
        throw new Error(`Streams fetch failed with HTTP ${res.status}`);
      }
      const data = await res.json();
      setStreams(data.streams || []);
    } catch (err) {
      console.error(err);
      setError(`Failed to fetch stream data from API: ${err.message}`);
    }
  }, []);

  // Debounce handling (300ms)
  const debounceTimer = useRef(null);
  useEffect(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    
    debounceTimer.current = setTimeout(() => {
      fetchStreams(thresholdYears, horizonMonths);
    }, 300);

    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, [thresholdYears, horizonMonths, fetchStreams]);

  // Derived Values
  const defaultTp = meta ? meta.default_throughput : 405278;
  const currentTp = Math.round(defaultTp * throughputMult);
  const totalInventory = meta ? meta.n_cases : (streams.reduce((acc, s) => acc + s.n, 0));
  
  // Baseline Projected Crossings
  const baselineCrossings = Math.round(
    streams.reduce((acc, s) => acc + (s.projected_crossings || (s.n * (s.p || 0))), 0)
  );

  // Optimised Crossings & Delta
  let optimisedCrossings = null;
  let delta = null;

  if (plan && plan.after) {
    optimisedCrossings = plan.after.crossings;
    
    // Apply local override adjustments if user edited targets
    if (Object.keys(overrides).length > 0) {
      let adjCrossings = 0;
      streams.forEach(s => {
        const target = overrides[s.id] !== undefined ? overrides[s.id] : (plan.allocation[s.id] || 0);
        const p = s.p || 0;
        adjCrossings += p * (s.n - target);
      });
      optimisedCrossings = Math.round(adjCrossings);
    }
    
    delta = optimisedCrossings - baselineCrossings;
  }

  // Handle Generate Plan
  const handleGeneratePlan = async () => {
    setOptimizing(true);
    setError(null);
    setOverrideNotice(null);
    setOverrides({});

    try {
      const tDays = thresholdYears * 365;
      const hDays = Math.round(horizonMonths * 30.416);

      const res = await fetch(`${API_BASE}/optimize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          throughput: currentTp,
          reserved: Number(reserved),
          threshold_days: tDays,
          horizon_days: hDays
        })
      });

      if (!res.ok) {
        throw new Error(`Optimization failed with status ${res.status}`);
      }

      const planData = await res.json();
      setPlan(planData);
    } catch (err) {
      console.error(err);
      setError(`Optimization request failed: ${err.message}`);
    } finally {
      setOptimizing(false);
    }
  };

  // Handle Override Target Change
  const handleOverrideChange = async (streamId, newVal) => {
    const parsedVal = Math.max(0, parseInt(newVal, 10) || 0);
    const newOverrides = { ...overrides, [streamId]: parsedVal };
    setOverrides(newOverrides);

    // Call POST /override
    try {
      const tDays = thresholdYears * 365;
      const hDays = Math.round(horizonMonths * 30.416);

      const res = await fetch(`${API_BASE}/override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          throughput: currentTp,
          reserved: Number(reserved),
          threshold_days: tDays,
          horizon_days: hDays,
          locked: newOverrides
        })
      });

      if (!res.ok) {
        setOverrideNotice(`Override update status: HTTP ${res.status}`);
      } else {
        const data = await res.json();

        if (!data.feasible) {
          setOverrideNotice(data.reason || "This combination of locked targets cannot be met.");
        } else {
          const before = Math.round(data.before.crossings);
          const after = Math.round(data.after.crossings);
          const delta = Math.round(data.delta);
          const deltaStr = `${delta > 0 ? '+' : ''}${delta}`;

          const parts = [`Projected crossings: ${before} -> ${after} (${deltaStr})`];

          if (data.affected_streams && data.affected_streams.length > 0) {
            parts.push(`Affected streams: ${data.affected_streams.join(', ')}`);
          }

          const constraintNotes = [...(data.violations || []), ...(data.relaxed_constraints || [])];
          parts.push(constraintNotes.length > 0
            ? `Constraints: ${constraintNotes.join('; ')}`
            : 'Constraints: OK');

          setOverrideNotice(parts.join(' | '));
        }
      }
    } catch (err) {
      setOverrideNotice("Override local adjustment applied.");
    }
  };

  return (
    <div className="app-container">
      {/* 1. HEADER */}
      <header className="app-header">
        <div className="header-left">
          <h1 className="brand-title">JudgeMyWay</h1>
          <span className="header-meta">
            {meta ? `${meta.district} · Data Period: ${meta.period}` : 'District Court Administration Console'}
          </span>
        </div>
        <div>
          <span className="badge-amber">RETROSPECTIVE SIMULATION</span>
        </div>
      </header>

      {/* ERROR BANNER IF DEGRADED */}
      {error && (
        <div className="error-banner">
          <div>
            <strong>System Notice:</strong> {error}
          </div>
          <button className="error-retry-btn" onClick={fetchInitialData}>Retry Connection</button>
        </div>
      )}

      {/* 2. CONTROLS ROW */}
      <section className="controls-card">
        <div className="control-group">
          <div className="control-label">
            <span>Ageing Threshold</span>
            <span className="control-val">{thresholdYears} Years</span>
          </div>
          <input
            type="range"
            min="1"
            max="10"
            step="1"
            value={thresholdYears}
            onChange={(e) => setThresholdYears(Number(e.target.value))}
            className="slider-input"
          />
        </div>

        <div className="control-group">
          <div className="control-label">
            <span>Planning Horizon</span>
            <span className="control-val">{horizonMonths} Months</span>
          </div>
          <input
            type="range"
            min="3"
            max="24"
            step="1"
            value={horizonMonths}
            onChange={(e) => setHorizonMonths(Number(e.target.value))}
            className="slider-input"
          />
        </div>

        <div className="control-group">
          <div className="control-label">
            <span>Throughput Capacity</span>
            <span className="control-val">{throughputMult.toFixed(1)}x ({currentTp.toLocaleString()})</span>
          </div>
          <input
            type="range"
            min="0.5"
            max="1.5"
            step="0.1"
            value={throughputMult}
            onChange={(e) => setThroughputMult(Number(e.target.value))}
            className="slider-input"
          />
        </div>

        <div className="control-group">
          <div className="control-label">
            <span>Reserved Priority</span>
            <span className="control-val">{Number(reserved).toLocaleString()} Cases</span>
          </div>
          <input
            type="number"
            min="0"
            max={currentTp}
            value={reserved}
            onChange={(e) => setReserved(Math.max(0, parseInt(e.target.value, 10) || 0))}
            className="number-input"
          />
        </div>
      </section>

      {/* 3. SUMMARY ROW */}
      <section className="summary-grid">
        <div className="stat-card">
          <span className="stat-title">Pending Inventory</span>
          <span className="stat-value">{loading ? '...' : totalInventory.toLocaleString()}</span>
          <span className="stat-subtext">Retrospective docket cases</span>
        </div>

        <div className="stat-card">
          <span className="stat-title">Projected Crossings (Baseline)</span>
          <span className="stat-value">{loading ? '...' : baselineCrossings.toLocaleString()}</span>
          <span className="stat-subtext">At current velocity</span>
        </div>

        <div className="stat-card highlight">
          <span className="stat-title">Projected Crossings (Optimised)</span>
          <span className="stat-value">
            {optimizing ? 'Calculating...' : (optimisedCrossings !== null ? optimisedCrossings.toLocaleString() : '—')}
          </span>
          <span className="stat-subtext">Under CP-SAT target allocation</span>
        </div>

        <div className="stat-card">
          <span className="stat-title">Delta Crossings</span>
          <span className={`stat-value ${delta !== null ? (delta <= 0 ? 'delta-negative' : 'delta-positive') : ''}`}>
            {delta !== null ? `${delta > 0 ? '+' : ''}${delta.toLocaleString()}` : '—'}
          </span>
          <span className="stat-subtext">{delta !== null && delta <= 0 ? 'Reduction in ageing cases' : 'Impact comparison'}</span>
        </div>
      </section>

      {/* ACTION BAR & NOTICES */}
      <div className="action-bar">
        <button 
          className="btn-primary" 
          onClick={handleGeneratePlan}
          disabled={loading || optimizing}
        >
          {optimizing ? 'Optimizing Allocation...' : 'GENERATE PLAN'}
        </button>

        {plan && plan.relaxed_constraints && plan.relaxed_constraints.length > 0 && (
          <div className="notice-amber" style={{ margin: 0, padding: '6px 14px' }}>
            <span className="notice-title">Solver Relaxation: </span>
            {plan.relaxed_constraints.join('; ')}
          </div>
        )}
      </div>

      {overrideNotice && (
        <div className="notice-amber">
          <strong>Override Status:</strong> {overrideNotice}
        </div>
      )}

      {/* 4. STREAM TABLE & OVERRIDE PANEL */}
      <section className="table-container">
        <table className="stream-table">
          <thead>
            <tr>
              <th>Stream (Category × Age)</th>
              <th className="num-col">Inventory</th>
              <th className="num-col">Ageing Risk (p)</th>
              <th>Confidence</th>
              <th className="num-col">Hist Share</th>
              <th className="num-col">Baseline Target</th>
              <th className="num-col">Recommended Target</th>
              <th className="num-col">Change</th>
            </tr>
          </thead>
          <tbody>
            {streams.length === 0 ? (
              <tr>
                <td colSpan="8" style={{ textAlign: 'center', padding: '24px', color: 'var(--color-ink-muted)' }}>
                  {loading ? 'Loading stream data from survival engine...' : 'No stream metrics available.'}
                </td>
              </tr>
            ) : (
              streams.slice(0, 50).map((s) => {
                const pPct = s.p !== null && s.p !== undefined ? (s.p * 100).toFixed(1) : '—';
                const pLoPct = s.p_lo !== null && s.p_lo !== undefined ? (s.p_lo * 100).toFixed(1) : null;
                const pHiPct = s.p_hi !== null && s.p_hi !== undefined ? (s.p_hi * 100).toFixed(1) : null;
                const ciStr = pLoPct !== null && pHiPct !== null ? ` [${pLoPct}%–${pHiPct}%]` : '';

                // Target calculations
                const baselineTarget = plan && plan.baseline ? Math.round(plan.baseline[s.id] || 0) : '—';
                const optTarget = plan && plan.allocation ? plan.allocation[s.id] : undefined;
                const currentTarget = overrides[s.id] !== undefined ? overrides[s.id] : optTarget;

                let changeStr = '—';
                let changeClass = 'change-tag';
                if (currentTarget !== undefined && baselineTarget !== '—') {
                  const diff = currentTarget - baselineTarget;
                  changeStr = `${diff >= 0 ? '+' : ''}${diff}`;
                  changeClass = `change-tag ${diff >= 0 ? 'pos' : 'neg'}`;
                }

                return (
                  <tr key={s.id}>
                    <td>
                      {s.low_confidence && (
                        <span 
                          className="dot-amber" 
                          data-tooltip={`Stratum resolution: ${s.stratum_level}`} 
                        />
                      )}
                      <strong>{s.case_type}</strong> · <span style={{ color: 'var(--color-ink-muted)' }}>{s.age_band}</span>
                    </td>
                    <td className="num-col">{s.n.toLocaleString()}</td>
                    <td className="num-col">
                      <strong>{pPct !== '—' ? `${pPct}%` : '—'}</strong>
                      <span style={{ fontSize: '10px', color: 'var(--color-ink-muted)' }}>{ciStr}</span>
                    </td>
                    <td>
                      {s.low_confidence ? (
                        <span className="badge-low-conf" data-tooltip={`Resolved at ${s.stratum_level}`}>
                          Low Conf
                        </span>
                      ) : (
                        <span className="badge-high-conf">Primary</span>
                      )}
                    </td>
                    <td className="num-col">{(s.historical_share * 100).toFixed(1)}%</td>
                    <td className="num-col">{baselineTarget.toLocaleString()}</td>
                    <td className="num-col">
                      {plan ? (
                        <input
                          type="number"
                          className="target-input"
                          value={currentTarget !== undefined ? currentTarget : ''}
                          onChange={(e) => handleOverrideChange(s.id, e.target.value)}
                        />
                      ) : (
                        <span>—</span>
                      )}
                    </td>
                    <td className="num-col">
                      <span className={changeClass}>{changeStr}</span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </section>

      {/* 7. DATA QUALITY STRIP */}
      {quality && (
        <section className="quality-strip">
          <div className="quality-header" onClick={() => setShowExclusions(!showExclusions)}>
            <div className="quality-metrics">
              <div className="quality-metric-item">
                <span className="quality-metric-label">Records Loaded:</span>
                <span className="quality-metric-val">{quality.records_loaded.toLocaleString()}</span>
              </div>
              <div className="quality-metric-item">
                <span className="quality-metric-label">Excluded:</span>
                <span className="quality-metric-val">{quality.records_excluded.toLocaleString()}</span>
              </div>
              <div className="quality-metric-item">
                <span className="quality-metric-label">Censored:</span>
                <span className="quality-metric-val">{quality.records_censored.toLocaleString()}</span>
              </div>
              <div className="quality-metric-item">
                <span className="quality-metric-label">Low-Confidence Streams:</span>
                <span className="quality-metric-val">{quality.low_confidence_streams}</span>
              </div>
            </div>
            <span className="toggle-link">
              {showExclusions ? 'Hide Exclusion Audit ▲' : 'View Exclusion Audit ▼'}
            </span>
          </div>

          {showExclusions && quality.exclusions && (
            <div className="exclusions-drawer">
              {Object.entries(quality.exclusions).map(([reason, count]) => (
                <div key={reason} className="exclusion-item">
                  <span style={{ textTransform: 'capitalize' }}>{reason.replace('_', ' ')}:</span>
                  <strong>{count.toLocaleString()}</strong>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* 8. FOOTER */}
      <footer className="app-footer">
        JudgeMyWay recommends disposal composition across case categories. It never ranks individual cases. Listing remains with the registrar.
      </footer>
    </div>
  );
}
