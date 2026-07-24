const fs = require('fs');

async function findStorageKey() {
    const jsRes = await fetch("https://embed18.streamc.xyz/player.js?ver=1.8", { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const jsCode = await jsRes.text();

    const idx = jsCode.indexOf("getStorageKey");
    console.log("getStorageKey index:", idx);
    console.log("Code snippet:\n", jsCode.substring(idx - 100, idx + 800));
}

findStorageKey().catch(console.error);
