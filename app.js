// app.js — Airlock Sabotage game logic

let state = {
  oxygen: 100,
  questionsRemaining: 10,
  gameOver: false,
  saboteur: 'jax',
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

// Per-suspect conversation history
const histories = { elena: [], marcus: [], chen: [], jax: [] };

// Unread tracking — which suspects have new responses not yet viewed
const unread = { elena: false, marcus: false, chen: false, jax: false };

const suspects = {
  elena: {
    name: "Elena Rostova",
    colorClass: "cyan",
    sprite: "sprites/elena.png",
    responses: {
      alibi: "I was in Sector 2 (Reactor Core) troubleshooting a minor power surge from 04:00 to 04:30. You can check the logs — Marcus saw me there briefly at 04:05.",
      jax: "Jax? He's security. He is supposed to be patrolling, but I rarely see him doing actual work. I don't know where he was during the leak.",
      chen: "Dr. Chen is usually in the Greenhouse. She stays out of engineering business, which I appreciate.",
      default: "Look, I've been working double shifts. I was in Sector 2 trying to prevent a reactor melt. What exactly are you implying?"
    }
  },
  marcus: {
    name: "Marcus Vance",
    colorClass: "amber",
    sprite: "sprites/marcus.png",
    responses: {
      alibi: "I was doing routine maintenance in Sector 2. Passed Elena around 04:05. Then I headed to the Lounge in Sector 5 to grab a coffee at 04:10 and stayed there alone until the alarm rang.",
      jax: "Jax? Didn't see him in the Reactor Room, and he definitely wasn't in the lounge when I was drinking coffee.",
      chen: "Dr. Chen is cool. A bit obsessive about her plants, but she doesn't bother anyone.",
      default: "I was just trying to get some caffeine in my system. Ask the station computer if you don't believe my alibi."
    }
  },
  chen: {
    name: "Dr. Mei-Ling Chen",
    colorClass: "green",
    sprite: "sprites/chen.png",
    responses: {
      alibi: "I was in the Greenhouse (Sector 4) checking hydroponic nutrient levels from 04:00 onwards. I was working alone.",
      jax: "Jax? No, I haven't seen Jax since yesterday afternoon. Why do you ask? Was he supposed to be in the Greenhouse?",
      chen: "Yes, I was checking the hydroponic systems. They require constant calibration.",
      default: "I was alone in the greenhouse. The plants require quiet concentration. I did not see or hear anyone else until the sirens went off."
    }
  },
  jax: {
    name: "Jax Thorne",
    colorClass: "red",
    sprite: "sprites/jax.png",
    responses: {
      alibi: "I was in Sector 4 (Greenhouse) helping Dr. Chen move some heavy soil and equipment crates from 04:10 to 04:20. Standard security assistance.",
      jax: "I was doing my duty. Standard patrol, followed by assisting the science staff in the greenhouse.",
      chen: "Yeah, Dr. Chen was in the Greenhouse. I was helping her with the equipment crates at 04:15 when the line blew.",
      default: "I was on duty. Security sweeps. Nothing unusual on my end until the decompression alarm sounded."
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
    else if (q.includes('jax') || q.includes('security') || q.includes('guard')) cat = 'jax';
    else if (q.includes('chen') || q.includes('botanist') ||
             q.includes('greenhouse') || q.includes('plants')) cat = 'chen';
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
      'Excellent work, Commander. You successfully identified Jax Thorne as the saboteur. He was ejected through the airlock, and the remaining crew has repaired the oxygen feed. The station is secure.');
  } else {
    const victim = suspects[suspectKey].name;
    triggerEndGame(false, 'MISSION FAILED',
      `Fatal error. You vented ${victim}, who was innocent. With life support failing and key personnel lost, the actual saboteur (Jax Thorne) successfully disabled the remaining backup systems. The station went dark.`);
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

// Start with Elena selected by default
selectSuspect('elena');
