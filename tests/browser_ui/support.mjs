/** Closed QA-only helpers. No browser/process starts when imported. */
import {createHash} from 'node:crypto';

export const SCENARIOS = Object.freeze([
  'list_and_open', 'duplicate_then_create', 'scalar_edit_save', 'repeated_save',
  'dirty_close_discard', 'reload_reattach', 'reference_and_narrow_layout',
  'close_relaunch_durable_reopen',
]);
export const ARTIFACTS = Object.freeze(['result.json', 'manifest.json',
  'list.png', 'editor.png', 'narrow.png']);
export const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');

export function launchURL(value) {
  if (typeof value !== 'string' || !/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}\/#session=[A-Za-z0-9_-]{43}$/.test(value))
    throw Error('invalid_launch_url');
  const url = new URL(value);
  if (Number(url.port) > 65535) throw Error('invalid_launch_url');
  return url;
}

export function launchOutputReader() {
  let buffered='',settled=false;
  return chunk=>{
    if(settled)return null;
    if(!Buffer.isBuffer(chunk)||Buffer.byteLength(buffered)+chunk.length>4096){
      settled=true;buffered='';throw Error('host_output_budget');
    }
    buffered+=chunk.toString();
    const match=buffered.match(/^http:\/\/127\.0\.0\.1:[0-9]+\/#session=[A-Za-z0-9_-]{43}(?=\r?\n)/m);
    if(!match)return null;
    settled=true;buffered='';return launchURL(match[0]);
  };
}

export function allowedRequest(value, origin) {
  try {
    const url = new URL(value);
    return url.origin === origin && !url.username && !url.password && !url.search &&
      ['/', '/app.js', '/style.css', '/LICENSE.txt', '/rpc', '/favicon.ico'].includes(url.pathname);
  } catch { return false; }
}
export function redact(value, tokens = []) {
  let text = String(value);
  for (const token of tokens) if (token) text = text.split(token).join('[redacted]');
  return text.replace(/#session=[^\s"'<>]+/g, '#session=[redacted]')
    .replace(/(X-Yadinassi-Session[^\n]*?:\s*)[^\s"'<>]+/gi, '$1[redacted]').slice(0, 8192);
}
export function childEnvironment(source, ownedHome) {
  const env = {HOME: ownedHome, TMPDIR: ownedHome, LANG: 'C.UTF-8',
    PYTHONDONTWRITEBYTECODE: '1', PYTHONIOENCODING: 'utf-8'};
  for (const key of ['PATH', 'PLAYWRIGHT_BROWSERS_PATH']) if (source[key]) env[key] = source[key];
  return env;
}

export function ownBrowserPid(processInfo) {
  if(!Array.isArray(processInfo)||processInfo.length>128)throw Error('browser_pid_invalid');
  const entries=processInfo.filter(row=>row&&row.type==='browser');
  if(entries.length!==1||!Number.isSafeInteger(entries[0].id)||entries[0].id<=0)
    throw Error('browser_pid_invalid');
  return entries[0].id;
}


export function commandLineArgs(bytes) {
  if(!Buffer.isBuffer(bytes)||bytes.length===0||bytes.length>16384||bytes.at(-1)!==0)
    throw Error('browser_command_invalid');
  return new TextDecoder('utf-8',{fatal:true}).decode(bytes).split(String.fromCharCode(0)).filter(Boolean);
}

export function sandboxCommand(args) {
  if (!Array.isArray(args) || !args.every(x => typeof x === 'string')) throw Error('sandbox_command_missing');
  const forbidden = ['--no-sandbox', '--disable-setuid-sandbox', '--disable-namespace-sandbox',
    '--disable-seccomp-filter-sandbox', '--disable-gpu-sandbox', '--single-process',
    '--no-zygote', '--disable-web-security'];
  if (args.some(arg => forbidden.some(flag => arg === flag || arg.startsWith(flag + '='))))
    throw Error('sandbox_disabled');
  if (!args.includes('--remote-debugging-pipe')) throw Error('unexpected_browser_transport');
  return true;
}
export function sandboxStatus(text) {
  // chrome://sandbox is read-only evidence. Unknown output is not a PASS.
  if (typeof text !== 'string' || text.length > 8192) throw Error('sandbox_status_invalid');
  const layer = /(?:Namespace sandbox\s+Yes|Layer 1 Sandbox\s+(?:Namespace|SUID))/.test(text);
  const seccomp = /Seccomp-BPF sandbox\s+Yes/.test(text);
  if (!layer || !seccomp) throw Error('sandbox_not_confirmed');
  return {layer1: true, seccompBpf: true};
}
export function completedResult(records) {
  return records.length === SCENARIOS.length && records.every((row, index) =>
    row.name === SCENARIOS[index] && row.status === 'PASS');
}
