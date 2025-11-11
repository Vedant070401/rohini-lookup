// script.js — debounced typeahead, keyboard nav, skeletons, clean cards

const nameColChip = document.getElementById("nameColChip");
const qInput = document.getElementById("q");
const clearBtn = document.getElementById("clearBtn");
const nameColDD = document.getElementById("nameCol");
const suggestBox = document.getElementById("suggestBox");
const results = document.getElementById("results");
document.getElementById("year").textContent = new Date().getFullYear();

let META = { name_col: "name", columns: [], total_rows: 0 };
let activeIndex = -1;
let currentOptions = [];

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
function debounce(fn, ms=300){ let t=null; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a), ms); }; }

function showSuggestions(options) {
  suggestBox.innerHTML = "";
  if (!options || options.length === 0) {
    suggestBox.classList.add("hidden"); activeIndex = -1; currentOptions = []; return;
  }
  currentOptions = options.slice(0, 300);
  currentOptions.forEach((name) => {
    const item = document.createElement("div");
    item.className = "s-item"; item.setAttribute("role", "option");
    item.innerHTML = `<div class="s-name">${escapeHTML(name)}</div>`;
    item.addEventListener("click", () => selectName(name));
    suggestBox.appendChild(item);
  });
  suggestBox.classList.remove("hidden"); activeIndex = -1;
}
function setActive(idx){ suggestBox.querySelectorAll(".s-item").forEach((el,i)=>el.classList.toggle("active", i===idx)); }
function hideSuggestions(){ suggestBox.classList.add("hidden"); activeIndex=-1; currentOptions=[]; }

function skeletonCards(count=2) {
  results.innerHTML = "";
  for (let i=0;i<count;i++){
    const c = document.createElement("div");
    c.className="card";
    c.innerHTML = `
      <div class="name skel" style="height:20px;width:220px;margin-bottom:10px;"></div>
      <table class="kv">
        ${Array.from({length:6}).map(()=>`
          <tr>
            <th><div class="skel" style="height:14px;width:140px;"></div></th>
            <td><div class="skel" style="height:14px;width:60%;"></div></td>
          </tr>
        `).join("")}
      </table>`;
    results.appendChild(c);
  }
}

function renderRows(rows){
  if (!rows || rows.length===0){
    results.innerHTML = `
      <div class="empty">
        <div class="empty-title">No matches</div>
        <div class="empty-sub">Try another spelling or select the correct Name column.</div>
      </div>`;
    return;
  }
  const nameKey = META.name_col;
  results.innerHTML = rows.map(obj=>{
    const name = escapeHTML(obj[nameKey] || "—");
    const kv = Object.entries(obj)
      .filter(([k])=>!k.startsWith("_"))
      .map(([k,v])=>`
        <tr>
          <th>${escapeHTML(pretty(k))}</th>
          <td>${escapeHTML(v || "—")}</td>
        </tr>
      `).join("");
    return `
      <div class="card">
        <div class="name">${name}</div>
        <table class="kv"><tbody>${kv}</tbody></table>
      </div>`;
  }).join("");
}

function pretty(k){ return k.replace(/_/g," ").replace(/\b\w/g,c=>c.toUpperCase()); }
function escapeHTML(s){ return String(s).replace(/[&<>"']/g, m=>({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[m])); }

async function selectName(name){
  hideSuggestions();
  qInput.value = name;
  skeletonCards();
  try{
    const data = await api(`/api/lookup?name=${encodeURIComponent(name)}`);
    renderRows(data.rows);
  }catch(e){
    results.innerHTML = `<div class="empty"><div class="empty-title">Error</div><div class="empty-sub">${escapeHTML(e.message)}</div></div>`;
  }
}

const doSuggest = debounce(async ()=>{
  const q = qInput.value.trim();
  if (q.length < 2){ hideSuggestions(); return; }
  try{
    const data = await api(`/api/suggest?q=${encodeURIComponent(q)}&limit=100`);
    showSuggestions(data.options || []);
  }catch(_e){ /* ignore */ }
}, 250);

qInput.addEventListener("input", doSuggest);
qInput.addEventListener("keydown", (e)=>{
  const open = !suggestBox.classList.contains("hidden");
  if (!open) return;
  const items = suggestBox.querySelectorAll(".s-item");
  if (["ArrowDown","ArrowUp","Enter","Escape","Tab"].includes(e.key)) e.preventDefault();
  if (e.key==="ArrowDown"){ activeIndex=Math.min(items.length-1, activeIndex+1); setActive(activeIndex); items[activeIndex]?.scrollIntoView({block:"nearest"}); }
  else if (e.key==="ArrowUp"){ activeIndex=Math.max(0, activeIndex-1); setActive(activeIndex); items[activeIndex]?.scrollIntoView({block:"nearest"}); }
  else if (e.key==="Enter"){
    if (activeIndex>=0 && currentOptions[activeIndex]) selectName(currentOptions[activeIndex]);
    else if (qInput.value.trim()) selectName(qInput.value.trim());
  } else if (e.key==="Escape" || e.key==="Tab"){ hideSuggestions(); }
});

clearBtn.addEventListener("click", ()=>{
  qInput.value = "";
  hideSuggestions();
  results.innerHTML = `
    <div class="empty">
      <div class="empty-title">Start your search</div>
      <div class="empty-sub">Pick the correct “Name column” if suggestions look empty.</div>
    </div>`;
  qInput.focus();
});

nameColDD.addEventListener("change", ()=>{
  META.name_col = nameColDD.value;
  nameColChip.textContent = META.name_col;
  doSuggest();
});

(async function init(){
  try{
    const m = await api("/api/meta");
    META = m;
    const opts = new Set([m.name_col, ...m.columns]);
    nameColDD.innerHTML = "";
    Array.from(opts).forEach(c=>{
      const opt = document.createElement("option");
      opt.value = c; opt.textContent = c;
      if (c === m.name_col) opt.selected = true;
      nameColDD.appendChild(opt);
    });
    nameColChip.textContent = m.name_col;
  }catch(e){ /* silent */ }
})();
