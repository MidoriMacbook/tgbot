import React, { Component, useEffect, useMemo, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { animate } from "animejs";
import { MotionConfig, motion, useReducedMotion } from "motion/react";
import { BarChart3, Inbox, RefreshCw, TriangleAlert } from "lucide-react";
import { AreaChart } from "@/components/charts/area-chart";
import { Area } from "@/components/charts/area";
import { BarChart } from "@/components/charts/bar-chart";
import { Bar } from "@/components/charts/bar";
import { BarYAxis } from "@/components/charts/bar-y-axis";
import { Grid } from "@/components/charts/grid";
import { XAxis } from "@/components/charts/x-axis";
import { YAxis } from "@/components/charts/y-axis";
import { ChartTooltip } from "@/components/charts/tooltip";
import { chartCssVars } from "@/components/charts/chart-context";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import "./islands.css";

type TrendRow = { date: string; created: number; closed: number };
type OperatorRow = { name: string; completed: number; rejected: number; total: number };
type StatisticsData = { trend: TrendRow[]; operators: OperatorRow[] };
const shortDate = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", timeZone: "Europe/Moscow" });
const fullDate = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric", timeZone: "Europe/Moscow" });
const number = new Intl.NumberFormat("ru-RU");
const formatCount = (value: number) => Number.isInteger(value) ? number.format(value) : "";

function useNarrow() {
  const [narrow, setNarrow] = useState(() => window.matchMedia("(max-width: 800px)").matches);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 800px)");
    const apply = () => setNarrow(query.matches);
    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, []);
  return narrow;
}
const chartStyle = { height: "100%", aspectRatio: "auto" };

function EmptyChart({ children }: { children: ReactNode }) {
  return <div className="chart-empty"><Inbox size={25} strokeWidth={1.5} /><p>{children}</p></div>;
}

function ChartTables({ data }: { data: StatisticsData }) {
  return <details className="chart-data"><summary>Показать данные графиков</summary><div className="chart-data-scroll">
    <table><caption className="sr-only">Поступление и закрытие заявок по дням</caption><thead><tr><th scope="col">Дата</th><th scope="col" className="numeric">Поступило</th><th scope="col" className="numeric">Закрыто</th></tr></thead><tbody>{data.trend.map(row => <tr key={row.date}><td>{fullDate.format(new Date(`${row.date}T12:00:00+03:00`))}</td><td className="numeric">{row.created}</td><td className="numeric">{row.closed}</td></tr>)}</tbody></table>
    <table><caption className="sr-only">Закрытия по сотрудникам</caption><thead><tr><th scope="col">Сотрудник</th><th scope="col" className="numeric">Выполнено</th><th scope="col" className="numeric">Отклонено</th><th scope="col" className="numeric">Всего</th></tr></thead><tbody>{data.operators.map((row, index) => <tr key={`${row.name}-${index}`}><td>{row.name}</td><td className="numeric">{row.completed}</td><td className="numeric">{row.rejected}</td><td className="numeric">{row.total}</td></tr>)}{!data.operators.length && <tr><td colSpan={4}>В этом периоде закрытий нет.</td></tr>}</tbody></table>
  </div></details>;
}

function Statistics({ endpoint }: { endpoint: string }) {
  const [days, setDays] = useState("30");
  const [attempt, setAttempt] = useState(0);
  const [data, setData] = useState<StatisticsData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const reducedMotion = useReducedMotion();
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setLoading(true); setError(""); setData(null);
    const timeout = window.setTimeout(() => controller.abort("timeout"), 15000);
    const url = new URL(endpoint, window.location.origin); url.searchParams.set("days", days);
    fetch(url, { signal: controller.signal, credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } })
      .then(async response => {
        if (response.status === 403 || response.redirected) throw new Error("Сессия завершилась или доступ к статистике закрыт. Обновите страницу и войдите заново.");
        if (!response.ok) throw new Error("Не удалось загрузить статистику. Повторите попытку.");
        const result: StatisticsData = await response.json();
        if (!Array.isArray(result.trend) || !Array.isArray(result.operators)) throw new Error("Сервер вернул неполные данные статистики.");
        if (active && !controller.signal.aborted) setData(result);
      })
      .catch(cause => {
        if (!active || (controller.signal.aborted && controller.signal.reason !== "timeout")) return;
        setError(controller.signal.reason === "timeout" ? "Сервер не ответил вовремя. Повторите попытку." : cause instanceof Error ? cause.message : "Проверьте подключение и повторите попытку.");
      })
      .finally(() => { window.clearTimeout(timeout); if (active && (!controller.signal.aborted || controller.signal.reason === "timeout")) setLoading(false); });
    return () => { active = false; window.clearTimeout(timeout); controller.abort(); };
  }, [endpoint, days, attempt]);

  const narrow = useNarrow();
  const trend = useMemo(() => (data?.trend ?? []).map(row => ({ ...row, date: new Date(`${row.date}T12:00:00+03:00`) })), [data]);
  const labels = useMemo(() => trend.map(row => shortDate.format(row.date)), [trend]);
  const operators = useMemo(() => (data?.operators ?? []).slice(0, 8).map((row, index) => {
    const limit = narrow ? 9 : 14;
    const name = row.name.length > limit ? `${row.name.slice(0, limit - 1)}…` : row.name;
    return { ...row, label: `${index + 1}. ${name}` };
  }), [data, narrow]);
  const hasTrend = trend.some(row => row.created > 0 || row.closed > 0);
  const hasOperators = operators.some(row => row.total > 0);
  const tooltipMotion = reducedMotion || narrow ? { damping: 0, showDots: !narrow, showCrosshair: !narrow, showDatePill: false, exit: false, animateSize: false } : {};

  return <MotionConfig reducedMotion="user"><Tabs value={days} onValueChange={setDays}>
    <div className="analytics-toolbar"><span className="period-caption">{days} дней · по московскому времени</span><TabsList className="analytics-tabs" aria-label="Период статистики">{["7", "30", "90"].map(value => <TabsTrigger key={value} value={value}>{value} дней</TabsTrigger>)}</TabsList></div>
    <TabsContent value={days} tabIndex={0}>
      <div className="sr-only" role="status" aria-live="polite">{loading ? "Статистика загружается" : error || `Статистика за ${days} дней загружена`}</div>
      {error ? <div className="error analytics-error" role="alert"><TriangleAlert size={20} /><p>{error}</p><Button className="button secondary-button" variant="outline" onClick={() => setAttempt(value => value + 1)}><RefreshCw size={15} />Повторить</Button></div> :
      <motion.div className="analytics-grid" initial={reducedMotion ? false : { opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .2 }} aria-busy={loading}>
        <Card className="chart-card"><CardHeader><CardTitle>Динамика заявок</CardTitle><CardDescription>Созданные и закрытые заявки по дням</CardDescription></CardHeader><CardContent>
          <div className="chart-legend"><span><i className="legend-dot" />Поступило</span><span><i className="legend-dot secondary-dot" />Закрыто</span></div>
          {loading ? <Skeleton className="chart-skeleton" aria-label="Загрузка динамики" /> : !hasTrend ? <EmptyChart>В этом периоде заявки не поступали и не закрывались.</EmptyChart> : <div className="chart-host" role="img" aria-label="График поступления и закрытия заявок. Данные доступны в таблице ниже."><AreaChart data={trend} style={chartStyle} margin={narrow ? { left: 28, top: 12, right: 8, bottom: 32 } : { left: 34, top: 20, right: 16, bottom: 36 }} animationDuration={reducedMotion ? 0 : 1100} yDomainTween={!reducedMotion}>
            <Grid horizontal numTicksRows={4} stroke={chartCssVars.grid} />
            <Area dataKey="created" fill={chartCssVars.linePrimary} fillOpacity={.15} animate={!reducedMotion} showHighlight={!reducedMotion} />
            <Area dataKey="closed" fill={chartCssVars.lineSecondary} fillOpacity={.05} animate={!reducedMotion} showHighlight={!reducedMotion} />
            <YAxis numTicks={narrow ? 3 : 4} formatValue={formatCount} /><XAxis numTicks={narrow ? 2 : { base: 3, sm: 5 }} labels={labels} />
            <ChartTooltip {...tooltipMotion} dateLabels={labels} rows={point => [{ color: chartCssVars.linePrimary, label: "Дата", value: point.date instanceof Date ? shortDate.format(point.date) : "" }, { color: chartCssVars.linePrimary, label: "Поступило", value: number.format(Number(point.created)) }, { color: chartCssVars.lineSecondary, label: "Закрыто", value: number.format(Number(point.closed)) }]} />
          </AreaChart></div>}
        </CardContent></Card>
        <Card className="chart-card"><CardHeader><CardTitle>Закрытия по сотрудникам</CardTitle><CardDescription>Выполненные и отклонённые заявки</CardDescription></CardHeader><CardContent>
          <div className="chart-legend"><span><i className="legend-dot" />Выполнено</span><span><i className="legend-dot secondary-dot" />Отклонено</span></div>
          {loading ? <Skeleton className="chart-skeleton" aria-label="Загрузка результатов сотрудников" /> : !hasOperators ? <EmptyChart>В этом периоде сотрудники ещё не закрывали заявки.</EmptyChart> : <div className="chart-host" role="img" aria-label="График закрытий по сотрудникам. Полные имена и значения доступны в таблице ниже."><BarChart data={operators} xDataKey="label" orientation="horizontal" stacked aspectRatio="auto" className="h-full" margin={narrow ? { left: 72, top: 8, right: 8, bottom: 12 } : { left: 95, top: 10, right: 15, bottom: 20 }} animationDuration={reducedMotion ? 0 : 1100}>
            <Grid horizontal={false} vertical numTicksColumns={4} stroke={chartCssVars.grid} />
            <Bar dataKey="completed" fill={chartCssVars.linePrimary} animate={!reducedMotion} lineCap={2} />
            <Bar dataKey="rejected" fill={chartCssVars.lineSecondary} animate={!reducedMotion} lineCap={2} />
            <BarYAxis />
            <ChartTooltip {...tooltipMotion} showDatePill={false} content={({ point }) => <div className="operator-tooltip"><strong>{String(point.name)}</strong><p>Выполнено: {number.format(Number(point.completed))}</p><p>Отклонено: {number.format(Number(point.rejected))}</p></div>} />
          </BarChart></div>}
          <p className="chart-note">По автору закрытия.{data && data.operators.length > 8 ? " На графике — первые 8 сотрудников; полный список в таблице." : ""}</p>
        </CardContent></Card>
      </motion.div>}
      {data && !loading && <ChartTables data={data} />}
    </TabsContent>
  </Tabs></MotionConfig>;
}

class ChartBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <div className="error"><BarChart3 size={20} /><p>Не удалось отобразить графики. Сводка по всем заявкам доступна ниже. Обновите страницу, чтобы повторить загрузку.</p></div> : this.props.children;
  }
}

const mount = document.getElementById("statistics-app");
if (mount?.dataset.endpoint) createRoot(mount).render(<ChartBoundary><Statistics endpoint={mount.dataset.endpoint} /></ChartBoundary>);

function initializeMiniApp() {
  const app = (window as Window & { Telegram?: { WebApp?: {
    initData?: string; ready?: () => void; expand?: () => void;
    setHeaderColor?: (value: string) => void; setBackgroundColor?: (value: string) => void;
  } } }).Telegram?.WebApp;
  if (!app?.initData) return;
  app.ready?.();
  app.expand?.();
  app.setHeaderColor?.("#141618");
  app.setBackgroundColor?.("#141618");
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initializeMiniApp, { once: true });
else initializeMiniApp();

if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  animate(".page-heading, .login-panel", { opacity: [0, 1], y: [6, 0], duration: 240, ease: "out(3)" });
  document.querySelectorAll(".notice, .field-error").forEach(element => animate(element, { opacity: [.3, 1], duration: 220, ease: "out(2)" }));
}
