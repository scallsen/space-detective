// app.js — Airlock Sabotage game logic

let state = {
  oxygen: 100,
  questionsRemaining: 10,
  gameOver: false,
  saboteur: 'security_guard',
  activeSuspect: null
};

const chatLog             = document.getElementById('chat-log');
const dialogText          = document.getElementById('dialog-text');
const chatInput           = document.getElementById('chat-input');
const oxygenBar           = document.getElementById('oxygen-bar');
const oxygenPct           = document.getElementById('oxygen-pct');
const interrogationCounter= document.getElementById('interrogation-counter');
const endOverlay          = document.getElementById('end-overlay');
const endTitle            = document.getElementById('end-title');
const endDesc             = document.getElementById('end-desc');
const dialogNameTab       = document.getElementById('dialog-name-tab');
const questionText        = document.getElementById('question-text');
const mainSprite          = document.getElementById('main-sprite');

// ── Intro Overlay ──────────────────────────────────────────────
(function initIntro() {
  const overlay    = document.getElementById('intro-overlay');
  const textEl     = document.getElementById('intro-text');
  const pressKeyEl = document.getElementById('intro-press-key');

  const INTRO = `The year is 2142. You are aboard a deepmind-space research station orbiting Saturn's moon, Titan. The station's primary mission is to test experimental atmospheric synthesis prototypes designed to make Mars habitable for future human colonies.

At exactly 04:16, the station's automated warnings went off: a critical breach alert from Sector 7 (Oxygen Life Support). The main oxygen feed line was physically severed, venting the station's air reserves directly into space. Because of the automatic lockdowns, the suspect list is restricted to the four crew members who were awake and patrolling near the affected sectors.

As the station captain, you immediately isolated the sector and gathered the four suspects in the Sub-Space Interrogation Channel. The situation is dire: oxygen reserves are dropping rapidly, giving you time for a few questions. If you successfully deduce the culprit, you can trigger the airlock vent to eject the saboteur, repair the main feed with the innocent crew, and secure the station.

However, the backup life support system is critically damaged. The only guaranteed path to survival is to identify the saboteur, lock them on the failing station, and escape via the emergency evacuation pod with the other three innocent crew members. Ejecting the wrong crew member will doom the remaining survivors to suffocation as the actual culprit disables the escape pods.`;

  let idx = 0;
  let twId = null;
  let done = false;

  function finish() {
    if (twId) { clearTimeout(twId); twId = null; }
    textEl.textContent = INTRO;
    done = true;
    pressKeyEl.classList.add('visible');
  }

  function tick() {
    if (idx >= INTRO.length) { finish(); return; }
    textEl.textContent += INTRO[idx++];
    twId = setTimeout(tick, 18);
  }

  function handleInput() {
    if (!done) { finish(); return; }
    overlay.classList.add('hidden');
    document.removeEventListener('keydown', handleInput);
    overlay.removeEventListener('click', handleInput);
    chatInput.focus();
  }

  setTimeout(tick, 400);
  document.addEventListener('keydown', handleInput);
  overlay.addEventListener('click', handleInput);
})();

// ── Typewriter ─────────────────────────────────────────────────
let twTimer = null;
let twFull  = '';

function typewrite(text, isSystem) {
  clearTimeout(twTimer);
  twFull = text;
  dialogText.className = isSystem ? 'system' : '';
  dialogText.textContent = '';
  let i = 0;
  function tick() {
    if (i >= text.length) { twTimer = null; return; }
    dialogText.textContent += text[i++];
    twTimer = setTimeout(tick, 22);
  }
  tick();
}

function skipTypewriter() {
  if (twTimer !== null) {
    clearTimeout(twTimer);
    twTimer = null;
    dialogText.textContent = twFull;
  }
}

function showText(text, isSystem, instant) {
  if (instant) {
    clearTimeout(twTimer);
    twTimer = null;
    twFull = text;
    dialogText.className = isSystem ? 'system' : '';
    dialogText.textContent = text;
  } else {
    typewrite(text, isSystem);
  }
}

// Click dialog log to skip typewriter
chatLog.addEventListener('click', skipTypewriter);

// Per-role conversation history
const histories = {
  chief_engineer: [],
  technician: [],
  botanist: [],
  security_guard: []
};

// Unread tracking: which role agents have new responses not yet viewed
const unread = {
  chief_engineer: false,
  technician: false,
  botanist: false,
  security_guard: false
};

const suspects = {
  chief_engineer: {
    name: "Chief Engineer",
    colorClass: "cyan",
    sprite: "images/fullsprite_chiefengineer.png",
    responses: {
      alibi: "I was in Sector 2 troubleshooting a reactor issue. The Technician saw me there briefly at 04:05.",
      security_guard: "The Security Guard is supposed to be patrolling. I do not know where that role was during the leak.",
      botanist: "The Botanist is usually in the Greenhouse. That role stays out of engineering business.",
      default: "I was in Sector 2 trying to keep the reactor stable. What exactly are you implying?"
    }
  },
  technician: {
    name: "Technician",
    colorClass: "amber",
    sprite: "images/fullsprite_techinician.png",
    responses: {
      alibi: "I was doing routine maintenance in Sector 2, then went to the Lounge in Sector 5 for coffee.",
      security_guard: "I did not see the Security Guard in the Reactor Room or the Lounge.",
      botanist: "The Botanist mostly stays near the plants. I did not have a reason to track that role.",
      default: "I was doing maintenance. Dirty work, bad timing, not sabotage."
    }
  },
  botanist: {
    name: "Botanist",
    colorClass: "green",
    sprite: "images/placeholder.png",
    responses: {
      alibi: "I was in the Greenhouse checking hydroponic nutrient levels. I was working alone.",
      security_guard: "The Security Guard? No, I did not see that role in the Greenhouse.",
      botanist: "Yes, I was checking the hydroponic systems. They require constant calibration.",
      default: "I was alone in the Greenhouse. I did not see anyone else until the sirens went off."
    }
  },
  security_guard: {
    name: "Security Guard",
    colorClass: "red",
    sprite: "images/fullsprite_securityguard.png",
    responses: {
      alibi: "I was in Sector 4 helping the Botanist move heavy equipment crates. Standard security assistance.",
      security_guard: "I was doing my duty: patrols, checks, and emergency response.",
      botanist: "The Botanist was in the Greenhouse. I was helping with equipment when the line blew.",
      default: "I was on duty. Nothing unusual on my end until the decompression alarm sounded."
    }
  }
};

// ── Switch active suspect ───────────────────────────────────────
function selectSuspect(key) {
  state.activeSuspect = key;
  const suspect = suspects[key];

  // Update sidebar highlights
  document.querySelectorAll('.chibi-entry').forEach(el => {
    el.classList.toggle('active', el.dataset.suspect === key);
  });

  // Update name tab
  dialogNameTab.textContent = suspect.name.toUpperCase();

  // Update main sprite (try real sprite, fall back to placeholder)
  const img = new Image();
  img.onload = () => { mainSprite.src = suspect.sprite; };
  img.onerror = () => { mainSprite.src = 'images/placeholder.png'; };
  img.src = suspect.sprite;

  // Clear unread dot
  unread[key] = false;
  const dot = document.getElementById(`dot-${key}`);
  if (dot) dot.classList.remove('visible');

  // Render this suspect's history
  renderLog(key);
}

function renderLog(key) {
  const hist = histories[key];
  if (hist.length === 0) {
    showText('[ NO TRANSMISSIONS YET — ASK A QUESTION TO BEGIN. ]', true, true);
  } else {
    showText(hist[hist.length - 1].text, false, true);
  }
}

// ── Question submit ─────────────────────────────────────────────
function handleQuestionSubmit(event) {
  event.preventDefault();
  if (state.gameOver) return;

  const query = chatInput.value.trim();
  if (!query) return;

  chatInput.value = '';

  // Show question in the bar above the dialog box
  questionText.textContent = `"${query}"`;

  state.oxygen -= 10;
  state.questionsRemaining -= 1;
  updateStatusUI();

  setTimeout(() => generateReplies(query), 600);
}

// ── Generate suspect replies ────────────────────────────────────
async function generateReplies(question) {
  let data = null;
  try {
    const response = await fetch('http://localhost:8080/api/interrogate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question })
    });
    if (response.ok) data = await response.json();
  } catch (_) { /* fall back to local */ }

  const keys = Object.keys(suspects);

  const getResponse = (key) => {
    if (data) return data[key] || 'No comment.';
    const q = question.toLowerCase();
    let cat = 'default';
    if (q.includes('where') || q.includes('alibi') || q.includes('time') ||
        q.includes('happen') || q.includes('incident') || q.includes('doing') ||
        q.includes('04:15')) cat = 'alibi';
    else if (q.includes('security') || q.includes('guard')) cat = 'security_guard';
    else if (q.includes('botanist') ||
             q.includes('greenhouse') || q.includes('plants')) cat = 'botanist';
    return suspects[key].responses[cat] || suspects[key].responses.default;
  };

  keys.forEach((key, i) => {
    setTimeout(() => {
      const text = getResponse(key);
      const suspect = suspects[key];

      // Store in history
      histories[key].push({
        sender: suspect.name,
        text,
        type: 'suspect',
        colorClass: suspect.colorClass
      });

      // Typewriter in if this is the active suspect; otherwise mark unread
      if (state.activeSuspect === key) {
        showText(text, false, false);
      } else {
        unread[key] = true;
        const dot = document.getElementById(`dot-${key}`);
        if (dot) dot.classList.add('visible');
      }
    }, i * 350);
  });

  // Check loss condition
  setTimeout(() => {
    if (state.questionsRemaining <= 0 && !state.gameOver) {
      triggerEndGame(false, 'OXYGEN DEPLETED',
        'You ran out of interrogation opportunities. The station\'s life support failed completely, and the saboteur escaped in the chaos.');
    }
  }, keys.length * 350 + 200);
}

// ── Status UI ──────────────────────────────────────────────────
function updateStatusUI() {
  oxygenBar.style.width = `${state.oxygen}%`;
  oxygenPct.textContent = `${state.oxygen}%`;
  interrogationCounter.textContent = `${state.questionsRemaining} / 10`;
  oxygenBar.classList.toggle('danger', state.oxygen <= 30);
}

// ── Vent ───────────────────────────────────────────────────────
function ventSuspect(suspectKey) {
  if (state.gameOver) return;
  document.getElementById(`chibi-${suspectKey}`).classList.add('vented');

  if (suspectKey === state.saboteur) {
    triggerEndGame(true, 'SABOTEUR NEUTRALIZED',
      'Excellent work, Commander. You successfully identified the Security Guard as the saboteur. The role was ejected through the airlock, and the remaining crew has repaired the oxygen feed. The station is secure.');
  } else {
    const victim = suspects[suspectKey].name;
    triggerEndGame(false, 'MISSION FAILED',
      `Fatal error. You vented the ${victim}, who was innocent. With life support failing and key personnel lost, the actual saboteur successfully disabled the remaining backup systems. The station went dark.`);
  }
}

// ── End game ───────────────────────────────────────────────────
function triggerEndGame(isVictory, title, description) {
  state.gameOver = true;
  endOverlay.classList.remove('hidden');
  endTitle.textContent = title;
  endTitle.className = `vn-modal-title ${isVictory ? 'victory-title' : 'defeat-title'}`;
  endDesc.textContent = description;
}

// ── Reset ──────────────────────────────────────────────────────
function resetGame() {
  state.oxygen = 100;
  state.questionsRemaining = 10;
  state.gameOver = false;
  state.activeSuspect = null;

  Object.keys(histories).forEach(k => { histories[k] = []; });
  Object.keys(unread).forEach(k => { unread[k] = false; });

  document.querySelectorAll('.chibi-entry').forEach(el => {
    el.classList.remove('vented', 'active');
  });
  document.querySelectorAll('.unread-dot').forEach(el => el.classList.remove('visible'));

  dialogNameTab.textContent = '— SELECT A SUSPECT —';
  questionText.textContent = '—';
  mainSprite.src = 'images/placeholder.png';
  showText('[ OXYGEN LINE SEVERED — SECTOR 7 — 04:15 ]\n[ SELECT A CREW MEMBER AND BEGIN INTERROGATION. ]', true, true);

  updateStatusUI();
  endOverlay.classList.add('hidden');
}

// Start with Chief Engineer selected by default
selectSuspect('chief_engineer');
