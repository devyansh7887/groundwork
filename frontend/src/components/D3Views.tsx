"use client";

import React, { useMemo } from "react";
import * as d3 from "d3";

interface Props {
  graph: any;
  fileSizes: Record<string, number>;
  colorMap?: Record<string, string>;
  width: number;
  height: number;
}

// Helper to build hierarchy
function buildHierarchy(graph: any, fileSizes: Record<string, number>) {
  const root: any = { name: "root", children: [] };
  const map: any = { root };

  graph.files.forEach((file: string) => {
    const parts = file.split("/");
    let current = root;
    let path = "";
    parts.forEach((part, i) => {
      path = path ? `${path}/${part}` : part;
      if (!map[path]) {
        const node = { name: part, path, children: [], value: 0 };
        map[path] = node;
        current.children.push(node);
      }
      current = map[path];
      if (i === parts.length - 1) {
        current.value = fileSizes[file] || 1000;
      }
    });
  });

  return d3.hierarchy(root)
    .sum((d: any) => d.value)
    .sort((a: any, b: any) => b.value - a.value);
}

export function TreemapView({ graph, fileSizes, colorMap, width, height }: Props) {
  const data = useMemo(() => {
    if (!graph?.files?.length) return null;
    const h = buildHierarchy(graph, fileSizes);
    const treemap = d3.treemap().size([width, height]).padding(1).round(true);
    return treemap(h);
  }, [graph, fileSizes, width, height]);

  if (!data) return null;

  return (
    <svg width={width} height={height} className="bg-[#0d1117]">
      {data.leaves().map((leaf: any, i: number) => {
        return (
          <g key={i} transform={`translate(${leaf.x0},${leaf.y0})`}>
            <rect 
              width={leaf.x1 - leaf.x0} 
              height={leaf.y1 - leaf.y0} 
              fill={colorMap?.[leaf.data.path] || "#21262d"} 
              stroke="#0d1117" 
              className="hover:opacity-80 transition-opacity cursor-pointer"
            />
            {leaf.x1 - leaf.x0 > 30 && leaf.y1 - leaf.y0 > 15 && (
              <text x={4} y={14} fill="#8b949e" fontSize="10px" fontFamily="monospace" className="pointer-events-none">
                {leaf.data.name}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export function TreeView({ graph, fileSizes, colorMap, width, height }: Props) {
  const data = useMemo(() => {
    if (!graph?.files?.length) return null;
    const h = buildHierarchy(graph, fileSizes);
    const tree = d3.tree().size([height - 40, width - 150]);
    return tree(h);
  }, [graph, fileSizes, width, height]);

  if (!data) return null;

  return (
    <svg width={width} height={height} className="bg-[#0d1117] overflow-visible">
      <g transform="translate(50, 20)">
        {data.links().map((link: any, i: number) => (
          <path
            key={`link-${i}`}
            d={d3.linkHorizontal()({
              source: [link.source.x, link.source.y] as any,
              target: [link.target.x, link.target.y] as any
            }) || undefined}
            fill="none"
            stroke="#30363d"
            strokeWidth={1}
          />
        ))}
        {data.descendants().map((node: any, i: number) => (
          <g key={`node-${i}`} transform={`translate(${node.y},${node.x})`}>
            <circle r={node.children ? 4 : 3} fill={node.children ? "#30363d" : (colorMap?.[node.data.path] || "#58a6ff")} />
            <text
              dy="0.31em"
              x={node.children ? -6 : 6}
              textAnchor={node.children ? "end" : "start"}
              fill="#c9d1d9"
              fontSize="10px"
              fontFamily="monospace"
            >
              {node.data.name}
            </text>
          </g>
        ))}
      </g>
    </svg>
  );
}

export function ClusterView({ graph, fileSizes, colorMap, width, height }: Props) {
  const data = useMemo(() => {
    if (!graph?.files?.length) return null;
    const h = buildHierarchy(graph, fileSizes);
    const cluster = d3.cluster().size([height - 40, width - 150]);
    return cluster(h);
  }, [graph, fileSizes, width, height]);

  if (!data) return null;

  return (
    <svg width={width} height={height} className="bg-[#0d1117] overflow-visible">
      <g transform="translate(50, 20)">
        {data.links().map((link: any, i: number) => (
          <path
            key={`link-${i}`}
            d={d3.linkHorizontal()({
              source: [link.source.x, link.source.y] as any,
              target: [link.target.x, link.target.y] as any
            }) || undefined}
            fill="none"
            stroke="#30363d"
            strokeWidth={1}
            opacity={0.6}
          />
        ))}
        {data.descendants().map((node: any, i: number) => (
          <g key={`node-${i}`} transform={`translate(${node.y},${node.x})`}>
            <circle r={3} fill={colorMap?.[node.data.path] || "#bc8cff"} />
            <text
              dy="0.31em"
              x={node.children ? -6 : 6}
              textAnchor={node.children ? "end" : "start"}
              fill="#8b949e"
              fontSize="9px"
              fontFamily="monospace"
            >
              {node.data.name}
            </text>
          </g>
        ))}
      </g>
    </svg>
  );
}

export function MatrixView({ graph, fileSizes, colorMap, width, height }: Props) {
  const data = useMemo(() => {
    if (!graph?.files?.length) return null;
    const files = graph.files;
    const n = files.length;
    const cap = Math.min(n, 50);
    const subset = files.slice(0, cap);
    
    const matrix = Array.from({ length: cap }, () => new Array(cap).fill(0));
    graph.imports.forEach((imp: any) => {
      const srcIdx = subset.indexOf(imp.source);
      const tgtMod = imp.target_module?.replace(/\./g, "/");
      const tgtIdx = subset.findIndex((f: string) => f.includes(tgtMod));
      if (srcIdx >= 0 && tgtIdx >= 0) {
        matrix[srcIdx][tgtIdx] = 1;
      }
    });
    
    const cellWidth = Math.min((width - 150) / cap, (height - 150) / cap);
    
    return { subset, matrix, cap, cellWidth };
  }, [graph, width, height]);

  if (!data) return null;

  return (
    <div style={{ width, height, overflow: "auto" }}>
      <svg width={Math.max(width, data.cap * data.cellWidth + 150)} height={Math.max(height, data.cap * data.cellWidth + 150)} className="bg-[#0d1117]">
        <g transform="translate(150, 150)">
          {data.matrix.map((row: any, i: number) => (
            <g key={`row-${i}`} transform={`translate(0, ${i * data.cellWidth})`}>
              {row.map((val: number, j: number) => (
                <rect
                  key={`cell-${j}`}
                  x={j * data.cellWidth}
                  width={data.cellWidth - 1}
                  height={data.cellWidth - 1}
                  fill={val ? (colorMap?.[data.subset[i]] || "#58a6ff") : "#21262d"}
                  stroke="#161b22"
                />
              ))}
            </g>
          ))}
          {data.subset.map((f: string, i: number) => (
            <g key={`lbl-${i}`}>
              <text x={-5} y={i * data.cellWidth + data.cellWidth / 2} dy="0.31em" textAnchor="end" fontSize="10px" fill={colorMap?.[f] || "#8b949e"} fontFamily="monospace">
                {f.split("/").pop()}
              </text>
              <text transform={`translate(${i * data.cellWidth + data.cellWidth / 2}, -5) rotate(-90)`} dy="0.31em" textAnchor="start" fontSize="10px" fill={colorMap?.[f] || "#8b949e"} fontFamily="monospace">
                {f.split("/").pop()}
              </text>
            </g>
          ))}
        </g>
      </svg>
    </div>
  );
}

export function BundleView({ graph, fileSizes, colorMap, width, height }: Props) {
  const data = useMemo(() => {
    if (!graph?.files?.length) return null;
    const h = buildHierarchy(graph, fileSizes);
    const radius = Math.min(width, height) / 2 - 120;
    
    const cluster = d3.cluster().size([2 * Math.PI, radius]);
    const root = cluster(h) as d3.HierarchyPointNode<any>;

    // Create a map to quickly look up nodes by path for edge routing
    const nodeMap = new Map<string, d3.HierarchyPointNode<any>>();
    root.each(d => nodeMap.set(d.data.path, d));

    // Create edge connections
    const links: { source: d3.HierarchyPointNode<any>; target: d3.HierarchyPointNode<any> }[] = [];
    graph.imports.forEach((imp: any) => {
      const sourceNode = nodeMap.get(imp.source);
      const tgtMod = imp.target_module?.replace(/\./g, "/");
      const targetPath = graph.files.find((f: string) => f.includes(tgtMod));
      if (sourceNode && targetPath) {
        const targetNode = nodeMap.get(targetPath);
        if (targetNode && sourceNode !== targetNode) {
          links.push({ source: sourceNode, target: targetNode });
        }
      }
    });

    return { root, links, radius };
  }, [graph, fileSizes, width, height]);

  if (!data) return null;

  const line = d3.lineRadial<d3.HierarchyPointNode<any>>()
    .curve(d3.curveBundle.beta(0.85))
    .radius(d => d.y)
    .angle(d => d.x);

  return (
    <svg width={width} height={height} className="bg-[#0d1117] overflow-visible">
      <g transform={`translate(${width / 2},${height / 2})`}>
        {/* Draw edges */}
        {data.links.map((link, i) => (
          <path
            key={`bundle-${i}`}
            d={line(link.source.path(link.target)) as string}
            fill="none"
            stroke="#58a6ff"
            strokeWidth={1}
            strokeOpacity={0.2}
            className="hover:stroke-[#79c0ff] hover:stroke-opacity-100 transition-all duration-300"
          />
        ))}
        
        {/* Draw leaf nodes and labels */}
        {data.root.leaves().map((node, i) => {
          const angle = (node.x * 180) / Math.PI - 90;
          return (
            <g key={`leaf-${i}`} transform={`rotate(${angle}) translate(${node.y},0)`}>
              <circle r={3} fill="#bc8cff" />
              <text
                dy="0.31em"
                x={node.x < Math.PI ? 6 : -6}
                textAnchor={node.x < Math.PI ? "start" : "end"}
                transform={node.x >= Math.PI ? "rotate(180)" : ""}
                fill="#8b949e"
                fontSize="9px"
                fontFamily="monospace"
                className="hover:fill-[#c9d1d9] cursor-default"
              >
                {node.data.name}
              </text>
            </g>
          );
        })}
      </g>
    </svg>
  );
}

export function BlockDiagramView({ graph, fileSizes, colorMap, width, height }: Props) {
  const data = useMemo(() => {
    if (!graph?.files?.length) return null;
    const h = buildHierarchy(graph, fileSizes);
    
    // Use an icicle (rectangular partition) layout for block diagrams
    const partition = d3.partition().size([height, width - 150]).padding(1);
    return partition(h) as d3.HierarchyRectangularNode<any>;
  }, [graph, fileSizes, width, height]);

  if (!data) return null;

  return (
    <svg width={width} height={height} className="bg-[#0d1117] overflow-visible">
      <g transform="translate(10, 10)">
        {data.descendants().map((node, i) => {
          // Calculate folder color
          const isLeaf = !node.children;
          return (
            <g key={`block-${i}`} transform={`translate(${node.y0},${node.x0})`}>
              <rect
                width={Math.max(1, node.y1 - node.y0 - 2)}
                height={Math.max(1, node.x1 - node.x0)}
                fill={isLeaf ? "#21262d" : "#161b22"}
                stroke="#30363d"
                strokeWidth={1}
                className="hover:stroke-[#58a6ff] hover:fill-[#30363d] transition-colors cursor-pointer"
              />
              {node.x1 - node.x0 > 15 && node.y1 - node.y0 > 30 && (
                <text
                  x={4}
                  y={12}
                  fill={isLeaf ? "#8b949e" : "#58a6ff"}
                  fontSize="10px"
                  fontFamily="monospace"
                  className="pointer-events-none"
                >
                  {node.data.name}
                </text>
              )}
            </g>
          );
        })}
      </g>
    </svg>
  );
}
