import { toneVar, type Tone } from "../../lib/status";

/** Sparkline SVG — tendência compacta de uma série. */
export function Sparkline({
  data,
  width = 120,
  height = 32,
  tone = "cyan",
  fill = true,
}: {
  data: number[];
  width?: number;
  height?: number;
  tone?: Tone;
  fill?: boolean;
}) {
  if (data.length < 2) return <svg width={width} height={height} aria-hidden="true" />;
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const span = max - min || 1;
  const stepX = width / (data.length - 1);
  const pts = data.map((d, i) => {
    const x = i * stepX;
    const y = height - 2 - ((d - min) / span) * (height - 4);
    return [x, y] as const;
  });
  const line = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${width},${height} L0,${height} Z`;
  const color = toneVar[tone];
  return (
    <svg width={width} height={height} aria-hidden="true" style={{ display: "block" }}>
      {fill && <path d={area} fill={color} opacity={0.12} />}
      <path d={line} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/** Barra de proporção 24h — sucesso vs falha (codifica resultado). */
export function RatioBar({
  success,
  failures,
  height = 6,
}: {
  success: number;
  failures: number;
  height?: number;
}) {
  const total = success + failures;
  const sPct = total > 0 ? (success / total) * 100 : 0;
  const fPct = total > 0 ? (failures / total) * 100 : 0;
  return (
    <div
      style={{
        display: "flex",
        height,
        borderRadius: 2,
        overflow: "hidden",
        background: "var(--graphite-700)",
      }}
      role="img"
      aria-label={`${success} sucessos, ${failures} falhas`}
    >
      <span style={{ width: `${sPct}%`, background: toneVar.green }} />
      <span style={{ width: `${fPct}%`, background: toneVar.red }} />
    </div>
  );
}
