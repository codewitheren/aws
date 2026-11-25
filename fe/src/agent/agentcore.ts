/**
 * AgentCore Runtime istemcisi. Backend'in beş eylemiyle konuşur (agent/main.py):
 * prepare → (kullanıcı kararları tarayıcıda) → finish, status, download, explain, view, depot.
 * Koşu kimliği Runtime oturum UUID'sidir; her yeni koşu yeni bir oturum açar.
 */
import { nf } from '../lib/format';
import type { AgentClient } from './client';
import { readEventStream } from './sse';
import type {
  ApprovalOutcome, ApprovalRequest, ApprovalResolution, ChatEvent, RunEvent, TransferTypeId,
} from './types';

// ---- Yapılandırma ve giriş ----

interface RuntimeConfig { region: string; clientId: string; runtimeArn: string }
interface Tokens { access: string; refresh: string; expiresAt: number; user: string }

const TOKEN_KEY = 'tk.auth';
const RUN_KEY = 'tk.run';
let configPromise: Promise<RuntimeConfig> | null = null;

export function loadConfig(): Promise<RuntimeConfig> {
  configPromise ??= fetch('/config.json', { cache: 'no-store' }).then((r) => {
    if (!r.ok) throw new Error('AWS bağlantı ayarları yüklenemedi.');
    return r.json() as Promise<RuntimeConfig>;
  });
  return configPromise;
}

function readStore<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeStore(key: string, value: unknown): void {
  try {
    if (value === null) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, JSON.stringify(value));
  } catch { /* depolama kapalıysa oturum bellekte sürer */ }
}

let tokens: Tokens | null = readStore<Tokens>(TOKEN_KEY);
const authListeners = new Set<() => void>();

export const auth = {
  user: () => tokens?.user ?? null,
  subscribe(fn: () => void) {
    authListeners.add(fn);
    return () => authListeners.delete(fn);
  },
};

function setTokens(next: Tokens | null) {
  tokens = next;
  writeStore(TOKEN_KEY, next);
  if (!next) {
    writeStore(RUN_KEY, null);
    current = null;
  }
  authListeners.forEach((fn) => fn());
}

async function cognito(target: string, body: unknown): Promise<Record<string, any>> {
  const { region } = await loadConfig();
  const res = await fetch(`https://cognito-idp.${region}.amazonaws.com/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-amz-json-1.1', 'X-Amz-Target': 'AWSCognitoIdentityProviderService.' + target },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Giriş başarısız. Kullanıcı adını ve parolanı kontrol et.');
  return res.json();
}

export async function login(user: string, password: string): Promise<void> {
  const { clientId } = await loadConfig();
  const r = await cognito('InitiateAuth', { AuthFlow: 'USER_PASSWORD_AUTH', ClientId: clientId, AuthParameters: { USERNAME: user, PASSWORD: password } });
  const a = r.AuthenticationResult;
  if (!a) throw new Error('Hesap için kalıcı parola gerekli.');
  setTokens({ access: a.AccessToken, refresh: a.RefreshToken, expiresAt: Date.now() + a.ExpiresIn * 1000, user });
}

export async function logout(): Promise<void> {
  const t = tokens;
  setTokens(null);
  if (t) await cognito('GlobalSignOut', { AccessToken: t.access }).catch(() => undefined);
}

async function accessToken(): Promise<string> {
  if (!tokens) throw new Error('Oturum kapalı. Yeniden giriş yap.');
  if (tokens.expiresAt - Date.now() < 120_000) {
    const { clientId } = await loadConfig();
    try {
      const r = await cognito('InitiateAuth', { AuthFlow: 'REFRESH_TOKEN_AUTH', ClientId: clientId, AuthParameters: { REFRESH_TOKEN: tokens.refresh } });
      const a = r.AuthenticationResult;
      setTokens({ ...tokens, access: a.AccessToken, expiresAt: Date.now() + a.ExpiresIn * 1000 });
    } catch {
      setTokens(null);
      throw new Error('Oturum süresi doldu. Yeniden giriş yap.');
    }
  }
  return tokens!.access;
}

// ---- Runtime çağrısı ----

/** Backend `start` → `pending`… → `transfer` olaylarını akıtır; `transfer` gövdesini döndürür. */
async function invoke<T>(session: string, payload: Record<string, unknown>, signal?: AbortSignal): Promise<T> {
  const { runtimeArn } = await loadConfig();
  const res = await fetch(`/runtimes/${encodeURIComponent(runtimeArn)}/invocations?qualifier=DEFAULT`, {
    method: 'POST',
    signal,
    headers: {
      'Content-Type': 'application/json', Accept: 'text/event-stream',
      Authorization: 'Bearer ' + (await accessToken()),
      'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id': session,
    },
    body: JSON.stringify(payload),
  });
  if (res.status === 401) {
    setTokens(null);
    throw new Error('Oturum süresi doldu. Yeniden giriş yap.');
  }
  if (!res.ok || !res.body) throw new Error(`Agent çağrısı başarısız (HTTP ${res.status}).`);
  const out: { result?: T; error?: string } = {};
  await readEventStream(res.body, (data) => {
    let v: any;
    try { v = JSON.parse(data); } catch { return; }
    if (v?.error) out.error ??= String(v.error);
    else if (v?.type === 'transfer') {
      const { type: _t, ...rest } = v;
      out.result ??= rest as T;
    }
  });
  if (out.error) throw new Error(out.error);
  if (out.result === undefined) throw new Error('Yanıt akışı kesildi. Tekrar deneyebilirsiniz.');
  return out.result;
}

// ---- Backend veri biçimleri ----

export interface Finding {
  row: number; depot: string; product: string; domain: string;
  current: number; proposed: number; batch: number; median: number; mean: number; limit: number;
}

export interface BackendSummary {
  center: string; date: string; kind: 'amb' | 'cold' | 'ms';
  suggested: number; sent: number; cp: number | null;
  cut: Record<string, number>;
  limits: { ad: string; deger: number; limit: number; birim: string }[];
  alerts: { level: 'hata' | 'uyari' | 'bilgi'; name: string; evidence: string }[];
  applied: number; reviewed: number;
}

interface BackendState {
  stage: 'empty' | 'review' | 'ready';
  center?: string; kind?: 'amb' | 'cold' | 'ms'; date?: string;
  rows?: number; unknownDomain?: number;
  findings?: Finding[];
  summary?: BackendSummary;
  changes?: Record<string, number>;
}

export interface LiveRun {
  session: string;
  merkez: string;
  transferType: TransferTypeId;
  runDate: string;
  findings: Finding[];
  summary: BackendSummary | null;
  changes: Record<string, number>;
}

const KIND: Record<TransferTypeId, 'amb' | 'cold' | 'ms'> = { amb: 'amb', c4: 'cold', ms: 'ms' };
const TYPE_OF: Record<string, TransferTypeId> = { amb: 'amb', cold: 'c4', ms: 'ms' };
export const TYPE_LABEL: Record<TransferTypeId, string> = { amb: 'Ambient & Su', c4: '+4 (Soğuk)', ms: 'Meyve-Sebze' };

/** Tamamlanmış son koşu; ekran verisi (data/live.ts) buradan okunur. */
let current: LiveRun | null = null;
export const liveRun = () => (current?.summary ? current : null);
/** Sayfa yenilendikten sonra son koşu geri yüklenene kadar bekler (sayfalar RunProvider'dan önce veri ister). */
let doneRestoring = () => {};
const restoring = readStore(RUN_KEY) ? new Promise<void>((r) => { doneRestoring = r; }) : Promise.resolve();
export const restored = () => restoring;

function todayIstanbul(): string {
  return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Istanbul' }).format(new Date());
}

/** Bu koşunun bir dosyasını indirir (5 dakikalık imzalı bağlantı). */
export async function downloadRunFile(name: 'transfer.xlsx' | 'uyarilar.csv' | 'anomaliler.csv'): Promise<void> {
  const run = liveRun();
  if (!run) throw new Error('Önce bir koşu tamamlanmalı.');
  const { url } = await invoke<{ url: string }>(run.session, { action: 'download', name });
  window.location.assign(url);
}

export function fetchView<T>(): Promise<T> {
  const run = liveRun();
  if (!run) return Promise.reject(new Error('Henüz tamamlanmış bir koşu yok. Koşu ekranından Hesapla\'ya basın.'));
  return invoke<T>(run.session, { action: 'view' });
}

export function fetchDepot<T>(name: string): Promise<T> {
  const run = liveRun();
  if (!run) return Promise.reject(new Error('Henüz tamamlanmış bir koşu yok.'));
  return invoke<T>(run.session, { action: 'depot', name });
}

// ---- Onay kartları ----

const snap = (value: number, batch: number) => Math.floor(value / batch + 1e-9) * batch;

function approvalFor(f: Finding, index: number, total: number): ApprovalRequest {
  const left = total - index;
  return {
    approvalId: 'row-' + f.row,
    index, total,
    findingKey: String(f.row),
    depotId: f.depot,
    title: `${f.depot} · ${f.product}`,
    found: `Relex bu ürün için ${f.depot} deposuna ${nf(f.current)} adet öneriyor. Aynı ürünün diğer ${f.domain} depolardaki önerisi medyan ${nf(f.median)}, ortalama ${nf(f.mean, 1)}; aykırılık üst sınırı ${nf(f.limit, 1)}.`,
    proposal: `Öneriyi medyana göre sipariş katına (${nf(f.batch)}) çekmek: ${nf(f.current)} → ${nf(f.proposed)} (−${nf(f.current - f.proposed)} adet).`,
    howApplied: 'Yalnızca bu koşuda, kesim motorundan önce çalışma kopyasındaki Effective quantity alanına yazılır. Relex kaydı değişmez.',
    impact: `${f.depot} önerisi ${nf(f.current - f.proposed)} adet azalır; kesim motoru kalan öneriyle çalışır.`,
    question: `Medyana (${nf(f.proposed)}) çekeyim mi?`,
    metric: 'oneri',
    currentValue: f.current,
    proposedValue: f.proposed,
    reference: { group: f.domain, mean: f.mean, median: f.median },
    options: [
      { id: 'accept', label: `Evet, medyana çek (${nf(f.proposed)})` },
      ...(left > 0 ? [{ id: 'accept_all_remaining' as const, label: `Evet, kalan ${nf(left)} bulguyu da sormadan medyana çek` }] : []),
      { id: 'reject', label: `Hayır, olduğu gibi bırak (${nf(f.current)})` },
      ...(left > 0 ? [{ id: 'reject_all_remaining' as const, label: `Hayır, kalan ${nf(left)} bulguyu da olduğu gibi bırak` }] : []),
    ],
    instruction: { allowed: true, placeholder: 'ör. ortalamaya çek, 20 ile sınırla' },
  };
}

/** Serbest talimat: sayı → o sayıyla sınırla, "ortalama" / "medyan" → çek. Değer sipariş katına yuvarlanır. */
function interpret(text: string, f: Finding): { outcome: ApprovalOutcome; summary: string; note?: string } {
  const t = text.toLocaleLowerCase('tr-TR');
  const m = t.match(/\d{1,3}(?:\.\d{3})+(?!\d)|\d+(?:,\d+)?/);
  let value: number | null = null;
  let method: 'instruction' | 'mean' | 'median' = 'instruction';
  if (m) value = snap(Number(m[0].replace(/\./g, '').replace(',', '.')), f.batch);
  else if (t.includes('ortalama')) { value = Math.max(f.batch, snap(f.mean, f.batch)); method = 'mean'; }
  else if (t.includes('medyan')) { value = f.proposed; method = 'median'; }
  if (value === null) {
    return { outcome: { kind: 'unchanged', reason: 'instruction_note' }, summary: `Olduğu gibi bırakıldı (${nf(f.current)}) · not alındı`, note: text };
  }
  if (!(value >= 0 && value < f.current)) {
    return { outcome: { kind: 'unchanged', reason: 'instruction_not_lower' }, summary: `Değiştirilmedi: ${nf(value)}, mevcut önerinin (${nf(f.current)}) altında değil`, note: text };
  }
  const how = method === 'mean' ? 'Ortalamaya çekildi' : method === 'median' ? 'Medyana çekildi' : 'Talimatla sınırlandı';
  return { outcome: { kind: 'applied', value, method }, summary: `${how} (${nf(f.current)} → ${nf(value)})`, note: method === 'instruction' ? text : undefined };
}

// ---- İstemci ----

interface Active {
  run: LiveRun;
  decided: Map<number, ApprovalResolution>;
  emit: (e: RunEvent) => void;
  signal: AbortSignal;
}

export function createAgentCoreClient(): AgentClient {
  let active: Active | null = null;

  const fail = (a: Active, err: unknown) => {
    if (a.signal.aborted) return;
    a.emit({ type: 'run_failed', runId: a.run.session, error: { code: 'agent_error', message: err instanceof Error ? err.message : String(err) } });
  };

  const started = (a: Active) => a.emit({
    type: 'run_started',
    run: { runId: a.run.session, merkez: a.run.merkez, transferType: a.run.transferType, transferTypeLabel: TYPE_LABEL[a.run.transferType], runDate: a.run.runDate },
  });

  const askNext = (a: Active) => {
    const i = a.run.findings.findIndex((f) => !a.decided.has(f.row));
    if (i === -1) return void finish(a);
    a.emit({ type: 'approval_requested', runId: a.run.session, approval: approvalFor(a.run.findings[i], i + 1, a.run.findings.length) });
  };

  const completed = (a: Active, s: BackendSummary) => {
    const id = a.run.session;
    const count = (l: string) => s.alerts.filter((x) => x.level === l).length;
    const applied = Object.keys(a.run.changes).length;
    const cutPct = s.cut.adet ?? Object.values(s.cut)[0];
    a.emit({ type: 'step_completed', runId: id, step: 'cutting_engine', detail: `${nf(s.sent)} satır gönderiliyor` });
    a.emit({ type: 'step_started', runId: id, step: 'agent_checks' });
    a.emit({ type: 'check_progress', runId: id, check: 'run_integrity', status: 'done', detail: 'Merkez eşleşmesi ve All PL doğrulandı' });
    a.emit({ type: 'check_progress', runId: id, check: 'faulty_output', status: 'done', detail: `${count('hata')} kritik bulgu` });
    a.emit({ type: 'check_progress', runId: id, check: 'relex_anomalies', status: 'done', detail: `${nf(s.reviewed)} aykırı öneri incelendi` });
    a.emit({ type: 'check_progress', runId: id, check: 'depot_cuts', status: 'done', detail: cutPct !== undefined ? `Kısma oranı %${nf(cutPct, 1)}` : 'Tamamlandı' });
    a.emit({ type: 'step_completed', runId: id, step: 'agent_checks' });
    a.emit({ type: 'step_completed', runId: id, step: 'ready' });
    a.emit({
      type: 'run_completed', runId: id,
      summary: {
        headline: `${s.center} ${TYPE_LABEL[a.run.transferType]} koşusu hazır: ${nf(s.suggested)} öneri satırı, ${nf(s.sent)} satır gönderiliyor`
          + (cutPct !== undefined ? `, kısma oranı %${nf(cutPct, 1)}.` : '.') + ` ${count('hata')} kritik, ${count('uyari')} uyarı var.`,
        counts: { kritik: count('hata'), uyari: count('uyari'), bilgi: count('bilgi') },
        corrections: { applied, unchanged: s.reviewed - applied },
        finishedAt: new Date().toISOString(),
        resultsAvailable: true,
      },
    });
  };

  const finish = async (a: Active) => {
    const id = a.run.session;
    const applied = [...a.decided.values()].filter((r) => r.outcome.kind === 'applied').length;
    if (a.run.findings.length) {
      a.emit({ type: 'step_completed', runId: id, step: 'outlier_review', detail: `${applied} düzeltme, ${a.decided.size - applied} öneri olduğu gibi` });
    }
    a.emit({ type: 'step_started', runId: id, step: 'cutting_engine' });
    a.emit({ type: 'step_progress', runId: id, step: 'cutting_engine', detail: 'Motor çalışıyor; büyük merkezlerde birkaç dakika sürebilir' });
    const changes: Record<string, number> = {};
    for (const f of a.run.findings) {
      const r = a.decided.get(f.row);
      if (r?.outcome.kind === 'applied') changes[String(f.row)] = r.outcome.value;
    }
    try {
      const state = await invoke<BackendState>(id, { action: 'finish', changes }, a.signal);
      if (state.stage !== 'ready' || !state.summary) throw new Error('Motor sonucu alınamadı.');
      a.run.summary = state.summary;
      a.run.changes = state.changes ?? changes;
      current = a.run;
      completed(a, state.summary);
    } catch (err) {
      fail(a, err);
    }
  };

  const begin = (run: LiveRun, onEvent: (e: RunEvent) => void) => {
    const controller = new AbortController();
    const a: Active = { run, decided: new Map(), emit: (e) => !controller.signal.aborted && onEvent(e), signal: controller.signal };
    active = a;
    return { a, handle: { abort: () => controller.abort() } };
  };

  return {
    mode: 'agentcore',

    startRun(command, onEvent) {
      const run: LiveRun = {
        session: crypto.randomUUID(), merkez: command.merkez, transferType: command.transferType,
        runDate: todayIstanbul(), findings: [], summary: null, changes: {},
      };
      doneRestoring(); // yeni koşu, yarım kalan geri yüklemenin yerini alır
      writeStore(RUN_KEY, { session: run.session, merkez: run.merkez, transferType: run.transferType, runDate: run.runDate });
      const { a, handle } = begin(run, onEvent);
      started(a);
      a.emit({ type: 'step_started', runId: run.session, step: 'relex_read' });
      a.emit({ type: 'step_progress', runId: run.session, step: 'relex_read', detail: 'Google Sheets girdileri okunuyor ve öneriler karşılaştırılıyor…' });
      invoke<BackendState>(run.session, { action: 'prepare', center: run.merkez, kind: KIND[run.transferType], date: run.runDate }, a.signal)
        .then((state) => {
          run.findings = state.findings ?? [];
          a.emit({ type: 'step_completed', runId: run.session, step: 'relex_read',
            detail: `${nf(state.rows ?? 0)} öneri satırı okundu` + (state.unknownDomain ? ` · ${nf(state.unknownDomain)} satırda depo tipi eksik` : '') });
          a.emit({ type: 'step_started', runId: run.session, step: 'outlier_review' });
          if (!run.findings.length) {
            a.emit({ type: 'step_completed', runId: run.session, step: 'outlier_review', detail: 'Aykırı öneri bulunmadı' });
          } else {
            a.emit({ type: 'step_progress', runId: run.session, step: 'outlier_review', detail: `${nf(run.findings.length)} aykırı öneri buldum. Onayınız bekleniyor` });
          }
          askNext(a);
        })
        .catch((err) => fail(a, err));
      return handle;
    },

    /** Sayfa yenilenince bu sekmedeki son koşuyu backend'den geri yükler. */
    resume(onEvent) {
      const saved = readStore<Omit<LiveRun, 'findings' | 'summary' | 'changes'>>(RUN_KEY);
      if (!saved || !tokens) {
        doneRestoring();
        return null;
      }
      const run: LiveRun = { ...saved, findings: [], summary: null, changes: {} };
      const { a, handle } = begin(run, onEvent);
      invoke<BackendState>(run.session, { action: 'status' }, a.signal)
        .then((state) => {
          if (state.stage === 'empty') return;
          if (state.kind) run.transferType = TYPE_OF[state.kind];
          started(a);
          run.findings = state.findings ?? [];
          a.emit({ type: 'step_completed', runId: run.session, step: 'relex_read', detail: `${nf(state.rows ?? 0)} öneri satırı okundu` });
          a.emit({ type: 'step_started', runId: run.session, step: 'outlier_review' });
          if (state.stage === 'review') return askNext(a);
          run.summary = state.summary!;
          run.changes = state.changes ?? {};
          current = run;
          a.emit({ type: 'step_completed', runId: run.session, step: 'outlier_review', detail: `${nf(Object.keys(run.changes).length)} düzeltme uygulandı` });
          completed(a, run.summary);
        })
        .catch((err) => fail(a, err))
        .finally(() => { if (!a.signal.aborted) doneRestoring(); });
      return handle;
    },

    async respondToApproval(command) {
      const a = active;
      if (!a || a.run.session !== command.runId) throw new Error('Bu onay süren koşuya ait değil.');
      const pending = a.run.findings.filter((f) => !a.decided.has(f.row));
      const f = pending[0];
      if (!f || 'row-' + f.row !== command.approvalId) throw new Error('Bu öneri zaten yanıtlandı.');
      const r = command.response;
      const resolve = (x: Finding, outcome: ApprovalOutcome, summary: string, decidedBy: 'user' | 'bulk', note?: string) => {
        const resolution: ApprovalResolution = {
          approvalId: 'row-' + x.row, findingKey: String(x.row), title: `${x.depot} · ${x.product}`,
          originalValue: x.current, outcome, summary, decidedBy, note,
        };
        a.decided.set(x.row, resolution);
        a.emit({ type: 'approval_resolved', runId: a.run.session, resolution });
      };
      const accept = (x: Finding, by: 'user' | 'bulk') =>
        resolve(x, { kind: 'applied', value: x.proposed, method: 'median' }, `Medyana çekildi (${nf(x.current)} → ${nf(x.proposed)})`, by);
      const keep = (x: Finding, by: 'user' | 'bulk') =>
        resolve(x, { kind: 'unchanged', reason: 'rejected' }, `Olduğu gibi bırakıldı (${nf(x.current)})`, by);
      if (r.kind === 'accept') accept(f, 'user');
      else if (r.kind === 'reject') keep(f, 'user');
      else if (r.kind === 'accept_all_remaining') pending.forEach((x, i) => accept(x, i ? 'bulk' : 'user'));
      else if (r.kind === 'reject_all_remaining') pending.forEach((x, i) => keep(x, i ? 'bulk' : 'user'));
      else {
        const t = interpret(r.text, f);
        resolve(f, t.outcome, t.summary, 'user', t.note);
      }
      askNext(a);
    },

    ask(command, onEvent: (e: ChatEvent) => void) {
      const controller = new AbortController();
      const id = 'm-' + Date.now().toString(36);
      const run = liveRun();
      const emit = (e: ChatEvent) => !controller.signal.aborted && onEvent(e);
      if (!run || (command.runId && command.runId !== run.session)) {
        emit({ type: 'chat_failed', messageId: null, error: { code: 'no_run', message: 'Önce bir koşuyu tamamlayın; agent o koşunun verisiyle yanıtlar.' } });
        return { abort: () => controller.abort() };
      }
      emit({ type: 'chat_message_started', messageId: id });
      invoke<{ answer: string }>(run.session, { action: 'explain', question: command.question }, controller.signal)
        .then(({ answer }) => {
          emit({ type: 'chat_delta', messageId: id, delta: answer });
          emit({ type: 'chat_message_completed', messageId: id, links: [] });
        })
        .catch((err) => {
          if (!controller.signal.aborted) emit({ type: 'chat_failed', messageId: id, error: { code: 'agent_error', message: err instanceof Error ? err.message : String(err) } });
        });
      return { abort: () => controller.abort() };
    },
  };
}
