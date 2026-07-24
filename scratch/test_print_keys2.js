const vm = require('vm');

async function testPrintKeys() {
    const embedUrl = "https://embed18.streamc.xyz/embed.php?hash=99f386254c018729b4e6a32ac08029f2";
    const res1 = await fetch(embedUrl, { headers: { 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://phim.nguonc.com/' } });
    const html = await res1.text();
    const obfMatch = html.match(/data-obf="([^"]+)"/);
    const obfData = JSON.parse(Buffer.from(obfMatch[1], 'base64').toString('utf-8'));

    const jsRes = await fetch("https://embed18.streamc.xyz/player.js?ver=1.8", { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const jsCode = await jsRes.text();

    const origImportKey = globalThis.crypto.subtle.importKey.bind(globalThis.crypto.subtle);
    const origDigest = globalThis.crypto.subtle.digest.bind(globalThis.crypto.subtle);
    const origDecrypt = globalThis.crypto.subtle.decrypt.bind(globalThis.crypto.subtle);

    let decryptedText = null;

    const customSubtle = {
        importKey: async (...args) => {
            if (args[1] instanceof Uint8Array || args[1] instanceof ArrayBuffer) {
                const bytes = new Uint8Array(args[1]);
                console.log("🔥 SUBTLE importKey RAW BYTES STRING:", new TextDecoder().decode(bytes));
            }
            return origImportKey(...args);
        },
        digest: async (...args) => {
            console.log("🔥 SUBTLE digest:", args[0]);
            return origDigest(...args);
        },
        decrypt: async (...args) => {
            console.log("🔥 SUBTLE decrypt:", args[0]);
            const res = await origDecrypt(...args);
            decryptedText = new TextDecoder().decode(res);
            console.log("\n🎉 DECRYPTED PLAINTEXT M3U8 SUCCESS! Length:", decryptedText.length);
            console.log(decryptedText.substring(0, 500));
            return res;
        }
    };

    const mockJw = { setup: () => mockJw, on: () => mockJw };
    let listeners = [];

    const winObj = {
        location: { href: embedUrl, origin: "https://embed18.streamc.xyz" },
        streamURL: '/' + obfData.sUb + '?d=1',
        videoHash: obfData.hD,
        jwplayer: () => mockJw,
        Blob: globalThis.Blob,
        URL: { createObjectURL: () => {}, revokeObjectURL: () => {} },
        addEventListener: (evt, fn) => {
            console.log("Registered window listener:", evt);
            listeners.push(fn);
        }
    };

    const winProxy = new Proxy(winObj, {
        get: (target, prop) => {
            if (prop in target) return target[prop];
            if (typeof prop === 'string' && (prop.endsWith('er') || prop.includes('jw'))) return () => mockJw;
            return undefined;
        }
    });

    const fakeElement = { dataset: { obf: obfMatch[1] }, appendChild: () => {}, style: {}, setAttribute: () => {}, addEventListener: () => {} };
    const docObj = {
        getElementById: () => fakeElement,
        querySelector: () => fakeElement,
        querySelectorAll: () => [fakeElement],
        createElement: () => fakeElement,
        addEventListener: (evt, fn) => {
            console.log("Registered doc listener:", evt);
            listeners.push(fn);
        }
    };
    const docProxy = new Proxy(docObj, { get: (target, prop) => prop in target ? target[prop] : () => fakeElement });

    const customFetch = async (url, opts) => {
        let fullUrl = url;
        if (url.startsWith('/')) fullUrl = `https://embed18.streamc.xyz${url}`;
        console.log("📡 Fetching:", fullUrl);
        opts = opts || {};
        opts.headers = opts.headers || {};
        opts.headers['User-Agent'] = 'Mozilla/5.0';
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
        document: docProxy,
        window: winProxy,
        navigator: { userAgent: 'Mozilla/5.0', platform: 'Win32' },
        devtoolsDetector: { launch: () => {}, addListener: () => {}, isSupported: true },
        setTimeout: setTimeout,
        clearTimeout: () => {},
        setInterval: () => 1,
        clearInterval: () => {}
    };

    const context = vm.createContext(sandbox);
    vm.runInContext(jsCode, context);

    console.log("Total listeners registered:", listeners.length);
    for (const fn of listeners) {
        try {
            console.log("Triggering listener...");
            await fn();
        } catch(e) {
            console.error("Listener error:", e);
        }
    }

    await new Promise(r => setTimeout(r, 1000));
}

testPrintKeys().catch(console.error);
