"""HTTP API plus a one-page demo dashboard.

  uvicorn serp.api:app --port 8000
  GET /search?q=...&mode=auto&aio=true&start=0&tbs=qdr:w&no_cache=false
  GET /stats
  GET /          (dashboard)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from .engine import MODES, SerpEngine
from .proxies import DIRECT

engine: SerpEngine | None = None


@asynccontextmanager
async def lifespan(_app):
    global engine
    engine = SerpEngine()
    yield
    engine.close()


app = FastAPI(title="SERP Engine", lifespan=lifespan)


@app.get("/search")
def search(
    q: str = Query(..., min_length=1),
    mode: str = "auto",
    aio: bool = False,
    start: int = Query(0, ge=0, le=300),
    tbs: str = "",
    no_cache: bool = False,
):
    if mode not in MODES:
        raise HTTPException(400, f"mode must be one of {MODES}")
    return engine.search(q, mode=mode, ai_overview=aio, start=start, tbs=tbs, no_cache=no_cache).to_dict()


@app.get("/stats")
def stats():
    return {
        **engine.stats.summary(),
        "blocked_for_s": engine.proxies.seconds_until_free(),
        "requests_last_hour": engine.stats.requests_since(DIRECT, 3600) if not engine.cfg.proxies else None,
        "max_per_hour": engine.cfg.max_per_hour,
    }


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return DASHBOARD


DASHBOARD = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SERP Engine</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#f5f6f9;--surface:#fff;--surface-2:#f0f2f6;--fg:#0f172a;--fg-2:#334155;--muted:#64748b;--line:#e2e6ed;
  --accent:#4f46e5;--accent-soft:rgba(79,70,229,.1);--accent-2:#0891b2;
  --good:#059669;--good-soft:rgba(5,150,105,.12);--warn:#b45309;--warn-soft:rgba(217,119,6,.13);--bad:#dc2626;--bad-soft:rgba(220,38,38,.1);
  --shadow:0 1px 2px rgba(15,23,42,.04),0 4px 16px rgba(15,23,42,.05);--shadow-lg:0 2px 4px rgba(15,23,42,.05),0 12px 32px rgba(15,23,42,.1);
  --glow:rgba(99,102,241,.16);--glow-2:rgba(6,182,212,.12);--skel:#e8ebf1;--skel-hi:#f4f6f9;
  --mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace;--ease:cubic-bezier(.2,.8,.2,1);
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0a0c11;--surface:#12151d;--surface-2:#191d27;--fg:#e7eaf0;--fg-2:#c3c9d5;--muted:#8a93a6;--line:#242a37;
  --accent:#818cf8;--accent-soft:rgba(129,140,248,.14);--accent-2:#22d3ee;
  --good:#34d399;--good-soft:rgba(52,211,153,.13);--warn:#fbbf24;--warn-soft:rgba(251,191,36,.13);--bad:#f87171;--bad-soft:rgba(248,113,113,.13);
  --shadow:0 1px 2px rgba(0,0,0,.3),0 4px 16px rgba(0,0,0,.25);--shadow-lg:0 2px 4px rgba(0,0,0,.3),0 16px 40px rgba(0,0,0,.45);
  --glow:rgba(99,102,241,.22);--glow-2:rgba(34,211,238,.1);--skel:#1b1f2a;--skel-hi:#252a37;
}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 Inter,system-ui,-apple-system,sans-serif;-webkit-font-smoothing:antialiased;min-height:100vh}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(700px 380px at 12% -8%,var(--glow),transparent 70%),radial-gradient(600px 340px at 92% 0%,var(--glow-2),transparent 70%)}
button,input,select{font:inherit;color:inherit}
a{color:inherit}
.wrap{position:relative;z-index:1;max-width:1180px;margin:0 auto;padding:0 16px 48px}

/* header */
header{position:sticky;top:0;z-index:10;backdrop-filter:saturate(1.4) blur(12px);-webkit-backdrop-filter:saturate(1.4) blur(12px);
  background:color-mix(in srgb,var(--bg) 72%,transparent);border-bottom:1px solid color-mix(in srgb,var(--line) 70%,transparent)}
.bar{max-width:1180px;margin:0 auto;padding:14px 16px;display:flex;align-items:center;gap:12px}
.logo{width:32px;height:32px;border-radius:9px;display:grid;place-items:center;color:#fff;flex:none;
  background:linear-gradient(135deg,#6366f1,#06b6d4);box-shadow:0 4px 14px rgba(99,102,241,.35)}
.brand{font-weight:700;font-size:16px;letter-spacing:-.01em}
.brand small{display:block;font-weight:500;font-size:12px;color:var(--muted);letter-spacing:0}
.pill{margin-left:auto;display:inline-flex;align-items:center;gap:8px;padding:6px 12px;border-radius:999px;font-size:13px;font-weight:500;
  background:var(--surface);border:1px solid var(--line);box-shadow:var(--shadow);transition:all .3s var(--ease);white-space:nowrap}
.dot{width:8px;height:8px;border-radius:50%;background:var(--muted);position:relative;flex:none}
.dot.live::after{content:"";position:absolute;inset:0;border-radius:50%;background:inherit;animation:ping 1.8s var(--ease) infinite}
.good-bg{background:var(--good)}.warn-bg{background:var(--warn)}.bad-bg{background:var(--bad)}
@keyframes ping{0%{transform:scale(1);opacity:.7}80%,100%{transform:scale(2.6);opacity:0}}
.loadbar{position:absolute;left:0;bottom:-1px;height:2px;width:100%;overflow:hidden;opacity:0;transition:opacity .2s}
.loadbar.on{opacity:1}
.loadbar::after{content:"";position:absolute;inset:0;width:40%;background:linear-gradient(90deg,transparent,var(--accent),var(--accent-2),transparent);animation:slide 1.1s ease-in-out infinite}
@keyframes slide{from{transform:translateX(-100%)}to{transform:translateX(260%)}}

/* layout */
.grid{display:grid;gap:20px;margin-top:24px}
.grid>*{min-width:0}
@media (min-width:1000px){.grid{grid-template-columns:minmax(0,1fr) 340px;align-items:start}.side{position:sticky;top:84px}}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow)}
h2{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:0 0 12px;display:flex;align-items:center;gap:8px}

/* search panel */
.search{padding:18px}
.qrow{display:flex;gap:10px}
.qbox{flex:1;min-width:0;position:relative}
.qbox svg{position:absolute;left:14px;top:50%;transform:translateY(-50%);color:var(--muted);transition:color .2s;pointer-events:none}
.qbox:focus-within svg{color:var(--accent)}
#q{width:100%;height:50px;padding:0 16px 0 44px;border-radius:12px;border:1px solid var(--line);background:var(--surface-2);font-size:16px;outline:none;
  transition:border-color .2s,box-shadow .2s,background .2s}
#q::placeholder{color:var(--muted)}
#q:focus{border-color:var(--accent);background:var(--surface);box-shadow:0 0 0 4px var(--accent-soft)}
.go{height:50px;padding:0 22px;border:0;border-radius:12px;cursor:pointer;color:#fff;font-weight:600;display:inline-flex;align-items:center;gap:8px;flex:none;
  background:linear-gradient(135deg,#6366f1,#4f46e5);box-shadow:0 6px 18px rgba(79,70,229,.35);transition:transform .15s var(--ease),box-shadow .2s,filter .2s}
.go:hover{transform:translateY(-1px);box-shadow:0 10px 24px rgba(79,70,229,.42);filter:brightness(1.06)}
.go:active{transform:translateY(0) scale(.98)}
.go:disabled{cursor:progress;filter:saturate(.7)}
.go:focus-visible{outline:none;box-shadow:0 0 0 4px var(--accent-soft),0 6px 18px rgba(79,70,229,.35)}
.spin{width:16px;height:16px;border:2px solid rgba(255,255,255,.35);border-top-color:#fff;border-radius:50%;animation:rot .7s linear infinite;display:none}
.go.busy .spin{display:block}.go.busy .arrow{display:none}
@keyframes rot{to{transform:rotate(360deg)}}
.opts{display:flex;flex-wrap:wrap;gap:14px 20px;margin-top:16px;align-items:flex-end}
.opt{display:flex;flex-direction:column;gap:6px}
.opt>span{font-size:12px;font-weight:500;color:var(--muted)}
.seg{position:relative;display:inline-flex;padding:3px;border-radius:10px;background:var(--surface-2);border:1px solid var(--line)}
.seg label{position:relative;z-index:1;cursor:pointer}
.seg input{position:absolute;opacity:0;pointer-events:none}
.seg label span{display:block;padding:5px 12px;font-size:13px;font-weight:500;color:var(--muted);border-radius:7px;transition:color .2s}
.seg input:checked+span{color:var(--fg)}
.seg label:hover span{color:var(--fg)}
.seg input:focus-visible+span{box-shadow:0 0 0 2px var(--accent)}
.seg .ind{position:absolute;top:3px;bottom:3px;left:0;border-radius:7px;background:var(--surface);box-shadow:0 1px 3px rgba(15,23,42,.12),0 0 0 1px var(--line);
  transition:transform .35s var(--ease),width .35s var(--ease)}
.sel{position:relative}
.sel select{appearance:none;-webkit-appearance:none;height:36px;padding:0 34px 0 12px;border-radius:10px;border:1px solid var(--line);background:var(--surface-2);
  font-size:13px;font-weight:500;cursor:pointer;outline:none;transition:border-color .2s,box-shadow .2s}
.sel select:focus-visible{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.sel::after{content:"";position:absolute;right:13px;top:50%;width:6px;height:6px;border-right:1.5px solid var(--muted);border-bottom:1.5px solid var(--muted);transform:translateY(-70%) rotate(45deg);pointer-events:none}
.toggles{display:flex;gap:16px;flex-wrap:wrap;height:36px;align-items:center}
.sw{display:inline-flex;align-items:center;gap:9px;cursor:pointer;font-size:13px;font-weight:500;color:var(--fg-2);user-select:none}
.sw input{position:absolute;opacity:0;pointer-events:none}
.track{width:34px;height:20px;border-radius:999px;background:var(--line);position:relative;transition:background .25s var(--ease);flex:none}
.track::after{content:"";position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.25);transition:transform .3s var(--ease)}
.sw input:checked+.track{background:var(--accent)}
.sw input:checked+.track::after{transform:translateX(14px)}
.sw input:focus-visible+.track{box-shadow:0 0 0 3px var(--accent-soft)}

/* results */
#out{margin-top:20px;display:flex;flex-direction:column;gap:16px}
.reveal{opacity:0;animation:rise .55s var(--ease) forwards;animation-delay:calc(var(--i,0)*55ms)}
@keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
.empty{padding:44px 20px;text-align:center;color:var(--muted)}
.empty .orb{width:64px;height:64px;margin:0 auto 14px;border-radius:18px;display:grid;place-items:center;color:var(--accent);background:var(--accent-soft);animation:float 4s ease-in-out infinite}
.empty b{display:block;color:var(--fg);font-size:16px;margin-bottom:4px}
@keyframes float{50%{transform:translateY(-6px)}}
.status{padding:16px 18px;display:flex;flex-direction:column;gap:12px}
.st-top{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.badge{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.badge.good{color:var(--good);background:var(--good-soft)}.badge.warn{color:var(--warn);background:var(--warn-soft)}.badge.bad{color:var(--bad);background:var(--bad-soft)}
.badge .dot{width:6px;height:6px;background:currentColor}
.via{color:var(--fg-2);font-size:14px}
.via b{font-weight:600;color:var(--fg)}
.ms{font-family:var(--mono);font-size:12.5px;font-weight:600;padding:2px 8px;border-radius:6px;background:var(--surface-2);color:var(--fg-2);margin-left:auto}
.tag{font-size:12px;font-weight:500;padding:2px 8px;border-radius:6px;background:var(--accent-soft);color:var(--accent)}
.tag.stale{background:var(--warn-soft);color:var(--warn)}
.trail{display:flex;flex-wrap:wrap;align-items:center;gap:6px}
.step{display:inline-flex;align-items:center;gap:7px;padding:5px 10px;border:1px solid var(--line);border-radius:8px;font-size:12.5px;background:var(--surface-2)}
.step b{font-weight:600}
.step .dot{width:7px;height:7px}
.step em{font-style:normal;color:var(--muted);font-family:var(--mono);font-size:11.5px}
.chev{color:var(--muted);font-size:12px}
.note{margin:0;padding:10px 12px;border-radius:10px;background:var(--bad-soft);color:var(--bad);font-size:14px}
.aio{padding:18px;position:relative;overflow:hidden;border:1px solid transparent;
  background:linear-gradient(var(--surface),var(--surface)) padding-box,linear-gradient(135deg,#818cf8,#22d3ee 50%,#a78bfa) border-box}
.aio h3{margin:0 0 8px;font-size:14px;display:flex;align-items:center;gap:8px}
.aio h3 svg{color:var(--accent)}
.aio p{margin:0 0 10px;color:var(--fg-2);white-space:pre-line}
.muted{color:var(--muted);font-size:13px}
.results{list-style:none;margin:0;padding:6px}
.res{display:flex;gap:14px;padding:14px 12px;border-radius:10px;position:relative;transition:background .2s}
.res:hover{background:var(--surface-2)}
.res+.res::before{content:"";position:absolute;top:0;left:12px;right:12px;height:1px;background:var(--line)}
.res:hover::before,.res:hover+.res::before{opacity:0}
.pos{flex:none;width:26px;height:26px;border-radius:8px;display:grid;place-items:center;font-family:var(--mono);font-size:12px;font-weight:600;color:var(--muted);background:var(--surface-2);transition:all .2s}
.res:hover .pos{background:var(--accent);color:#fff}
.rb{min-width:0;flex:1}
.src{display:flex;align-items:center;gap:8px;min-width:0;font-size:12.5px}
.av{flex:none;width:20px;height:20px;border-radius:6px;display:grid;place-items:center;font-size:11px;font-weight:700;color:#fff}
.sn{font-weight:600;color:var(--fg-2);white-space:nowrap}
.crumb{color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.rt{display:inline-block;margin:4px 0 2px;font-size:16.5px;font-weight:600;line-height:1.35;color:var(--accent);text-decoration:none;background:linear-gradient(currentColor,currentColor) 0 100%/0 1.5px no-repeat;transition:background-size .3s var(--ease)}
.rt:hover{background-size:100% 1.5px}
.rt:focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:3px}
.rt svg{vertical-align:-1px;margin-left:4px;opacity:0;transform:translate(-3px,3px);transition:all .25s var(--ease)}
.rt:hover svg,.rt:focus-visible svg{opacity:1;transform:none}
.snip{margin:0;color:var(--fg-2);font-size:14px}
.two{display:grid;gap:16px}
@media (min-width:700px){.two{grid-template-columns:1fr 1fr}}
.list{padding:16px 18px}
.list ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:2px}
.list li{display:flex;gap:10px;align-items:flex-start;padding:8px;margin:0 -8px;border-radius:8px;font-size:14px;color:var(--fg-2);transition:background .2s,color .2s}
.list li:hover{background:var(--surface-2);color:var(--fg)}
.list li svg{flex:none;margin-top:3px;color:var(--muted)}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{padding:6px 12px;border-radius:999px;border:1px solid var(--line);background:var(--surface-2);font-size:13px;color:var(--fg-2);transition:border-color .2s,color .2s,transform .2s var(--ease)}
.chip:hover{border-color:var(--accent);color:var(--accent);transform:translateY(-1px)}
.skel{position:relative;overflow:hidden;background:var(--skel);border-radius:6px}
.skel::after{content:"";position:absolute;inset:0;transform:translateX(-100%);background:linear-gradient(90deg,transparent,var(--skel-hi),transparent);animation:shim 1.3s infinite}
@keyframes shim{to{transform:translateX(100%)}}
.sk-row{display:flex;gap:14px;padding:14px 12px}
.sk-row .rb{display:flex;flex-direction:column;gap:8px}
.json summary{display:flex;align-items:center;gap:10px;padding:14px 18px;cursor:pointer;list-style:none;font-weight:600;font-size:14px}
.json summary::-webkit-details-marker{display:none}
.json summary::before{content:"\25B8";color:var(--muted);transition:transform .2s var(--ease)}
.json[open] summary::before{transform:rotate(90deg)}
.json summary code{font-family:var(--mono);font-size:12px;font-weight:400;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.json .cp{margin-left:auto;flex:none;padding:4px 10px;border:1px solid var(--line);border-radius:8px;background:var(--surface-2);color:var(--fg-2);font:inherit;font-size:12px;cursor:pointer}
.json .cp:hover{border-color:var(--accent);color:var(--accent)}
.json pre{margin:0;padding:14px 18px;border-top:1px solid var(--line);max-height:480px;overflow:auto;font-family:var(--mono);font-size:12px;line-height:1.5;color:var(--fg-2);background:var(--surface-2);border-radius:0 0 inherit inherit}

/* health */
.side .card{padding:16px}
.tiles{display:grid;gap:12px}
.tile{padding:16px;transition:transform .25s var(--ease),box-shadow .25s}
.tile:hover{transform:translateY(-2px);box-shadow:var(--shadow-lg)}
.tl{font-size:12.5px;font-weight:500;color:var(--muted);display:flex;align-items:center;gap:8px}
.big{font-size:28px;font-weight:700;letter-spacing:-.02em;line-height:1.15;margin:4px 0 2px;font-variant-numeric:tabular-nums}
.big.bad{color:var(--bad)}
.sub{font-size:12.5px;color:var(--muted)}
.tile.cool{border-color:color-mix(in srgb,var(--bad) 40%,var(--line));background:linear-gradient(180deg,var(--bad-soft),transparent 70%),var(--surface)}
.meter{height:6px;border-radius:99px;background:var(--surface-2);overflow:hidden;margin:10px 0 8px}
.meter i{display:block;height:100%;width:0;border-radius:inherit;background:linear-gradient(90deg,var(--accent),var(--accent-2));transition:width 1s var(--ease)}
.meter i.full{background:var(--bad)}
.modes{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.mode{display:flex;flex-direction:column;align-items:center;text-align:center;padding:16px 10px}
.ring{position:relative;width:76px;height:76px;margin:6px 0 8px}
.ring svg{transform:rotate(-90deg)}
.ring circle{fill:none;stroke-width:7}
.ring .bgc{stroke:var(--surface-2)}
.ring .fgc{stroke-linecap:round;transition:stroke-dashoffset 1.2s var(--ease)}
.ring span{position:absolute;inset:0;display:grid;place-items:center;font-weight:700;font-size:17px;font-variant-numeric:tabular-nums}
.mode .name{font-weight:600;font-size:13px}
.mode:last-child:nth-child(odd){grid-column:span 2}
.kv{display:flex;flex-direction:column;gap:2px;margin-top:6px;width:100%}
.kv div{display:flex;justify-content:space-between;font-size:12px;color:var(--muted)}
.kv b{font-weight:600;color:var(--fg-2);font-family:var(--mono);font-size:11.5px}
.stack{display:flex;height:10px;border-radius:99px;overflow:hidden;gap:2px;margin:12px 0}
.stack i{display:block;height:100%;width:0;transition:width 1s var(--ease)}
.legend{display:flex;flex-direction:column;gap:6px}
.legend div{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--fg-2)}
.legend .sq{width:9px;height:9px;border-radius:3px;flex:none}
.legend b{margin-left:auto;font-family:var(--mono);font-size:12px;font-weight:600}
.hs{margin-bottom:0}
@media (max-width:560px){
  .qrow{flex-direction:column}.go{justify-content:center}
  .brand small{display:none}
  .ms{margin-left:0}
}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.001ms!important;animation-iteration-count:1!important;transition-duration:.001ms!important}}
</style></head><body>
<header><div class="bar">
  <div class="logo"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/></svg></div>
  <div class="brand">SERP Engine<small>Google results, fetched and parsed</small></div>
  <div class="pill" id="pill"><span class="dot"></span><span>Checking…</span></div>
</div><div class="loadbar" id="lb"></div></header>

<div class="wrap"><div class="grid">
<main>
  <form id="f" class="card search" autocomplete="off">
    <div class="qrow">
      <div class="qbox">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
        <input type="text" id="q" placeholder="Search Google…" required aria-label="Search query">
      </div>
      <button class="go" id="go"><span class="spin"></span>Search<svg class="arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button>
    </div>
    <div class="opts">
      <div class="opt"><span>Mode</span>
        <div class="seg" role="radiogroup" aria-label="Mode"><span class="ind"></span>
          <label><input type="radio" name="mode" value="auto" checked><span>auto</span></label>
          <label><input type="radio" name="mode" value="lite"><span>lite</span></label>
          <label><input type="radio" name="mode" value="http"><span>http</span></label>
          <label><input type="radio" name="mode" value="browser"><span>browser</span></label>
        </div></div>
      <div class="opt"><span>Time</span>
        <div class="sel"><select id="tbs" aria-label="Time range"><option value="">Any time</option><option value="qdr:d">Past day</option><option value="qdr:w">Past week</option><option value="qdr:m">Past month</option><option value="qdr:y">Past year</option></select></div></div>
      <div class="opt"><span>Page</span>
        <div class="seg" role="radiogroup" aria-label="Page"><span class="ind"></span>
          <label><input type="radio" name="start" value="0" checked><span>1</span></label>
          <label><input type="radio" name="start" value="10"><span>2</span></label>
          <label><input type="radio" name="start" value="20"><span>3</span></label>
        </div></div>
      <div class="opt"><span>Options</span>
        <div class="toggles">
          <label class="sw"><input type="checkbox" id="aio"><span class="track"></span>AI Overview</label>
          <label class="sw"><input type="checkbox" id="nc"><span class="track"></span>Skip cache</label>
        </div></div>
    </div>
  </form>
  <div id="out"><div class="card empty reveal"><div class="orb"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg></div><b>Run a search</b>Results, AI Overviews and the fetch trail will show up here.</div></div>
</main>
<aside class="side">
  <h2>Health</h2>
  <div id="stats" class="tiles"></div>
</aside>
</div></div>

<script>
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const radio=n=>document.querySelector(`input[name="${n}"]:checked`).value;
const tone=s=>s=='ok'?'good':(s=='blocked'||s=='throttled')?'warn':'bad';
const ICON={
  ext:'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17L17 7M8 7h9v9"/></svg>',
  q:'<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5v.4M12 17h.01"/></svg>',
  spark:'<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l1.8 5.7L19.5 9.5l-5.7 1.8L12 17l-1.8-5.7L4.5 9.5l5.7-1.8zM19 15l.9 2.6 2.6.9-2.6.9L19 22l-.9-2.6-2.6-.9 2.6-.9z"/></svg>'
};
const HUES=['#6366f1','#0ea5e9','#14b8a6','#f59e0b','#ec4899','#8b5cf6','#ef4444','#10b981'];
const hue=s=>{let h=5381;for(const c of String(s))h=((h*33)^c.charCodeAt(0))>>>0;return HUES[h%HUES.length]};
const OUT={ok:'var(--good)',captcha:'#ef4444',error:'#f97316',empty_parse:'#f59e0b',js_required:'#8b5cf6',consent:'#0ea5e9'};

// sliding segmented controls
function placeInd(seg){const on=seg.querySelector('input:checked').parentElement,ind=seg.querySelector('.ind');
  ind.style.width=on.offsetWidth+'px';ind.style.transform=`translateX(${on.offsetLeft}px)`}
document.querySelectorAll('.seg').forEach(seg=>{placeInd(seg);seg.addEventListener('change',()=>placeInd(seg))});
const replace=()=>document.querySelectorAll('.seg').forEach(placeInd);
addEventListener('resize',replace);document.fonts&&document.fonts.ready.then(replace);

// numbers count up from their last value
function countUp(el){const to=+el.dataset.count,from=+(el.dataset.from||0),suf=el.dataset.suf||'',t0=performance.now(),d=900;
  if(matchMedia('(prefers-reduced-motion:reduce)').matches||from===to){el.textContent=to+suf;return}
  (function f(t){const p=Math.min(1,(t-t0)/d),e=1-Math.pow(1-p,3);el.textContent=Math.round(from+(to-from)*e)+suf;if(p<1)requestAnimationFrame(f)})(t0)}
const prev={};
const num=(key,v,suf='')=>{const f=prev[key]??0;prev[key]=v;return `<span data-count="${v}" data-from="${f}" data-suf="${suf}">${f}${suf}</span>`};

let cdTimer;
function mmss(s){s=Math.max(0,Math.ceil(s));return s>=60?`${Math.floor(s/60)}m ${String(s%60).padStart(2,'0')}s`:`${s}s`}
function setPill(t,text,live){$('#pill').innerHTML=`<span class="dot ${t}-bg ${live?'live':''}"></span><span>${text}</span>`}

async function loadStats(){
  const s=await (await fetch('/stats')).json();
  clearInterval(cdTimer);
  const full=s.requests_last_hour!=null&&s.max_per_hour&&s.requests_last_hour>=s.max_per_hour;
  const outs=Object.entries(s.outcomes),total=outs.reduce((a,[,v])=>a+v,0)||1;
  const oc=k=>OUT[k]||hue(k);
  const modes=Object.entries(s.by_mode);
  let h='';
  if(s.blocked_for_s)h+=`<div class="card tile cool reveal"><div class="tl"><span class="dot bad-bg live"></span>Cooling down</div><div class="big bad" id="cd">${mmss(s.blocked_for_s)}</div><div class="sub">until Google is contacted again</div></div>`;
  if(s.requests_last_hour!=null&&s.max_per_hour){const pct=Math.min(100,s.requests_last_hour/s.max_per_hour*100);
    h+=`<div class="card tile reveal" style="--i:1"><div class="tl">This hour</div><div class="big ${full?'bad':''}">${num('rh',s.requests_last_hour)}<span class="sub" style="font-size:15px;font-weight:500"> / ${s.max_per_hour}</span></div><div class="meter"><i class="${full?'full':''}" data-w="${pct}"></i></div><div class="sub">requests to Google (SERP_MAX_PER_HOUR)</div></div>`}
  if(modes.length)h+=`<div class="modes">${modes.map(([m,v],i)=>{const r=Math.round(v.success_rate*100),C=2*Math.PI*32,col=r>=80?'var(--good)':r>=40?'var(--warn)':'var(--bad)';
    return `<div class="card tile mode reveal" style="--i:${i+2}"><div class="name">${esc(m)} mode</div>
      <div class="ring"><svg width="76" height="76"><circle class="bgc" cx="38" cy="38" r="32"/><circle class="fgc" cx="38" cy="38" r="32" stroke="${col}" stroke-dasharray="${C}" stroke-dashoffset="${C}" data-off="${C*(1-r/100)}"/></svg><span>${num('m'+m,r,'%')}</span></div>
      <div class="kv"><div>tries<b>${v.attempts}</b></div><div>avg<b>${v.avg_ms} ms</b></div><div>layout breaks<b>${v.layout_breaks}</b></div></div></div>`}).join('')}</div>`;
  h+=`<div class="card tile reveal" style="--i:${modes.length+2}"><div class="tl">Cached searches</div><div class="big">${num('c',s.cached_searches)}</div><div class="sub">answered without Google</div></div>`;
  h+=`<div class="card tile reveal" style="--i:${modes.length+3}"><div class="tl">Outcomes</div>${outs.length?`<div class="stack">${outs.map(([k,v])=>`<i style="background:${oc(k)}" data-w="${v/total*100}" title="${esc(k)}: ${v}"></i>`).join('')}</div>
    <div class="legend">${outs.map(([k,v])=>`<div><span class="sq" style="background:${oc(k)}"></span>${esc(k)}<b>${v}</b></div>`).join('')}</div>`:'<div class="sub" style="margin-top:6px">No attempts yet</div>'}</div>`;
  const box=$('#stats');box.innerHTML=h;
  requestAnimationFrame(()=>requestAnimationFrame(()=>{
    box.querySelectorAll('[data-w]').forEach(e=>e.style.width=e.dataset.w+'%');
    box.querySelectorAll('[data-off]').forEach(e=>e.style.strokeDashoffset=e.dataset.off);
    box.querySelectorAll('[data-count]').forEach(countUp);
  }));
  if(s.blocked_for_s){const end=Date.now()+s.blocked_for_s*1000;setPill('bad',`Cooling down · ${mmss(s.blocked_for_s)}`,true);
    cdTimer=setInterval(()=>{const left=(end-Date.now())/1000,cd=$('#cd');
      if(left<=0){clearInterval(cdTimer);if(cd)cd.textContent='0s';setPill('good','Ready',false);return}
      if(cd)cd.textContent=mmss(left);setPill('bad',`Cooling down · ${mmss(left)}`,true)},1000)}
  else if(full)setPill('warn','Hourly limit reached',true);
  else setPill('good','Ready',false);
}

function skeleton(){const row=i=>`<div class="sk-row"><div class="skel" style="width:26px;height:26px;border-radius:8px"></div><div class="rb"><div class="skel" style="width:30%;height:10px"></div><div class="skel" style="width:${70-i*8}%;height:15px"></div><div class="skel" style="width:95%;height:10px"></div><div class="skel" style="width:80%;height:10px"></div></div></div>`;
  return `<div class="card status"><div class="st-top"><div class="skel" style="width:60px;height:20px;border-radius:99px"></div><div class="skel" style="width:160px;height:12px"></div></div></div>
  <div class="card" style="padding:6px">${[0,1,2,3].map(row).join('')}</div>`}

$('#f').onsubmit=async e=>{
  e.preventDefault();
  const out=$('#out'),go=$('#go');
  out.innerHTML=skeleton();go.classList.add('busy');go.disabled=true;$('#lb').classList.add('on');
  try{
    const p=new URLSearchParams({q:q.value,mode:radio('mode'),aio:aio.checked,tbs:tbs.value,start:radio('start'),no_cache:nc.checked});
    const res=await fetch('/search?'+p);const r=await res.json();
    if(!res.ok)throw new Error(typeof r.detail=='string'?r.detail:res.statusText);
    const t=tone(r.status);
    const via=r.stale?`<span class="tag stale">stale copy</span> fetched ${new Date(r.created_at*1000).toLocaleString()} via <b>${esc(r.mode)}</b>`
      :r.cached?`<span class="tag">from cache</span> fetched ${new Date(r.created_at*1000).toLocaleTimeString()} via <b>${esc(r.mode)}</b>`
      :r.mode?`via <b>${esc(r.mode)}</b>`:'';
    const trail=r.cached&&!r.stale||!r.attempts.length?'':`<div class="trail">${r.attempts.map((a,i)=>`${i?'<span class="chev">→</span>':''}<span class="step"><span class="dot ${a.outcome=='ok'?'good':'bad'}-bg"></span><b>${esc(a.mode)}</b>${esc(a.outcome)}<em>${a.elapsed_ms} ms</em></span>`).join('')}</div>`;
    let i=0,h=`<div class="card status reveal" style="--i:${i++}"><div class="st-top"><span class="badge ${t}"><span class="dot"></span>${esc(r.status)}</span><span class="via">${via}</span><span class="ms">${r.elapsed_ms} ms</span></div>${trail}${r.note?`<p class="note">${esc(r.note)}</p>`:''}</div>`;
    if(r.ai_overview)h+=`<div class="card aio reveal" style="--i:${i++}"><h3>${ICON.spark}AI Overview</h3><p>${esc(r.ai_overview.text.slice(0,800))}</p><div class="muted">${r.ai_overview.sources.length} sources</div></div>`;
    if(r.organic.length)h+=`<div class="card"><ol class="results">${r.organic.map(o=>{const name=o.source||o.domain||'';return `<li class="res reveal" style="--i:${i++}"><div class="pos">${o.position||''}</div><div class="rb">
      <div class="src"><span class="av" style="background:${hue(o.domain||name||o.url)}">${esc((o.domain||name||'?').replace(/^www\./,'')[0].toUpperCase())}</span>${name?`<span class="sn">${esc(name)}</span>`:''}<span class="crumb">${esc(o.display_url||o.domain||o.url)}</span></div>
      <a class="rt" href="${esc(o.url)}" target="_blank" rel="noopener noreferrer">${esc(o.title)}${ICON.ext}</a>
      ${o.snippet?`<p class="snip">${esc(o.snippet)}</p>`:''}</div></li>`}).join('')}</ol></div>`;
    const paa=r.people_also_ask.length,rel=r.related_searches.length;
    if(paa||rel)h+=`<div class="two">`
      +(paa?`<div class="card list reveal" style="--i:${i++}"><h2>People also ask</h2><ul>${r.people_also_ask.map(x=>`<li>${ICON.q}<span>${esc(x)}</span></li>`).join('')}</ul></div>`:'')
      +(rel?`<div class="card list reveal" style="--i:${i++}"><h2>Related searches</h2><div class="chips">${r.related_searches.map(x=>`<span class="chip">${esc(x)}</span>`).join('')}</div></div>`:'')
      +`</div>`;
    const url='/search?'+p;
    h+=`<details class="card json reveal" style="--i:${i++}"><summary>API response<code>GET ${esc(url)}</code><button type="button" class="cp">Copy</button></summary><pre>${esc(JSON.stringify(r,null,2))}</pre></details>`;
    out.innerHTML=h;
    out.querySelector('.json .cp').onclick=e=>{e.preventDefault();navigator.clipboard.writeText(JSON.stringify(r,null,2)).then(()=>{e.target.textContent='Copied';setTimeout(()=>e.target.textContent='Copy',1500)})};
  }catch(err){
    out.innerHTML=`<div class="card status reveal"><div class="st-top"><span class="badge bad"><span class="dot"></span>error</span><span class="via">${esc(err.message||err)}</span></div></div>`;
  }finally{go.classList.remove('busy');go.disabled=false;$('#lb').classList.remove('on')}
  loadStats();
};
loadStats();
</script></body></html>"""
