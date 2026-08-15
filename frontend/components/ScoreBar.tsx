export function ScoreBar({ label, value }: { label: string; value: number }) {
  const tone = value >= 75 ? "good" : value >= 50 ? "warn" : "poor";
  return (
    <div className="score-row">
      <div className="score-label">
        <span>{label}</span>
        <strong>{Math.round(value)}</strong>
      </div>
      <div className="score-track" aria-label={`${label}: ${Math.round(value)} out of 100`}>
        <span className={tone} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </div>
    </div>
  );
}
