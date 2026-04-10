import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-basic-dist-min";

const Plot = createPlotlyComponent(Plotly);

type ChartFigurePlotProps = {
  figure: Record<string, unknown> | null;
  height?: number;
};

export default function ChartFigurePlot({
  figure,
  height = 320
}: ChartFigurePlotProps) {
  if (!figure) {
    return <div className="empty-card">No hay gráfico disponible para este bloque.</div>;
  }

  const layout = (figure.layout as Partial<Plotly.Layout>) ?? {};

  return (
    <Plot
      data={(figure.data as Plotly.Data[]) ?? []}
      layout={{
        ...layout,
        autosize: true,
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        margin: {
          l: 36,
          r: 18,
          t: 30,
          b: 34,
          ...(layout.margin ?? {})
        }
      }}
      config={{
        displayModeBar: false,
        responsive: true
      }}
      className="plot"
      useResizeHandler
      style={{ width: "100%", height }}
    />
  );
}
