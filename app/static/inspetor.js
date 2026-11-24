// Interface Web do Inspetor (Bloco 3 da Figura 1)
const $ = (id) => document.getElementById(id);
const tela = $('tela'), g = tela.getContext('2d');
const TAM = 600;

let atual = null;            // resposta da inspeção
let marcas = [];             // marcações do sistema (YOLO + anomalias), na ordem do servidor
let descartadas = new Set(); // índices marcados como "não é defeito"
let reclass = {};            // índice -> nova classe
let adicionadas = [];        // caixas desenhadas pelo inspetor
let imgAnotada = null, imgOriginal = null;
let zoom = 1, desenhando = false, arrasto = null;
let cronoInicio = null, cronoTimer = null;

function nomeClasse(c) { return ROTULOS[c] || c; }
function msg(el, texto, tipo = 'erro') { $(el).innerHTML = texto ? `<p class="${tipo}" role="${tipo === 'erro' ? 'alert' : 'status'}">${texto}</p>` : ''; }
function esc(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

// ---------------------------------------------------------------- metadados
function preencher(m) {
  for (const k of ['lote', 'modelo_placa', 'turno', 'posto', 'etapa_origem', 'data_hora_producao']) if (m[k] != null) $(k).value = m[k];
  $('simulado').value = m.simulado ? 'true' : 'false';
}
$('btn-simular').onclick = async () => {
  try { preencher(await api('/api/metadados/simulados?modelo_placa=' + encodeURIComponent($('modelo_placa').value || 'HRIPCB'))); msg('msg-entrada', ''); }
  catch (e) { msg('msg-entrada', e.message); }
};
$('qr').addEventListener('change', async () => {
  if (!$('qr').value.trim()) return;
  const fd = new FormData(); fd.append('texto', $('qr').value);
  try { preencher(await api('/api/metadados/qr', { method: 'POST', body: fd })); msg('msg-entrada', ''); }
  catch (e) { msg('msg-entrada', e.message); }
});
['lote', 'modelo_placa', 'turno', 'posto', 'etapa_origem'].forEach(k => $(k).addEventListener('input', () => $('simulado').value = 'false'));

// ---------------------------------------------------------------- inspeção
$('form-insp').onsubmit = async (ev) => {
  ev.preventDefault();
  const fd = new FormData($('form-insp'));
  $('btn-inspecionar').disabled = true; $('btn-inspecionar').textContent = 'Processando…';
  msg('msg-entrada', ''); msg('msg-decisao', '');
  try {
    mostrar(await api('/api/inspecoes', { method: 'POST', body: fd }), true);
  } catch (e) { msg('msg-entrada', e.message); }
  finally { $('btn-inspecionar').disabled = false; $('btn-inspecionar').textContent = 'Inspecionar'; }
};

async function carregarImg(url) {
  const im = new Image(); im.src = url + '?t=' + Date.now();
  await im.decode(); return im;
}

async function mostrar(r, nova) {
  atual = r; marcas = r.marcacoes || [];
  if (nova) { descartadas = new Set(); reclass = {}; adicionadas = []; iniciarCrono(); }
  else { descartadas = new Set(); reclass = {}; }  // após reanálise as marcações mudam
  [imgAnotada, imgOriginal] = await Promise.all([
    carregarImg(`/api/inspecoes/${r.id}/imagem/anotada`), carregarImg(`/api/inspecoes/${r.id}/imagem/original`)]);
  $('vazio').hidden = true; tela.hidden = false;
  renderSugestao(); renderLista(); desenhar();
  document.querySelectorAll('.decisoes button').forEach(b => b.disabled = false);
  document.querySelector('[data-d=REVISAR_1]').disabled = r.modo !== 'assistido' || r.reprocessamentos >= 1;
  $('btn-desenhar').disabled = false;
}

function renderSugestao() {
  const r = atual;
  const cls = r.sugestao ? 'sug-' + r.sugestao : 'sug-CONTINGENCIA';
  const titulo = r.sugestao ? ({ APROVAR: 'APROVAR', REVISAR: 'REVISAR', REPROVAR: 'REPROVAR' })[r.sugestao] : 'MODO CONTINGÊNCIA';
  $('sugestao').innerHTML = `<div class="sugestao ${cls}"><div class="titulo">${titulo}</div>
    <div>${esc(r.motivo)}</div>
    <div class="lembrete">Tempo de análise: ${(r.latencia_ms / 1000).toFixed(2)} s${r.reprocessamentos ? ' · após reanálise' : ''}
    ${r.anomalia_score != null ? ` · índice de anomalia: ${r.anomalia_score.toFixed(2)} (≥ 1 = fora do padrão)` : ''}</div></div>`;
  $('avisos').innerHTML = (r.avisos || []).map(a => `<p class="aviso">${esc(a)}</p>`).join('');
}

function opcoesClasse(sel) {
  return [...CLASSES, 'anomalia', 'outro'].map(c => `<option value="${c}" ${c === sel ? 'selected' : ''}>${esc(nomeClasse(c === 'outro' ? 'outro' : c) === 'outro' ? 'Outro defeito' : nomeClasse(c))}</option>`).join('');
}

function renderLista() {
  const itens = marcas.map((m, i) => {
    const desc = descartadas.has(i);
    const classe = reclass[i] || m.tipo;
    const conf = m.confianca != null ? `${Math.round(m.confianca * 100)}%` : '';
    return `<li class="${desc ? 'descartada' : ''}">
      <div class="linha"><span class="num">${i + 1}.</span><span>${esc(nomeClasse(m.tipo))}</span>
        <span class="tag">${m.origem === 'anomalia' ? 'anomalia' : 'confiança ' + conf}</span></div>
      <div class="acoes">
        <label class="sr" for="rc-${i}">Classe da marcação ${i + 1}</label>
        <select id="rc-${i}" data-i="${i}" ${desc ? 'disabled' : ''}>${opcoesClasse(classe)}</select>
        <button type="button" class="btn sec" data-desc="${i}" aria-pressed="${desc}">${desc ? 'Desfazer' : 'Não é defeito'}</button>
      </div></li>`;
  });
  const extras = adicionadas.map((a, k) => `<li>
      <div class="linha"><span class="num">+${k + 1}.</span><span>Marcado por você</span></div>
      <div class="acoes"><label class="sr" for="ad-${k}">Classe</label>
        <select id="ad-${k}" data-k="${k}">${opcoesClasse(a.classe)}</select>
        <button type="button" class="btn sec" data-rm="${k}">Remover</button></div></li>`);
  $('marcas').innerHTML = (itens.concat(extras).join('')) ||
    '<li>Nenhuma marcação. Faça a verificação visual completa antes de decidir.</li>';
  $('marcas').querySelectorAll('select[data-i]').forEach(s => s.onchange = () => {
    const i = +s.dataset.i; if (s.value === marcas[i].tipo) delete reclass[i]; else reclass[i] = s.value; desenhar(); });
  $('marcas').querySelectorAll('[data-desc]').forEach(b => b.onclick = () => {
    const i = +b.dataset.desc; descartadas.has(i) ? descartadas.delete(i) : descartadas.add(i); renderLista(); desenhar(); });
  $('marcas').querySelectorAll('select[data-k]').forEach(s => s.onchange = () => { adicionadas[+s.dataset.k].classe = s.value; desenhar(); });
  $('marcas').querySelectorAll('[data-rm]').forEach(b => b.onclick = () => { adicionadas.splice(+b.dataset.rm, 1); renderLista(); desenhar(); });
}

// ---------------------------------------------------------------- desenho
function rotulo(txt, x, y, cor) {
  g.font = 'bold 13px system-ui'; const w = g.measureText(txt).width + 8;
  g.fillStyle = cor; g.fillRect(x, Math.max(0, y - 18), w, 18);
  g.fillStyle = '#fff'; g.fillText(txt, x + 4, Math.max(13, y - 5));
}
function desenhar() {
  if (!imgAnotada) return;
  tela.width = TAM * zoom; tela.height = TAM * zoom;
  g.setTransform(zoom, 0, 0, zoom, 0, 0);
  g.drawImage($('ver-original').checked ? imgOriginal : imgAnotada, 0, 0, TAM, TAM);
  if ($('ver-original').checked) return;
  marcas.forEach((m, i) => {
    if (descartadas.has(i)) {            // X sobre o falso positivo
      for (const [cor, esp] of [['#000', 5], ['#fff', 2]]) {
        g.strokeStyle = cor; g.lineWidth = esp / zoom; g.beginPath();
        g.moveTo(m.x1, m.y1); g.lineTo(m.x2, m.y2); g.moveTo(m.x2, m.y1); g.lineTo(m.x1, m.y2); g.stroke();
      }
    } else if (reclass[i]) {
      rotulo(`${i + 1} → ${nomeClasse(reclass[i])}`, m.x1, m.y2 + 18, '#1d4e89');
    }
  });
  const todas = adicionadas.slice(); if (arrasto) todas.push(arrasto);
  todas.forEach((a, k) => {
    g.setLineDash([3, 3]); g.lineWidth = 4 / zoom; g.strokeStyle = '#000'; g.strokeRect(a.x1, a.y1, a.x2 - a.x1, a.y2 - a.y1);
    g.lineWidth = 2 / zoom; g.strokeStyle = '#4aa3ff'; g.strokeRect(a.x1, a.y1, a.x2 - a.x1, a.y2 - a.y1); g.setLineDash([]);
    if (a !== arrasto) rotulo(`+${k + 1}. ${a.classe === 'outro' ? 'Outro' : nomeClasse(a.classe)}`, a.x1, a.y1 - 2, '#1d4e89');
  });
}
$('zoom').oninput = () => { zoom = +$('zoom').value; $('zoom-v').textContent = Math.round(zoom * 100) + '%'; desenhar(); };
$('ver-original').onchange = desenhar;
$('btn-desenhar').onclick = () => {
  desenhando = !desenhando; $('btn-desenhar').setAttribute('aria-pressed', desenhando);
  $('btn-desenhar').textContent = desenhando ? 'Arraste na imagem… (clique para sair)' : '+ Marcar defeito não apontado';
};
function pos(ev) { const r = tela.getBoundingClientRect(); return [(ev.clientX - r.left) / zoom, (ev.clientY - r.top) / zoom]; }
tela.addEventListener('mousedown', ev => { if (!desenhando) return; const [x, y] = pos(ev); arrasto = { x0: x, y0: y, x1: x, y1: y, x2: x, y2: y, classe: 'outro' }; });
tela.addEventListener('mousemove', ev => {
  if (!arrasto) return; const [x, y] = pos(ev);
  Object.assign(arrasto, { x1: Math.min(arrasto.x0, x), y1: Math.min(arrasto.y0, y), x2: Math.max(arrasto.x0, x), y2: Math.max(arrasto.y0, y) });
  desenhar();
});
window.addEventListener('mouseup', () => {
  if (!arrasto) return;
  const a = arrasto; arrasto = null;
  if (a.x2 - a.x1 >= 4 && a.y2 - a.y1 >= 4) {
    const c = v => Math.max(0, Math.min(TAM, Math.round(v * 10) / 10));
    adicionadas.push({ x1: c(a.x1), y1: c(a.y1), x2: c(a.x2), y2: c(a.y2), classe: 'outro' });
    renderLista();
  }
  desenhar();
});

// ---------------------------------------------------------------- cronômetro (janela ~30 s)
function iniciarCrono() {
  clearInterval(cronoTimer); cronoInicio = Date.now();
  cronoTimer = setInterval(() => {
    const resta = 30 - Math.floor((Date.now() - cronoInicio) / 1000);
    $('crono').textContent = resta >= 0 ? `${resta}s` : `+${-resta}s`;
    $('crono').classList.toggle('estourou', resta < 0);
  }, 250);
}

// ---------------------------------------------------------------- decisão
async function decidir(d) {
  if (!atual) return;
  const botoes = document.querySelectorAll('.decisoes button');
  if (d === 'REVISAR_1') {
    botoes.forEach(b => b.disabled = true);
    msg('msg-decisao', 'Reanalisando (máx. 3 s)…', 'aviso');
    try { await mostrar(await api(`/api/inspecoes/${atual.id}/reprocessar`, { method: 'POST' }), false); msg('msg-decisao', 'Reanálise concluída. Confira e decida.', 'ok-msg'); }
    catch (e) { msg('msg-decisao', e.message); botoes.forEach(b => b.disabled = false); document.querySelector('[data-d=REVISAR_1]').disabled = true; }
    return;
  }
  if (d === 'APROVAR' && marcas.some((_, i) => !descartadas.has(i)) &&
      !confirm('Ainda há marcações não descartadas. Confirmar APROVAÇÃO mesmo assim?')) return;
  botoes.forEach(b => b.disabled = true);
  try {
    const r = await api(`/api/inspecoes/${atual.id}/decisao`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decisao: d, descartadas: [...descartadas], reclassificadas: reclass,
        adicionadas: adicionadas.map(({ x1, y1, x2, y2, classe }) => ({ x1, y1, x2, y2, classe })), observacao: $('obs').value || null }),
    });
    clearInterval(cronoTimer);
    msg('msg-decisao', `Registrado: <b>${d.replace('_', ' ')}</b> · ${r.defeitos_registrados} defeito(s) · ${r.correcoes} correção(ões) enviada(s) à curadoria. Pronto para a próxima placa.`, 'ok-msg');
    atual = null; $('btn-desenhar').disabled = true; desenhando = false; $('obs').value = ''; $('imagem').value = '';
    $('imagem').focus();
  } catch (e) { msg('msg-decisao', e.message); botoes.forEach(b => b.disabled = false); }
}
document.querySelectorAll('.decisoes button').forEach(b => b.onclick = () => decidir(b.dataset.d));
document.addEventListener('keydown', ev => {
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) || !atual) return;
  const mapa = { '1': 'APROVAR', '2': 'REVISAR_1', '3': 'REVISAR_2', '4': 'REPROVAR' };
  const d = mapa[ev.key]; if (!d) return;
  const b = document.querySelector(`[data-d=${d}]`); if (b && !b.disabled) decidir(d);
});
