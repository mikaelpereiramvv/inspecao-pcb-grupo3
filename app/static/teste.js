// Teste controlado com voluntários (Seção 10, aspectos 4 e 5)
const $ = id => document.getElementById(id);
const tela = $('tela-t'), g = tela.getContext('2d');
let plano = null, idx = 0, cliques = [], respostas = [], img = null, inicio = 0, timer = null, zoom = 1;

$('comecar').onclick = async () => {
  try {
    plano = await api(`/api/teste/${encodeURIComponent(SESSAO)}/plano?participante=${encodeURIComponent($('participante').value.trim())}`);
    $('inicio').hidden = true; $('tarefa').hidden = false; abrir(0);
  } catch (e) { $('msg-ini').innerHTML = `<p class="erro">${e.message}</p>`; }
};

async function abrir(i) {
  idx = i; cliques = [];
  const p = plano.placas[i];
  $('titulo-placa').textContent = `Placa ${i + 1} de ${plano.placas.length}`;
  $('condicao').textContent = p.com_assistente ? 'COM assistente' : 'SEM assistente';
  img = new Image(); img.src = `/api/teste/${encodeURIComponent(SESSAO)}/img/${p.arquivo}`; await img.decode();
  desenhar(); inicio = Date.now(); clearInterval(timer);
  timer = setInterval(() => {
    const resta = plano.limite_s - (Date.now() - inicio) / 1000;
    $('crono-t').textContent = Math.max(0, Math.ceil(resta)) + 's';
    $('crono-t').classList.toggle('estourou', resta <= 5);
    if (resta <= 0) concluir(true);
  }, 200);
}

function desenhar() {
  const p = plano.placas[idx];
  tela.width = p.largura * zoom; tela.height = p.altura * zoom;
  g.setTransform(zoom, 0, 0, zoom, 0, 0); g.drawImage(img, 0, 0, p.largura, p.altura);
  for (const s of p.sugestoes) {
    const forte = s.confianca >= plano.limiar_revisar;
    g.setLineDash(forte ? [] : [6, 4]);
    for (const [cor, esp] of [['#000', 4], ['#e03030', 2]]) { g.strokeStyle = cor; g.lineWidth = esp / zoom; g.strokeRect(s.x1, s.y1, s.x2 - s.x1, s.y2 - s.y1); }
    g.setLineDash([]); g.font = 'bold 12px system-ui'; const t = `${ROTULOS[s.classe] || s.classe} ${Math.round(s.confianca * 100)}%`;
    g.fillStyle = '#b3261e'; g.fillRect(s.x1, Math.max(0, s.y1 - 16), g.measureText(t).width + 6, 16);
    g.fillStyle = '#fff'; g.fillText(t, s.x1 + 3, Math.max(12, s.y1 - 4));
  }
  cliques.forEach(([x, y], k) => {
    g.beginPath(); g.arc(x, y, 9, 0, 2 * Math.PI); g.lineWidth = 4 / zoom; g.strokeStyle = '#000'; g.stroke();
    g.lineWidth = 2 / zoom; g.strokeStyle = '#4aa3ff'; g.stroke();
    g.fillStyle = '#fff'; g.font = 'bold 11px system-ui'; g.fillText(String(k + 1), x + 11, y - 9);
  });
  $('n-cliques').textContent = cliques.length;
}
tela.addEventListener('click', ev => {
  const r = tela.getBoundingClientRect(); const x = (ev.clientX - r.left) / zoom, y = (ev.clientY - r.top) / zoom;
  const k = cliques.findIndex(([cx, cy]) => Math.hypot(cx - x, cy - y) < 10);
  if (k >= 0) cliques.splice(k, 1); else cliques.push([Math.round(x * 10) / 10, Math.round(y * 10) / 10]);
  desenhar();
});
$('zoom-t').oninput = () => { zoom = +$('zoom-t').value; desenhar(); };

function concluir(esgotou = false) {
  clearInterval(timer);
  respostas.push({ id: plano.placas[idx].id, cliques, tempo_s: (Date.now() - inicio) / 1000, esgotou });
  if (idx + 1 < plano.placas.length) abrir(idx + 1);
  else { $('tarefa').hidden = true; $('questionario').hidden = false; }
}
$('concluir').onclick = () => concluir(false);

$('enviar').onclick = async () => {
  const u = document.querySelector('input[name=usab]:checked');
  if (!u) { $('msg-q').innerHTML = '<p class="erro">Escolha uma nota de 1 a 5.</p>'; return; }
  const n = document.querySelector('input[name=notou]:checked');
  try {
    await api(`/api/teste/${encodeURIComponent(SESSAO)}/resultado`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ participante: plano.participante, usabilidade: +u.value, notou_sugestao_errada: n ? n.value : null,
        comentario: $('coment').value, respostas }) });
    $('questionario').innerHTML = '<h2>Obrigado!</h2><p>Resultado registrado. Chame o próximo participante.</p><a class="btn" href="">Novo participante</a>';
  } catch (e) { $('msg-q').innerHTML = `<p class="erro">${e.message}</p>`; }
};
