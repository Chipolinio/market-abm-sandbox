import {
  collapseCyberLogLines,
  formatCyberLine,
  severityClass,
  type CyberLogLine,
} from "@/state/cyberLog";

type Props = {
  lines: CyberLogLine[];
};

export function CyberEventTerminal({ lines }: Props) {
  const displayLines = collapseCyberLogLines(lines);

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden p-4">
      <h2 className="mb-2 h-6 shrink-0 font-mono text-xs uppercase tracking-wider text-zinc-500">
        Микро-лог
      </h2>
      <div
        data-testid="cyber-log-scroll"
        className="flex flex-1 flex-col-reverse gap-1 overflow-y-auto font-mono text-xs text-zinc-400"
      >
        {displayLines.length === 0 ? (
          <div className="text-zinc-600">Ожидание событий…</div>
        ) : (
          displayLines.map((line) => (
            <div
              key={line.event_id}
              data-testid="cyber-log-line"
              className={severityClass(line)}
            >
              {formatCyberLine(line)}
            </div>
          ))
        )}
      </div>
    </section>
  );
}
