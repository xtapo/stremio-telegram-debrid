const vm = require('vm');

async function decryptNguonC(embedUrl) {
    const res1 = await fetch(embedUrl, {
        headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://phim.nguonc.com/'
        }
    });
    const html = await res1.text();
    const obfMatch = html.match(/data-obf="([^"]+)"/);
    if (!obfMatch) throw new Error("data-obf not found");

    const obfData = JSON.parse(Buffer.from(obfMatch[1], 'base64').toString('utf-8'));
    const sUb = obfData.sUb;
    const hash = obfData.hD;
    const urlObj = new URL(embedUrl);
    const domain = urlObj.origin;

    const jsRes = await fetch(`${domain}/player.js?ver=1.8`, {
        headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' }
    });
    const jsCode = await jsRes.text();

    const m3u8Res = await fetch(`${domain}/${sUb}?d=1`, {
        headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Referer': embedUrl
        }
    });
    const encryptedText = await m3u8Res.text();

    let decryptedResult = null;

    const mockJw = { setup: () => mockJw, on: () => mockJw };

    class CustomBlob {
        constructor(parts, options) {
            const bufParts = parts.map(p => typeof p === 'string' ? Buffer.from(p) : Buffer.from(p));
            this._buffer = Buffer.concat(bufParts);
            this.size = this._buffer.length;
            this.type = options ? options.type : '';
            decryptedResult = this._buffer.toString('utf-8');
            console.log("CustomBlob captured size:", this.size);
        }
        async text() {
            return this._buffer.toString('utf-8');
        }
    }

    const baseWindow = {
        location: { href: embedUrl, origin: domain, reload: () => {} },
        streamURL: '/' + sUb + '?d=1',
        videoHash: hash,
        jwplayer: () => mockJw,
        Blob: CustomBlob,
        URL: {
            createObjectURL: (blob) => {
                console.log("createObjectURL called!");
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
            if (typeof prop === 'string' && (prop.endsWith('er') || prop.includes('jw'))) return () => mockJw;
            return undefined;
        }
    });

    const fakeElement = {
        dataset: { obf: obfMatch[1] },
        appendChild: () => {},
        style: {},
        setAttribute: () => {},
        addEventListener: () => {},
        offsetWidth: 1000,
        offsetHeight: 1000,
        getBoundingClientRect: () => ({ width: 1000, height: 1000, top: 0, left: 0 })
    };

    const docObj = {
        getElementById: () => fakeElement,
        querySelector: () => fakeElement,
        querySelectorAll: () => [fakeElement],
        getElementsByTagName: () => [fakeElement],
        getElementsByClassName: () => [fakeElement],
        createElement: () => fakeElement,
        addEventListener: () => {}
    };

    const docProxy = new Proxy(docObj, {
        get: (target, prop) => {
            if (prop in target) return target[prop];
            if (typeof prop === 'string' && (prop.includes('All') || prop.includes('Elements'))) {
                return () => [fakeElement];
            }
            return () => fakeElement;
        }
    });

    const customFetch = async (url, opts) => {
        let fullUrl = url;
        if (url.startsWith('/')) fullUrl = `${domain}${url}`;
        if (fullUrl.includes(sUb)) {
            return {
                ok: true,
                status: 200,
                text: async () => encryptedText
            };
        }
        return fetch(fullUrl, opts);
    };

    const sandbox = {
        console: console,
        fetch: customFetch,
        crypto: globalThis.crypto,
        TextEncoder: TextEncoder,
        TextDecoder: TextDecoder,
        atob: atob,
        btoa: btoa,
        Buffer: Buffer,
        document: docProxy,
        window: windowProxy,
        navigator: { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', platform: 'Win32' },
        devtoolsDetector: { launch: () => {}, addListener: () => {}, isSupported: true },
        setTimeout: (fn, delay) => {
            setTimeout(fn, 1);
            return 1;
        },
        clearTimeout: () => {},
        setInterval: () => 1,
        clearInterval: () => {}
    };

    const context = vm.createContext(sandbox);
    try {
        vm.runInContext(jsCode, context);
    } catch(e) {
        console.error("VM ERROR:", e.stack || e);
    }

    for (let i = 0; i < 40; i++) {
        if (decryptedResult && decryptedResult.includes('#EXTM3U')) break;
        await new Promise(r => setTimeout(r, 25));
    }

    return decryptedResult;
}

const embedUrl = process.argv[2] || "https://embed18.streamc.xyz/embed.php?hash=99f386254c018729b4e6a32ac08029f2";
decryptNguonC(embedUrl).then(res => {
    console.log("RESULT:", res ? res.substring(0, 300) : "NULL");
}).catch(console.error);
