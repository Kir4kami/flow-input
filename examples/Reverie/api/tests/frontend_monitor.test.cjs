const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../complete_frontend.html'), 'utf8');
const script = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)]
  .map(match => match[1]).find(source => source.includes('const { createApp } = Vue'));

function app(fetchImpl) {
  let options;
  let nextInterval = 0;
  const intervals = new Map();
  vm.runInNewContext(script, {
    Vue: { createApp(config) { options = config; return { mount() { return {}; } }; } },
    window: { location: { protocol: 'http:', hostname: 'localhost' } },
    console: { log() {}, warn() {}, error() {} },
    fetch: fetchImpl,
    setInterval(callback) { intervals.set(++nextInterval, callback); return nextInterval; },
    clearInterval(id) { intervals.delete(id); },
  });
  const ctx = options.data();
  for (const [name, method] of Object.entries(options.methods)) ctx[name] = method.bind(ctx);
  ctx.$refs = {};
  ctx.simulationResult = { simulation_id: 'run1' };
  ctx.showToast = () => {};
  return { ctx, options, intervals };
}

function event(task, ns = 100) {
  return { event_id: `run1:${task}:0`, simulation_id: 'run1', task_id: task,
    event: 'enter', sim_time_ns: ns, wall_clock_ts: 1700000000 };
}

function snapshot(revision, steady = false) {
  return { simulation_id: 'run1', revision, is_steady: steady, timestamp: 1700000001,
    history: [event(1), event(2), event(3), event(4)], details: [] };
}

test('same timestamps on four tasks are kept; repeated polls are deduplicated', () => {
  const { ctx } = app();
  ctx.applySteadySnapshot(snapshot(8));
  ctx.applySteadySnapshot(snapshot(8));
  assert.equal(ctx.steadyStateHistory.length, 4);
  assert.equal(ctx.simulationStatus.steady_state, false);
});

test('exit state wins over entry history and older responses', () => {
  const { ctx } = app();
  ctx.applySteadySnapshot(snapshot(4, true));
  ctx.applySteadySnapshot(snapshot(8, false));
  ctx.applySteadySnapshot(snapshot(4, true));
  assert.equal(ctx.steadyStateHistory.length, 4);
  assert.equal(ctx.simulationStatus.steady_state, false);
});

test('previous runs cannot overwrite the active run', () => {
  const { ctx } = app();
  ctx.applySteadySnapshot({ ...snapshot(99, true), simulation_id: 'old' });
  assert.equal(ctx.steadyStateHistory.length, 0);
  assert.equal(ctx.simulationStatus.steady_state, false);
});

test('UI history identifies task, simulation time and real wall time', () => {
  const { ctx, options } = app();
  ctx.applySteadySnapshot(snapshot(8));
  const lines = options.computed.steadyStateCaptureLogs.call(ctx);
  assert.match(lines[0], /任务 1.*100 ns.*实际发生时间/);
  assert.match(lines[3], /任务 4/);
});

test('analysis preserves events without changing the current state', () => {
  const { ctx } = app();
  ctx.applySteadyEventsFromAnalysis({ steady_state_analysis: {
    is_system_steady: true, steady_wall_times: [event(1), event(2)] } });
  assert.equal(ctx.steadyStateHistory.length, 2);
  assert.equal(ctx.simulationStatus.steady_state, false);
});

test('legacy analysis never fabricates a wall-clock timestamp', () => {
  const { ctx } = app();
  ctx.applySteadyEventsFromAnalysis({ steady_state_analysis: { steady_times_ns: [100] } });
  assert.equal(ctx.steadyStateHistory[0].timestamp, null);
});

test('poll uses the authoritative combined status and cannot overlap itself', async () => {
  let resolve;
  let calls = 0;
  const { ctx } = app(() => {
    calls++;
    return new Promise(done => { resolve = done; });
  });
  const pending = ctx.updateSimulationStatusSilently();
  await ctx.updateSimulationStatusSilently();
  assert.equal(calls, 1);
  resolve({ ok: true, json: async () => ({ simulation_id: 'run1', is_running: true,
    monitor: snapshot(4, true) }) });
  await pending;
  assert.equal(ctx.simulationStatus.steady_state, true);
  assert.equal(ctx.steadyStateHistory.length, 4);
  assert.equal(ctx.statusPollPending, false);
});

test('start sends an automatic DAG plan and mixed settings together', async () => {
  let body;
  const { ctx } = app(async (url, request) => {
    if (url.endsWith('/run-simulation')) body = JSON.parse(request.body);
    return { ok: true, json: async () => ({ success: true, simulation_id: 'run2' }) };
  });
  ctx.prepareSimulationInputs = async () => {};
  ctx.startAutoMonitor = () => {};
  ctx.simulation.enableCut = true;
  ctx.cutResult = { plan_file: 'TreeGroup/plan.json' };
  ctx.simulation.enableMixedGranularity = true;
  await ctx.startSimulation();
  assert.equal(body.task_num, 1);
  assert.equal(body.use_dag, true);
  assert.equal(body.plan_file, 'TreeGroup/plan.json');
  assert.equal(body.deduplicate, true);
  assert.equal(Object.hasOwn(body, 'validate'), false);
  assert.equal(body.workers, 2);
  assert.equal(body.enable_mixed_granularity, true);
  assert.equal(ctx.steadySnapshotRevision, -1);
});

test('failed background runs are surfaced in the simulation panel', async () => {
  const { ctx } = app(async () => ({ ok: true, json: async () => ({
    simulation_id: 'run1', is_running: false, error: 'task 3 failed', monitor: snapshot(8)
  }) }));
  await ctx.updateSimulationStatusSilently();
  assert.equal(ctx.simulationResult.status, 'failed');
  assert.equal(ctx.simulationError, 'task 3 failed');
  assert.equal(ctx.simulationStatus.steady_state, false);
});

test('tree requests use the directory returned by the current load', async () => {
  let payload;
  const { ctx } = app(async (url, request) => {
    payload = JSON.parse(request.body);
    return { ok: true, json: async () => ({ success: true, nodes_count: 4, tree_data: {} }) };
  });
  ctx.loadResult = { rdma_root: '/workspace/examples/Reverie/Generator/Generator/TrafficGenerator/rdma_result' };
  ctx.loadSource = 'generated';
  await ctx.generateTreeOnly();
  assert.equal(payload.rdma_root, ctx.loadResult.rdma_root);
  assert.equal(payload.load_source, 'generated');
  assert.equal(ctx.isGeneratingTree, false);
});


test('execution result restores the logical schedule and does not synthesize wall time', async () => {
  const result = { mode: 'dag', summary: { logical_unit_count: 21, representative_count: 6 },
    schedule: { stage1: { start_ns: 0, finish_ns: 100, representative_id: 'rep1' } },
    steady_state_timeline: [{ stage_id: 'stage1', global_time_ns: 10, reused: true, representative_id: 'rep1' }] };
  const { ctx, options } = app(async () => ({ ok: true, json: async () => ({
    simulation_id: 'run1', is_running: false, monitor: snapshot(8),
    execution: { phase: 'completed', representative_count: 6, completed_jobs: 6 }, results: { run1: result }
  }) }));
  await ctx.updateSimulationStatusSilently();
  assert.equal(ctx.executionSummary.representative_count, 6);
  assert.equal(ctx.dagResult.summary.logical_unit_count, 21);
  const rows = options.computed.dagScheduleRows.call(ctx);
  assert.equal(rows[0].finish_ns, 100);
  assert.match(options.computed.dagTimelineText.call(ctx), /stage1.*10 ns.*复用.*rep1/);
});

for (const endpoint of ['generate-topology', 'generate-load']) {
  for (const httpFailure of [false, true]) {
    test(`preparation stops on ${endpoint} ${httpFailure ? 'HTTP failure' : 'unsuccessful result'}`, async () => {
      const calls = [];
      const { ctx } = app(async url => {
        calls.push(url.split('/').at(-1));
        if (url.endsWith(`/${endpoint}`)) {
          return { ok: !httpFailure, json: async () => ({ success: httpFailure, detail: 'current input failed' }) };
        }
        return { ok: true, json: async () => ({ success: true, num_hosts: 64 }) };
      });
      ctx.treeGenResult = { success: true, tree_data: { nodes: ['old tree'] } };
      ctx.loadResult = { rdma_root: '/previous/load' };
      await assert.rejects(ctx.prepareSimulationInputs(), /current input failed/);
      assert.deepEqual(calls, endpoint === 'generate-topology'
        ? ['generate-topology'] : ['generate-topology', 'generate-load']);
      assert.equal(ctx.isGeneratingTopology, false);
      assert.equal(ctx.isGeneratingLoad, false);
    });
  }
}

for (const httpFailure of [false, true]) {
  test(`failed tree parsing clears a previous custom DAG (${httpFailure ? 'HTTP' : 'JSON'})`, async () => {
    const calls = [];
    const { ctx } = app(async url => {
      calls.push(url.split('/').at(-1));
      if (url.endsWith('/generate-communication-tree')) {
        return { ok: !httpFailure, json: async () => ({ success: httpFailure, detail: 'tree parsing failed' }) };
      }
      return { ok: true, json: async () => ({ success: true, num_hosts: 64 }) };
    });
    ctx.load.model_name = 'custom';
    ctx.loadSource = 'custom';
    ctx.customTrafficResult = { success: true };
    ctx.treeGenResult = { success: true, tree_data: { nodes: ['old tree'] } };
    ctx.cutResult = { plan_file: 'old/plan.json' };
    ctx.executionPlanIsFinal = true;
    await assert.rejects(ctx.prepareSimulationInputs(), /tree parsing failed/);
    assert.deepEqual(calls, ['generate-topology', 'generate-communication-tree']);
    assert.equal(ctx.treeGenResult, null);
    assert.equal(ctx.cutResult, null);
    assert.equal(ctx.executionPlanIsFinal, false);
    assert.equal(ctx.isGeneratingTree, false);
  });
}

test('a second start cannot rebuild inputs or launch while preparation is pending', async () => {
  const calls = [];
  const { ctx } = app(async url => {
    calls.push(url.split('/').at(-1));
    return { ok: true, json: async () => ({ success: true, simulation_id: 'run2' }) };
  });
  let finishPreparation;
  let preparations = 0;
  ctx.prepareSimulationInputs = () => {
    preparations++;
    return new Promise(resolve => { finishPreparation = resolve; });
  };
  ctx.startAutoMonitor = () => {};
  ctx.cutResult = { plan_file: 'TreeGroup/plan.json' };
  const first = ctx.startSimulation();
  assert.equal(ctx.isStartingSimulation, true);
  await ctx.startSimulation();
  assert.equal(preparations, 1);
  assert.equal(calls.length, 0);
  finishPreparation();
  await first;
  assert.deepEqual(calls, ['start-steady-state-monitor', 'run-simulation']);
  assert.equal(ctx.isStartingSimulation, false);
  assert.equal(ctx.simulationStatus.is_running, true);
});

test('failed preparation releases the start lock without launching', async () => {
  let calls = 0;
  const { ctx } = app(async () => { calls++; throw new Error('must not launch'); });
  ctx.prepareSimulationInputs = async () => { throw new Error('invalid current input'); };
  await ctx.startSimulation();
  assert.equal(calls, 0);
  assert.equal(ctx.isStartingSimulation, false);
  assert.equal(ctx.simulationStatus.is_running, false);
});

test('runner timeline lists mapped stages and identifies reused events', () => {
  const { ctx, options } = app();
  ctx.dagResult = { steady_state_timeline: [
    { stage_ids: ['TP1', 'EP2'], group_id: 'group1', global_sim_time_ns: 125,
      source: 'reused', representative_id: 'rep1', event: 'enter' },
    { stage_ids: [], group_id: 'group2', global_sim_time_ns: 250,
      source: 'simulator', representative_id: 'rep2', event: 'exit' }
  ] };
  const lines = options.computed.dagTimelineText.call(ctx).split('\n');
  assert.match(lines[0], /TP1, EP2.*125 ns.*enter.*复用.*rep1/);
  assert.match(lines[1], /group2.*250 ns.*exit.*rep2/);
});

test('final grouping updates the current projection while retaining the candidate directory count', async () => {
  const finalPlan = { counts: { group_count: 2 }, stages: [{ id: 'A', group_id: 'group1' }] };
  const { ctx } = app(async () => ({ ok: true, json: async () => ({
    simulation_id: 'run1', is_running: false, execution: {}, monitor: snapshot(8),
    results: { run1: { mode: 'dag', execution_plan: finalPlan } }
  }) }));
  ctx.cutResult = { tree_groups: 3, output_directory: 'TreeGroup', execution_plan: {} };
  await ctx.updateSimulationStatusSilently();
  assert.equal(ctx.executionSummary, null);
  assert.equal(ctx.cutResult.tree_groups, 3);
  assert.equal(ctx.cutResult.execution_plan.counts.group_count, 2);
  assert.equal(ctx.executionPlanIsFinal, true);
});

function executionPlan(groupCount, representativeCount = groupCount) {
  return { counts: { logical_unit_count: 3, group_count: groupCount, representative_count: representativeCount },
    stages: [{ id: 'A', group_id: 'group1', representative_id: 'rep1', predecessors: [] }],
    groups: Array.from({ length: groupCount }, (_, index) => ({ id: `group${index + 1}`, stage_ids: [String(index)] })) };
}

function decodeAttribute(value) {
  return value.replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
}

test('3D sends the current final projection instead of the old three-group files', async () => {
  const calls = [];
  const finalPlan = executionPlan(2, 1);
  const markup = '<!doctype html><html><body>FINAL 2</body></html>';
  const { ctx } = app(async (url, request) => {
    calls.push({ url, request });
    return { ok: true, text: async () => markup };
  });
  ctx.cutResult = { tree_groups: 3, output_directory: 'TreeGroup', execution_plan: finalPlan };
  ctx.executionPlanIsFinal = true;
  await ctx.visualizeTreeGroups();
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /\/visualize-execution-plan$/);
  assert.equal(calls[0].request.method, 'POST');
  const payload = JSON.parse(calls[0].request.body);
  assert.deepEqual(payload.execution_plan, finalPlan);
  assert.equal(payload.is_final, true);
  assert.equal(payload.simulation_id, 'run1');
  assert.match(ctx.modal.title, /最终执行分组.*子单元 2.*代表任务 1/);
  assert.equal(ctx.cutResult.tree_groups, 3);
  assert.match(ctx.modal.content, /^<iframe /);
  assert.doesNotMatch(ctx.modal.content, /get-tree-groups-3d|visualize-tree-groups|get-tree-image|zoom:|translateX/);
});

test('3D srcdoc escapes complete markup without leaking nodes or attributes into its parent', async () => {
  const markup = '<!doctype html><html><body data-name="A&B">\n<script>const x = \"><img onerror=alert(1)>\";</script>\'&quot;</body></html>';
  const { ctx } = app(async () => ({ ok: true, text: async () => markup }));
  ctx.cutResult = { execution_plan: executionPlan(2) };
  await ctx.visualizeTreeGroups();
  const match = ctx.modal.content.match(/^<iframe title="([^"]*)" srcdoc="([^"]*)"><\/iframe>$/);
  assert.ok(match, 'single quoted srcdoc attribute must contain the whole child document');
  assert.equal(decodeAttribute(match[2]), markup);
  assert.doesNotMatch(ctx.modal.content, /<script|<img|<body/);
  assert.match(ctx.modal.title, /候选执行分组/);
});

test('an open candidate visualization automatically follows the final runtime plan', async () => {
  const renderPayloads = [];
  const finalPlan = executionPlan(2, 1);
  const { ctx } = app(async (url, request) => {
    if (url.endsWith('/simulation-status')) return { ok: true, json: async () => ({
      simulation_id: 'run1', is_running: false, execution: {}, monitor: snapshot(8),
      results: { run1: { mode: 'dag', execution_plan: finalPlan } }
    }) };
    assert.match(url, /\/visualize-execution-plan$/);
    const payload = JSON.parse(request.body);
    renderPayloads.push(payload);
    return { ok: true, text: async () => `<html>${payload.is_final ? 'FINAL' : 'CANDIDATE'} ${payload.execution_plan.counts.group_count}</html>` };
  });
  ctx.cutResult = { tree_groups: 3, execution_plan: executionPlan(3) };
  await ctx.visualizeTreeGroups();
  assert.match(ctx.modal.content, /CANDIDATE 3/);
  await ctx.updateSimulationStatusSilently();
  assert.equal(renderPayloads.length, 2);
  assert.equal(renderPayloads[1].is_final, true);
  assert.equal(renderPayloads[1].execution_plan.counts.group_count, 2);
  assert.match(ctx.modal.title, /最终执行分组.*子单元 2/);
  assert.match(ctx.modal.content, /FINAL 2/);
  await ctx.updateSimulationStatusSilently();
  assert.equal(renderPayloads.length, 2, 'identical status polls must retain the current camera/view');
});

test('a slower candidate response cannot overwrite a newer final visualization', async () => {
  let completeOld;
  let renders = 0;
  const { ctx } = app(() => {
    if (++renders === 1) return new Promise(resolve => { completeOld = resolve; });
    return Promise.resolve({ ok: true, text: async () => '<html>FINAL 2</html>' });
  });
  ctx.cutResult = { execution_plan: executionPlan(3) };
  const oldRequest = ctx.visualizeTreeGroups();
  ctx.cutResult.execution_plan = executionPlan(2);
  ctx.executionPlanIsFinal = true;
  await ctx.refreshExecutionPlanVisualization();
  completeOld({ ok: true, text: async () => '<html>OLD 3</html>' });
  await oldRequest;
  assert.equal(renders, 2);
  assert.match(ctx.modal.content, /FINAL 2/);
  assert.doesNotMatch(ctx.modal.content, /OLD 3/);
});

for (const close of ['closeModal', 'closeModalDirectly']) {
  test(`a pending visualization cannot reopen a modal closed with ${close}`, async () => {
    let complete;
    const { ctx } = app(() => new Promise(resolve => { complete = resolve; }));
    ctx.cutResult = { execution_plan: executionPlan(3) };
    const pending = ctx.visualizeTreeGroups();
    ctx[close]();
    complete({ ok: true, text: async () => '<html>LATE</html>' });
    await pending;
    assert.equal(ctx.modal.show, false);
    assert.doesNotMatch(ctx.modal.content, /LATE/);
  });
}

test('a pending 3D response cannot replace another modal or a changed plan', async () => {
  let complete;
  const { ctx } = app(() => new Promise(resolve => { complete = resolve; }));
  ctx.cutResult = { execution_plan: executionPlan(3) };
  const pending = ctx.visualizeTreeGroups();
  ctx.modal = { show: true, type: 'content', content: 'Other dialog' };
  complete({ ok: true, text: async () => '<html>LATE</html>' });
  await pending;
  assert.equal(ctx.modal.type, 'content');
  assert.equal(ctx.modal.content, 'Other dialog');
});

test('clearing a plan invalidates the open 3D view and pending response', async () => {
  let complete;
  const { ctx, options } = app(() => new Promise(resolve => { complete = resolve; }));
  ctx.cutResult = { execution_plan: executionPlan(3) };
  const pending = ctx.visualizeTreeGroups();
  ctx.cutResult = null;
  options.watch['cutResult.execution_plan'].handler.call(ctx);
  complete({ ok: true, text: async () => '<html>LATE</html>' });
  await pending;
  assert.equal(ctx.modal.show, false);
  assert.doesNotMatch(ctx.modal.content, /LATE/);
});

test('render errors are shown safely and leave the current plan retryable', async () => {
  const { ctx } = app(async () => ({ ok: false, text: async () => JSON.stringify({ detail: '<img onerror=alert(1)>' }) }));
  ctx.cutResult = { execution_plan: executionPlan(3) };
  await ctx.visualizeTreeGroups();
  assert.match(ctx.modal.content, /&lt;img/);
  assert.doesNotMatch(ctx.modal.content, /<img/);
  assert.equal(ctx.executionVisualizationRequestKey, '');
});

test('packet and mixed deduplication evidence show their own acceptance or fallback', () => {
  const { ctx } = app();
  assert.equal(ctx.deduplicationValidationText({ performed: true, passed: true,
    final_representative_count: 6 }), '通过；实际代表 6 个');
  assert.equal(ctx.deduplicationValidationText({ performed: true, passed: true, fallback: true,
    final_representative_count: 7 }), '候选映射未通过，已使用保守分组；实际代表 7 个');
  assert.equal(ctx.deduplicationValidationText({ performed: false, final_representative_count: 7 }),
    '未验证重排候选，使用保守分组；实际代表 7 个');
});

function analysisApp(fetchImpl) {
  const instance = app(fetchImpl);
  instance.ctx.simulationResult = { simulation_id: 'run1', status: 'completed' };
  instance.ctx.updateSimulationStatusSilently = async () => {};
  instance.ctx.$nextTick = callback => callback();
  instance.ctx.drawFctComparisonChart = () => {};
  return instance;
}

function analysisResponse(reused = false) {
  return { ok: true, json: async () => ({ success: true, summary: 'analysis ready', results: {
    dag_result: { mode: 'dag', success: true },
    baseline_status: { status: 'completed', reused, cache_key: 'frozen-input-1' },
    comparison: { passed: true, max_abs_fct_error_ns: 0 }
  } }) };
}

const flushTasks = () => new Promise(resolve => setImmediate(resolve));

test('full packet baseline is requested only by the analysis module', () => {
  const { ctx } = app();
  assert.equal(Object.hasOwn(ctx.simulation, 'validate'), false);
  assert.doesNotMatch(html, /v-model="simulation\.validate"/);
  assert.match(html, /首次分析会自动运行/);
  assert.match(html, /关闭切分与混合粒度/);
});

test('analysis waits for a first baseline and automatically displays its comparison', async () => {
  const calls = [];
  let complete;
  const { ctx, intervals } = analysisApp((url, options) => {
    calls.push({ url, options });
    if (url.includes('/baseline-status')) return Promise.resolve({ ok: true, json: async () => ({
      success: true, status: 'running', is_running: true, has_baseline: false
    }) });
    return new Promise(resolve => { complete = resolve; });
  });
  ctx.dagResult = { mode: 'dag', summary: { representative_count: 6 } };
  const pending = ctx.analyzeResults();
  await flushTasks();
  assert.equal(ctx.isAnalyzing, true);
  assert.equal(ctx.analysisPhase, 'baseline_running');
  assert.match(ctx.analysisProgress, /结束后将自动分析/);
  assert.equal(intervals.size, 1);
  const request = calls.find(call => call.url.endsWith('/analyze-results'));
  assert.deepEqual(JSON.parse(request.options.body), { simulation_id: 'run1', analysis_type: 'all' });
  complete(analysisResponse());
  await pending;
  assert.equal(ctx.isAnalyzing, false);
  assert.equal(intervals.size, 0);
  assert.equal(ctx.analysisResult.results.comparison.max_abs_fct_error_ns, 0);
  assert.equal(ctx.analysisPhase, 'completed');
  assert.match(ctx.analysisProgress, /自动完成/);
  assert.equal(ctx.simulationStatus.is_running, false);
});

test('a matching cached baseline goes directly to analysis without a launch endpoint', async () => {
  const calls = [];
  const { ctx } = analysisApp(async url => {
    calls.push(url);
    return url.includes('/baseline-status')
      ? { ok: true, json: async () => ({ success: true, status: 'completed', has_baseline: true }) }
      : analysisResponse(true);
  });
  await ctx.analyzeResults();
  assert.equal(ctx.analysisResult.results.baseline_status.reused, true);
  assert.match(ctx.analysisProgress, /已复用/);
  assert.equal(calls.filter(url => url.endsWith('/analyze-results')).length, 1);
  assert.ok(calls.every(url => !url.includes('/run-simulation')));
});

test('analysis locks before its first await so a double click cannot duplicate work', async () => {
  let finishStatus;
  let statusReads = 0;
  const calls = [];
  const { ctx } = analysisApp(async url => {
    calls.push(url);
    return url.includes('/baseline-status')
      ? { ok: true, json: async () => ({ success: true, status: 'completed', has_baseline: true }) }
      : analysisResponse(true);
  });
  ctx.updateSimulationStatusSilently = () => {
    statusReads++;
    return new Promise(resolve => { finishStatus = resolve; });
  };
  const pending = ctx.analyzeResults();
  await ctx.analyzeResults();
  assert.equal(statusReads, 1);
  assert.equal(calls.length, 0);
  finishStatus();
  await pending;
  assert.equal(calls.filter(url => url.endsWith('/analyze-results')).length, 1);
});

for (const unavailable of ['missing', 'running', 'failed']) {
  test(`analysis does not launch a baseline for an ${unavailable} experiment`, async () => {
    const calls = [];
    const { ctx, intervals } = analysisApp(async url => { calls.push(url); throw Error('unexpected request'); });
    if (unavailable === 'missing') ctx.simulationResult = null;
    if (unavailable === 'running') ctx.simulationStatus.is_running = true;
    if (unavailable === 'failed') ctx.simulationResult.status = 'failed';
    await ctx.analyzeResults();
    assert.equal(calls.length, 0);
    assert.equal(ctx.isAnalyzing, false);
    assert.equal(intervals.size, 0);
    assert.equal(ctx.analysisPhase, 'failed');
    assert.equal(ctx.simulationStatus.is_running, unavailable === 'running');
  });
}

test('a failed baseline leaves experiment state unchanged and analysis retryable', async () => {
  const { ctx, intervals } = analysisApp(async url => url.includes('/baseline-status')
    ? { ok: true, json: async () => ({ success: true, status: 'running', is_running: true }) }
    : { ok: false, json: async () => ({ detail: 'baseline process failed' }) });
  await ctx.analyzeResults();
  assert.equal(ctx.analysisPhase, 'failed');
  assert.equal(ctx.analysisProgress, 'baseline process failed');
  assert.equal(ctx.analysisResult, null);
  assert.equal(ctx.simulationStatus.is_running, false);
  assert.equal(ctx.isAnalyzing, false);
  assert.equal(intervals.size, 0);
});

test('cancel analysis cancels only its baseline and discards the pending response', async () => {
  let complete;
  const calls = [];
  const { ctx, intervals } = analysisApp((url, options) => {
    calls.push({ url, options });
    if (url.includes('/baseline-status')) return Promise.resolve({ ok: true, json: async () => ({
      success: true, status: 'running', is_running: true
    }) });
    if (url.endsWith('/cancel-baseline')) return Promise.resolve({ ok: true, json: async () => ({
      success: true, cancelled: true
    }) });
    return new Promise(resolve => { complete = resolve; });
  });
  const pending = ctx.analyzeResults();
  await flushTasks();
  await ctx.cancelAnalysis();
  assert.equal(ctx.analysisPhase, 'cancelled');
  assert.equal(ctx.isAnalyzing, false);
  assert.equal(ctx.isCancellingAnalysis, false);
  assert.equal(intervals.size, 0);
  const cancellation = calls.find(call => call.url.endsWith('/cancel-baseline'));
  assert.deepEqual(JSON.parse(cancellation.options.body), { simulation_id: 'run1' });
  assert.ok(calls.every(call => !call.url.includes('/stop-simulation')));
  complete(analysisResponse());
  await pending;
  assert.equal(ctx.analysisResult, null);
  assert.equal(ctx.analysisPhase, 'cancelled');
});

test('changing the experiment invalidates old analysis and status responses', async () => {
  let complete;
  const { ctx, options, intervals } = analysisApp(url => url.includes('/baseline-status')
    ? Promise.resolve({ ok: true, json: async () => ({ success: true, status: 'running', is_running: true }) })
    : new Promise(resolve => { complete = resolve; }));
  const pending = ctx.analyzeResults();
  await flushTasks();
  ctx.simulationResult = { simulation_id: 'run2', status: 'completed' };
  options.watch['simulationResult.simulation_id'].call(ctx, 'run2');
  complete(analysisResponse());
  await pending;
  assert.equal(ctx.analysisResult, null);
  assert.equal(ctx.isAnalyzing, false);
  assert.equal(intervals.size, 0);
  assert.match(ctx.analysisProgress, /实验已变更/);
});

test('a late status poll cannot replace a completed analysis', async () => {
  let completeStatus;
  const { ctx } = analysisApp(url => url.includes('/baseline-status')
    ? new Promise(resolve => { completeStatus = resolve; })
    : Promise.resolve(analysisResponse(true)));
  await ctx.analyzeResults();
  completeStatus({ ok: true, json: async () => ({ success: true, status: 'running', is_running: true }) });
  await flushTasks();
  assert.equal(ctx.analysisPhase, 'completed');
  assert.match(ctx.analysisProgress, /已复用/);
});

test('a new experiment cannot start while analysis or cancellation is pending', async () => {
  let preparations = 0;
  const { ctx } = analysisApp();
  ctx.prepareSimulationInputs = async () => { preparations++; };
  ctx.isAnalyzing = true;
  await ctx.startSimulation();
  ctx.isAnalyzing = false;
  ctx.isCancellingAnalysis = true;
  await ctx.startSimulation();
  assert.equal(preparations, 0);
});

test('zero error is displayed as zero and unavailable ratios remain explicit', () => {
  const { ctx } = app();
  assert.equal(ctx.analysisMetric(0, 6), '0.000000');
  assert.equal(ctx.analysisMetric(null), '无法计算');
  assert.equal(ctx.analysisMetric(Infinity), '无法计算');
});

test('the comparison chart renders after Vue wraps the accepted response', async () => {
  const { ctx } = analysisApp(async url => url.includes('/baseline-status')
    ? { ok: true, json: async () => ({ success: true, status: 'completed', has_baseline: true }) }
    : analysisResponse(true));
  let reactiveResult = null;
  Object.defineProperty(ctx, 'analysisResult', {
    configurable: true,
    get() { return reactiveResult; },
    set(value) { reactiveResult = value === null ? null : new Proxy(value, {}); }
  });
  const nextTicks = [];
  let charts = 0;
  ctx.$nextTick = callback => nextTicks.push(callback);
  ctx.drawFctComparisonChart = () => { charts++; };
  await ctx.analyzeResults();
  assert.equal(charts, 0);
  nextTicks.forEach(callback => callback());
  assert.equal(charts, 1);
});
