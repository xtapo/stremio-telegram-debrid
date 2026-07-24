const fs = require('fs');

async function inspectDecryptMethod() {
    const jsRes = await fetch("https://embed18.streamc.xyz/player.js?ver=1.8", { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const jsCode = await jsRes.text();

    const idx = jsCode.indexOf("decryptM3U8");
    console.log("decryptM3U8 index:", idx);
    console.log("Code snippet around decryptM3U8:\n", jsCode.substring(idx - 100, idx + 1500));
}

inspectDecryptMethod().catch(console.error);
