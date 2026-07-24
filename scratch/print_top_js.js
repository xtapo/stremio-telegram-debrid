const fs = require('fs');

async function printTop() {
    const jsRes = await fetch("https://embed14.streamc.xyz/player.js?ver=1.8", { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const jsCode = await jsRes.text();
    console.log(jsCode.substring(0, 1500));
}

printTop().catch(console.error);
