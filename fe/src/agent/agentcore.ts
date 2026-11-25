/**
 * AgentCore Runtime istemcisi. Backend'in beş eylemiyle konuşur (agent/main.py):
 * prepare → (kullanıcı kararları tarayıcıda) → finish, status, download, explain, view, depot.
 * Optimizasyon kimliği Runtime oturum UUID'sidir; her yeni optimizasyon yeni bir oturum açar.
 */
import { forecastName, nf } from '../lib/format';
import type { AgentClient } from './client';
import { readEventStream } from './sse';
import type {
  ApprovalOption, ApprovalOutcome, ApprovalRequest, ChatEvent, RunEvent, TransferTypeId,
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

// ---- Backend veri biçimleri (agent/transfer_runs.py, agent/transfer/preflight.py) ----

/** Bir bulgunun önerdiği tek satır değişikliği (depo × ürün). */
export interface Edit {
  depotCode: string; productCode: string; depot: string; product: string; domain: string;
  current: number; proposed: number; batch: number; unit: string; reason: string;
  median?: number; evidence: string;
}

/** İnceleme bulgusu. `uyari` bulguları karar ister; `edits` varsa miktar önerisidir. `hata` optimizasyonu durdurur. */
export interface Check {
  id: string; phase: string; level: 'hata' | 'uyari' | 'bilgi';
  title: string; evidence: string; source: string; edits?: Edit[];
}

export interface BackendSummary {
  center: string; date: string; kind: 'amb' | 'cold' | 'ms';
  suggested: number; sent: number; cp: number | null;
  cut: Record<string, number>;
  limits: { ad: string; deger: number; limit: number; birim: string }[];
  alerts: { level: 'hata' | 'uyari' | 'bilgi'; name: string; evidence: string }[];
  applied: number; reviewed: number;
}

interface Page { checks: Check[]; remaining: number; offset: number }

interface BackendState extends Partial<Page> {
  stage: 'empty' | 'review' | 'blocked' | 'ready';
  center?: string; kind?: 'amb' | 'cold' | 'ms'; date?: string;
  rows?: number; legacy?: boolean;
  summary?: BackendSummary;
}

export interface LiveRun {
  session: string;
  merkez: string;
  transferType: TransferTypeId;
  runDate: string;
  /** Şimdiye kadar getirilen bulgular (sayfa sayfa). */
  checks: Check[];
  /** Bulgu kimliği → satır başına yeni miktar (null: olduğu gibi). Yalnız bu tarayıcı oturumunda bilinir. */
  decisions: Record<string, (number | null)[] | null>;
  summary: BackendSummary | null;
}

const KIND: Record<TransferTypeId, 'amb' | 'cold' | 'ms'> = { amb: 'amb', c4: 'cold', ms: 'ms' };
const TYPE_OF: Record<string, TransferTypeId> = { amb: 'amb', cold: 'c4', ms: 'ms' };
export const TYPE_LABEL: Record<TransferTypeId, string> = { amb: 'Ambient & Su', c4: '+4 (Soğuk)', ms: 'Meyve-Sebze' };

/** Tamamlanmış son optimizasyon; ekran verisi (data/live.ts) buradan okunur. */
let current: LiveRun | null = null;
export const liveRun = () => (current?.summary ? current : null);
/** Sayfa yenilendikten sonra son optimizasyon geri yüklenene kadar bekler (sayfalar RunProvider'dan önce veri ister). */
let doneRestoring = () => {};
const restoring = readStore(RUN_KEY) ? new Promise<void>((r) => { doneRestoring = r; }) : Promise.resolve();
export const restored = () => restoring;

function todayIstanbul(): string {
  return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Istanbul' }).format(new Date());
}

export type RunFile = 'transfer.xlsx' | 'transfer.parquet' | 'uyarilar.csv' | 'anomaliler.csv';

/** Bu optimizasyonun bir dosyasını indirir (5 dakikalık imzalı bağlantı). */
export async function downloadRunFile(name: RunFile): Promise<void> {
  const run = liveRun();
  if (!run) throw new Error('Önce bir optimizasyon tamamlanmalı.');
  const { url } = await invoke<{ url: string }>(run.session, { action: 'download', name });
  window.location.assign(url);
}

export function fetchView<T>(): Promise<T> {
  const run = liveRun();
  if (!run) return Promise.reject(new Error('Henüz tamamlanmış bir optimizasyon yok. Optimizasyon ekranından Hesapla\'ya basın.'));
  return invoke<T>(run.session, { action: 'view' });
}

export function fetchDepot<T>(name: string): Promise<T> {
  const run = liveRun();
  if (!run) return Promise.reject(new Error('Henüz tamamlanmış bir optimizasyon yok.'));
  return invoke<T>(run.session, { action: 'depot', name });
}

// ---- Onay kartları ----

const OFFICIAL = 'official';
const snap = (value: number, batch: number) => Math.floor(value / batch + 1e-9) * batch;
const needsDecision = (c: Check) => c.level === 'uyari';
const qty = (n: number, unit: string) => `${nf(n)} ${unit}`;

function editLines(edits: Edit[]): string {
  const shown = edits.slice(0, 4).map((e) => `${e.depot}: ${qty(e.current, e.unit)} → ${qty(e.proposed, e.unit)}`);
  return shown.join(' · ') + (edits.length > 4 ? ` · +${edits.length - 4} depo` : '');
}

function approvalFor(c: Check, index: number, total: number, more: number): ApprovalRequest {
  const edits = c.edits ?? [];
  const left = total - index;
  // Sonraki sayfalardaki bulgu sayısı (bilgi dahil) henüz bilinmiyor; sayıya katılmaz, yalnız belirtilir.
  const tail = more > 0 ? ' (sonraki sayfalar dahil)' : '';
  const bulk = (accept: boolean): ApprovalOption[] => left > 0 || more > 0
    ? [{ id: accept ? 'accept_all_remaining' : 'reject_all_remaining',
        label: accept ? `Evet, kalan bulgularda da önerileri uygula${tail}` : `Kalan bulguları olduğu gibi bırak${tail}` }]
    : [];
  const base = {
    approvalId: 'check-' + c.id, index, total, findingKey: c.id,
    depotId: edits[0]?.depot ?? '', title: forecastName(c.title), metric: 'oneri' as const,
  };
  if (!edits.length) {
    return {
      ...base,
      found: forecastName(c.evidence),
      proposal: 'Miktar değişikliği önerilmiyor; girdiyi bilerek devam etmeniz gerekiyor.',
      howApplied: `Kaynak: ${forecastName(c.source)}. Girdi düzeltilecekse kaynağında düzeltip optimizasyonu yeniden başlatın.`,
      impact: 'Devam ederseniz motor bu girdiyle çalışır.',
      question: 'Bu uyarıyla devam edeyim mi?',
      currentValue: 0, proposedValue: 0, reference: { group: '', mean: 0, median: 0 },
      options: [{ id: 'accept', label: 'Gördüm, devam et' }, ...bulk(false)],
      instruction: { allowed: false, placeholder: '' },
    };
  }
  const now = edits.reduce((s, e) => s + e.current, 0);
  const next = edits.reduce((s, e) => s + e.proposed, 0);
  const unit = edits[0].unit;
  const first = edits[0];
  return {
    ...base,
    found: forecastName(edits.length === 1 ? first.evidence : `${c.evidence} ${first.depot}: ${first.evidence}`),
    proposal: `${edits.length === 1 ? 'Öneriyi' : `${nf(edits.length)} depoda öneriyi`} düşürmek: ${editLines(edits)}.`,
    howApplied: 'Yalnızca bu optimizasyonda, motor çalışmadan önce girdi kopyasına yazılır ve revize kaydına girer. Forecast kaydı değişmez.',
    impact: `Toplam öneri ${qty(now, unit)} → ${qty(next, unit)} (−${qty(now - next, unit)}).`,
    question: edits.length === 1 ? `${nf(first.proposed)} ${unit} olarak uygulayayım mı?` : 'Önerilen miktarları uygulayayım mı?',
    currentValue: now, proposedValue: next,
    reference: { group: first.domain, mean: 0, median: first.median ?? 0 },
    options: [
      { id: 'accept', label: 'Evet, önerilen miktarları uygula' }, ...bulk(true),
      { id: 'reject', label: 'Hayır, olduğu gibi bırak' }, ...bulk(false),
    ],
    instruction: { allowed: true, placeholder: 'ör. 20 ile sınırla, medyana çek' },
  };
}

function officialApproval(run: LiveRun, leaveRemaining: number): ApprovalRequest {
  const applied = Object.values(run.decisions).filter((d) => d?.some((v) => v !== null));
  const lines = applied.reduce((s, d) => s + (d?.filter((v) => v !== null).length ?? 0), 0);
  return {
    approvalId: OFFICIAL, index: 1, total: 1, findingKey: OFFICIAL, depotId: '',
    title: 'Resmi optimizasyonu çalıştır',
    found: `${nf(Object.keys(run.decisions).length)} bulguya karar verdiniz; ${nf(lines)} satırda miktar değişecek.`
      + (leaveRemaining ? ` Gösterilmeyen ${nf(leaveRemaining)} bulgu olduğu gibi bırakılacak.` : ''),
    proposal: 'Kesim motoru onaylanan miktarlarla resmi çıktıyı üretir.',
    howApplied: 'Değişiklikler yalnız bu optimizasyonun girdi kopyasına ve revize kaydına yazılır.',
    impact: 'Sonuçlar, transfer dosyası ve uyarılar hazır olur.',
    question: 'Resmi optimizasyonu çalıştırayım mı?',
    metric: 'oneri', currentValue: 0, proposedValue: 0, reference: { group: '', mean: 0, median: 0 },
    options: [{ id: 'accept', label: 'Evet, resmi optimizasyonu çalıştır' }, { id: 'reject', label: 'Hayır, kararlarımı baştan gözden geçir' }],
    instruction: { allowed: false, placeholder: '' },
  };
}

/** Serbest talimat: sayı → her satırı o sayıyla sınırla; "medyan" → önerilen miktar. Sipariş katına yuvarlanır. */
function interpret(text: string, edits: Edit[]): (number | null)[] | null {
  const t = text.toLocaleLowerCase('tr-TR');
  const m = t.match(/\d{1,3}(?:\.\d{3})+(?!\d)|\d+(?:,\d+)?/);
  if (m) {
    const cap = Number(m[0].replace(/\./g, '').replace(',', '.'));
    const values = edits.map((e) => { const v = snap(Math.min(cap, e.current), e.batch); return v < e.current ? v : null; });
    return values.some((v) => v !== null) ? values : null;
  }
  if (t.includes('medyan') || t.includes('öneri')) return edits.map((e) => e.proposed);
  return null;
}

// ---- İstemci ----

interface Active {
  run: LiveRun;
  emit: (e: RunEvent) => void;
  signal: AbortSignal;
  remaining: number;
  offset: number;
  awaitingOfficial: boolean;
  leaveRemaining: boolean;
}

export function createAgentCoreClient(): AgentClient {
  let active: Active | null = null;
  const chat: { question: string; answer: string }[] = [];

  const fail = (a: Active, err: unknown) => {
    if (a.signal.aborted) return;
    a.emit({ type: 'run_failed', runId: a.run.session, error: { code: 'agent_error', message: err instanceof Error ? err.message : String(err) } });
  };

  const started = (a: Active) => a.emit({
    type: 'run_started',
    run: { runId: a.run.session, merkez: a.run.merkez, transferType: a.run.transferType, transferTypeLabel: TYPE_LABEL[a.run.transferType], runDate: a.run.runDate },
  });

  const pendingChecks = (a: Active) => a.run.checks.filter((c) => needsDecision(c) && !(c.id in a.run.decisions));

  /** Sonraki sayfayı getirir; bulguları listeye ekler. */
  const nextPage = async (a: Active) => {
    const page = await invoke<Page>(a.run.session, { action: 'review_page', offset: a.offset + 10 }, a.signal);
    a.run.checks.push(...page.checks);
    a.offset = page.offset;
    a.remaining = page.remaining;
  };

  const askNext = async (a: Active) => {
    try {
      while (!pendingChecks(a).length && a.remaining > 0 && !a.leaveRemaining) await nextPage(a);
    } catch (err) {
      return fail(a, err);
    }
    const asked = a.run.checks.filter(needsDecision);
    const pending = pendingChecks(a);
    if (!pending.length) {
      a.awaitingOfficial = true;
      a.emit({ type: 'approval_requested', runId: a.run.session, approval: officialApproval(a.run, a.leaveRemaining ? a.remaining : 0) });
      return;
    }
    const c = pending[0];
    a.emit({ type: 'approval_requested', runId: a.run.session,
      approval: approvalFor(c, asked.indexOf(c) + 1, asked.length, a.remaining) });
  };

  const completed = (a: Active, s: BackendSummary) => {
    const id = a.run.session;
    const count = (l: string) => s.alerts.filter((x) => x.level === l).length;
    const cutPct = s.cut.adet ?? Object.values(s.cut)[0];
    a.emit({ type: 'step_completed', runId: id, step: 'cutting_engine', detail: `${nf(s.sent)} satır gönderiliyor` });
    a.emit({ type: 'step_started', runId: id, step: 'agent_checks' });
    a.emit({ type: 'check_progress', runId: id, check: 'run_integrity', status: 'done', detail: 'Merkez eşleşmesi ve All PL doğrulandı' });
    a.emit({ type: 'check_progress', runId: id, check: 'faulty_output', status: 'done', detail: `${count('hata')} kritik bulgu` });
    a.emit({ type: 'check_progress', runId: id, check: 'relex_anomalies', status: 'done', detail: `${nf(s.reviewed)} bulgu incelendi, ${nf(s.applied)} satır revize edildi` });
    a.emit({ type: 'check_progress', runId: id, check: 'depot_cuts', status: 'done', detail: cutPct !== undefined ? `Kısma oranı %${nf(cutPct, 1)}` : 'Tamamlandı' });
    a.emit({ type: 'step_completed', runId: id, step: 'agent_checks' });
    a.emit({ type: 'step_completed', runId: id, step: 'ready' });
    a.emit({
      type: 'run_completed', runId: id,
      summary: {
        headline: `${s.center} ${TYPE_LABEL[a.run.transferType]} optimizasyonu hazır: ${nf(s.suggested)} öneri satırı, ${nf(s.sent)} satır gönderiliyor`
          + (cutPct !== undefined ? `, kısma oranı %${nf(cutPct, 1)}.` : '.') + ` ${count('hata')} kritik, ${count('uyari')} uyarı var.`,
        counts: { kritik: count('hata'), uyari: count('uyari'), bilgi: count('bilgi') },
        corrections: { applied: s.applied, unchanged: Math.max(0, s.reviewed - s.applied) },
        finishedAt: new Date().toISOString(),
        resultsAvailable: true,
      },
    });
  };

  const finish = async (a: Active) => {
    const id = a.run.session;
    a.emit({ type: 'step_completed', runId: id, step: 'outlier_review',
      detail: `${nf(Object.keys(a.run.decisions).length)} karar · resmi optimizasyon onaylandı` });
    a.emit({ type: 'step_started', runId: id, step: 'cutting_engine' });
    a.emit({ type: 'step_progress', runId: id, step: 'cutting_engine', detail: 'Motor çalışıyor; büyük merkezlerde birkaç dakika sürebilir' });
    try {
      const state = await invoke<BackendState>(id, {
        action: 'finish', approveOfficial: true, decisions: a.run.decisions, offset: a.offset,
        leaveRemaining: a.remaining > 0,
      }, a.signal);
      if (state.stage !== 'ready' || !state.summary) throw new Error('Motor sonucu alınamadı.');
      a.run.summary = state.summary;
      current = a.run;
      completed(a, state.summary);
    } catch (err) {
      fail(a, err);
    }
  };

  /** prepare/status yanıtındaki inceleme durumundan devam eder. */
  const review = (a: Active, state: BackendState) => {
    const id = a.run.session;
    const checks = state.checks ?? [];
    a.run.checks = [...checks];
    a.offset = state.offset ?? 0;
    a.remaining = state.remaining ?? 0;
    const errors = checks.filter((c) => c.level === 'hata');
    // Girdide seçilen merkezin depoları yoksa bu bir hata değil, "veri yok" durumudur.
    const other = errors.length === 1 && /merkezi uyuşmuyor/i.test(errors[0].title)
      ? errors[0].evidence.match(/tespit edilen merkez ([^.]+)\./)?.[1] : undefined;
    if (other !== undefined) {
      a.emit({ type: 'step_completed', runId: id, step: 'relex_read', detail: `${a.run.merkez} için depo verisi yok` });
      a.emit({ type: 'run_failed', runId: id, error: { code: 'no_data',
        message: `${a.run.merkez} için depo verisi bulunamadı. Forecast girdisinde ${other === 'belirsiz' ? 'tanınan bir merkez yok' : `yalnız ${other} depoları var`}; o merkezi seçerek optimizasyonu başlatabilirsiniz.` } });
      return;
    }
    if (state.stage === 'blocked' || errors.length) {
      const why = state.legacy ? 'Bu inceleme eski sürümle başlatılmış; yeni optimizasyon başlatın.'
        : errors.map((c) => `${forecastName(c.title)}: ${forecastName(c.evidence)}`).join(' · ');
      a.emit({ type: 'step_completed', runId: id, step: 'relex_read', detail: 'Kritik girdi hatası; motor çalıştırılmadı' });
      return fail(a, new Error('Kritik girdi bulgusu var; motor çalıştırılmadı. ' + why + ' · Merkez seçimini ve iş tarihini kontrol edin; girdi eskiyse Google Sheet güncellendikten sonra yeniden deneyin.'));
    }
    const total = checks.length + a.remaining;
    const info = checks.filter((c) => c.level === 'bilgi').length;
    a.emit({ type: 'step_completed', runId: id, step: 'relex_read',
      detail: `${nf(state.rows ?? 0)} öneri satırı okundu · ${nf(total)} bulgu` + (info && !a.remaining ? ` (${nf(info)} bilgi)` : '') });
    a.emit({ type: 'step_started', runId: id, step: 'outlier_review' });
    a.emit({ type: 'step_progress', runId: id, step: 'outlier_review', detail: 'Uyarılar için kararınız bekleniyor' });
    void askNext(a);
  };

  const begin = (run: LiveRun, onEvent: (e: RunEvent) => void) => {
    const controller = new AbortController();
    const a: Active = { run, emit: (e) => !controller.signal.aborted && onEvent(e), signal: controller.signal,
      remaining: 0, offset: 0, awaitingOfficial: false, leaveRemaining: false };
    active = a;
    return { a, handle: { abort: () => controller.abort() } };
  };

  const newRun = (session: string, merkez: string, transferType: TransferTypeId, runDate: string): LiveRun =>
    ({ session, merkez, transferType, runDate, checks: [], decisions: {}, summary: null });

  return {
    mode: 'agentcore',

    startRun(command, onEvent) {
      doneRestoring(); // yeni optimizasyon, yarım kalan geri yüklemenin yerini alır
      const run = newRun(crypto.randomUUID(), command.merkez, command.transferType, command.date || todayIstanbul());
      writeStore(RUN_KEY, { session: run.session, merkez: run.merkez, transferType: run.transferType, runDate: run.runDate });
      chat.length = 0;
      const { a, handle } = begin(run, onEvent);
      started(a);
      a.emit({ type: 'step_started', runId: run.session, step: 'relex_read' });
      a.emit({ type: 'step_progress', runId: run.session, step: 'relex_read', detail: 'Girdiler okunuyor, kontroller ve taslak motor çalışıyor…' });
      invoke<BackendState>(run.session, { action: 'prepare', center: run.merkez, kind: KIND[run.transferType], date: run.runDate }, a.signal)
        .then((state) => review(a, state))
        .catch((err) => fail(a, err));
      return handle;
    },

    /** Sayfa yenilenince bu sekmedeki son optimizasyonu backend'den geri yükler. */
    resume(onEvent) {
      const saved = readStore<{ session: string; merkez: string; transferType: TransferTypeId; runDate: string }>(RUN_KEY);
      if (!saved || !tokens) {
        doneRestoring();
        return null;
      }
      const run = newRun(saved.session, saved.merkez, saved.transferType, saved.runDate);
      const { a, handle } = begin(run, onEvent);
      invoke<BackendState>(run.session, { action: 'status' }, a.signal)
        .then((state) => {
          if (state.stage === 'empty') return;
          if (state.kind) run.transferType = TYPE_OF[state.kind];
          started(a);
          if (state.stage !== 'ready') return review(a, state);
          run.summary = state.summary!;
          current = run;
          a.emit({ type: 'step_completed', runId: run.session, step: 'relex_read', detail: `${nf(state.rows ?? 0)} öneri satırı okundu` });
          a.emit({ type: 'step_completed', runId: run.session, step: 'outlier_review', detail: `${nf(run.summary.applied)} satır revize edildi` });
          completed(a, run.summary);
        })
        .catch((err) => fail(a, err))
        .finally(() => { if (!a.signal.aborted) doneRestoring(); });
      return handle;
    },

    async respondToApproval(command) {
      const a = active;
      if (!a || a.run.session !== command.runId) throw new Error('Bu onay süren optimizasyona ait değil.');
      const r = command.response;
      if (a.awaitingOfficial) {
        if (command.approvalId !== OFFICIAL) throw new Error('Bu öneri zaten yanıtlandı.');
        a.awaitingOfficial = false;
        if (r.kind === 'accept') {
          a.emit({ type: 'approval_resolved', runId: a.run.session, resolution: {
            approvalId: OFFICIAL, findingKey: OFFICIAL, title: 'Resmi optimizasyon', originalValue: 0,
            outcome: { kind: 'unchanged', reason: 'rejected' }, summary: 'Onaylandı', decidedBy: 'user' } });
          return void finish(a);
        }
        a.run.decisions = {};
        a.leaveRemaining = false;
        a.emit({ type: 'approval_resolved', runId: a.run.session, resolution: {
          approvalId: OFFICIAL, findingKey: OFFICIAL, title: 'Resmi optimizasyon', originalValue: 0,
          outcome: { kind: 'unchanged', reason: 'rejected' }, summary: 'Kararlar sıfırlandı', decidedBy: 'user' } });
        return void askNext(a);
      }
      const pending = pendingChecks(a);
      const c = pending[0];
      if (!c || 'check-' + c.id !== command.approvalId) throw new Error('Bu öneri zaten yanıtlandı.');
      const decide = (x: Check, values: (number | null)[] | null, by: 'user' | 'bulk', note?: string) => {
        a.run.decisions[x.id] = values;
        const edits = x.edits ?? [];
        const changed = values ? values.filter((v) => v !== null).length : 0;
        const outcome: ApprovalOutcome = changed
          ? { kind: 'applied', value: values!.reduce<number>((s, v, i) => s + (v ?? edits[i].current), 0), method: note ? 'instruction' : 'median' }
          : { kind: 'unchanged', reason: note ? 'instruction_note' : 'rejected' };
        const summary = !edits.length ? 'Görüldü, devam edildi'
          : changed ? `${nf(changed)} satır revize edildi` + (edits.length === 1 && values![0] !== null ? ` (${nf(edits[0].current)} → ${nf(values![0]!)})` : '')
          : 'Olduğu gibi bırakıldı';
        a.emit({ type: 'approval_resolved', runId: a.run.session, resolution: {
          approvalId: 'check-' + x.id, findingKey: x.id, title: forecastName(x.title),
          originalValue: edits.reduce((s, e) => s + e.current, 0), outcome, summary, decidedBy: by, note } });
      };
      const proposed = (x: Check) => (x.edits?.length ? x.edits.map((e) => e.proposed) : null);
      try {
        if (r.kind === 'accept') decide(c, proposed(c), 'user');
        else if (r.kind === 'reject') decide(c, null, 'user');
        else if (r.kind === 'reject_all_remaining') {
          pending.forEach((x, i) => decide(x, null, i ? 'bulk' : 'user'));
          a.leaveRemaining = a.remaining > 0;
        } else if (r.kind === 'accept_all_remaining') {
          while (a.remaining > 0) await nextPage(a);
          pendingChecks(a).forEach((x, i) => decide(x, proposed(x), i ? 'bulk' : 'user'));
        } else {
          const values = interpret(r.text, c.edits ?? []);
          decide(c, values, 'user', values ? r.text : `Talimat anlaşılamadı, değişiklik yapılmadı: ${r.text}`);
        }
      } catch (err) {
        return fail(a, err);
      }
      void askNext(a);
    },

    ask(command, onEvent: (e: ChatEvent) => void) {
      const controller = new AbortController();
      const id = 'm-' + Date.now().toString(36);
      const run = liveRun();
      const emit = (e: ChatEvent) => !controller.signal.aborted && onEvent(e);
      if (!run || (command.runId && command.runId !== run.session)) {
        emit({ type: 'chat_failed', messageId: null, error: { code: 'no_run', message: 'Önce bir optimizasyonu tamamlayın; agent o optimizasyonun verisiyle yanıtlar.' } });
        return { abort: () => controller.abort() };
      }
      emit({ type: 'chat_message_started', messageId: id });
      invoke<{ answer: string }>(run.session, { action: 'explain', question: command.question, conversation: chat.slice(-3) }, controller.signal)
        .then(({ answer }) => {
          chat.push({ question: command.question.slice(0, 2000), answer: answer.slice(0, 5000) });
          emit({ type: 'chat_delta', messageId: id, delta: forecastName(answer) });
          emit({ type: 'chat_message_completed', messageId: id, links: [] });
        })
        .catch((err) => {
          if (!controller.signal.aborted) emit({ type: 'chat_failed', messageId: id, error: { code: 'agent_error', message: err instanceof Error ? err.message : String(err) } });
        });
      return { abort: () => controller.abort() };
    },
  };
}
