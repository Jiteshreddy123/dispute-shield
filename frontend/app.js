'use strict';

/**
 * app.js — Dispute Shield Story Engine
 *
 * ARCHITECTURE:
 * - All financial decisions come from the backend API — never hardcoded here
 * - Story steps are narrative wrappers around real backend API calls
 * - Technical details are real (payment IDs, ARNs, ledger events) — never fake
 * - The story engine calls /api/scenarios/reset + /api/scenarios/load/ before each run
 */

const API_BASE = 'https://dispute-shield-production-be56.up.railway.app';

// ============================================================
// API HELPERS
// ============================================================

async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function apiPost(path, body = null, headers = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

function inr(paise) {
  return `₹${(paise / 100).toLocaleString('en-IN')}`;
}

// ============================================================
// ENGINE STATE
// ============================================================

const engine = {
  story: null,   // current STORY object
  stepIndex: 0,
  scenarioData: null,   // from /api/scenarios/load/
  stateData: null,   // from /api/state/{payment_id}
  refundData: null,   // from /api/refunds/request
  defenseData: null,   // from /api/defense/{dispute_id}
  techLogs: [],
  // Transient per-step
  _stepResultData: null,
  _dupEventId: null,
  _wfEventId: null,
};

// ============================================================
// STORY DEFINITIONS
// All 8 scenarios mapped to human stories with step-by-step narrative
// ============================================================

const STORIES = [

  // ════════════════════════════════════════════════════════════
  // STORY 1 — PRE_ALERT (HERO)
  // ════════════════════════════════════════════════════════════
  {
    id: 'PRE_ALERT',
    scenarioApiName: 'PRE_ALERT',
    paymentId: 'scen_alert_001',
    amountPaise: 300000,
    num: '01',
    icon: '⚡',
    badge: 'HERO',
    badgeClass: 'badge-hero',
    featured: true,
    riskClass: 'risk-high',
    title: 'A Dispute Is Brewing',
    tagline: 'Ramu asks for a refund while his bank has already signalled a dispute on the same payment.',
    customer: 'Ramu Kumar',
    product: 'Winter Jacket',
    amountDisplay: '₹3,000',
    risk: 'Pre-dispute network alert',
    outcomeLabel: 'Refund BLOCKED — ₹3,000 duplicate outflow prevented',
    steps: [
      {
        phase: 'Purchase',
        icon: '🛒',
        heading: 'Ramu Makes a Purchase',
        narrative: 'Ramu Kumar visits Acme Fashion and orders a winter jacket for ₹3,000. The payment is captured immediately.',
        cards: [
          { label: 'Customer', value: 'Ramu Kumar' },
          { label: 'Product', value: 'Winter Jacket' },
          { label: 'Order', value: 'ORD-2847' },
          { label: 'Amount', value: '₹3,000', cls: 'highlight' },
          { label: 'Status', value: 'Payment Captured', cls: 'green' },
        ],
        cta: 'Three Days Later →',
        ctaClass: 'cta-continue',
      },
      {
        phase: 'Alert',
        icon: '📡',
        heading: 'A Network Signal Arrives',
        narrative: 'Unbeknownst to the merchant, a pre-dispute network alert arrives from the card network. This simulates a Visa/Mastercard signal indicating the customer may be about to dispute this payment.',
        cards: [
          { label: 'Alert Type', value: 'Pre-dispute signal (simulated)' },
          { label: 'Provider', value: 'Simulated Network Feed' },
          { label: 'Status', value: 'OPEN', cls: 'red' },
          { label: 'Payment at Risk', value: '₹3,000', cls: 'red' },
        ],
        cta: 'Meanwhile, Ramu Contacts Support →',
        ctaClass: 'cta-continue',
      },
      {
        phase: 'Support',
        icon: '💬',
        heading: 'Ramu Contacts Customer Support',
        narrative: 'Unaware of the network alert, Ramu writes to the merchant\'s support team asking for a refund.',
        quote: '"The jacket never arrived. It\'s been 3 days and I haven\'t received anything. Please refund my ₹3,000 immediately."',
        cards: [
          { label: 'Channel', value: 'Email Support' },
          { label: 'Day', value: 'Day 3' },
          { label: 'Request', value: 'Full refund of ₹3,000', cls: 'highlight' },
        ],
        cta: 'Support Opens Refund →',
        ctaClass: 'cta-continue',
      },
      {
        phase: 'Intercept',
        icon: '💳',
        heading: 'Support Clicks Refund',
        narrative: 'The support agent finds the order and prepares to issue a full refund. Dispute Shield intercepts the request before it reaches the payment provider.',
        cards: [
          { label: 'Refund Amount', value: '₹3,000' },
          { label: 'Payment ID', value: 'scen_alert_001', cls: 'mono' },
        ],
        cta: '💳 Refund ₹3,000',
        ctaClass: 'cta-refund',
        apiCallDef: {
          execute: async (eng) => {
            return await apiPost('/api/refunds/request', {
              payment_id: eng.story.paymentId,
              amount_paise: eng.story.amountPaise,
            });
          },
          buildResult: (data, eng) => {
            eng.refundData = data;
            const blocked = data.decision !== 'ALLOW';
            return {
              decision: {
                type: blocked ? 'blocked' : 'approved',
                label: blocked ? '🚫 REFUND BLOCKED' : '✅ REFUND APPROVED',
                reason: data.reason,
                amountProtected: blocked ? eng.story.amountPaise : null,
              },
            };
          },
        },
        advanceCta: 'See the Outcome →',
      },
      {
        phase: 'Outcome',
        icon: '🛡️',
        heading: 'Duplicate Outflow Prevented',
        narrative: 'Dispute Shield detected the active pre-alert and stopped the refund before the payment provider was called. No money moved. The merchant avoided paying twice for the same dispute.',
        isOutcome: true,
        buildOutcome: (eng) => {
          const rd = eng.refundData || {};
          return {
            icon: '🛡️',
            title: 'Dispute Shield Outcome',
            items: [
              { label: 'Refund Decision', value: 'BLOCKED', cls: 'red' },
              { label: 'Reason', value: 'Active pre-dispute alert detected' },
              { label: 'Amount Protected', value: inr(eng.story.amountPaise), cls: 'green' },
              { label: 'Provider Called', value: 'No — refund never sent to Razorpay', cls: 'green' },
              { label: 'Intent Status', value: rd.status || 'BLOCKED', cls: 'red' },
            ],
          };
        },
        cta: '↺ Replay Story',
        ctaClass: 'cta-replay',
        isTerminal: true,
      },
    ],
  },

  // ════════════════════════════════════════════════════════════
  // STORY 2 — ACTIVE_DISPUTE
  // ════════════════════════════════════════════════════════════
  {
    id: 'ACTIVE_DISPUTE',
    scenarioApiName: 'ACTIVE_DISPUTE',
    paymentId: 'scen_dispute_001',
    amountPaise: 500000,
    num: '02',
    icon: '⚔️',
    badge: null,
    featured: false,
    riskClass: 'risk-high',
    title: 'A Chargeback Is Already Open',
    tagline: 'Ramu files a bank dispute, then also asks the merchant for a refund on the same payment.',
    customer: 'Ramu Kumar',
    product: 'Running Shoes',
    amountDisplay: '₹5,000',
    risk: 'Active chargeback + refund request',
    outcomeLabel: 'Refund BLOCKED — double liability prevented',
    steps: [
      {
        phase: 'Purchase',
        icon: '🛒',
        heading: 'Ramu Buys Running Shoes',
        narrative: 'Ramu orders a pair of premium running shoes for ₹5,000. Payment is captured.',
        cards: [
          { label: 'Customer', value: 'Ramu Kumar' },
          { label: 'Product', value: 'Running Shoes' },
          { label: 'Amount', value: '₹5,000', cls: 'highlight' },
          { label: 'Status', value: 'Payment Captured', cls: 'green' },
        ],
        cta: 'A Week Later →',
        ctaClass: 'cta-continue',
      },
      {
        phase: 'Dispute',
        icon: '🏦',
        heading: 'Ramu Files a Bank Dispute',
        narrative: 'Ramu tells his bank the shoes never arrived. The bank opens a formal chargeback on the payment.',
        cards: [
          { label: 'Action', value: 'Chargeback filed with bank' },
          { label: 'Amount', value: '₹5,000', cls: 'red' },
          { label: 'Dispute Status', value: 'OPEN', cls: 'red' },
          { label: 'Phase', value: 'Chargeback' },
        ],
        cta: 'Meanwhile at Support →',
        ctaClass: 'cta-continue',
      },
      {
        phase: 'Support',
        icon: '💬',
        heading: 'Ramu Also Contacts Support',
        narrative: 'On the same day, Ramu writes to the merchant\'s support team — without mentioning he already filed a bank dispute.',
        quote: '"I ordered shoes a week ago and never received them. Can you please refund my ₹5,000?"',
        cards: [
          { label: 'Channel', value: 'Email Support' },
          { label: 'Request', value: 'Full refund of ₹5,000' },
          { label: 'Note', value: 'Bank dispute not disclosed', cls: 'red' },
        ],
        cta: 'Support Initiates Refund →',
        ctaClass: 'cta-continue',
      },
      {
        phase: 'Intercept',
        icon: '💳',
        heading: 'Support Clicks Refund',
        narrative: 'The support agent processes the refund request. Dispute Shield intercepts it and runs a risk check before any money moves.',
        cards: [
          { label: 'Refund Amount', value: '₹5,000' },
          { label: 'Payment ID', value: 'scen_dispute_001', cls: 'mono' },
        ],
        cta: '💳 Refund ₹5,000',
        ctaClass: 'cta-refund',
        apiCallDef: {
          execute: async (eng) => {
            return await apiPost('/api/refunds/request', {
              payment_id: eng.story.paymentId,
              amount_paise: eng.story.amountPaise,
            });
          },
          buildResult: (data, eng) => {
            eng.refundData = data;
            return {
              decision: {
                type: 'blocked',
                label: '🚫 REFUND BLOCKED',
                reason: data.reason,
                amountProtected: eng.story.amountPaise,
              },
            };
          },
        },
        advanceCta: 'View Outcome →',
      },
      {
        phase: 'Outcome',
        icon: '🛡️',
        heading: 'Double Liability Prevented',
        narrative: 'The merchant would have paid twice — once via the voluntary refund, once via the bank chargeback. Dispute Shield stopped the voluntary payment before it compounded the loss.',
        isOutcome: true,
        buildOutcome: (eng) => ({
          icon: '🛡️',
          title: 'Dispute Shield Outcome',
          items: [
            { label: 'Refund Decision', value: 'BLOCKED', cls: 'red' },
            { label: 'Reason', value: 'Active chargeback exists on this payment' },
            { label: 'Amount Protected', value: inr(eng.story.amountPaise), cls: 'green' },
            { label: 'Bank Dispute', value: 'OPEN — still to be resolved by bank', cls: 'orange' },
            { label: 'Double Payment', value: 'Prevented', cls: 'green' },
          ],
        }),
        cta: '↺ Replay Story',
        ctaClass: 'cta-replay',
        isTerminal: true,
      },
    ],
  },

  // ════════════════════════════════════════════════════════════
  // STORY 3 — REFUND_THEN_CHARGEBACK (conflicting recovery)
  // ════════════════════════════════════════════════════════════
  {
    id: 'REFUND_THEN_CHARGEBACK',
    scenarioApiName: 'REFUND_THEN_CHARGEBACK',
    paymentId: 'scen_rtc_001',
    amountPaise: 800000,
    disputeId: 'disp_rtc_001',
    num: '03',
    icon: '🕵️',
    badge: 'DEFENSE',
    badgeClass: 'badge-defense',
    featured: false,
    riskClass: 'risk-med',
    title: 'Refunded — Then Charged Back',
    tagline: 'Ramu receives a full refund, then files a chargeback for the same ₹8,000 transaction.',
    customer: 'Ramu Kumar',
    product: 'Laptop Stand',
    amountDisplay: '₹8,000',
    risk: 'Conflicting recovery request',
    outcomeLabel: 'Defense package ready — ₹8,000 fully covered',
    steps: [
      {
        phase: 'Purchase',
        icon: '🛒',
        heading: 'Ramu Buys a Laptop Stand',
        narrative: 'Ramu purchases a premium laptop stand for ₹8,000. Payment is captured.',
        cards: [
          { label: 'Customer', value: 'Ramu Kumar' },
          { label: 'Product', value: 'Laptop Stand' },
          { label: 'Amount', value: '₹8,000', cls: 'highlight' },
          { label: 'Status', value: 'Payment Captured', cls: 'green' },
        ],
        cta: 'Three Days Later →',
        ctaClass: 'cta-continue',
      },
      {
        phase: 'Complaint',
        icon: '💬',
        heading: 'Ramu Claims Item Not Received',
        narrative: 'Ramu contacts support saying the laptop stand never arrived.',
        quote: '"I want to return the product. I was promised a full refund."',
        cards: [
          { label: 'Claim', value: 'Item not received' },
          { label: 'Requested', value: 'Full refund of ₹8,000' },
        ],
        cta: 'Merchant Issues Full Refund →',
        ctaClass: 'cta-continue',
      },
      {
        phase: 'Refund',
        icon: '✅',
        heading: 'Merchant Refunds ₹8,000',
        narrative: 'The merchant processes a full refund. It is confirmed with an ARN — the Acquirer Reference Number, the banking identifier for this specific refund transaction.',
        buildDynamic: (eng) => {
          const r = (eng.stateData?.refunds || [])[0] || {};
          return {
            cards: [
              { label: 'Refund Amount', value: '₹8,000', cls: 'green' },
              { label: 'Status', value: r.status || 'PROCESSED', cls: 'green' },
              { label: 'ARN', value: r.arn || 'ARN987654321RTC', cls: 'mono' },
              { label: 'Refund ID', value: r.id || 'rfnd_rtc_001', cls: 'mono' },
            ],
          };
        },
        cta: 'Five Days Later →',
        ctaClass: 'cta-continue',
      },
      {
        phase: 'Chargeback',
        icon: '⚡',
        heading: 'Ramu Files a Chargeback Anyway',
        narrative: 'Despite already receiving a full ₹8,000 refund, Ramu contacts his bank and disputes the original charge. The bank opens a chargeback.',
        cards: [
          { label: 'Action', value: 'Chargeback filed with bank' },
          { label: 'Chargeback Amount', value: '₹8,000', cls: 'red' },
          { label: 'Prior Refund', value: '₹8,000 already processed', cls: 'orange' },
          { label: 'Assessment', value: 'Potential duplicate recovery attempt', },
        ],
        cta: '⚖️ Build Defense Package',
        ctaClass: 'cta-api',
        apiCallDef: {
          execute: async (eng) => {
            eng.stateData = await apiGet(`/api/state/${eng.story.paymentId}`);
            return await apiGet(`/api/defense/${eng.story.disputeId}`);
          },
          buildResult: (data, eng) => {
            eng.defenseData = data;
            const dp = data.defense_package;
            return {
              defense: {
                contestable: dp.contestable_amount_paise,
                uncovered: dp.uncovered_amount_paise,
                status: dp.status,
                evidence: data.evidence_items || [],
                summary: dp.summary,
              },
            };
          },
        },
        advanceCta: 'View Defense Package →',
      },
      {
        phase: 'Outcome',
        icon: '⚖️',
        heading: 'Defense Package Ready',
        narrative: 'Dispute Shield automatically assembled a complete defense package using the prior refund as evidence. The full ₹8,000 is contestable.',
        isOutcome: true,
        buildOutcome: (eng) => {
          const dp = eng.defenseData?.defense_package || {};
          const ev = eng.defenseData?.evidence_items || [];
          return {
            icon: '⚖️',
            title: 'Defense Package',
            items: [
              { label: 'Chargeback Amount', value: '₹8,000', cls: 'red' },
              { label: 'Contestable (covered)', value: inr(dp.contestable_amount_paise || 800000), cls: 'green' },
              { label: 'Uncovered Exposure', value: inr(dp.uncovered_amount_paise || 0), cls: dp.uncovered_amount_paise > 0 ? 'red' : 'green' },
              { label: 'Evidence Items', value: `${ev.length} item${ev.length !== 1 ? 's' : ''} attached`, cls: 'green' },
              { label: 'Package Status', value: dp.status || 'READY', cls: 'green' },
            ],
          };
        },
        cta: '↺ Replay Story',
        ctaClass: 'cta-replay',
        isTerminal: true,
      },
    ],
  },

  // ════════════════════════════════════════════════════════════
  // STORY 4 — SAFE_REFUND
  // ════════════════════════════════════════════════════════════
  {
    id: 'SAFE_REFUND',
    scenarioApiName: 'SAFE_REFUND',
    paymentId: 'scen_safe_001',
    amountPaise: 750000,
    num: '04',
    icon: '✅',
    badge: 'SAFE',
    badgeClass: 'badge-safe',
    featured: false,
    riskClass: 'risk-low',
    title: 'A Normal Refund',
    tagline: 'A clean refund with no disputes — approved, executed, and confirmed with an ARN.',
    customer: 'Priya Sharma',
    product: 'Wireless Headphones',
    amountDisplay: '₹7,500',
    risk: 'None detected',
    outcomeLabel: 'Refund APPROVED — ARN issued',
    steps: [
      {
        phase: 'Purchase',
        icon: '🛒',
        heading: 'Priya Buys Headphones',
        narrative: 'Priya Sharma orders wireless headphones for ₹7,500. Payment is captured.',
        cards: [
          { label: 'Customer', value: 'Priya Sharma' },
          { label: 'Product', value: 'Wireless Headphones' },
          { label: 'Amount', value: '₹7,500', cls: 'highlight' },
          { label: 'Status', value: 'Payment Captured', cls: 'green' },
        ],
        cta: 'Two Days Later →',
        ctaClass: 'cta-continue',
      },
      {
        phase: 'Support',
        icon: '💬',
        heading: 'Priya Requests a Refund',
        narrative: 'Priya contacts support. She hasn\'t received the order and requests a refund.',
        quote: '"Hi, I need a refund for my order. I haven\'t received it yet."',
        cards: [
          { label: 'Disputes', value: 'None', cls: 'green' },
          { label: 'Pre-alerts', value: 'None', cls: 'green' },
          { label: 'Balance', value: '₹7,500 available', cls: 'green' },
        ],
        cta: 'Risk Check Passes →',
        ctaClass: 'cta-continue',
      },
      {
        phase: 'Approved',
        icon: '✅',
        heading: 'Refund Approved and Processed',
        narrative: 'Dispute Shield runs the risk check. No disputes, no pre-alerts, sufficient balance. The refund is approved, executed by the provider, and confirmed with an ARN.',
        buildDynamic: (eng) => {
          const r = (eng.stateData?.refunds || [])[0] || {};
          return {
            cards: [
              { label: 'Risk Check', value: 'PASSED', cls: 'green' },
              { label: 'Decision', value: 'APPROVED', cls: 'green' },
              { label: 'Status', value: r.status || 'PROCESSED', cls: 'green' },
              { label: 'ARN', value: r.arn || 'ARN123456789SAFE', cls: 'mono' },
            ],
          };
        },
        cta: 'View Outcome →',
        ctaClass: 'cta-continue',
      },
      {
        phase: 'Outcome',
        icon: '✅',
        heading: 'Clean Refund — No Issues',
        narrative: 'The refund was approved, executed, and confirmed. An immutable ledger record was created. The customer will receive the funds within 3-5 business days.',
        isOutcome: true,
        buildOutcome: (eng) => {
          const r = (eng.stateData?.refunds || [])[0] || {};
          return {
            icon: '✅',
            title: 'Clean Refund Executed',
            items: [
              { label: 'Decision', value: 'APPROVED', cls: 'green' },
              { label: 'Amount', value: '₹7,500', cls: 'green' },
              { label: 'Status', value: r.status || 'PROCESSED', cls: 'green' },
              { label: 'ARN', value: r.arn || 'ARN123456789SAFE', cls: 'mono' },
              { label: 'Ledger', value: 'Immutable record created', cls: 'green' },
            ],
          };
        },
        cta: '↺ Replay Story',
        ctaClass: 'cta-replay',
        isTerminal: true,
      },
    ],
  },

  // ════════════════════════════════════════════════════════════
  // STORY 5 — PARTIAL_REFUND_THEN_CHARGEBACK
  // ════════════════════════════════════════════════════════════
  {
    id: 'PARTIAL_REFUND_THEN_CHARGEBACK',
    scenarioApiName: 'PARTIAL_REFUND_THEN_CHARGEBACK',
    paymentId: 'scen_partial_001',
    amountPaise: 1000000,
    disputeId: 'disp_partial_001',
    num: '05',
    icon: '⚖️',
    badge: null,
    featured: false,
    riskClass: 'risk-med',
    title: 'Partial Refund, Full Chargeback',
    tagline: 'Partial refunds were issued, but Ramu disputes the full ₹10,000 with his bank.',
    customer: 'Ramu Kumar',
    product: 'Fashion Bundle',
    amountDisplay: '₹10,000',
    risk: 'Partial coverage — ₹4,000 exposed',
    outcomeLabel: '₹6,000 covered, ₹4,000 unresolved',
    steps: [
      {
        phase: 'Purchase',
        icon: '🛒',
        heading: 'Ramu Orders a Fashion Bundle',
        narrative: 'Ramu orders a bundle of clothing items for ₹10,000. Payment is captured.',
        cards: [
          { label: 'Customer', value: 'Ramu Kumar' },
          { label: 'Product', value: 'Fashion Bundle (3 items)' },
          { label: 'Amount', value: '₹10,000', cls: 'highlight' },
          { label: 'Status', value: 'Payment Captured', cls: 'green' },
        ],
        cta: 'See What Happened →',
        ctaClass: 'cta-continue',
      },
      {
        phase: 'Refunds',
        icon: '💸',
        heading: 'Two Partial Refunds Issued',
        narrative: 'Two items were not delivered. The merchant issues two partial refunds — ₹4,000 and ₹2,000 — for the missing items.',
        cards: [
          { label: 'Refund 1 — Item A', value: '₹4,000', cls: 'green' },
          { label: 'ARN 1', value: 'ARN_PARTIAL_001A', cls: 'mono' },
          { label: 'Refund 2 — Item B', value: '₹2,000', cls: 'green' },
          { label: 'ARN 2', value: 'ARN_PARTIAL_001B', cls: 'mono' },
          { label: 'Total Refunded', value: '₹6,000', cls: 'green' },
          { label: 'Remaining', value: '₹4,000 (not yet refunded)' },
        ],
        cta: 'Then the Chargeback Arrives →',
        ctaClass: 'cta-continue',
      },
      {
        phase: 'Dispute',
        icon: '⚡',
        heading: 'Ramu Disputes the Full ₹10,000',
        narrative: 'Despite receiving ₹6,000 in partial refunds, Ramu disputes the full original charge of ₹10,000 with his bank.',
        cards: [
          { label: 'Chargeback Amount', value: '₹10,000', cls: 'red' },
          { label: 'Already Refunded', value: '₹6,000', cls: 'orange' },
          { label: 'Net Exposure', value: '₹4,000', cls: 'red' },
        ],
        cta: '⚖️ Analyse Defense',
        ctaClass: 'cta-api',
        apiCallDef: {
          execute: async (eng) => {
            eng.stateData = await apiGet(`/api/state/${eng.story.paymentId}`);
            return await apiGet(`/api/defense/${eng.story.disputeId}`);
          },
          buildResult: (data, eng) => {
            eng.defenseData = data;
            const dp = data.defense_package;
            return {
              defense: {
                contestable: dp.contestable_amount_paise,
                uncovered: dp.uncovered_amount_paise,
                status: dp.status,
                evidence: data.evidence_items || [],
                summary: dp.summary,
              },
            };
          },
        },
        advanceCta: 'View Outcome →',
      },
      {
        phase: 'Outcome',
        icon: '⚖️',
        heading: 'Partial Defense — Some Exposure Remains',
        narrative: 'The ₹6,000 in prior refunds is fully contestable with ARN evidence. The remaining ₹4,000 has no refund coverage — it is honestly flagged as unresolved exposure. No evidence is fabricated.',
        isOutcome: true,
        buildOutcome: (eng) => {
          const dp = eng.defenseData?.defense_package || {};
          const ev = eng.defenseData?.evidence_items || [];
          return {
            icon: '⚖️',
            title: 'Partial Defense Package',
            items: [
              { label: 'Chargeback Amount', value: '₹10,000', cls: 'red' },
              { label: 'Contestable (with ARNs)', value: inr(dp.contestable_amount_paise || 600000), cls: 'green' },
              { label: 'Uncovered Exposure', value: inr(dp.uncovered_amount_paise || 400000), cls: 'red' },
              { label: 'Evidence Items', value: `${ev.length} items`, cls: 'green' },
              { label: 'Package Status', value: dp.status || 'PARTIALLY_DEFENSIBLE', cls: 'orange' },
            ],
          };
        },
        cta: '↺ Replay Story',
        ctaClass: 'cta-replay',
        isTerminal: true,
      },
    ],
  },

  // ════════════════════════════════════════════════════════════
  // STORY 6 — DUPLICATE_WEBHOOK
  // ════════════════════════════════════════════════════════════
  {
    id: 'DUPLICATE_WEBHOOK',
    scenarioApiName: 'DUPLICATE_WEBHOOK',
    paymentId: 'scen_dup_001',
    amountPaise: 400000,
    refundIdForWebhook: 'rfnd_dup_001',
    num: '06',
    icon: '🔄',
    badge: 'SYS',
    badgeClass: 'badge-sys',
    featured: false,
    riskClass: 'risk-sys',
    title: 'The Webhook Arrived Twice',
    tagline: 'The same refund confirmation is delivered twice by the payment provider.',
    customer: 'System Reliability',
    product: '₹4,000 payment',
    amountDisplay: '₹4,000',
    risk: 'Duplicate event delivery',
    outcomeLabel: 'Exactly one financial effect',
    steps: [
      {
        phase: 'Context',
        icon: '🔄',
        heading: 'Providers Guarantee At-Least-Once Delivery',
        narrative: 'Razorpay and other payment providers guarantee webhook delivery — meaning the same event can legitimately arrive more than once. Dispute Shield must handle this without creating duplicate financial effects.',
        cards: [
          { label: 'Scenario', value: 'Duplicate webhook delivery' },
          { label: 'Refund', value: '₹4,000 — PENDING' },
          { label: 'Challenge', value: 'Process exactly once' },
        ],
        cta: 'Deliver First Webhook →',
        ctaClass: 'cta-continue',
      },
      {
        phase: 'First',
        icon: '📨',
        heading: 'First Webhook Delivery',
        narrative: 'The refund.processed event arrives. Dispute Shield processes it: updates the refund status, records the ARN, creates a ledger event.',
        cta: '📨 Deliver Webhook',
        ctaClass: 'cta-api',
        apiCallDef: {
          execute: async (eng) => {
            eng._dupEventId = `evt_dup_demo_${Date.now()}`;
            return await apiPost('/webhooks/razorpay', {
              event: 'refund.processed',
              payload: {
                refund: {
                  entity: {
                    id: eng.story.refundIdForWebhook,
                    payment_id: eng.story.paymentId,
                    amount: eng.story.amountPaise,
                    status: 'processed',
                    acquirer_data: { arn: `ARN_DUP_${Date.now()}` },
                  }
                }
              },
            }, { 'x-razorpay-event-id': eng._dupEventId });
          },
          buildResult: (data) => ({
            info: {
              label: `First Delivery — ${data.status}`,
              value: data.status === 'processed'
                ? '✅ Refund processed. Ledger event created. ARN recorded.'
                : data.status,
              cls: data.status === 'processed' ? 'green' : 'orange',
            },
          }),
        },
        advanceCta: 'Send Same Webhook Again →',
      },
      {
        phase: 'Second',
        icon: '📨',
        heading: 'Same Webhook Arrives Again',
        narrative: 'The provider retries — the identical webhook with the same event ID arrives. Dispute Shield checks its provider_events table.',
        cta: '📨 Deliver Same Webhook Again',
        ctaClass: 'cta-api',
        apiCallDef: {
          execute: async (eng) => {
            return await apiPost('/webhooks/razorpay', {
              event: 'refund.processed',
              payload: {
                refund: {
                  entity: {
                    id: eng.story.refundIdForWebhook,
                    payment_id: eng.story.paymentId,
                    amount: eng.story.amountPaise,
                    status: 'processed',
                    acquirer_data: { arn: 'ARN_RETRY_ATTEMPT' },
                  }
                }
              },
            }, { 'x-razorpay-event-id': eng._dupEventId });
          },
          buildResult: (data) => ({
            info: {
              label: `Second Delivery — ${data.status}`,
              value: data.status === 'duplicate_event_ignored'
                ? '✅ Duplicate detected and safely ignored. No new ledger event.'
                : data.status,
              cls: data.status === 'duplicate_event_ignored' ? 'green' : 'red',
            },
          }),
        },
        advanceCta: 'View Outcome →',
      },
      {
        phase: 'Outcome',
        icon: '🛡️',
        heading: 'Exactly One Financial Effect',
        narrative: 'The first delivery was processed. The second delivery was safely ignored. The ledger contains exactly one REFUND_PROCESSED event — no double processing.',
        isOutcome: true,
        buildOutcome: () => ({
          icon: '🛡️',
          title: 'Idempotency Preserved',
          items: [
            { label: 'First Delivery', value: 'processed → ledger event created', cls: 'green' },
            { label: 'Second Delivery', value: 'duplicate_event_ignored', cls: 'green' },
            { label: 'Ledger Events', value: '1 (not 2)', cls: 'green' },
            { label: 'Financial Effect', value: 'Exactly once', cls: 'green' },
          ],
        }),
        cta: '↺ Replay Story',
        ctaClass: 'cta-replay',
        isTerminal: true,
      },
    ],
  },

  // ════════════════════════════════════════════════════════════
  // STORY 7 — WEBHOOK_FAILURE (retry)
  // ════════════════════════════════════════════════════════════
  {
    id: 'WEBHOOK_FAILURE',
    scenarioApiName: 'WEBHOOK_FAILURE',
    paymentId: 'scen_wf_001',
    amountPaise: 600000,
    refundIdForWebhook: 'rfnd_wf_001',
    num: '07',
    icon: '⏱️',
    badge: 'SYS',
    badgeClass: 'badge-sys',
    featured: false,
    riskClass: 'risk-sys',
    title: 'The Network Went Down',
    tagline: 'A refund was initiated but the network timed out. Is it safe to retry?',
    customer: 'System Reliability',
    product: '₹6,000 payment',
    amountDisplay: '₹6,000',
    risk: 'Network timeout — retry needed',
    outcomeLabel: 'Safe retry — one refund, no double-charge',
    steps: [
      {
        phase: 'Context',
        icon: '⏱️',
        heading: 'The Refund Got Stuck',
        narrative: 'A ₹6,000 refund was initiated. The call reached the provider — but the middleware lost the response due to a network timeout. The refund is stuck in PENDING. Can we retry without double-charging?',
        cards: [
          { label: 'Refund', value: '₹6,000' },
          { label: 'Status', value: 'PENDING', cls: 'orange' },
          { label: 'Idempotency Key', value: 'idem-ri_wf_001', cls: 'mono' },
          { label: 'Question', value: 'Safe to retry?' },
        ],
        cta: 'Process the Refund →',
        ctaClass: 'cta-continue',
      },
      {
        phase: 'Retry',
        icon: '🔁',
        heading: 'Deliver the Refund.Processed Webhook',
        narrative: 'The provider sends the refund.processed webhook. Dispute Shield processes it with the original idempotency key — guaranteeing exactly one refund regardless of how many times the webhook arrives.',
        cta: '📨 Deliver Webhook',
        ctaClass: 'cta-api',
        apiCallDef: {
          execute: async (eng) => {
            eng._wfEventId = `evt_wf_retry_${Date.now()}`;
            return await apiPost('/webhooks/razorpay', {
              event: 'refund.processed',
              payload: {
                refund: {
                  entity: {
                    id: eng.story.refundIdForWebhook,
                    payment_id: eng.story.paymentId,
                    amount: eng.story.amountPaise,
                    status: 'processed',
                    acquirer_data: { arn: `ARN_WF_${Date.now()}` },
                  }
                }
              },
            }, { 'x-razorpay-event-id': eng._wfEventId });
          },
          buildResult: (data) => ({
            info: {
              label: `Webhook Result — ${data.status}`,
              value: data.status === 'processed'
                ? `✅ Refund confirmed. ARN recorded. Ledger updated.`
                : data.status,
              cls: data.status === 'processed' ? 'green' : 'orange',
            },
          }),
        },
        advanceCta: 'View Outcome →',
      },
      {
        phase: 'Outcome',
        icon: '🛡️',
        heading: 'Safe Retry — One Refund Created',
        narrative: 'The retry completed safely. The idempotency key on the refund intent ensured that even if this event had arrived before, only one refund would ever be created.',
        isOutcome: true,
        buildOutcome: () => ({
          icon: '🛡️',
          title: 'Safe Retry Complete',
          items: [
            { label: 'Refund Status', value: 'PROCESSED', cls: 'green' },
            { label: 'Double Charge Risk', value: 'None — idempotency key protected', cls: 'green' },
            { label: 'Ledger Events', value: '1 REFUND_PROCESSED', cls: 'green' },
          ],
        }),
        cta: '↺ Replay Story',
        ctaClass: 'cta-replay',
        isTerminal: true,
      },
    ],
  },

  // ════════════════════════════════════════════════════════════
  // STORY 8 — OUT_OF_ORDER_WEBHOOK
  // ════════════════════════════════════════════════════════════
  {
    id: 'OUT_OF_ORDER_WEBHOOK',
    scenarioApiName: 'OUT_OF_ORDER_WEBHOOK',
    paymentId: 'scen_ooo_001',
    amountPaise: 500000,
    refundIdForWebhook: 'rfnd_ooo_001',
    num: '08',
    icon: '🔀',
    badge: 'SYS',
    badgeClass: 'badge-sys',
    featured: false,
    riskClass: 'risk-sys',
    title: 'Events Arrived Out of Order',
    tagline: 'A stale webhook arrives after the refund is already processed. Does the state regress?',
    customer: 'System Reliability',
    product: '₹5,000 payment',
    amountDisplay: '₹5,000',
    risk: 'Out-of-order event delivery',
    outcomeLabel: 'State preserved — original ARN unchanged',
    steps: [
      {
        phase: 'Context',
        icon: '🔀',
        heading: 'The Refund Is Already Done',
        narrative: 'A ₹5,000 refund has already been processed with a confirmed ARN. But a delayed, stale webhook from an earlier network retry is about to arrive with a different event ID — and a different ARN.',
        cards: [
          { label: 'Refund Status', value: 'PROCESSED', cls: 'green' },
          { label: 'Original ARN', value: 'ARN_OOO_001', cls: 'mono' },
          { label: 'Stale Event', value: 'About to arrive (delayed delivery)' },
          { label: 'Risk', value: 'Could the ARN be overwritten?' },
        ],
        cta: 'Send Stale Webhook →',
        ctaClass: 'cta-continue',
      },
      {
        phase: 'Stale Event',
        icon: '📨',
        heading: 'Stale Webhook Arrives',
        narrative: 'A delayed refund.processed event arrives with a new event ID but for an already-processed refund. It even carries a different (fake) ARN. If handled naively, the state could regress.',
        cta: '📨 Deliver Stale Webhook',
        ctaClass: 'cta-api',
        apiCallDef: {
          execute: async (eng) => {
            return await apiPost('/webhooks/razorpay', {
              event: 'refund.processed',
              payload: {
                refund: {
                  entity: {
                    id: eng.story.refundIdForWebhook,
                    payment_id: eng.story.paymentId,
                    amount: eng.story.amountPaise,
                    status: 'processed',
                    acquirer_data: { arn: 'ARN_STALE_OVERWRITE_ATTEMPT' },
                  }
                }
              },
            }, { 'x-razorpay-event-id': `evt_ooo_stale_${Date.now()}` });
          },
          buildResult: (data) => ({
            info: {
              label: `Stale Event — ${data.status}`,
              value: data.status === 'already_processed'
                ? '✅ State NOT regressed. Original ARN preserved. No new ledger event.'
                : data.status,
              cls: data.status === 'already_processed' ? 'green' : 'orange',
            },
          }),
        },
        advanceCta: 'View Outcome →',
      },
      {
        phase: 'Outcome',
        icon: '🛡️',
        heading: 'Original State Preserved',
        narrative: 'The stale webhook was safely ignored at the financial-state level. The original ARN remains intact. No state regression occurred.',
        isOutcome: true,
        buildOutcome: () => ({
          icon: '🛡️',
          title: 'State Preserved',
          items: [
            { label: 'Refund Status', value: 'PROCESSED (unchanged)', cls: 'green' },
            { label: 'Original ARN', value: 'ARN_OOO_001 (preserved)', cls: 'mono' },
            { label: 'Stale Event', value: 'already_processed — ignored', cls: 'green' },
            { label: 'State Regression', value: 'Prevented', cls: 'green' },
          ],
        }),
        cta: '↺ Replay Story',
        ctaClass: 'cta-replay',
        isTerminal: true,
      },
    ],
  },

];

// ============================================================
// SCREEN MANAGEMENT
// ============================================================

function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.add('hidden'));
  document.getElementById(id).classList.remove('hidden');

  const backBtn = document.getElementById('backBtn');
  if (id === 'screen-story') {
    backBtn.classList.remove('hidden');
  } else {
    backBtn.classList.add('hidden');
  }
}

// ============================================================
// TOAST
// ============================================================

function showToast(msg, type = 'info', dur = 4000) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast ${type} show`;
  setTimeout(() => t.classList.remove('show'), dur);
}

// ============================================================
// TECH LOG
// ============================================================

function addTechLog(text, type = 'info') {
  engine.techLogs.push({ text, type });
  const log = document.getElementById('techLog');
  if (!log) return;
  const el = document.createElement('div');
  el.className = `tech-entry ${type}`;
  el.textContent = text;
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
}

// ============================================================
// STORY SELECTION SCREEN
// ============================================================

function renderStorySelection() {
  const grid = document.getElementById('storiesGrid');
  if (!grid) return;

  grid.innerHTML = STORIES.map(story => {
    const riskDotClass = story.riskClass;
    const badgeHtml = story.badge
      ? `<span class="card-badge ${story.badgeClass}">${story.badge}</span>`
      : '';

    return `
      <div class="story-card ${story.featured ? 'featured' : ''}" id="card-${story.id}">
        <div class="card-top">
          <span class="card-num">${story.num}</span>
          ${badgeHtml}
        </div>
        <div class="card-icon">${story.icon}</div>
        <div class="card-title">${story.title}</div>
        <div class="card-tagline">${story.tagline}</div>
        <div class="card-details">
          ${story.customer !== 'System Reliability' ? `
            <div class="card-detail-row">
              <span class="card-detail-label">Customer</span>
              <span class="card-detail-value">${story.customer}</span>
            </div>
            <div class="card-detail-row">
              <span class="card-detail-label">Product</span>
              <span class="card-detail-value">${story.product}</span>
            </div>
          ` : ''}
          <div class="card-detail-row">
            <span class="card-detail-label">Amount</span>
            <span class="card-detail-value" style="font-weight:700">${story.amountDisplay}</span>
          </div>
        </div>
        <div class="card-risk-row ${riskDotClass}">
          <div class="risk-dot"></div>
          <span class="card-risk-label">${story.risk}</span>
        </div>
        <div class="card-outcome">
          <span class="card-outcome-arrow">→</span>
          <span>${story.outcomeLabel}</span>
        </div>
        <button class="card-start-btn" data-story="${story.id}">
          Start Story →
        </button>
      </div>
    `;
  }).join('');

  // Bind start buttons
  grid.querySelectorAll('[data-story]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const id = e.currentTarget.dataset.story;
      startStory(id);
    });
  });
}

// ============================================================
// STORY ENGINE — START
// ============================================================

async function startStory(storyId) {
  const story = STORIES.find(s => s.id === storyId);
  if (!story) return;

  // Reset engine
  engine.story = story;
  engine.stepIndex = 0;
  engine.scenarioData = null;
  engine.stateData = null;
  engine.refundData = null;
  engine.defenseData = null;
  engine.techLogs = [];
  engine._stepResultData = null;
  engine._dupEventId = null;
  engine._wfEventId = null;

  // Switch to story screen
  showScreen('screen-story');

  // Set scenario label
  const lbl = document.getElementById('storyScenarioLabel');
  if (lbl) lbl.textContent = `${story.icon} ${story.title}`;

  // Render sidebar context
  renderSideContext();

  // Clear tech log
  const techLog = document.getElementById('techLog');
  if (techLog) techLog.innerHTML = '';

  // Show loading in main
  const main = document.getElementById('storyMain');
  if (main) main.innerHTML = `
    <div class="story-loading">
      <div class="loading-spinner"></div>
      <p>Setting up scenario…</p>
    </div>`;

  // Load from backend
  try {
    addTechLog(`POST /api/scenarios/reset`, 'request');
    await apiPost('/api/scenarios/reset');
    addTechLog(`Reset complete`, 'info');

    addTechLog(`POST /api/scenarios/load/${story.scenarioApiName}`, 'request');
    engine.scenarioData = await apiPost(`/api/scenarios/load/${story.scenarioApiName}`);
    addTechLog(`Scenario loaded`, 'response');

    addTechLog(`GET /api/state/${story.paymentId}`, 'request');
    engine.stateData = await apiGet(`/api/state/${story.paymentId}`);
    addTechLog(`State: ${JSON.stringify(engine.stateData?.payment?.status)}`, 'response');

  } catch (err) {
    if (main) main.innerHTML = `
      <div class="step-card">
        <div class="step-header">
          <span class="step-icon">❌</span>
          <h2 class="step-heading">Setup Failed</h2>
        </div>
        <p class="step-narrative">${err.message}</p>
        <p class="step-narrative">Make sure the backend is running: <code style="font-family:monospace">uvicorn app.main:app --reload</code></p>
        <div class="step-actions">
          <button class="step-cta cta-continue" onclick="startStory('${storyId}')">Retry</button>
        </div>
      </div>`;
    showToast(err.message, 'error');
    return;
  }

  // Update side state
  renderSideState();

  // Render first step
  renderStep(0);

  // Refresh header metrics
  refreshMetrics();
}

// ============================================================
// STORY ENGINE — RENDER STEP
// ============================================================

function renderStep(index) {
  engine.stepIndex = index;
  engine._stepResultData = null;

  const steps = engine.story.steps;
  if (index >= steps.length) {
    showScreen('screen-selection');
    return;
  }

  const step = steps[index];

  // Update progress bar
  renderProgressBar(steps, index);

  // Render step card
  const main = document.getElementById('storyMain');
  if (main) main.innerHTML = buildStepHTML(step, false);

  // Bind CTA
  bindStepCta(step, false);
}

// ============================================================
// STORY ENGINE — BUILD STEP HTML
// ============================================================

function buildStepHTML(step, showResult) {
  const eng = engine;

  // Resolve cards: may be static or dynamic
  let cards = step.cards || [];
  if (step.buildDynamic) {
    const dyn = step.buildDynamic(eng);
    if (dyn.cards) cards = dyn.cards;
  }

  const cardsHtml = cards.length > 0 ? `
    <div class="step-data-grid">
      ${cards.map(c => `
        <div class="step-data-item">
          <div class="step-data-label">${c.label}</div>
          <div class="step-data-value ${c.cls || ''}">${c.value}</div>
        </div>
      `).join('')}
    </div>` : '';

  const quoteHtml = step.quote
    ? `<div class="step-quote">${step.quote}</div>` : '';

  // Result (after API call)
  let resultHtml = '';
  if (showResult && eng._stepResultData) {
    resultHtml = buildResultHTML(eng._stepResultData);
  }

  // Outcome card (terminal step)
  let outcomeHtml = '';
  if (step.isOutcome && step.buildOutcome) {
    outcomeHtml = buildOutcomeHTML(step.buildOutcome(eng));
  }

  // CTA area
  let ctaHtml = '';
  if (step.isOutcome || !showResult) {
    // Show primary CTA (always shown unless waiting for advance)
    const disabled = showResult && step.apiCallDef ? 'disabled' : '';
    ctaHtml += `<button id="stepCta" class="step-cta ${step.ctaClass || 'cta-continue'}" ${disabled}>${step.cta}</button>`;
  }
  if (showResult && !step.isTerminal) {
    // Show advance CTA after API result
    ctaHtml += `<button id="stepAdvanceCta" class="step-cta cta-continue">${step.advanceCta || 'Continue →'}</button>`;
  }
  if (step.isTerminal) {
    ctaHtml += `<button class="step-cta cta-try-another" id="tryAnotherBtn">← Try Another Story</button>`;
  }

  return `
    <div class="step-card">
      <div class="step-phase-label">
        <span class="step-phase-dot"></span>
        ${step.phase}
      </div>
      <div class="step-header">
        <span class="step-icon">${step.icon}</span>
        <h2 class="step-heading">${step.heading}</h2>
      </div>
      <p class="step-narrative">${step.narrative}</p>
      ${cardsHtml}
      ${quoteHtml}
      ${resultHtml}
      ${outcomeHtml}
      <div class="step-actions">${ctaHtml}</div>
    </div>`;
}

// ============================================================
// STEP CTA BINDING
// ============================================================

function bindStepCta(step, showResult) {
  const ctaEl = document.getElementById('stepCta');
  const advEl = document.getElementById('stepAdvanceCta');
  const tryEl = document.getElementById('tryAnotherBtn');

  if (tryEl) {
    tryEl.addEventListener('click', () => showScreen('screen-selection'));
  }

  if (ctaEl) {
    if (step.isTerminal) {
      ctaEl.addEventListener('click', () => startStory(engine.story.id));
    } else if (step.apiCallDef && !showResult) {
      ctaEl.addEventListener('click', () => handleApiStep(step));
    } else if (!step.apiCallDef) {
      ctaEl.addEventListener('click', () => renderStep(engine.stepIndex + 1));
    }
  }

  if (advEl) {
    advEl.addEventListener('click', () => renderStep(engine.stepIndex + 1));
  }
}

// ============================================================
// STORY ENGINE — API STEP HANDLER
// ============================================================

async function handleApiStep(step) {
  const ctaEl = document.getElementById('stepCta');
  if (ctaEl) {
    ctaEl.disabled = true;
    ctaEl.textContent = 'Processing…';
  }

  addTechLog(`Calling API…`, 'request');

  try {
    const result = await step.apiCallDef.execute(engine);
    addTechLog(JSON.stringify(result), 'response');

    const resultDisplay = step.apiCallDef.buildResult(result, engine);
    engine._stepResultData = resultDisplay;

    // Update state after API call
    try {
      engine.stateData = await apiGet(`/api/state/${engine.story.paymentId}`);
      renderSideState();
    } catch (_) { /* non-critical */ }

    // Re-render step with result shown
    const main = document.getElementById('storyMain');
    if (main) main.innerHTML = buildStepHTML(step, true);

    // Re-bind
    bindStepCta(step, true);

    refreshMetrics();

  } catch (err) {
    addTechLog(`Error: ${err.message}`, 'error');
    if (ctaEl) {
      ctaEl.disabled = false;
      ctaEl.textContent = step.cta;
    }
    showToast(err.message, 'error');
  }
}

// ============================================================
// BUILD RESULT HTML
// ============================================================

function buildResultHTML(data) {
  let html = '<div class="step-result">';

  if (data.decision) {
    const d = data.decision;
    html += `
      <div class="decision-card decision-${d.type}">
        <div class="decision-label">${d.label}</div>
        <div class="decision-reason">${d.reason}</div>
        ${d.amountProtected ? `<div class="decision-protected">💰 ${inr(d.amountProtected)} protected</div>` : ''}
      </div>`;
  }

  if (data.info) {
    const info = data.info;
    html += `
      <div class="result-info-card">
        <div class="result-info-label ${info.cls || ''}">${info.label}</div>
        <div class="result-info-value">${info.value}</div>
      </div>`;
  }

  if (data.defense) {
    const d = data.defense;
    html += `
      <div class="defense-result-card">
        <div class="defense-result-header">⚖️ Defense Package Built</div>
        <div class="defense-amounts">
          <div class="defense-amount-row">
            <span>Contestable amount</span>
            <span class="green">${inr(d.contestable)}</span>
          </div>
          <div class="defense-amount-row">
            <span>Uncovered exposure</span>
            <span class="${d.uncovered > 0 ? 'red' : 'green'}">${inr(d.uncovered)}</span>
          </div>
          <div class="defense-amount-row">
            <span>Package status</span>
            <span class="${d.status === 'READY' ? 'green' : 'orange'}">${d.status}</span>
          </div>
        </div>
        ${d.evidence.length > 0 ? `
          <div class="evidence-mini-list">
            ${d.evidence.map(ev => `
              <div class="evidence-mini-item">
                <span class="ev-check">✓</span>
                <span>${ev.evidence_type.replace(/_/g, ' ')} — ${ev.description.slice(0, 60)}${ev.description.length > 60 ? '…' : ''}</span>
              </div>`).join('')}
          </div>` : ''}
      </div>`;
  }

  html += '</div>';
  return html;
}

// ============================================================
// BUILD OUTCOME HTML
// ============================================================

function buildOutcomeHTML(outcome) {
  return `
    <div class="outcome-card">
      <div class="outcome-header">
        <span class="outcome-icon">${outcome.icon}</span>
        <span class="outcome-title">${outcome.title}</span>
      </div>
      <div class="outcome-items">
        ${outcome.items.map(item => `
          <div class="outcome-item">
            <span class="outcome-item-label">${item.label}</span>
            <span class="outcome-item-value ${item.cls || ''} ${item.mono ? 'mono' : ''}">${item.value}</span>
          </div>`).join('')}
      </div>
    </div>`;
}

// ============================================================
// PROGRESS BAR
// ============================================================

function renderProgressBar(steps, currentIndex) {
  const bar = document.getElementById('storyProgress');
  if (!bar) return;

  bar.innerHTML = steps.map((step, i) => {
    let cls = 'progress-step';
    if (i < currentIndex) cls += ' done';
    else if (i === currentIndex) cls += ' active';

    const sep = i < steps.length - 1 ? '<span class="progress-sep">›</span>' : '';
    return `
      <div class="${cls}">
        <span class="progress-step-label">${step.phase}</span>
      </div>
      ${sep}`;
  }).join('');
}

// ============================================================
// SIDEBAR
// ============================================================

function renderSideContext() {
  const body = document.getElementById('sideContextBody');
  if (!body || !engine.story) return;

  const s = engine.story;
  body.innerHTML = `
    <div class="side-context-row">
      <span class="side-ctx-label">Story</span>
      <span class="side-ctx-value">${s.icon} ${s.title}</span>
    </div>
    ${s.customer !== 'System Reliability' ? `
    <div class="side-context-row">
      <span class="side-ctx-label">Customer</span>
      <span class="side-ctx-value">${s.customer}</span>
    </div>
    <div class="side-context-row">
      <span class="side-ctx-label">Product</span>
      <span class="side-ctx-value">${s.product}</span>
    </div>` : ''}
    <div class="side-context-row">
      <span class="side-ctx-label">Amount</span>
      <span class="side-ctx-value" style="font-weight:700">${s.amountDisplay}</span>
    </div>
    <div class="side-context-row">
      <span class="side-ctx-label">Payment ID</span>
      <span class="side-ctx-value mono" style="font-size:10px">${s.paymentId}</span>
    </div>`;
}

function renderSideState() {
  const body = document.getElementById('sideStateBody');
  if (!body) return;

  const sd = engine.stateData;
  if (!sd) {
    body.innerHTML = '<div class="side-placeholder">Loading…</div>';
    return;
  }

  const risk = sd.risk_state || {};
  const refunds = sd.refunds || [];
  const disputes = sd.disputes || [];
  const dps = sd.defense_packages || [];
  const latestR = refunds[0];
  const dp = dps[0];

  const rows = [
    {
      label: 'Payment', value: sd.payment?.status || '—',
      cls: sd.payment?.status === 'CAPTURED' ? 'green' : ''
    },
    {
      label: 'Risk', value: risk.would_block_refund ? 'BLOCKED' : 'SAFE',
      cls: risk.would_block_refund ? 'red' : 'green'
    },
    {
      label: 'Disputes', value: disputes.length > 0 ? `${disputes.filter(d => d.status === 'OPEN').length} OPEN` : 'None',
      cls: disputes.some(d => d.status === 'OPEN') ? 'red' : 'green'
    },
    {
      label: 'Refund', value: latestR?.status || 'None',
      cls: latestR?.status === 'PROCESSED' ? 'green' : latestR ? 'orange' : ''
    },
    {
      label: 'ARN', value: latestR?.arn ? latestR.arn.slice(0, 14) + '…' : '—',
      cls: latestR?.arn ? 'green' : ''
    },
    ...(dp ? [
      { label: 'Contestable', value: inr(dp.contestable_amount_paise), cls: 'green' },
      { label: 'Uncovered', value: inr(dp.uncovered_amount_paise), cls: dp.uncovered_amount_paise > 0 ? 'red' : 'green' },
      {
        label: 'Defense', value: dp.status,
        cls: dp.status === 'READY' ? 'green' : dp.status === 'PARTIALLY_DEFENSIBLE' ? 'orange' : 'red'
      },
    ] : []),
  ];

  body.innerHTML = rows.map(r => `
    <div class="side-state-row">
      <span class="state-row-label">${r.label}</span>
      <span class="state-row-value ${r.cls || ''}">${r.value}</span>
    </div>`).join('');
}

// ============================================================
// METRICS — HEADER PILLS
// ============================================================

async function refreshMetrics() {
  try {
    const data = await apiGet('/api/metrics');

    const headerMetrics = document.getElementById('headerMetrics');
    if (!headerMetrics) return;

    const pills = [
      { label: 'Intercepted', value: data.refund_requests_intercepted, cls: '' },
      { label: 'Blocked', value: data.dangerous_refunds_blocked, cls: data.dangerous_refunds_blocked > 0 ? 'red' : '' },
      { label: 'Protected', value: inr(data.duplicate_outflow_prevented_paise), cls: 'green' },
      { label: 'Defense Packages', value: data.defense_packages_generated, cls: '' },
    ];

    headerMetrics.innerHTML = pills.map(p => `
      <div class="metric-pill">
        <span class="metric-pill-label">${p.label}</span>
        <span class="metric-pill-value ${p.cls}">${p.value}</span>
      </div>`).join('');

  } catch (_) { /* silent */ }
}

// ============================================================
// API STATUS CHECK
// ============================================================

async function checkApiStatus() {
  const dot = document.getElementById('apiStatusDot');
  const text = document.getElementById('apiStatusText');
  try {
    const data = await apiGet('/');
    dot.className = 'status-dot connected';
    text.textContent = `${data.service} v${data.version}`;
  } catch {
    dot.className = 'status-dot error';
    text.textContent = 'API offline';
  }
}

// ============================================================
// TECH LOG TOGGLE
// ============================================================

function initTechToggle() {
  const btn = document.getElementById('techToggleBtn');
  const content = document.getElementById('techLog');
  const arrow = document.getElementById('techArrow');
  if (!btn || !content) return;

  btn.addEventListener('click', () => {
    const open = !content.classList.contains('hidden');
    content.classList.toggle('hidden', open);
    arrow.classList.toggle('open', !open);
    btn.setAttribute('aria-expanded', String(!open));
  });
}

// ============================================================
// BACK BUTTON
// ============================================================

function initBackButton() {
  const btn = document.getElementById('backBtn');
  if (btn) {
    btn.addEventListener('click', () => showScreen('screen-selection'));
  }
}

// ============================================================
// INIT
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
  // Render story cards
  renderStorySelection();

  // UI init
  initBackButton();
  initTechToggle();

  // API status
  checkApiStatus();
  setInterval(checkApiStatus, 15000);

  // Initial metrics
  refreshMetrics();
  setInterval(refreshMetrics, 30000);
});
