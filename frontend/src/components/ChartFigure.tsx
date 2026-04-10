import { lazy, Suspense } from "react";

const LazyChartFigurePlot = lazy(() => import("./ChartFigurePlot"));

type ChartFigureProps = {
  figure: Record<string, unknown> | null;
  height?: number;
};

export function ChartFigure({ figure, height = 320 }: ChartFigureProps) {
  if (!figure) {
    return <div className="empty-card">No hay gráfico disponible para este bloque.</div>;
  }

  return (
    <Suspense fallback={<div className="empty-card">Cargando gráfico...</div>}>
      <LazyChartFigurePlot figure={figure} height={height} />
    </Suspense>
  );
}
