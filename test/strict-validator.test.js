import assert from "node:assert/strict";
import test from "node:test";
import { validatePptdProject } from "../skills/ansatz-slide/scripts/local-export/validate-pptd.mjs";

function project(elements, extraPage = {}) {
  return {
    manifest: {
      version: "v2",
      title: "validator test",
      size: [960, 540],
      pages: ["pages/1.page"],
    },
    pages: [{
      path: "pages/1.page",
      data: { elements, ...extraPage },
    }],
  };
}

const shape = {
  elementId: "box",
  elementType: "shape",
  bounds: [20, 20, 100, 80],
  shapeName: "rect",
  fill: { type: "solid", color: "#FF0000" },
};

test("accepts a representative valid page containing all seven element types", () => {
  const value = project([
    shape,
    {
      elementId: "text",
      elementType: "text",
      bounds: [20, 120, 200, 40],
      content: { text: "hello", fontSize: 18 },
    },
    {
      elementId: "line",
      elementType: "line",
      bounds: [20, 180, 200, 30],
      viewBox: [200, 30],
      points: "0,15 200,15",
      border: { style: "solid", width: 1, color: "#000000" },
    },
    {
      elementId: "image",
      elementType: "image",
      bounds: [240, 20, 100, 80],
      src: "data:image/png;base64,AA==",
    },
    {
      elementId: "icon",
      elementType: "icon",
      bounds: [360, 20, 40, 40],
      iconName: "fas:house",
    },
    {
      elementId: "table",
      elementType: "table",
      bounds: [20, 240, 300, 160],
      columnWidths: [0.5, 0.5],
      rowHeights: [0.5, 0.5],
      rows: [[{ text: "A" }, { text: "B" }], [{ text: "1" }, { text: "2" }]],
    },
    {
      elementId: "chart",
      elementType: "chart",
      bounds: [360, 120, 400, 280],
      data: { cols: ["month", "value"], rows: [["Jan", 1], ["Feb", 2]] },
      series: [{ type: "bar", encode: { x: "month", y: "value" } }],
    },
  ]);
  assert.deepEqual(validatePptdProject(value), { ok: true, pageCount: 1 });
});

test("rejects the seven previously silent negative cases", () => {
  const cases = {
    "bad-animation-target": project([shape], {
      animations: [{ elementId: "missing", effect: "fade-in" }],
    }),
    "bad-custom-shape": project([{
      ...shape,
      shapeName: "custom",
    }]),
    "bad-image-crop": project([{
      elementId: "image",
      elementType: "image",
      bounds: [20, 20, 100, 80],
      src: "data:image/png;base64,AA==",
      crop: { left: 0.6, right: 0.5 },
    }]),
    "bad-table-widths": project([{
      elementId: "table",
      elementType: "table",
      bounds: [20, 20, 400, 200],
      columnWidths: [0.2, 0.2],
      rowHeights: [1],
      rows: [[{ text: "A" }, { text: "B" }]],
    }]),
    "duplicate-column": project([{
      elementId: "chart",
      elementType: "chart",
      bounds: [40, 40, 800, 420],
      data: { cols: ["x", "x"], rows: [["A", 1]] },
      series: [{ type: "bar", encode: { x: "x", y: "x" } }],
    }]),
    "row-length": project([{
      elementId: "chart",
      elementType: "chart",
      bounds: [40, 40, 800, 420],
      data: { cols: ["x", "y"], rows: [["A"]] },
      series: [{ type: "bar", encode: { x: "x", y: "y" } }],
    }]),
    "unknown-encode": project([{
      elementId: "chart",
      elementType: "chart",
      bounds: [40, 40, 800, 420],
      data: { cols: ["x", "y"], rows: [["A", 1]] },
      series: [{ type: "bar", encode: { x: "missing", y: "y" } }],
    }]),
  };
  for (const [name, value] of Object.entries(cases)) {
    assert.throws(
      () => validatePptdProject(value),
      (error) => error.name === "PptdValidationError" && /PPTD validation failed/.test(error.message),
      name,
    );
  }
});

test("rejects constructs proven to be dropped or visually empty", () => {
  const unsupportedCharts = ["candlestick", "heatmap", "treemap", "sunburst", "sankey"];
  for (const type of unsupportedCharts) {
    const value = project([{
      elementId: `chart-${type}`,
      elementType: "chart",
      bounds: [40, 40, 800, 420],
      data: { cols: ["x", "y"], rows: [["A", 1]] },
      series: [{ type, encode: {} }],
    }]);
    assert.throws(
      () => validatePptdProject(value),
      (error) => error.name === "PptdValidationError" && /externally rendered PNG\/SVG/.test(error.message),
      type,
    );
  }

  for (const transform of ["rotation", "opacity", "flip"]) {
    const transformedText = {
      elementId: "text",
      elementType: "text",
      bounds: [20, 20, 200, 80],
      content: { text: "must not disappear" },
      [transform]: transform === "rotation" ? 20 : transform === "opacity" ? 0.5 : [true, false],
    };
    assert.throws(
      () => validatePptdProject(project([transformedText])),
      (error) => error.name === "PptdValidationError" && /not preserved by the local PPTX writer/.test(error.message),
      transform,
    );
  }
});

test("direct JSON protocol data is rejected for a semantic error", () => {
  const input = JSON.stringify(project([{
    ...shape,
    elementId: "duplicate",
  }, {
    ...shape,
    elementId: "duplicate",
  }]));
  // This test exercises the exported validator directly; the shell-level
  // export smoke test verifies that no output file is written after this gate.
  assert.throws(() => validatePptdProject(JSON.parse(input)), /duplicate elementId/);
});

test("scatter and bubble encodings reject missing or non-numeric channels", () => {
  const invalidSeries = [
    {
      name: "scatter missing y",
      data: { cols: ["x", "y"], rows: [[1, 2]] },
      series: { type: "scatter", encode: { x: "x" } },
      message: /missing required field "y"/,
    },
    {
      name: "bubble missing size",
      data: { cols: ["x", "y", "size"], rows: [[1, 2, 3]] },
      series: { type: "bubble", encode: { x: "x", y: "y" } },
      message: /missing required field "size"/,
    },
    {
      name: "bubble non-numeric size",
      data: { cols: ["x", "y", "size"], rows: [[1, 2, "large"]] },
      series: { type: "bubble", encode: { x: "x", y: "y", size: "size" } },
      message: /numeric channel contains a non-numeric value/,
    },
  ];

  for (const { name, data, series, message } of invalidSeries) {
    const value = project([{
      elementId: "chart",
      elementType: "chart",
      bounds: [40, 40, 800, 420],
      data,
      series: [series],
    }]);
    assert.throws(() => validatePptdProject(value), message, name);
  }
});

test("effect-specific animation fields are mandatory and scoped", () => {
  const invalidAnimations = [
    [{ elementId: "box", effect: "motion-path" }, /missing required field "path"/],
    [{ elementId: "box", effect: "motion-path", path: "M 10 10 L 20 20" }, /must start with M 0 0/],
    [{ elementId: "box", effect: "fill-color" }, /missing required field "color"/],
    [{ elementId: "box", effect: "fade-in", color: "#FF0000" }, /color is only valid/],
  ];
  for (const [animation, message] of invalidAnimations) {
    assert.throws(
      () => validatePptdProject(project([shape], { animations: [animation] })),
      message,
    );
  }
});

test("icon names require an explicit supported-family prefix", () => {
  for (const iconName of ["lightbulb", "foo:lightbulb", "fas:", "fas:a:b"]) {
    const value = project([{
      elementId: "icon",
      elementType: "icon",
      bounds: [20, 20, 40, 40],
      iconName,
    }]);
    assert.throws(() => validatePptdProject(value), /iconName must use fas:name, far:name, or fab:name/);
  }
});
