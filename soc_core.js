// =====================================================================
// SentinelOps SOC — core simulation logic (DOM-free, shared by the
// browser page and this headless test harness).
// =====================================================================

// --- seeded RNG (mulberry32) ---
function makeRng(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function choice(rng, arr) { return arr[Math.floor(rng() * arr.length)]; }
function randIp(rng) {
  return `${Math.floor(uniform(rng,1,223))}.${Math.floor(uniform(rng,0,255))}.${Math.floor(uniform(rng,0,255))}.${Math.floor(uniform(rng,1,254))}`;
}
function uniform(rng, lo, hi) { return lo + rng() * (hi - lo); }

// --- synthetic asset inventory + CVE knowledge base (baked in as vulnerable_to) ---
const ASSETS = {
  "web-app-01": { exposure: "internet-facing", criticality: "high", software: "Log4j 2.14 / Apache Struts 2.3", vulnerable_to: ["log4shell", "struts_rce", "sqli"] },
  "vpn-gateway-01": { exposure: "internet-facing", criticality: "high", software: "OpenSSH (weak password policy)", vulnerable_to: ["ssh_bruteforce"] },
  "db-server-02": { exposure: "internal", criticality: "critical", software: "PostgreSQL 15.2 (patched)", vulnerable_to: [] },
  "file-server-03": { exposure: "internal", criticality: "medium", software: "Samba 4.19 (patched)", vulnerable_to: [] },
};
const ASSET_NAMES = Object.keys(ASSETS);

// --- simulated NIDS/Snort/Suricata alert signatures ---
// severityWord is what a naive triage tool would key off of -- the label alone.
const ALERT_TYPES = [
  { sig: "ET EXPLOIT Log4Shell Attempt", exploit: "log4shell", severityWord: "EXPLOIT", targets: ["web-app-01"] },
  { sig: "ET EXPLOIT Apache Struts RCE Attempt", exploit: "struts_rce", severityWord: "EXPLOIT", targets: ["web-app-01"] },
  { sig: "ET WEB SQL Injection Attempt", exploit: "sqli", severityWord: "WEB", targets: ["web-app-01"] },
  { sig: "ET POLICY SSH Brute Force", exploit: "ssh_bruteforce", severityWord: "POLICY", targets: ["vpn-gateway-01"] },
  { sig: "ET SCAN Nmap Port Scan", exploit: "portscan", severityWord: "SCAN", targets: ASSET_NAMES },
  { sig: "ET TROJAN Possible C2 Beacon", exploit: "c2_beacon", severityWord: "TROJAN", targets: ["db-server-02", "file-server-03", "web-app-01"] },
];

const EVIDENCE_TYPES = ["asset_inventory", "vulnerability_kb", "packet_metadata", "server_logs"];
const CONFIDENCE_THRESHOLD = 0.5;
const INCONCLUSIVE_BAND = 0.25;
const MAX_TICKS_PER_CASE = 8; // safety cap even if evidence keeps coming back flaky

// --- learned per-signature evidence-priority policy ---
const PRIOR_WEIGHTS = {
  log4shell: { asset_inventory: 0.3, vulnerability_kb: 0.6, packet_metadata: 0.3, server_logs: 0.7 },
  struts_rce: { asset_inventory: 0.3, vulnerability_kb: 0.6, packet_metadata: 0.3, server_logs: 0.7 },
  sqli: { asset_inventory: 0.2, vulnerability_kb: 0.4, packet_metadata: 0.35, server_logs: 0.6 },
  ssh_bruteforce: { asset_inventory: 0.2, vulnerability_kb: 0.15, packet_metadata: 0.3, server_logs: 0.7 },
  portscan: { asset_inventory: 0.2, vulnerability_kb: 0.1, packet_metadata: 0.6, server_logs: 0.3 },
  c2_beacon: { asset_inventory: 0.2, vulnerability_kb: 0.1, packet_metadata: 0.4, server_logs: 0.7 },
};

class SocPolicy {
  constructor(alpha = 0.3) { this.alpha = alpha; this.w = JSON.parse(JSON.stringify(PRIOR_WEIGHTS)); }
  rank(exploit, excluded) {
    const table = this.w[exploit] || { asset_inventory: 0.25, vulnerability_kb: 0.25, packet_metadata: 0.25, server_logs: 0.25 };
    return EVIDENCE_TYPES.filter(e => !excluded.has(e)).sort((a, b) => table[b] - table[a]);
  }
  decide(exploit, excluded, rng) {
    const ranked = this.rank(exploit, excluded);
    if (ranked.length === 0) return null;
    if (rng() < 0.1) return choice(rng, ranked);
    return ranked[0];
  }
  update(exploit, evidenceType, observedAbsPush) {
    if (!this.w[exploit]) this.w[exploit] = { asset_inventory: 0.25, vulnerability_kb: 0.25, packet_metadata: 0.25, server_logs: 0.25 };
    const old = this.w[exploit][evidenceType];
    this.w[exploit][evidenceType] = old + this.alpha * (observedAbsPush - old);
  }
}

// --- Environment: generates the alert stream + evidence-on-demand ---
class SocEnvironment {
  constructor(seed, alertProb = 0.35, flakyProb = 0.08) {
    this.alertRng = makeRng(seed);        // controls WHEN alerts spawn + ground truth
    this.evidenceRng = makeRng(seed + 999); // controls evidence flakiness (only consumed by the adaptive agent)
    this.alertProb = alertProb;
    this.flakyProb = flakyProb;
    this.tickNum = 0;
    this.nextId = 1;
  }

  maybeSpawnAlert() {
    if (this.alertRng() >= this.alertProb) return null;
    const type = choice(this.alertRng, ALERT_TYPES);
    const target = choice(this.alertRng, type.targets);
    const asset = ASSETS[target];
    const srcIp = randIp(this.alertRng);

    const isPortscan = type.exploit === "portscan";
    const falsePositiveRoll = this.alertRng();
    const isFalsePositive = isPortscan ? false : falsePositiveRoll < 0.22;

    let isRealAttempt = !isFalsePositive;
    let vulnerable = asset.vulnerable_to.includes(type.exploit);
    let succeeded = false;
    if (isPortscan) {
      succeeded = false; // recon only, never a compromise by itself
    } else if (isRealAttempt) {
      succeeded = vulnerable && this.alertRng() < 0.82;
    }

    // A minority of TRUE successful compromises have delayed forensic evidence --
    // early server_log checks under-report them, requiring later reconsideration.
    const hasDelayedEvidence = succeeded && this.alertRng() < 0.35;
    const revealTick = hasDelayedEvidence ? this.tickNum + Math.floor(uniform(this.alertRng, 4, 8)) : null;

    return {
      id: this.nextId++,
      spawnTick: this.tickNum,
      alert: type,
      target,
      srcIp,
      gt: { isRealAttempt, succeeded, isPortscan },
      hasDelayedEvidence,
      revealTick,
    };
  }

  // Returns {text, push} or null (flaky / temporarily unavailable)
  queryEvidence(kase, evidenceType) {
    if (this.evidenceRng() < this.flakyProb) return null;

    const asset = ASSETS[kase.target];
    if (evidenceType === "asset_inventory") {
      return {
        text: `${kase.target}: ${asset.exposure}, criticality=${asset.criticality}, running ${asset.software}`,
        push: asset.exposure === "internet-facing" ? 0.05 : -0.05,
      };
    }
    if (evidenceType === "vulnerability_kb") {
      if (kase.gt.isPortscan) return { text: `vulnerability_kb: not applicable — reconnaissance, not an exploit attempt`, push: -0.1 };
      const vulnerable = asset.vulnerable_to.includes(kase.alert.exploit);
      return {
        text: vulnerable
          ? `vulnerability_kb: ${kase.target} IS VULNERABLE to ${kase.alert.exploit} (unpatched)`
          : `vulnerability_kb: ${kase.target} is NOT vulnerable to ${kase.alert.exploit} (patched / not applicable)`,
        push: vulnerable ? 0.3 : -0.35,
      };
    }
    if (evidenceType === "packet_metadata") {
      if (kase.gt.isPortscan) return { text: `packet_metadata: sequential low-volume probes across common ports — classic scan pattern`, push: -0.25 };
      if (!kase.gt.isRealAttempt) return { text: `packet_metadata: single malformed packet, no crafted payload — consistent with automated noise`, push: -0.3 };
      return { text: `packet_metadata: crafted payload matching known exploit shape, repeated attempts from ${kase.srcIp}`, push: 0.2 };
    }
    if (evidenceType === "server_logs") {
      if (kase.hasDelayedEvidence && this.tickNum < kase.revealTick) {
        return { text: `server_logs: no anomalous process or auth activity in available window (partial log coverage)`, push: -0.2, partial: true };
      }
      if (kase.gt.succeeded) {
        const msgs = {
          log4shell: "server_logs: JVM spawned an unexpected child process and opened an outbound connection to an unlisted host",
          struts_rce: "server_logs: web worker spawned a shell process — command execution confirmed",
          sqli: "server_logs: application logs show a bulk SELECT against the customer table minutes after the request",
          ssh_bruteforce: "server_logs: auth log shows 40+ failed logins followed by a successful login from the same source",
          c2_beacon: "server_logs: recurring outbound beacon to a known-bad host every 60s, established persistence artifact found",
        };
        return { text: msgs[kase.alert.exploit] || "server_logs: anomalous process and outbound activity observed", push: 0.55 };
      }
      if (kase.gt.isRealAttempt) {
        return { text: `server_logs: attempt logged and rejected (patched / WAF enforced) — no compromise indicators`, push: -0.45 };
      }
      return { text: `server_logs: no anomalous activity found — consistent with a benign trigger`, push: -0.3 };
    }
    return null;
  }

  tick() { this.tickNum++; }
}

// --- Adaptive SOC investigation agent ---
class AdaptiveSocAgent {
  constructor(env, onLog = () => {}) {
    this.env = env; this.onLog = onLog;
    this.policy = new SocPolicy();
    this.cases = new Map(); // id -> case state
    this.pendingReconsider = []; // {revealTick, caseId}
    this.stats = { total: 0, resolved: 0, escalations: 0, blocked: 0, falseBlocks: 0, missedBreaches: 0, correct: 0, reconsiderations: 0, overrides: 0 };
  }

  ingest(kase) {
    this.stats.total++;
    const state = {
      kase, queried: new Set(), evidence: [], score: 0, sawRealSignal: false,
      status: "investigating", verdict: null, action: null, ticksSpent: 0, overridden: false,
    };
    this.cases.set(kase.id, state);
    this.onLog(kase.id, "new", `Alert #${kase.id}: '${kase.alert.sig}' → target ${kase.target}, source ${kase.srcIp}`);
    if (kase.hasDelayedEvidence) this.pendingReconsider.push({ revealTick: kase.revealTick, caseId: kase.id });
    return state;
  }

  step() {
    // advance every open investigation by exactly one evidence-gathering or finalize action
    for (const [id, st] of this.cases) {
      if (st.status !== "investigating") continue;
      st.ticksSpent++;
      const next = this.policy.decide(st.kase.alert.exploit, st.queried, this.env.alertRng);

      if (next === null || Math.abs(st.score) >= CONFIDENCE_THRESHOLD || st.ticksSpent > MAX_TICKS_PER_CASE) {
        this._finalize(id, st);
        continue;
      }
      const result = this.env.queryEvidence(st.kase, next);
      if (result === null) {
        this.onLog(id, "flaky", `decide: query ${next} → temporarily unavailable, will retry`);
        continue;
      }
      st.queried.add(next);
      st.score += result.push;
      if (result.push > 0.15 && next !== "asset_inventory") st.sawRealSignal = true;
      st.evidence.push({ type: next, text: result.text, push: result.push });
      this.onLog(id, "evidence", `decide: query ${next} → ${result.text}`);
      this.policy.update(st.kase.alert.exploit, next, Math.abs(result.push));

      if (Math.abs(st.score) >= CONFIDENCE_THRESHOLD || st.queried.size === EVIDENCE_TYPES.length) {
        this._finalize(id, st);
      }
    }

    // process any evidence that arrives independently of the agent's own queries
    this.pendingReconsider = this.pendingReconsider.filter(r => {
      if (this.env.tickNum < r.revealTick) return true;
      this._reconsider(r.caseId);
      return false;
    });
  }

  _finalize(id, st) {
    if (st.score >= CONFIDENCE_THRESHOLD) st.verdict = "ATTACK SUCCEEDED";
    else if (st.score <= -0.4) st.verdict = st.sawRealSignal ? "ATTACK FAILED (blocked/patched)" : "FALSE POSITIVE";
    else st.verdict = "INCONCLUSIVE";

    if (st.verdict === "ATTACK SUCCEEDED") {
      st.action = "BLOCKED " + st.kase.srcIp;
      this.stats.blocked++;
      this.onLog(id, "action", `act: simulated firewall block on ${st.kase.srcIp}`);
      this.onLog(id, "verify", `evaluate: re-checked traffic — 0 further packets from ${st.kase.srcIp}, block confirmed effective`);
    } else if (st.verdict === "INCONCLUSIVE") {
      st.action = "ESCALATED to analyst";
      this.stats.escalations++;
      this.onLog(id, "escalate", `evaluate: evidence inconclusive (score ${st.score.toFixed(2)}) → escalating to human analyst`);
    } else {
      st.action = st.verdict === "FALSE POSITIVE" ? "closed, no action" : "logged for monitoring, no block";
    }
    st.status = "resolved";
    this.stats.resolved++;

    const correct = (st.verdict === "ATTACK SUCCEEDED") === st.kase.gt.succeeded;
    if (correct) this.stats.correct++;
    if (st.verdict === "ATTACK SUCCEEDED" && !st.kase.gt.succeeded) this.stats.falseBlocks++;
    if (st.verdict !== "ATTACK SUCCEEDED" && st.kase.gt.succeeded) this.stats.missedBreaches++;

    this.onLog(id, "verdict", `assessment: ${st.verdict} (confidence score ${st.score.toFixed(2)}) → ${st.action}`);
  }

  _reconsider(id) {
    const st = this.cases.get(id);
    if (!st) return;
    const wasBlocked = st.action && st.action.startsWith("BLOCKED");
    const update = { text: `server_logs UPDATE: delayed forensic sweep found outbound data transfer (4.2GB) from ${st.kase.target}`, push: 0.6 };
    st.evidence.push({ type: "server_logs (delayed)", text: update.text, push: update.push });
    st.score += update.push;
    this.stats.reconsiderations++;
    this.onLog(id, "reconsider", `NEW EVIDENCE ARRIVED: ${update.text}`);

    const prevVerdict = st.verdict;
    if (st.score >= CONFIDENCE_THRESHOLD) st.verdict = "ATTACK SUCCEEDED"; else if (st.score <= -0.4) st.verdict = "ATTACK FAILED (blocked/patched)"; else st.verdict = "INCONCLUSIVE";

    if (prevVerdict !== st.verdict) {
      if (st.verdict === "ATTACK SUCCEEDED" && !wasBlocked) {
        st.action = "BLOCKED " + st.kase.srcIp + " (retroactive)";
        this.stats.blocked++;
        if (prevVerdict !== "ATTACK SUCCEEDED" && st.kase.gt.succeeded) this.stats.missedBreaches = Math.max(0, this.stats.missedBreaches - 1);
        this.onLog(id, "action", `act: reconsidered verdict (${prevVerdict} → ${st.verdict}) → simulated firewall block on ${st.kase.srcIp} taken retroactively`);
      }
    }
  }

  override(id, humanVerdict) {
    const st = this.cases.get(id);
    if (!st || st.status !== "resolved") return;
    const wasBlocked = st.action && st.action.startsWith("BLOCKED");
    st.overridden = true;
    this.stats.overrides++;

    if (humanVerdict === "false_positive") {
      st.verdict = "FALSE POSITIVE (analyst override)";
      if (wasBlocked) { st.action = "UNBLOCKED (analyst override)"; this.onLog(id, "override", `ANALYST OVERRIDE: unblocked ${st.kase.srcIp}, reclassified as false positive`); }
      else { st.action = "closed, no action (analyst override)"; this.onLog(id, "override", `ANALYST OVERRIDE: confirmed as false positive`); }
    } else {
      st.verdict = "ATTACK SUCCEEDED (analyst override)";
      if (!wasBlocked) { st.action = "BLOCKED " + st.kase.srcIp + " (analyst override)"; this.stats.blocked++; this.onLog(id, "override", `ANALYST OVERRIDE: analyst confirmed compromise → simulated firewall block on ${st.kase.srcIp}`); }
    }
    // soft correction: down-weight whichever evidence type most drove the (now-overturned) original call
    if (st.evidence.length) {
      const most = st.evidence.reduce((a, b) => (Math.abs(b.push) > Math.abs(a.push) ? b : a));
      const et = most.type.split(" ")[0];
      this.policy.update(st.kase.alert.exploit, et, this.policy.w[st.kase.alert.exploit][et] * 0.5);
    }
  }
}

// --- Naive "Alert-Label Autopilot" baseline: trusts the signature severity word alone ---
class LabelAutopilot {
  constructor(onLog = () => {}) {
    this.onLog = onLog;
    this.stats = { total: 0, resolved: 0, blocked: 0, falseBlocks: 0, missedBreaches: 0, correct: 0 };
  }
  ingest(kase) {
    this.stats.total++;
    const word = kase.alert.severityWord;
    let action, blocked = false;
    if (word === "EXPLOIT" || word === "WEB" || word === "TROJAN") { action = "auto-blocked (label looked severe)"; blocked = true; }
    else if (word === "POLICY") { action = "logged only (label seemed low-severity)"; }
    else { action = "ignored (label read as routine scan)"; }

    this.stats.resolved++;
    if (blocked) this.stats.blocked++;
    const correct = blocked === kase.gt.succeeded;
    if (correct) this.stats.correct++;
    if (blocked && !kase.gt.succeeded) this.stats.falseBlocks++;
    if (!blocked && kase.gt.succeeded) this.stats.missedBreaches++;

    this.onLog(kase.id, `Alert #${kase.id} '${kase.alert.sig}' (${word}) on ${kase.target} → ${action}`);
  }
}

const SentinelOpsSOC = { makeRng, choice, uniform, ASSETS, ALERT_TYPES, EVIDENCE_TYPES, SocPolicy, SocEnvironment, AdaptiveSocAgent, LabelAutopilot };
if (typeof module !== "undefined" && module.exports) {
  module.exports = SentinelOpsSOC; // Node (test harness)
} else if (typeof window !== "undefined") {
  window.SentinelOpsSOC = SentinelOpsSOC; // browser (docs/index.html)
}