import { memo, useMemo } from "react";
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-basic-dist-min";

const Plot = createPlotlyComponent(Plotly);
const PLOT_CONFIG: Partial<Plotly.Config> = {
  displayModeBar: false,
  responsive: true
};

type ChartFigurePlotProps = {
  figure: Record<string, unknown> | null;
  height?: number;
};

function ChartFigurePlot({
  figure,
  height = 320
}: ChartFigurePlotProps) {
  if (!figure) {
    return <div className="empty-card">No hay gráfico disponible para este bloque.</div>;
  }

  const plotData = useMemo(() => (figure.data as Plotly.Data[]) ?? [], [figure]);
  const layout = useMemo(() => {
    const base = (figure.layout as Partial<Plotly.Layout>) ?? {};
    return {
      ...base,
      autosize: true,
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      margin: {
        l: 36,
        r: 18,
        t: 30,
        b: 34,
        ...(base.margin ?? {})
      }
    };
  }, [figure]);

  return (
    <Plot
      data={plotData}
      layout={layout}
      config={PLOT_CONFIG}
      className="plot"
      useResizeHandler
      style={{ width: "100%", height }}
    />
  );
}

export default memo(ChartFigurePlot);
