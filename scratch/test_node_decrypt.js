const vm = require('vm');

async function testNodeDecrypt() {
    const embedUrl = "https://embed18.streamc.xyz/embed.php?hash=99f386254c018729b4e6a32ac08029f2";
    const res1 = await fetch(embedUrl, {
        headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Referer': 'https://phim.nguonc.com/'
        }
    });
    const html = await res1.text();
    const obfMatch = html.match(/data-obf="([^"]+)"/);
    const obfData = JSON.parse(Buffer.from(obfMatch[1], 'base64').toString('utf-8'));
    const sUb = obfData.sUb;
    const hash = obfData.hD;
    const domain = "https://embed18.streamc.xyz";

    console.log("Got sUb:", sUb.substring(0, 20), "hD hash:", hash);

    const jsRes = await fetch(`${domain}/player.js?ver=1.8`, { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const jsCode = await jsRes.text();

    const m3u8Res = await fetch(`${domain}/${sUb}?d=1`, {
        headers: { 'User-Agent': 'Mozilla/5.0', 'Referer': embedUrl }
    });
    const encryptedM3U8Text = await m3u8Res.text();

    let decryptedResult = null;

    const mockJw = {
        setup: (cfg) => {
            console.log("JWPLAYER setup called!");
            return mockJw;
        },
        on: () => mockJw
    };

    class CustomBlob {
        constructor(parts, options) {
            const bufParts = parts.map(p => typeof p === 'string' ? Buffer.from(p) : Buffer.from(p));
            this._buffer = Buffer.concat(bufParts);
            this.size = this._buffer.length;
            this.type = options ? options.type : '';
            decryptedResult = this._buffer.toString('utf-8');
            console.log("CustomBlob captured result length:", decryptedResult.length);
        }
        async text() {
            return this._buffer.toString('utf-8');
        }
    }

    const baseWindow = {
        location: { href: embedUrl, origin: domain },
        streamURL: '/' + sUb + '?d=1',
        videoHash: hash,
        jwplayer: () => mockJw,
        Blob: CustomBlob,
        URL: {
            createObjectURL: (blob) => {
                if (blob && blob._buffer) {
                    decryptedResult = blob._buffer.toString('utf-8');
                }
                return `blob:${domain}/fake-m3u8`;
            },
            revokeObjectURL: () => {}
        }
    };

    const windowProxy = new Proxy(baseWindow, {
        get: (target, prop) => {
            if (prop in target) return target[prop];
            if (typeof prop === 'string' && (prop.endsWith('er') || prop.includes('jw'))) {
                return () => mockJw;
            }
            return undefined;
        }
    });

    const customFetch = async (url, opts) => {
        let fullUrl = url;
        if (url.startsWith('/')) fullUrl = `${domain}${url}`;
        if (fullUrl.includes(sUb)) {
            return {
                ok: true,
                status: 200,
                text: async () => encryptedM3U8Text
            };
        }
        return fetch(fullUrl, opts);
    };

    let domListener = null;

    const sandbox = {
        console: console,
        fetch: customFetch,
        crypto: globalThis.crypto,
        TextEncoder: TextEncoder,
        TextDecoder: TextDecoder,
        atob: atob,
        btoa: btoa,
        Buffer: Buffer,
        document: {
            addEventListener: (evt, fn) => {
                if (evt === 'DOMContentLoaded') domListener = fn;
            },
            getElementById: () => ({ dataset: { obf: obfMatch[1] }, appendChild: () => {}, style: {} }),
            querySelector: () => null,
            querySelectorAll: () => []
        },
        window: windowProxy,
        navigator: { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', platform: 'Win32' },
        devtoolsDetector: { launch: () => {}, addListener: () => {} },
        setTimeout: (fn, delay) => { setImmediate(fn); return 1; },
        clearTimeout: () => {},
        setInterval: () => 1,
        clearInterval: () => {}
    };

    const context = vm.createContext(sandbox);
    vm.runInContext(jsCode, context);

    if (domListener) {
        await domListener();
    }

    for (let i = 0; i < 40; i++) {
        if (decryptedResult && decryptedResult.includes('#EXTM3U')) break;
        await new Promise(r => setTimeout(r, 50));
    }

    console.log("FINAL RESULT:\n", decryptedResult ? decryptedResult.substring(0, 500) : "FAILED");
}

testNodeDecrypt().catch(console.error);
