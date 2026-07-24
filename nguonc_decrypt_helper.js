const vm = require('vm');

async function decryptEmbed(embedUrl) {
    const res1 = await fetch(embedUrl, {
        headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://phim.nguonc.com/'
        }
    });
    const html = await res1.text();
    const obfMatch = html.match(/data-obf="([^"]+)"/);
    if (!obfMatch) {
        throw new Error("data-obf attribute not found in embed page");
    }

    const obfData = JSON.parse(Buffer.from(obfMatch[1], 'base64').toString('utf-8'));
    const sUb = obfData.sUb;
    const hash = obfData.hD;
    const urlObj = new URL(embedUrl);
    const domain = urlObj.origin;

    const jsRes = await fetch(`${domain}/player.js?ver=1.8`, {
        headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' }
    });
    const jsCode = await jsRes.text();

    const fakePlayer = {
        dataset: { obf: obfMatch[1] },
        appendChild: () => {},
        style: {}
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
        async text() {
            return this._buffer.toString('utf-8');
        }
        async arrayBuffer() {
            return this._buffer.buffer;
        }
    }

    const mockJwPlayerInstance = {
        setup: function(cfg) {
            return mockJwPlayerInstance;
        },
        on: function(evt, fn) { return mockJwPlayerInstance; }
    };

    const mockJwPlayer = function(id) {
        return mockJwPlayerInstance;
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
                if (blob && blob._buffer) {
                    decryptedM3u8Text = blob._buffer.toString('utf-8');
                }
                return `blob:${domain}/fake-m3u8`;
            },
            revokeObjectURL: () => {}
        }
    };

    const windowProxy = new Proxy(baseWindow, {
        get: (target, prop) => {
            if (prop in target) return target[prop];
            if (typeof prop === 'string' && prop.endsWith('er')) {
                return mockJwPlayer;
            }
            return undefined;
        }
    });

    let domListener = null;

    const fakeDoc = {
        addEventListener: (evt, fn) => {
            if (evt === 'DOMContentLoaded') {
                domListener = fn;
            }
        },
        getElementById: (id) => fakePlayer,
        querySelector: () => fakePlayer,
        querySelectorAll: () => [fakePlayer],
        createElement: () => ({ appendChild: () => {}, setAttribute: () => {} })
    };

    const dummyTimer = 1;
    const context = vm.createContext({
        console: console,
        fetch: fetch,
        crypto: globalThis.crypto,
        TextEncoder: TextEncoder,
        TextDecoder: TextDecoder,
        atob: atob,
        btoa: btoa,
        Buffer: Buffer,
        document: fakeDoc,
        window: windowProxy,
        navigator: { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', platform: 'Win32', maxTouchPoints: 0 },
        devtoolsDetector: { launch: () => {}, addListener: () => {}, isSupported: false },
        jwplayer: mockJwPlayer,
        URL: baseWindow.URL,
        Blob: CustomBlob,
        setTimeout: (fn, delay) => {
            if (typeof fn === 'function') setTimeout(fn, delay);
            return dummyTimer;
        },
        clearTimeout: () => {},
        setInterval: () => dummyTimer,
        clearInterval: () => {}
    });

    try {
        vm.runInContext(jsCode, context);
    } catch (e) {
        console.error("VM Error:", e.stack || e);
    }

    if (domListener) {
        try {
            domListener();
        } catch(e) {
            console.error("domListener Error:", e.stack || e);
        }
    }

    for (let i = 0; i < 40; i++) {
        if (decryptedM3u8Text && decryptedM3u8Text.includes('#EXTM3U')) break;
        await new Promise(r => setTimeout(r, 50));
    }

    if (!decryptedM3u8Text) {
        throw new Error("Decryption timed out");
    }

    return { domain, m3u8: decryptedM3u8Text };
}

const embedUrlArg = process.argv[2];
decryptEmbed(embedUrlArg)
    .then(result => {
        process.stdout.write(JSON.stringify(result));
        process.exit(0);
    })
    .catch(err => {
        console.error("FAILED:", err.stack || err.message || err);
        process.exit(1);
    });
