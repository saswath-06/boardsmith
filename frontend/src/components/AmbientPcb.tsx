// Ambient PCB trace animation — subtle moving dashes on a wide trace network.
// Sits behind the landing hero. Performant: pure SVG, transform-only animation.
const AmbientPcb = () => {
  const traces = [
    "M 0 80 L 180 80 L 180 140 L 320 140",
    "M 60 0 L 60 200 L 240 200 L 240 320",
    "M 0 260 L 140 260 L 140 380 L 360 380 L 360 480",
    "M 480 0 L 480 100 L 380 100 L 380 220",
    "M 600 60 L 600 180 L 720 180 L 720 100 L 880 100",
    "M 940 0 L 940 140 L 800 140 L 800 280 L 1000 280",
    "M 1080 60 L 1080 200 L 1180 200 L 1180 360",
    "M 1280 0 L 1280 120 L 1380 120 L 1380 260 L 1500 260",
    "M 1100 380 L 1100 460 L 1300 460",
    "M 200 460 L 200 540 L 600 540",
    "M 700 480 L 700 580 L 980 580",
    "M 0 600 L 220 600 L 220 720",
    "M 1280 540 L 1280 660 L 1500 660",
    "M 420 280 L 540 280 L 540 420",
    "M 880 360 L 880 460 L 760 460 L 760 600",
  ];
  const pads: Array<[number, number]> = [
    [180, 80], [320, 140], [60, 200], [240, 320], [140, 260], [360, 380],
    [380, 100], [380, 220], [600, 180], [720, 180], [880, 100], [800, 140],
    [800, 280], [1000, 280], [1080, 200], [1180, 200], [1180, 360], [1380, 120],
    [1380, 260], [1500, 260], [1100, 460], [1300, 460], [200, 540], [600, 540],
    [700, 580], [980, 580], [220, 600], [220, 720], [1280, 660], [540, 280],
    [540, 420], [880, 460], [760, 460], [760, 600],
  ];
  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      viewBox="0 0 1500 800"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      <defs>
        <radialGradient id="bs-fade" cx="50%" cy="50%" r="60%">
          <stop offset="0%" stopColor="#000" stopOpacity="0.0" />
          <stop offset="60%" stopColor="#000" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#000" stopOpacity="0.95" />
        </radialGradient>
        <mask id="bs-mask">
          <rect width="1500" height="800" fill="#fff" />
          <rect width="1500" height="800" fill="url(#bs-fade)" />
        </mask>
      </defs>

      <g mask="url(#bs-mask)" opacity="0.55">
        {/* base traces — dim copper */}
        {traces.map((d, i) => (
          <path key={`t-${i}`} d={d}
            stroke="var(--bs-copper)" strokeWidth="1.2"
            strokeLinecap="square" strokeLinejoin="miter"
            fill="none" opacity="0.35" />
        ))}
        {/* animated overlay — moving dashes give "current flow" */}
        {traces.map((d, i) => (
          <path key={`f-${i}`} d={d}
            stroke="var(--bs-cyan)" strokeWidth="1.2"
            strokeLinecap="butt" fill="none"
            className="bs-trace-flow"
            style={{ animationDelay: `${(i * 0.13) % 1.4}s`, animationDuration: `${1.6 + (i % 4) * 0.3}s`, opacity: 0.45 }} />
        ))}
        {/* pads */}
        {pads.map(([x, y], i) => (
          <g key={`p-${i}`}>
            <circle cx={x} cy={y} r="3.5" fill="var(--bs-gold)" opacity="0.6" />
            <circle cx={x} cy={y} r="1.3" fill="var(--bs-bg)" />
          </g>
        ))}
        {/* a few labeled component outlines for "real PCB" feel */}
        <g stroke="var(--bs-fg-dim)" strokeWidth="1" fill="none" opacity="0.4">
          <rect x="240" y="120" width="80" height="50" rx="2" />
          <rect x="600" y="240" width="120" height="80" rx="2" />
          <rect x="1080" y="80" width="60" height="100" rx="2" />
          <rect x="1380" y="380" width="100" height="60" rx="2" />
        </g>
      </g>
    </svg>
  );
};

export default AmbientPcb;
