const fs = require('fs');

async function printBottom() {
    const jsRes = await fetch("https://embed14.streamc.xyz/player.js?ver=1.8", { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const jsCode = await jsRes.text();
    console.log(jsCode.substring(jsCode.length - 2000));
}

printBottom().catch(console.error);
