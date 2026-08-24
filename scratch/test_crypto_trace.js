const fs = require('fs');
fs.writeFileSync('scratch/crypto_trace.txt', 'Starting trace...\n');

function log(...args) {
    fs.appendFileSync('scratch/crypto_trace.txt', args.map(a => typeof a === 'object' ? (a && a.stack ? a.stack : JSON.stringify(a)) : String(a)).join(' ') + '\n');
}

const vm = require('vm');

async function traceCrypto(embedUrl) {
    log("Fetching embed URL:", embedUrl);
    const res1 = await fetch(embedUrl, {
        headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://phim.nguonc.com/'
        }
    });
    const html = await res1.text();
    const obfMatch = html.match(/data-obf="([^"]+)"/);
    if (!obfMatch) return;

    const obfData = JSON.parse(Buffer.from(obfMatch[1], 'base64').toString('utf-8'));
    const sUb = obfData.sUb;
    const hash = obfData.hD;
    const urlObj = new URL(embedUrl);
    const domain = urlObj.origin;

    const jsRes = await fetch(`${domain}/player.js?ver=1.8`, {
        headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' }
    });
    const jsCode = await jsRes.text();

    const realSubtle = globalThis.crypto.subtle;
    const subtleProxy = new Proxy(realSubtle, {
        get: (target, prop) => {
            const orig = target[prop];
            if (typeof orig === 'function') {
                return async (...args) => {
                    log("[crypto.subtle." + String(prop) + " CALL]", ...args.map(a => {
                        if (a instanceof ArrayBuffer || ArrayBuffer.isView(a)) {
                            return `Buf(${a.byteLength || a.length}: ${Buffer.from(a).toString('hex').slice(0, 40)}...)`;
                        }
                        return a;
                    }));
                    try {
                        const result = await orig.apply(target, args);
                        log("[crypto.subtle." + String(prop) + " RET]", result);
                        return result;
                    } catch (err) {
                        log("[crypto.subtle." + String(prop) + " ERR]", err.message);
                        throw err;
                    }
                };
            }
            return orig;
        }
    });

    const cryptoProxy = {
        getRandomValues: (buf) => globalThis.crypto.getRandomValues(buf),
        randomUUID: () => globalThis.crypto.randomUUID(),
        subtle: subtleProxy
    };

    let decryptedM3u8Text = null;

    class CustomBlob {
        constructor(parts, options) {
            const bufParts = parts.map(p => typeof p === 'string' ? Buffer.from(p) : Buffer.from(p));
            this._buffer = Buffer.concat(bufParts);
            this.size = this._buffer.length;
            this.type = options ? options.type : '';
            decryptedM3u8Text = this._buffer.toString('utf-8');
        }
        async text() { return this._buffer.toString('utf-8'); }
        async arrayBuffer() { return this._buffer.buffer; }
    }

    const mockJwPlayer = function(id) {
        return { setup: () => this, on: () => this };
    };

    const rawFakePlayer = {
        dataset: { obf: obfMatch[1] },
        appendChild: () => {},
        style: {},
        id: "player",
        getAttribute: (attr) => attr === 'data-obf' ? obfMatch[1] : null,
        setAttribute: () => {}
    };

    const docTarget = {
        readyState: "complete",
        getElementById: () => rawFakePlayer,
        querySelector: () => rawFakePlayer,
        querySelectorAll: () => [rawFakePlayer],
        createElement: () => ({ appendChild: () => {}, setAttribute: () => {} }),
        addEventListener: () => {}
    };

    const baseWindow = {
        location: { reload: () => {}, href: embedUrl, origin: domain },
        oncontextmenu: null,
        streamURL: '/' + sUb + '?d=1',
        videoHash: hash,
        jwplayer: mockJwPlayer,
        Blob: CustomBlob,
        URL: {
            createObjectURL: (blob) => {
                if (blob && blob._buffer) decryptedM3u8Text = blob._buffer.toString('utf-8');
                return `blob:${domain}/fake-m3u8`;
            },
            revokeObjectURL: () => {}
        },
        addEventListener: () => {}
    };

    async function customFetch(url, opts = {}) {
        const fullUrl = typeof url === 'string' && url.startsWith('/') ? `${domain}${url}` : url;
        const reqHeaders = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': embedUrl,
            ...(opts.headers || {})
        };
        return await fetch(fullUrl, { ...opts, headers: reqHeaders });
    }

    const context = vm.createContext({
        console: { log, error: log, warn: log, info: log },
        fetch: customFetch,
        crypto: cryptoProxy,
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
        document: docTarget,
        window: baseWindow,
        navigator: { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', platform: 'Win32', maxTouchPoints: 0 },
        devtoolsDetector: { launch: () => {}, addListener: () => {}, isSupported: false },
        jwplayer: mockJwPlayer,
        URL: baseWindow.URL,
        Blob: CustomBlob,
        setTimeout: (fn, d) => setTimeout(fn, d || 0),
        clearTimeout: (id) => clearTimeout(id),
        setInterval: (fn, d) => setInterval(fn, d || 100),
        clearInterval: (id) => clearInterval(id)
    });

    try {
        vm.runInContext(jsCode, context);
    } catch (e) {
        log("VM Error:", e.stack || e);
    }

    for (let i = 0; i < 40; i++) {
        if (decryptedM3u8Text && decryptedM3u8Text.includes('#EXTM3U')) break;
        await new Promise(r => setTimeout(r, 100));
    }

    log("Decrypted text available:", !!decryptedM3u8Text);
    if (decryptedM3u8Text) {
        log("Decrypted M3U8 length:", decryptedM3u8Text.length);
        log("M3U8 Sample:\n", decryptedM3u8Text.slice(0, 400));
    }
}

traceCrypto("https://embed18.streamc.xyz/embed.php?hash=c9e5230c3e65847df88fc05ea66cbbb6")
    .then(() => log("Trace done."));
