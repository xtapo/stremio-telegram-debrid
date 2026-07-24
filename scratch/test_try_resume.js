const vm = require('vm');

async function testTryResume() {
    process.stdout.write("Starting testTryResume...\n");
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
        importKey: async (...args) => origImportKey(...args),
        digest: async (...args) => origDigest(...args),
        decrypt: async (...args) => {
            const res = await origDecrypt(...args);
            decryptedText = new TextDecoder().decode(res);
            process.stdout.write("\n🎉 DECRYPTED PLAINTEXT M3U8 SUCCESS! Length: " + decryptedText.length + "\n");
            process.stdout.write("Snippet:\n" + decryptedText.substring(0, 500) + "\n");
            return res;
        }
    };

    const mockJw = { setup: () => mockJw, on: () => mockJw };

    class CustomBlob {
        constructor(parts, options) {
            const bufParts = parts.map(p => typeof p === 'string' ? Buffer.from(p) : Buffer.from(p));
            this._buffer = Buffer.concat(bufParts);
            this.size = this._buffer.length;
            this.type = options ? options.type : '';
            decryptedText = this._buffer.toString('utf-8');
            process.stdout.write("🎉 CustomBlob captured decrypted M3U8! Length: " + decryptedText.length + "\n");
        }
        async text() {
            return this._buffer.toString('utf-8');
        }
    }

    const winObj = {
        location: { href: embedUrl, origin: "https://embed18.streamc.xyz", reload: () => {} },
        streamURL: '/' + obfData.sUb + '?d=1',
        videoHash: obfData.hD,
        jwplayer: () => mockJw,
        Blob: CustomBlob,
        URL: {
            createObjectURL: (blob) => {
                if (blob && blob._buffer) {
                    decryptedText = blob._buffer.toString('utf-8');
                }
                return "blob:https://embed18.streamc.xyz/fake-m3u8";
            },
            revokeObjectURL: () => {}
        },
        addEventListener: (evt, fn) => {
            process.stdout.write("win.addEventListener: " + evt + "\n");
            if (typeof fn === 'function') setTimeout(fn, 10);
        }
    };

    const winProxy = new Proxy(winObj, {
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
        createElement: () => fakeElement,
        addEventListener: (evt, fn) => {
            process.stdout.write("doc.addEventListener: " + evt + "\n");
            if (typeof fn === 'function') setTimeout(fn, 10);
        }
    };
    const docProxy = new Proxy(docObj, {
        get: (target, prop) => prop in target ? target[prop] : () => fakeElement
    });

    const customFetch = async (url, opts) => {
        let fullUrl = url;
        if (url.startsWith('/')) fullUrl = `https://embed18.streamc.xyz${url}`;
        process.stdout.write("📡 Fetching: " + fullUrl + "\n");
        opts = opts || {};
        opts.headers = opts.headers || {};
        opts.headers['User-Agent'] = 'Mozilla/5.0';
        opts.headers['Referer'] = embedUrl;
        return fetch(fullUrl, opts);
    };

    const sandbox = {
        console: { log: (...args) => process.stdout.write(args.join(' ') + '\n'), error: (...args) => process.stderr.write(args.join(' ') + '\n') },
        fetch: customFetch,
        crypto: { subtle: customSubtle },
        TextEncoder: TextEncoder,
        TextDecoder: TextDecoder,
        atob: atob,
        btoa: btoa,
        Buffer: Buffer,
        document: docProxy,
        window: winProxy,
        navigator: { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', platform: 'Win32' },
        devtoolsDetector: { launch: () => {}, addListener: () => {}, isSupported: true },
        setTimeout: setTimeout,
        clearTimeout: () => {},
        setInterval: () => 1,
        clearInterval: () => {}
    };

    const context = vm.createContext(sandbox);
    vm.runInContext(jsCode, context);

    for (let i = 0; i < 40; i++) {
        if (decryptedText) break;
        await new Promise(r => setTimeout(r, 100));
    }
}

testTryResume().catch(err => process.stderr.write(String(err)));
