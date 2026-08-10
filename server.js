const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const PORT = Number(process.env.PORT || 3000);
const ADMIN_KEY = 'snack-admin-2026';
const DATA_FILE = process.env.DATA_FILE || path.join(__dirname, 'data.json');
const PUBLIC_DIR = path.join(__dirname, 'public');
const CATALOG_FILE = path.join(PUBLIC_DIR, 'snack-catalog.json');

let mutationQueue = Promise.resolve();

function readData() {
  try {
    return JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
  } catch {
    return { submissions: [] };
  }
}

function writeData(data) {
  fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2));
}

function updateData(mutator) {
  const run = mutationQueue.then(() => {
    const data = readData();
    const result = mutator(data);
    writeData(data);
    return result;
  });
  mutationQueue = run.catch(() => {});
  return run;
}

function json(res, status, value) {
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  res.end(JSON.stringify(value));
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let raw = '';
    req.on('data', chunk => {
      raw += chunk;
      if (raw.length > 50_000) reject(new Error('요청 내용이 너무 큽니다.'));
    });
    req.on('end', () => {
      try {
        resolve(raw ? JSON.parse(raw) : {});
      } catch {
        reject(new Error('잘못된 요청입니다.'));
      }
    });
    req.on('error', reject);
  });
}

function isAdmin(req) {
  return req.headers['x-admin-key'] === ADMIN_KEY;
}

function validRespondentId(value) {
  const id = String(value || '').trim();
  return /^[a-zA-Z0-9_-]{16,80}$/.test(id) ? id : '';
}

function getSurveyStatus(data, room) {
  const saved = data.rooms && data.rooms[room];
  return {
    isOpen: saved ? saved.isOpen !== false : true,
    updatedAt: saved ? saved.updatedAt || null : null,
  };
}

function requestError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function catalogMap() {
  try {
    const catalog = JSON.parse(fs.readFileSync(CATALOG_FILE, 'utf8'));
    return new Map(catalog.products.filter(x => x.optionStatus).map(x => [String(x.optionNo), x]));
  } catch {
    return new Map();
  }
}

function serve(req, res) {
  let pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  if (pathname === '/') pathname = '/index.html';
  const file = path.normalize(path.join(PUBLIC_DIR, pathname));
  if (!file.startsWith(PUBLIC_DIR)) return json(res, 403, { error: '접근이 거부되었습니다.' });

  fs.readFile(file, (err, content) => {
    if (err) return json(res, 404, { error: '페이지를 찾을 수 없습니다.' });
    const ext = path.extname(file);
    const types = {
      '.html': 'text/html; charset=utf-8',
      '.css': 'text/css; charset=utf-8',
      '.js': 'text/javascript; charset=utf-8',
      '.json': 'application/json; charset=utf-8',
    };
    res.writeHead(200, { 'Content-Type': types[ext] || 'application/octet-stream' });
    res.end(content);
  });
}

http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  if (!url.pathname.startsWith('/api/')) return serve(req, res);

  try {
    const room = (url.searchParams.get('room') || 'ssafy-16-snack').trim().slice(0, 80);

    if (req.method === 'GET' && url.pathname === '/api/survey-status') {
      return json(res, 200, getSurveyStatus(readData(), room));
    }

    if (req.method === 'GET' && url.pathname === '/api/my-submission') {
      const respondentId = validRespondentId(url.searchParams.get('respondentId'));
      if (!respondentId) return json(res, 400, { error: '참여자 정보가 올바르지 않습니다.' });
      const submissions = readData().submissions.filter(
        item => item.room === room && item.respondentId === respondentId,
      );
      return json(res, 200, { submissions });
    }

    if (req.method === 'GET' && url.pathname === '/api/submissions') {
      if (!isAdmin(req)) return json(res, 401, { error: '관리자 인증이 필요합니다.' });
      const submissions = readData().submissions
        .filter(item => item.room === room)
        .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
      return json(res, 200, { submissions });
    }

    if (req.method === 'POST' && url.pathname === '/api/submissions') {
      const input = await readBody(req);
      const submitRoom = String(input.room || room).trim().slice(0, 80) || room;
      const respondentId = validRespondentId(input.respondentId);
      if (!respondentId) return json(res, 400, { error: '참여자 정보가 올바르지 않습니다.' });

      const optionNos = Array.isArray(input.optionNos) ? input.optionNos : [input.optionNo];
      const catalog = catalogMap();
      const products = [...new Set(optionNos.map(String))].map(no => catalog.get(no)).filter(Boolean);
      if (!products.length) return json(res, 400, { error: '목록에서 간식을 하나 이상 선택해 주세요.' });

      const now = new Date().toISOString();
      const newItems = products.map(product => ({
        id: crypto.randomUUID(),
        room: submitRoom,
        respondentId,
        optionNo: String(product.optionNo),
        title: product.name,
        category: product.category,
        createdAt: now,
      }));
      const previousCount = await updateData(data => {
        if (!getSurveyStatus(data, submitRoom).isOpen) {
          throw requestError(403, '설문이 마감되어 선택을 등록하거나 수정할 수 없습니다.');
        }
        const before = data.submissions.length;
        data.submissions = data.submissions.filter(
          item => item.room !== submitRoom || item.respondentId !== respondentId,
        );
        const removed = before - data.submissions.length;
        data.submissions.push(...newItems);
        return removed;
      });
      return json(res, 201, { submissions: newItems, updated: previousCount > 0 });
    }

    if (req.method === 'DELETE' && url.pathname === '/api/my-submission') {
      const respondentId = validRespondentId(url.searchParams.get('respondentId'));
      if (!respondentId) return json(res, 400, { error: '참여자 정보가 올바르지 않습니다.' });
      const deletedCount = await updateData(data => {
        if (!getSurveyStatus(data, room).isOpen) {
          throw requestError(403, '설문이 마감되어 제출한 선택을 취소할 수 없습니다.');
        }
        const before = data.submissions.length;
        data.submissions = data.submissions.filter(
          item => item.room !== room || item.respondentId !== respondentId,
        );
        return before - data.submissions.length;
      });
      return json(res, 200, { ok: true, deletedCount });
    }

    if (!isAdmin(req)) return json(res, 401, { error: '관리자 인증이 필요합니다.' });

    if (req.method === 'PUT' && url.pathname === '/api/survey-status') {
      const input = await readBody(req);
      if (typeof input.isOpen !== 'boolean') {
        return json(res, 400, { error: '설문 상태가 올바르지 않습니다.' });
      }
      const status = await updateData(data => {
        data.rooms ||= {};
        data.rooms[room] = { isOpen: input.isOpen, updatedAt: new Date().toISOString() };
        return data.rooms[room];
      });
      return json(res, 200, status);
    }

    if (req.method === 'DELETE' && url.pathname === '/api/submissions') {
      await updateData(data => {
        data.submissions = data.submissions.filter(item => item.room !== room);
      });
      return json(res, 200, { ok: true });
    }

    const match = url.pathname.match(/^\/api\/submissions\/([^/]+)$/);
    if (req.method === 'DELETE' && match) {
      await updateData(data => {
        data.submissions = data.submissions.filter(item => item.id !== match[1]);
      });
      return json(res, 200, { ok: true });
    }

    return json(res, 404, { error: 'API를 찾을 수 없습니다.' });
  } catch (error) {
    return json(res, error.status || 500, { error: error.message || '서버 오류가 발생했습니다.' });
  }
}).listen(PORT, () => console.log(`Snack Survey: http://localhost:${PORT}`));
