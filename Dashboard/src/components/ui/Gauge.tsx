import { toneVar, type Tone } from "../../lib/status";

interface GaugeProps {
  value: number | null | undefined;
  max?: number;
  label: string;
  unit?: string;
  tone?: Tone;
  size?: number;
}

/** Mostrador de instrumento (arco 270°) — leitura analógica de um valor. */
export function Gauge({ value, max = 100, label, unit, tone = "cyan", size = 132 }: GaugeProps) {
  const v = value ?? 0;
  const frac = max > 0 ? Math.max(0, Math.min(1, v / max)) : 0;
  const cx = 64;
  const cy = 64;
  const r = 52;
  const C = 2 * Math.PI * r;
  const arc = 0.75; // 270°
  const track = arc * C;
  const color = toneVar[tone];

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
      <svg viewBox="0 0 128 128" width={size} height={size} role="img" aria-label={`${label}: ${value ?? "—"}${unit ?? ""}`}>
        <g transform="rotate(135 64 64)">
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke="var(--graphite-700)"
            strokeWidth={9}
            strokeLinecap="round"
            strokeDasharray={`${track} ${C}`}
          />
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={9}
            strokeLinecap="round"
            strokeDasharray={`${frac * track} ${C}`}
            style={{ transition: "stroke-dasharray 0.4s var(--ease)" }}
          />
        </g>
        <text
          x="64"
          y="60"
          textAnchor="middle"
          fontFamily="var(--font-mono)"
          fontSize="22"
          fontWeight="500"
          fill="var(--text-hi)"
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          {value == null ? "—" : Math.round(v)}
        </text>
        {unit && (
          <text x="64" y="78" textAnchor="middle" fontFamily="var(--font-mono)" fontSize="10" fill="var(--text-lo)">
            {unit}
          </text>
        )}
      </svg>
      <span
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "var(--fs-label)",
          letterSpacing: "var(--track-mid)",
          textTransform: "uppercase",
          color: "var(--text-lo)",
        }}
      >
        {label}
      </span>
    </div>
  );
}
