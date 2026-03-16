"use client";

import { useEffect, useRef } from "react";
import * as d3 from "d3";

interface DistributionChartProps {
  baseline: number[];
  current: number[];
  label?: string;
  width?: number;
  height?: number;
}

export function DistributionChart({
  baseline,
  current,
  label = "Feature Distribution",
  width = 500,
  height = 300,
}: DistributionChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const margin = { top: 30, right: 20, bottom: 40, left: 50 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;

    const allValues = [...baseline, ...current];
    const extent = d3.extent(allValues) as [number, number];
    const padding = (extent[1] - extent[0]) * 0.1;

    const x = d3
      .scaleLinear()
      .domain([extent[0] - padding, extent[1] + padding])
      .range([0, innerWidth]);

    // Compute kernel density estimation
    const kde = kernelDensityEstimator(kernelEpanechnikov(0.5), x.ticks(50));
    const baselineDensity = kde(baseline);
    const currentDensity = kde(current);

    const maxDensity = Math.max(
      d3.max(baselineDensity, (d) => d[1]) || 0,
      d3.max(currentDensity, (d) => d[1]) || 0
    );

    const y = d3.scaleLinear().domain([0, maxDensity * 1.1]).range([innerHeight, 0]);

    const g = svg
      .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    // Axes
    g.append("g")
      .attr("transform", `translate(0,${innerHeight})`)
      .call(d3.axisBottom(x).ticks(8))
      .selectAll("text")
      .style("font-size", "10px")
      .style("fill", "hsl(215, 16%, 47%)");

    g.append("g")
      .call(d3.axisLeft(y).ticks(5))
      .selectAll("text")
      .style("font-size", "10px")
      .style("fill", "hsl(215, 16%, 47%)");

    g.selectAll(".domain").style("stroke", "hsl(214, 32%, 91%)");
    g.selectAll(".tick line").style("stroke", "hsl(214, 32%, 91%)");

    // Baseline area
    const areaGen = d3
      .area<[number, number]>()
      .x((d) => x(d[0]))
      .y0(innerHeight)
      .y1((d) => y(d[1]))
      .curve(d3.curveBasis);

    g.append("path")
      .datum(baselineDensity)
      .attr("fill", "hsl(245, 58%, 51%)")
      .attr("fill-opacity", 0.3)
      .attr("stroke", "hsl(245, 58%, 51%)")
      .attr("stroke-width", 2)
      .attr("d", areaGen);

    // Current area
    g.append("path")
      .datum(currentDensity)
      .attr("fill", "hsl(0, 84%, 60%)")
      .attr("fill-opacity", 0.3)
      .attr("stroke", "hsl(0, 84%, 60%)")
      .attr("stroke-width", 2)
      .attr("d", areaGen);

    // Legend
    const legend = g.append("g").attr("transform", `translate(${innerWidth - 120}, 0)`);

    legend
      .append("rect")
      .attr("width", 12)
      .attr("height", 12)
      .attr("rx", 2)
      .attr("fill", "hsl(245, 58%, 51%)")
      .attr("fill-opacity", 0.5);
    legend
      .append("text")
      .attr("x", 18)
      .attr("y", 10)
      .style("font-size", "11px")
      .style("fill", "hsl(222, 47%, 11%)")
      .text("Baseline");

    legend
      .append("rect")
      .attr("y", 18)
      .attr("width", 12)
      .attr("height", 12)
      .attr("rx", 2)
      .attr("fill", "hsl(0, 84%, 60%)")
      .attr("fill-opacity", 0.5);
    legend
      .append("text")
      .attr("x", 18)
      .attr("y", 28)
      .style("font-size", "11px")
      .style("fill", "hsl(222, 47%, 11%)")
      .text("Current");

    // Title
    svg
      .append("text")
      .attr("x", width / 2)
      .attr("y", 16)
      .attr("text-anchor", "middle")
      .style("font-size", "13px")
      .style("font-weight", "600")
      .style("fill", "hsl(222, 84%, 4.9%)")
      .text(label);
  }, [baseline, current, label, width, height]);

  return <svg ref={svgRef} width={width} height={height} className="overflow-visible" />;
}

function kernelDensityEstimator(
  kernel: (v: number) => number,
  X: number[]
): (V: number[]) => [number, number][] {
  return function (V: number[]) {
    return X.map((x) => [x, d3.mean(V, (v) => kernel(x - v)) || 0]);
  };
}

function kernelEpanechnikov(k: number): (v: number) => number {
  return function (v: number) {
    v = v / k;
    return Math.abs(v) <= 1 ? (0.75 * (1 - v * v)) / k : 0;
  };
}
