"use client";

import React, { useEffect, useRef, useState } from 'react';
// import * as d3 from 'd3'; // Un-comment when D3 is installed

interface Node {
  id: string;
  type: string;
  value: string;
  reportCount: number;
}

interface Link {
  source: string;
  target: string;
}

export default function FraudNetworkGraph({ entityValue }: { entityValue?: string }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);

  useEffect(() => {
    // In a real implementation, we would fetch data from /v1/intelligence/graph?entity=${entityValue}&depth=2
    // and then render the force-directed graph using D3.js here.

    /* Example D3 Implementation outline:
    const svg = d3.select(svgRef.current);
    const width = 800;
    const height = 600;

    const simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id((d: any) => d.id))
      .force("charge", d3.forceManyBody().strength(-400))
      .force("center", d3.forceCenter(width / 2, height / 2));

    const link = svg.append("g").selectAll("line").data(links).enter().append("line");

    const node = svg.append("g").selectAll("circle").data(nodes).enter().append("circle")
      .attr("r", (d) => Math.sqrt(d.reportCount) * 5)
      .attr("fill", (d) => getColor(d.type))
      .on("click", (event, d) => setSelectedNode(d as Node));

    simulation.on("tick", () => { ... });
    */

  }, [entityValue]);

  return (
    <div className="flex border rounded shadow h-[600px]">
      <div className="flex-1 p-4 flex flex-col relative">
        <h3 className="font-bold mb-2">Entity Network Graph</h3>
        <div className="flex-1 bg-gray-50 flex items-center justify-center border rounded">
          {/* <svg ref={svgRef} width="100%" height="100%" /> */}
          <span className="text-gray-400">[D3.js Force-Directed Graph Rendering]</span>
        </div>
      </div>

      {selectedNode && (
        <div className="w-80 bg-white border-l p-4">
          <h3 className="font-bold text-lg mb-4">Entity Details</h3>
          <p className="mb-2"><strong>Value:</strong> {selectedNode.value}</p>
          <p className="mb-2"><strong>Type:</strong> {selectedNode.type}</p>
          <p className="mb-2"><strong>Reports:</strong> {selectedNode.reportCount}</p>
          <button className="mt-4 bg-red-600 text-white px-4 py-2 rounded w-full">
            Blacklist Entity
          </button>
        </div>
      )}
    </div>
  );
}
