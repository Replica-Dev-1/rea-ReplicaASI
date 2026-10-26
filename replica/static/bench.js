/* bench.js - measures THIS device, in this tab, when the visitor presses the button. Nothing is sent unless a host
   chooses to report it. CPU: a 256x256 float32 matrix multiply in JS. GPU: a 1024x1024 tiled matrix multiply in a
   WebGPU compute shader, 8 rounds. GFLOPS = 2*n^3*rounds / seconds. Browser numbers run well below a device's spec sheet. */
(function (root) {
  "use strict";

  function cpu() {
    const n = 256, a = new Float32Array(n * n), b = new Float32Array(n * n), c = new Float32Array(n * n);
    for (let i = 0; i < n * n; i++) { a[i] = (i % 7) * 0.1; b[i] = (i % 5) * 0.2; }
    let rounds = 0; const t0 = performance.now();
    while (performance.now() - t0 < 600) {
      for (let i = 0; i < n; i++) for (let k = 0; k < n; k++) { const x = a[i * n + k]; for (let j = 0; j < n; j++) c[i * n + j] += x * b[k * n + j]; }
      rounds++;
    }
    const s = (performance.now() - t0) / 1000;
    return (2 * n * n * n * rounds) / s / 1e9;
  }

  const WGSL = `
@group(0) @binding(0) var<storage, read> A : array<f32>;
@group(0) @binding(1) var<storage, read> B : array<f32>;
@group(0) @binding(2) var<storage, read_write> C : array<f32>;
const N : u32 = 1024u;
var<workgroup> ta : array<f32, 256>;
var<workgroup> tb : array<f32, 256>;
@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) g : vec3<u32>, @builtin(local_invocation_id) l : vec3<u32>) {
  var acc = 0.0;
  for (var t = 0u; t < N / 16u; t++) {
    ta[l.y * 16u + l.x] = A[g.y * N + t * 16u + l.x];
    tb[l.y * 16u + l.x] = B[(t * 16u + l.y) * N + g.x];
    workgroupBarrier();
    for (var k = 0u; k < 16u; k++) { acc += ta[l.y * 16u + k] * tb[k * 16u + l.x]; }
    workgroupBarrier();
  }
  C[g.y * N + g.x] = acc;
}`;

  async function gpu() {
    if (!navigator.gpu) return null;
    const ad = await navigator.gpu.requestAdapter({ powerPreference: "high-performance" });
    if (!ad) return null;
    const dev = await ad.requestDevice(), N = 1024, bytes = N * N * 4;
    const mk = (usage) => dev.createBuffer({ size: bytes, usage });
    const A = mk(GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST), B = mk(GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST), C = mk(GPUBufferUsage.STORAGE);
    const fill = new Float32Array(N * N).map((_, i) => (i % 13) * 0.01);
    dev.queue.writeBuffer(A, 0, fill); dev.queue.writeBuffer(B, 0, fill);
    const pipe = dev.createComputePipeline({ layout: "auto", compute: { module: dev.createShaderModule({ code: WGSL }), entryPoint: "main" } });
    const bind = dev.createBindGroup({ layout: pipe.getBindGroupLayout(0), entries: [A, B, C].map((buffer, binding) => ({ binding, resource: { buffer } })) });
    const run = async (rounds) => {
      const enc = dev.createCommandEncoder();
      for (let r = 0; r < rounds; r++) { const p = enc.beginComputePass(); p.setPipeline(pipe); p.setBindGroup(0, bind); p.dispatchWorkgroups(N / 16, N / 16); p.end(); }
      dev.queue.submit([enc.finish()]); await dev.queue.onSubmittedWorkDone();
    };
    await run(1);                                   // warm-up (shader compile)
    const t0 = performance.now(); await run(8); const s = (performance.now() - t0) / 1000;
    const info = ad.info || {};
    dev.destroy();
    return { gflops: (2 * N * N * N * 8) / s / 1e9, label: [info.vendor, info.architecture].filter(Boolean).join(" ") || "unnamed GPU" };
  }

  async function measure() {
    const g = await gpu().catch(() => null);
    return { cpu_gflops: cpu(), gpu_gflops: g ? g.gflops : 0, gpu_label: g ? g.label : null,
             cores: navigator.hardwareConcurrency || 0, mem_gb: navigator.deviceMemory || 0 };
  }
  root.Bench = { measure };
})(window);
