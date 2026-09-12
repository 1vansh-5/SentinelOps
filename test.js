const { SocEnvironment, AdaptiveSocAgent, LabelAutopilot } = require("./soc_core.js");

const SEED = 11;
const TICKS = 80;

const env = new SocEnvironment(SEED);
const agent = new AdaptiveSocAgent(env, (id, kind, msg) => {}); // silent for summary run
const baseline = new LabelAutopilot(() => {});

for (let t = 0; t < TICKS; t++) {
  env.tick();
  const kase = env.maybeSpawnAlert();
  if (kase) {
    agent.ingest(kase);
    baseline.ingest(kase);
  }
  agent.step();
}

console.log("=== ADAPTIVE SOC AGENT ===");
console.log(agent.stats);
console.log("=== LABEL AUTOPILOT (baseline) ===");
console.log(baseline.stats);

// sanity: no case should be stuck 'investigating' forever beyond safety cap
let stuck = 0;
for (const [, st] of agent.cases) if (st.status !== "resolved") stuck++;
console.log("still investigating at end of run:", stuck);

// print one fully-traced case for manual inspection
let sample = null;
for (const [, st] of agent.cases) { if (st.evidence.length >= 2) { sample = st; break; } }
if (sample) {
  console.log("\n--- sample case ---");
  console.log("alert:", sample.kase.alert.sig, "target:", sample.kase.target, "ground truth succeeded:", sample.kase.gt.succeeded);
  sample.evidence.forEach(e => console.log(" ", e.type, "->", e.text, `(push ${e.push})`));
  console.log("verdict:", sample.verdict, "action:", sample.action);
}