const fs = require('fs');
fs.writeFileSync('scratch/node_out.txt', 'Starting test...\n');

function log(...args) {
    fs.appendFileSync('scratch/node_out.txt', args.map(a => typeof a === 'object' ? (a && a.stack ? a.stack : JSON.stringify(a)) : String(a)).join(' ') + '\n');
}

const vm = require('vm');

async function decryptEmbed(embedUrl) {
    log("Fetching embed URL:", embedUrl);
    const res1 = await fetch(embedUrl, {
        headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://phim.nguonc.com/'
        }
    });
    const html = await res1.text();
    const obfMatch = html.match(/data-obf="([^"]+)"/);
    if (!obfMatch) {
        log("No data-obf found");
        return;
    }

    const obfData = JSON.parse(Buffer.from(obfMatch[1], 'base64').toString('utf-8'));
    const sUb = obfData.sUb;
    const hash = obfData.hD;
    const urlObj = new URL(embedUrl);
    const domain = urlObj.origin;

    log("Fetching player.js from domain:", domain);
    const jsRes = await fetch(`${domain}/player.js?ver=1.8`, {
        headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' }
    });
    const jsCode = await jsRes.text();
    log("Got player.js code length:", jsCode.length);

    let decryptedM3u8Text = null;

    class CustomBlob {
        constructor(parts, options) {
            log("[CustomBlob constructed]");
            const bufParts = parts.map(p => typeof p === 'string' ? Buffer.from(p) : Buffer.from(p));
            this._buffer = Buffer.concat(bufParts);
            this.size = this._buffer.length;
            this.type = options ? options.type : '';
            decryptedM3u8Text = this._buffer.toString('utf-8');
            log("[CustomBlob] text len:", decryptedM3u8Text.length);
        }
        async text() {
            return this._buffer.toString('utf-8');
        }
        async arrayBuffer() {
            return this._buffer.buffer;
        }
    }

    const mockJwPlayerInstance = {
        setup: function(cfg) {
            log("[mockJwPlayer setup called] cfg:", JSON.stringify(cfg));
            return mockJwPlayerInstance;
        },
        on: function(evt, fn) { 
            log("[mockJwPlayer on called] evt:", evt);
            return mockJwPlayerInstance; 
        }
    };

    const mockJwPlayer = function(id) {
        log("[mockJwPlayer called] id:", id);
        return mockJwPlayerInstance;
    };

    const listeners = {};

    const rawFakePlayer = {
        dataset: { obf: obfMatch[1] },
        appendChild: () => {},
        style: {},
        id: "player",
        getAttribute: (attr) => {
            log("player.getAttribute:", attr);
            if (attr === 'data-obf') return obfMatch[1];
            return null;
        },
        setAttribute: (k, v) => {
            log("player.setAttribute:", k, v);
        }
    };

    const playerProxy = new Proxy(rawFakePlayer, {
        get: (target, prop) => {
            if (prop in target) return target[prop];
            log("[player get unknown]:", String(prop));
            return undefined;
        },
        set: (target, prop, val) => {
            log("[player set]:", String(prop), typeof val);
            target[prop] = val;
            return true;
        }
    });

    const docTarget = {
        readyState: "complete",
        getElementById: (id) => {
            log("doc.getElementById:", id);
            return playerProxy;
        },
        querySelector: (sel) => {
            log("doc.querySelector:", sel);
            return playerProxy;
        },
        querySelectorAll: (sel) => {
            log("doc.querySelectorAll:", sel);
            return [playerProxy];
        },
        createElement: (tag) => {
            log("doc.createElement:", tag);
            return { appendChild: () => {}, setAttribute: () => {} };
        },
        addEventListener: (evt, fn) => {
            log("doc.addEventListener:", evt);
            listeners['doc_' + evt] = fn;
        }
    };

    const docProxy = new Proxy(docTarget, {
        get: (target, prop) => {
            if (prop in target) return target[prop];
            log("[doc get unknown]:", String(prop));
            return undefined;
        }
    });

    const baseWindow = {
        location: { reload: () => {}, href: embedUrl, origin: domain },
        oncontextmenu: null,
        streamURL: '/' + sUb + '?d=1',
        videoHash: hash,
        jwplayer: mockJwPlayer,
        Blob: CustomBlob,
        URL: {
            createObjectURL: (blob) => {
                log("[URL.createObjectURL called]");
                if (blob && blob._buffer) {
                    decryptedM3u8Text = blob._buffer.toString('utf-8');
                }
                return `blob:${domain}/fake-m3u8`;
            },
            revokeObjectURL: () => {}
        },
        addEventListener: (evt, fn) => {
            log("window.addEventListener:", evt);
            listeners['win_' + evt] = fn;
        }
    };

    const windowProxy = new Proxy(baseWindow, {
        get: (target, prop) => {
            if (prop in target) return target[prop];
            log("[window get unknown]:", String(prop));
            if (typeof prop === 'string' && prop.endsWith('er')) {
                return mockJwPlayer;
            }
            return undefined;
        },
        set: (target, prop, val) => {
            log("[window set]:", String(prop), typeof val);
            target[prop] = val;
            return true;
        }
    });

    async function customFetch(url, opts = {}) {
        log("[customFetch]", url, JSON.stringify(opts));
        const fullUrl = typeof url === 'string' && url.startsWith('/') ? `${domain}${url}` : url;
        const reqHeaders = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': embedUrl,
            ...(opts.headers || {})
        };
        try {
            const resp = await fetch(fullUrl, { ...opts, headers: reqHeaders });
            log("[customFetch resp status]", resp.status);
            return resp;
        } catch (e) {
            log("[customFetch error]", e.message);
            throw e;
        }
    }

    const dummyTimer = 1;
    const context = vm.createContext({
        console: { log, error: log, warn: log, info: log },
        fetch: customFetch,
        crypto: globalThis.crypto,
        TextEncoder: TextEncoder,
        TextDecoder: TextDecoder,
        atob: atob,
        btoa: btoa,
        Buffer: Buffer,
        AbortController: globalThis.AbortController,
        AbortSignal: globalThis.AbortSignal,
        Headers: globalThis.Headers,
        Request: globalThis.Request,
        Response: globalThis.Response,
        URL: globalThis.URL,
        URLSearchParams: globalThis.URLSearchParams,
        document: docProxy,
        window: windowProxy,
        navigator: { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', platform: 'Win32', maxTouchPoints: 0 },
        devtoolsDetector: { launch: () => {}, addListener: () => {}, isSupported: false },
        jwplayer: mockJwPlayer,
        URL: baseWindow.URL,
        Blob: CustomBlob,
        setTimeout: (fn, delay) => {
            log("setTimeout called, delay:", delay);
            return setTimeout(fn, delay || 0);
        },
        clearTimeout: (id) => clearTimeout(id),
        setInterval: (fn, delay) => {
            log("setInterval called, delay:", delay);
            return setInterval(fn, delay || 100);
        },
        clearInterval: (id) => clearInterval(id)
    });

    try {
        log("Running vm...");
        vm.runInContext(jsCode, context);
        log("VM executed successfully.");
    } catch (e) {
        log("VM Error:", e.stack || e);
    }

    for (let i = 0; i < 40; i++) {
        if (decryptedM3u8Text && decryptedM3u8Text.includes('#EXTM3U')) break;
        await new Promise(r => setTimeout(r, 100));
    }

    if (!decryptedM3u8Text) {
        log("Decryption timed out");
    } else {
        log("Decryption SUCCESS! Length: " + decryptedM3u8Text.length);
        log("Snippet:\n" + decryptedM3u8Text.slice(0, 500));
    }
}

decryptEmbed("https://embed18.streamc.xyz/embed.php?hash=c9e5230c3e65847df88fc05ea66cbbb6")
    .then(() => log("Finished."))
    .catch(e => log("Fatal err:", e));
