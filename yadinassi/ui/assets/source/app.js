'use strict';
const token = new URLSearchParams(location.hash.slice(1)).get('session');
history.replaceState(null, '', location.pathname);
const status = document.getElementById('status'), result = document.getElementById('result'), close = document.getElementById('close');
let id = 0;
async function call(method) {
  const response = await fetch('/rpc', {method:'POST', headers:{'Content-Type':'application/x-ndjson','X-Yadinassi-Session':token || ''},body:JSON.stringify({jsonrpc:'2.0',id:++id,method,params:{}})+'\n'});
  if (!response.ok) throw new Error('Доступ к диагностике потерян. Повторного запуска runtime не будет.');
  const data = await response.json();
  if (data.result.protocol !== 'yadinassi-source-diagnostics/1') throw new Error('Неизвестный протокол');
  return data.result.state;
}
call('source.snapshot').then(state => {
  status.textContent = state.kind === 'closed' ? 'Закрыто' : 'Источник: ' + state.name + '; попытка запуска: ' + state.startup;
  result.textContent = JSON.stringify(state, null, 2);
  close.disabled = state.kind === 'closed';
}).catch(error => {status.textContent = error.message;});
close.addEventListener('click', async () => {
  close.disabled = true;
  try {await call('source.close'); status.textContent = 'Диагностика закрыта';}
  catch(error) {status.textContent = error.message;}
});
