const el = id => document.getElementById(id);
const format = n => Number(n).toLocaleString("tr-TR", {maximumFractionDigits: 2});
const types = {amb: "Ambient & Su", cold: "Cold (+4)", ms: "Meyve & Sebze"};
let config, auth, session, owner, state, busy = false;
let decisions = new Map();
function status(message) { el("status").textContent = message; }
async function cognito(target, data) {
  const response = await fetch("https://cognito-idp." + config.region + ".amazonaws.com/", {
    method: "POST", headers: {"Content-Type": "application/x-amz-json-1.1",
      "X-Amz-Target": "AWSCognitoIdentityProviderService." + target}, body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error("Giriş başarısız. Kullanıcı adını ve parolanı kontrol et.");
  return response.json();
}
function eventData(frame) {
  const line = frame.split(/\r?\n/).find(line => line.startsWith("data:"));
  return line ? JSON.parse(line.slice(5).trim()) : null;
}
async function receive(response, expected) {
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  try {
    for (;;) {
      const {done, value} = await reader.read();
      buffer += value || "";
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop();
      if (done && buffer) frames.push(buffer);
      for (const frame of frames) {
        const data = eventData(frame);
        if (data?.error) throw new Error(data.error + (data.request ? " İstek: " + data.request : ""));
        if (data?.type === expected) return data;
      }
      if (done) throw new Error("Yanıt akışı kesildi. Aynı mesajı yeniden deneyebilirsin.");
    }
  } finally { reader.releaseLock(); }
}
async function invoke(payload, id, expected) {
  const path = "/runtimes/" + encodeURIComponent(config.runtimeArn) + "/invocations?qualifier=DEFAULT";
  const response = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json",
    Accept: "text/event-stream", Authorization: "Bearer " + auth.AccessToken,
    "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": id}, body: JSON.stringify(payload)});
  if (response.status === 401) {
    clearAccount();
    throw new Error("Oturum süresi doldu. Yeniden giriş yap.");
  }
  if (!response.ok) throw new Error("Ajan çağrısı başarısız (HTTP " + response.status + ").");
  return receive(response, expected);
}
function view(name) {
  if (!auth) name = "login";
  for (const id of ["login","run","results"]) el(id).hidden = id !== name;
  el("crumb").textContent = {login:"Giriş",run:"Koşu",results:"Sonuçlar"}[name];
  for (const button of document.querySelectorAll("[data-view]")) {
    if (button.dataset.view === name) button.setAttribute("aria-current","page");
    else button.removeAttribute("aria-current");
  }
}
function clearAccount() {
  auth = null; state = null; owner = null; session = null; decisions.clear();
  el("navigation").hidden = el("logout").hidden = true;
  el("answer").textContent = ""; el("question").value = ""; view("login");
}
async function work(message, fn) {
  if (busy) return;
  busy = true;
  const controls = [...document.querySelectorAll("button,input,select")].filter(x => !x.disabled);
  controls.forEach(x => x.disabled = true);
  status(message);
  try { await fn(); status(""); }
  catch (error) { status(error.message); }
  finally { controls.forEach(x => x.disabled = false); busy = false; }
}
const call = payload => invoke(payload, session, "transfer");
function element(tag, value, className) {
  const node = document.createElement(tag); node.textContent = value;
  if (className) node.className = className;
  return node;
}
function newRun() {
  session = crypto.randomUUID(); sessionStorage.setItem(owner, session);
  state = {stage:"empty"}; decisions.clear(); el("answer").textContent = ""; el("question").value = "";
  render(); view("run");
}
function render() {
  const ready = state.stage === "ready", review = state.stage === "review";
  el("setup").hidden = review;
  el("review").hidden = !review; el("output").hidden = !ready;
  el("metrics").replaceChildren(); el("findings").replaceChildren(); el("alerts").replaceChildren();
  el("context").textContent = ready ? [state.center,types[state.kind],state.date].join(" · ") : "Henüz tamamlanmış koşu yok.";
  if (review) {
    el("coverage").textContent = [state.center, types[state.kind], state.date, format(state.rows)+" satır",
      state.findings.length+" aykırı öneri", state.unknownDomain+" satırda depo tipi eksik"].join(" · ");
    drawFinding();
  }
  if (ready) {
    const s = state.summary;
    const metrics = [["Önerilen satır",format(s.suggested)],["Gönderilen satır",format(s.sent)],
      ["Satır C/P",s.cp == null ? "—" : "%"+format(s.cp)],["Onaylanan düzeltme",format(s.applied)]];
    for (const [unit,value] of Object.entries(s.cut)) metrics.push(["Kısma oranı · "+unit,"%"+format(value)]);
    for (const limit of s.limits) metrics.push([limit.ad+" kullanımı",format(limit.deger)+" / "+format(limit.limit)]);
    for (const [label,value] of metrics) {
      const card = element("div",label,"metric"); card.append(element("strong",value)); el("metrics").append(card);
    }
    const severity = {hata:"Kritik",uyari:"Uyarı",bilgi:"Bilgi"};
    for (const alert of [...s.alerts].sort((a,b) => Object.keys(severity).indexOf(a.level)-Object.keys(severity).indexOf(b.level))) {
      const card = element("div","","alert");
      card.append(element("strong",severity[alert.level]+" · "+alert.name),element("p",alert.evidence)); el("alerts").append(card);
    }
    if (!s.alerts.length) el("alerts").textContent = "Motor kontrollerinde uyarı bulunmadı.";
  }
}
function drawFinding() {
  const box = el("findings"); box.replaceChildren();
  const f = state.findings.find(x => !decisions.has(x.row));
  el("finish").hidden = Boolean(f); el("all").hidden = el("skip").hidden = !f;
  if (!f) { box.textContent = "İnceleme tamamlandı."; return; }
  const choose = value => { decisions.set(f.row,value); saveDecisions(); drawFinding(); };
  const input = element("input","");
  input.value = String(f.proposed); input.setAttribute("aria-label","Miktar veya talimat");
  input.placeholder = "Örn. ortalamaya çek veya 20 ile sınırla";
  const apply = element("button","Uygula");
  apply.onclick = () => {
    const instruction = input.value.trim().toLocaleLowerCase("tr-TR");
    const numeric = instruction.match(/^(\d+(?:[.,]\d+)?)(?: ile sınırla)?$/);
    let value;
    if (numeric) value = Number(numeric[1].replace(",","."));
    else if (["ortalamaya çek","ortalama"].includes(instruction)) value = Math.max(f.batch, Math.floor(f.mean/f.batch)*f.batch);
    else if (["medyana çek","medyan"].includes(instruction)) value = f.proposed;
    if (!Number.isFinite(value) || value >= f.current || Math.abs(value/f.batch-Math.round(value/f.batch)) > 1e-8) {
      status("Medyan, ortalama veya mevcut öneriden küçük bir sipariş katı girin."); return;
    }
    status(""); choose(value);
  };
  const reject = element("button","Olduğu gibi bırak"); reject.onclick = () => choose(null);
  const actions = element("div","","actions"); actions.append(apply,reject);
  box.append(element("strong",f.depot+" · "+f.product),element("p",
    "Öneri "+format(f.current)+" · "+f.domain+" medyanı "+format(f.median)+" · üst sınır "+format(f.limit)+" · sipariş katı "+format(f.batch)),
    element("p","Miktar veya talimat girin (ör. ortalamaya çek, 20 ile sınırla)."),input,actions,element("p","Karar yalnızca bu koşunun girdisine uygulanır."));
}
function saveDecisions() {
  sessionStorage.setItem(owner+"."+session,JSON.stringify([...decisions]));
}
el("skip").onclick = () => {
  for (const f of state.findings) if (!decisions.has(f.row)) decisions.set(f.row,null);
  saveDecisions(); drawFinding();
};
el("all").onclick = () => {
  for (const f of state.findings) if (!decisions.has(f.row)) decisions.set(f.row,f.proposed);
  saveDecisions(); drawFinding();
};
el("restart").onclick = newRun;
el("center").onchange = () => {
  const unavailable = el("center").value === "Diyarbakır";
  el("kind").querySelector('[value="ms"]').disabled = unavailable;
  if (unavailable && el("kind").value === "ms") el("kind").value = "amb";
};
el("auth").onsubmit = e => {
  e.preventDefault();
  work("Giriş yapılıyor…",async () => {
    const name = el("username").value.trim();
    const response = await cognito("InitiateAuth",{AuthFlow:"USER_PASSWORD_AUTH",ClientId:config.clientId,
      AuthParameters:{USERNAME:name,PASSWORD:el("password").value}});
    if (!response.AuthenticationResult) throw new Error("Hesap için kalıcı parola gerekli.");
    auth = response.AuthenticationResult; el("password").value = "";
    owner = "rota.run."+name;
    session = sessionStorage.getItem(owner) || crypto.randomUUID(); sessionStorage.setItem(owner,session);
    state = {stage:"empty"}; el("navigation").hidden = el("logout").hidden = false; render(); view("run");
    state = await call({action:"status"});
    decisions = new Map(JSON.parse(sessionStorage.getItem(owner+"."+session) || "[]"));
    render(); view(state.stage === "ready" ? "results":"run");
  });
};
el("logout").onclick = () => work("Oturum kapatılıyor…",async () => {
  try { await cognito("GlobalSignOut",{AccessToken:auth.AccessToken}); } finally { clearAccount(); }
});
for (const button of document.querySelectorAll("[data-view]")) button.onclick = () => view(button.dataset.view);
el("setup").onsubmit = e => {
  e.preventDefault();
  work("Google Sheets girdileri okunuyor ve öneriler karşılaştırılıyor…",async () => {
    if (state.stage === "ready") newRun();
    state = await call({action:"prepare",date:el("date").value,center:el("center").value,kind:el("kind").value});
    decisions.clear(); render();
  });
};
el("finish").onclick = () => work("Kesim motoru çalışıyor. Çıktılar ve kontroller hazırlanıyor…",async () => {
  const changes = Object.fromEntries([...decisions].filter(([,v]) => v !== null));
  state = await call({action:"finish",changes}); render(); view("results");
});
for (const button of document.querySelectorAll("[data-file]")) button.onclick = () => work("Dosya hazırlanıyor…",async () => {
  const result = await call({action:"download",name:button.dataset.file}); location.assign(result.url);
});
el("ask").onsubmit = e => {
  e.preventDefault(); work("Transfer Agent koşu kanıtlarını inceliyor…",async () => {
    const response = await call({action:"explain",question:el("question").value}); el("answer").textContent = response.answer;
  });
};
el("date").value = new Intl.DateTimeFormat("sv-SE",{timeZone:"Europe/Istanbul"}).format(new Date());
fetch("/config.json",{cache:"no-store"}).then(async response => {
  if (!response.ok) throw new Error();
  config = await response.json(); el("submitLogin").disabled = false;
}).catch(() => status("AWS bağlantı ayarları yüklenemedi."));
