#!/usr/bin/env python3
"""
◢ SESSIONGUARD v1.0 — auth gateway / session shield for HTTP tools
  Made by Aryan Giri | giriaryan694-a11y

  python sessionguard.py --set-admin
  python sessionguard.py --add-user admin2 --as 1
  python sessionguard.py --port 8000
  cloudflared tunnel --url http://127.0.0.1:8000

  Set the backend target from /admin → GATEWAY TARGET panel.
"""
import argparse, hashlib, hmac, json, os, re, secrets, sys, threading, time
from urllib.parse import quote
from functools import wraps
from pathlib import Path

import requests as rq
from flask import (Flask, request, redirect, url_for, render_template_string,
                   make_response, jsonify, g, Response)

# ═══════════════════════ CONFIG ═══════════════════════
BASE        = Path(__file__).parent
DATA        = BASE / "data"
ADMIN_AUTH  = BASE / "admin_auth.txt"
USERS_TXT   = BASE / "users.txt"
SESSIONS_DB = DATA / "sessions.json"
EVENTS_DB   = DATA / "events.json"
CONFIG_DB   = DATA / "config.json"

ROUNDS      = 200_000
SESSION_TTL = 60 * 60 * 12
SID_COOKIE  = "sg_sid"
PRE_COOKIE  = "sg_pre"
LOCK_ATTEMPTS, LOCK_SECONDS = 5, 300
ALL_METHODS = ["GET","POST","PUT","DELETE","PATCH","OPTIONS","HEAD"]
CRED_HASH_RE = re.compile(r"^[0-9a-f]{32}\$[0-9a-f]{64}$")
LINE_RE = re.compile(r"^\s*([A-Za-z0-9_.-]{2,32}):(\S+)(?:\s+AS:(\d+))?\s*(OFF)?\s*(?:#.*)?$")
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' "
       "https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
       "img-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'")

_lock   = threading.RLock()
_fails  = {}
app     = Flask(__name__)

# ═══════════════════════ BANNER / CREDIT ═══════════════════════
def banner(host, port, target):
    A = "\033[38;5;214m"
    G = "\033[38;5;78m"
    C = "\033[38;5;75m"
    R = "\033[38;5;196m"
    D = "\033[2m"
    B = "\033[1m"
    X = "\033[0m"
    ln = "─" * 46
    print()
    print(f"  {A}{B}┌{ln}┐{X}")
    print(f"  {A}{B}│{'◢ S E S S I O N G U A R D':^46}│{X}")
    print(f"  {A}{B}│{'v1.0 · auth gateway · session shield':^46}│{X}")
    print(f"  {A}{B}└{ln}┘{X}")
    print(f"  {D}Made by{X} {B}Aryan Giri{X} {D}|{X} {C}giriaryan694-a11y{X}")
    print(f"  {D}{ln}{X}")
    print(f"  {G}▸ listen{X}    http://{host}:{port}")
    print(f"  {G}▸ target{X}    {target}")
    print(f"  {G}▸ admin{X}     http://{host}:{port}/admin")
    print(f"  {G}▸ guards{X}    {G}csrf · lockout · AS limits{X}")
    print(f"  {D}{ln}{X}")
    print(f"  {R}▲ point cloudflared at gateway :{port}, NOT the tool{X}")
    print(f"  {D}▲ change target live from /admin → GATEWAY TARGET{X}")
    print()

def mini_banner():
    print(f"\n  \033[38;5;214m\033[1m◢ SESSIONGUARD\033[0m"
          f" \033[2m— Made by Aryan Giri | giriaryan694-a11y\033[0m\n")

# ═══════════════════════ EMBEDDED CSS ═══════════════════════
GUARD_CSS = r"""
:root{
  --ink:#0b1114;--panel:#121b21;--panel2:#0e161a;--line:#1e2c33;--line-hi:#2b4049;
  --text:#d9e4e8;--dim:#7d929b;--faint:#54676f;
  --amber:#ffb454;--amber-hi:#ffc678;--green:#43d9a3;--red:#ff5d5d;--cyan:#5bc8ff;
  --mono:'IBM Plex Mono',ui-monospace,monospace;--disp:'Chakra Petch',sans-serif;--body:'IBM Plex Sans',system-ui,sans-serif;
}
*{margin:0;padding:0;box-sizing:border-box}
[hidden]{display:none!important}
html{color-scheme:dark}
body{background:var(--ink);color:var(--text);font-family:var(--body);font-size:14px;min-height:100vh}
::selection{background:rgba(255,180,84,.3)}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-thumb{background:#22333b;border:2px solid var(--ink)}
.mono{font-family:var(--mono)}.dim{color:var(--faint)}.ok{color:var(--green)}.warn{color:var(--amber)}
.ta-r{text-align:right}.inline{display:inline}
.bg-glow{position:fixed;inset:0;z-index:-3;background:
  radial-gradient(700px 420px at 12% -8%,rgba(255,180,84,.10),transparent 60%),
  radial-gradient(820px 520px at 88% 112%,rgba(67,217,163,.07),transparent 60%),
  radial-gradient(620px 420px at 72% 18%,rgba(91,200,255,.05),transparent 60%)}
.bg-grid{position:fixed;inset:0;z-index:-2;background-image:
  linear-gradient(rgba(91,200,255,.045) 1px,transparent 1px),
  linear-gradient(90deg,rgba(91,200,255,.045) 1px,transparent 1px);
  background-size:44px 44px;mask-image:radial-gradient(ellipse at 50% 0%,#000 30%,transparent 78%)}
.scanlines{position:fixed;inset:0;z-index:50;pointer-events:none;opacity:.3;
  background:repeating-linear-gradient(0deg,rgba(0,0,0,.18) 0 1px,transparent 1px 3px)}
.console-bar{display:flex;align-items:center;gap:12px;padding:10px 16px;border-bottom:1px solid var(--line);background:#0d1519}
.bar-dots i{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:5px;background:#2b4049}
.bar-dots i:first-child{background:var(--red)}.bar-dots i:nth-child(2){background:var(--amber)}.bar-dots i:last-child{background:var(--green)}
.bar-title{font:600 10.5px var(--mono);letter-spacing:.22em;color:var(--dim);flex:1}
.bar-tty{font:500 10px var(--mono);letter-spacing:.14em;color:var(--faint);display:flex;align-items:center;gap:6px}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block;flex:none}
.dot-live{background:var(--green);box-shadow:0 0 8px var(--green);animation:pulse 1.6s infinite}
.dot-admin{background:var(--amber);box-shadow:0 0 8px var(--amber);animation:pulse 1.6s infinite}
@keyframes pulse{50%{opacity:.35}}
.btn{font:600 12px var(--disp);letter-spacing:.09em;padding:9px 16px;border:1px solid var(--line-hi);
  background:rgba(21,33,38,.6);color:var(--text);cursor:pointer;text-decoration:none;display:inline-block;
  clip-path:polygon(8px 0,100% 0,100% calc(100% - 8px),calc(100% - 8px) 100%,0 100%,0 8px);
  transition:transform .18s,box-shadow .18s,background .18s,border-color .18s,color .18s}
.btn:hover{transform:translateY(-1px);border-color:var(--cyan);color:#fff;
  box-shadow:0 0 0 1px rgba(91,200,255,.25),0 8px 20px -10px rgba(91,200,255,.45)}
.btn .arr{display:inline-block;transition:transform .18s}
.btn:hover .arr{transform:translateX(3px)}
.btn-amber{background:var(--amber);color:#1a1206;border-color:var(--amber)}
.btn-amber:hover{background:var(--amber-hi);border-color:var(--amber-hi);color:#1a1206;box-shadow:0 0 20px -4px rgba(255,180,84,.6)}
.btn-danger{border-color:rgba(255,93,93,.5);color:#ffb3b3}
.btn-danger:hover{border-color:var(--red);color:#fff;box-shadow:0 0 0 1px rgba(255,93,93,.3)}
.btn-block{width:100%;padding:12px;text-align:center}
.btn-ico{width:28px;height:28px;border:1px solid var(--line);background:#0d1519;color:var(--dim);font-size:13px;cursor:pointer;transition:.15s;margin-left:4px}
.btn-ico:hover{color:var(--cyan);border-color:var(--cyan);transform:translateY(-1px)}
.btn-ico-danger:hover{color:var(--red);border-color:var(--red)}
.btn-ico:disabled{opacity:.25;cursor:not-allowed;transform:none}
.btn-ico.armed{color:#1a0d0d;background:var(--red);border-color:var(--red);font-weight:700}
.field{display:block;margin-bottom:16px}
.field-key{font:500 10px var(--mono);letter-spacing:.16em;color:var(--dim);display:block;margin-bottom:6px}
.field-in{width:100%;background:#0b1216;border:1px solid var(--line);color:var(--text);font:500 14px var(--mono);padding:10px 12px;outline:0;transition:border-color .15s,box-shadow .15s}
.field-in:focus{border-color:var(--amber);box-shadow:0 0 0 1px rgba(255,180,84,.3),0 0 16px -6px rgba(255,180,84,.5)}
.field-sm{padding:7px 10px;font-size:12px;width:150px}
.field.check{display:flex;align-items:center;gap:9px;font:600 10.5px var(--mono);letter-spacing:.14em;color:var(--dim)}
.field.check input{accent-color:var(--amber);width:15px;height:15px}
.hint{font:400 11.5px var(--mono);color:var(--faint);margin:0 0 16px;line-height:1.6}
.gate-wrap{min-height:100vh;display:grid;grid-template-columns:1.1fr .9fr;gap:64px;align-items:center;max-width:1160px;margin:0 auto;padding:48px 32px}
.gate-wrap.solo{grid-template-columns:1fr;max-width:640px}
.gate-kicker{font:600 10px var(--mono);letter-spacing:.3em;color:var(--red);margin-bottom:18px}
.gate-brand h1{font:700 clamp(52px,7.5vw,96px)/.95 var(--disp)}
.gate-brand h1 span{color:var(--amber)}
.gate-sub{font:500 10.5px var(--mono);letter-spacing:.22em;color:var(--dim);margin-top:14px}
.gate-status{margin-top:36px;list-style:none;border-top:1px solid var(--line)}
.gate-status li{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:11px 2px;border-bottom:1px solid rgba(30,44,51,.6);font:500 11px var(--mono);letter-spacing:.1em}
.gate-status li span{color:var(--faint)}
.gate-status li b{color:var(--dim);font-weight:500;display:flex;align-items:center;gap:7px}
.gate-console{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--line-hi);box-shadow:0 40px 90px -30px #000}
.console-body{padding:22px 24px 26px}
.console-body.center{text-align:center;padding:44px 30px}
.boot{margin:4px 0 20px;display:grid;gap:5px}
.boot-line{font:400 12px var(--mono);color:var(--faint);opacity:0;animation:bootin .4s forwards;animation-delay:var(--d)}
@keyframes bootin{to{opacity:1}}
.cursor{color:var(--green);animation:blink 1s steps(1) infinite;margin-left:4px}
@keyframes blink{50%{opacity:0}}
.gate-error{background:rgba(255,93,93,.1);border:1px solid rgba(255,93,93,.4);color:#ffb3b3;font:500 12px var(--mono);padding:10px 12px;margin-bottom:16px;line-height:1.6}
.gate-foot{margin-top:18px;font:400 9.5px var(--mono);letter-spacing:.18em;color:var(--faint);text-align:center}
.shake{animation:shake .45s}
@keyframes shake{20%{transform:translateX(-9px)}40%{transform:translateX(7px)}60%{transform:translateX(-5px)}80%{transform:translateX(3px)}}
.home-grid{display:grid;margin:8px 0 16px;border:1px solid var(--line)}
.home-grid div{display:flex;justify-content:space-between;padding:11px 14px;border-bottom:1px solid rgba(30,44,51,.6);font-size:12px;letter-spacing:.06em}
.home-grid div:last-child{border-bottom:0}
.home-grid span{color:var(--faint)}.home-grid b{font-weight:600}
.portal-list{border:1px solid var(--line);margin-bottom:16px;max-height:260px}
.portal-actions{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}
.err-code{font:700 84px/1 var(--disp);color:var(--red);text-shadow:0 0 30px rgba(255,93,93,.4)}
.err-msg{font:600 13px var(--mono);letter-spacing:.1em;margin:14px 0 10px}
.topbar{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:13px 26px;border-bottom:1px solid var(--line);background:rgba(13,20,24,.88);backdrop-filter:blur(6px);position:sticky;top:0;z-index:20}
.brand{font:700 17px var(--disp);letter-spacing:.1em;display:flex;align-items:center;gap:10px}
.brand-mark{color:var(--amber);font-size:20px}
.brand-tag{font:600 9px var(--mono);letter-spacing:.18em;color:var(--faint);border:1px solid var(--line);padding:3px 8px}
.top-right{display:flex;align-items:center;gap:14px}
.clock{font:500 12px var(--mono);letter-spacing:.12em;color:var(--dim)}
.chip{display:inline-flex;align-items:center;gap:8px;font:600 11px var(--mono);letter-spacing:.1em;border:1px solid var(--line-hi);padding:7px 12px;background:#101a1f}
.deck{max-width:1440px;margin:0 auto;padding:0 26px 40px}
.credit{margin-top:34px;text-align:center;font:500 10px var(--mono);letter-spacing:.24em;color:var(--faint)}
.credit span{color:var(--amber)}
.readout{display:flex;border:1px solid var(--line);background:linear-gradient(180deg,var(--panel),var(--panel2));margin:22px 0 18px}
.stat{flex:1;padding:16px 22px;border-right:1px solid var(--line)}
.stat:last-child{border-right:0}
.stat-num{font:700 34px/1.1 var(--disp);display:block}
.stat-num.bump{animation:bump .45s}
@keyframes bump{30%{transform:scale(1.2);color:var(--amber)}}
.stat-key{font:500 10px var(--mono);letter-spacing:.18em;color:var(--faint)}
.grid{display:grid;grid-template-columns:1.65fr 1fr;gap:18px;align-items:start}
.rail{display:grid;gap:18px}
.panel{position:relative;background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--line)}
.panel::before,.panel::after{content:"";position:absolute;width:10px;height:10px;border:1px solid var(--line-hi)}
.panel::before{top:-1px;left:-1px;border-right:0;border-bottom:0}
.panel::after{bottom:-1px;right:-1px;border-left:0;border-top:0}
.panel-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 16px;border-bottom:1px solid var(--line)}
.panel-title{font:600 12px var(--disp);letter-spacing:.22em}
.panel-title::before{content:"\25AE ";color:var(--amber)}
.panel-tools{display:flex;gap:8px;align-items:center}
.config-row{display:flex;gap:8px;padding:14px 16px;align-items:center}
.config-row .field-in{flex:1}
.config-hint{padding:0 16px 12px;margin:0}
.table-wrap{overflow-x:auto}
.tbl{width:100%;border-collapse:collapse}
.tbl th{font:500 10.5px var(--mono);letter-spacing:.16em;color:var(--faint);text-align:left;padding:10px 14px;border-bottom:1px solid var(--line)}
.tbl td{padding:12px 14px;border-bottom:1px solid rgba(30,44,51,.55);vertical-align:middle}
.tbl tbody tr{transition:background .15s,box-shadow .15s}
.tbl tbody tr:hover{background:rgba(91,200,255,.045);box-shadow:inset 2px 0 0 var(--cyan)}
tr.flash{animation:rowflash 1s ease-out}
@keyframes rowflash{0%{background:rgba(255,180,84,.22)}100%{background:transparent}}
.row-empty{color:var(--faint);font:400 12px var(--mono);text-align:center;padding:22px!important;letter-spacing:.1em;list-style:none}
.u-name{font:600 13.5px var(--mono)}
.pill{display:inline-flex;align-items:center;gap:6px;font:600 10px var(--mono);letter-spacing:.12em;padding:4px 9px;border:1px solid var(--line)}
.pill-ok{color:var(--green);border-color:rgba(67,217,163,.35);background:rgba(67,217,163,.07)}
.pill-off{color:var(--faint)}
.meter{width:76px;height:5px;background:#0a1013;border:1px solid var(--line);position:relative;margin-top:5px}
.meter i{position:absolute;inset:0;transform-origin:left;background:var(--green);transition:transform .4s}
.meter.hot i{background:var(--amber)}.meter.full i{background:var(--red)}
.asl{display:inline-flex;align-items:center;border:1px solid var(--line-hi);background:#0d1519}
.asl button{width:27px;height:27px;background:none;border:0;color:var(--dim);font:600 15px var(--mono);cursor:pointer;transition:.15s}
.asl button:hover{color:var(--amber);background:rgba(255,180,84,.1)}
.asl output{min-width:36px;text-align:center;font:600 13px var(--mono)}
.sess-list{list-style:none;max-height:340px;overflow:auto}
.sess-list li{display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid rgba(30,44,51,.55);font:400 12px var(--mono);animation:slidein .3s both}
@keyframes slidein{from{opacity:0;transform:translateX(9px)}}
.s-user{font-weight:600}
.you{font-style:normal;color:var(--amber);font-size:9px;letter-spacing:.14em;border:1px solid rgba(255,180,84,.4);padding:1px 5px}
.s-meta{flex:1;color:var(--faint);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.s-meta .ago{font-style:normal;margin-left:6px;color:var(--dim)}
.s-role{font-size:9.5px;letter-spacing:.14em;color:var(--cyan);border:1px solid rgba(91,200,255,.3);padding:2px 6px}
.log-list{list-style:none;max-height:300px;overflow:auto}
.log-list li{display:flex;gap:9px;align-items:baseline;padding:8px 14px;border-bottom:1px solid rgba(30,44,51,.5);font-size:12.5px}
.log-list li.fresh{animation:slidein .35s both}
.log-txt{color:var(--dim);flex:1;line-height:1.45}
.log-ts{font:400 10.5px var(--mono);color:var(--faint);white-space:nowrap;font-style:normal}
.k-auth{background:var(--green)}
.k-auth_fail,.k-user_delete,.k-session_kill{background:var(--red)}
.k-as_block,.k-as_enforce,.k-lockout,.k-pass_reset{background:var(--amber)}
.k-user_create,.k-user_edit,.k-cred_upgrade,.k-config{background:var(--cyan)}
.modal-backdrop{position:fixed;inset:0;background:rgba(5,9,11,.74);display:flex;align-items:center;justify-content:center;z-index:60;opacity:0;transition:opacity .2s}
.modal-backdrop.open{opacity:1}
.modal{width:min(440px,92vw);background:var(--panel);border:1px solid var(--line-hi);box-shadow:0 30px 80px -20px #000,0 0 0 1px rgba(91,200,255,.07);transform:translateY(12px);transition:transform .22s}
.modal-backdrop.open .modal{transform:none}
.modal-x{background:none;border:0;color:var(--dim);cursor:pointer;font-size:13px;transition:.15s}
.modal-x:hover{color:var(--red)}
.modal form{padding:20px 22px}
.modal-foot{display:flex;justify-content:flex-end;gap:8px;margin-top:4px}
#toasts{position:fixed;right:20px;bottom:20px;z-index:80;display:flex;flex-direction:column;gap:8px}
.toast{background:var(--panel);border:1px solid var(--line-hi);border-left:3px solid var(--cyan);padding:11px 16px;font:500 12.5px var(--mono);box-shadow:0 12px 30px -10px #000;animation:toastin .25s;max-width:340px}
.toast.ok{border-left-color:var(--green)}.toast.err{border-left-color:var(--red)}.toast.warn{border-left-color:var(--amber)}
@keyframes toastin{from{opacity:0;transform:translateX(16px)}}
@media(max-width:1080px){
  .grid{grid-template-columns:1fr}
  .gate-wrap{grid-template-columns:1fr;gap:36px;padding-top:64px}
  .readout{flex-wrap:wrap}
  .stat{flex:1 1 45%;border-bottom:1px solid var(--line)}
}
"""

# ═══════════════════════ EMBEDDED JS ═══════════════════════
GUARD_JS = r"""
const $=s=>document.querySelector(s);
const $$=s=>[...document.querySelectorAll(s)];
const CSRF=document.querySelector('meta[name="csrf-token"]')?.content||"";
async function api(path,opts={}){
  const res=await fetch(path,{headers:{"Content-Type":"application/json","X-CSRF-Token":CSRF},...opts});
  if(res.status===401){location.href="/auth/login";throw new Error("session expired")}
  const data=await res.json().catch(()=>({}));
  if(!res.ok||!data.ok)throw new Error(data.error||res.statusText);
  return data;
}
function toast(msg,kind="ok"){
  const t=document.createElement("div");
  t.className="toast "+kind;t.textContent=msg;
  $("#toasts").appendChild(t);
  setTimeout(()=>{t.style.opacity="0";t.style.transition=".3s";setTimeout(()=>t.remove(),300)},3400);
}
function esc(s){const el=document.createElement("i");el.textContent=s??"";return el.innerHTML}
function rel(ts){
  const d=Math.max(0,(Date.now()/1000|0)-ts);
  if(d<8)return"just now";if(d<60)return d+"s ago";
  if(d<3600)return(d/60|0)+"m ago";if(d<86400)return(d/3600|0)+"h ago";
  return(d/86400|0)+"d ago";
}
function refreshTimes(){$$("[data-ago]").forEach(el=>el.textContent=rel(+el.dataset.ago))}
setInterval(refreshTimes,5000);refreshTimes();
setInterval(()=>{const el=$("#clock");if(el)el.textContent=new Date().toISOString().slice(11,19)+" UTC"},1000);
if(document.body.classList.contains("gate")){
  setInterval(()=>{const gc=$("#gate-clock");if(gc)gc.textContent=new Date().toISOString().slice(11,19)+" UTC"},1000);
}
if(document.body.classList.contains("console")){
  let USERS=[],editing=null,passWho=null,sessSig="",evSig="";
  function setNum(sel,val){
    const el=$(sel);
    if(el.textContent!==String(val)){el.textContent=val;el.classList.remove("bump");void el.offsetWidth;el.classList.add("bump")}
  }
  async function loadStats(){
    const d=await api("/api/stats");
    setNum("#st-users",d.stats.users);setNum("#st-sessions",d.stats.sessions);
    setNum("#st-limit",d.stats.at_limit);setNum("#st-disabled",d.stats.disabled);
  }
  async function loadUsers(){const d=await api("/api/users");USERS=d.users;renderUsers()}
  function renderUsers(){
    const q=($("#user-search").value||"").toLowerCase();
    const rows=USERS.filter(u=>!q||u.username.includes(q));
    const body=$("#users-body");
    if(!rows.length){body.innerHTML='<tr><td colspan="5" class="row-empty">no users \u2014 add one or edit users.txt</td></tr>';return}
    body.innerHTML=rows.map(u=>`
      <tr data-user="${esc(u.username)}">
        <td><span class="u-name">@${esc(u.username)}</span></td>
        <td>${u.enabled?'<span class="pill pill-ok"><b class="dot dot-live"></b>ACTIVE</span>':'<span class="pill pill-off">OFF</span>'}</td>
        <td><span class="mono ${u.at_limit?"warn":""}">${u.sessions}/${u.as}</span>
            <div class="meter ${u.sessions>=u.as?"full":u.sessions>=u.as-1?"hot":""}">
              <i style="transform:scaleX(${Math.min(1,u.sessions/u.as)})"></i></div></td>
        <td><div class="asl">
              <button type="button" data-asl="dec" title="decrease AS">\u2212</button>
              <output>${u.as}</output>
              <button type="button" data-asl="inc" title="increase AS">+</button>
            </div></td>
        <td class="ta-r">
          <button class="btn-ico" data-act="pass" title="reset passkey">\u27F3</button>
          <button class="btn-ico" data-act="edit" title="edit (AS / enable)">\u270E</button>
          <button class="btn-ico" data-act="kick" title="force logout all sessions" ${u.sessions?"":"disabled"}>\u23FB</button>
          <button class="btn-ico btn-ico-danger" data-act="del" title="delete user">\u2715</button>
        </td>
      </tr>`).join("");
  }
  function flashRow(user){const tr=$(`tr[data-user="${user}"]`);if(tr){tr.classList.add("flash");setTimeout(()=>tr.classList.remove("flash"),1000)}}
  function confirmThen(btn,fn){
    if(btn.dataset.armed){fn();return}
    btn.dataset.armed="1";const old=btn.textContent;
    btn.textContent="!";btn.classList.add("armed");
    setTimeout(()=>{if(btn.isConnected){btn.dataset.armed="";btn.textContent=old;btn.classList.remove("armed")}},2600);
  }
  $("#users-body").addEventListener("click",async e=>{
    const btn=e.target.closest("button");if(!btn||btn.disabled)return;
    const user=btn.closest("tr").dataset.user;
    try{
      if(btn.dataset.asl){
        const u=USERS.find(x=>x.username===user);
        const next=btn.dataset.asl==="inc"?u.as+1:u.as-1;
        if(next<1)return toast("AS minimum is 1","warn");
        await api(`/api/users/${user}`,{method:"PATCH",body:JSON.stringify({as:next})});
        toast(`${user} AS \u2192 ${next}${next<u.as?" \u00B7 excess sessions evicted":""}`,next<u.as?"warn":"ok");
        await Promise.all([loadUsers(),loadSessions(),loadStats()]);
        flashRow(user);
      }else if(btn.dataset.act==="pass")openPass(user);
      else if(btn.dataset.act==="edit")openEdit(user);
      else if(btn.dataset.act==="kick"){
        await api(`/api/users/${user}/kill-all`,{method:"POST"});
        toast(`all sessions of ${user} terminated`,"warn");
        loadUsers();loadSessions();loadStats();
      }else if(btn.dataset.act==="del"){
        confirmThen(btn,async()=>{
          await api(`/api/users/${user}`,{method:"DELETE"});
          toast(`user ${user} deleted`,"err");
          loadUsers();loadSessions();loadStats();
        });
      }
    }catch(err){toast(err.message,"err")}
  });
  $("#user-search").addEventListener("input",renderUsers);
  async function loadSessions(){
    const d=await api("/api/sessions");
    $("#sess-count").textContent=d.sessions.length+" tracked";
    const sig=JSON.stringify(d.sessions.map(s=>[s.id,s.user,s.last_seen,s.current]));
    if(sig===sessSig)return;
    sessSig=sig;
    const list=$("#sess-list");
    if(!d.sessions.length){list.innerHTML='<li class="row-empty">no live sessions</li>';return}
    list.innerHTML=d.sessions.map(s=>`
      <li data-token="${esc(s.id)}">
        <b class="dot ${s.role==="admin"?"dot-admin":"dot-live"}"></b>
        <span class="s-user">${esc(s.user)}${s.current?' <em class="you">YOU</em>':""}</span>
        <span class="s-meta">${esc(s.ip)} \u00B7 <i data-ago="${s.last_seen}"></i></span>
        <span class="s-role">${s.role}</span>
        <button class="btn-ico btn-ico-danger" data-kill title="terminate session">\u23FB</button>
      </li>`).join("");
    refreshTimes();
  }
  $("#sess-list").addEventListener("click",async e=>{
    const btn=e.target.closest("[data-kill]");if(!btn)return;
    try{
      await api(`/api/sessions/${btn.closest("li").dataset.token}/kill`,{method:"POST"});
      toast("session terminated","warn");
      loadSessions();loadUsers();loadStats();
    }catch(err){toast(err.message,"err")}
  });
  async function loadEvents(){
    const d=await api("/api/events");
    const sig=d.events.length+":"+(d.events[0]?.ts||0);
    if(sig===evSig)return;
    const known=evSig!=="";evSig=sig;
    $("#log-list").innerHTML=d.events.map((ev,i)=>`
      <li class="${known&&i<2?"fresh":""}">
        <b class="dot k-${esc(ev.kind)}"></b>
        <span class="log-txt">${esc(ev.detail)}</span>
        <i class="log-ts" data-ago="${ev.ts}"></i>
      </li>`).join("")||'<li class="row-empty">log empty</li>';
    refreshTimes();
  }
  const btnSave=$("#btn-save-target");
  if(btnSave)btnSave.onclick=async()=>{
    const t=$("#cfg-target").value.trim();
    if(!t)return toast("target address required","err");
    try{
      await api("/api/config",{method:"POST",body:JSON.stringify({target:t})});
      toast("gateway target updated \u2014 live, no restart needed","ok");
      const st=$("#cfg-status");if(st){st.textContent="SAVED";setTimeout(()=>st.textContent="",2500)}
    }catch(err){toast(err.message,"err")}
  };
  function openModal(id){const m=$(id);m.hidden=false;requestAnimationFrame(()=>m.classList.add("open"))}
  function closeModal(m){m.classList.remove("open");setTimeout(()=>m.hidden=true,200)}
  $$(".modal-backdrop").forEach(m=>
    m.addEventListener("click",e=>{if(e.target===m||e.target.closest("[data-close]"))closeModal(m)}));
  $("#btn-new-user").onclick=()=>{
    editing=null;
    $("#modal-user-title").textContent="NEW USER";
    $("#f-username").disabled=false;$("#f-username").value="";
    $("#f-pass").value="";$("#f-as").value=1;
    $("#passrow").hidden=false;$("#enablerow").hidden=true;
    openModal("#modal-user");
  };
  function openEdit(user){
    const u=USERS.find(x=>x.username===user);if(!u)return;
    editing=user;
    $("#modal-user-title").textContent="EDIT \u2014 @"+user;
    $("#f-username").value=user;$("#f-username").disabled=true;
    $("#f-as").value=u.as;$("#f-enabled").checked=u.enabled;
    $("#passrow").hidden=true;$("#enablerow").hidden=false;
    openModal("#modal-user");
  }
  $("#form-user").onsubmit=async e=>{
    e.preventDefault();
    try{
      if(editing){
        await api(`/api/users/${editing}`,{method:"PATCH",body:JSON.stringify({as:+$("#f-as").value||1,enabled:$("#f-enabled").checked})});
        toast("user updated","ok");
      }else{
        await api("/api/users",{method:"POST",body:JSON.stringify({username:$("#f-username").value.trim(),password:$("#f-pass").value,as:+$("#f-as").value||1})});
        toast("user provisioned \u2192 users.txt","ok");
      }
      closeModal($("#modal-user"));loadUsers();loadStats();
    }catch(err){toast(err.message,"err")}
  };
  function openPass(user){
    passWho=user;$("#pass-who").textContent="@"+user;
    $("#pass-new").value="";$("#pass-confirm").value="";
    openModal("#modal-pass");
  }
  $("#form-pass").onsubmit=async e=>{
    e.preventDefault();
    const p1=$("#pass-new").value,p2=$("#pass-confirm").value;
    if(p1!==p2)return toast("passkeys do not match","err");
    try{
      await api(`/api/users/${passWho}/password`,{method:"POST",body:JSON.stringify({password:p1})});
      toast(`passkey reset for ${passWho} \u2014 sessions revoked`,"ok");
      closeModal($("#modal-pass"));loadSessions();loadUsers();
    }catch(err){toast(err.message,"err")}
  };
  (async function boot(){
    await Promise.all([loadStats(),loadUsers(),loadSessions(),loadEvents()]);
    setInterval(()=>{loadStats();loadUsers();loadSessions()},5000);
    setInterval(loadEvents,4000);
  })();
}
"""

# ═══════════════════════ EMBEDDED TEMPLATES ═══════════════════════
_HTML_HEAD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/sg-static/guard.css">
{{ extra_head }}</head>
<body class="{{ bodyclass }}">
<div class="bg-glow" aria-hidden="true"></div>
<div class="bg-grid" aria-hidden="true"></div>
<div class="scanlines" aria-hidden="true"></div>
"""
_HTML_FOOT = """
<script src="/sg-static/guard.js"></script></body></html>"""

TPL_LOGIN = _HTML_HEAD + r"""
<main class="gate-wrap">
  <section class="gate-brand">
    <p class="gate-kicker">SECURE GATEWAY // AUTHENTICATION REQUIRED</p>
    <h1>SESSION<span>GUARD</span></h1>
    <p class="gate-sub">AUTH GATEWAY &middot; SESSION ENFORCEMENT &middot; AS LIMITS</p>
    <ul class="gate-status">
      <li><span>GATEWAY STATE</span><b class="ok">ARMED <i class="dot dot-live"></i></b></li>
      <li><span>TARGET BACKEND</span><b>{{ backend }}</b></li>
      <li><span>CREDENTIAL STORE</span><b>users.txt &middot; PBKDF2-SHA256</b></li>
      <li><span>GUARDS</span><b class="ok">CSRF &middot; LOCKOUT &middot; AS</b></li>
      <li><span>GATEWAY TIME</span><b id="gate-clock">--:--:--</b></li>
    </ul>
  </section>
  <section class="gate-console {{ 'shake' if shake else '' }}">
    <header class="console-bar">
      <span class="bar-dots"><i></i><i></i><i></i></span>
      <span class="bar-title">SESSIONGUARD &middot; ACCESS GATE</span>
      <span class="bar-tty">TTY-01 <b class="dot dot-live"></b></span>
    </header>
    <div class="console-body">
      <div class="boot">
        <p class="boot-line" style="--d:.1s">SessionGuard v1.0 &mdash; auth gateway online</p>
        <p class="boot-line" style="--d:.5s">csrf guard armed &middot; bruteforce lockout armed &middot; AS policy enforcing</p>
        <p class="boot-line" style="--d:.9s">present credentials<span class="cursor">&#9610;</span></p>
      </div>
      {% if error %}<div class="gate-error">&#9650; {{ error }}</div>{% endif %}
      <form method="post" class="gate-form" autocomplete="off">
        <input type="hidden" name="csrf_token" value="{{ pre }}">
        <input type="hidden" name="next" value="{{ next }}">
        <label class="field"><span class="field-key">OPERATOR ID</span>
          <input class="field-in" name="username" required autofocus spellcheck="false"></label>
        <label class="field"><span class="field-key">PASSKEY</span>
          <input class="field-in" type="password" name="password" required></label>
        <button class="btn btn-amber btn-block" type="submit">AUTHENTICATE <span class="arr">&rarr;</span></button>
      </form>
      <footer class="gate-foot">ALL ACTIVITY IS LOGGED &middot; MADE BY ARYAN GIRI | GIRIARYAN694-A11Y</footer>
    </div>
  </section>
</main>
""" + _HTML_FOOT

TPL_ADMIN = _HTML_HEAD + r"""
<meta name="csrf-token" content="{{ csrf }}">
<header class="topbar">
  <div class="brand"><span class="brand-mark">&#9698;</span>SESSIONGUARD <span class="brand-tag">ADMIN</span></div>
  <div class="top-right">
    <span class="clock" id="clock">--:--:-- UTC</span>
    <span class="chip"><b class="dot dot-live"></b>{{ admin }}</span>
    <form method="post" action="/auth/logout" class="inline">
      <input type="hidden" name="csrf_token" value="{{ csrf }}">
      <button class="btn" type="submit">LOG OUT</button>
    </form>
  </div>
</header>
<main class="deck">
  <section class="readout">
    <div class="stat"><span class="stat-num" id="st-users">0</span><span class="stat-key">USERS IN users.txt</span></div>
    <div class="stat"><span class="stat-num" id="st-sessions">0</span><span class="stat-key">LIVE SESSIONS</span></div>
    <div class="stat"><span class="stat-num warn" id="st-limit">0</span><span class="stat-key">AT AS LIMIT</span></div>
    <div class="stat"><span class="stat-num" id="st-disabled">0</span><span class="stat-key">DISABLED</span></div>
  </section>
  <section class="panel" style="margin-bottom:18px">
    <header class="panel-head">
      <h2 class="panel-title">GATEWAY TARGET</h2>
      <span class="dim mono" id="cfg-status"></span>
    </header>
    <div class="config-row">
      <input class="field-in" id="cfg-target" value="{{ backend }}" spellcheck="false" placeholder="http://127.0.0.1:8080">
      <button class="btn btn-amber" id="btn-save-target">SAVE ROUTE</button>
    </div>
    <p class="hint config-hint">Where authenticated traffic is forwarded. Change live &mdash; no restart needed. Keep your tool bound to 127.0.0.1.</p>
  </section>
  <div class="grid">
    <section class="panel">
      <header class="panel-head">
        <h2 class="panel-title">USER REGISTRY</h2>
        <div class="panel-tools">
          <input id="user-search" class="field-in field-sm" placeholder="filter&hellip;" spellcheck="false">
          <button class="btn btn-amber" id="btn-new-user">+ NEW USER</button>
        </div>
      </header>
      <div class="table-wrap">
        <table class="tbl">
          <thead><tr><th>USER</th><th>STATUS</th><th>SESSIONS</th><th>AS LIMIT</th><th class="ta-r">ACTIONS</th></tr></thead>
          <tbody id="users-body"><tr><td colspan="5" class="row-empty">loading registry&hellip;</td></tr></tbody>
        </table>
      </div>
    </section>
    <aside class="rail">
      <section class="panel">
        <header class="panel-head"><h2 class="panel-title">LIVE SESSIONS</h2><span class="dim mono" id="sess-count"></span></header>
        <ul class="sess-list" id="sess-list"><li class="row-empty">scanning&hellip;</li></ul>
      </section>
      <section class="panel">
        <header class="panel-head"><h2 class="panel-title">ACTIVITY LOG</h2><b class="dot dot-live"></b></header>
        <ul class="log-list" id="log-list"><li class="row-empty">log empty</li></ul>
      </section>
    </aside>
  </div>
  <footer class="credit">SESSIONGUARD &mdash; MADE BY ARYAN GIRI <span>|</span> GIRIARYAN694-A11Y</footer>
</main>
<div class="modal-backdrop" id="modal-user" hidden>
  <div class="modal">
    <header class="console-bar"><span class="bar-title" id="modal-user-title">NEW USER</span><button class="modal-x" data-close type="button">&#10005;</button></header>
    <form id="form-user">
      <label class="field"><span class="field-key">USERNAME</span><input class="field-in" id="f-username" spellcheck="false"></label>
      <label class="field" id="passrow"><span class="field-key">PASSKEY (min 8)</span><input class="field-in" id="f-pass" type="password"></label>
      <label class="field"><span class="field-key">AS &mdash; ALLOWED SESSIONS</span><input class="field-in" id="f-as" type="number" min="1" max="50" value="1"></label>
      <label class="field check" id="enablerow" hidden><input type="checkbox" id="f-enabled" checked><span>ACCOUNT ENABLED</span></label>
      <footer class="modal-foot"><button class="btn" type="button" data-close>CANCEL</button><button class="btn btn-amber" type="submit">COMMIT</button></footer>
    </form>
  </div>
</div>
<div class="modal-backdrop" id="modal-pass" hidden>
  <div class="modal">
    <header class="console-bar"><span class="bar-title">RESET PASSKEY &mdash; <span id="pass-who"></span></span><button class="modal-x" data-close type="button">&#10005;</button></header>
    <form id="form-pass">
      <label class="field"><span class="field-key">NEW PASSKEY (min 8)</span><input class="field-in" id="pass-new" type="password" required minlength="8"></label>
      <label class="field"><span class="field-key">CONFIRM</span><input class="field-in" id="pass-confirm" type="password" required></label>
      <p class="hint">&#9650; all live sessions of this user are revoked on reset.</p>
      <footer class="modal-foot"><button class="btn" type="button" data-close>CANCEL</button><button class="btn btn-amber" type="submit">RESET</button></footer>
    </form>
  </div>
</div>
<div id="toasts"></div>
""" + _HTML_FOOT

TPL_PORTAL = _HTML_HEAD + r"""
<main class="gate-wrap solo">
  <section class="gate-console">
    <header class="console-bar">
      <span class="bar-dots"><i></i><i></i><i></i></span>
      <span class="bar-title">SESSIONGUARD &middot; SESSION PORTAL</span>
      <span class="bar-tty"><b class="dot dot-live"></b> LIVE</span>
    </header>
    <div class="console-body">
      {% if error %}<div class="gate-error">&#9650; {{ error }}</div>{% endif %}
      <div class="home-grid mono">
        <div><span>OPERATOR</span><b>@{{ user }}</b></div>
        <div><span>ALLOWED SESSIONS (AS)</span><b>{{ as_limit }}</b></div>
        <div><span>ACTIVE NOW</span><b>{{ sessions|length }} / {{ as_limit }}</b></div>
      </div>
      <p class="hint">Free up a slot by ending a session below &mdash; then log in from your other device.</p>
      <ul class="sess-list portal-list">
        {% for s in sessions %}
        <li>
          <b class="dot {{ 'dot-admin' if s.role == 'admin' else 'dot-live' }}"></b>
          <span class="s-meta">{{ s.ip }} &middot; {{ s.ua or "unknown client" }}
            <i class="ago" data-ago="{{ s.last_seen }}"></i></span>
          {% if s.current %}<em class="you">THIS DEVICE</em>{% endif %}
          <form method="post" class="inline">
            <input type="hidden" name="csrf_token" value="{{ csrf }}">
            <input type="hidden" name="action" value="logout-one">
            <input type="hidden" name="sid" value="{{ s.sid }}">
            <button class="btn-ico btn-ico-danger" title="end this session">&#9211;</button>
          </form>
        </li>
        {% endfor %}
      </ul>
      <div class="portal-actions">
        <a class="btn" href="/">&larr; BACK TO TOOL</a>
        <form method="post" class="inline">
          <input type="hidden" name="csrf_token" value="{{ csrf }}">
          <input type="hidden" name="action" value="logout-all">
          <button class="btn btn-danger" type="submit">END ALL MY SESSIONS</button>
        </form>
      </div>
      <footer class="gate-foot">SESSIONGUARD &middot; MADE BY ARYAN GIRI | GIRIARYAN694-A11Y</footer>
    </div>
  </section>
</main>
""" + _HTML_FOOT

TPL_DOWN = _HTML_HEAD + r"""
<main class="gate-wrap solo">
  <section class="gate-console">
    <header class="console-bar">
      <span class="bar-dots"><i></i><i></i><i></i></span>
      <span class="bar-title">SESSIONGUARD &middot; UPSTREAM ERROR</span>
    </header>
    <div class="console-body center">
      <p class="err-code">502</p>
      <p class="err-msg">BACKEND UNREACHABLE &mdash; <span class="mono">{{ backend }}</span></p>
      <p class="hint">Is your tool running there? Set the target from /admin &rarr; GATEWAY TARGET.</p>
      <a class="btn" href="/">RETRY GATEWAY</a>
    </div>
  </section>
</main>
""" + _HTML_FOOT

# ═══════════════════════ STORAGE ═══════════════════════
def _now(): return int(time.time())

def _load(p, default):
    if not p.exists(): return default
    try: return json.loads(p.read_text())
    except json.JSONDecodeError: return default

def _save(p, obj):
    DATA.mkdir(exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    os.replace(tmp, p)
    os.chmod(p, 0o600)

# ═══════════════════════ GATEWAY CONFIG ═══════════════════════
def load_config():
    return _load(CONFIG_DB, {"target": "http://127.0.0.1:8080"})

def save_config(cfg):
    _save(CONFIG_DB, cfg)

def get_target():
    return load_config().get("target", "http://127.0.0.1:8080")

# ═══════════════════════ CRYPTO ═══════════════════════
def hash_password(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), ROUNDS)
    return f"{salt}${dk.hex()}"

def verify_password(pw, stored):
    try:
        salt, expected = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), ROUNDS)
        return hmac.compare_digest(dk.hex(), expected)
    except (ValueError, TypeError):
        return False

def read_admin_record():
    if not ADMIN_AUTH.exists(): return None, None
    line = ADMIN_AUTH.read_text().strip().splitlines()[0]
    if "|" not in line: return None, None
    n, r = line.split("|", 1)
    return n.strip(), r.strip()

def write_admin_record(name, pw):
    ADMIN_AUTH.write_text(f"{name}|{hash_password(pw)}\n")
    os.chmod(ADMIN_AUTH, 0o600)

# ═══════════════════════ USERS.TXT ═══════════════════════
def load_users():
    users = {}
    if not USERS_TXT.exists(): return users
    for raw in USERS_TXT.read_text().splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"): continue
        m = LINE_RE.match(raw)
        if not m: continue
        users[m.group(1).lower()] = {
            "cred": m.group(2),
            "as": max(1, min(50, int(m.group(3) or 1))),
            "enabled": m.group(4) is None,
        }
    return users

def save_users(users):
    lines = ["# SessionGuard users — user:credential AS:<allowed sessions> [OFF]",
             "# plaintext credentials are auto-hashed on first login"]
    for name, u in users.items():
        line = f"{name}:{u['cred']} AS:{u['as']}"
        if not u["enabled"]: line += " OFF"
        lines.append(line)
    tmp = USERS_TXT.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n")
    os.replace(tmp, USERS_TXT)
    os.chmod(USERS_TXT, 0o600)

def verify_user(name, pw, users):
    u = users.get(name)
    if not u: return False
    if CRED_HASH_RE.match(u["cred"]):
        return verify_password(pw, u["cred"])
    if hmac.compare_digest(pw, u["cred"]):
        u["cred"] = hash_password(pw)
        save_users(users)
        log_event("cred_upgrade", f"'{name}' plaintext credential auto-hashed on login")
        return True
    return False

# ═══════════════════════ SESSIONS ═══════════════════════
def load_sessions(): return _load(SESSIONS_DB, {})

def create_session(user, role, ip, ua):
    with _lock:
        sessions = load_sessions()
        token = secrets.token_urlsafe(32)
        sessions[token] = {"user": user, "role": role, "csrf": secrets.token_urlsafe(24),
                           "created": _now(), "last_seen": _now(),
                           "ip": ip, "ua": (ua or "")[:110]}
        _save(SESSIONS_DB, sessions)
    return token

def kill_token(token):
    with _lock:
        s = load_sessions()
        v = s.pop(token, None)
        if v: _save(SESSIONS_DB, s)
    return v

def kill_all_for(user, role="user"):
    with _lock:
        s = load_sessions()
        dead = [t for t, v in s.items() if v["user"] == user and v["role"] == role]
        for t in dead: del s[t]
        if dead: _save(SESSIONS_DB, s)
    return len(dead)

def count_sessions(user, role="user"):
    return sum(1 for v in load_sessions().values() if v["user"] == user and v["role"] == role)

def evict_excess(user, limit):
    with _lock:
        s = load_sessions()
        live = sorted(((t, v) for t, v in s.items() if v["user"] == user and v["role"] == "user"),
                      key=lambda kv: kv[1]["last_seen"])
        killed = 0
        while len(live) > limit:
            del s[live.pop(0)[0]]
            killed += 1
        if killed:
            _save(SESSIONS_DB, s)
            log_event("as_enforce", f"AS enforced for '{user}': {killed} oldest session(s) evicted")
    return killed

def purge_expired():
    cutoff = _now() - SESSION_TTL
    with _lock:
        s = load_sessions()
        dead = [t for t, v in s.items() if v["last_seen"] < cutoff]
        for t in dead: del s[t]
        if dead: _save(SESSIONS_DB, s)

def get_session():
    tok = request.cookies.get(SID_COOKIE)
    if not tok: return None, None
    s = load_sessions().get(tok)
    if not s: return None, None
    if s["last_seen"] < _now() - SESSION_TTL:
        kill_token(tok)
        return None, None
    return tok, s

def touch(tok, s):
    if _now() - s["last_seen"] > 30:
        with _lock:
            all_s = load_sessions()
            if tok in all_s:
                all_s[tok]["last_seen"] = _now()
                _save(SESSIONS_DB, all_s)

# ═══════════════════════ AUDIT ═══════════════════════
def log_event(kind, detail):
    with _lock:
        ev = _load(EVENTS_DB, [])
        ev.insert(0, {"ts": _now(), "kind": kind, "detail": detail})
        _save(EVENTS_DB, ev[:100])

# ═══════════════════════ HARDENING ═══════════════════════
def page(tpl, status=200, **ctx):
    ctx.setdefault("extra_head", "")
    resp = make_response(render_template_string(tpl, **ctx), status)
    resp.headers.update({"Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff",
                         "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                         "Cache-Control": "no-store"})
    return resp

def set_sid(resp, token):
    secure = request.headers.get("X-Forwarded-Proto", "") == "https"
    resp.set_cookie(SID_COOKIE, token, httponly=True, samesite="Lax",
                    max_age=SESSION_TTL, secure=secure, path="/")
    return resp

def safe_next(val):
    if val and val.startswith("/") and not val.startswith(("//", "/\\")):
        return val
    return "/"

def locked(key):
    return _fails.get(key, (0, 0))[1] > _now()

def record_fail(key):
    c, _ = _fails.get(key, (0, 0))
    c += 1
    _fails[key] = (c, _now() + LOCK_SECONDS if c >= LOCK_ATTEMPTS else 0)
    return c

def csrf_ok(sess):
    tok = request.form.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")
    if not tok: return False
    pre = request.cookies.get(PRE_COOKIE, "")
    if pre and hmac.compare_digest(tok, pre): return True
    return bool(sess) and hmac.compare_digest(tok, sess.get("csrf", ""))

def admin_required(fn):
    @wraps(fn)
    def w(*a, **k):
        tok, sess = get_session()
        if not sess or sess["role"] != "admin":
            if request.path.startswith("/api/"):
                return jsonify(ok=False, error="unauthorized"), 401
            return redirect(url_for("login"))
        touch(tok, sess)
        g.tok, g.sess = tok, sess
        return fn(*a, **k)
    return w

def admin_api(fn):
    @wraps(fn)
    def w(*a, **k):
        if request.method != "GET" and not csrf_ok(g.sess):
            return jsonify(ok=False, error="CSRF token invalid"), 403
        return fn(*a, **k)
    return admin_required(w)

# ═══════════════════════ STATIC ASSETS ═══════════════════════
@app.route("/sg-static/guard.css")
def sg_css():
    resp = make_response(GUARD_CSS)
    resp.headers["Content-Type"] = "text/css; charset=utf-8"
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp

@app.route("/sg-static/guard.js")
def sg_js():
    resp = make_response(GUARD_JS)
    resp.headers["Content-Type"] = "application/javascript; charset=utf-8"
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp

# ═══════════════════════ AUTH GATE ═══════════════════════
ERR_MAP = {"disabled": "ACCOUNT DISABLED — contact administrator",
           "expired":  "SESSION EXPIRED — authenticate again"}

@app.route("/auth/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        tok, sess = get_session()
        if sess:
            return redirect("/admin" if sess["role"] == "admin" else safe_next(request.args.get("next")))
        pre = secrets.token_urlsafe(24)
        resp = page(TPL_LOGIN, title="SessionGuard // AUTH REQUIRED", bodyclass="gate",
                    backend=get_target(), pre=pre, next=safe_next(request.args.get("next")),
                    error=ERR_MAP.get(request.args.get("err")))
        resp.set_cookie(PRE_COOKIE, pre, httponly=True, samesite="Lax", max_age=600)
        return resp
    ip = request.remote_addr or "?"
    name = request.form.get("username", "").strip()
    pw   = request.form.get("password", "")
    nxt  = safe_next(request.form.get("next"))
    if not csrf_ok(None):
        return _login_page("CSRF CHECK FAILED — reload and retry", nxt), 403
    if locked(f"ip:{ip}") or locked(f"u:{name.lower()}"):
        log_event("lockout", f"login locked for '{name}' / {ip}")
        return _login_page("BRUTEFORCE GUARD — too many attempts, locked 5 min", nxt), 423
    admin_name, admin_rec = read_admin_record()
    if admin_rec and admin_name and hmac.compare_digest(name, admin_name) and verify_password(pw, admin_rec):
        _fails.pop(f"ip:{ip}", None)
        resp = set_sid(make_response(redirect("/admin")),
                       create_session(name, "admin", ip, request.user_agent.string))
        log_event("auth", f"admin '{name}' logged in from {ip}")
        return resp
    users = load_users()
    key = name.lower()
    u = users.get(key)
    if u and u["enabled"] and verify_user(key, pw, users):
        _fails.pop(f"ip:{ip}", None)
        _fails.pop(f"u:{key}", None)
        if count_sessions(key) >= u["as"]:
            log_event("as_block", f"'{key}' denied: AS {u['as']} reached from {ip}")
            return _login_page(
                f"SESSION LIMIT REACHED (AS {u['as']}) — log out from your other device "
                f"at /auth/portal, or contact the administrator", nxt), 403
        resp = set_sid(make_response(redirect(nxt)),
                       create_session(key, "user", ip, request.user_agent.string))
        log_event("auth", f"user '{key}' logged in from {ip}")
        return resp
    record_fail(f"ip:{ip}")
    record_fail(f"u:{key}")
    log_event("auth_fail", f"failed login '{name}' from {ip}")
    return _login_page("ACCESS DENIED — invalid credentials", nxt), 401

def _login_page(error, nxt="/"):
    pre = secrets.token_urlsafe(24)
    resp = page(TPL_LOGIN, title="SessionGuard // AUTH REQUIRED", bodyclass="gate",
                backend=get_target(), pre=pre, next=nxt, error=error, shake=True)
    resp.set_cookie(PRE_COOKIE, pre, httponly=True, samesite="Lax", max_age=600)
    return resp

@app.route("/auth/logout", methods=["POST"])
def logout():
    tok, sess = get_session()
    if sess and csrf_ok(sess):
        kill_token(tok)
        log_event("auth", f"'{sess['user']}' logged out")
    resp = make_response(redirect(url_for("login")))
    resp.delete_cookie(SID_COOKIE)
    return resp

@app.route("/auth/portal", methods=["GET", "POST"])
def portal():
    tok, sess = get_session()
    if not sess:
        return redirect("/auth/login?next=/auth/portal")
    if request.method == "POST":
        if not csrf_ok(sess):
            return page(TPL_PORTAL, title="SessionGuard // MY SESSIONS", bodyclass="gate",
                        error="CSRF CHECK FAILED", **_portal_ctx(tok, sess)), 403
        action = request.form.get("action")
        if action == "logout-all":
            kill_all_for(sess["user"], sess["role"])
            log_event("session_kill", f"'{sess['user']}' ended all own sessions")
            resp = make_response(redirect(url_for("login")))
            resp.delete_cookie(SID_COOKIE)
            return resp
        if action == "logout-one":
            target = request.form.get("sid", "")
            victim = load_sessions().get(target)
            if victim and victim["user"] == sess["user"] and victim["role"] == sess["role"]:
                kill_token(target)
                log_event("session_kill", f"'{sess['user']}' ended own session ({victim['ip']})")
                if target == tok:
                    resp = make_response(redirect(url_for("login")))
                    resp.delete_cookie(SID_COOKIE)
                    return resp
        return redirect("/auth/portal")
    return page(TPL_PORTAL, title="SessionGuard // MY SESSIONS", bodyclass="gate",
                error=None, **_portal_ctx(tok, sess))

def _portal_ctx(tok, sess):
    mine = [{"sid": t, **v, "current": t == tok}
            for t, v in load_sessions().items()
            if v["user"] == sess["user"] and v["role"] == sess["role"]]
    mine.sort(key=lambda s: -s["last_seen"])
    u = load_users().get(sess["user"], {})
    return {"user": sess["user"], "role": sess["role"], "as_limit": u.get("as", "\u221e"),
            "sessions": mine, "csrf": sess["csrf"]}

# ═══════════════════════ ADMIN CONSOLE ═══════════════════════
@app.route("/admin")
@admin_required
def admin_panel():
    return page(TPL_ADMIN, title="SessionGuard // ADMIN", bodyclass="console",
                admin=g.sess["user"], backend=get_target(), csrf=g.sess["csrf"])

@app.route("/api/config")
@admin_required
def api_config():
    return jsonify(ok=True, config=load_config())

@app.route("/api/config", methods=["POST"])
@admin_api
def api_set_config():
    d = request.get_json(silent=True) or {}
    target = str(d.get("target", "")).strip()
    if not target:
        return jsonify(ok=False, error="target address required"), 400
    if not target.startswith(("http://", "https://")):
        target = "http://" + target
    cfg = load_config()
    old = cfg.get("target", "")
    cfg["target"] = target
    save_config(cfg)
    log_event("config", f"gateway target changed: {old} -> {target}")
    return jsonify(ok=True, target=target)

@app.route("/api/stats")
@admin_required
def api_stats():
    users, sessions = load_users(), load_sessions()
    live = {}
    for v in sessions.values():
        if v["role"] == "user":
            live[v["user"]] = live.get(v["user"], 0) + 1
    return jsonify(ok=True, stats={
        "users": len(users), "sessions": sum(live.values()),
        "at_limit": sum(1 for n, u in users.items() if u["enabled"] and live.get(n, 0) >= u["as"]),
        "disabled": sum(1 for u in users.values() if not u["enabled"]),
        "admins": sum(1 for v in sessions.values() if v["role"] == "admin")})

@app.route("/api/users")
@admin_required
def api_users():
    users, sessions = load_users(), load_sessions()
    out = []
    for name, u in users.items():
        live = sum(1 for v in sessions.values() if v["user"] == name and v["role"] == "user")
        out.append({"username": name, "as": u["as"], "enabled": u["enabled"],
                    "sessions": live, "at_limit": live >= u["as"]})
    out.sort(key=lambda x: x["username"])
    return jsonify(ok=True, users=out)

@app.route("/api/users", methods=["POST"])
@admin_api
def api_create_user():
    d = request.get_json(silent=True) or {}
    name = str(d.get("username", "")).strip().lower()
    pw   = str(d.get("password", ""))
    try:
        as_n = max(1, min(50, int(d.get("as", 1))))
    except (TypeError, ValueError):
        as_n = 1
    if not re.match(r"^[a-z0-9_.-]{2,32}$", name):
        return jsonify(ok=False, error="username: 2-32 chars, a-z 0-9 _ . -"), 400
    if len(pw) < 8:
        return jsonify(ok=False, error="passkey must be >= 8 characters"), 400
    users = load_users()
    admin_name, _ = read_admin_record()
    if name == (admin_name or "").lower():
        return jsonify(ok=False, error="reserved username"), 409
    if name in users:
        return jsonify(ok=False, error="user already exists"), 409
    users[name] = {"cred": hash_password(pw), "as": as_n, "enabled": True}
    save_users(users)
    log_event("user_create", f"user '{name}' provisioned (AS {as_n})")
    return jsonify(ok=True)

@app.route("/api/users/<u>", methods=["PATCH"])
@admin_api
def api_edit_user(u):
    users = load_users()
    if u not in users:
        return jsonify(ok=False, error="no such user"), 404
    d = request.get_json(silent=True) or {}
    changes = []
    if "enabled" in d:
        users[u]["enabled"] = bool(d["enabled"])
        changes.append("enabled" if users[u]["enabled"] else "disabled")
        if not users[u]["enabled"]:
            n = kill_all_for(u)
            if n:
                changes.append(f"{n} session(s) revoked")
    if "as" in d:
        try:
            new = max(1, min(50, int(d["as"])))
        except (TypeError, ValueError):
            return jsonify(ok=False, error="invalid AS"), 400
        old = users[u]["as"]
        users[u]["as"] = new
        changes.append(f"AS {old}->{new}")
        if new < old:
            k = evict_excess(u, new)
            if k:
                changes.append(f"{k} session(s) evicted")
    save_users(users)
    log_event("user_edit", f"'{u}' updated: {', '.join(changes)}")
    return jsonify(ok=True)

@app.route("/api/users/<u>/password", methods=["POST"])
@admin_api
def api_reset_pass(u):
    users = load_users()
    if u not in users:
        return jsonify(ok=False, error="no such user"), 404
    pw = str((request.get_json(silent=True) or {}).get("password", ""))
    if len(pw) < 8:
        return jsonify(ok=False, error="passkey must be >= 8 characters"), 400
    users[u]["cred"] = hash_password(pw)
    save_users(users)
    n = kill_all_for(u)
    log_event("pass_reset", f"passkey of '{u}' reset · {n} session(s) revoked")
    return jsonify(ok=True)

@app.route("/api/users/<u>/kill-all", methods=["POST"])
@admin_api
def api_kill_all(u):
    n = kill_all_for(u)
    log_event("session_kill", f"all sessions of '{u}' terminated by admin ({n})")
    return jsonify(ok=True, killed=n)

@app.route("/api/users/<u>", methods=["DELETE"])
@admin_api
def api_delete_user(u):
    users = load_users()
    if u not in users:
        return jsonify(ok=False, error="no such user"), 404
    del users[u]
    save_users(users)
    n = kill_all_for(u)
    log_event("user_delete", f"user '{u}' deleted · {n} session(s) purged")
    return jsonify(ok=True)

@app.route("/api/sessions")
@admin_required
def api_sessions():
    purge_expired()
    out = [{"id": t[:10], "user": v["user"], "role": v["role"], "ip": v["ip"], "ua": v["ua"],
            "created": v["created"], "last_seen": v["last_seen"], "current": t == g.tok}
           for t, v in load_sessions().items()]
    out.sort(key=lambda x: -x["last_seen"])
    return jsonify(ok=True, sessions=out)

@app.route("/api/sessions/<sid>/kill", methods=["POST"])
@admin_api
def api_kill(sid):
    with _lock:
        s = load_sessions()
        hits = [t for t in s if t.startswith(sid)]
        if not hits:
            return jsonify(ok=False, error="session not found"), 404
        victim = s.pop(hits[0])
        _save(SESSIONS_DB, s)
    log_event("session_kill", f"'{victim['user']}' session terminated by admin ({victim['ip']})")
    return jsonify(ok=True)

@app.route("/api/events")
@admin_required
def api_events():
    return jsonify(ok=True, events=_load(EVENTS_DB, [])[:30])

# ═══════════════════════ THE GATEWAY (reverse proxy) ═══════════════════════
STRIP_REQ  = {"host","content-length","connection","keep-alive","proxy-authenticate",
              "proxy-authorization","te","trailers","transfer-encoding","upgrade"}
STRIP_RESP = {"content-encoding","content-length","transfer-encoding","connection"}

@app.route("/", defaults={"path": ""}, methods=ALL_METHODS)
@app.route("/<path:path>", methods=ALL_METHODS)
def gateway(path):
    tok, sess = get_session()
    if request.method != "OPTIONS":
        if not sess:
            nxt = quote("/" + path + ("?" + request.query_string.decode() if request.query_string else ""))
            return redirect(f"/auth/login?next={nxt}")
        if sess["role"] == "user":
            u = load_users().get(sess["user"])
            if not u or not u["enabled"]:
                kill_token(tok)
                return redirect("/auth/login?err=disabled")
        touch(tok, sess)
    target = get_target()
    headers = {k: v for k, v in request.headers if k.lower() not in STRIP_REQ}
    kept = [p.strip() for p in request.headers.get("Cookie", "").split(";")
            if p.strip() and not p.strip().startswith((SID_COOKIE, PRE_COOKIE))]
    if kept:
        headers["Cookie"] = "; ".join(kept)
    else:
        headers.pop("Cookie", None)
    headers["X-Forwarded-For"] = request.remote_addr or ""
    headers["X-Forwarded-Proto"] = request.headers.get("X-Forwarded-Proto", "http")
    if sess:
        headers["X-SG-User"] = sess["user"]
    try:
        up = rq.request(request.method, f"{target.rstrip('/')}/{path}",
                        params=request.query_string.decode(), data=request.get_data(),
                        headers=headers, stream=True, timeout=(5, 300), allow_redirects=False)
    except rq.RequestException:
        return page(TPL_DOWN, title="SessionGuard // 502", bodyclass="gate", backend=target), 502
    resp = Response(up.iter_content(chunk_size=65536), status=up.status_code)
    for k, v in up.raw.headers.items():
        if k.lower() not in STRIP_RESP:
            resp.headers.add(k, v)
    return resp

# ═══════════════════════ CLI ═══════════════════════
def cli_set_admin():
    import getpass
    mini_banner()
    if ADMIN_AUTH.exists() and input("  admin_auth.txt exists — overwrite? [y/N] ").lower() != "y":
        return
    name = input("  Admin username [admin]: ").strip() or "admin"
    while True:
        p1 = getpass.getpass("  Admin passkey: ")
        if len(p1) < 8:
            print("  min 8 characters")
            continue
        if p1 != getpass.getpass("  Confirm: "):
            print("  mismatch")
            continue
        break
    write_admin_record(name, p1)
    print(f"  \033[38;5;78m[+]\033[0m {ADMIN_AUTH} written (PBKDF2 x{ROUNDS}, chmod 600)")

def cli_add_user(name, as_n):
    import getpass
    mini_banner()
    users = load_users()
    name = name.lower()
    if name in users and input(f"  '{name}' exists — overwrite? [y/N] ").lower() != "y":
        return
    pw = getpass.getpass(f"  Passkey for {name} (min 8): ")
    if len(pw) < 8:
        print("  too short")
        return
    users[name] = {"cred": hash_password(pw), "as": as_n, "enabled": True}
    save_users(users)
    print(f"  \033[38;5;78m[+]\033[0m {name}:<pbkdf2 hash> AS:{as_n}  -> {USERS_TXT}")

# ═══════════════════════ MAIN ═══════════════════════
if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="◢ SESSIONGUARD — Made by Aryan Giri | giriaryan694-a11y")
    ap.add_argument("--set-admin", action="store_true")
    ap.add_argument("--add-user", metavar="NAME")
    ap.add_argument("--as", type=int, default=1, dest="max_as",
                    help="allowed sessions for --add-user")
    ap.add_argument("--list-users", action="store_true")
    ap.add_argument("--target", default=None,
                    help="initial backend (changeable later from /admin)")
    ap.add_argument("--host", default="0.0.0.0",
                    help="bind address (default: 0.0.0.0 — the shield faces outward)")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    if args.set_admin:
        cli_set_admin()
        sys.exit(0)

    if args.add_user:
        cli_add_user(args.add_user, max(1, min(50, args.max_as)))
        sys.exit(0)

    if args.list_users:
        mini_banner()
        for n, u in load_users().items():
            print(f"  {n:<20} AS:{u['as']:<3} {'OFF' if not u['enabled'] else 'active'}")
        sys.exit(0)

    if not ADMIN_AUTH.exists():
        mini_banner()
        print("  \033[38;5;196m[!]\033[0m admin_auth.txt missing — run: python sessionguard.py --set-admin")
        sys.exit(1)

    DATA.mkdir(exist_ok=True)
    os.chmod(DATA, 0o700)

    if not USERS_TXT.exists():
        USERS_TXT.write_text(
            "# SessionGuard users — user:credential AS:<allowed sessions> [OFF]\n"
            "# example:  operator:ChangeMe!23 AS:2\n"
            "# plaintext credentials are auto-hashed on first login\n")
        os.chmod(USERS_TXT, 0o600)

    if args.target:
        cfg = load_config()
        t = args.target if args.target.startswith("http") else f"http://{args.target}"
        cfg["target"] = t
        save_config(cfg)

    purge_expired()
    banner(args.host, args.port, get_target())
    app.run(host=args.host, port=args.port, threaded=True)
