const API = window.INVESTMENT_API_URL || localStorage.getItem('investment_api_url') || 'http://localhost:8000';
const stageNames = {watch:'观察',anomaly:'异常触发',industry_validation:'产业验证',company_mapping:'公司映射',deep_research:'深度研究',candidate:'候选',waiting_price:'等待价格',weakened:'逻辑削弱',falsified:'已证伪',archived:'归档'};
const icons = {sectors:'◫',companies:'◇',company_snapshots:'▤',metric_observations:'⌁',opportunities:'◎',evidence:'✓',verified_evidence:'◆',open_alerts:'!'};
const labels = {sectors:'覆盖行业',companies:'公司档案',company_snapshots:'公司快照',metric_observations:'指标观测',opportunities:'研究机会',evidence:'证据记录',verified_evidence:'已验证证据',open_alerts:'待处理异常'};

function esc(value=''){return String(value).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
function fmt(value){return new Intl.NumberFormat('zh-CN',{maximumFractionDigits:1}).format(value||0);}
function pct(value){return `${Math.round((value||0)*100)}%`;}
function setStatus(text,type='info'){const el=document.querySelector('#status');el.className=`status ${type}`;el.textContent=text;}
function clearStatus(){document.querySelector('#status').className='status hidden';}
async function get(path, options={}){const r=await fetch(`${API}${path}`,options);if(!r.ok)throw new Error(`${r.status} ${r.statusText}`);return r.json();}

function renderStats(counts={}){document.querySelector('#stats').innerHTML=Object.keys(labels).map(k=>`<div class="stat"><div class="stat-icon">${icons[k]}</div><div><strong>${fmt(counts[k])}</strong><span>${labels[k]}</span></div></div>`).join('');}
function renderSectors(sectors=[]){document.querySelector('#sectors').innerHTML=sectors.map(s=>`<span title="${esc(s.description)}"><b>${esc(s.code)}</b>${esc(s.name)}<i>${esc(s.taxonomy_type)}</i></span>`).join('');}
function renderOpportunities(items=[]){
  const el=document.querySelector('#opportunities');
  if(!items.length){el.innerHTML='<div class="empty">当前没有达到扫描阈值的机会。</div>';return;}
  el.innerHTML=items.map((o,i)=>`<article data-id="${o.id}">
    <div class="rank">${String(i+1).padStart(2,'0')}</div>
    <div class="op-main"><div class="op-title"><h3>${esc(o.title)}</h3><span class="pill pill-${esc(o.stage)}">${esc(stageNames[o.stage]||o.stage)}</span></div>
      <p>${esc(o.thesis)}</p><div class="op-meta"><span>${esc(o.origin||'market')}入口</span><span>行业 ${esc(o.sector_code)}</span><span>置信度 ${pct(o.confidence)}</span><span>${o.is_demo?'DEMO':'LIVE'}</span></div>
    </div><div class="score"><strong>${fmt(o.score)}</strong><span>综合分</span></div></article>`).join('');
  el.querySelectorAll('article').forEach(x=>x.addEventListener('click',()=>openOpportunity(x.dataset.id)));
}
function renderRuns(items=[]){const el=document.querySelector('#runs');el.innerHTML=items.length?items.map(r=>`<div><span class="dot"></span><div><strong>${esc(r.role)}</strong><small>${esc(r.provider)} · ${fmt(r.duration_ms)}ms</small></div><em>${esc(r.status)}</em></div>`).join(''):'<div class="empty">尚无运行记录</div>';}
function renderAlerts(items=[]){const el=document.querySelector('#alerts');el.innerHTML=items.length?items.map(x=>`<div class="alert-${esc(x.severity)}"><strong>${esc(x.title)}</strong><small>${esc(x.details)}</small></div>`).join(''):'<div class="empty">暂无需要人工处理的异常</div>';}
function renderReports(items=[]){const el=document.querySelector('#reports');el.innerHTML=items.length?items.map(x=>`<div><strong>${esc(x.title)}</strong><small>${new Date(x.created_at).toLocaleString('zh-CN')}</small></div>`).join(''):'<div class="empty">尚无报告</div>';}

function openDrawer(html){document.querySelector('#drawer-content').innerHTML=html;document.querySelector('#drawer').classList.remove('hidden');document.querySelector('#drawer-backdrop').classList.remove('hidden');}
function closeDrawer(){document.querySelector('#drawer').classList.add('hidden');document.querySelector('#drawer-backdrop').classList.add('hidden');}
async function openOpportunity(id){
  openDrawer('<div class="empty">正在读取完整研究档案…</div>');
  try{
    const d=await get(`/api/opportunities/${id}`), o=d.opportunity;
    const companies=d.candidate_companies.map(x=>`<button class="company-row" data-company="${x.company.id}"><span><b>${esc(x.company.name)}</b><small>${esc(x.company.ticker)}</small></span><em>${fmt(x.link.ranking_score)}</em></button>`).join('')||'<div class="empty">尚无公司映射</div>';
    const evidence=d.evidence.slice(0,20).map(x=>`<div class="evidence ${x.verified?'verified':''}"><b>${esc(x.variable)}</b><p>${esc(x.claim)}</p><small>等级 ${x.source_rank} · ${x.verified?'已交叉验证':'待验证'} · ${esc(x.independent_path)}</small></div>`).join('')||'<div class="empty">尚无证据</div>';
    const transitions=d.transitions.map(x=>`<li><b>${esc(stageNames[x.from_stage]||x.from_stage)} → ${esc(stageNames[x.to_stage]||x.to_stage)}</b><span>${esc(x.reason)}</span></li>`).join('');
    openDrawer(`<div class="drawer-eyebrow">${esc(o.origin)} / ${esc(o.sector_code)} / ${o.is_demo?'DEMO':'LIVE'}</div><h2>${esc(o.title)}</h2>
      <div class="drawer-score"><strong>${fmt(o.score)}</strong><span>${esc(stageNames[o.stage]||o.stage)} · 置信度 ${pct(o.confidence)}</span></div>
      <section><h3>当前结论</h3><p>${esc(o.thesis)}</p></section>
      <section><h3>利润传导</h3><p>${esc(o.profit_transmission||'尚未形成')}</p></section>
      <section><h3>市场预期</h3><p>${esc(o.market_pricing||'尚未计算')}</p></section>
      <section class="warning"><h3>缺失证据与证伪条件</h3><p>${esc(o.missing_evidence)}</p><p>${esc(o.falsification_conditions)}</p></section>
      <section><h3>公司排名</h3>${companies}</section>
      <section><h3>证据链</h3>${evidence}</section>
      <section><h3>状态历史</h3><ol class="timeline">${transitions}</ol></section>`);
    document.querySelectorAll('.company-row').forEach(x=>x.addEventListener('click',()=>openCompany(x.dataset.company)));
  }catch(e){openDrawer(`<div class="status error">读取失败：${esc(e.message)}</div>`);}
}
async function openCompany(id){
  openDrawer('<div class="empty">正在读取公司利润模型…</div>');
  try{
    const d=await get(`/api/companies/${id}`), c=d.company, latest=d.snapshots[0], model=d.financial_model.scenarios||{};
    const scenarios=Object.entries(model).map(([name,x])=>`<div class="scenario"><b>${esc(name)}</b><strong>${fmt(x.net_profit)}</strong><small>EPS ${fmt(x.eps)} · 估值 ${fmt(x.implied_value_per_share)}</small></div>`).join('');
    const tree=(d.profit_tree[0]?.children||[]).map(x=>`<li><b>${esc(x.name)}</b><span>${esc(x.formula)}</span></li>`).join('');
    const expectation=d.market_expectations[0];
    openDrawer(`<div class="drawer-eyebrow">${esc(c.exchange)} / ${esc(c.ticker)} / ${c.is_demo?'DEMO':'LIVE'}</div><h2>${esc(c.name)}</h2>
      <section><h3>最新经营快照</h3><div class="metric-grid"><span>收入增长<b>${pct(latest?.revenue_growth)}</b></span><span>利润增长<b>${pct(latest?.profit_growth)}</b></span><span>现金/利润<b>${latest?.net_profit?fmt(latest.operating_cash_flow/latest.net_profit):'—'}</b></span><span>负债率<b>${pct(latest?.debt_ratio)}</b></span><span>订单增长<b>${pct(latest?.order_growth)}</b></span><span>业务纯度<b>${pct(latest?.business_purity)}</b></span></div></section>
      <section><h3>三情景盈利模型</h3><div class="scenario-grid">${scenarios||'<div class="empty">假设不完整</div>'}</div></section>
      <section><h3>市场隐含预期</h3><p>${expectation?`要达到 ${pct(expectation.required_return)} 的年化回报，当前价格隐含未来 ${expectation.horizon_years} 年 EPS 年增速约 ${pct(expectation.implied_eps_growth)}。`:'缺少价格、EPS或股本数据。'}</p></section>
      <section><h3>利润驱动树</h3><ul class="driver-tree">${tree}</ul></section>`);
  }catch(e){openDrawer(`<div class="status error">读取失败：${esc(e.message)}</div>`);}
}

async function load(){
  try{clearStatus();const [d,sectors]=await Promise.all([get('/api/dashboard'),get('/api/sectors')]);renderStats(d.counts);renderOpportunities(d.top_opportunities);renderRuns(d.recent_runs);renderSectors(sectors);renderAlerts(d.open_alerts);renderReports(d.recent_reports);}
  catch(e){setStatus(`后端尚未连接：${e.message}。请启动 FastAPI 服务。`,'error');renderStats({});}
}

document.querySelector('#run-cycle').addEventListener('click',async e=>{const b=e.currentTarget;b.disabled=true;b.textContent='正在扫描、建模与反证…';try{const result=await get('/api/research/run-cycle',{method:'POST'});setStatus(`研究周期完成：发现 ${result.radar_count} 个方向，处理 ${result.processed_count} 个，失败 ${result.failed_count} 个。`,'success');await load();}catch(err){setStatus(`运行失败：${err.message}`,'error');}finally{b.disabled=false;b.textContent='运行完整研究周期';}});
document.querySelector('#drawer-close').addEventListener('click',closeDrawer);document.querySelector('#drawer-backdrop').addEventListener('click',closeDrawer);load();
