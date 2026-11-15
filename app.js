const $ = id => document.getElementById(id);
const sourceNames = {IS:'Ilta-Sanomat', IL:'Iltalehti'};
const formatDate = new Intl.DateTimeFormat('fi-FI',{dateStyle:'medium',timeStyle:'short',timeZone:'Europe/Helsinki'});
let source = '';
let adminToken = '';
let routeSequence = 0;
let activeThread;

function element(tag, label='', className='') {
  const node = document.createElement(tag);
  node.textContent = label;
  if(className) node.className = className;
  return node;
}

const mobileBanner = window.matchMedia('(max-width: 600px)');

function loadBanner(banner) {
  const folder = mobileBanner.matches ? 'mobiili' : 'tietokone';
  const image = element('img');
  image.alt = 'Mainos';
  banner.textContent = 'Mainospaikka';
  image.addEventListener('load', () => {
    if (mobileBanner.matches === (folder === 'mobiili')) banner.replaceChildren(image);
  }, {once:true});
  image.src = '/' + folder + '/mainokset/' + banner.dataset.adSlot + '.webp';
}

async function api(path, data, token) {
  const headers = token ? {Authorization:'Bearer '+token} : {};
  const options = {headers};
  if(data !== undefined) {
    options.method = 'POST';
    options.body = JSON.stringify(data);
    headers['Content-Type'] = 'application/json';
  }
  const response = await fetch(path, options);
  const result = await response.json();
  if(!response.ok) throw Error(result.error || 'Pyyntö epäonnistui.');
  return result;
}

function meta(item) {
  return element('p', sourceNames[item.source]+' · '+formatDate.format(item.published*1000), 'meta');
}

async function listThreads(sequence) {
  const {threads, sources} = await api('/api/threads');
  if(sequence !== routeSequence) return;
  $('threads').replaceChildren();
  const visible = threads.map((item, index) => ({...item, position:index+1}))
    .filter(item => !source || item.source === source);
  $('status').hidden = Boolean(visible.length);
  $('status').textContent = Object.keys(sources).length
    ? 'Tässä näkymässä ei ole vahvistettuja uutisia.'
    : 'Tarkistetaan lehtien listoja…';
  $('updated').textContent = Object.entries(sourceNames).map(([key,name]) => {
    const info = sources[key];
    if(!info) return name+' · tarkistus käynnissä';
    const last = info.checked ? formatDate.format(info.checked*1000) : '';
    if(info.status === 'error') return name+' · haku epäonnistui'+(last ? ', edellinen lista '+last : '');
    return name+' · '+last+(info.status === 'partial' ? ' (osa jutuista jäi varmistamatta)' : '');
  }).join(' | ');
  for(const [index, item] of visible.entries()) {
    const li = element('li');
    li.value = item.position;
    const rank = element('span',String(item.position),'rank');
    rank.setAttribute('aria-hidden','true');
    const section = element('div');
    const heading = element('h2');
    const title = element('a', item.title);
    title.href = '#ketju/'+item.id;
    heading.append(title);
    const status = item.status === 'ended' ? 'Kommentointi päättynyt' : 'Kommentointi pois käytöstä';
    section.append(element('p',sourceNames[item.source]+' · Luetuimmat #'+item.rank,'meta'),
      heading,element('span',status+' · '+item.replies+' viestiä'+(item.locked?' · Lukittu':''),'meta'));
    li.append(rank,section);
    $('threads').append(li);
    if((index + 1) % 5 === 0) {
      const slot = element('li', '', 'ad-row');
      slot.setAttribute('role', 'presentation');
      const banner = element('aside', 'Mainospaikka', 'ad-banner');
      banner.dataset.adSlot = 'after-' + (index + 1);
      banner.setAttribute('aria-label', 'Mainosbannerin paikka');
      slot.append(banner);
      $('threads').append(slot);
      loadBanner(banner);
    }
  }
}

async function showThread(id, sequence) {
  const item = await api('/api/threads/'+id);
  if(sequence !== routeSequence) return;
  activeThread = item.id;
  const original = element('a','Avaa alkuperäinen uutinen ↗');
  original.href = item.url;
  original.target = '_blank';
  original.rel = 'noopener noreferrer';
  const originalLink = element('div', '', 'thread-link');
  originalLink.append(original);
  $('article').replaceChildren(meta(item),element('h1',item.title),originalLink);
  $('messages').replaceChildren();
  $('reply').hidden = Boolean(item.locked);
  $('thread-status').textContent = item.locked ? 'Ketju on lukittu.' : '';
  for(const message of item.messages) {
    const li = element('li');
    const report = element('button','Ilmoita viestistä');
    report.type = 'button';
    report.addEventListener('click',async () => {
      report.disabled = true;
      try {
        await api('/api/report',{id:message.id});
        report.textContent = 'Ilmoitettu';
      } catch(error) {
        $('thread-status').textContent = error.message;
        report.disabled = false;
      }
    });
    li.append(element('strong',message.author),element('p',formatDate.format(message.created*1000),'meta'),
      element('p',message.body,'message'),report);
    $('messages').append(li);
  }
}

async function route() {
  const sequence = ++routeSequence;
  const match = location.hash.match(/^#ketju\/(\d+)$/);
  const admin = location.hash === '#yllapito';
  $('moderation').hidden = !admin;
  $('thread').hidden = !match;
  $('forum').hidden = Boolean(match || admin);
  if(admin) return;
  activeThread = undefined;
  if(match) {
    $('reply').reset();
    $('article').replaceChildren();
    $('messages').replaceChildren();
    $('reply').hidden = true;
    $('thread-status').textContent = 'Ladataan keskustelua…';
  }
  try {
    if(match) await showThread(match[1],sequence);
    else await listThreads(sequence);
  } catch(error) {
    if(sequence !== routeSequence) return;
    const status = match ? $('thread-status') : $('status');
    status.hidden = false;
    status.textContent = error.message;
  }
}
for(const button of document.querySelectorAll('[data-source]')) {
  button.addEventListener('click',() => {
    source = button.dataset.source;
    document.querySelectorAll('[data-source]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
    route();
  });
}
$('reply').addEventListener('submit',async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const sequence = routeSequence;
  const id = activeThread;
  const data = new FormData(form);
  const button = form.querySelector('button');
  button.disabled = true;
  try {
    await api('/api/messages',{id,author:data.get('author'),body:data.get('body')});
    if(sequence===routeSequence) {
      form.elements.body.value = '';
      await showThread(id,sequence);
    }
  } catch(error) {
    if(sequence===routeSequence) $('thread-status').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

async function showReports() {
  const reports = await api('/api/reports',undefined,adminToken);
  $('reports').replaceChildren();
  $('admin-status').textContent = reports.length ? '' : 'Ei avoimia ilmoituksia.';
  $('lock').hidden = false;
  for(const report of reports) {
    const li = element('li');
    const remove = element('button','Poista viesti');
    remove.addEventListener('click',async () => {
      try {
        await api('/api/moderate',{id:report.id,action:'remove'},adminToken);
        await showReports();
      } catch(error) {
        $('admin-status').textContent = error.message;
      }
    });
    li.append(element('strong',report.title),element('p','Ketju '+report.article_id+' · '+report.author,'meta'),
      element('p',report.body,'message'),remove);
    $('reports').append(li);
  }
}
$('admin').addEventListener('submit',async event => {
  event.preventDefault();
  const field = event.currentTarget.elements.token;
  adminToken = field.value;
  field.value = '';
  try { await showReports(); }
  catch(error) {
    $('reports').replaceChildren();
    $('lock').hidden = true;
    $('admin-status').textContent = error.message;
  }
});
$('lock').addEventListener('submit',async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const action = event.submitter.value;
  try {
    await api('/api/moderate',{id:Number(form.elements.id.value),action},adminToken);
    $('admin-status').textContent = action==='lock' ? 'Ketju lukittu.' : 'Ketjun lukitus avattu.';
  } catch(error) {
    $('admin-status').textContent = error.message;
  }
});

loadBanner($('top-banner'));
mobileBanner.addEventListener('change', () => {
  document.querySelectorAll('[data-ad-slot]').forEach(loadBanner);
});
window.addEventListener('hashchange',route);
route();
setInterval(() => { if(!location.hash) route(); },30000);
