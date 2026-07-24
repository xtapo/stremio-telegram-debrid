const { spawn } = require('child_process');
const path = require('path');

async function decryptWithEdge(embedUrl) {
    const edgePath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
    const port = 9222;

    const proc = spawn(edgePath, [
        `--remote-debugging-port=${port}`,
        '--headless=new',
        '--disable-gpu',
        '--no-sandbox',
        '--user-data-dir=' + path.join(__dirname, 'edge_profile')
    ]);

    let wsUrl = null;
    for (let i = 0; i < 30; i++) {
        try {
            const res = await fetch(`http://127.0.0.1:${port}/json/version`);
            const data = await res.json();
            wsUrl = data.webSocketDebuggerUrl;
            if (wsUrl) break;
        } catch(e) {}
        await new Promise(r => setTimeout(r, 100));
    }

    if (!wsUrl) {
        proc.kill();
        throw new Error("Failed to get CDP WebSocket URL");
    }

    const ws = new WebSocket(wsUrl);
    let msgId = 1;
    const callbacks = new Map();

    ws.onmessage = (evt) => {
        const msg = JSON.parse(evt.data);
        if (msg.id && callbacks.has(msg.id)) {
            callbacks.get(msg.id)(msg.result);
            callbacks.delete(msg.id);
        }
    };

    await new Promise(resolve => ws.onopen = resolve);

    function sendCDP(method, params = {}) {
        return new Promise(resolve => {
            const id = msgId++;
            callbacks.set(id, resolve);
            ws.send(JSON.stringify({ id, method, params }));
        });
    }

    const targetRes = await sendCDP('Target.createTarget', { url: 'about:blank' });
    const targetId = targetRes.targetId;

    const attachRes = await sendCDP('Target.attachToTarget', { targetId, flatten: true });
    const sessionId = attachRes.sessionId;

    function sendSession(method, params = {}) {
        return new Promise(resolve => {
            const id = msgId++;
            callbacks.set(id, resolve);
            ws.send(JSON.stringify({ id, sessionId, method, params }));
        });
    }

    await sendSession('Page.enable');
    await sendSession('Network.enable');
    await sendSession('Runtime.enable');

    await sendSession('Network.setExtraHTTPHeaders', {
        headers: {
            'Referer': 'https://phim.nguonc.com/'
        }
    });

    await sendSession('Page.addScriptToEvaluateOnNewDocument', {
        source: `
            window.decryptedM3U8Text = null;
            const origCreate = URL.createObjectURL;
            URL.createObjectURL = function(blob) {
                if (blob) {
                    blob.text().then(t => { window.decryptedM3U8Text = t; });
                }
                return origCreate.call(URL, blob);
            };
        `
    });

    await sendSession('Page.navigate', { url: embedUrl });

    let decryptedText = null;
    for (let i = 0; i < 30; i++) {
        const evalRes = await sendSession('Runtime.evaluate', { expression: 'window.decryptedM3U8Text' });
        if (evalRes && evalRes.result && evalRes.result.value) {
            decryptedText = evalRes.result.value;
            break;
        }
        await new Promise(r => setTimeout(r, 150));
    }

    ws.close();
    proc.kill();

    return decryptedText;
}

const embedUrl = process.argv[2] || "https://embed18.streamc.xyz/embed.php?hash=99f386254c018729b4e6a32ac08029f2";
decryptWithEdge(embedUrl).then(text => {
    if (text) {
        console.log("\n🎉 REAL DECRYPTED M3U8 FROM EDGE SUCCESS! Length:", text.length);
        console.log("\n=== M3U8 CONTENT PREVIEW ===\n");
        console.log(text.substring(0, 800));
        console.log("\n============================\n");
        process.exit(0);
    } else {
        console.error("FAILED to decrypt M3U8 via Edge CDP");
        process.exit(1);
    }
}).catch(err => {
    console.error(err);
    process.exit(1);
});
