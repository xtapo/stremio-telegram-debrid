const { spawn } = require('child_process');
const http = require('http');

async function testEdgeCDP() {
    const edgePath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
    const port = 9222;

    // Launch Edge with Remote Debugging Enabled
    const proc = spawn(edgePath, [
        `--remote-debugging-port=${port}`,
        '--headless=new',
        '--disable-gpu',
        '--no-sandbox',
        '--user-data-dir=' + __dirname + '\\edge_profile'
    ]);

    console.log("Edge launched with PID:", proc.pid);

    // Wait for CDP endpoint
    let cdpUrl = null;
    for (let i = 0; i < 20; i++) {
        try {
            const res = await fetch(`http://127.0.0.1:${port}/json/version`);
            const data = await res.json();
            cdpUrl = data.webSocketDebuggerUrl;
            if (cdpUrl) break;
        } catch(e) {}
        await new Promise(r => setTimeout(r, 200));
    }

    console.log("CDP WebSocket URL:", cdpUrl);
    proc.kill();
}

testEdgeCDP().catch(console.error);
