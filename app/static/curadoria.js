// Fila de curadoria do Técnico de Qualidade (Bloco 5 da Figura 1)
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const TIPOS = { falso_positivo: 'Falso positivo (inspetor disse que não é defeito)', defeito_nao_apontado: 'Defeito não apontado pelo sistema', classe_errada: 'Classe corrigida' };
const nome = c => c === 'outro' ? 'Outro' : (ROTULOS[c] || c || '—');

async function recorte(cv, c) {
  const im = new Image(); im.src = `/api/inspecoes/${c.inspecao_id}/imagem/original`; await im.decode();
  const g = cv.getContext('2d'); const m = 40;
  const x = Math.max(0, c.x1 - m), y = Math.max(0, c.y1 - m), w = Math.min(600, c.x2 + m) - x, h = Math.min(600, c.y2 + m) - y;
  const s = Math.min(cv.width / w, cv.height / h);
  g.drawImage(im, x, y, w, h, 0, 0, w * s, h * s);
  g.lineWidth = 3; g.strokeStyle = '#000'; g.strokeRect((c.x1 - x) * s, (c.y1 - y) * s, (c.x2 - c.x1) * s, (c.y2 - c.y1) * s);
  g.lineWidth = 1.5; g.setLineDash([4, 3]); g.strokeStyle = '#ffd400'; g.strokeRect((c.x1 - x) * s, (c.y1 - y) * s, (c.x2 - c.x1) * s, (c.y2 - c.y1) * s);
}

async function carregar() {
  const st = $('st').value;
  try {
    const itens = await api('/api/curadoria?status=' + st);
    if (!itens.length) { $('lista').innerHTML = '<p class="dica">Nada aqui.</p>'; return; }
    $('lista').innerHTML = itens.map(c => `<div class="cur-item">
      <canvas width="220" height="220" id="cv-${c.id}" aria-label="Recorte da região corrigida"></canvas>
      <div><b>${esc(TIPOS[c.tipo_correcao])}</b>
        <p>Classe: <b>${esc(nome(c.classe))}</b>${c.classe_original && c.classe_original !== c.classe ? ` (sistema: ${esc(nome(c.classe_original))})` : ''}</p>
        <p class="dica">Lote ${esc(c.lote)} · modelo ${esc(c.modelo_placa)} · turno ${esc(c.turno)} · posto ${esc(c.posto)} · ${esc(c.criado_em.slice(0, 16).replace('T', ' '))}</p>
        <p><a href="/api/inspecoes/${c.inspecao_id}/imagem/anotada" target="_blank">Abrir imagem anotada completa</a></p>
        ${st === 'pendente' ? `<label for="obs-${c.id}">Observação</label><input id="obs-${c.id}" maxlength="500">
        <div style="display:flex;gap:.5rem;margin-top:.5rem"><button class="btn" data-ap="${c.id}">Aprovar para treino</button>
        <button class="btn sec" data-rj="${c.id}">Rejeitar</button></div>` : `<p class="dica">${esc(c.obs_curadoria || '')}</p>`}
      </div></div>`).join('');
    itens.forEach(c => recorte($('cv-' + c.id), c).catch(() => {}));
    const curar = async (id, aprovar) => {
      try { await api('/api/curadoria/' + id, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ aprovar, obs: $('obs-' + id).value || null }) }); carregar(); }
      catch (e) { $('msg').innerHTML = `<p class="erro">${esc(e.message)}</p>`; }
    };
    document.querySelectorAll('[data-ap]').forEach(b => b.onclick = () => curar(+b.dataset.ap, true));
    document.querySelectorAll('[data-rj]').forEach(b => b.onclick = () => curar(+b.dataset.rj, false));
  } catch (e) { $('lista').innerHTML = `<p class="erro">${esc(e.message)}</p>`; }
}
$('st').onchange = carregar;
$('exportar').onclick = async () => {
  try { const r = await api('/api/curadoria/exportar', { method: 'POST' });
    $('msg').innerHTML = `<p class="ok-msg">Exportadas ${r.imagens} imagem(ns) com ${r.caixas} caixa(s) para <code>${esc(r.pasta)}</code>${r.caixas_sem_classe_yolo ? ` (${r.caixas_sem_classe_yolo} marcação(ões) "outro/anomalia" sem classe YOLO ficaram de fora)` : ''}.</p>`; }
  catch (e) { $('msg').innerHTML = `<p class="erro">${esc(e.message)}</p>`; }
};
carregar();
