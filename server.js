const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const PORT = Number(process.env.PORT || 3000);
const ADMIN_KEY = 'snack-admin-2026';
const DATA_FILE = process.env.DATA_FILE || path.join(__dirname, 'data.json');
const PUBLIC_DIR = path.join(__dirname, 'public');
const CATALOG_FILE = path.join(PUBLIC_DIR, 'snack-catalog.json');

function readData() {
  try { return JSON.parse(fs.readFileSync(DATA_FILE, 'utf8')); }
  catch { return { submissions: [] }; }
}
function writeData(data) { fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2)); }
function json(res, status, value) { res.writeHead(status, {'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'}); res.end(JSON.stringify(value)); }
function readBody(req) { return new Promise((resolve, reject) => { let raw=''; req.on('data', c => raw += c); req.on('end', () => { try { resolve(raw ? JSON.parse(raw) : {}); } catch { reject(new Error('잘못된 요청입니다.')); } }); req.on('error', reject); }); }
function isAdmin(req) { return req.headers['x-admin-key'] === ADMIN_KEY; }
function catalogMap() { try { const catalog=JSON.parse(fs.readFileSync(CATALOG_FILE,'utf8')); return new Map(catalog.products.filter(x=>x.optionStatus).map(x=>[String(x.optionNo),x])); } catch { return new Map(); } }
function serve(req, res) {
  let pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname); if (pathname === '/') pathname='/index.html';
  const file = path.normalize(path.join(PUBLIC_DIR, pathname)); if (!file.startsWith(PUBLIC_DIR)) return json(res,403,{error:'접근이 거부되었습니다.'});
  fs.readFile(file, (err, content) => { if (err) return json(res,404,{error:'페이지를 찾을 수 없습니다.'}); const ext=path.extname(file); const types={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.json':'application/json; charset=utf-8'}; res.writeHead(200,{'Content-Type':types[ext]||'application/octet-stream'}); res.end(content); });
}

http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  if (!url.pathname.startsWith('/api/')) return serve(req,res);
  try {
    const data=readData(); const room=(url.searchParams.get('room')||'ssafy-16-snack').trim().slice(0,80);
    if (req.method==='GET' && url.pathname==='/api/submissions') return json(res,200,{submissions:data.submissions.filter(x=>x.room===room).sort((a,b)=>b.createdAt.localeCompare(a.createdAt))});
    if (req.method==='POST' && url.pathname==='/api/submissions') {
      const input=await readBody(req); const submitRoom=String(input.room||room).trim().slice(0,80)||room; const optionNos=Array.isArray(input.optionNos)?input.optionNos:[input.optionNo]; const catalog=catalogMap(); const products=[...new Set(optionNos.map(String))].map(no=>catalog.get(no)).filter(Boolean);
      if (!products.length) return json(res,400,{error:'목록에서 간식을 하나 이상 선택해 주세요.'});
      const now=new Date().toISOString(); const newItems=products.map(product=>({id:crypto.randomUUID(),room:submitRoom,optionNo:String(product.optionNo),title:product.name,category:product.category,createdAt:now})); data.submissions.push(...newItems); writeData(data); return json(res,201,{submissions:newItems});
    }
    if (!isAdmin(req)) return json(res,401,{error:'관리자 인증이 필요합니다.'});
    if (req.method==='DELETE' && url.pathname==='/api/submissions') { data.submissions=data.submissions.filter(x=>x.room!==room); writeData(data); return json(res,200,{ok:true}); }
    const match=url.pathname.match(/^\/api\/submissions\/([^/]+)$/); if (req.method==='DELETE' && match) { data.submissions=data.submissions.filter(x=>x.id!==match[1]); writeData(data); return json(res,200,{ok:true}); }
    return json(res,404,{error:'API를 찾을 수 없습니다.'});
  } catch (e) { return json(res,500,{error:e.message||'서버 오류가 발생했습니다.'}); }
}).listen(PORT,()=>console.log(`Snack Survey: http://localhost:${PORT}`));
