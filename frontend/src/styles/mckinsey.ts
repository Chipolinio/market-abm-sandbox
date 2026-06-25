/** Shared McKinsey-style utility classes for the trading terminal. */
export const MCK_BUTTON =
  "border border-border bg-white px-3 py-1.5 text-sm text-accent hover:bg-slate-50 disabled:opacity-50";

export const MCK_BUTTON_MD = `${MCK_BUTTON} py-2`;

/** Primary shock CTA when simulation is RUNNING (no bg-white — avoids Tailwind clash). */
export const MCK_BUTTON_SHOCK_ACCENT =
  "border border-red-900 bg-red-800 px-3 py-2 text-sm font-medium text-white hover:bg-red-900 disabled:cursor-not-allowed disabled:bg-red-800/70 disabled:text-white/90";

export const MCK_SECTION_TITLE = "text-xs uppercase tracking-wide text-muted";
