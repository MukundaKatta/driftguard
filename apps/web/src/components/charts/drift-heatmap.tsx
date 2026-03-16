"use client";

import { useEffect, useRef } from "react";
import * as d3 from "d3";

interface HeatmapData {
  model: string;
  drift_type: string;
  score: number;
}

interface DriftHeatmapProps {
  data: HeatmapData[];
  width?: number;
  height?: number;
}

export function DriftHeatmap({ data, width = 600, height = 400 }: DriftHeatmapProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const margin = { top: 30, right: 30, bottom: 100, left: 140 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;

    const models = Array.from(new Set(data.map((d) => d.model)));
    const driftTypes = Array.from(new Set(data.map((d) => d.drift_type)));

    const x = d3
      .scaleBand<string>()
      .domain(driftTypes)
      .range([0, innerWidth])
      .padding(0.05);

    const y = d3
      .scaleBand<string>()
      .domain(models)
      .range([0, innerHeight])
      .padding(0.05);

    const colorScale = d3
      .scaleSequential(d3.interpolateRdYlGn)
      .domain([1, 0]); // Reversed: 0 = green (safe), 1 = red (critical)

    const g = svg
      .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    // X axis
    g.append("g")
      .attr("transform", `translate(0,${innerHeight})`)
      .call(d3.axisBottom(x))
      .selectAll("text")
      .attr("transform", "rotate(-45)")
      .style("text-anchor", "end")
      .style("font-size", "11px")
      .style("fill", "hsl(215, 16%, 47%)");

    // Y axis
    g.append("g")
      .call(d3.axisLeft(y))
      .selectAll("text")
      .style("font-size", "11px")
      .style("fill", "hsl(215, 16%, 47%)");

    // Remove axis lines
    g.selectAll(".domain").remove();
    g.selectAll(".tick line").remove();

    // Tooltip
    const tooltip = d3
      .select("body")
      .append("div")
      .style("position", "absolute")
      .style("background", "hsl(222, 84%, 4.9%)")
      .style("color", "hsl(210, 40%, 98%)")
      .style("padding", "8px 12px")
      .style("border-radius", "6px")
      .style("font-size", "12px")
      .style("pointer-events", "none")
      .style("opacity", 0)
      .style("z-index", "1000");

    // Heatmap cells
    g.selectAll("rect.cell")
      .data(data)
      .join("rect")
      .attr("class", "cell")
      .attr("x", (d) => x(d.drift_type) || 0)
      .attr("y", (d) => y(d.model) || 0)
      .attr("width", x.bandwidth())
      .attr("height", y.bandwidth())
      .attr("rx", 4)
      .attr("fill", (d) => colorScale(d.score))
      .attr("opacity", 0.85)
      .style("cursor", "pointer")
      .on("mouseover", function (event, d) {
        d3.select(this).attr("opacity", 1).attr("stroke", "#fff").attr("stroke-width", 2);
        tooltip
          .style("opacity", 1)
          .html(
            `<strong>${d.model}</strong><br/>` +
            `${d.drift_type}<br/>` +
            `Score: <strong>${d.score.toFixed(4)}</strong>`
          )
          .style("left", event.pageX + 12 + "px")
          .style("top", event.pageY - 10 + "px");
      })
      .on("mousemove", function (event) {
        tooltip
          .style("left", event.pageX + 12 + "px")
          .style("top", event.pageY - 10 + "px");
      })
      .on("mouseout", function () {
        d3.select(this).attr("opacity", 0.85).attr("stroke", "none");
        tooltip.style("opacity", 0);
      });

    // Score labels on cells
    g.selectAll("text.cell-label")
      .data(data)
      .join("text")
      .attr("class", "cell-label")
      .attr("x", (d) => (x(d.drift_type) || 0) + x.bandwidth() / 2)
      .attr("y", (d) => (y(d.model) || 0) + y.bandwidth() / 2)
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "central")
      .style("font-size", "10px")
      .style("font-weight", "600")
      .style("fill", (d) => (d.score > 0.5 ? "#fff" : "#333"))
      .style("pointer-events", "none")
      .text((d) => d.score.toFixed(2));

    // Title
    svg
      .append("text")
      .attr("x", width / 2)
      .attr("y", 16)
      .attr("text-anchor", "middle")
      .style("font-size", "13px")
      .style("font-weight", "600")
      .style("fill", "hsl(222, 84%, 4.9%)")
      .text("Drift Score Heatmap");

    return () => {
      tooltip.remove();
    };
  }, [data, width, height]);

  return (
    <svg
      ref={svgRef}
      width={width}
      height={height}
      className="overflow-visible"
    />
  );
}
