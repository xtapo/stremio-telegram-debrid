process.on('uncaughtException', err => console.error('Uncaught Exception:', err));
process.on('unhandledRejection', err => console.error('Unhandled Rejection:', err));

const vm = require('vm');

async function findSecret() {
    console.log("Starting test...");
    const embedUrl = "https://embed14.streamc.xyz/embed.php?hash=30fa9e72a99c1cb3dabdf8a2e4222061";
    const res1 = await fetch(embedUrl, { headers: { 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://phim.nguonc.com/' } });
    const html = await res1.text();
    const obfMatch = html.match(/data-obf="([^"]+)"/);
    const obfData = JSON.parse(Buffer.from(obfMatch[1], 'base64').toString('utf-8'));
    const sUb = obfData.sUb;

    console.log("Got sUb:", sUb.substring(0, 20));

    const jsRes = await fetch("https://embed14.streamc.xyz/player.js?ver=1.8", { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const jsCode = await jsRes.text();

    const mockJw = {
        setup: function(cfg) {
            console.log("🔥 JWPLAYER SETUP CALLED WITH CFG:", cfg);
            return mockJw;
        },
        on: function(evt, fn) { return mockJw; }
    };

    const winObj = {
        location: { href: embedUrl, origin: "https://embed14.streamc.xyz" },
        streamURL: '/' + sUb + '?d=1',
        videoHash: obfData.hD,
        jwplayer: () => mockJw
    };

    const winProxy = new Proxy(winObj, {
        get: (target, prop) => {
            if (prop in target) return target[prop];
            if (typeof prop === 'string' && (prop.endsWith('er') || prop.includes('jw'))) {
                return () => mockJw;
            }
            return undefined;
        }
    });

    let domListener = null;

    const docObj = {
        addEventListener: (evt, fn) => {
            console.log("Registered doc listener:", evt);
            if (evt === 'DOMContentLoaded') domListener = fn;
        },
        getElementById: () => ({
            dataset: { obf: obfMatch[1] },
            appendChild: () => {},
            style: {}
        }),
        querySelector: () => null,
        querySelectorAll: () => []
    };

    const origImportKey = globalThis.crypto.subtle.importKey.bind(globalThis.crypto.subtle);
    const origDigest = globalThis.crypto.subtle.digest.bind(globalThis.crypto.subtle);
    const origDecrypt = globalThis.crypto.subtle.decrypt.bind(globalThis.crypto.subtle);

    const customSubtle = {
        importKey: async (...args) => {
            console.log("👉 importKey:", args[0], args[1] instanceof Uint8Array ? Buffer.from(args[1]).toString('utf-8') : args[1], args[2]);
            return origImportKey(...args);
        },
        digest: async (...args) => {
            console.log("👉 digest:", args[0]);
            return origDigest(...args);
        },
        decrypt: async (...args) => {
            console.log("👉 decrypt:", args[0]);
            const res = await origDecrypt(...args);
            const text = new TextDecoder().decode(res);
            console.log("🎉 DECRYPTED M3U8 RESULT:\n", text.substring(0, 600));
            return res;
        }
    };

    const customFetch = async (url, opts) => {
        let fullUrl = url;
        if (url.startsWith('/')) {
            fullUrl = `https://embed14.streamc.xyz${url}`;
        }
        console.log("📡 Fetching:", fullUrl);
        opts = opts || {};
        opts.headers = opts.headers || {};
        opts.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)';
        opts.headers['Referer'] = embedUrl;
        return fetch(fullUrl, opts);
    };

    const sandbox = {
        console: console,
        fetch: customFetch,
        crypto: { subtle: customSubtle },
        TextEncoder: TextEncoder,
        TextDecoder: TextDecoder,
        atob: atob,
        btoa: btoa,
        Buffer: Buffer,
        document: docObj,
        window: winProxy,
        navigator: { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', platform: 'Win32' },
        devtoolsDetector: { launch: () => {}, addListener: () => {}, isSupported: false },
        setTimeout: setTimeout,
        clearTimeout: clearTimeout,
        setInterval: () => 1,
        clearInterval: () => {}
    };

    const context = vm.createContext(sandbox);
    vm.runInContext(jsCode, context);

    if (domListener) {
        console.log("Calling domListener...");
        await domListener();
    }
}

findSecret().catch(console.error);
