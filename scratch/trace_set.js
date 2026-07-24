const vm = require('vm');

async function traceSet() {
    const embedUrl = "https://embed18.streamc.xyz/embed.php?hash=99f386254c018729b4e6a32ac08029f2";
    const res1 = await fetch(embedUrl, { headers: { 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://phim.nguonc.com/' } });
    const html = await res1.text();
    const obfMatch = html.match(/data-obf="([^"]+)"/);
    const obfData = JSON.parse(Buffer.from(obfMatch[1], 'base64').toString('utf-8'));

    const jsRes = await fetch("https://embed18.streamc.xyz/player.js?ver=1.8", { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const jsCode = await jsRes.text();

    let assignedFns = [];

    const winObj = {
        location: { href: embedUrl, origin: "https://embed18.streamc.xyz" },
        streamURL: '/' + obfData.sUb + '?d=1',
        videoHash: obfData.hD
    };

    const winProxy = new Proxy(winObj, {
        get: (target, prop) => target[prop],
        set: (target, prop, value) => {
            console.log("👉 window SET:", prop, typeof value);
            target[prop] = value;
            if (typeof value === 'function') assignedFns.push(value);
            return true;
        }
    });

    const docObj = {};
    const docProxy = new Proxy(docObj, {
        get: (target, prop) => target[prop],
        set: (target, prop, value) => {
            console.log("👉 doc SET:", prop, typeof value);
            target[prop] = value;
            if (typeof value === 'function') assignedFns.push(value);
            return true;
        }
    });

    const sandbox = {
        console: console,
        fetch: fetch,
        crypto: globalThis.crypto,
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

    console.log("Total assigned functions:", assignedFns.length);
    for (const fn of assignedFns) {
        console.log("Calling assigned function...");
        await fn();
    }
}

traceSet().catch(console.error);
