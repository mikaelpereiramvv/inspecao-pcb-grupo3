// Painel de Indicadores (Bloco 5 da Figura 1)
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = v => v == null ? '—' : (v * 100).toFixed(1).replace('.', ',') + '%';

function tabelaGrupo(linhas) {
  if (!linhas.length) return '<p class="dica">Sem dados.</p>';
  const max = Math.max(...linhas.map(l => l.taxa_defeito), 0.0001);
  return `<table><thead><tr><th scope="col">Grupo</th><th scope="col">Inspeções</th><th scope="col">Com defeito</th><th scope="col">Reprovadas</th><th scope="col">Taxa de defeito</th></tr></thead><tbody>
  ${linhas.map(l => `<tr><td>${esc(l.chave)}</td><td>${l.inspecoes}</td><td>${l.com_defeito}</td><td>${l.reprovadas}</td>
    <td><div style="display:flex;gap:.4rem;align-items:center"><span style="min-width:3.5rem">${pct(l.taxa_defeito)}</span>
    <div class="barra" style="width:${(l.taxa_defeito / max) * 100}px" aria-hidden="true"></div></div></td></tr>`).join('')}</tbody></table>`;
}

async function carregar() {
  const p = new URLSearchParams(new FormData($('filtros')));
  if (p.get('ate')) p.set('ate', p.get('ate') + 'T23:59:59');
  try {
    const [r, alertas] = await Promise.all([api('/api/painel?' + p), api('/api/alertas' + (p.get('desde') ? '?desde=' + p.get('desde') : ''))]);
    $('alertas').innerHTML = alertas.length ? alertas.map(a => `<div class="alerta">${esc(a.mensagem)} <span class="dica">Turnos: ${esc(a.turnos)}</span></div>`).join('')
      : '<p class="dica">Nenhuma reincidência acima dos limites configurados.</p>';
    const k = [
      ['Placas inspecionadas', r.total_inspecoes, ''],
      ['Taxa de reprovação', pct(r.taxa_reprovacao), `${r.reprovadas} reprovadas`],
      ['Aprovadas', r.aprovadas, ''],
      ['Revisar 2ª vez', r.revisar_2, `${r.passaram_por_revisar_1} passaram por reanálise`],
      ['Em contingência manual', r.em_contingencia, 'assistente indisponível'],
      ['Latência média', r.latencia_media_s == null ? '—' : r.latencia_media_s.toFixed(2).replace('.', ',') + ' s', 'meta < 5 s'],
      ['Concordância sugestão × decisão', pct(r.concordancia_sugestao_decisao), 'sugestões Aprovar/Reprovar'],
      ['Alertas descartados', pct(r.taxa_alertas_descartados), 'monitora falsos positivos'],
    ];
    $('kpis').innerHTML = k.map(([t, v, s]) => `<div class="kpi"><div class="r">${t}</div><div class="v">${v}</div><div class="r">${s}</div></div>`).join('');
    $('por-tipo').innerHTML = r.por_tipo.length ? `<table><thead><tr><th scope="col">Tipo</th><th scope="col">Ocorrências</th><th scope="col">Placas</th></tr></thead><tbody>
      ${r.por_tipo.map(t => `<tr><td>${esc(t.rotulo)}</td><td>${t.ocorrencias}</td><td>${t.placas}</td></tr>`).join('')}</tbody></table>` : '<p class="dica">Sem defeitos registrados.</p>';
    $('por-lote').innerHTML = tabelaGrupo(r.por_lote);
    $('por-turno').innerHTML = tabelaGrupo(r.por_turno);
    $('por-etapa').innerHTML = tabelaGrupo(r.por_etapa_origem);
    $('por-posto').innerHTML = tabelaGrupo(r.por_posto);
    const c = r.correcoes;
    $('correcoes').innerHTML = `<table><tbody>
      <tr><th scope="row">Falsos positivos descartados</th><td>${c.falso_positivo || 0}</td></tr>
      <tr><th scope="row">Defeitos não apontados (marcados pelo inspetor)</th><td>${c.defeito_nao_apontado || 0}</td></tr>
      <tr><th scope="row">Classe corrigida</th><td>${c.classe_errada || 0}</td></tr></tbody></table>
      <p class="dica">Alta taxa de descarte indica limiar baixo demais; muitos defeitos não apontados indicam necessidade de retreino.</p>`;
  } catch (e) { $('alertas').innerHTML = `<p class="erro">${esc(e.message)}</p>`; }
}
$('filtros').onsubmit = ev => { ev.preventDefault(); carregar(); };
carregar();
