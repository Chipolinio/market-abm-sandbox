import { useCallback, useEffect, useMemo, useState } from "react";

import {
  experimentFigureUrl,
  fetchCurrentJob,
  fetchExperimentList,
  fetchExperimentSummary,
  fetchJob,
  fetchMlRegistryStatus,
  postExperimentRun,
  postTrainMl,
} from "@/api/experiments";
import type {
  ExperimentPreset,
  ExperimentRunRequest,
  ExperimentSummaryRow,
  JobStatus,
  MlRegistryStatus,
} from "@/types/experiments";
import { PAPER_PRESET, SMOKE_PRESET } from "@/types/experiments";

const METRIC_LABELS: Record<string, string> = {
  consumer_surplus_proxy: "Излишек потребителя (proxy)",
  producer_surplus: "Излишек производителя",
  platform_profit: "Прибыль платформы",
  gmv: "GMV",
  hhi: "HHI",
  median_price: "Медианная цена",
  mean_listing_price: "Средняя цена витрины",
  n_tx: "Число транзакций",
  price_std: "Стд. откл. цены",
};

const WINDOW_LABELS: Record<string, string> = {
  post_burn_in: "после прогрева",
  full: "весь период",
};

const STATUS_LABELS: Record<string, string> = {
  QUEUED: "В очереди",
  RUNNING: "Выполняется",
  DONE: "Готово",
  FAILED: "Ошибка",
};

const FIGURE_LABELS: Record<string, string> = {
  "F1.png": "F1 — траектория цены",
  "F2.png": "F2 — волатильность",
  "F3.png": "F3 — HHI",
  "F4.png": "F4 — welfare",
  "F5.png": "F5 — Zipf / rank-size",
};

function metricLabel(metric: string): string {
  return METRIC_LABELS[metric] ?? metric;
}

function windowLabel(window: string): string {
  return WINDOW_LABELS[window] ?? window;
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

function formatNum(value: number | undefined): string {
  if (value === undefined || Number.isNaN(value)) {
    return "—";
  }
  if (!Number.isFinite(value)) {
    return String(value);
  }
  if (Math.abs(value) >= 1e6 || (Math.abs(value) > 0 && Math.abs(value) < 1e-3)) {
    return value.toExponential(3);
  }
  return value.toLocaleString("ru-RU", { maximumFractionDigits: 4 });
}

/** Next free id for preset: smoke-1, paper-2, custom-1, … */
export function nextExperimentId(preset: ExperimentPreset, existing: string[]): string {
  const prefix = preset;
  const re = new RegExp(`^${prefix}-(\\d+)$`, "i");
  let max = 0;
  for (const id of existing) {
    const m = id.match(re);
    if (m) {
      max = Math.max(max, Number(m[1]));
    }
  }
  return `${prefix}-${max + 1}`;
}

function applyPreset(preset: ExperimentPreset): Omit<ExperimentRunRequest, "experiment_id"> {
  if (preset === "paper") {
    return { ...PAPER_PRESET };
  }
  if (preset === "smoke") {
    return { ...SMOKE_PRESET };
  }
  return { ...SMOKE_PRESET, preset: "custom" };
}

function formatShareGrid(grid: number[]): string {
  return grid.map((x) => String(x)).join(", ");
}

function parseShareGrid(raw: string): number[] | null {
  const parts = raw
    .split(/[,;\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  if (parts.length === 0) {
    return null;
  }
  const values: number[] = [];
  for (const p of parts) {
    const n = Number(p);
    if (!Number.isFinite(n) || n < 0 || n > 1) {
      return null;
    }
    values.push(n);
  }
  return values;
}

type ConfirmFn = (message: string) => boolean;

type Props = {
  /** Injected for Vitest — defaults to window.confirm. */
  confirmFn?: ConfirmFn;
  /** Injected poll interval ms (default 2000). */
  pollIntervalMs?: number;
};

/** Spec 015.1 — Launch + status poll + summary + figure gallery. */
export function ResearchLab({
  confirmFn = (msg) => window.confirm(msg),
  pollIntervalMs = 2000,
}: Props) {
  const [preset, setPreset] = useState<ExperimentPreset>("smoke");
  const [experimentId, setExperimentId] = useState(() => nextExperimentId("smoke", []));
  const [idManual, setIdManual] = useState(false);
  const [form, setForm] = useState(() => applyPreset("smoke"));
  const [shareGridText, setShareGridText] = useState(() =>
    formatShareGrid(SMOKE_PRESET.ml_share_grid),
  );
  const [job, setJob] = useState<JobStatus | null>(null);
  const [summaryRows, setSummaryRows] = useState<ExperimentSummaryRow[]>([]);
  const [pastExperiments, setPastExperiments] = useState<string[]>([]);
  const [resultsExperimentId, setResultsExperimentId] = useState<string | null>(null);
  const [figures, setFigures] = useState<string[]>([]);
  const [resultWarnings, setResultWarnings] = useState<string[]>([]);
  const [figureCacheBust, setFigureCacheBust] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [launching, setLaunching] = useState(false);
  const [training, setTraining] = useState(false);
  const [useRobustTable, setUseRobustTable] = useState(true);
  const [mlRegistry, setMlRegistry] = useState<MlRegistryStatus | null>(null);

  const running = job?.status === "RUNNING";
  const formLocked = running || launching || training;
  const customEditable = preset === "custom" && !formLocked;
  const isTrainJob = job?.experiment_id === "ml-train";

  const occupiedIds = useMemo(() => {
    const ids = new Set(pastExperiments);
    if (job?.experiment_id) {
      ids.add(job.experiment_id);
    }
    return [...ids];
  }, [job?.experiment_id, pastExperiments]);

  const refreshPastList = useCallback(async () => {
    try {
      const ids = await fetchExperimentList();
      setPastExperiments(ids);
      return ids;
    } catch {
      return [] as string[];
    }
  }, []);

  const refreshMlRegistry = useCallback(async () => {
    try {
      setMlRegistry(await fetchMlRegistryStatus());
    } catch {
      setMlRegistry(null);
    }
  }, []);

  const loadSummary = useCallback(async (id: string) => {
    try {
      const res = await fetchExperimentSummary(id);
      setSummaryRows(res.rows);
      setResultsExperimentId(res.experiment_id);
      setFigures(res.figures ?? []);
      setResultWarnings(res.warnings ?? []);
      setFigureCacheBust(Date.now());
    } catch {
      setSummaryRows([]);
      setFigures([]);
      setResultWarnings([]);
    }
  }, []);

  useEffect(() => {
    void refreshPastList();
    void refreshMlRegistry();
  }, [refreshMlRegistry, refreshPastList]);

  // Auto-suggest next free smoke-N / paper-N / custom-N unless user edited the field.
  useEffect(() => {
    if (idManual || formLocked) {
      return;
    }
    setExperimentId(nextExperimentId(preset, occupiedIds));
  }, [formLocked, idManual, occupiedIds, preset]);

  useEffect(() => {
    let cancelled = false;
    void fetchCurrentJob()
      .then((res) => {
        if (cancelled || !res.job) {
          return;
        }
        setJob(res.job);
        if (res.job.status === "DONE") {
          if (res.job.experiment_id === "ml-train") {
            setResultWarnings(res.job.warnings ?? []);
            void refreshMlRegistry();
          } else {
            void loadSummary(res.job.experiment_id).then(() => refreshPastList());
          }
        }
      })
      .catch(() => {
        /* idle */
      });
    return () => {
      cancelled = true;
    };
  }, [loadSummary, refreshMlRegistry, refreshPastList]);

  useEffect(() => {
    if (!job || job.status !== "RUNNING") {
      return;
    }
    const handle = window.setInterval(() => {
      void fetchJob(job.job_id)
        .then((next) => {
          setJob(next);
          if (next.status === "DONE") {
            if (next.experiment_id === "ml-train") {
              setResultWarnings(next.warnings ?? []);
              void refreshMlRegistry();
              void refreshPastList();
            } else {
              void loadSummary(next.experiment_id).then(() => refreshPastList());
            }
            setIdManual(false);
          }
          if (next.status === "FAILED") {
            setError(next.error ?? "Задача эксперимента завершилась с ошибкой");
            setResultWarnings(next.warnings ?? []);
            setIdManual(false);
          }
        })
        .catch((err: unknown) => {
          setError(err instanceof Error ? err.message : "Ошибка опроса статуса");
        });
    }, pollIntervalMs);
    return () => window.clearInterval(handle);
  }, [job, loadSummary, pollIntervalMs, refreshMlRegistry, refreshPastList]);

  const effectiveShareGrid = useMemo(() => {
    if (preset !== "custom") {
      return form.ml_share_grid;
    }
    return parseShareGrid(shareGridText) ?? form.ml_share_grid;
  }, [form.ml_share_grid, preset, shareGridText]);

  const tickEstimate = useMemo(() => {
    return form.n_runs * effectiveShareGrid.length * form.n_ticks;
  }, [effectiveShareGrid.length, form.n_runs, form.n_ticks]);

  const uniqueSharesInSummary = useMemo(() => {
    return [...new Set(summaryRows.map((r) => r.ml_share))].sort((a, b) => a - b);
  }, [summaryRows]);

  const hasRobustCols = useMemo(
    () => summaryRows.some((r) => r.median !== undefined),
    [summaryRows],
  );

  const onPresetChange = (next: ExperimentPreset) => {
    setPreset(next);
    const nextForm = applyPreset(next);
    setForm(nextForm);
    setShareGridText(formatShareGrid(nextForm.ml_share_grid));
    setIdManual(false);
    setExperimentId(nextExperimentId(next, occupiedIds));
    setError(null);
  };

  const patchForm = <K extends keyof Omit<ExperimentRunRequest, "experiment_id" | "preset">>(
    key: K,
    value: Omit<ExperimentRunRequest, "experiment_id">[K],
  ) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const onOpenPast = (id: string) => {
    setError(null);
    void loadSummary(id);
  };

  const onTrainMl = async () => {
    setError(null);
    if (mlRegistry?.present) {
      const ok = confirmFn(
        "Уже есть frozen CatBoost в output/ml_frozen. Переобучить и перезаписать?",
      );
      if (!ok) {
        return;
      }
    } else {
      const ok = confirmFn(
        "Обучить CatBoost на bootstrap rules-прогонах и сохранить в output/ml_frozen? Это займёт несколько минут.",
      );
      if (!ok) {
        return;
      }
    }
    setTraining(true);
    try {
      const accepted = await postTrainMl({});
      setJob({
        job_id: accepted.job_id,
        experiment_id: accepted.experiment_id,
        status: accepted.status,
        done: 0,
        total: 4,
      });
      setResultWarnings([]);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Не удалось запустить обучение");
    } finally {
      setTraining(false);
    }
  };

  const onLaunch = async () => {
    setError(null);

    let launchForm = { ...form, preset };
    if (preset === "custom") {
      const parsed = parseShareGrid(shareGridText);
      if (parsed === null) {
        setError("Сетка долей ML: числа от 0 до 1 через запятую (например 0, 0.5, 1)");
        return;
      }
      launchForm = { ...form, ml_share_grid: parsed, preset: "custom" };
      setForm(launchForm);
    }

    if (preset === "paper") {
      const ok = confirmFn(
        `Paper-сетка выполнит примерно ${(launchForm.n_runs * launchForm.ml_share_grid.length * launchForm.n_ticks).toLocaleString("ru-RU")} тик-симуляций в фоне на этой машине. Продолжить?`,
      );
      if (!ok) {
        return;
      }
    }

    const launchId =
      experimentId.trim() || nextExperimentId(preset, occupiedIds);
    const body: ExperimentRunRequest = {
      experiment_id: launchId,
      ...launchForm,
      preset,
    };
    setLaunching(true);
    try {
      const accepted = await postExperimentRun(body);
      setJob({
        job_id: accepted.job_id,
        experiment_id: accepted.experiment_id,
        status: accepted.status,
        done: 0,
        total: launchForm.n_runs * launchForm.ml_share_grid.length,
      });
      setSummaryRows([]);
      setFigures([]);
      setResultWarnings([]);
      setResultsExperimentId(null);
      setExperimentId(accepted.experiment_id);
      setIdManual(true); // keep accepted id while job runs; unlock auto after DONE
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Не удалось запустить эксперимент");
    } finally {
      setLaunching(false);
    }
  };

  const displayCenter = (row: ExperimentSummaryRow): number =>
    useRobustTable && row.median !== undefined ? row.median : row.mean;
  const displayLo = (row: ExperimentSummaryRow): number =>
    useRobustTable && row.q25 !== undefined ? row.q25 : row.lo;
  const displayHi = (row: ExperimentSummaryRow): number =>
    useRobustTable && row.q75 !== undefined ? row.q75 : row.hi;

  return (
    <div className="h-screen overflow-y-auto overscroll-contain bg-slate-50 p-6 text-slate-900">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Лаборатория исследований</h1>
          <p className="text-sm text-slate-600">
            Сетка сценариев по доле ML-продавцов: прогоны, сводка, графики F1–F5.
          </p>
        </div>
        <a
          href="#"
          data-testid="nav-live-terminal"
          className="text-sm font-medium text-slate-700 underline-offset-4 hover:underline"
        >
          ← Live terminal
        </a>
      </header>

      <section
        className="mb-6 max-w-3xl rounded border border-slate-200 bg-white p-4"
        data-testid="ml-train-panel"
      >
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Frozen CatBoost
        </h2>
        <p className="mt-2 text-sm text-slate-600">
          Paper/smoke с ML используют registry из{" "}
          <span className="font-mono text-xs">output/ml_frozen</span>. Без него — research stub.
        </p>
        <p className="mt-2 text-sm" data-testid="ml-registry-status">
          {mlRegistry == null
            ? "Статус registry: …"
            : mlRegistry.present
              ? `Готов · strategies: ${(mlRegistry.strategies ?? []).join(", ") || "—"} · ${mlRegistry.catboost_version ?? ""}`
              : "Нет frozen registry — перед paper нажмите «Обучить CatBoost»."}
        </p>
        <button
          type="button"
          className="mt-3 rounded border border-slate-300 bg-white px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-40"
          disabled={formLocked}
          onClick={() => void onTrainMl()}
        >
          {training || (running && isTrainJob) ? "Обучение…" : "Обучить CatBoost"}
        </button>
      </section>

      <div className="mb-6 grid gap-6 lg:grid-cols-[minmax(0,28rem)_minmax(0,1fr)]">
        <section className="space-y-3 rounded border border-slate-200 bg-white p-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Запуск эксперимента
          </h2>
          <label className="block text-sm">
            Пресет
            <select
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
              value={preset}
              disabled={formLocked}
              onChange={(e) => onPresetChange(e.target.value as ExperimentPreset)}
            >
              <option value="smoke">Smoke — доли 0 и 1, 3 прогона × 20 тиков</option>
              <option value="paper">Paper — 0 / 0.25 / 0.5 / 0.75 / 1 × 30 seeds</option>
              <option value="custom">Свой — все параметры вручную</option>
            </select>
          </label>

          <label className="block text-sm">
            ID эксперимента
            <input
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1 font-mono text-sm"
              value={experimentId}
              disabled={formLocked}
              onChange={(e) => {
                setIdManual(true);
                setExperimentId(e.target.value);
              }}
            />
          </label>
          <p className="text-xs text-slate-500">
            Авто по пресету: <span className="font-mono">smoke-1</span>,{" "}
            <span className="font-mono">paper-1</span>,{" "}
            <span className="font-mono">custom-1</span> — следующий свободный номер. Артефакты:{" "}
            <span className="font-mono">output/experiments/&lt;id&gt;/</span>
          </p>

          {preset === "custom" ? (
            <div className="space-y-3 border-t border-slate-100 pt-3" data-testid="custom-params">
              <label className="block text-sm">
                Сетка долей ML (0…1 через запятую)
                <input
                  className="mt-1 w-full rounded border border-slate-300 px-2 py-1 font-mono text-sm"
                  value={shareGridText}
                  disabled={!customEditable}
                  onChange={(e) => setShareGridText(e.target.value)}
                />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block text-sm">
                  Прогонов на долю
                  <input
                    type="number"
                    min={1}
                    className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
                    value={form.n_runs}
                    disabled={!customEditable}
                    onChange={(e) => patchForm("n_runs", Number(e.target.value))}
                  />
                </label>
                <label className="block text-sm">
                  Тиков
                  <input
                    type="number"
                    min={1}
                    className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
                    value={form.n_ticks}
                    disabled={!customEditable}
                    onChange={(e) => patchForm("n_ticks", Number(e.target.value))}
                  />
                </label>
                <label className="block text-sm">
                  Burn-in (тиков)
                  <input
                    type="number"
                    min={0}
                    className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
                    value={form.burn_in_ticks}
                    disabled={!customEditable}
                    onChange={(e) => patchForm("burn_in_ticks", Number(e.target.value))}
                  />
                </label>
                <label className="block text-sm">
                  Параллельных jobs
                  <input
                    type="number"
                    min={1}
                    className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
                    value={form.jobs}
                    disabled={!customEditable}
                    onChange={(e) => patchForm("jobs", Number(e.target.value))}
                  />
                </label>
                <label className="block text-sm">
                  Покупатели
                  <input
                    type="number"
                    min={1}
                    className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
                    value={form.n_buyers}
                    disabled={!customEditable}
                    onChange={(e) => patchForm("n_buyers", Number(e.target.value))}
                  />
                </label>
                <label className="block text-sm">
                  Продавцы
                  <input
                    type="number"
                    min={1}
                    className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
                    value={form.n_sellers}
                    disabled={!customEditable}
                    onChange={(e) => patchForm("n_sellers", Number(e.target.value))}
                  />
                </label>
                <label className="col-span-2 block text-sm">
                  Base seed
                  <input
                    type="number"
                    className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
                    value={form.base_seed}
                    disabled={!customEditable}
                    onChange={(e) => patchForm("base_seed", Number(e.target.value))}
                  />
                </label>
              </div>
            </div>
          ) : (
            <p className="rounded bg-slate-50 px-3 py-2 text-xs text-slate-600">
              Сетка долей: <span className="font-mono">{formatShareGrid(form.ml_share_grid)}</span>
            </p>
          )}

          <p className="text-xs text-slate-500">
            Оценка: {form.n_runs} × {effectiveShareGrid.length} × {form.n_ticks} ≈{" "}
            {tickEstimate.toLocaleString("ru-RU")} тик-симуляций
          </p>
          <button
            type="button"
            className="rounded bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-40"
            disabled={formLocked}
            onClick={() => void onLaunch()}
          >
            {launching ? "Запуск…" : "Запустить"}
          </button>
          {error ? (
            <p className="text-sm text-red-700" role="alert">
              {error}
            </p>
          ) : null}
        </section>

        <section className="rounded border border-slate-200 bg-white p-4" data-testid="past-experiments">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Прошлые эксперименты
          </h2>
          {pastExperiments.length === 0 ? (
            <p className="mt-3 text-sm text-slate-500">Пока нет сохранённых сводок.</p>
          ) : (
            <ul className="mt-3 max-h-80 space-y-1 overflow-y-auto text-sm">
              {pastExperiments.map((id) => (
                <li key={id}>
                  <button
                    type="button"
                    className={`w-full rounded px-2 py-1 text-left font-mono hover:bg-slate-100 ${
                      id === resultsExperimentId ? "bg-slate-100 font-semibold" : ""
                    }`}
                    disabled={formLocked}
                    onClick={() => onOpenPast(id)}
                  >
                    {id}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {job ? (
        <section
          className="mb-6 max-w-xl rounded border border-slate-200 bg-white p-4"
          data-testid="job-status"
        >
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Статус задачи
          </h2>
          <p className="mt-2 font-mono text-sm">
            {statusLabel(job.status)} {job.done} / {job.total}{" "}
            {isTrainJob ? "шагов обучения" : "прогонов"} — {job.experiment_id}
          </p>
          {typeof job.current_ml_share === "number" ? (
            <p className="text-xs text-slate-500">
              Сейчас: доля ML {job.current_ml_share}
              {typeof job.current_run_index === "number"
                ? `, run ${job.current_run_index}`
                : null}
            </p>
          ) : null}
          {job.error ? <p className="text-sm text-red-700">{job.error}</p> : null}
          {(job.warnings?.length ?? 0) > 0 ? (
            <ul className="mt-2 list-disc pl-5 text-xs text-amber-800">
              {job.warnings!.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

      {resultWarnings.length > 0 ? (
        <section className="mb-6 rounded border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <h2 className="font-semibold">Предупреждения прогона</h2>
          <ul className="mt-2 list-disc pl-5 text-xs">
            {resultWarnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="mb-6 rounded border border-slate-200 bg-white" data-testid="figure-gallery">
        <h2 className="border-b border-slate-200 bg-slate-100 px-3 py-2 text-sm font-semibold">
          Графики F1–F5{" "}
          {resultsExperimentId ? (
            <span className="font-mono font-normal">({resultsExperimentId})</span>
          ) : null}
        </h2>
        {figures.length === 0 || !resultsExperimentId ? (
          <p className="px-3 py-4 text-sm text-slate-500">
            Графиков пока нет — дождитесь завершения прогона или откройте прошлый эксперимент.
          </p>
        ) : (
          <div className="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-3">
            {figures.map((name) => (
              <figure key={name} className="rounded border border-slate-100 bg-slate-50 p-2">
                <figcaption className="mb-2 text-xs font-medium text-slate-600">
                  {FIGURE_LABELS[name] ?? name}
                </figcaption>
                <img
                  src={`${experimentFigureUrl(resultsExperimentId, name)}?t=${figureCacheBust}`}
                  alt={FIGURE_LABELS[name] ?? name}
                  className="w-full bg-white"
                />
              </figure>
            ))}
          </div>
        )}
      </section>

      <section className="mb-10 rounded border border-slate-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-100 px-3 py-2">
          <h2 className="text-sm font-semibold">
            Результаты{" "}
            {resultsExperimentId ? (
              <span className="font-mono font-normal">({resultsExperimentId})</span>
            ) : null}
          </h2>
          {hasRobustCols ? (
            <label className="flex items-center gap-2 text-xs text-slate-600">
              <input
                type="checkbox"
                checked={useRobustTable}
                onChange={(e) => setUseRobustTable(e.target.checked)}
              />
              Робастно: медиана / IQR (вместо mean ± t-CI)
            </label>
          ) : null}
        </div>
        {summaryRows.length > 0 && resultsExperimentId ? (
          <p className="border-b border-slate-100 px-3 py-2 text-xs text-slate-500">
            Доли ML: <span className="font-mono">{uniqueSharesInSummary.join(", ")}</span>
            {" · "}
            <span className="font-mono">
              output/experiments/{resultsExperimentId}/aggregate/summary.json
            </span>
          </p>
        ) : null}
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-3 py-2">метрика</th>
                <th className="px-3 py-2">доля ML</th>
                <th className="px-3 py-2">окно</th>
                <th className="px-3 py-2">
                  {useRobustTable && hasRobustCols ? "медиана" : "среднее"}
                </th>
                <th className="px-3 py-2">
                  {useRobustTable && hasRobustCols ? "q25" : "нижняя"}
                </th>
                <th className="px-3 py-2">
                  {useRobustTable && hasRobustCols ? "q75" : "верхняя"}
                </th>
              </tr>
            </thead>
            <tbody>
              {summaryRows.length === 0 ? (
                <tr>
                  <td className="px-3 py-3 text-slate-500" colSpan={6}>
                    Сводки пока нет — запустите smoke или выберите прошлый эксперимент.
                  </td>
                </tr>
              ) : (
                summaryRows.map((row) => (
                  <tr
                    key={`${row.metric}-${row.ml_share}-${row.window}`}
                    className="border-b border-slate-100"
                  >
                    <td className="px-3 py-2" title={row.metric}>
                      {metricLabel(row.metric)}
                    </td>
                    <td className="px-3 py-2">{row.ml_share}</td>
                    <td className="px-3 py-2">{windowLabel(row.window)}</td>
                    <td className="px-3 py-2 font-mono text-xs">{formatNum(displayCenter(row))}</td>
                    <td className="px-3 py-2 font-mono text-xs">{formatNum(displayLo(row))}</td>
                    <td className="px-3 py-2 font-mono text-xs">{formatNum(displayHi(row))}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
