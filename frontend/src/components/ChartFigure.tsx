import { lazy, Suspense, useEffect } from "react";

const loadChartFigurePlot = () => import("./ChartFigurePlot");
const LazyChartFigurePlot = lazy(loadChartFigurePlot);

type ChartFigureProps = {
  figure: Record<string, unknown> | null;
  height?: number;
};

export function ChartFigure({ figure, height = 320 }: ChartFigureProps) {
  useEffect(() => {
    void loadChartFigurePlot();
  }, []);

  if (!figure) {
    return (
      <div className="empty-card" style={{ minHeight: `${height}px`, height: `${height}px` }}>
        No hay gráfico disponible para este bloque.
      </div>
    );
  }

  return (
    <Suspense
      fallback={
        <div className="empty-card" style={{ minHeight: `${height}px`, height: `${height}px` }}>
          Cargando gráfico...
        </div>
      }
    >
      <LazyChartFigurePlot figure={figure} height={height} />
    </Suspense>
  );
}
