// docs/app.js — Front-End CMP Virtual Metrology & Alarm Bifurcation Simulator
const S = window.SCENARIOS;
const $ = s => document.querySelector(s);

const cssv = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

let COL = {}, C = {};
function loadColors() {
  COL = {
    CRIT: cssv('--bad') || '#ff453a',
    MAJ: cssv('--warn') || '#ff9f0a',
    MIN: cssv('--min') || '#ffd60a',
    INFO: cssv('--ok') || '#30d158'
  };
  C = {
    ink: cssv('--ink') || '#ffffff',
    mut: cssv('--ink-40') || 'rgba(255,255,255,0.4)',
    bad: cssv('--bad') || '#ff453a',
    warn: cssv('--warn') || '#ff9f0a',
    min: cssv('--min') || '#ffd60a',
    accent: cssv('--accent') || '#0a84ff',
    ok: cssv('--ok') || '#30d158'
  };
}
loadColors();

const SPEED = { 1: 1800, 5: 350, 20: 90, 50: 35 };
const STEP_MIN = 6;

let day = 0, eqp = 0, logv = 'all';
let cur = 99, playing = false, speed = 20, timer = null;
let queue = [], saved = null;
let live = {}, dIdx = {}, halt = {}, alarmAt = {}, replaced = {}, replaceIdx = {};
let decided = {};
const key = c => c.alarm_id + (c.esc ? '#esc' : '');

const N = () => S[day].equipments[0].series.t.length;
const nowT = () => S[day].equipments[0].series.t[Math.max(cur, 0)];

// ── 실시간 시계열 & 단독 챔버 정지 로직 ───────────────────────
function resetLive() {
  live = {}; dIdx = {}; halt = {}; alarmAt = {}; replaced = {}; replaceIdx = {};
  S[day].equipments.forEach(e => {
    live[e.id] = {
      mrr_act: [], mrr_pred: [], press: [], flow: [], rpm: [],
      temp: [], curr: [], wear: [], rul: [], halt: []
    };
    dIdx[e.id] = -1;
    halt[e.id] = false;
    replaced[e.id] = false;
    replaceIdx[e.id] = 0;
  });
}

function stepLive(k) {
  S[day].equipments.forEach(e => {
    const L = live[e.id], s = e.series, n = L.mrr_act.length;
    if (halt[e.id]) {
      // 챔버 단독 정지: 모터 RPM 및 압력 0, 마모 누적 정지
      const prev_temp = n ? L.temp[n - 1] : 34.0;
      L.mrr_act.push(0);
      L.mrr_pred.push(0);
      L.press.push(0);
      L.flow.push(0);
      L.rpm.push(0);
      L.curr.push(0);
      L.temp.push(+(prev_temp - 0.3).toFixed(1));
      L.wear.push(n ? L.wear[n - 1] : 400.0);
      L.rul.push(n ? L.rul[n - 1] : 0);
      L.halt.push(1);
    } else {
      // 챔버 정상 가동
      const i = Math.min(++dIdx[e.id], s.t.length - 1);
      L.press.push(s.press[i]);
      L.flow.push(s.flow[i]);
      L.rpm.push(s.rpm[i]);
      L.temp.push(s.temp[i]);
      L.curr.push(s.curr[i]);

      if (replaced[e.id]) {
        // 패드 교체 후: 신품 1200um 기준 재누적
        const past = i - replaceIdx[e.id];
        const new_wear = Math.max(1200.0 - past * 1.6, 400.0);
        L.wear.push(+new_wear.toFixed(1));
        L.rul.push(Math.max(0, Math.round((new_wear - 400.0) / 1.65)));
        L.mrr_act.push(+(2200.0 + (Math.random() - 0.5) * 20.0).toFixed(1));
        L.mrr_pred.push(+(2200.0 + (Math.random() - 0.5) * 18.0).toFixed(1));
      } else {
        L.wear.push(s.wear[i]);
        L.rul.push(s.rul[i]);
        L.mrr_act.push(s.mrr_act[i]);
        L.mrr_pred.push(s.mrr_pred[i]);
      }
      L.halt.push(0);
    }
  });

  S[day].alarms.forEach(a => {
    if (alarmAt[a.id] !== undefined || dIdx[a.eqp] < a.step) return;
    alarmAt[a.id] = k;
  });
}

function fillAll() {
  resetLive();
  for (let k = 0; k < N(); k++) stepLive(k);
}

const haltSteps = () => S[day].equipments.reduce((tot, e) => tot + (live[e.id] ? live[e.id].halt.reduce((x, y) => x + y, 0) : 0), 0);

// ── SVG 차트 (Y축 스케일 최적화 & 일자 뭉개짐 해결) ─────────────
const W = 760, H = 88, PL = 46, PR = 10, PT = 8, PB = 15;

function chart({ label, unit, series, limits = [], marks = [], fills = [], base, minSpread, clampFloor }) {
  const n = series[0].t.length, c = cur;
  
  // 정지(0)를 제외한 유효 가동 값으로 Y축 범위 계산 -> 1자 뭉개짐 원천 방지
  const nonZero = series.flatMap(s => s.v.filter(v => v > 0));
  const ref = base || (nonZero.length ? nonZero : [100]);
  let lo = Math.min(...ref), hi = Math.max(...ref);

  const spread = hi - lo;
  const targetMinSpread = minSpread || (hi * 0.12) || 20;
  if (spread < targetMinSpread) {
    const mid = (hi + lo) / 2;
    lo = mid - targetMinSpread / 2;
    hi = mid + targetMinSpread / 2;
  }

  const shown = limits.filter(l => l.v >= lo - (hi - lo) * 0.5 && l.v <= hi + (hi - lo) * 0.5);
  shown.forEach(l => { lo = Math.min(lo, l.v); hi = Math.max(hi, l.v); });

  const pad = (hi - lo) * 0.12 || 1;
  lo -= pad; hi += pad;
  if (clampFloor !== undefined && lo < clampFloor) lo = clampFloor;

  const X = i => PL + i * (W - PL - PR) / (n - 1);
  const Y = v => {
    if (v <= 0) return H - PB; // 0(정지)은 차트 최하단에 안착
    const clamped = Math.min(Math.max(v, lo), hi);
    return PT + (hi - clamped) * (H - PT - PB) / (hi - lo);
  };

  const line = vs => vs.slice(0, c + 1).map((v, i) => (i ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1)).join(' ');
  let g = '';

  // 정지 구간 붉은 배경 음영
  fills.filter(f => f[0] <= c).forEach(f => {
    const x0 = X(f[0]), x1 = X(Math.min(f[1], c));
    g += `<rect x="${x0}" y="${PT}" width="${Math.max(x1 - x0, 1.5)}" height="${H - PT - PB}" fill="${f[2]}" opacity=".22"/>`;
  });
  // 알람 발생선
  marks.filter(m => m[0] <= c).forEach(m => {
    const x = X(m[0]);
    g += `<line x1="${x}" y1="${PT}" x2="${x}" y2="${H - PB}" stroke="${m[1]}" stroke-width="1.2" opacity=".75"/>`;
  });
  // 판정 기준선 (글자 겹침 방지 Collision Avoidance & 다크 헤일로 스트로크)
  const limitItems = shown.map(l => ({
    ...l,
    y: Y(l.v),
    textY: Y(l.v) - 4,
    textX: W - PR
  })).sort((a, b) => a.y - b.y);

  for (let i = 1; i < limitItems.length; i++) {
    const prev = limitItems[i - 1];
    const curr = limitItems[i];
    const dy = curr.textY - prev.textY;
    if (dy < 14) {
      // 상하 간격이 14px 미만으로 겹칠 경우 지능형 분리
      if (curr.y < H - PB - 12) {
        // 하단 여유가 있으면 아래 기준선 글자를 선 밑으로 배치
        curr.textY = curr.y + 11;
        prev.textY = Math.max(PT + 8, prev.y - 4);
      } else {
        // 바닥 근처(예: 400 한계선)인 경우 좌우 오프셋으로 수평 분리
        prev.textY = Math.max(PT + 8, prev.y - 4);
        curr.textX = W - PR - 120;
        curr.textY = curr.y - 4;
      }
    }
  }

  limitItems.forEach(l => {
    g += `<line x1="${PL}" y1="${l.y}" x2="${W - PR}" y2="${l.y}" stroke="${l.c}" stroke-width="1" stroke-dasharray="3 3" opacity=".75"/>`
       + `<text x="${l.textX}" y="${l.textY}" fill="${l.c}" font-size="9.5" font-weight="600" text-anchor="end" `
       + `paint-order="stroke fill" stroke="rgba(18,18,20,0.95)" stroke-width="3.5" stroke-linejoin="round">${l.t}</text>`;
  });

  // 센서 데이터 라인
  series.forEach(s => {
    g += `<path d="${line(s.v)}" fill="none" stroke="${s.c}" stroke-width="${s.dyn ? 1 : 1.4}"${s.dyn ? ' stroke-dasharray="4 3" opacity=".8"' : ''}/>`;
  });

  // 현재 재생 커서
  if (c < n - 1) {
    const x = X(c);
    g += `<line x1="${x}" y1="${PT}" x2="${x}" y2="${H - PB}" stroke="${C.ink}" stroke-width="1" opacity=".45"/>`;
    series.filter(s => !s.dyn).forEach(s => g += `<circle cx="${x}" cy="${Y(s.v[c])}" r="2.4" fill="${s.c}"/>`);
  }
  g += `<text x="${PL - 6}" y="${Math.max(PT + 8, Y(hi) + 4)}" fill="${C.mut}" font-size="9" text-anchor="end" paint-order="stroke fill" stroke="rgba(18,18,20,0.95)" stroke-width="3">${hi.toFixed(0)}</text>`
     + `<text x="${PL - 6}" y="${Math.min(H - PB, Y(lo))}" fill="${C.mut}" font-size="9" text-anchor="end" paint-order="stroke fill" stroke="rgba(18,18,20,0.95)" stroke-width="3">${lo.toFixed(0)}</text>`;
  [0, 0.25, 0.5, 0.75, 1].forEach(f => {
    const i = Math.round(f * (n - 1));
    g += `<text x="${X(i)}" y="${H - 3}" fill="${C.mut}" font-size="9" text-anchor="${f === 0 ? 'start' : f === 1 ? 'end' : 'middle'}" paint-order="stroke fill" stroke="rgba(18,18,20,0.95)" stroke-width="3">${series[0].t[i]}</text>`;
  });

  const leg = series.filter(s => s.name).map(s => `<span style="color:${s.c}">■</span> ${s.name}`).join(' &nbsp;');
  return `<div class="ch"><div class="ch-head"><b>${label}</b><em>${leg} &nbsp;${unit}</em></div>
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="height:${H}px">${g}</svg></div>`;
}

function renderCharts() {
  const d = S[day], e = d.equipments[eqp], L = live[e.id], s = e.series;
  const my = d.alarms.filter(a => a.eqp === e.id && alarmAt[a.id] !== undefined);
  const marks = my.map(a => [alarmAt[a.id], COL[a.grade]]);
  const fills = [];
  L.halt.forEach((h, i) => { if (h) fills.push([i, i + 1, C.bad]); });

  $('#charts').innerHTML = [
    chart({
      label: '가상계측 MRR (연마 제거율)', unit: '[Å/min] · 파란선: 가상계측 예측 | 주황선: 실측값',
      series: [
        { t: s.t, v: L.mrr_act, c: C.warn, name: 'MRR 실측값' },
        { t: s.t, v: L.mrr_pred, c: C.accent, name: 'VM 예측값' }
      ],
      limits: [
        { v: 2200, c: C.ok, t: '목표 MRR 2200' },
        { v: 2100, c: C.bad, t: '하한 관리선 2100' }
      ],
      minSpread: 180, clampFloor: 2000, marks, fills
    }),
    chart({
      label: '캐리어 다운포스 압력', unit: '[psi] · 레시피 목표 3.80 psi',
      series: [{ t: s.t, v: L.press, c: C.ink }],
      limits: [
        { v: 4.10, c: C.bad, t: '4.10 상한' },
        { v: 3.50, c: C.min, t: '3.50 하한' }
      ],
      minSpread: 0.8, clampFloor: 3.2, marks, fills
    }),
    chart({
      label: '슬러리 공급 유량', unit: '[ml/min] · 목표 220.0 ml/min',
      series: [{ t: s.t, v: L.flow, c: C.ink }],
      limits: [
        { v: 236, c: C.min, t: '236 상한' },
        { v: 204, c: C.bad, t: '204 하한 (자동보정)' }
      ],
      minSpread: 50, clampFloor: 170, marks, fills
    }),
    chart({
      label: '테이블 모터 마찰 전류', unit: '[A] · 패드 마찰 특성 지표',
      series: [{ t: s.t, v: L.curr, c: C.ink }],
      limits: [{ v: 16.5, c: C.bad, t: '16.5A 마찰 한계' }],
      minSpread: 4.0, clampFloor: 12.0, marks, fills
    }),
    chart({
      label: '폴리싱 패드 잔여 홈 깊이 & RUL', unit: '[μm] · 400μm 도달 시 즉시 정지',
      series: [{ t: s.t, v: L.wear, c: C.warn }],
      limits: [
        { v: 480, c: C.min, t: '480 주의 (차기PM)' },
        { v: 400, c: C.bad, t: '400 한계 (즉시정지)' }
      ],
      base: [380, 1220], marks, fills
    })
  ].join('');
}

// ── CMP 물리 거동 트윈 애니메이션 (재생 중에만 작동!) ─────────
function renderTwin() {
  const d = S[day], e = d.equipments[eqp], L = live[e.id];
  const isHalted = halt[e.id];
  const isRunning = playing && cur < N() - 1 && !isHalted;

  const card = $('#cmp-twin-card');
  const badge = $('#twin-status-badge');
  const overlay = $('#cmp-halt-overlay');
  const chName = $('#twin-ch-name');

  if (chName) chName.textContent = `${e.id} — ${e.type}`;

  if (card) {
    // 재생 중일 때만 .is-running 클래스 부여하여 애니메이션 작동
    card.classList.toggle('is-running', isRunning);
    card.classList.toggle('is-halted', isHalted);
  }

  if (isHalted) {
    if (badge) badge.innerHTML = `<span class="badge bad">🔴 단독 정지 (HALTED)</span>`;
    if (overlay) overlay.style.opacity = '1';

    $('#g-mrr').textContent = '0 Å/min';
    $('#g-mrr').className = 'gauge-val alert';
    $('#g-mrr-err').textContent = '설비 단독 정지 상태';
    $('#g-press').textContent = '0.00 psi';
    $('#g-press').className = 'gauge-val alert';
    $('#g-flow').textContent = '0.0 ml/min';
    $('#g-flow').className = 'gauge-val alert';
    $('#g-wear').textContent = `${L.wear[cur] || 400.0} μm`;
    $('#g-wear').className = 'gauge-val alert';
    $('#g-rul').textContent = '잔여 0매 (교체 대기)';
  } else {
    if (badge) {
      badge.innerHTML = isRunning
        ? `<span class="badge ok">🟢 연마 가동 중 (RUNNING)</span>`
        : `<span class="badge ghost">⏸ 일시정지 (PAUSED)</span>`;
    }
    if (overlay) overlay.style.opacity = '0';

    const mrrP = L.mrr_pred[cur] || 2200.0;
    const mrrA = L.mrr_act[cur] || 2200.0;
    const pVal = L.press[cur] || 3.8;
    const fVal = L.flow[cur] || 220.0;
    const wVal = L.wear[cur] || 950.0;
    const rVal = L.rul[cur] || 320;

    $('#g-mrr').textContent = `${mrrP.toFixed(0)} Å/min`;
    $('#g-mrr').className = 'gauge-val ok';
    $('#g-mrr-err').textContent = `실측: ${mrrA.toFixed(0)} Å/min (오차 ${(mrrP - mrrA).toFixed(1)})`;
    $('#g-press').textContent = `${pVal.toFixed(2)} psi`;
    $('#g-press').className = 'gauge-val';
    $('#g-flow').textContent = `${fVal.toFixed(1)} ml/min`;
    $('#g-flow').className = 'gauge-val';
    $('#g-wear').textContent = `${wVal.toFixed(1)} μm`;
    $('#g-wear').className = wVal <= 480 ? 'gauge-val warn' : 'gauge-val';
    $('#g-rul').textContent = `잔여 약 ${rVal}매 (한계 400μm)`;
  }
}

// ── 조치 이력 통합 뷰 (사람 개입 + 자동 보정 동시 표출) ────────
const seenAlarms = () => S[day].alarms.filter(a => alarmAt[a.id] !== undefined);
const seenActions = () => S[day].actions.filter(c => dIdx[c.eqp] >= c.step);

function renderLog() {
  const d = S[day];
  const alarms = seenAlarms();
  const actions = seenActions();

  const events = [];

  // 자동 보정 건
  actions.filter(c => c.auto).forEach(c => {
    events.push({
      time: c.time,
      step: c.step,
      eqp: c.eqp,
      type: 'auto',
      grade: 'INFO',
      badge: '⚡ R2R APC 자동 보정',
      badgeClass: 'auto',
      title: c.act,
      desc: c.why,
      result: c.result
    });
  });

  // 사람 개입 건 (알람 및 PM 수동 조치)
  alarms.forEach(a => {
    const act = actions.find(c => c.alarm_id === a.id);
    const dec = act ? decided[key(act)] : null;
    const isCrit = a.grade === 'CRIT';

    let resultText = '조치 완료';
    if (isCrit) {
      resultText = dec === '승인' ? '조치 완료 · 챔버 재가동됨' : (dIdx[a.eqp] < a.endStep ? '단독 정지 중 · 승인 대기' : '~' + a.end);
    } else {
      resultText = '차기 PM 이관 등록됨';
    }

    events.push({
      time: a.time,
      step: a.step,
      eqp: a.eqp,
      type: 'man',
      grade: a.grade,
      badge: '👤 사람 개입 (소모품 PM)',
      badgeClass: 'man',
      title: `${a.ko} (${a.value})`,
      desc: (act ? act.why : '') + (a.sub && a.sub.length ? ` [동반: ${a.sub.map(x=>x.ko).join(', ')}]` : ''),
      result: resultText
    });
  });

  events.sort((x, y) => x.step - y.step);

  let filtered = events;
  if (logv === 'auto') filtered = events.filter(e => e.type === 'auto');
  if (logv === 'man')  filtered = events.filter(e => e.type === 'man');

  const rows = filtered.slice().reverse().map(ev => {
    const tagHtml = `<span class="badge-tag ${ev.badgeClass}">${ev.badge}</span>`;
    const pill = ev.type === 'auto'
      ? `<span class="pill auto">무중단 실시간 보정</span>`
      : ev.result.includes('대기')
        ? `<span class="pill man">⚠️ 정지 · 승인 대기</span>`
        : `<span class="pill auto">확인 완료</span>`;

    return `<div class="row">
      <span class="led ${ev.grade}"></span>
      <span class="tm">${ev.time}</span>
      <span class="t">
        ${tagHtml} <b>${ev.title}</b> <i>${ev.eqp}</i> ${pill}
        <p>${ev.desc}</p>
      </span>
      <span class="r">${ev.result}</span>
    </div>`;
  }).join('');

  $('#log').innerHTML = rows || '<p class="empty">현재 시점까지 발생한 이력이 없습니다.</p>';

  const nAuto = events.filter(e => e.type === 'auto').length;
  const nMan = events.filter(e => e.type === 'man').length;
  if ($('#nall')) $('#nall').textContent = events.length;
  if ($('#nauto')) $('#nauto').textContent = nAuto;
  if ($('#nman')) $('#nman').textContent = nMan;
}

// ── 재생 & KPI ────────────────────────────────────────
function renderKpi() {
  const d = S[day], vis = seenAlarms(), act = seenActions();
  const auto = act.filter(c => c.auto).length;
  const prog = Math.max(...S[day].equipments.map(e => dIdx[e.id]));
  const raw = d.raw_cum[Math.max(prog, 0)];
  const hs = haltSteps();
  const e = d.equipments[eqp];
  const L = live[e.id];
  const curMRR = (halt[e.id] ? 0 : (L && L.mrr_pred[cur] ? L.mrr_pred[cur] : 2204));

  $('#kpi').innerHTML = [
    ['가상계측 MRR (제거율)', `${curMRR.toFixed(0)} Å/min`, '목표 2200 Å/min (정상 제어)'],
    ['원시 센서 임계 초과', raw, '단순 알람 누적'],
    ['R2R 자동 보정', auto, 'Preston 레시피 보정 (무중단)'],
    ['사람 조치 필요', act.length - auto, '비가역 소모품 교체 (PM)'],
    ['회피한 라인 정지', auto, '설비 셧다운 차단 효과'],
    ['정지 손실 시간', (hs * STEP_MIN) + '분', hs ? '조치 대기 중 챔버 단독 정지' : '정상 가동 (손실 0분)']
  ].map(([k, v, sb], i) => `<div class="kpi${i === 0 ? ' hero-tint' : ''}">
       <div class="kpi-lab">${k}</div><div class="kpi-val">${v}</div><div class="kpi-sub">${sb}</div></div>`).join('');
}

function renderBar() {
  const done = cur >= N() - 1;
  $('#play').textContent = playing ? '⏸ 일시정지' : done ? '↺ 다시 재생' : '▶ 재생';
  $('#play').classList.toggle('on', playing);
  $('#clock').textContent = nowT();
  $('#bar').classList.toggle('alert', queue.length > 0);
  const hl = S[day].equipments.filter(e => halt[e.id]).map(e => e.id);
  $('#slow').textContent = hl.length ? `${hl.join(', ')} 정지 중 · 배속 x1` : '양산 진행 중';
  $('#prog').style.width = ((cur + 1) / N() * 100) + '%';
  document.querySelectorAll('#spd button').forEach(b => b.classList.toggle('on', +b.dataset.s === speed));
}

function renderHold() {
  if (!queue.length) {
    $('#hold').innerHTML = '';
    $('#hold').classList.remove('show');
    return;
  }
  $('#hold').classList.add('show');
  $('#hold').innerHTML = queue.map(c => {
    const a = S[day].alarms.find(x => x.id === c.alarm_id);
    return `<div class="hold-in">
      <div class="hold-h"><span class="led CRIT"></span><b>${c.time} · ${c.eqp} — ${a ? a.ko : c.act}</b>
        <span class="badge-tag man">👤 사람 개입 필요</span>
        <span class="pill man">소모품 마모 · 단독 정지</span></div>
      <p><b>측정 상태:</b> ${a ? a.value : ''} &nbsp;·&nbsp; <b>필요 조치:</b> ${c.act}</p>
      <p class="why">${c.why}</p>
      <p class="why" style="color:var(--bad)">⚠️ [단독 정지 상태]: ${c.eqp}의 테이블 및 헤드 모터가 정지(0 RPM)되었습니다. 다른 챔버는 정상 가동 중입니다. 조치가 늦어질수록 정지 손실이 누적됩니다.</p>
      <div class="hold-b">
        <button data-k="${key(c)}" data-d="승인">소모품(패드) 교체 완료 · 재가동</button>
        <button class="ghost" data-k="${key(c)}" data-d="보류">정지 상태 유지</button>
      </div>
    </div>`;
  }).join('');
}

function step() {
  if (cur >= N() - 1) { stop(); return; }
  cur++;
  stepLive(cur);

  const hits = S[day].actions.filter(c => !c.auto && c.grade === 'CRIT'
    && dIdx[c.eqp] === c.step && !decided[key(c)] && !queue.includes(c));

  if (hits.length) {
    hits.forEach(c => halt[c.eqp] = true);
    if (saved === null) saved = speed;
    speed = 1;
    queue.push(...hits);
    renderHold();
  }
  paint();
  timer = setTimeout(step, SPEED[speed]);
}

function play() {
  if (cur >= N() - 1) {
    cur = 0; decided = {}; queue = []; saved = null;
    resetLive(); stepLive(0);
  }
  playing = true;
  renderBar();
  renderTwin();
  timer = setTimeout(step, SPEED[speed]);
}
function pause() {
  playing = false;
  clearTimeout(timer);
  renderBar();
  renderTwin();
}
function stop() {
  playing = false;
  clearTimeout(timer);
  renderBar();
  renderTwin();
}

function paint() {
  paintTabs();
  renderCharts();
  renderTwin();
  renderLog();
  renderKpi();
  renderBar();
}

function paintTabs() {
  const dotClasses = ['ch-a', 'ch-b', 'ch-c'];
  $('#eqps').innerHTML = S[day].equipments.map((e, i) =>
    `<button class="${i === eqp ? 'on' : ''}${halt[e.id] ? ' halted' : ''}" data-i="${i}" title="${e.id} (${e.type}) 모니터링">
      <span class="ch-dot ${dotClasses[i] || 'ch-a'}"></span>
      <b>${e.id}</b>
      <em>${e.type}</em>
      ${halt[e.id] ? '<b class="stopdot">정지</b>' : ''}
    </button>`).join('');
}

window.switchEqp = function(i) {
  eqp = i;
  paintTabs();
  renderCharts();
  renderTwin();
};

function render() {
  const d = S[day];
  if (!live[d.equipments[0].id]) fillAll();
  document.querySelectorAll('#days button').forEach(b =>
    b.classList.toggle('on', +b.dataset.i === day));
  $('#title').textContent = `${d.date} · ${d.title}`;
  const bd = $('#daybadge');
  if (bd) bd.textContent = `${d.date.slice(5)} ${d.title}`;
  $('#brief').textContent = d.brief;
  paintTabs();
  renderHold();
  paint();
}

// ── 이벤트 리스너 ─────────────────────────────────────
$('#days').innerHTML = S.map((d, i) =>
  `<button data-i="${i}"><b>${d.date.slice(5)}</b><span>${d.title}</span></button>`).join('');
$('#spd').innerHTML = [1, 5, 20, 50].map(s => `<button data-s="${s}">x${s}</button>`).join('');

const pickDay = e => {
  const b = e.target.closest('button'); if (!b) return;
  stop(); day = +b.dataset.i; eqp = 0; cur = N() - 1;
  queue = []; saved = null; decided = {};
  fillAll(); render();
};
$('#days').onclick = pickDay;

$('#eqps').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  eqp = +b.dataset.i;
  document.querySelectorAll('#eqps button').forEach((x, i) => x.classList.toggle('on', i === eqp));
  renderCharts();
  renderTwin();
};

$('#logtabs').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  logv = b.dataset.v;
  document.querySelectorAll('#logtabs button').forEach(x => x.classList.toggle('on', x === b));
  renderLog();
};

$('#play').onclick = () => playing ? pause() : play();
$('#rst').onclick  = () => {
  stop(); cur = 0; queue = []; saved = null; decided = {};
  resetLive(); stepLive(0); paint(); renderHold();
};
$('#end').onclick  = () => {
  stop(); cur = N() - 1; queue = []; saved = null; decided = {};
  fillAll(); paint(); renderHold();
};
$('#spd').onclick  = e => {
  const b = e.target.closest('button'); if (!b) return;
  speed = +b.dataset.s; saved = null; renderBar();
};

$('#hold').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  const c = queue.find(x => key(x) === b.dataset.k);
  decided[b.dataset.k] = b.dataset.d;

  if (b.dataset.d === '승인' && c) {
    halt[c.eqp] = false;
    replaced[c.eqp] = true;
    replaceIdx[c.eqp] = dIdx[c.eqp];
  }
  queue = queue.filter(x => key(x) !== b.dataset.k);
  if (!queue.length && saved !== null) {
    speed = saved; saved = null;
  }
  renderHold();
  paint();
};

window.addEventListener('resize', () => {
  loadColors();
  if (live[S[day].equipments[0].id]) paint();
});
window.__state = () => ({ cur, live, dIdx, halt, replaced, queue, speed });

fillAll();
render();
