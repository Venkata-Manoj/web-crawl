#!/usr/bin/env python3
"""Flask Web UI for Website Cloner."""

import io
import os
import threading
import zipfile
from datetime import datetime

from flask import Flask, Response, jsonify, request

from cloner import clone_website_job
from web_crawl.webjobs import JobStore

app = Flask(__name__)

job_store = JobStore()

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Web Cloner</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
@keyframes drift{0%{transform:translate(0,0) rotate(0deg)}33%{transform:translate(30px,-20px) rotate(1deg)}66%{transform:translate(-20px,10px) rotate(-1deg)}100%{transform:translate(0,0) rotate(0deg)}}
@keyframes webPulse{0%,100%{opacity:.08}50%{opacity:.15}}
@keyframes slideUp{0%{opacity:0;transform:translateY(24px) scale(.97)}100%{opacity:1;transform:translateY(0) scale(1)}}
@keyframes shimmer{0%{background-position:-200% 0}100%{background-position:200% 0}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes toastIn{0%{transform:translateX(120%) scale(.85);opacity:0}100%{transform:translateX(0) scale(1);opacity:1}}
@keyframes toastOut{0%{transform:translateX(0) scale(1);opacity:1}100%{transform:translateX(120%) scale(.85);opacity:0}}
@keyframes badgePulse{0%,100%{box-shadow:0 0 0 0 rgba(56,189,248,.4)}50%{box-shadow:0 0 0 8px rgba(56,189,248,0)}}
@keyframes glowPulse{0%,100%{opacity:.04}50%{opacity:.1}}
@keyframes ripple{to{transform:scale(4);opacity:0}}

body{
  background:#080b1a;
  color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  min-height:100vh;overflow-x:hidden;position:relative
}
body::before{
  content:'';position:fixed;top:-50%;left:-50%;width:200%;height:200%;
  background:radial-gradient(ellipse at 20% 50%,rgba(56,189,248,.03) 0%,transparent 50%),
             radial-gradient(ellipse at 80% 20%,rgba(129,140,248,.03) 0%,transparent 50%),
             radial-gradient(ellipse at 50% 80%,rgba(168,85,247,.02) 0%,transparent 50%);
  pointer-events:none;z-index:0
}

/* Spider web decoration */
.web-bg{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden;animation:webPulse 8s ease infinite}
.web-line{position:absolute;background:linear-gradient(90deg,transparent,rgba(56,189,248,.06),transparent);height:1px}
.web-line:nth-child(1){top:15%;left:0;right:70%;transform:rotate(-3deg);animation:drift 25s ease-in-out infinite}
.web-line:nth-child(2){top:35%;left:20%;right:20%;transform:rotate(2deg);animation:drift 30s ease-in-out infinite reverse}
.web-line:nth-child(3){top:55%;left:30%;right:40%;transform:rotate(-4deg);animation:drift 20s ease-in-out infinite}
.web-line:nth-child(4){top:72%;left:10%;right:50%;transform:rotate(1deg);animation:drift 35s ease-in-out infinite reverse}
.web-line:nth-child(5){top:88%;left:40%;right:10%;transform:rotate(-2deg);animation:drift 28s ease-in-out infinite}
.web-dot{position:absolute;width:3px;height:3px;border-radius:50%;background:rgba(56,189,248,.2);animation:glowPulse 4s ease infinite}
.web-dot:nth-child(6){top:15%;left:15%}
.web-dot:nth-child(7){top:35%;left:60%}
.web-dot:nth-child(8){top:55%;left:25%}
.web-dot:nth-child(9){top:72%;left:70%}
.web-dot:nth-child(10){top:45%;left:85%}

.container{max-width:860px;margin:0 auto;padding:2rem 1.5rem 3rem;position:relative;z-index:1}

/* Header */
.hero{text-align:center;margin-bottom:2.5rem;animation:slideUp .6s ease}
.hero-icon{font-size:3rem;display:block;margin-bottom:.25rem;filter:drop-shadow(0 0 24px rgba(56,189,248,.25));transition:transform .3s}
.hero-icon:hover{transform:scale(1.1) rotate(-5deg)}
.hero h1{
  font-size:2.5rem;font-weight:800;line-height:1.15;
  background:linear-gradient(135deg,#38bdf8 0%,#818cf8 40%,#a78bfa 70%,#38bdf8 100%);
  background-size:200% auto;-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
  animation:shimmer 4s linear infinite
}
.hero p{color:#64748b;font-size:.95rem;margin-top:.4rem;letter-spacing:.01em}

/* Card */
.card{
  background:rgba(15,23,42,.65);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  border:1px solid rgba(71,85,105,.25);border-radius:20px;padding:1.75rem;
  box-shadow:0 8px 48px rgba(0,0,0,.3);transition:border-color .3s,box-shadow .3s;
  animation:slideUp .6s ease .1s both
}
.card:hover{border-color:rgba(56,189,248,.2);box-shadow:0 8px 48px rgba(56,189,248,.05)}
.input-group{display:flex;gap:.75rem;flex-wrap:wrap}
.input-group>div{flex:1;min-width:160px}
label{display:block;font-size:.7rem;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.06em;margin-bottom:.35rem}
input[type="text"],input[type="number"]{
  width:100%;padding:.7rem .9rem;
  background:rgba(8,11,26,.6);border:1px solid rgba(71,85,105,.4);
  border-radius:10px;color:#e2e8f0;font-size:.9rem;
  transition:border-color .2s,box-shadow .2s;outline:none
}
input:focus{border-color:#38bdf8;box-shadow:0 0 0 3px rgba(56,189,248,.12)}

/* URL row */
.url-row{margin-bottom:1rem}
.url-row input{font-size:1rem;padding:.8rem 1rem}

/* Advanced toggle */
.adv-hdr{
  display:flex;align-items:center;justify-content:space-between;cursor:pointer;
  padding:.5rem 0;margin-top:.25rem;user-select:none;border-radius:8px;transition:background .2s
}
.adv-hdr:hover{background:rgba(56,189,248,.03)}
.adv-hdr span{color:#64748b;font-size:.82rem;font-weight:600;display:flex;align-items:center;gap:.45rem}
.adv-hdr .arrow{transition:transform .35s cubic-bezier(.68,-.55,.27,1.55);color:#475569;font-size:.7rem;display:inline-block}
.adv-hdr.open .arrow{transform:rotate(180deg)}
.adv-body{
  display:grid;grid-template-rows:0fr;transition:grid-template-rows .4s ease,opacity .3s ease;opacity:0
}
.adv-body.open{grid-template-rows:1fr;opacity:1}
.adv-body-inner{overflow:hidden}
.adv-grid{display:flex;flex-wrap:wrap;gap:.75rem;padding-top:.75rem}
.adv-grid>div{flex:1;min-width:140px}
.chk-row{display:flex;flex-wrap:wrap;gap:.75rem 1.25rem;margin-top:.6rem}
.chk-item{display:flex;align-items:center;gap:.4rem;cursor:pointer;font-size:.85rem;color:#94a3b8;transition:color .2s}
.chk-item:hover{color:#e2e8f0}
.chk-item input[type="checkbox"]{
  appearance:none;width:16px;height:16px;flex-shrink:0;
  background:rgba(8,11,26,.6);border:1px solid #475569;border-radius:4px;cursor:pointer;
  transition:all .2s;display:flex;align-items:center;justify-content:center;position:relative
}
.chk-item input[type="checkbox"]:checked{
  background:#2563eb;border-color:#2563eb
}
.chk-item input[type="checkbox"]:checked::after{
  content:'';position:absolute;width:4px;height:8px;border:solid #fff;border-width:0 2px 2px 0;transform:rotate(45deg);top:2px
}

/* Button */
.btn-wrap{position:relative;margin-top:1rem}
.btn{
  width:100%;padding:.85rem 1rem;border:none;border-radius:12px;
  font-size:.95rem;font-weight:700;cursor:pointer;
  background:linear-gradient(135deg,#2563eb,#1d4ed8);
  color:#fff;display:flex;align-items:center;justify-content:center;gap:.55rem;
  transition:all .3s;position:relative;overflow:hidden
}
.btn::after{content:'';position:absolute;inset:0;border-radius:12px;background:linear-gradient(135deg,transparent 0%,rgba(255,255,255,.08) 50%,transparent 100%);pointer-events:none}
.btn:hover:not(:disabled){transform:translateY(-2px);box-shadow:0 8px 32px rgba(37,99,235,.4)}
.btn:active:not(:disabled){transform:translateY(0)}
.btn:disabled{background:#1e293b;color:#475569;cursor:not-allowed;transform:none;box-shadow:none}
.btn.loading .btn-lbl{display:none}
.btn.loading .btn-spin{display:inline-block}
.btn-spin{display:none;width:18px;height:18px;border:2px solid rgba(255,255,255,.25);border-top-color:#fff;border-radius:50%;animation:spin .6s linear infinite}

/* Jobs section */
.jobs-hdr{display:flex;align-items:center;gap:.75rem;margin:2rem 0 1rem}
.jobs-hdr h2{font-size:1.1rem;font-weight:700;color:#e2e8f0}
.jobs-cnt{background:rgba(56,189,248,.08);color:#38bdf8;padding:.15rem .55rem;border-radius:999px;font-size:.7rem;font-weight:700}

.empty{text-align:center;padding:2.5rem 1rem;color:#334155;animation:slideUp .5s ease}
.empty-i{font-size:2.5rem;margin-bottom:.4rem;opacity:.4}
.empty-t{font-size:.85rem}

.job-card{
  background:rgba(15,23,42,.5);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
  border:1px solid rgba(71,85,105,.2);border-radius:14px;padding:1rem 1.25rem;
  margin-bottom:.75rem;animation:slideUp .4s ease;transition:border-color .3s,box-shadow .3s
}
.job-card:hover{border-color:rgba(71,85,105,.4)}
.job-hdr{display:flex;justify-content:space-between;align-items:center;gap:.75rem}
.job-url{font-size:.85rem;font-weight:600;word-break:break-all;flex:1;color:#e2e8f0}
.job-uri{color:#64748b}
.job-bdg{
  padding:.2rem .65rem;border-radius:999px;font-size:.65rem;font-weight:700;
  text-transform:uppercase;letter-spacing:.04em;white-space:nowrap;flex-shrink:0
}
.bdg-run{background:rgba(56,189,248,.1);color:#38bdf8;animation:badgePulse 2s ease infinite}
.bdg-done{background:rgba(74,222,128,.1);color:#4ade80}
.bdg-err{background:rgba(248,113,113,.1);color:#f87171}

.job-pbar{margin-top:.7rem}
.job-ptrack{width:100%;height:5px;background:rgba(71,85,105,.2);border-radius:3px;overflow:hidden}
.job-pfill{
  height:100%;border-radius:3px;transition:width .5s cubic-bezier(.22,1,.36,1);
  background:linear-gradient(90deg,#2563eb,#38bdf8,#2563eb);background-size:200% 100%;
  min-width:0
}
.job-pfill.run{animation:shimmer 2s ease infinite}
.job-pfill.done{background:linear-gradient(90deg,#4ade80,#22d3ee)}
.job-plbl{display:flex;justify-content:space-between;font-size:.75rem;color:#475569;margin-top:.25rem}

.job-dtl{font-size:.8rem;color:#475569;margin-top:.25rem}

/* Log */
.job-log{margin-top:.35rem}
.log-tgl{
  font-size:.75rem;color:#475569;cursor:pointer;user-select:none;transition:color .2s;
  display:inline-flex;align-items:center;gap:.25rem
}
.log-tgl:hover{color:#94a3b8}
.log-box{
  display:grid;grid-template-rows:0fr;transition:grid-template-rows .4s ease;margin-top:0
}
.log-box.open{grid-template-rows:1fr}
.log-inner{overflow:hidden}
.log-out{
  background:rgba(0,0,0,.35);border-radius:8px;padding:.65rem;margin-top:.4rem;
  font-family:'SF Mono','Fira Code','Cascadia Code',monospace;font-size:.72rem;line-height:1.55;color:#64748b;
  max-height:220px;overflow-y:auto
}
.log-out::-webkit-scrollbar{width:3px}
.log-out::-webkit-scrollbar-track{background:transparent}
.log-out::-webkit-scrollbar-thumb{background:#1e293b;border-radius:2px}
.log-e{animation:slideUp .15s ease}
.log-t{color:#334155;margin-right:.4rem}
.log-u{color:#94a3b8}
.log-s{color:#4ade80}
.log-e{color:#f87171}

.job-act{margin-top:.5rem;display:flex;gap:1rem;display:none}
.job-act a{
  color:#38bdf8;text-decoration:none;font-size:.8rem;font-weight:600;
  transition:color .2s;display:inline-flex;align-items:center;gap:.3rem
}
.job-act a:hover{color:#7dd3fc}

/* Toast */
#toasts{position:fixed;top:1.25rem;right:1.25rem;z-index:999;display:flex;flex-direction:column;gap:.5rem;max-width:340px;pointer-events:none}
.toast{
  pointer-events:auto;background:rgba(15,23,42,.92);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
  border:1px solid rgba(71,85,105,.3);border-radius:12px;padding:.7rem 1rem;
  animation:toastIn .35s ease;display:flex;align-items:center;gap:.5rem;
  box-shadow:0 8px 32px rgba(0,0,0,.4);font-size:.85rem
}
.toast.out{animation:toastOut .35s ease forwards}
.toast.er{border-color:rgba(248,113,113,.3)}
.toast.ok{border-color:rgba(74,222,128,.3)}
.toast-i{font-size:1rem;flex-shrink:0}

@media(max-width:640px){
  body{padding:0}
  .container{padding:1rem}
  .hero h1{font-size:1.7rem}
  .card{padding:1.25rem;border-radius:14px}
  .input-group>div{min-width:100%}
  .adv-grid>div{min-width:100%}
  #toasts{left:1rem;right:1rem;max-width:none;top:.75rem}
}
</style>
</head>
<body>

<div class="web-bg">
  <div class="web-line"></div><div class="web-line"></div><div class="web-line"></div>
  <div class="web-line"></div><div class="web-line"></div>
  <div class="web-dot"></div><div class="web-dot"></div><div class="web-dot"></div>
  <div class="web-dot"></div><div class="web-dot"></div>
</div>

<div class="container">
<div class="hero">
  <span class="hero-icon">&#x1F578;</span>
  <h1>Web Cloner</h1>
  <p>Download entire websites for offline viewing</p>
</div>

<div class="card" id="mainCard">
  <div class="url-row">
    <label for="url">Website URL</label>
    <input type="text" id="url" placeholder="https://example.com" autofocus>
  </div>

  <div class="input-group">
    <div><label for="maxPages">Max Pages</label><input type="number" id="maxPages" value="100" min="1" max="10000"></div>
    <div><label for="output">Output Dir</label><input type="text" id="output" value="cloned_sites"></div>
  </div>

  <div class="adv-hdr" id="advToggle">
    <span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg> Advanced</span>
    <span class="arrow">&#x25BC;</span>
  </div>
  <div class="adv-body" id="advBody">
    <div class="adv-body-inner">
      <div class="adv-grid">
        <div><label for="delay">Delay (s)</label><input type="number" id="delay" value="0.2" min="0" max="10" step="0.1"></div>
        <div><label for="timeout">Timeout (s)</label><input type="number" id="timeout" value="30" min="5" max="120"></div>
      </div>
      <div class="chk-row">
        <label class="chk-item"><input type="checkbox" id="renderJs"><span>JS Rendering</span></label>
        <label class="chk-item"><input type="checkbox" id="allDomains"><span>All Domains</span></label>
      </div>
    </div>
  </div>

  <div class="btn-wrap">
    <button class="btn" id="startBtn">
      <span class="btn-lbl">Start Cloning</span>
      <span class="btn-spin"></span>
    </button>
  </div>
</div>

<div class="jobs-hdr">
  <h2>Jobs</h2>
  <span class="jobs-cnt" id="jobCount">0</span>
</div>
<div id="jobsList">
  <div class="empty" id="emptyState">
    <div class="empty-i">&#x1F4E1;</div>
    <div class="empty-t">No jobs yet — enter a URL above</div>
  </div>
</div>
</div>

<div id="toasts"></div>

<script>
(function(){
'use strict';

var pollId = null;

// ── DOM refs (cache once) ─────────────────────────────────────────────
var $ = function(id){ return document.getElementById(id); };
var urlIn = $('url');
var maxPagesIn = $('maxPages');
var outputIn = $('output');
var delayIn = $('delay');
var timeoutIn = $('timeout');
var renderJs = $('renderJs');
var allDomains = $('allDomains');
var startBtn = $('startBtn');
var jobsList = $('jobsList');
var emptyState = $('emptyState');
var advBody = $('advBody');
var advToggle = $('advToggle');
var jobCount = $('jobCount');

// ── Advanced toggle ──────────────────────────────────────────────────
advToggle.addEventListener('click', function(){
  advBody.classList.toggle('open');
  advToggle.classList.toggle('open');
});

// ── Toast ────────────────────────────────────────────────────────────
function toast(msg, type){
  var c = $('toasts');
  var icon = type === 'er' ? '\u26a0' : type === 'ok' ? '\u2714' : '\u2139';
  var el = document.createElement('div');
  el.className = 'toast ' + type;
  el.innerHTML = '<span class="toast-i">' + icon + '</span>' + esc(msg);
  c.appendChild(el);
  setTimeout(function(){
    el.classList.add('out');
    setTimeout(function(){ el.remove(); }, 350);
  }, 4000);
}

// ── Helpers ──────────────────────────────────────────────────────────
function esc(s){
  var d = document.createElement('div');
  d.appendChild(document.createTextNode(s));
  return d.innerHTML;
}

function validUrl(s){
  try{ return !!new URL(s); }catch(e){ return false; }
}

function fmtUrl(s){
  try{
    var u = new URL(s);
    return '<span style="color:#475569">' + esc(u.protocol + '//') + '</span>' + esc(u.hostname) + '<span style="color:#334155">' + esc(u.pathname) + '</span>';
  }catch(e){ return esc(s); }
}

function countJobs(){
  var n = jobsList.querySelectorAll('.job-card').length;
  jobCount.textContent = n;
  if(emptyState) jobCount.textContent = '0';
}

// ── Start clone ─────────────────────────────────────────────────────
startBtn.addEventListener('click', function(){
  var url = urlIn.value.trim();
  if(!url){ toast('Enter a URL', 'er'); return; }
  var testUrl = url.indexOf('http') === 0 ? url : 'https://' + url;
  if(!validUrl(testUrl)){ toast('Invalid URL', 'er'); return; }

  startBtn.disabled = true;
  startBtn.classList.add('loading');

  var body = JSON.stringify({
    url: url,
    output: outputIn.value || 'cloned_sites',
    max_pages: parseInt(maxPagesIn.value) || 100,
    delay: parseFloat(delayIn.value) || 0.2,
    timeout: parseInt(timeoutIn.value) || 30,
    render_js: renderJs.checked,
    follow_domains: allDomains.checked
  });

  fetch('/api/v1/clone', { method:'POST', headers:{'Content-Type':'application/json'}, body:body })
    .then(function(r){ return r.json(); })
    .then(function(data){
      startBtn.disabled = false;
      startBtn.classList.remove('loading');
      if(data.error){ toast(data.error, 'er'); return; }
      addJob(data.id, url);
      toast('Clone started', 'ok');
      startPoll();
    })
    .catch(function(err){
      startBtn.disabled = false;
      startBtn.classList.remove('loading');
      toast('Failed: ' + err.message, 'er');
    });
});

// ── Render job card ─────────────────────────────────────────────────
function addJob(id, url){
  if(emptyState) emptyState.remove();
  var card = document.createElement('div');
  card.className = 'job-card';
  card.id = 'j' + id;
  card.innerHTML =
    '<div class="job-hdr">' +
      '<span class="job-url">' + fmtUrl(url) + '</span>' +
      '<span class="job-bdg bdg-run" id="jb' + id + '">Run</span>' +
    '</div>' +
    '<div class="job-pbar">' +
      '<div class="job-ptrack"><div class="job-pfill run" id="jp' + id + '" style="width:0%"></div></div>' +
      '<div class="job-plbl"><span id="jpp' + id + '">0%</span><span id="jpd' + id + '">Starting</span></div>' +
    '</div>' +
    '<div class="job-dtl" id="jdt' + id + '"></div>' +
    '<div class="job-log">' +
      '<span class="log-tgl" id="lt' + id + '">&#x25B6; Log</span>' +
      '<div class="log-box" id="lb' + id + '"><div class="log-inner"><div class="log-out" id="lo' + id + '"></div></div></div>' +
    '</div>' +
    '<div class="job-act" id="ja' + id + '">' +
      '<a href="/download/' + id + '">&#x2B07; ZIP</a>' +
      '<a href="/output/' + id + '" target="_blank">&#x1F50D; View</a>' +
    '</div>';

  // Log toggle via direct event
  card.querySelector('.log-tgl').addEventListener('click', function(){
    var box = $('lb' + id);
    box.classList.toggle('open');
    this.innerHTML = box.classList.contains('open') ? '\u25bc Log' : '\u25b6 Log';
  });

  jobsList.insertBefore(card, jobsList.firstChild);
  countJobs();
}

function updJob(id, data){
  var badge = $('jb' + id);
  var fill = $('jp' + id);
  var pctL = $('jpp' + id);
  var dtl = $('jpd' + id);
  var acts = $('ja' + id);
  if(!badge) return;

  if(data.status === 'running'){
    var pct = data.max_pages > 0 ? Math.round(data.pages_cloned / data.max_pages * 100) : 0;
    fill.style.width = pct + '%';
    fill.className = 'job-pfill run';
    if(pctL) pctL.textContent = pct + '%';
    if(dtl) dtl.textContent = data.pages_cloned + ' / ' + data.max_pages;
    addLog(id, data.current_url, 'u');
  } else if(data.status === 'done'){
    badge.textContent = 'Done';
    badge.className = 'job-bdg bdg-done';
    fill.style.width = '100%';
    fill.className = 'job-pfill done';
    if(pctL) pctL.textContent = '100%';
    if(dtl) dtl.textContent = data.pages_cloned + ' pages done';
    if(acts) acts.style.display = 'flex';
    addLog(id, 'Complete', 's');
  } else if(data.status === 'error'){
    var em = data.error || 'Error';
    badge.textContent = 'Error';
    badge.className = 'job-bdg bdg-err';
    fill.className = 'job-pfill';
    if(dtl) dtl.textContent = em;
    if(acts) acts.style.display = 'flex';
    addLog(id, em, 'e');
  }
}

// ── Log ──────────────────────────────────────────────────────────────
function addLog(jid, txt, cls){
  var out = $('lo' + jid);
  if(!out || !txt) return;
  if(cls === 'u' && out.lastChild && out.lastChild.textContent.indexOf(txt) >= 0) return;
  var e = document.createElement('div');
  e.className = 'log-e';
  var t = new Date().toLocaleTimeString();
  var ic = cls === 's' ? '\u2714 ' : cls === 'e' ? '\u26a0 ' : '';
  e.innerHTML = '<span class="log-t">' + esc(t) + '</span>' + (ic ? '<span class="log-' + cls + '">' + ic + '</span>' : '') + '<span class="log-u">' + esc(txt.slice(0, 130)) + '</span>';
  out.appendChild(e);
  out.scrollTop = out.scrollHeight;
}

// ── Polling ──────────────────────────────────────────────────────────
function startPoll(){
  if(pollId) return;
  poll();
  pollId = setInterval(poll, 1200);
}

function stopPoll(){
  if(pollId){ clearInterval(pollId); pollId = null; }
}

function poll(){
  fetch('/api/v1/jobs')
    .then(function(r){ return r.json(); })
    .then(function(data){
      var anyRun = false;
      for(var k in data){
        if(data.hasOwnProperty(k)){
          updJob(k, data[k]);
          if(data[k].status === 'running') anyRun = true;
        }
      }
      if(!anyRun) stopPoll();
    })
    .catch(function(){});
}

// ── Init ──────────────────────────────────────────────────────────────
poll();

})();
</script>
</body>
</html>"""


def run_clone_job(job_id: str, config: dict):
    """Run a clone job in a background thread."""

    def progress(cloned, total, url):
        job_store.update(job_id, pages_cloned=cloned, max_pages=total, current_url=url)

    try:
        clone_website_job(config, progress_callback=progress)
        job_store.update(job_id, status="done", output_dir=config["output"])
    except Exception as e:
        job_store.update(job_id, status="error", error=str(e))


@app.route("/")
def index():
    return Response(PAGE, content_type="text/html")


@app.route("/api/clone", methods=["POST"])
@app.route("/api/v1/clone", methods=["POST"])
def api_clone():
    data = request.get_json()
    if not data or "url" not in data:
        return jsonify({"error": "URL is required"}), 400

    url = data["url"].strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    data["url"] = url

    # Convert render_js checkbox (backward compat) to render_level
    if "render_js" in data:
        data["render_level"] = 2 if data.pop("render_js") else 0
    data.setdefault("render_level", 0)

    # Validate output directory to prevent path traversal
    output_dir = data.get("output", "cloned_sites")
    safe_base = os.path.abspath("cloned_sites")
    resolved = os.path.abspath(output_dir)
    if os.path.commonpath([resolved, safe_base]) != safe_base:
        output_dir = f"cloned_sites/{datetime.now().strftime('%Y%m%d%H%M%S')}"
    data["output"] = output_dir

    job_id = job_store.create(url, max_pages=data.get("max_pages", 100))

    thread = threading.Thread(target=run_clone_job, args=(job_id, data), daemon=True)
    thread.start()

    return jsonify({"id": job_id, "status": "started"})


@app.route("/api/jobs")
@app.route("/api/v1/jobs")
def api_jobs():
    return jsonify(job_store.list())


@app.route("/api/status/<job_id>")
@app.route("/api/v1/status/<job_id>")
def api_status(job_id):
    job = job_store.get(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/download/<job_id>")
def download_zip(job_id):
    job = job_store.get(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    output_dir = job.get("output_dir", "")

    if not output_dir or not os.path.exists(output_dir):
        return jsonify({"error": "Output directory not found"}), 404

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(output_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, os.path.dirname(output_dir))
                zf.write(file_path, arcname)

    zip_buffer.seek(0)
    return Response(
        zip_buffer.getvalue(),
        mimetype="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{os.path.basename(output_dir)}.zip"'
            )
        },
    )


@app.route("/output/<job_id>")
def view_output(job_id):
    job = job_store.get(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    output_dir = job.get("output_dir", "")

    if not output_dir or not os.path.exists(output_dir):
        return jsonify({"error": "Output directory not found"}), 404

    index_path = os.path.join(output_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(
            content,
            content_type="text/html",
            headers={"Content-Security-Policy": "script-src 'none'; sandbox"},
        )

    files = []
    for root, dirs, fnames in os.walk(output_dir):
        for fname in fnames:
            rel = os.path.relpath(os.path.join(root, fname), output_dir)
            files.append(rel)
    files.sort()

    html = f"<html><head><title>{output_dir}</title></head><body>"
    html += f"<h1>{output_dir}</h1><ul>"
    for f in files:
        html += f"<li>{f}</li>"
    html += "</ul></body></html>"
    return Response(
        html,
        content_type="text/html",
        headers={"Content-Security-Policy": "script-src 'none'; sandbox"},
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
