# 🛡️ SentinelOps

## Autonomous SOC Investigation & Response Agent

> **The alert label is a hint. It is not the verdict.**

SentinelOps is an experimental **AI-assisted Security Operations Center (SOC) agent** that investigates security alerts by correlating evidence from multiple security sources instead of trusting the alert signature alone.

It receives simulated **NIDS / Snort / Suricata alerts**, investigates the targeted asset, checks vulnerability and configuration context, retrieves server-side evidence, determines whether an attack actually succeeded, performs a sandboxed response when justified, verifies the result, and can reconsider its conclusion when new evidence or human feedback appears.

### Core loop

```text
🚨 ALERT
   ↓
🔎 INVESTIGATE
   ↓
🧩 CORRELATE EVIDENCE
   ↓
🧠 DETERMINE ATTACK OUTCOME
   ↓
🛡️ RESPOND
   ↓
✅ VERIFY
   ↓
🔄 RECONSIDER / ADAPT
```

---

## 🎯 The Problem

A security alert does **not** necessarily mean a successful compromise.

For example:

```text
🚨 Suricata:
"Log4Shell exploitation attempt detected"
```

A naive SOC automation system might immediately conclude:

```text
EXPLOIT ALERT
      ↓
BLOCK SOURCE IP
```

But the alert alone does not answer the important questions:

- Was the target actually vulnerable?
- Was the exploit request successful?
- Did the server execute anything?
- Did authentication succeed?
- Did the attacker obtain a session?
- Was the request blocked by a WAF?
- Was the asset patched?
- Did suspicious activity occur after the alert?
- Is the alert a false positive?

SentinelOps treats the alert as the **starting point of an investigation**, not the conclusion.

---

# 🧠 Core Idea

### Don't ask:

> "What does this alert label say?"

### Ask:

> "What evidence do I need to determine what actually happened?"

This changes the workflow from:

```text
ALERT → ACTION
```

to:

```text
ALERT
  ↓
EVIDENCE
  ↓
CORRELATION
  ↓
ASSESSMENT
  ↓
RESPONSE
  ↓
VERIFICATION
  ↓
REASSESSMENT
```

---

# 🏗️ SOC Architecture

```text
                     ┌─────────────────────┐
                     │ NIDS / Snort /       │
                     │ Suricata Alert      │
                     └──────────┬──────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │ Alert Normalization │
                     └──────────┬──────────┘
                                │
                                ▼
                 ┌────────────────────────────┐
                 │     SentinelOps SOC Agent  │
                 │                            │
                 │  Investigation Planner    │
                 │  Evidence Correlation      │
                 │  Decision / Policy Engine  │
                 └─────────────┬──────────────┘
                               │
             ┌─────────────────┼─────────────────┐
             │                 │                 │
             ▼                 ▼                 ▼
       🖥️ Asset Data      🐞 Vulnerability   📜 Server Logs
                           / CVE Context
             │                 │                 │
             └─────────────────┼─────────────────┘
                               │
                               ▼
                    ┌────────────────────┐
                    │ Evidence Assessment│
                    └─────────┬──────────┘
                              │
              ┌───────────────┼────────────────┐
              ▼               ▼                ▼
        ❌ ATTACK         ❓ INCONCLUSIVE    ✅ ATTACK
           FAILED                             SUCCEEDED
              │               │                │
              │               ▼                ▼
              │          👨‍💻 ESCALATE     🛡️ RESPONSE
              │                                │
              │                                ▼
              │                       🚧 SIMULATED FIREWALL
              │                                │
              └────────────────┬───────────────┘
                               ▼
                         🔍 VERIFY EFFECT
                               │
                               ▼
                       🆕 NEW EVIDENCE?
                               │
                               ▼
                         🔄 RECONSIDER
```

---

# 🔬 Evidence Sources

SentinelOps correlates multiple simulated security data sources.

### 🚨 NIDS / Suricata / Snort Alerts

Examples include:

- Log4Shell exploitation attempts
- Apache Struts RCE attempts
- SQL injection
- SSH brute force
- policy/scan events

The alert signature is intentionally treated as **one piece of evidence**, rather than unquestioned truth.

### 🖥️ Asset Inventory

The agent considers:

- target asset
- exposure
- criticality
- software
- configuration
- known weaknesses

Example:

```text
web-app-01
├── Internet-facing
├── High criticality
├── Apache / Struts
└── Vulnerable to Log4Shell
```

### 🐞 Vulnerability Context

Synthetic vulnerability/CVE knowledge is used to determine whether an attack is plausible against the targeted asset.

### 📜 Server Evidence

Server-side evidence helps distinguish:

```text
ATTACK ATTEMPT
```

from:

```text
SUCCESSFUL COMPROMISE
```

Examples include:

- authentication results
- rejected requests
- suspicious activity
- execution indicators
- outbound activity
- forensic updates

---

# 🧠 Evidence-Driven Verdicts

SentinelOps can distinguish between different outcomes:

```text
✅ ATTACK SUCCEEDED

❌ ATTACK FAILED

❓ INCONCLUSIVE

⚠️ FALSE POSITIVE
```

The important distinction is:

> **Detection ≠ compromise**

An exploit attempt can be detected without the exploit succeeding.

---

# 🛡️ Simulated Response

When the evidence justifies containment, SentinelOps can perform a **simulated firewall block**.

Example:

```text
Assessment:
ATTACK SUCCEEDED

Action:
BLOCK 185.x.x.x

Result:
Simulated firewall rule created

Verification:
0 further packets observed

Response:
CONFIRMED EFFECTIVE
```

No real production firewall is modified by the browser simulation.

---

# 🔍 Verify, Don't Assume

A response is not considered successful simply because the action was issued.

SentinelOps verifies the environment again.

```text
BLOCK
  ↓
RE-CHECK TRAFFIC
  ↓
ANY FURTHER PACKETS?
  │
  ├── YES → investigate again
  │
  └── NO  → response confirmed
```

This closes the loop between:

**action → environment → evidence**

---

# 🔄 Reconsideration

Security investigations are not always complete when the first verdict is produced.

New evidence may arrive later.

Example:

```text
Initial evidence
      ↓
INCONCLUSIVE
      ↓
Investigation continues
      ↓
Delayed forensic evidence
      ↓
Outbound data transfer discovered
      ↓
ATTACK SUCCEEDED
      ↓
Retroactive containment
```

This allows SentinelOps to change an earlier assessment when the evidence changes.

---

# 👨‍💻 Human Analyst Override

Autonomous systems should not assume they are always correct.

SentinelOps therefore supports analyst feedback.

```text
                Agent verdict
                     │
              ┌──────┴──────┐
              │             │
         Analyst agrees  Analyst disagrees
              │             │
              ▼             ▼
           Continue       Override
                            │
                  ┌─────────┴─────────┐
                  ▼                   ▼
             False Positive       Confirmed Attack
                  │                   │
               Unblock             Block
```

The system can also use the correction as feedback for future evidence weighting.

---

# 🧪 Controlled SOC Simulation

The deployed demonstration is intentionally **100% client-side**.

It does not require:

- a backend
- an API key
- a real SIEM
- a real firewall
- access to production infrastructure

Instead, it provides a controlled environment for demonstrating the investigation and response logic.

---

# ⚔️ SentinelOps vs Alert-Label Autopilot

The project includes a deliberately simple baseline.

### Alert-Label Autopilot

```text
EXPLOIT / WEB / TROJAN
        ↓
AUTO-BLOCK

POLICY
        ↓
LOG ONLY

SCAN
        ↓
IGNORE
```

It makes decisions from the alert label.

### SentinelOps SOC Agent

```text
ALERT
 ↓
TARGET ASSET
 ↓
VULNERABILITY CONTEXT
 ↓
SERVER EVIDENCE
 ↓
CORRELATION
 ↓
VERDICT
 ↓
RESPONSE
 ↓
VERIFICATION
 ↓
RECONSIDERATION
```

Both systems process the **same simulated alert stream**, making the comparison focused on the investigation strategy rather than different inputs.

---

# 📊 What the Demo Measures

The SOC simulation tracks metrics such as:

- 🎯 correct-response rate
- 🚫 false blocks
- 🕵️ missed breaches
- 🛡️ simulated blocks
- 👨‍💻 analyst escalations
- 🔄 reconsiderations
- ✋ human overrides

The goal is not simply to maximize blocking.

A good SOC agent must balance:

```text
DETECTION
    +
INVESTIGATION
    +
CONTAINMENT
    +
FALSE-POSITIVE CONTROL
    +
HUMAN ESCALATION
```

---

# 🧩 Core Components

| Component | Purpose |
|---|---|
| `index.html` | Interactive browser SOC demonstration |
| `soc_core.js` | Core client-side SOC simulation logic |
| `agent.py` | Python agent implementation |
| `environment.py` | Simulated security environment |
| `policy.py` | Adaptive decision/evidence policy |
| `reasoner.py` | Reasoning layer |
| `planner.py` | Investigation/planning logic |
| `run_demo.py` | Simulation runner |
| `tools/` | Agent capabilities/tools |
| `safety/` | Safety and execution constraints |
| `sample_run.log` | Example execution trace |
| `Go_to_market.md` | Productization / business direction |

---

# 🔐 Safety Model

SentinelOps is an experimental cybersecurity research and portfolio project.

The current public demonstration operates on **synthetic security events and simulated response actions**.

It does not provide autonomous access to real production infrastructure.

A real deployment would require additional controls including:

- 🔐 authentication
- 🧑‍⚖️ authorization
- 🛡️ least-privilege tool permissions
- 📋 audit logging
- 🚦 response approval policies
- 🔄 rollback mechanisms
- 💥 blast-radius controls
- 👨‍💻 human escalation
- 🔎 forensic validation

---

# 🚀 Demo

Run the interactive investigation:

```bash
python3 run_demo.py --trace
```

The browser demonstration can also be deployed as a static website because the SOC simulation runs entirely client-side.

---

# 🗺️ Roadmap

## Phase 1 — SOC Investigation

- [x] Simulated NIDS alerts
- [x] Snort/Suricata-style signatures
- [x] Asset inventory
- [x] Vulnerability context
- [x] Server evidence
- [x] Evidence correlation
- [x] Attack outcome assessment
- [x] Simulated firewall response
- [x] Response verification
- [x] Delayed evidence / reconsideration
- [x] Human analyst override

## Phase 2 — Real SOC Integrations

- [ ] Real Suricata ingestion
- [ ] Zeek integration
- [ ] Wazuh integration
- [ ] SIEM event ingestion
- [ ] Real CVE/NVD enrichment
- [ ] Threat-intelligence enrichment
- [ ] Persistent incident database

## Phase 3 — Production-Grade Agent

- [ ] FastAPI backend
- [ ] PostgreSQL
- [ ] Redis
- [ ] Authentication / RBAC
- [ ] Immutable audit trail
- [ ] Tool permission system
- [ ] Human approval workflows
- [ ] Response rollback
- [ ] Production observability

## Phase 4 — Autonomous SOC

- [ ] Multi-stage investigations
- [ ] Threat hunting
- [ ] Incident memory
- [ ] Cross-alert correlation
- [ ] Campaign detection
- [ ] Attack-chain reconstruction
- [ ] MITRE ATT&CK mapping
- [ ] Adaptive investigation policies

---

# 🎓 What SentinelOps Demonstrates

SentinelOps explores the intersection of:

🛡️ Cybersecurity  
🤖 Agentic AI  
🔎 Security Investigation  
🚨 SOC Automation  
📊 Security Analytics  
🧠 Evidence-Based Reasoning  
🔄 Adaptive Decision Making  
👨‍💻 Human-in-the-Loop Security  
⚙️ Automated Response  

The central idea is simple:

> **Don't let the alert make the decision. Let the evidence make the decision.**

---

# ⚠️ Project Status

**Experimental / Research Prototype**

SentinelOps is designed to demonstrate an autonomous SOC investigation and response workflow in a controlled environment.

It is **not currently a production SIEM, EDR, SOAR, or autonomous security appliance.**

---

## 📜 License

Add an explicit open-source license if you intend to accept external use or contributions.
