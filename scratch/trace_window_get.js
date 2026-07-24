const vm = require('vm');

async function traceWindow() {
    const embedUrl = "https://embed18.streamc.xyz/embed.php?hash=99f386254c018729b4e6a32ac08029f2";
    const res1 = await fetch(embedUrl, { headers: { 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://phim.nguonc.com/' } });
    const html = await res1.text();
    const obfMatch = html.match(/data-obf="([^"]+)"/);
    const obfData = JSON.parse(Buffer.from(obfMatch[1], 'base64').toString('utf-8'));

    const jsRes = await fetch("https://embed18.streamc.xyz/player.js?ver=1.8", { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const jsCode = await jsRes.text();

    let decryptedM3u8Text = null;

    const mockJw = {
        setup: (cfg) => mockJw,
        on: () => mockJw
    };

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
                    decryptedM3u8Text = blob._buffer.toString('utf-8');
                }
                return "blob:https://embed18.streamc.xyz/fake-m3u8";
            },
            revokeObjectURL: () => {}
        }
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

    const fakeElement = {
        dataset: { obf: obfMatch[1] },
        appendChild: () => {},
        style: {},
        setAttribute: () => {},
        addEventListener: () => {}
    };

    const docObj = {
        getElementById: () => fakeElement,
        querySelector: () => fakeElement,
        querySelectorAll: () => [fakeElement],
        createElement: () => fakeElement,
        addEventListener: () => {}
    };

    const docProxy = new Proxy(docObj, {
        get: (target, prop) => {
            if (prop in target) return target[prop];
            if (typeof prop === 'string' && prop.endsWith('er')) {
                return () => fakeElement;
            }
            return () => {};
        }
    });

    const customFetch = async (url, opts) => {
        let fullUrl = url;
        if (url.startsWith('/')) fullUrl = `https://embed18.streamc.xyz${url}`;
        opts = opts || {};
        opts.headers = opts.headers || {};
        opts.headers['User-Agent'] = 'Mozilla/5.0';
        opts.headers['Referer'] = embedUrl;
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
        window: winProxy,
        navigator: { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', platform: 'Win32' },
        devtoolsDetector: { launch: () => {}, addListener: () => {}, isSupported: true },
        setTimeout: (fn, delay) => setTimeout(fn, 5),
        clearTimeout: () => {},
        setInterval: () => 1,
        clearInterval: () => {}
    };

    const context = vm.createContext(sandbox);
    vm.runInContext(jsCode, context);

    for (let i = 0; i < 40; i++) {
        if (decryptedM3u8Text) break;
        await new Promise(r => setTimeout(r, 50));
    }

    if (decryptedM3u8Text) {
        process.stdout.write("DECRYPTED M3U8 RESULT:\n" + decryptedM3u8Text.substring(0, 800));
    } else {
        process.stdout.write("DECRYPT FAILED (NULL)");
    }
}

traceWindow().catch(err => process.stderr.write(String(err)));
