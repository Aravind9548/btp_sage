/* Shared benchmark numbers + chart helpers, used by results.html.
   Every value here traces to results/experiment_results.csv via
   slides/key_numbers.md — see that file for the exact groupby/computation. */

var PATHS = {
  path_a:      { label:"A: Orchestration",  short:"A",      colorVar:"--series-a" },
  path_b:      { label:"B: Choreography",   short:"B",      colorVar:"--series-b" },
  path_d:      { label:"D: Graph-aware",    short:"D",      colorVar:"--series-d" },
  path_d_lifo: { label:"D: LIFO ablation",  short:"D-LIFO", colorVar:"--series-dl" }
};

/* One real saga run per path, captured by actually executing run_path_a /
   run_path_b / run_path_d(scheduler="dependency_aware"|"lifo") against the
   base 3-step scenario (no extra dag_width steps) and reading back
   EventLog.rows_for(saga_id). Not simulated, not hand-tuned — these are the
   literal timestamps and thread interleaving one real process produced. */
var REAL_RUN = {
  path_a: [
    {t:0.02,step:null,event:"saga_started"},{t:0.03,step:"Order",event:"execute_started"},
    {t:100.31,step:"Order",event:"execute_finished"},{t:100.39,step:"Notification",event:"execute_started"},
    {t:150.79,step:"Notification",event:"execute_finished"},{t:150.87,step:"Payment",event:"execute_started"},
    {t:451.3,step:"Payment",event:"execute_finished"},{t:451.35,step:"Inventory",event:"failure_detected"},
    {t:451.36,step:null,event:"rollback_started"},{t:451.4,step:"Payment",event:"compensate_started"},
    {t:1251.72,step:"Payment",event:"compensate_finished"},{t:1251.77,step:"Notification",event:"compensate_started"},
    {t:1352.34,step:"Notification",event:"compensate_finished"},{t:1352.4,step:"Order",event:"compensate_started"},
    {t:1502.93,step:"Order",event:"compensate_finished"},{t:1502.96,step:null,event:"rollback_finished"}
  ],
  path_b: [
    {t:2.73,step:null,event:"saga_started"},{t:2.76,step:"Order",event:"execute_started"},
    {t:103.35,step:"Order",event:"execute_finished"},{t:103.4,step:"Notification",event:"execute_started"},
    {t:153.73,step:"Notification",event:"execute_finished"},{t:153.78,step:"Payment",event:"execute_started"},
    {t:453.98,step:"Payment",event:"execute_finished"},{t:454.01,step:"Inventory",event:"failure_detected"},
    {t:454.03,step:null,event:"rollback_started"},{t:455.15,step:"Order",event:"compensate_started"},
    {t:455.37,step:"Notification",event:"compensate_started"},{t:455.62,step:"Payment",event:"compensate_started"},
    {t:555.86,step:"Notification",event:"compensate_finished"},{t:605.63,step:"Order",event:"compensate_finished"},
    {t:1256.34,step:"Payment",event:"compensate_finished"},{t:1256.46,step:null,event:"rollback_finished"}
  ],
  path_d: [
    {t:0.04,step:null,event:"saga_started"},{t:0.05,step:"Order",event:"execute_started"},
    {t:100.56,step:"Order",event:"execute_finished"},{t:100.6,step:"Notification",event:"execute_started"},
    {t:150.81,step:"Notification",event:"execute_finished"},{t:150.84,step:"Payment",event:"execute_started"},
    {t:450.93,step:"Payment",event:"execute_finished"},{t:450.96,step:"Inventory",event:"failure_detected"},
    {t:450.97,step:null,event:"rollback_started"},{t:451.52,step:"Order",event:"elected_orchestrator"},
    {t:452.43,step:"Payment",event:"compensate_started"},{t:452.64,step:"Order",event:"compensate_started"},
    {t:603.05,step:"Order",event:"compensate_finished"},{t:1252.63,step:"Payment",event:"compensate_finished"},
    {t:1252.85,step:"Notification",event:"compensate_started"},{t:1353.29,step:"Notification",event:"compensate_finished"},
    {t:1353.52,step:null,event:"rollback_finished"}
  ],
  path_d_lifo: [
    {t:0.03,step:null,event:"saga_started"},{t:0.03,step:"Order",event:"execute_started"},
    {t:100.48,step:"Order",event:"execute_finished"},{t:100.53,step:"Notification",event:"execute_started"},
    {t:151.18,step:"Notification",event:"execute_finished"},{t:151.2,step:"Payment",event:"execute_started"},
    {t:451.63,step:"Payment",event:"execute_finished"},{t:451.69,step:"Inventory",event:"failure_detected"},
    {t:451.7,step:null,event:"rollback_started"},{t:452.51,step:"Order",event:"elected_orchestrator"},
    {t:453.61,step:"Payment",event:"compensate_started"},{t:1253.78,step:"Payment",event:"compensate_finished"},
    {t:1253.83,step:"Notification",event:"compensate_started"},{t:1354.14,step:"Notification",event:"compensate_finished"},
    {t:1354.19,step:"Order",event:"compensate_started"},{t:1504.48,step:"Order",event:"compensate_finished"},
    {t:1504.62,step:null,event:"rollback_finished"}
  ]
};
var REAL_RUN_TOTAL_MS = 1550;

/* ---------------- theme toggle (shared across all pages) ---------------- */
function initThemeToggle(btnId){
  var KEY = "ccr-theme";
  var btn = document.getElementById(btnId);
  var ICON = { system:"◐", light:"☀", dark:"☾" };
  function apply(mode){
    if (mode === "system") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", mode);
    if (btn) btn.textContent = ICON[mode];
    if (btn) btn.title = "Theme: " + mode + " (click to change)";
  }
  var saved = "system";
  try { saved = localStorage.getItem(KEY) || "system"; } catch(e){}
  apply(saved);
  if (!btn) return;
  var order = ["system","light","dark"];
  btn.addEventListener("click", function(){
    var cur = order.indexOf(saved);
    saved = order[(cur+1) % order.length];
    try { localStorage.setItem(KEY, saved); } catch(e){}
    apply(saved);
  });
}

var DATA = {
  dag_width: {
    path_a:{1:1252.5,2:1453.3,3:1654.4,4:1854.1,5:2054.4,6:2254.3,7:2456.3,8:2657.8},
    path_b:{1:819.3,2:805.5,3:804.1,4:810.7,5:802.4,6:801.5,7:801.9,8:801.9},
    path_d:{1:930.7,2:919.2,3:907.1,4:903.6,5:904.0,6:910.0,7:907.1,8:922.7}
  },
  lifo_ablation: {
    path_d:{1:919.4,2:915.7,3:904.8,4:906.2,5:921.4,6:907.5,7:904.6,8:907.3},
    path_d_lifo:{1:1263.4,2:1470.2,3:1660.4,4:1856.5,5:2062.8,6:2264.1,7:2473.8,8:2669.0}
  },
  cluster_size: {
    path_a:{4:1051.9,5:1256.7,6:1462.1,7:1661.3,8:1867.8,9:2064.2,10:2265.2,11:2458.7,12:2679.7,13:2860.2,14:3063.7,15:3286.8,16:3457.9},
    path_b:{4:805.4,5:808.9,6:806.4,7:811.0,8:810.6,9:811.4,10:822.3,11:817.1,12:817.7,13:818.3,14:823.0,15:819.8,16:822.9},
    path_d:{4:911.2,5:987.6,6:914.0,7:917.9,8:920.2,9:979.6,10:915.2,11:916.5,12:916.7,13:920.2,14:922.2,15:920.8,16:924.1}
  },
  concurrency: {
    path_d:{1:903.8,2:905.1,3:906.7,4:912.0,5:911.5,6:911.6,7:911.4,8:906.7,9:914.5,10:910.2,11:908.3,12:916.2,13:915.8,14:915.9,15:949.2,16:910.7,17:910.7,18:918.7,19:919.3,20:915.4}
  }
};

var TABLE1 = {
  path_a:{mean:1954.6,std:460.3,vs_b:2.43},
  path_b:{mean:805.9,std:11.2,vs_b:1.00},
  path_d:{mean:913.0,std:18.6,vs_b:1.13},
  path_d_lifo:{mean:1965.0,std:461.8,vs_b:2.44}
};
var CORRECT = { path_a:100, path_b:0, path_d:100, path_d_lifo:100 };
var WHY = {
  path_b:"No mechanism makes one reactor wait on another — wrong by construction, not by chance.",
  path_d:"Graph-aware dispatch makes the one required wait (Payment→Notification) explicit.",
  path_a:"Strict reverse-order compensation happens to satisfy the one edge on this schedule.",
  path_d_lifo:"Same guarantee as D, paid for by giving up all parallelism."
};
var TABLE2 = {
  path_a:{expected:1250.0,measured:1252.5,deviation_pct:0.20},
  path_b:{expected:800.0,measured:819.3,deviation_pct:2.41},
  path_d:{expected:900.0,measured:930.7,deviation_pct:3.41}
};

function fmt(n, d){ d = d===undefined?0:d; return Number(n).toLocaleString('en-US',{minimumFractionDigits:d, maximumFractionDigits:d}); }

/* ---------------- SVG line chart (dependency-free) ---------------- */
var CHART_W = 880, CHART_H = 340;
var CHART_M = { top:16, right:104, bottom:34, left:52 };
var chartState = {};

function niceTicks(min, max, count){
  count = count || 5;
  var range = (max - min) || 1;
  var rawStep = range / (count - 1);
  var mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  var norm = rawStep / mag, step;
  if (norm < 1.5) step = 1*mag; else if (norm < 3) step = 2*mag; else if (norm < 7) step = 5*mag; else step = 10*mag;
  var niceMax = Math.ceil(max / step) * step;
  var ticks = [];
  for (var v = 0; v <= niceMax + 1e-6; v += step) ticks.push(Math.round(v));
  return ticks;
}

function svgEl(tag, attrs){
  var e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (var k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}

function renderSweepChart(sweepKey, meta, svgId, legendId, captionId, tooltipId, wrapId){
  var plotW = CHART_W - CHART_M.left - CHART_M.right;
  var plotH = CHART_H - CHART_M.top - CHART_M.bottom;
  var svg = document.getElementById(svgId);
  svg.innerHTML = "";

  var firstPathData = DATA[sweepKey][meta.paths[0]];
  var xDense = Object.keys(firstPathData).map(Number).sort(function(a,b){return a-b;});
  var xMin = xDense[0], xMax = xDense[xDense.length-1];
  var yMax = 0;
  meta.paths.forEach(function(pk){
    var vals = DATA[sweepKey][pk];
    Object.keys(vals).forEach(function(k){ if (vals[k] > yMax) yMax = vals[k]; });
  });
  var yTicks = niceTicks(0, yMax * 1.08, 5);
  var yMaxNice = yTicks[yTicks.length - 1];

  function xScale(x){ return CHART_M.left + (x - xMin) / (xMax - xMin) * plotW; }
  function yScale(y){ return CHART_M.top + (1 - y / yMaxNice) * plotH; }

  yTicks.forEach(function(t){
    var y = yScale(t);
    svg.appendChild(svgEl("line", { x1:CHART_M.left, x2:CHART_W-CHART_M.right, y1:y, y2:y, stroke:"var(--rule)", "stroke-width":1 }));
    var lbl = svgEl("text", { x:CHART_M.left-10, y:y+4, "text-anchor":"end", class:"mono", style:"font-size:11px;fill:var(--ink-muted)" });
    lbl.textContent = t;
    svg.appendChild(lbl);
  });
  svg.appendChild(svgEl("line", { x1:CHART_M.left, x2:CHART_M.left, y1:CHART_M.top, y2:CHART_H-CHART_M.bottom, stroke:"var(--rule-strong)", "stroke-width":1 }));
  svg.appendChild(svgEl("line", { x1:CHART_M.left, x2:CHART_W-CHART_M.right, y1:CHART_H-CHART_M.bottom, y2:CHART_H-CHART_M.bottom, stroke:"var(--rule-strong)", "stroke-width":1 }));

  meta.xTicks.forEach(function(t){
    var x = xScale(t);
    var lbl = svgEl("text", { x:x, y:CHART_H-CHART_M.bottom+20, "text-anchor":"middle", class:"mono", style:"font-size:11px;fill:var(--ink-muted)" });
    lbl.textContent = t;
    svg.appendChild(lbl);
  });
  var xLabel = svgEl("text", { x:CHART_M.left+plotW/2, y:CHART_H-2, "text-anchor":"middle", style:"font-size:12px;fill:var(--ink-2)" });
  xLabel.textContent = meta.xLabel;
  svg.appendChild(xLabel);
  var yLabel = svgEl("text", { x:-(CHART_M.top+plotH/2), y:14, "text-anchor":"middle", transform:"rotate(-90)", style:"font-size:12px;fill:var(--ink-2)" });
  yLabel.textContent = "Mean makespan (ms)";
  svg.appendChild(yLabel);

  var series = [];
  meta.paths.forEach(function(pk){
    var p = PATHS[pk];
    var vals = DATA[sweepKey][pk];
    var pts = xDense.map(function(x){ return { x:x, y:vals[x] }; });
    var d = pts.map(function(pt, i){ return (i===0?"M":"L") + xScale(pt.x).toFixed(1) + "," + yScale(pt.y).toFixed(1); }).join(" ");
    var color = "var(" + p.colorVar + ")";
    svg.appendChild(svgEl("path", { d:d, fill:"none", stroke:color, "stroke-width":2.5, "stroke-linecap":"round", "stroke-linejoin":"round" }));
    pts.forEach(function(pt, i){
      var r = (i === pts.length-1) ? 4.5 : 3;
      svg.appendChild(svgEl("circle", { cx:xScale(pt.x), cy:yScale(pt.y), r:r, fill:color }));
    });
    var last = pts[pts.length-1];
    var lx = xScale(last.x) + 9, ly = yScale(last.y);
    var elbl = svgEl("text", { x:lx, y:ly+4, class:"mono", style:"font-size:11.5px;font-weight:600;fill:var(--ink)" });
    elbl.textContent = p.short + " " + Math.round(last.y);
    svg.appendChild(elbl);
    series.push({ key:pk, label:p.label, color:color, pts:pts });
  });

  var overlay = svgEl("rect", { x:CHART_M.left, y:CHART_M.top, width:plotW, height:plotH, fill:"transparent", cursor:"crosshair" });
  svg.appendChild(overlay);
  var crosshair = svgEl("line", { x1:0, x2:0, y1:CHART_M.top, y2:CHART_H-CHART_M.bottom, stroke:"var(--ink-muted)", "stroke-width":1, "stroke-dasharray":"3,3", opacity:0, "pointer-events":"none" });
  svg.appendChild(crosshair);

  chartState = { xDense:xDense, xScale:xScale, series:series, crosshair:crosshair, plotW:plotW, sweepKey:sweepKey, svgId:svgId, tooltipId:tooltipId, wrapId:wrapId };

  overlay.addEventListener("mousemove", onSweepHover);
  overlay.addEventListener("mouseleave", function(){
    crosshair.setAttribute("opacity", 0);
    document.getElementById(tooltipId).style.opacity = 0;
  });

  var legend = document.getElementById(legendId);
  legend.innerHTML = "";
  series.forEach(function(s){
    var item = document.createElement("div");
    item.className = "item";
    item.innerHTML = '<span class="sw" style="background:' + s.color + '"></span>' + s.label;
    legend.appendChild(item);
  });

  document.getElementById(captionId).textContent = meta.caption;
}

function onSweepHover(e){
  var svg = document.getElementById(chartState.svgId);
  var rect = svg.getBoundingClientRect();
  var relX = (e.clientX - rect.left) / rect.width;
  var svgX = relX * CHART_W;
  var xMin = chartState.xDense[0], xMax = chartState.xDense[chartState.xDense.length-1];
  var dataX = xMin + (svgX - CHART_M.left) / chartState.plotW * (xMax - xMin);
  var nearest = chartState.xDense.reduce(function(a,b){ return Math.abs(b-dataX) < Math.abs(a-dataX) ? b : a; });
  var cx = chartState.xScale(nearest);
  chartState.crosshair.setAttribute("x1", cx); chartState.crosshair.setAttribute("x2", cx);
  chartState.crosshair.setAttribute("opacity", 1);

  var tt = document.getElementById(chartState.tooltipId);
  var wrapRect = document.getElementById(chartState.wrapId).getBoundingClientRect();
  var rows = chartState.series.map(function(s){
    var pt = s.pts.filter(function(p){ return p.x === nearest; })[0];
    return '<div class="trow"><span class="sw" style="background:' + s.color + '"></span><b>' + s.label + '</b>&nbsp;' + Math.round(pt.y) + ' ms</div>';
  }).join("");
  var xLbl = chartState.sweepKey === "dag_width" ? "width " + nearest : chartState.sweepKey === "cluster_size" ? nearest + " services" : "level " + nearest;
  tt.innerHTML = '<div style="margin-bottom:4px;color:var(--ink-muted)">' + xLbl + "</div>" + rows;
  tt.style.opacity = 1;
  var px = (cx / CHART_W) * rect.width;
  var left = px + 14, top = (rect.top - wrapRect.top) + 6;
  if (left + 170 > rect.width) left = px - 170;
  tt.style.left = left + "px";
  tt.style.top = top + "px";
}
