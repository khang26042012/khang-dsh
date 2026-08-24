// APP WORKER v1 - thay the sau bang DSH/bot that
const http = require('http');
const PORT = parseInt(process.env.APP_PORT || '30007', 10);
console.log('[APP] worker khoi dong pid=' + process.pid);
const s = http.createServer((req,res)=>{ res.writeHead(200); res.end('APP OK'); });
s.listen(PORT, '127.0.0.1');
setInterval(()=>console.log('[APP] alive pid=' + process.pid + ' t=' + Math.floor(process.uptime())), 120000);
