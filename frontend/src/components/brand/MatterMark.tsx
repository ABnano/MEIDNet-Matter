/** The Matter mark: latent nodes converging into a crystal cube with the MEIDNet indigo–purple gradient. */
export function MatterMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="MEIDNet Matter">
      <defs><linearGradient id="mm" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#4f46e5" /><stop offset="1" stopColor="#9333ea" /></linearGradient></defs>
      <g stroke="currentColor" strokeOpacity={0.35} strokeWidth={1.6} strokeLinecap="round" fill="none"><path d="M8 14L30 27M8 32L30 32M8 50L30 37M15 23L30 30" /></g>
      <circle cx={8} cy={14} r={3.2} fill="#8b5cf6" /><circle cx={8} cy={32} r={3.2} fill="#3b82f6" /><circle cx={8} cy={50} r={3.2} fill="#14b8a6" /><circle cx={15} cy={23} r={2.2} fill="#8b5cf6" />
      <path d="M44 12L58 20V40L44 48L30 40V20Z" fill="url(#mm)" />
      <path d="M30 20L44 28L58 20M44 28V48" stroke="#fff" strokeOpacity={0.6} strokeWidth={1.4} fill="none" />
      <circle cx={44} cy={34} r={3} fill="#fff" />
    </svg>
  );
}

export function Wordmark({ sub = 'Matter' }: { sub?: string }) {
  return <><b>MEIDNet</b>&nbsp;<span>{sub}</span></>;
}
